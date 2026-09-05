"""部署端（Jetson Nano）运行配置。

所有网络/串口/图像参数均可通过环境变量覆盖，方便在开发机上无硬件联调：

    SERVER_IP       运算端(服务器) IP，默认 192.168.87.77
    NANO_IP         本机(nano) IP，默认 192.168.87.102
    SERVER_VIDEO_PORT  nano 向运算端发送视频的 UDP 端口，默认 5552
    NANO_CMD_PORT   本机接收运算端指令的 TCP 端口，默认 12345
    SERIAL_PORT     串口设备，默认 /dev/ttyTHS1；设 "mock" 则用日志伪串口
    CAM0_ID         摄像图传用摄像头编号
    CAM1_ID         黑线循迹用摄像头编号
"""
from __future__ import annotations

import os
import logging

# ---- 网络 ----
SERVER_IP = os.environ.get("SERVER_IP", "192.168.87.77")
NANO_IP = os.environ.get("NANO_IP", "192.168.87.102")
SERVER_VIDEO_PORT = int(os.environ.get("SERVER_VIDEO_PORT", "5552"))
NANO_CMD_PORT = int(os.environ.get("NANO_CMD_PORT", "12345"))

# 指令服务绑定地址：默认 NANO_IP（仅暴露在该网卡）。
# 若该 IP 无法绑定（如开发机），默认“失败即关闭”，绝不静默回退到 0.0.0.0 暴露全网卡。
# 仅当显式设 ALLOW_UNSAFE=1 时才回退到 0.0.0.0（会打印醒目告警）；开发建议设 COMMAND_BIND=127.0.0.1 回环。
COMMAND_BIND = os.environ.get("COMMAND_BIND", "")
ALLOW_UNSAFE = os.environ.get("ALLOW_UNSAFE", "") == "1"   # 显式开关，才允许 0.0.0.0 暴露
# 可选共享令牌：为空 = 不鉴权（默认信任局域网，启动会告警）；建议对外/生产两端设相同 NANO_TOKEN。
SHARED_TOKEN = os.environ.get("NANO_TOKEN", "")

# ---- 串口 ----
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyTHS1")
BAUDRATE = 115200
# "mock" 时使用日志伪串口（无硬件也能跑通指令链路）
MOCK_SERIAL = SERIAL_PORT.lower() == "mock"

# ---- 图像 / 循迹 ----
CAM0_ID = int(os.environ.get("CAM0_ID", "0"))   # 图传视频
CAM1_ID = int(os.environ.get("CAM1_ID", "1"))   # 黑线循迹
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "89"))
UDP_MAX_FRAME = 65500                      # 单帧 JPEG 上限，超出则降质重压
MAX_COMPRESS_TRIES = 4
LINE_THRESHOLD = 90                        # 黑线二值化阈值
LINE_FOLLOW_INTERVAL = 0.5                 # 循迹控制信号发送间隔秒

# ---- 日志 ----
def setup_logging(name: str = "nano_car") -> logging.Logger:
    """创建一个带统一格式的 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
        logger.addHandler(handler)
    return logger


# ---- 串口控制字节（第二字节固定为 0x43，与下位机固件约定）----
# 数值取自原 All_IN.py，不同模式语义不同，由下位机固件按模式解释。
CTRL_TRAIL = 0x43                       # 帧尾/类型字节

# 黑线循迹方向（自动模式）
LINE_SHARP_LEFT = 0
LINE_LEFT = 1
LINE_STRAIGHT = 2
LINE_RIGHT = 3
LINE_SHARP_RIGHT = 4

# 避障动作
DETOUR = 5
STOP = 6
AVOID_LEFT = 7
AVOID_RIGHT = 8

# WASD 手动
WASD_W = 9
WASD_A = 10
WASD_S = 11
WASD_D = 12
WASD_F = 13
WASD_G = 15

# 语义 -> 字节
SIGNALS = {
    "sharp_left": LINE_SHARP_LEFT,
    "left": LINE_LEFT,          # 循迹向左
    "straight": LINE_STRAIGHT,
    "right": LINE_RIGHT,        # 循迹向右
    "sharp_right": LINE_SHARP_RIGHT,
    "detour": DETOUR,
    "stop": STOP,
    "avoid_left": AVOID_LEFT,
    "avoid_right": AVOID_RIGHT,
    "w": WASD_W,
    "a": WASD_A,
    "s": WASD_S,
    "d": WASD_D,
    "f": WASD_F,
    "g": WASD_G,
}

# ---- 控制模式 ----
MODE_AUTO = 0       # 自动循迹
MODE_WASD = 1       # 手动 WASD
MODE_AVOID = 2      # 避障（箭头/遥控）
MODE_RESUME = 3     # 关闭避障 → 恢复循迹（并非停车；停车用避障动作 'stop'）
