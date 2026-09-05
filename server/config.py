"""运算端（服务器）运行配置，可用环境变量覆盖。"""

from __future__ import annotations

import os
import logging

# ---- 网络角色 ----
# 运算端与上位机 Q 通常同机：两者 IP 一致，前往上位机用回环。
SERVER_IP = os.environ.get("SERVER_IP", "192.168.87.77")     # 本机(运算端)
NANO_IP = os.environ.get("NANO_IP", "192.168.87.102")        # 下位机 / 部署端
QT_IP = os.environ.get("QT_IP", "127.0.0.1")                 # 上位机 Qt（默认同机回环）

# 端口
SERVER_VIDEO_PORT = int(os.environ.get("SERVER_VIDEO_PORT", "5552"))  # 本机接收 nano 视频 UDP
NANO_CMD_PORT = int(os.environ.get("NANO_CMD_PORT", "12345"))          # 前往 nano 指令 TCP
HOST_CMD_TCP = int(os.environ.get("HOST_CMD_TCP", "9999"))             # 前往上位机指令 TCP
HOST_VIDEO_UDP = int(os.environ.get("HOST_VIDEO_UDP", "8888"))         # 回传上位机视频 UDP

# ---- 控制模式（与部署端保持一致，见 docs/protocol.md）----
MODE_AUTO = 0       # 自动循迹
MODE_WASD = 1       # 手动 WASD
MODE_AVOID = 2      # 避障
MODE_RESUME = 3     # 关闭避障 → 恢复循迹（非停车）

# ---- YOLO / 跟踪参数 ----
MODEL = os.environ.get("MODEL", "yolov8n.pt")                # ultralytics 权重，可换成 yolov8s.pt
CONF_THRES = float(os.environ.get("CONF_THRES", "0.25"))
IOU_THRES = float(os.environ.get("IOU_THRES", "0.45"))
CLASSES = [0]                                  # COCO: person
DEVICE = os.environ.get("DEVICE", "")          # ""=自动, 可填 "0" / "cpu"
TRACKER = os.environ.get("TRACKER", "bytetrack.yaml")

# ---- 避障决策 ----
SMALL_AREA_THRESHOLD = int(os.environ.get("SMALL_AREA_THRESHOLD", "60000"))  # 判定为可避让对象的最小面积
ACTION_THROTTLE = float(os.environ.get("ACTION_THROTTLE", "0.5"))            # 动作节流间隔秒

# ---- 帧来源 ----
DEFAULT_SOURCE = os.environ.get("DEFAULT_SOURCE", "udp")    # udp | webcam | video | synthetic

# ---- 日志 ----
def setup_logging(name: str = "vision_server") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"))
        logger.addHandler(handler)
    return logger
