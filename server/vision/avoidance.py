"""避障决策模块（运算端）。

从原 serve+yolo+detect.py 中抽出：按最大目标的位置（左/中/右区）与面积阈值
生成动作 left / right / detour / no，并加入节流 + 动作变化约束，降低抖动与误触发。

纯逻辑，不依赖网络——便于单元测试与复用到其它传感器方案。
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Detection:
    """单帧中一个被跟踪目标。"""
    track_id: int
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def area(self) -> int:
        return (self.x2 - self.x1) * (self.y2 - self.y1)

    @property
    def center_x(self) -> int:
        return (self.x1 + self.x2) // 2


def pick_largest(detections: list[Detection]) -> Detection | None:
    """返回面积最大的目标（决定避障对象）。"""
    if not detections:
        return None
    return max(detections, key=lambda d: d.area)


def decide_action(target: Detection | None, frame_width: int,
                  small_area_threshold: int,
                  mode: int) -> str:
    """根据最大目标位置与面积生成动作。

    规则：
      - 目标为空或面积未达阈值 → 'no'（无避让）
      - 目标在画面左 1/3 → 'right'（向右绕）
      - 目标在画面右 1/3 → 'left'
      - 目标居中 → 'detour'
    仅在避障模式(mode==2)下有避让行为，否则一律 'no'。
    """
    if mode != 2:
        return "no"
    if target is None or target.area < small_area_threshold:
        return "no"
    left_threshold = frame_width // 3
    right_threshold = (frame_width * 2) // 3
    cx = target.center_x
    if cx < left_threshold:
        return "right"
    if cx > right_threshold:
        return "left"
    return "detour"


class ActionThrottle:
    """节流 + 仅变化才发送，避免相同动作高频下发。"""

    def __init__(self, interval: float):
        self._interval = interval
        self._last_time = 0.0
        self._last_action: str | None = None

    def should_send(self, action: str) -> bool:
        """动作相对上一次发生变化，且距上次发送超过间隔时，才允许发送。

        相同动作不重复下发（避免刷屏），动作变化但未到间隔则不发送（去抖动）。
        """
        now = time.time()
        if action != self._last_action and (now - self._last_time) >= self._interval:
            self._last_action = action
            self._last_time = now
            return True
        return False
