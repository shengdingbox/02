"""主题样式 - 亮色/暗色/跟随系统"""

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

# 亮色主题
LIGHT_THEME = {
    "bg_primary": "#FFFFFF",
    "bg_secondary": "#F5F7FA",
    "bg_tertiary": "#EDF0F5",
    "bg_card": "#FFFFFF",
    "bg_hover": "#F0F2F5",
    "bg_active": "#E8F4FD",
    "text_primary": "#1A1D23",
    "text_secondary": "#5F6B7A",
    "text_tertiary": "#9BA4B0",
    "text_inverse": "#FFFFFF",
    "accent": "#2B6CB0",
    "accent_hover": "#1E5A9E",
    "accent_light": "#E8F4FD",
    "success": "#38A169",
    "success_light": "#E6F7ED",
    "warning": "#D69E2E",
    "warning_light": "#FFF8E6",
    "error": "#E53E3E",
    "error_light": "#FEE8E8",
    "border": "#E2E6EC",
    "border_light": "#EDF0F5",
    "shadow": "rgba(0,0,0,0.08)",
    "sidebar_bg": "#1A1D23",
    "sidebar_text": "#B0B8C4",
    "sidebar_active": "#2B6CB0",
    "sidebar_hover": "rgba(255,255,255,0.06)",
}

# 暗色主题
DARK_THEME = {
    "bg_primary": "#1A1D23",
    "bg_secondary": "#22262E",
    "bg_tertiary": "#2A2F3A",
    "bg_card": "#262B35",
    "bg_hover": "#2F3540",
    "bg_active": "#1E3A5F",
    "text_primary": "#E8ECF1",
    "text_secondary": "#9BA4B0",
    "text_tertiary": "#6B7685",
    "text_inverse": "#1A1D23",
    "accent": "#4DA3E8",
    "accent_hover": "#6BB5F0",
    "accent_light": "#1E3A5F",
    "success": "#48BB78",
    "success_light": "#1C3B2A",
    "warning": "#ECC94B",
    "warning_light": "#3B3420",
    "error": "#FC8181",
    "error_light": "#3B1C1C",
    "border": "#2F3540",
    "border_light": "#262B35",
    "shadow": "rgba(0,0,0,0.3)",
    "sidebar_bg": "#12151A",
    "sidebar_text": "#9BA4B0",
    "sidebar_active": "#4DA3E8",
    "sidebar_hover": "rgba(255,255,255,0.04)",
}


def get_stylesheet(theme: str = "system") -> str:
    """生成完整 QSS 样式表"""
    import sys
    if theme == "system":
        from PySide6.QtWidgets import QApplication
        theme = "dark" if QApplication.instance().styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"

    colors = DARK_THEME if theme == "dark" else LIGHT_THEME

    return f"""
        /* === 全局样式 === */
        QMainWindow {{
            background-color: {colors['bg_primary']};
        }}
        QWidget {{
            font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
            font-size: 13px;
            color: {colors['text_primary']};
        }}

        /* === 侧边栏 === */
        #sidebar {{
            background-color: {colors['sidebar_bg']};
            border-right: 1px solid rgba(255,255,255,0.05);
            min-width: 220px;
            max-width: 220px;
        }}
        #sidebar_logo {{
            color: {colors['text_inverse']};
            font-size: 18px;
            font-weight: 700;
            padding: 20px 16px 12px;
        }}
        #sidebar_version {{
            color: {colors['sidebar_text']};
            font-size: 11px;
            padding: 0px 16px 16px;
            opacity: 0.6;
        }}

        /* 侧边栏按钮 */
        QPushButton#nav_btn {{
            background-color: transparent;
            color: {colors['sidebar_text']};
            border: none;
            border-radius: 8px;
            padding: 10px 16px;
            text-align: left;
            font-size: 13px;
            margin: 2px 8px;
        }}
        QPushButton#nav_btn:hover {{
            background-color: {colors['sidebar_hover']};
            color: #FFFFFF;
        }}
        QPushButton#nav_btn[active="true"] {{
            background-color: {colors['sidebar_active']};
            color: #FFFFFF;
            font-weight: 600;
        }}

        /* === 页面内容区 === */
        #content_area {{
            background-color: {colors['bg_primary']};
        }}
        #page_title {{
            color: {colors['text_primary']};
            font-size: 24px;
            font-weight: 700;
            padding: 24px 32px 8px;
        }}
        #page_subtitle {{
            color: {colors['text_secondary']};
            font-size: 13px;
            padding: 0px 32px 20px;
        }}

        /* === 卡片 === */
        QFrame#card {{
            background-color: {colors['bg_card']};
            border: 1px solid {colors['border']};
            border-radius: 12px;
            padding: 20px;
        }}
        QFrame#card:hover {{
            border-color: {colors['accent']};
        }}
        QLabel#card_title {{
            color: {colors['text_primary']};
            font-size: 15px;
            font-weight: 600;
        }}
        QLabel#card_value {{
            color: {colors['accent']};
            font-size: 28px;
            font-weight: 700;
        }}
        QLabel#card_label {{
            color: {colors['text_tertiary']};
            font-size: 12px;
        }}

        /* === 按钮 === */
        QPushButton#primary_btn {{
            background-color: {colors['accent']};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton#primary_btn:hover {{
            background-color: {colors['accent_hover']};
        }}
        QPushButton#primary_btn:pressed {{
            background-color: {colors['accent']};
        }}

        QPushButton#secondary_btn {{
            background-color: transparent;
            color: {colors['accent']};
            border: 1px solid {colors['accent']};
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton#secondary_btn:hover {{
            background-color: {colors['accent_light']};
        }}

        QPushButton#danger_btn {{
            background-color: {colors['error']};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 13px;
            font-weight: 600;
        }}

        QPushButton#icon_btn {{
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 6px;
        }}
        QPushButton#icon_btn:hover {{
            background-color: {colors['bg_hover']};
        }}

        /* === 输入框 === */
        QLineEdit {{
            background-color: {colors['bg_secondary']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 10px 14px;
            color: {colors['text_primary']};
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {colors['accent']};
        }}
        QLineEdit:hover {{
            border-color: {colors['text_tertiary']};
        }}

        QTextEdit {{
            background-color: {colors['bg_secondary']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 10px;
            color: {colors['text_primary']};
        }}

        /* === 下拉框 === */
        QComboBox {{
            background-color: {colors['bg_secondary']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 8px 12px;
            color: {colors['text_primary']};
            min-height: 20px;
        }}
        QComboBox:hover {{
            border-color: {colors['accent']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 30px;
        }}

        /* === 表格 === */
        QTableWidget {{
            background-color: {colors['bg_card']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            gridline-color: {colors['border_light']};
            alternate-background-color: {colors['bg_secondary']};
        }}
        QTableWidget::item {{
            padding: 8px;
            border-bottom: 1px solid {colors['border_light']};
        }}
        QTableWidget::item:hover {{
            background-color: {colors['bg_hover']};
        }}
        QTableWidget::item:selected {{
            background-color: {colors['accent_light']};
            color: {colors['accent']};
        }}
        QHeaderView::section {{
            background-color: {colors['bg_secondary']};
            color: {colors['text_secondary']};
            border: none;
            border-bottom: 2px solid {colors['accent']};
            padding: 10px;
            font-weight: 600;
            font-size: 12px;
        }}

        /* === 进度条 === */
        QProgressBar {{
            background-color: {colors['bg_tertiary']};
            border: none;
            border-radius: 4px;
            height: 6px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {colors['accent']};
            border-radius: 4px;
        }}

        /* === 滚动条 === */
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {colors['text_tertiary']};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {colors['text_secondary']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}

        /* === Tab 标签 === */
        QTabWidget::pane {{
            border: none;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {colors['text_secondary']};
            padding: 10px 20px;
            border: none;
            border-bottom: 2px solid transparent;
            font-size: 13px;
        }}
        QTabBar::tab:selected {{
            color: {colors['accent']};
            border-bottom: 2px solid {colors['accent']};
            font-weight: 600;
        }}
        QTabBar::tab:hover {{
            color: {colors['text_primary']};
            background-color: {colors['bg_hover']};
            border-radius: 6px;
        }}

        /* === 状态标签 === */
        QLabel#status_active {{
            color: {colors['success']};
            font-weight: 600;
        }}
        QLabel#status_error {{
            color: {colors['error']};
            font-weight: 600;
        }}
        QLabel#status_warning {{
            color: {colors['warning']};
            font-weight: 600;
        }}

        /* === 开关按钮 === */
        QCheckBox#toggle {{
            spacing: 8px;
        }}
        QCheckBox#toggle::indicator {{
            width: 36px;
            height: 20px;
            border-radius: 10px;
            background-color: {colors['bg_tertiary']};
        }}
        QCheckBox#toggle::indicator:checked {{
            background-color: {colors['accent']};
        }}

        /* === Toast 通知 === */
        #toast {{
            background-color: {colors['bg_card']};
            border: 1px solid {colors['border']};
            border-radius: 10px;
            padding: 12px 20px;
        }}
        #toast_success {{
            border-left: 3px solid {colors['success']};
        }}
        #toast_error {{
            border-left: 3px solid {colors['error']};
        }}
    """
