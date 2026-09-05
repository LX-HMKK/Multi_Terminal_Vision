# multi_terminal_vision_car

**多端协同视觉避障与远程控制系统**（动量轮自平衡自行车 · 课程项目三）

一个由 **上位机(Qt) — 运算端(YOLO) — 部署端(Jetson Nano)** 组成的三端系统：
摄像头采集 → 远程传输 → 行人检测与跟踪 → 避障决策 → 设备控制 的端到端闭环。
本仓库是旧项目的**重构整编版**，目标：清晰命名 + 可直接运行 + git 管理。

```
├── deployment/   # 部署端（Jetson Nano 车端，Python）
├── server/       # 运算端（笔记本/PC，YOLO 检测+跟踪+避障，Python）
├── host/         # 上位机（Windows Qt Widgets C++）
├── docs/         # 架构 / 协议 / 已知问题
└── tools/        # 冒烟测试等
```

## 快速开始

### 1. 上位机（Windows Qt）
```
cd host
qmake host.pro && make          # 或用 Qt Creator 打开 host.pro 构建
```
启动后点击 **“开启监听”**（TCP `9999` / UDP `8888`）。前提：装了 Qt 5/6 的
`core gui widgets network sql` 模块（**无需 OpenCV**）。

### 2. 运算端（笔记本/PC）—— 缺 GPU 也能跑（CPU 慢一点）
```
cd server
pip install -r requirements.txt
python -m server.vision_server --source synthetic --show   # 无硬件 demo
```
`--source`：`udp`(nano，默认) / `webcam` / `video <file>` / `synthetic`(合成帧)。
首次会下载 ultralytics 权重 `yolov8n.pt`。

### 3. 部署端（Jetson Nano）
```
cd deployment
pip install -r requirements.txt
python -m deployment.nano_car                     # 真机（串口 /dev/ttyTHS1）
SERIAL_PORT=mock python -m deployment.nano_car    # 无硬件联调（只打印串口）
```

## 一条命令在本机跑通整条链路（无需实体车）

终端 A（上位机，启动并点“开启监听”）
终端 B（运算端，合成帧源）：
```
cd server && python -m server.vision_server --source synthetic
```
运算端会连到上位机的 `9999`，把带标注的合成画面经 UDP `8888` 回传，
目标进出会触发 `ID_xx_start/end` 事件 → 上位机保存截图并入库；
避障动作则发往 nano 链路（未接线则打印重连日志）。部署端不启动也完全不影响演示。

## 联调建议

- 地址用环境变量覆盖，不必改代码：
  `SERVER_IP` `NANO_IP` `QT_IP` 及 `SERVER_VIDEO_PORT` `NANO_CMD_PORT` `HOST_CMD_TCP` `HOST_VIDEO_UDP`。
- 详见 [docs/protocol.md](docs/protocol.md)（端口与指令集）、[docs/architecture.md](docs/architecture.md)（架构图）、
  [docs/known-issues.md](docs/known-issues.md)（遗留/需你真机标定项）。

## 技术栈

- 部署端：Python · OpenCV · socket · pyserial · threading
- 运算端：Python · ultralytics(YOLO) · OpenCV · numpy · socket · threading
- 上位机：C++ · Qt 6/5 (Widgets/Network/SQL) · SQLite

## 说明

- 原有 `yolov5+SORT` 外部依赖、`备份/*` 历史版本、`吕哲的代码/*`（无关的共享单车示例）、
  MIT 行人数据集（约 900+ 张）均未纳入本仓库，见 `docs/known-issues.md`。
- 仓库名/命名整洁化处理，行为与原意一致；串口控制字节语义以小车固件为准。

License: MIT
