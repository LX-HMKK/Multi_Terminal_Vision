"""黑线循迹模块（部署端）。

从原 All_IN.py 的 road_follow() 中抽出：取摄像头下半部分画面，
灰度化 + 高斯滤波 + 阈值分割 + 腐蚀膨胀，统计左右两半 **亮像素区面积**，
生成控制信号名（sharp_left / left / straight / right / sharp_right / stop）。

> 说明：沿用原实现的 `THRESH_BINARY`（亮=255），变量名里的 "black" 实为
> 亮像素。此处保持与原逻辑一致（左右面积比较），若要反转可自行调整阈值方向，
> 见 docs/known-issues.md。
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from . import config


class LineFollower:
    """单帧黑线循迹决策器。纯函数式，便于与摄像头解耦、单元测试。"""

    def __init__(self, threshold: int = config.LINE_THRESHOLD, logger: Optional[logging.Logger] = None):
        self._threshold = threshold
        self._logger = logger or config.setup_logging("line_follow")
        # 腐蚀膨胀核
        self._kernel = np.ones((5, 5), np.uint8)

    def process(self, frame: np.ndarray) -> str:
        """输入一帧 BGR 图像，输出控制信号名（停止时 'stop'）。"""
        height, width = frame.shape[:2]
        # 只保留上半部分画面（道路黑线通常在上方）
        upper_half = frame[: height // 2, :]

        blurred = cv2.GaussianBlur(upper_half, (5, 5), 0)
        gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, self._threshold, 255, cv2.THRESH_BINARY)

        eroded = cv2.erode(binary, self._kernel, iterations=1)
        dilated = cv2.dilate(eroded, self._kernel, iterations=1)

        half_h, half_w = dilated.shape
        left_half = dilated[:, : half_w // 2]
        right_half = dilated[:, half_w // 2:]

        left_black = int(np.sum(left_half == 255))
        right_black = int(np.sum(right_half == 255))
        total = half_w * half_h

        if left_black == 0 and right_black == 0:
            return "stop"
        if left_black > right_black * 1.5:
            return "sharp_right"
        if left_black > right_black:
            return "right"
        if abs(left_black - right_black) <= total * 0.05:
            return "straight"
        if right_black > left_black * 1.3:
            return "sharp_left"
        if right_black > left_black:
            return "left"
        return "straight"

    @staticmethod
    def _annotate(frame: np.ndarray, dilated: Optional[np.ndarray] = None) -> np.ndarray:
        """(可选) 叠加处理结果用于本地调试视频。"""
        out = frame.copy()
        if dilated is not None:
            h, w = frame.shape[:2]
            half = dilated[: h // 2, :]
            out[: h // 2, :] = cv2.cvtColor(half, cv2.COLOR_GRAY2BGR)
        return out

    def close(self) -> None:
        pass
