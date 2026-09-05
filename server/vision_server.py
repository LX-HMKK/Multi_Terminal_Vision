"""运算端主程序（笔记本电脑 / 服务器）。

职责：
1. 接收视频帧（默认 UDP 来自部署端 nano；也可 webcam / video / synthetic）。
2. YOLO 检测 + 跟踪（ultralytics，替代原 yolov5+SORT）。
3. 目标生命周期事件（ID_xx_start / ID_xx_end）通过 TCP 发给上位机 Q。
4. 按最大目标位置与面积生成避障动作（left/right/detour/no），节流后经 TCP 发 nano。
5. 把带标注的画面经 UDP 回传上位机显示。
6. 接收上位机指令（0/1/2/3、w/a/s/d），更新模式并转发 nano。

帧源与网络链路拆到独立模块：
    server.sources  帧来源抽象（udp / webcam / video / synthetic）
    server.net      网络收发 + 指令分发（TCPSender / UDPSender / TrackState / HostCommandHandler）
本文件保留检测胶水（load_model / track_frame / draw_frame / jpeg_compress）与主循环。

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
import time

import cv2

from . import config
from .config import setup_logging
from .avoidance import Detection, pick_largest, decide_action, ActionThrottle
from .sources import build_source
from .net import TCPSender, UDPSender, TrackState, HostCommandHandler


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
    source = build_source(args, logger)
    try:
        model = load_model(logger)
    except Exception as exc:  # noqa: BLE001
        logger.error("模型加载失败（请 pip install ultralytics 并确保可联网下载权重）: %s", exc)
        source.close()
        return

    # ---- 网络链路 ----
    nano = TCPSender(config.NANO_IP, config.NANO_CMD_PORT, logger, "nano",
                     auth_line=("AUTH " + config.NANO_TOKEN) if config.NANO_TOKEN else None)
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
            if frame.shape[0] > 1080:   # 限制分辨率，避免推理过慢
                scale = 1080 / frame.shape[0]
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), 1080))

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
            action = decide_action(largest, frame.shape[1], config.SMALL_AREA_THRESHOLD, mode)
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
