# 已知问题与后续方向

记录原项目遗留下来、本重构**已处理或仍待处理**的事项。

## 已在本仓库内解决

- **上位机源码缺件**：`QT_code/RECV/udp_thread.cpp` 为 0 字节、`备份/完整/tcp_thread.cpp`
  为 0 字节，任何单独目录都无法编译。本仓库取三份的**并集**成一份可编译源码。
- **上位机硬编码路径**：原代码把保存路径写死到 `D:/StudyWorks/2.1/Item3/...`，
  且 `on_btn_path_change_clicked` 存在 `if(!isEmpty) filePath="."` 的反向 bug。
  已改为默认相对目录 `screenshots/`，并修复目录选择逻辑。
- **死代码 / 空实现**：`serve+yolo+detect.py` 的 `handle_tcp_connection(4447)` 为空；
  `getout.py` 为 0 字节；`All_IN_20250113_103346.py` 与 `All_IN.py` 仅端口不同。
  均已删除，未纳入新仓库。
- **外部依赖缺失**：原运算端依赖仓库外的 `yolov5/`（`models.experimental/...`）与 `sort`，
  没有 requirements，无法直接跑。本仓库改用 pip 可装的 `ultralytics` 提供等价检测+跟踪。
- **`.accelerate/`**：实为 HuggingFace 缓存残留，非配置，未纳入仓库。
- **串口直写竞态**：原 `All_IN.py` 多个线程直接 `ser.write`，本重构收敛到中央控制器 + `serial_bridge`。
- **链路健壮性**：原 `serve+yolo+detect.py`（TCP 到 nano/上位机）无重连、无分帧，空连接 `4447` 死代码；
  本重构的 `TCPSender` 改为**非阻塞 + select** 自动重连，统一**换行分帧**，空闲不再抖动、未接线不阻塞主循环。
- **上位机并行缺陷**：原 `QT_code/RECV`（`udp_thread.cpp` 为 0 字节、tcp/udp 线程用共享 `QMutex` 控制暂停导致可能双解锁 UB、
  队列/保存标志跨线程竞争、文本框逐键发送）均已修复（`QMutex+QWaitCondition` 暂停、互斥锁队列、发送按钮）。
- **客户端断开未处理**：原 `socket_disconnect` 走旧式 `SIGNAL/SLOT` 字符串连接但未声明为槽，导致断开事件丢失；已改为
  旧式连接 + 真正的槽，或新式 `&QTcpSocket::disconnected` 连接。

## 仍待解决 / 需要你补全

- **下位机固件协议**：串口控制字节（`[signal,0x43]`）的语义是按原 `All_IN.py` 反推的，
  真实含义取决于小车固件，请以实际固件为准（在 `deployment/config.py` 调整 `SIGNALS`）。
- **循迹计数方向**：`deployment/line_follow.py` 沿用原实现的 `THRESH_BINARY`（数的是**亮**像素区域面积，
  “left_black/right_black”为历史命名）。左右面积比较逻辑与原一致，请在真车上验证是否需要反转阈值方向。
- **模型与真机**：`ultralytics` 首次运行会联网下载权重（默认 `yolov8n.pt`）；
  部署到无网环境请预先 `yolo export` 或把 `.pt` 放到本地并修改 `MODEL`。
- **避障决策标定**：`SMALL_AREA_THRESHOLD`、左/中/右分区的边界值与真实镜头、距离有关，
  需在真车上实测调参（`server/config.py`）。
- **数据标注与再训练**：原数据集为 MIT 行人集（约 900+ 张，`吕哲的代码/MITdate/`），
  未纳入本仓库；如需微调可在 ultralytics 上按 YOLO 格式重排。
- **多车/多路**：当前为单 nano 单上位机；若要多路，需引入通道 ID 或对象前缀。
- **安全性**：UDP/TCP 均无鉴权，仅适合局域网课程演示。

## 安全说明（2026-09 加固）

- **上位机截图路径**：收到事件先按 `^ID_(\d+)_(start|end)$` 白名单校验，
  只用数字 ID 拼接文件名，杜绝路径穿越/任意写文件。
- **部署端指令通道**：默认绑定 `NANO_IP`，绑定失败即**拒绝启动**（fail-closed，绝不静默 `0.0.0.0`）；
  开发联调用 `COMMAND_BIND=127.0.0.1` 或显式 `ALLOW_UNSAFE=1`。需更强时两端设相同 `NANO_TOKEN`
  启用 `AUTH` 握手鉴权（`hmac.compare_digest` 校验、失败 3 次断开）。默认不开鉴权，信任局域网。
- **上位机缓冲**：TCP 接收缓冲与消息/帧队列均设上限（1 MiB / 200 条 / 96 帧），
  超限丢弃或断开，防内存耗尽。

## 不建议做什么

- 回溯 `备份/*` 的旧循环逻辑（`road_follow` 在自动/避障模式下都直写串口），
  与中央控制器冲突，已收敛。
