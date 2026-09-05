# 上位机（Qt Widgets）CMake 构建 —— 与 host.pro 等价。
# 便于在 VS Code Qt 插件 / CMake 工作流中构建（插件偏好 CMake）。
# 依赖：Qt 5 或 Qt 6（core/gui/widgets/network/sql），无需 OpenCV。
cmake_minimum_required(VERSION 3.16)
project(host VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)   # 对含 Q_OBJECT 的类跑 moc
set(CMAKE_AUTOUIC ON)   # 对 widget.ui 跑 uic

find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Widgets Sql Network)
find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Widgets Sql Network)

# Qt6 用 qt_add_executable；Qt5 用 add_executable（含 Q_OBJECT 需链接 Qt::moc 等，
# 由自动 AUTOMOC 处理，Qt5 下 add_executable 即可）。
set(HOST_SOURCES
    main.cpp
    widget.cpp
    tcp_thread.cpp
    udp_thread.cpp
    message_store.cpp
)

if(QT_VERSION_MAJOR EQUAL 6)
    qt_add_executable(host WIN32 ${HOST_SOURCES})
else()
    add_executable(host WIN32 ${HOST_SOURCES})
endif()

target_link_libraries(host PRIVATE
    Qt${QT_VERSION_MAJOR}::Widgets
    Qt${QT_VERSION_MAJOR}::Sql
    Qt${QT_VERSION_MAJOR}::Network
)
