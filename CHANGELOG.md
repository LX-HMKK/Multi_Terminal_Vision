# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- 重构三端：部署端（车端）、运算端（YOLO）、上位机（Qt）均为可独立编译/运行的工程。
- 上位机视频显示与记录端，TCP 指令 / UDP 视频双通道，截图自动入库（SQLite）。
- 运算端推理与避障服务，支持 `udp` / `webcam` / `video` / `synthetic` 四种帧源。
- 核心逻辑冒烟测试（`tools/smoke_test.py`）。
- 浅色 / 暗色两套主题，控制卡“暗色主题”复选框实时切换，`CAR_THEME=dark` 可强制暗色。
- 两套构建路径：`host.pro`（qmake）与 `host/CMakeLists.txt`（CMake，适配 VS Code Qt 扩展）。

### Changed

- 上位机界面美化并重排为响应式两列卡片布局（左＝视频+历史，右＝控制/连接/消息）。
- 各模块按领域分区归纳：`server/{net,vision}`、`deployment/{vision,device}`、`host/src`。
- 收敛巨型单体：`vision_server` 拆分帧源与网络模块；抽取 `MessageStore` 收敛数据库职责。
- 原 `yolov5+SORT` 依赖替换为 ultralytics。

### Fixed

- 指令服务接口 fail-closed：绑定失败即拒绝启动，杜绝静默 `0.0.0.0` 暴露。
- 加固路径注入（截图文件名白名单 `ID_<id>_<event>`）、未鉴权控车与无界缓冲。
- 修复 `.gitignore` 行内尾随注释导致规则失效的问题。

### Security

- NANO_TOKEN 鉴权握手（`hmac.compare_digest`），上位机缓存设上限，未鉴权指令不执行。
