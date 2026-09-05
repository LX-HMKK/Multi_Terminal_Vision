"""部署端主程序（Jetson Nano 车端）。

职责：
1. 摄像头0 拍画面 → JPEG 压缩 → UDP 发给运算端(服务器) SERVER_IP:SERVER_VIDEO_PORT。
2. 摄像头1 做黑线循迹 → 控制信号 → 串口下发给下位机。
3. 开 TCP 服务监听 NANO_CMD_PORT，接收运算端指令（模式切换 / WASD / 避障动作），
   由中央控制器决定当前真正下发的串口控制字节。

运行（Nano）：
    python -m deployment.nano_car
    SERIAL_PORT=/dev/ttyTHS1 SERVER_IP=192.168.87.77 python -m deployment.nano_car
无硬件联调（本机）：
    SERIAL_PORT=mock python -m deployment.nano_car

协议详见 docs/protocol.md。
"""
from __future__ import annotations

import hmac
import socket
import threading
import time
from dataclasses import dataclass, field

import cv2

from . import config
from .config import setup_logging
from .vision.line_follow import LineFollower
from .device.serial_bridge import make_serial_bridge


@dataclass
class SharedState:
    """多线程共享的车辆控制状态。"""
    mode: int = config.MODE_AUTO                # 控制模式
    cmd: str = ""                                # 最近一条外部指令(wasd/避障)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set_mode(self, mode: int) -> None:
        with self.lock:
            self.mode = mode
            self.cmd = ""

    def set_cmd(self, cmd: str) -> None:
        with self.lock:
            self.cmd = cmd

    def snapshot(self) -> tuple[int, str]:
        with self.lock:
            return self.mode, self.cmd


def jpeg_compress(frame, quality: int = config.JPEG_QUALITY) -> bytes:
    """JPEG 压缩，若单帧超过 UDP 上限则逐步降质重压。"""
    q = quality
    for _ in range(config.MAX_COMPRESS_TRIES):
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        if ok and len(buf) <= config.UDP_MAX_FRAME:
            return buf.tobytes()
        q = max(20, q - 10)
    # 兜底：不超限时直接用最后结果
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    return buf.tobytes() if ok else b""


def video_sender(state: SharedState, logger) -> None:
    """摄像头0 → JPEG → UDP 发送给运算端。"""
    cam = cv2.VideoCapture(config.CAM0_ID)
    if not cam.isOpened():
        logger.warning("摄像头%d 无法打开，跳过图传线程", config.CAM0_ID)
        return
    logger.info("图传已打开 camera%d", config.CAM0_ID)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (config.SERVER_IP, config.SERVER_VIDEO_PORT)
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                logger.warning("图传读取失败")
                time.sleep(0.2)
                continue
            data = jpeg_compress(frame)
            if data:
                sock.sendto(data, addr)
            time.sleep(0.03)   # ~30fps，避免打爆网卡
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        cam.release()
        logger.info("图传线程结束")


# ---- 中央控制器：决定当前下发哪个控制字节 ----

def decide_control(mode: int, cmd: str, line: str) -> str | None:
    """输入模式、最近外部指令、最近循迹结果，返回控制信号名或 None(保持不动)。

    语义名保证与模式无关，字节映射在 serial_bridge 里按语义查表。
    模式语义（与 docs/protocol.md 一致）：
      0 自动循迹 / 1 手动 WASD / 2 避障 / 3 关闭避障-恢复循迹
    """
    if mode == config.MODE_WASD:
        return cmd if cmd in ("w", "a", "s", "d", "f", "g") else None
    if mode == config.MODE_AVOID:
        # 避障动作优先（'no' 表示无行人 → 继续循迹）
        mapping = {"left": "avoid_left", "right": "avoid_right",
                   "detour": "detour", "stop": "stop"}
        if cmd in mapping:
            return mapping[cmd]
        return line
    # 自动循迹(0) / 恢复循迹(3)：一律以循迹为底
    return line


def control_thread(state: SharedState, bridge, line_follower: LineFollower, logger) -> None:
    """循迹 + 决策 + 串口下发。"""
    cam = cv2.VideoCapture(config.CAM1_ID)
    has_cam = cam.isOpened()
    if not has_cam:
        logger.warning("循迹摄像头%d 无法打开，关闭循迹，但仍以外部指令控制", config.CAM1_ID)

    last_send = 0.0
    try:
        while True:
            line = "straight"
            if has_cam:
                ok, frame = cam.read()
                if ok:
                    line = line_follower.process(frame)
            mode, cmd = state.snapshot()
            signal = decide_control(mode, cmd, line)
            now = time.time()
            if signal is not None and (now - last_send) >= config.LINE_FOLLOW_INTERVAL:
                bridge.send_control(signal)
                logger.info("下发信号: %s (mode=%d, cmd=%r)", signal, mode, cmd)
                last_send = now
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if has_cam:
            cam.release()
        logger.info("控制线程结束")


def command_server(state: SharedState, bridge, logger) -> None:
    """TCP 服务：接收运算端指令，更新共享状态。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # ---- 接口 fail-closed：绝不静默回退到 0.0.0.0 ----
    bind_addr = config.COMMAND_BIND or config.NANO_IP
    try:
        srv.bind((bind_addr, config.NANO_CMD_PORT))
        bound = bind_addr
    except OSError as exc:
        if config.ALLOW_UNSAFE:
            logger.warning("绑定 %s:%d 失败(%s)，因显式 ALLOW_UNSAFE=1 回退到 0.0.0.0！"
                           "仅限开发机，切勿在生产暴露。", bind_addr, config.NANO_CMD_PORT, exc)
            srv.bind(("0.0.0.0", config.NANO_CMD_PORT))
            bound = "0.0.0.0"
        else:
            logger.error("无法绑定 %s:%d（%s）。为安全起见指令服务已拒绝启动。\n"
                         "   - 真机请确保 NANO_IP 为本机地址；开发联调请设 COMMAND_BIND=127.0.0.1（回环）\n"
                         "   - 确要全网卡暴露可显式设 ALLOW_UNSAFE=1。",
                         bind_addr, config.NANO_CMD_PORT, exc)
            return
    srv.listen(2)
    logger.info("指令服务监听 %s:%d", bound, config.NANO_CMD_PORT)
    if not config.SHARED_TOKEN:
        logger.warning("指令服务未启用鉴权（默认信任局域网）。对外/生产建议两端设相同 NANO_TOKEN。")

    try:
        while True:
            conn, addr = srv.accept()
            logger.info("运算端已连接: %s", addr)
            # 每连接一个线程，避免单个客户端长期占住监听，阻塞新的连接
            threading.Thread(target=handle_client, args=(state, conn, addr, logger),
                             daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        logger.info("指令服务线程结束")


def handle_client(state: SharedState, conn, addr, logger) -> None:
    """处理单个运算端连接。addr 来自 accept，避免对已关闭的 socket 调用 getpeername。"""
    conn.settimeout(1.0)
    buf = b""
    authed = not config.SHARED_TOKEN            # 未设令牌时默认信任局域网
    fail_count = 0
    try:
        while True:
            try:
                chunk = conn.recv(1024)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            # 按行分帧：完整换行才算一条完整指令
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                if not authed:
                    # 鉴权握手：第一行必须是 "AUTH <token>"，用恒定时间比较避免时序侧信道
                    token = line.strip().decode().split(" ", 1)
                    if len(token) == 2 and token[0] == "AUTH" and hmac.compare_digest(token[1], config.SHARED_TOKEN):
                        authed = True
                        logger.info("客户端鉴权成功: %s", addr)
                    else:
                        fail_count += 1
                        if fail_count > 3:
                            logger.warning("鉴权失败次数过多，断开: %s", addr)
                            return
                    continue
                apply_command(state, line.decode().strip(), logger)
        # 连接关闭：处理残留的最后一条未换行指令（仅已鉴权时）
        if buf.strip() and authed:
            apply_command(state, buf.decode().strip(), logger)
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass
        logger.info("运算端连接断开: %s", addr)


def apply_command(state: SharedState, cmd: str, logger) -> None:
    """把一条指令写入共享状态。"""
    if not cmd:
        return
    if cmd in ("0", "1", "2", "3"):
        mode = int(cmd)
        state.set_mode(mode)
        logger.info("控制模式 -> %d", mode)
        return
    # 其余为控制字（wasd / 避障动作），记录到状态，由控制线程按模式解释
    state.set_cmd(cmd)
    logger.info("外部指令 %r", cmd)


def main() -> None:
    logger = setup_logging()
    logger.info("===== 部署端(nano)启动 =====")
    logger.info("串口=%s, UDP->%s:%d, TCP监听:%s:%d",
                config.SERIAL_PORT, config.SERVER_IP, config.SERVER_VIDEO_PORT,
                config.NANO_IP, config.NANO_CMD_PORT)

    bridge = make_serial_bridge(logger=logger)
    state = SharedState()
    line_follower = LineFollower(logger=logger)

    threads = [
        threading.Thread(target=video_sender, args=(state, logger), daemon=True),
        threading.Thread(target=command_server, args=(state, bridge, logger), daemon=True),
        threading.Thread(target=control_thread, args=(state, bridge, line_follower, logger), daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到退出信号...")
    finally:
        bridge.close()
        logger.info("===== 部署端退出 =====")


if __name__ == "__main__":
    main()
