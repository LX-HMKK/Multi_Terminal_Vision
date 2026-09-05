"""依赖无关的快速冒烟测试：验证核心纯逻辑。

覆盖：
- computation: 避障决策 decide_action / pick_largest / ActionThrottle
- 部署端: 串口信号映射 config.SIGNALS / decide_control（需 cv2，缺则跳过系统级部分）

运行：
    python tools/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_avoidance():
    from server.vision.avoidance import Detection, decide_action, pick_largest, ActionThrottle
    from server import config as scfg

    dets = [
        Detection(1, 0, 0, 100, 100),       # 左侧，面积10000
        Detection(2, 480, 0, 640, 100),     # 右侧（最大的）
    ]
    biggest = pick_largest(dets)
    assert biggest.track_id == 2, "应选出最大目标"

    # 左/中/右分区
    assert decide_action(Detection(3, 0, 0, 30, 100), 600, 1, 2) == "right"
    assert decide_action(Detection(3, 300, 0, 330, 100), 600, 1, 2) == "detour"
    assert decide_action(Detection(3, 500, 0, 580, 100), 600, 1, 2) == "left"

    # 面积不足 / 非避障模式 → no
    assert decide_action(Detection(3, 0, 0, 10, 10), 600, 60000, 2) == "no"
    assert decide_action(biggest, 600, 1, 1) == "no"

    # 节流+仅变化
    th = ActionThrottle(0.5)
    first = th.should_send("left")
    again_same = th.should_send("left")       # 相同动作不再发
    assert first and not again_same, "同动作不应重复发送"
    print("[ok] server.avoidance")


def test_serial_mapping():
    from deployment import config as dcfg
    assert dcfg.SIGNALS["straight"] == 2
    assert dcfg.SIGNALS["avoid_left"] == 7
    assert dcfg.SIGNALS["avoid_right"] == 8
    assert dcfg.SIGNALS["detour"] == 5
    assert dcfg.SIGNALS["stop"] == 6
    assert dcfg.CTRL_TRAIL == 0x43
    print("[ok] deployment.serial mapping")


def test_decide_control():
    from deployment import config as dcfg
    from deployment.nano_car import decide_control
    # 手动 WASD
    assert decide_control(dcfg.MODE_WASD, "w", "straight") == "w"
    assert decide_control(dcfg.MODE_WASD, "x", "straight") is None
    # 避障模式：动作优先
    assert decide_control(dcfg.MODE_AVOID, "right", "straight") == "avoid_right"
    assert decide_control(dcfg.MODE_AVOID, "detour", "straight") == "detour"
    assert decide_control(dcfg.MODE_AVOID, "stop", "straight") == "stop"
    assert decide_control(dcfg.MODE_AVOID, "no", "straight") == "straight"
    # 自动循迹 / 关闭避障(恢复)：以循迹为底
    assert decide_control(dcfg.MODE_AUTO, "", "left") == "left"
    assert decide_control(dcfg.MODE_RESUME, "", "straight") == "straight"
    assert decide_control(dcfg.MODE_RESUME, "right", "straight") == "straight"
    print("[ok] nano_car.decide_control")


def main() -> int:
    test_avoidance()
    test_serial_mapping()
    try:
        test_decide_control()
    except ImportError:
        print("[skip] decide_control 需要 cv2，已跳过")
    print("\nALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
