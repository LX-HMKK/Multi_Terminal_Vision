#ifndef STYLE_H
#define STYLE_H

#include <QString>

// 上位机全局样式（QSS）：现代化浅色主题。
// 用 C++ 内联字符串承载，避免资源系统/外部文件路径问题，qmake 与 CMake 均无需改构建配置。
// 在 Widget 构造函数中 setStyleSheet(appStyleSheet()) 应用到整棵控件树。
inline QString appStyleSheet()
{
    return QString::fromUtf8(R"QSS(
/* ---- 全局基础 ---- */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 10pt;
    background-color: #f3f4f6;
    color: #1f2937;
}

/* ---- 标签 ---- */
QLabel { background: transparent; color: #1f2937; }
QLabel#label, QLabel#label_3, QLabel#label_5, QLabel#label_6 {
    color: #374151; font-weight: 600;
}
/* 视频区：深色面板，画面未铺满时以深底衬出 */
QLabel#label_frame {
    background-color: #111827;
    color: #9ca3af;
    border: 1px solid #374151;
    border-radius: 6px;
}

/* ---- 按钮：次级（白底描边）---- */
QPushButton {
    background-color: #ffffff;
    color: #1f2937;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
}
QPushButton:hover  { background-color: #f0f9ff; border-color: #93c5fd; }
QPushButton:pressed{ background-color: #dbeafe; border-color: #60a5fa; }
QPushButton:disabled { background-color: #f3f4f6; color: #9ca3af; border-color: #e5e7eb; }

/* 主按钮：强调色填充（开启监听 / 发送 / 查询） */
QPushButton#btn_open, QPushButton#btn_send, QPushButton#selectBtn {
    background-color: #2563eb; color: #ffffff; border: 1px solid #2563eb; font-weight: 600;
}
QPushButton#btn_open:hover, QPushButton#btn_send:hover, QPushButton#selectBtn:hover {
    background-color: #3b82f6; border-color: #3b82f6;
}
QPushButton#btn_open:pressed, QPushButton#btn_send:pressed, QPushButton#selectBtn:pressed {
    background-color: #1d4ed8; border-color: #1d4ed8;
}

/* ---- 输入 ---- */
QLineEdit, QComboBox {
    background: #ffffff; color: #1f2937;
    border: 1px solid #d1d5db; border-radius: 6px;
    padding: 4px 8px; selection-background-color: #2563eb; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border-color: #2563eb; }

/* ---- 文本域（消息 / 发送日志）---- */
QTextEdit {
    background: #f9fafb; color: #1f2937;
    border: 1px solid #d1d5db; border-radius: 6px; padding: 4px;
}
QTextEdit:focus { border-color: #2563eb; }

/* ---- 表格 ---- */
QTableWidget {
    background: #ffffff; border: 1px solid #d1d5db; border-radius: 6px;
    gridline-color: #eef2f7;
    selection-background-color: #dbeafe; selection-color: #1f2937;
    alternate-background-color: #f9fafb;
}
QHeaderView::section {
    background-color: #f3f4f6; color: #374151; font-weight: 600;
    padding: 6px 8px; border: none;
    border-bottom: 1px solid #d1d5db; border-right: 1px solid #e5e7eb;
}
QTableWidget::item { padding: 4px 8px; }

/* ---- 滚动条 ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #cbd5e1; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #94a3b8; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- 提示框 ---- */
QToolTip { background: #111827; color: #f9fafb; border: 1px solid #374151; padding: 4px 6px; }
)QSS");
}

#endif // STYLE_H
