#ifndef STYLE_H
#define STYLE_H

#include <QString>

// 上位机全局样式（QSS）：浅色 / 暗色 两套主题。
// 用 C++ 内联字符串承载，避免资源系统/外部文件路径问题，qmake 与 CMake 均无需改构建配置。
// 由 Widget 的“暗色主题”复选框或 CAR_THEME=dark 环境变量决定应用哪套，
// setStyleSheet(lightStyleSheet()) / setStyleSheet(darkStyleSheet())。

inline QString lightStyleSheet()
{
    return QString::fromUtf8(R"QSS(
/* ---- 全局基础 ---- */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 10pt;
    background-color: #f3f4f6;
    color: #1f2937;
}

/* ---- 面板卡片 ---- */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    margin-top: 12px;
    padding: 6px 8px 8px 8px;
    font-weight: 600;
    color: #374151;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #374151;
}

/* ---- 标签 ---- */
QLabel { background: transparent; color: #1f2937; }
QLabel#label_3, QLabel#label_5, QLabel#label_6 {
    color: #374151; font-weight: 600;
}
/* 视频区：深色面板，画面未铺满时以深底衬出 */
QLabel#label_frame {
    background-color: #111827;
    color: #9ca3af;
    border: 1px solid #374151;
    border-radius: 6px;
}

/* ---- 复选框 ---- */
QCheckBox { color: #374151; }

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

inline QString darkStyleSheet()
{
    return QString::fromUtf8(R"QSS(
/* ---- 全局基础 ---- */
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 10pt;
    background-color: #111827;
    color: #e5e7eb;
}

/* ---- 面板卡片 ---- */
QGroupBox {
    background-color: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
    margin-top: 12px;
    padding: 6px 8px 8px 8px;
    font-weight: 600;
    color: #e5e7eb;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #d1d5db;
}

/* ---- 标签 ---- */
QLabel { background: transparent; color: #e5e7eb; }
QLabel#label_3, QLabel#label_5, QLabel#label_6 {
    color: #d1d5db; font-weight: 600;
}
/* 视频区：更深面板 */
QLabel#label_frame {
    background-color: #0b0f19;
    color: #6b7280;
    border: 1px solid #1f2937;
    border-radius: 6px;
}

/* ---- 复选框 ---- */
QCheckBox { color: #d1d5db; }

/* ---- 按钮：次级（暗底描边）---- */
QPushButton {
    background-color: #1f2937;
    color: #e5e7eb;
    border: 1px solid #4b5563;
    border-radius: 6px;
    padding: 5px 14px;
    min-height: 20px;
}
QPushButton:hover  { background-color: #374151; border-color: #6b7280; }
QPushButton:pressed{ background-color: #0b0f19; border-color: #9ca3af; }
QPushButton:disabled { background-color: #111827; color: #6b7280; border-color: #1f2937; }

/* 主按钮：强调色填充 */
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
    background: #0b0f19; color: #e5e7eb;
    border: 1px solid #4b5563; border-radius: 6px;
    padding: 4px 8px; selection-background-color: #3b82f6; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus { border-color: #3b82f6; }

/* ---- 文本域（消息 / 发送日志）---- */
QTextEdit {
    background: #0b0f19; color: #e5e7eb;
    border: 1px solid #4b5563; border-radius: 6px; padding: 4px;
}
QTextEdit:focus { border-color: #3b82f6; }

/* ---- 表格 ---- */
QTableWidget {
    background: #0b0f19; border: 1px solid #4b5563; border-radius: 6px;
    gridline-color: #1f2937;
    selection-background-color: #1e3a8a; selection-color: #ffffff;
    alternate-background-color: #1f2937;
}
QHeaderView::section {
    background-color: #1f2937; color: #d1d5db; font-weight: 600;
    padding: 6px 8px; border: none;
    border-bottom: 1px solid #374151; border-right: 1px solid #111827;
}
QTableWidget::item { padding: 4px 8px; }

/* ---- 滚动条 ---- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #4b5563; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #6b7280; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #4b5563; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #6b7280; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- 提示框 ---- */
QToolTip { background: #1f2937; color: #e5e7eb; border: 1px solid #4b5563; padding: 4px 6px; }
)QSS");
}

#endif // STYLE_H
