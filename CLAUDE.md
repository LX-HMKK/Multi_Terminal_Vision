# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

多端协同的视觉避障与远程控制系统（动量轮自平衡自行车 · 课程项目三）。一套**「上位机(Qt C++) — 运算端(YOLO) — 部署端(Jetson Nano)」**三端系统，用「UDP 视频 + TCP 指令」贯通成闭环：摄像头→JPEG→UDP→检测+跟踪+避障决策→TCP 指令→串口控制下位机，同时把标注画面回传上位机显示、把目标生命周期事件入库截图。本仓库是旧项目的**重构整编版**，文档以 `docs/architecture.md`（架构）、`docs/protocol.md`（通信协议，唯一权威）、`docs/known-issues.md`（待你真机标定项）为准。**README 是面向使用者的；CLAUDE.md 是给你改代码时用的**，两者不重复。

## 常用命令

没有 pytest/ruff/black——测试与检查全靠 `tools/smoke_test.py`（无第三方依赖，安装依赖前即可跑）：

```bash
python tools/smoke_test.py        # 验证避障决策 / 串口信号映射 / decide_control（缺 cv2 时自动跳过系统级项）
```

运算端（笔记本/PC，需 `pip install -r server/requirements.txt`，首次运行联网下载 yolov8n.pt）：

```bash
python -m server.vision_server                        # 默认 --source udp（接 nano）
python -m server.vision_server --source synthetic --show   # 无硬件本地演示
python -m server.vision_server --source video path/to/video.mp4
```

部署端（Jetson Nano，需 `pip install -r deployment/requirements.txt`）：

```bash
python -m deployment.nano_car                          # 真机（串口 /dev/ttyTHS1）
SERIAL_PORT=mock python -m deployment.nano_car         # 无硬件联调（只打印串口）
```

上位机（Windows Qt Widgets，依赖 Qt5/6 的 `core gui widgets network sql`，**无需 OpenCV**）：

```bash
cd host && qmake host.pro && make                      # 或用 Qt Creator 打开 host.pro
cd host && cmake -S . -B build -G Ninja && cmake --build build   # == host.pro，VS Code/CMake 工作流
```

整条链路无实体车跑通：终端 A 启动上位机并点「开启监听」；终端 B 运行
`python -m server.vision_server --source synthetic`。任一端未启动都不影响其它端（各连接自动重连）。

所有网络/串口/模型参数都用**环境变量**覆盖，无需改代码：`SERVER_IP` `NANO_IP` `QT_IP`、
`SERVER_VIDEO_PORT`(5552) `NANO_CMD_PORT`(12345) `HOST_CMD_TCP`(9999) `HOST_VIDEO_UDP`(8888)、
`SERIAL_PORT` `MODEL` `COMMAND_BIND` `ALLOW_UNSAFE` `NANO_TOKEN`。

## 架构

三端各自**独立可运行**（各自有 `config.py` 的 `setup_logging` + 主循环），靠网络连接，无共享代码依赖。核心是「把纯逻辑抽成无网络依赖的可测模块，把网络 I/O 和 I/O 胶水分开」。

**部署端 `deployment/`（Jetson Nano）** 三个线程 + 中央控制器：
- `video_sender`：摄像头0 → JPEG → UDP `SERVER_IP:SERVER_VIDEO_PORT`。
- `command_server`：TCP 监听 `NANO_CMD_PORT`，按换行分帧，可选 `AUTH <token>` 鉴权（`hmac.compare_digest`）。**默认绑定 `NANO_IP`，绑定失败即拒绝启动（fail-closed，绝不静默暴露 `0.0.0.0`）**；开发用 `COMMAND_BIND=127.0.0.1` 或显式 `ALLOW_UNSAFE=1`。
- `control_thread`：摄像头1 → `LineFollower.process` 循迹 → `decide_control(mode, cmd, line)` 决定信号名 → 统一经 `serial_bridge` 下发两字节 `[signal, 0x43]`。**串口写入只走中央控制器**，避免多线程直写竞态。
- `device/serial_bridge.py`：`RealSerial`（pyserial）/ `MockSerial`（仅日志），`make_serial_bridge` 按 `SERIAL_PORT == "mock"` 选择。

**运算端 `server/`（笔记本/PC）** 主循环 `vision_server.py`，胶水分到两处、检测胶水留在入口：
- `vision/sources.py`：`FrameSource` + `build_source` 工厂，`udp`/`webcam`/`video`/`synthetic` 四种帧源。
- `net/net.py`：`TCPSender`（**非阻塞 + select** 自动重连，按行分帧、可选鉴权/收行回调）、`UDPSender`、`TrackState`（目标生命周期 diff；发出 `ID_<id>_start/end` 给上位机）、`HostCommandHandler`（解析上位机指令 `0/1/2/3`、`w/a/s/d/f/g`，更新模式 + 转发 nano）。
- `vision/avoidance.py`：**纯函数** `Detection` / `pick_largest` / `decide_action`（画面左/中/右三分区 + 面积阈值 → `right/left/detour/no`，仅避障模式生效）/ `ActionThrottle`（节流 + 仅变化才发）。

**上位机 `host/`（Windows Qt）**：`Widget` 为主窗，`Udp_Thread` 收 8888 显示视频，`Tcp_Thread` 收 9999 指令/事件、保存截图，`MessageStore` 封装 SQLite `messages.db`（截图路径 + 时间，含 CRUD）。**事件按 `^ID_(\d+)_(start|end)$` 白名单解析**后再用数字 ID 拼文件名，杜绝路径穿越。

## 跨端共享的事实（改动前先在 `docs/protocol.md` 确认语义）

- **运算端与部署端各有一份 `config.py`**，且模式（`MODE_*` = `0/1/2/3`）、端口、`SIGNALS` 定义了同一套协议常量——**改任何一端必须先改另一端，保持一致**。
- 控制模式：`0` 自动循迹 / `1` 手动 WASD / `2` 避障 / `3` 关闭避障-恢复循迹（非停车）。紧急停车=避障动作 `stop`（字节 6）或手动 `s`。
- 避障动作在模式2下优先，`'no'` 表示无目标、不改变动作（继续循迹）；`left` 在循迹=字节1、在避障=字节7（`avoid_left`），代码用语义名 `avoid_left/avoid_right` 区分，避免与循迹方向字冲突。
- 串口帧固定两字节 `[signal, 0x43]`；`SIGNALS` 语义名→字节映射见 `deployment/config.py`。
- **默认不鉴权（信任局域网）**；需要时两端设相同 `NANO_TOKEN`，运算端连接发 `AUTH <token>` 握手。

## 约定 / 注意

- 仓库全中文注释与提交信息，保持该风格。评论、docstring、commit message 都写中文。
- `LineFollower` 沿用了原实现的 `THRESH_BINARY`（数的是**亮**像素区面积，变量名里的 `black` 是历史命名）——左右比较逻辑与原一致，真机验证是否需反转，见 `docs/known-issues.md`。
- `ultralytics` 首次运行联网下载权重（默认 `yolov8n.pt`）；无网环境需预先 `yolo export` 或放本地 `.pt` 并改 `MODEL`。
- `avoidance.py`、`line_follow.py`、`decide_control`、`config.SIGNALS` 都是纯逻辑，改动后跑 `python tools/smoke_test.py` 验证，无需起网络/硬件。
- `SMALL_AREA_THRESHOLD`、左中右分区边界、循迹计数方向都与真实镜头/距离有关，属真机标定项，别顺手“修复”为拍脑袋值。
