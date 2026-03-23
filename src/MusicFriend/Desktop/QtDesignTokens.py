"""
Qt 样式表设计令牌，与项目根目录 UIDesign.JSON / static/themeTokens.css 语义对齐。
集中维护色值与圆角，避免在界面代码中散落硬编码颜色。
"""

from __future__ import annotations

# 色板（与 co-listening_room.colors、CSS 变量一致）
COLORS = {
    "bgPage": "#121212",
    "bgPrimary": "#212121",
    "bgSecondary": "#1e1e1e",
    "accent": "#00bcd4",
    "textHigh": "#ffffff",
    "textMedium": "#b0b0b0",
    "textLow": "#616161",
    "divider": "#333333",
    "success": "#4caf50",
    "warning": "#ff9800",
    "danger": "#e53935",
}


def application_stylesheet() -> str:
    """QApplication 级全局样式：窗口、输入框、按钮、分组框、列表等。"""
    c = COLORS
    return f"""
    QWidget {{
        background-color: {c["bgPage"]};
        color: {c["textHigh"]};
        font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    }}
    QLabel {{
        background-color: transparent;
        color: {c["textHigh"]};
    }}
    QLineEdit, QPlainTextEdit {{
        background-color: {c["bgPrimary"]};
        color: {c["textHigh"]};
        border: 1px solid {c["divider"]};
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: {c["accent"]};
        selection-color: {c["textHigh"]};
    }}
    QPushButton {{
        background-color: {c["bgSecondary"]};
        color: {c["textHigh"]};
        border: 1px solid {c["divider"]};
        border-radius: 8px;
        padding: 8px 14px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        border-color: {c["accent"]};
        background-color: {c["bgPrimary"]};
    }}
    QPushButton:pressed {{
        background-color: {c["bgPrimary"]};
    }}
    QPushButton:disabled {{
        color: {c["textLow"]};
        border-color: {c["divider"]};
        background-color: {c["bgSecondary"]};
    }}
    QGroupBox {{
        border: 1px solid {c["divider"]};
        border-radius: 12px;
        margin-top: 14px;
        padding-top: 10px;
        font-weight: 600;
        color: {c["textMedium"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c["textMedium"]};
    }}
    QListWidget {{
        background-color: {c["bgPrimary"]};
        color: {c["textHigh"]};
        border: 1px solid {c["divider"]};
        border-radius: 8px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 6px;
    }}
    QListWidget::item:hover {{
        background-color: {c["bgSecondary"]};
    }}
    QListWidget::item:selected {{
        background-color: {c["accent"]};
        color: {c["textHigh"]};
    }}
    QRadioButton {{
        color: {c["textMedium"]};
        spacing: 8px;
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
    }}
    QDialog {{
        background-color: {c["bgPage"]};
    }}
    QMainWindow {{
        background-color: {c["bgPage"]};
    }}
    QScrollBar:vertical {{
        background: {c["bgSecondary"]};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c["divider"]};
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["textLow"]};
    }}
    QScrollBar:horizontal {{
        background: {c["bgSecondary"]};
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["divider"]};
        min-width: 24px;
        border-radius: 4px;
    }}
    """


def seat_widget_stylesheet() -> str:
    """座位卡片 SeatWidget 动态属性 occupied 的样式。"""
    c = COLORS
    return f"""
    SeatWidget {{
        background-color: {c["bgSecondary"]};
        border-radius: 12px;
        border: 2px solid {c["bgSecondary"]};
    }}
    SeatWidget[occupied="false"] {{
        background-color: transparent;
        border: 2px dashed {c["divider"]};
    }}
    SeatWidget[occupied="true"] {{
        border: 2px solid {c["accent"]};
    }}
    """


def album_art_label_stylesheet() -> str:
    """座位内封面占位区域。"""
    c = COLORS
    return (
        f"background-color: {c['bgPrimary']}; "
        f"border: 1px solid {c['divider']}; "
        f"border-radius: 8px;"
    )


def chat_log_stylesheet() -> str:
    """只读聊天区：略区别于普通输入框时可单独调用；与全局 QPlainTextEdit 一致亦可。"""
    c = COLORS
    return f"""
    QPlainTextEdit {{
        background-color: {c["bgPrimary"]};
        color: {c["textMedium"]};
        border: 1px solid {c["divider"]};
        border-radius: 12px;
        padding: 8px;
    }}
    """


def muted_label_stylesheet() -> str:
    """辅助说明文字（如随机房间 ID 提示）。"""
    return f"color: {COLORS['textMedium']}; background: transparent;"
