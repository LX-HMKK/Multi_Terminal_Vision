# 上位机（Qt Widgets）工程文件
# 依赖：Qt 5 或 Qt 6（core/gui/widgets/network/sql），无需 OpenCV。
# 构建：
#   qmake host.pro && make                 (Linux/mingw)
#   或在 Qt Creator 中打开本文件直接构建。
QT       += core gui sql network
greaterThan(QT_MAJOR_VERSION, 4): QT += widgets
CONFIG += c++11
TARGET = host
TEMPLATE = app

DEFINES += QT_DEPRECATED_WARNINGS

SOURCES += \
    main.cpp \
    tcp_thread.cpp \
    udp_thread.cpp \
    widget.cpp \
    message_store.cpp

HEADERS += \
    tcp_thread.h \
    udp_thread.h \
    widget.h \
    message_store.h

FORMS += \
    widget.ui

# 如果你在 Windows 使用 mingw + OpenCV（本项目未用到），可在下面自行添加 include/lib。
# INCLUDEPATH += path/to/opencv/include
# LIBS += -Lpath/to/opencv/lib -lopencv_core -lopencv_imgproc ...
