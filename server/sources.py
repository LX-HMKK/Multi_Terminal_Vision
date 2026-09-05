"""帧来源抽象（运算端）。

从原 vision_server 中拆出：统一的帧来源接口 + 四种实现 + 选择工厂。
纯帧 I/O，不涉及检测/网络逻辑——便于替换帧源与单元测试。

帧源：
    udp      (默认) 从部署端 nano 接收 JPEG 视频帧
    webcam   本地摄像头
    video    视频文件
    synthetic 合成帧源（无硬件时跑通链路）
"""
from __future__ import annotations

import socket

import cv2
import numpy as np

from . import config


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

    def close(self) -> None:
        self._sock.close()


class VideoCaptureSource(FrameSource):
    """摄像头(cam_id)或视频文件(path)统一帧源。
    cv2.VideoCapture 对 int(设备号) 与 str(路径) 皆可，故两者共用一个类。
    """

    def __init__(self, path_or_id, logger):
        self._cap = cv2.VideoCapture(path_or_id)
        self._logger = logger
        if not self._cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {path_or_id}")

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        return frame if ok else None

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


def build_source(args, logger) -> FrameSource:
    """按命令行选择帧源。"""
    if args.source == "udp":
        return UdpVideoSource(config.SERVER_VIDEO_PORT, logger)
    if args.source == "webcam":
        return VideoCaptureSource(args.cam, logger)
    if args.source == "video":
        return VideoCaptureSource(args.input, logger)
    if args.source == "synthetic":
        return SyntheticSource(logger=logger)
    raise ValueError(f"未知帧源: {args.source}")
