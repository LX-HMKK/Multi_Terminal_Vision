"""运算端主程序（笔记本电脑 / 服务器）。

职责：
1. 接收视频帧（默认 UDP 来自部署端 nano；也可 webcam / video / synthetic）。
2. YOLO 检测 + 跟踪（ultralytics，替代原 yolov5+SORT）。
3. 目标生命周期事件（ID_xx_start / ID_xx_end）通过 TCP 发给上位机 Q。
4. 按最大目标位置与面积生成避障动作（left/right/detour/no），节流后经 TCP 发 nano。
5. 把带标注的画面经 UDP 回传上位机显示。
6. 接收上位机指令（0/1/2/3、w/a/s/d），更新模式并转发 nano。

运行：
    # 与真实的 nano + Q 上位机
    python -m server.vision_server
    # 本机无硬件 demo（合成帧源，检测靠模型，用真实摄像头/视频更佳）
    python -m server.vision_server --source synthetic
    python -m server.vision_server --source webcam
    python -m server.vision_server --source video path/to/video.mp4

协议详见 docs/protocol.md。
"""
from __future__ import annotations

import argparse
import socket
import select
import threading
import time

import cv2
import numpy as np

from . import config
from .config import setup_logging
from .avoidance import Detection, pick_largest, decide_action, ActionThrottle


# --------------------------------------------------------------------------- #
# 帧源抽象
# --------------------------------------------------------------------------- #
class FrameSource:
    """统一的帧来源接口。"""

    def read(self) -> np.ndarray | None:  # pragma: no cover - 抽象
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError


class UdpVideoSource(FrameSource):
    """从部署端 nano 接收 JPEG 视频帧（原架构主链路）。"""

    def __init__(self, port: int, logger):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 绑定所有网卡，避免开发机未配置 192.168.87.77 时绑定失败
        self._sock.bind(("0.0.0.0", port))
        # 非阻塞：没帧时不卡住主循环
        self._sock.settimeout(0.05)
        self._logger = logger
        logger.info("视频接收 UDP 监听 0.0.0.0:%d（服务器 IP %s）", port, config.SERVER_IP)

    def read(self) -> np.ndarray | None:
        try:
            data, _ = self._sock.recvfrom(65535)
        except socket.timeout:
            return None
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        return frame


class WebcamSource(FrameSource):
    """本地摄像头帧源。"""

    def __init__(self, cam_id: int, logger):
        self._cap = cv2.VideoCapture(cam_id)
        self._logger = logger
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 {cam_id}")

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()


class VideoFileSource(FrameSource):
    """视频文件帧源。"""

    def __init__(self, path: str, logger):
        self._cap = cv2.VideoCapture(path)
        self._logger = logger
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开视频 {path}")

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        if ok:
            return frame
        return None   # 播完返回 None

    def close(self) -> None:
        self._cap.release()


class SyntheticSource(FrameSource):
    """合成帧源：画一个高对比度行人剪影在画面中来回移动。

    用于无硬件时跑通整条链路（检测依赖模型对高对比人形的敏感度，
    需要稳定检测建议改用 webcam / 含人的视频文件）。
    """

    def __init__(self, size=(640, 480), logger=None):
        self._w, self._h = size
        self._t = 0.0
        self._logger = logger

    def read(self) -> np.ndarray | None:
        self._t += 0.03
        frame = np.full((self._h, self._w, 3), 235, np.uint8)  # 浅色背景
        # 行人：头 + 躯干 + 腿的剪影，横向来回移动模拟行走
        cx = int(self._w * 0.5 + np.sin(self._t * 2.0) * self._w * 0.35)
        top = self._h // 8
        hgt = self._h // 3
        wid = self._w // 12
        # 躯干
        cv2.rectangle(frame, (cx - wid, top + hgt // 3),
                      (cx + wid, top + hgt), (0, 0, 0), -1)
        # 头
        cv2.circle(frame, (cx, top + hgt // 6), wid, (0, 0, 0), -1)
        # 双腿
        cv2.rectangle(frame, (cx - wid, top + hgt),
                      (cx - wid // 4, top + hgt + self._h // 5), (0, 0, 0), -1)
        cv2.rectangle(frame, (cx + wid // 4, top + hgt),
                      (cx + wid, top + hgt + self._h // 5), (0, 0, 0), -1)
        return frame

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------- #
# 网络链路（自动重连）
# --------------------------------------------------------------------------- #
class TCPSender:
    """自动重连的 TCP 客户端，向 nano / 上位机发送指令（按行分帧，**以 `\\n` 结尾**）。

    线程安全 + 不阻塞设计：
    - 只有后台 `_loop` 线程建立连接，`_sock` 一律在 `_lock` 下读写，杜绝并发 connect。
    - socket 设为**非阻塞**：读线程用 `select` 轮询（0.5s），写用 `select` 等写就绪（1s 上限）。
      因此空闲不会误判为断开、也不会有 3s 超时残留导致抖动；
      未连接/对方无响应时 `send()` 快速返回，不会阻塞主循环。
    - 可选 `recv_handler` 处理收到的完整行（例如上位机指令）；EOF 会 flush 尾部残留。
    """

    def __init__(self, host: str, port: int, logger, name: str, recv_handler=None):
        self._host, self._port, self._name = host, port, name
        self._logger = logger
        self._recv_handler = recv_handler
        self._sock: socket.socket | None = None
        self._stop = False
        self._lock = threading.Lock()
        self._down_log_at = 0.0                 # 降频的连接失败日志

    # ---- 连接生命周期 ----
    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self._stop:
            with self._lock:
                need_connect = self._sock is None
            if need_connect:
                s = self._open()
                if s is not None:
                    self._attach(s)
            time.sleep(1.0)

    def _open(self) -> socket.socket | None:
        try:
            s = socket.create_connection((self._host, self._port), timeout=3.0)
        except OSError as exc:
            if time.time() - self._down_log_at > 5.0:
                self._logger.info("[%s] 连接 %s:%d 失败: %s（持续重连）",
                                  self._name, self._host, self._port, exc)
                self._down_log_at = time.time()
            return None
        s.setblocking(False)                    # 关键：避免 connect 超时残留在已连接 socket 上
        return s

    def _attach(self, s: socket.socket) -> None:
        with self._lock:
            old = self._sock
            self._sock = s
        if old is not None:
            self._safe_close(old)
        self._logger.info("[%s] 连接成功 %s:%d", self._name, self._host, self._port)
        if self._recv_handler:
            threading.Thread(target=self._reader, args=(s,), daemon=True).start()

    def _reader(self, sock: socket.socket) -> None:
        buf = b""
        sock.setblocking(False)
        while not self._stop:
            try:
                r, _, _ = select.select([sock], [], [], 0.5)
            except OSError:
                break
            if not r:
                continue
            try:
                chunk = sock.recv(4096)
            except BlockingIOError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    self._recv_handler(line.decode().strip())
        if buf.strip():                          # EOF 尾部残留 flush
            self._recv_handler(buf.decode().strip())
        with self._lock:
            if self._sock is sock:
                self._sock = None
        self._safe_close(sock)
        self._logger.info("[%s] 连接断开，等待重连", self._name)

    def send(self, text: str) -> bool:
        """发送一行（自动补 `\\n`）。未连接返回 False；最多等 1s 写就绪，不阻塞主循环。"""
        with self._lock:
            s = self._sock
            if s is None:
                return False
        payload = (text + "\n").encode()
        try:
            _, w, _ = select.select([], [s], [], 1.0)
            if not w:
                return False
            s.sendall(payload)
            return True
        except (BlockingIOError, OSError):
            with self._lock:
                if self._sock is s:
                    self._sock = None
            self._safe_close(s)
            return False

    def _safe_close(self, s: socket.socket) -> None:
        try:
            s.close()
        except OSError:
            pass

    def close(self) -> None:
        self._stop = True
        with self._lock:
            s = self._sock
            self._sock = None
        if s is not None:
            self._safe_close(s)


class UDPSender:
    """向指定地址发送 JPEG 帧。"""

    def __init__(self, addr: tuple[str, int], logger):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._addr = addr

    def send_frame(self, jpeg: bytes) -> None:
        self._sock.sendto(jpeg, self._addr)

    def close(self) -> None:
        self._sock.close()


class TrackState:
    """跟踪目标生命周期：新出现/消失目标生成事件。"""

    def __init__(self):
        self._active: dict[int, dict] = {}

    def diff(self, seen_ids: set[int]) -> tuple[list[int], list[int]]:
        """返回 (新出现id, 消失id)。"""
        new_ids = list(seen_ids - set(self._active))
        gone_ids = [tid for tid in self._active if tid not in seen_ids]
        self._active = {tid: {} for tid in seen_ids}
        return new_ids, gone_ids


# --------------------------------------------------------------------------- #
# 指令处理（来自上位机）
# --------------------------------------------------------------------------- #
class HostCommandHandler:
    """处理上位机发来的指令，更新模式并转发 nano。"""

    def __init__(self, mode_holder: dict, nano: TCPSender, logger):
        self._mode_holder = mode_holder
        self._nano = nano
        self._logger = logger

    def __call__(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return
        if cmd in ("0", "1", "2", "3"):
            mode = int(cmd)
            self._mode_holder["mode"] = mode
            self._logger.info("上位机指令：模式 -> %d", mode)
            self._nano.send(cmd)      # 转发模式给 nano
        elif cmd in ("w", "a", "s", "d", "f", "g"):
            self._logger.info("上位机指令：%s", cmd)
            self._nano.send(cmd)
        else:
            self._logger.info("上位机指令：%s（忽略未知）", cmd)


# --------------------------------------------------------------------------- #
# 主逻辑
# --------------------------------------------------------------------------- #
def make_source(args, logger) -> FrameSource:
    if args.source == "udp":
        return UdpVideoSource(config.SERVER_VIDEO_PORT, logger)
    if args.source == "webcam":
        return WebcamSource(args.cam, logger)
    if args.source == "video":
        return VideoFileSource(args.input, logger)
    if args.source == "synthetic":
        return SyntheticSource(logger=logger)
    raise ValueError(f"未知帧源: {args.source}")


def load_model(logger):
    """延迟加载 ultralytics 模型（首次会下载权重）。"""
    from ultralytics import YOLO
    logger.info("加载模型 %s (device=%r)", config.MODEL, config.DEVICE or "auto")
    model = YOLO(config.MODEL)
    logger.info("模型就绪")
    return model


def track_frame(model, frame: np.ndarray):
    """运行一次检测+跟踪，返回 (Detection 列表, track_ids可见集合)。"""
    results = model.track(
        frame, persist=True, classes=config.CLASSES,
        conf=config.CONF_THRES, iou=config.IOU_THRES,
        tracker=config.TRACKER, verbose=False,
    )
    detections: list[Detection] = []
    seen_ids: set[int] = set()
    if not results:
        return detections, seen_ids
    boxes = results[0].boxes
    if boxes is None or boxes.id is None:
        return detections, seen_ids
    ids = boxes.id.int().tolist()
    xyxys = boxes.xyxy.tolist()
    for tid, xyxy in zip(ids, xyxys):
        if tid is None:
            continue
        x1, y1, x2, y2 = (int(v) for v in xyxy)
        seen_ids.add(tid)
        detections.append(Detection(tid, x1, y1, x2, y2))
    return detections, seen_ids


def draw_frame(frame, detections, model_name, fps):
    """在画面上画框与 id。"""
    for d in detections:
        cv2.rectangle(frame, (d.x1, d.y1), (d.x2, d.y2), (0, 255, 0), 2)
        cv2.putText(frame, f"#{d.track_id}", (d.x1, max(20, d.y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(frame, f"{model_name} {fps:>5.1f} FPS", (12, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return frame


def jpeg_compress(frame, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else b""


def run(args, logger) -> None:
    source = make_source(args, logger)
    frame_width = 640
    try:
        model = load_model(logger)
    except Exception as exc:  # noqa: BLE001
        logger.error("模型加载失败（请 pip install ultralytics 并确保可联网下载权重）: %s", exc)
        source.close()
        return

    # ---- 网络链路 ----
    nano = TCPSender(config.NANO_IP, config.NANO_CMD_PORT, logger, "nano")
    mode_holder = {"mode": config.MODE_AVOID}   # 默认避障模式
    handler = HostCommandHandler(mode_holder, nano, logger)
    host = TCPSender(config.QT_IP, config.HOST_CMD_TCP, logger, "host", recv_handler=handler)
    video_q = UDPSender((config.QT_IP, config.HOST_VIDEO_UDP), logger)

    nano.start()
    host.start()
    logger.info("链路：nano=%s:%d, host=%s:%d/%d",
                config.NANO_IP, config.NANO_CMD_PORT,
                config.QT_IP, config.HOST_CMD_TCP, config.HOST_VIDEO_UDP)

    track_state = TrackState()
    throttle = ActionThrottle(config.ACTION_THROTTLE)

    idle = 0   # 连续无帧计数，用于给新手用户一个提示
    try:
        while True:
            frame = source.read()
            if frame is None:
                time.sleep(0.02)
                idle += 1
                if idle == 300:
                    logger.info("仍未收到视频帧（默认 --source udp 监听 %d）。"
                                "无 nano 硬件时可改用 --source synthetic 本地演示。",
                                config.SERVER_VIDEO_PORT)
                continue
            idle = 0
            frame_width = frame.shape[1]
            if frame.shape[0] > 1080:   # 限制分辨率，避免推理过慢
                scale = 1080 / frame.shape[0]
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), 1080))
                frame_width = frame.shape[1]

            st = time.time()
            detections, seen_ids = track_frame(model, frame)
            frame_time = time.time() - st
            fps = 1.0 / frame_time if frame_time > 0 else 0.0

            # ---- 生命周期事件 → 上位机 ----
            new_ids, gone_ids = track_state.diff(seen_ids)
            for tid in new_ids:
                host.send(f"ID_{tid}_start")
                logger.info("目标进入: ID_%d_start", tid)
            for tid in gone_ids:
                host.send(f"ID_{tid}_end")
                logger.info("目标离开: ID_%d_end", tid)

            # ---- 避障动作 → nano（按最大目标 + 节流 + 仅变化）----
            # 'no' 也需下发：目标消失/未达阈值得让车恢复循迹，否则会一直保持上次绕行动作。
            mode = mode_holder.get("mode", config.MODE_AVOID)
            largest = pick_largest(detections)
            action = decide_action(largest, frame_width, config.SMALL_AREA_THRESHOLD, mode)
            if throttle.should_send(action):
                nano.send(action)
                if action != "no":
                    logger.info("避障动作 -> nano: %s (目标#%s)", action,
                                largest.track_id if largest else "?")

            # ---- 回传上位机 ----
            annotated = draw_frame(frame, detections, config.MODEL, fps)
            video_q.send_frame(jpeg_compress(annotated))

            if args.show:
                cv2.imshow("vision_server", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        logger.info("收到退出信号...")
    finally:
        source.close()
        nano.close()
        host.close()
        video_q.close()
        logger.info("===== 运算端退出 =====")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="运算端（YOLO 检测 + 跟踪 + 避障）")
    p.add_argument("--source", default=config.DEFAULT_SOURCE,
                   choices=["udp", "webcam", "video", "synthetic"],
                   help="帧来源：udp(默认,nano) / webcam / video / synthetic")
    p.add_argument("--input", default="", help="video 选项的视频文件路径")
    p.add_argument("--cam", type=int, default=0, help="webcam 摄像头编号")
    p.add_argument("--show", action="store_true", help="本地窗口显示画面")
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    logger = setup_logging()
    logger.info("===== 运算端启动 (source=%s) =====", args.source)
    run(args, logger)


if __name__ == "__main__":
    main()
