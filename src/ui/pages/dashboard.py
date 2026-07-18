"""仪表盘页面 — 支持响应式缩放，窗口缩小时文字和UI同步缩小"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QButtonGroup, QApplication, QScrollArea, QSpinBox, QComboBox,
    QMessageBox, QCheckBox, QProgressBar, QDialog, QLineEdit
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPalette

from ...i18n import t
from ...utils.store import load_accounts, load_setting, save_setting
from ...models import AccountStatus
from ...modules.proxy_server import ProxyDatabase
from ..styles.theme import LIGHT_THEME, DARK_THEME

logger = logging.getLogger(__name__)


def _current_theme_colors() -> dict:
    """获取当前主题颜色字典"""
    theme = load_setting("theme", "system")
    if theme == "system":
        app = QApplication.instance()
        is_dark = bool(app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        theme = "dark" if is_dark else "light"
    return DARK_THEME if theme == "dark" else LIGHT_THEME


class StatCard(QFrame):
    """统计卡片 — 支持响应式缩放"""

    _BASE_ICON = 20
    _BASE_TITLE = 12
    _BASE_VALUE = 24
    _BASE_MH = 16
    _BASE_MV = 12
    _BASE_SPACING = 8

    def __init__(self, title: str, value: str, icon: str = "", color_key: str = "accent"):
        """
        Args:
            color_key: 主题色板键名，如 accent / success / warning / error
        """
        super().__init__()
        self.setObjectName("card")
        self._color_key = color_key
        self._colors = _current_theme_colors()
        self._scale = 1.0
        self._icon_label = None

        layout = QVBoxLayout(self)
        layout.setSpacing(self._BASE_SPACING)
        layout.setContentsMargins(self._BASE_MH, self._BASE_MV, self._BASE_MH, self._BASE_MV)

        header = QHBoxLayout()
        if icon:
            self._icon_label = QLabel(icon)
            self._icon_label.setStyleSheet(f"font-size: {self._BASE_ICON}px;")
            header.addWidget(self._icon_label)
        title_label = QLabel(title)
        title_label.setObjectName("card_label")
        title_label.setStyleSheet(f"font-size: {self._BASE_TITLE}px; color: {self._colors['text_tertiary']};")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("card_value")
        self._apply_value_style()
        layout.addWidget(self._value_label)

    def _apply_value_style(self):
        """根据当前主题色和缩放比例更新数值标签样式"""
        color = self._colors.get(self._color_key, self._colors["accent"])
        size = int(self._BASE_VALUE * self._scale)
        self._value_label.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: 700;")

    def set_value(self, text: str):
        self._value_label.setText(text)

    def apply_scale(self, scale: float):
        """响应式缩放：调整字体大小、边距、间距"""
        self._scale = scale
        layout = self.layout()
        mh = int(self._BASE_MH * scale)
        mv = int(self._BASE_MV * scale)
        layout.setContentsMargins(mh, mv, mh, mv)
        layout.setSpacing(int(self._BASE_SPACING * scale))
        if self._icon_label:
            self._icon_label.setStyleSheet(f"font-size: {int(self._BASE_ICON * scale)}px;")
        title_label = self.findChild(QLabel, "card_label")
        if title_label:
            title_label.setStyleSheet(
                f"font-size: {int(self._BASE_TITLE * scale)}px; color: {self._colors['text_tertiary']};"
            )
        self._apply_value_style()

    def apply_theme(self, colors: dict):
        """主题切换时刷新颜色（保持当前缩放比例）"""
        self._colors = colors
        title_label = self.findChild(QLabel, "card_label")
        if title_label:
            title_label.setStyleSheet(
                f"font-size: {int(self._BASE_TITLE * self._scale)}px; color: {colors['text_tertiary']};"
            )
        self._apply_value_style()


class CacheHitRateChart(QWidget):
    """缓存命中率环形图 — 用 QPainter 手绘 donut chart，支持响应式缩放"""

    _BASE_SIZE = 140
    _BASE_PEN = 12
    _BASE_FONT = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rate = 0.0  # 缓存命中率 (0~1)
        self._colors = _current_theme_colors()
        self._scale = 1.0
        self.setFixedSize(self._BASE_SIZE, self._BASE_SIZE)

    def set_rate(self, rate: float):
        """设置命中率（0~1），触发重绘"""
        self._rate = max(0.0, min(1.0, float(rate)))
        self.update()

    def apply_scale(self, scale: float):
        """响应式缩放：调整图表尺寸"""
        self._scale = scale
        size = int(self._BASE_SIZE * scale)
        self.setFixedSize(size, size)

    def apply_theme(self, colors: dict):
        """主题切换时刷新颜色"""
        self._colors = colors
        self.update()

    def paintEvent(self, event):
        """绘制环形图（画笔宽度和字号随缩放比例调整）"""
        colors = self._colors
        color_hit = QColor(colors["success"])
        color_miss = QColor(colors["border"])
        color_text = QColor(colors["text_primary"])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        pen_width = max(6, int(self._BASE_PEN * self._scale))
        rect = QRectF(
            pen_width / 2, pen_width / 2,
            w - pen_width, h - pen_width
        )

        # 背景圆环（未命中部分）
        bg_pen = QPen(color_miss, pen_width)
        bg_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # 命中部分（从12点钟方向顺时针绘制）
        if self._rate > 0:
            hit_pen = QPen(color_hit, pen_width)
            hit_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(hit_pen)
            start_angle = 90 * 16
            span_angle = int(-self._rate * 360 * 16)
            painter.drawArc(rect, start_angle, span_angle)

        # 中心文字（百分比）
        painter.setPen(color_text)
        font = QFont()
        font.setPixelSize(max(10, int(self._BASE_FONT * self._scale)))
        font.setBold(True)
        painter.setFont(font)
        text = f"{self._rate * 100:.1f}%"
        painter.drawText(rect, Qt.AlignCenter, text)

        painter.end()


class CheckableBox(QCheckBox):
    """自定义复选框 — 用 QPainter 绘制清晰的对勾"""

    def __init__(self, text: str, accent_color: str, border_color: str, text_color: str, parent=None):
        super().__init__(text, parent)
        self._accent = accent_color
        self._border = border_color
        self._text_color = text_color
        self.setStyleSheet(f"""
            QCheckBox {{
                color: {text_color};
                font-size: 13px;
                spacing: 8px;
                padding: 4px 0;
            }}
        """)

    def paintEvent(self, event):
        """自绘：文字正常绘制，indicator 手动绘制对勾"""
        from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush
        from PySide6.QtCore import QRect, Qt, QPoint, QLineF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制 indicator 方框
        box_size = 18
        box_y = (self.height() - box_size) // 2
        box_rect = QRect(0, box_y, box_size, box_size)

        if self.isChecked():
            # 蓝色背景
            painter.setBrush(QBrush(QColor(self._accent)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(box_rect, 4, 4)

            # 白色对勾
            pen = QPen(QColor("#FFFFFF"), 2.5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            # 对勾路径: (4,9) → (8,13) → (14,5)
            painter.drawLine(QLineF(4, box_y + 9, 8, box_y + 13))
            painter.drawLine(QLineF(8, box_y + 13, 14, box_y + 5))
        else:
            # 透明背景 + 灰色边框
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor(self._border), 2)
            painter.setPen(pen)
            painter.drawRoundedRect(box_rect, 4, 4)

        # 绘制文字
        text_rect = QRect(box_size + 8, 0, self.width() - box_size - 8, self.height())
        painter.setPen(QColor(self._text_color))
        font = QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())

        painter.end()


class DashboardPage(QWidget):
    """仪表盘页面 — 纯本地数据概览，不自动发网络请求，支持响应式缩放"""

    _REF_WIDTH = 980    # 参考宽度（100%缩放时的可用内容宽度）
    _MIN_SCALE = 0.7    # 最小缩放比例

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("content_area")
        self._colors = _current_theme_colors()
        self._scale = 1.0
        self._all_cards = []
        self._proxy_page = None  # ApiProxyPage 引用，由 MainWindow 注入
        self._credits_loaded = False  # 是否已从后端加载过积分
        self._setup_ui()
        self._load_cached_credits()  # 启动时从本地缓存加载积分

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel(t("nav.dashboard"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("积分额度 · API 代理 · 使用统计")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # 可滚动内容区域（兜底：极端窄窗口时允许滚动查看全部内容）
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # 内容区域
        self._content = QWidget()
        self._content.setObjectName("dashboard_scroll_content")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(20)

        # === 激活卡密按钮 + 积分进度条 ===
        quota_card = QFrame()
        quota_card.setObjectName("proxy_control_card")
        quota_layout = QHBoxLayout(quota_card)
        quota_layout.setContentsMargins(20, 16, 20, 16)
        quota_layout.setSpacing(16)

        quota_icon_label = QLabel("💎")
        quota_icon_label.setStyleSheet("font-size: 32px;")
        quota_layout.addWidget(quota_icon_label)

        quota_text_col = QVBoxLayout()
        quota_text_col.setSpacing(6)
        quota_text_col.addWidget(QLabel("积分包余额"))
        self._quota_value_label = QLabel("--")
        self._quota_value_label.setStyleSheet("font-size: 28px; font-weight: 700;")
        self._quota_packages_label = QLabel("")
        self._quota_packages_label.setStyleSheet("color: #9BA4B0; font-size: 13px;")
        quota_text_col.addWidget(self._quota_value_label)
        quota_text_col.addWidget(self._quota_packages_label)
        quota_layout.addLayout(quota_text_col)

        self._quota_progress = QProgressBar()
        self._quota_progress.setRange(0, 100)
        self._quota_progress.setValue(0)
        self._quota_progress.setTextVisible(False)
        self._quota_progress.setFixedHeight(8)
        quota_layout.addWidget(self._quota_progress, 1)

        # 隐藏徽章（保留引用避免报错）
        self._quota_badge_label = QLabel("--")
        self._quota_badge_label.setVisible(False)

        # 按钮列：激活卡密 + 刷新积分
        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)

        # 激活卡密按钮
        self._btn_activate = QPushButton(f"🔑 {t('accounts.add_account')}")
        self._btn_activate.setObjectName("primary_btn")
        self._btn_activate.setCursor(Qt.PointingHandCursor)
        self._btn_activate.setMinimumHeight(36)
        self._btn_activate.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._colors['accent']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_hover']};
            }}
        """)
        self._btn_activate.clicked.connect(self._activate_card)
        btn_col.addWidget(self._btn_activate)

        # 刷新积分按钮
        self._btn_refresh_credits = QPushButton("🔄 刷新积分")
        self._btn_refresh_credits.setCursor(Qt.PointingHandCursor)
        self._btn_refresh_credits.setMinimumHeight(36)
        self._btn_refresh_credits.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self._colors['accent']};
                border: 1px solid {self._colors['accent']};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_light']};
            }}
        """)
        self._btn_refresh_credits.clicked.connect(self._refresh_credits)
        btn_col.addWidget(self._btn_refresh_credits)

        quota_layout.addLayout(btn_col)

        content_layout.addWidget(quota_card)

        # === API 代理服务控制区 ===
        self._proxy_control_card = QFrame()
        self._proxy_control_card.setObjectName("proxy_control_card")
        proxy_ctrl_layout = QVBoxLayout(self._proxy_control_card)
        proxy_ctrl_layout.setSpacing(10)

        # 端口和访问控制
        proxy_config_row = QHBoxLayout()
        proxy_config_row.addWidget(QLabel("端口:"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(int(load_setting("proxy_port", "8002")))
        self._port_spin.valueChanged.connect(lambda _: self._on_port_changed())
        proxy_config_row.addWidget(self._port_spin)

        proxy_config_row.addWidget(QLabel("  "))

        self._proxy_status_label = QLabel("⏹ 已停止")
        self._proxy_status_label.setStyleSheet("font-weight: 600; color: #9BA4B0;")
        proxy_config_row.addWidget(self._proxy_status_label)

        self._toggle_proxy_btn = QPushButton("▶ 启动服务")
        self._toggle_proxy_btn.setObjectName("primary_btn")
        self._toggle_proxy_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_proxy_btn.setMinimumHeight(36)
        self._toggle_proxy_btn.setMinimumWidth(100)
        self._toggle_proxy_btn.clicked.connect(self._toggle_proxy_service)
        self._apply_toggle_btn_style()
        proxy_config_row.addWidget(self._toggle_proxy_btn)

        proxy_config_row.addStretch()

        proxy_ctrl_layout.addLayout(proxy_config_row)

        # 服务 URL 显示
        proxy_url_row = QHBoxLayout()
        proxy_url_row.addWidget(QLabel("接口地址:"))
        self._proxy_url_label = QLabel(f"http://127.0.0.1:{int(load_setting('proxy_port', '8002'))}/v1/chat/completions")
        self._proxy_url_label.setStyleSheet("color: #2B6CB0; font-weight: 600; font-size: 13px;")
        self._proxy_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        proxy_url_row.addWidget(self._proxy_url_label)

        btn_copy_proxy_url = QPushButton("📋 复制")
        btn_copy_proxy_url.setCursor(Qt.PointingHandCursor)
        btn_copy_proxy_url.setFixedWidth(60)
        btn_copy_proxy_url.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self._colors['accent']};
                border: 1px solid {self._colors['accent']};
                border-radius: 6px;
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_light']};
            }}
        """)
        btn_copy_proxy_url.clicked.connect(self._copy_proxy_url)
        proxy_url_row.addWidget(btn_copy_proxy_url)

        proxy_url_row.addStretch()
        proxy_ctrl_layout.addLayout(proxy_url_row)

        # 子 API Key 行
        subkey_row = QHBoxLayout()
        subkey_row.addWidget(QLabel("API Key:"))
        self._subkey_label = QLabel("sk-")
        self._subkey_label.setStyleSheet("color: #805AD5; font-weight: 600; font-size: 13px;")
        self._subkey_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        subkey_row.addWidget(self._subkey_label)

        btn_copy_subkey = QPushButton("📋 复制")
        btn_copy_subkey.setCursor(Qt.PointingHandCursor)
        btn_copy_subkey.setFixedWidth(60)
        btn_copy_subkey.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self._colors['accent']};
                border: 1px solid {self._colors['accent']};
                border-radius: 6px;
                padding: 6px 10px;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_light']};
            }}
        """)
        btn_copy_subkey.clicked.connect(self._copy_subkey)
        subkey_row.addWidget(btn_copy_subkey)

        btn_regen_subkey = QPushButton("🔄 重新生成")
        btn_regen_subkey.setCursor(Qt.PointingHandCursor)
        btn_regen_subkey.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._colors['accent']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_hover']};
            }}
        """)
        btn_regen_subkey.clicked.connect(self._regen_subkey)
        subkey_row.addWidget(btn_regen_subkey)

        subkey_row.addStretch()
        proxy_ctrl_layout.addLayout(subkey_row)

        # === 客户端配置（同一个 card 内） ===
        import getpass
        _username = getpass.getuser()

        # 模型前缀输入框（放到复制配置前面的 action_row 中）

        client_title = QLabel("选择目标客户端（可多选）")
        client_title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {self._colors['text_primary']};"
        )
        proxy_ctrl_layout.addWidget(client_title)

        # 复选框样式 — 带对号
        # WorkBuddy
        self._chk_workbuddy = CheckableBox(
            f"WorkBuddy  腾讯代码助手桌面版  ✓ C:\\Users\\{_username}\\.workbuddy",
            self._colors['accent'], self._colors['border'], self._colors['text_primary']
        )
        self._chk_workbuddy.setChecked(load_setting("config_target_workbuddy", "true") == "true")
        proxy_ctrl_layout.addWidget(self._chk_workbuddy)

        # CodeBuddy
        self._chk_codebuddy = CheckableBox(
            f"CodeBuddy  腾讯云 AI IDE 插件  ✓ C:\\Users\\{_username}\\.codebuddy",
            self._colors['accent'], self._colors['border'], self._colors['text_primary']
        )
        self._chk_codebuddy.setChecked(load_setting("config_target_codebuddy", "true") == "true")
        proxy_ctrl_layout.addWidget(self._chk_codebuddy)

        # 自动备份 + 打开备份目录
        self._chk_auto_backup = CheckableBox(
            "配置前自动备份原文件（推荐）",
            self._colors['accent'], self._colors['border'], self._colors['text_primary']
        )
        self._chk_auto_backup.setChecked(load_setting("config_auto_backup", "true") == "true")

        backup_row = QHBoxLayout()
        backup_row.addWidget(self._chk_auto_backup)
        backup_row.addStretch()
        btn_open_backup = QPushButton("打开备份目录")
        btn_open_backup.setCursor(Qt.PointingHandCursor)
        btn_open_backup.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self._colors['text_primary']};
                border: 1px solid {self._colors['border']};
                border-radius: 6px;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                background-color: {self._colors['bg_hover']};
            }}
        """)
        btn_open_backup.clicked.connect(self._open_backup_dir)
        backup_row.addWidget(btn_open_backup)
        proxy_ctrl_layout.addLayout(backup_row)

        # 底部按钮：复制配置 / 删除配置 / 立即配置
        action_row = QHBoxLayout()

        # 模型前缀输入框（短小，放在复制配置前）
        prefix_label = QLabel("模型前缀:")
        prefix_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        action_row.addWidget(prefix_label)
        self._model_prefix_input = QLineEdit()
        self._model_prefix_input.setPlaceholderText("不知道这是啥 不要动")
        self._model_prefix_input.setText(load_setting("model_prefix", ""))
        self._model_prefix_input.setFixedWidth(160)
        self._model_prefix_input.setStyleSheet(f"""
            QLineEdit {{
                border: 2px solid #E53E3E;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                color: {self._colors['text_primary']};
                background-color: {self._colors['bg_secondary']};
            }}
            QLineEdit::placeholder {{
                color: #E53E3E;
            }}
        """)
        action_row.addWidget(self._model_prefix_input)

        action_row.addStretch()

        btn_copy_config = QPushButton("复制配置")
        btn_copy_config.setCursor(Qt.PointingHandCursor)
        btn_copy_config.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._colors['bg_secondary']};
                color: {self._colors['text_primary']};
                border: 1px solid {self._colors['border']};
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {self._colors['bg_hover']};
            }}
        """)
        btn_copy_config.clicked.connect(self._copy_config)
        action_row.addWidget(btn_copy_config)

        btn_delete_config = QPushButton("删除配置")
        btn_delete_config.setCursor(Qt.PointingHandCursor)
        btn_delete_config.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._colors['bg_secondary']};
                color: {self._colors['text_primary']};
                border: 1px solid {self._colors['border']};
                border-radius: 6px;
                padding: 8px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {self._colors['bg_hover']};
            }}
        """)
        btn_delete_config.clicked.connect(self._delete_config)
        action_row.addWidget(btn_delete_config)

        btn_apply_config = QPushButton("立即配置")
        btn_apply_config.setCursor(Qt.PointingHandCursor)
        btn_apply_config.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._colors['accent']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._colors['accent_hover']};
            }}
        """)
        btn_apply_config.clicked.connect(self._apply_config)
        action_row.addWidget(btn_apply_config)

        proxy_ctrl_layout.addLayout(action_row)

        content_layout.addWidget(self._proxy_control_card)

        # === 诊断项定义（名称, 描述）— 弹窗形式，启动服务时展示 ===
        self._diag_items_def = [
            ("服务端口监听检查",  "端口 {port} 正在监听"),
            ("HTTP 接口健康检查",  "接口响应正常"),
            ("端口占用检测",       "端口 {port} 未被占用"),
            ("Windows 端口预留检查","端口 {port} 不在系统预留段内"),
            ("系统代理检测",       "系统代理未开启"),
            ("Windows 防火墙状态", "所有防火墙配置文件均已关闭"),
            ("hosts 文件检查",     "hosts 文件无异常"),
            ("云端服务连通性",     "云端服务端口可达"),
        ]
        self._diag_dialog = None
        self._diag_rows = []

        content_layout.addStretch()

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        # 显式设置背景色（必须在 setWidget 之后，QScrollArea viewport 默认用系统 palette 不跟主题）
        self._apply_scroll_background()

        # 收集所有静态卡片用于缩放（使用情况图表已移至额度管理页面）
        self._all_cards = []

    # === 响应式缩放 ===

    def resizeEvent(self, event):
        """窗口大小变化时重新计算缩放比例"""
        super().resizeEvent(event)
        self._apply_responsive_scale()

    def _apply_responsive_scale(self):
        """根据当前可用宽度计算缩放比例并应用到所有UI元素"""
        # 安全检查：UI 未完全初始化时跳过（resizeEvent 可能在 _setup_ui 期间被触发）
        if not getattr(self, '_all_cards', None):
            return
        w = self.width()
        if w <= 0:
            w = self._REF_WIDTH
        available = w - 64  # 减去内容区域左右边距 (32*2)
        self._scale = max(self._MIN_SCALE, min(1.0, available / self._REF_WIDTH))
        s = self._scale

        # 缩放所有静态卡片
        for card in self._all_cards:
            card.apply_scale(s)

    # === 主题相关 ===

    def _apply_scroll_background(self):
        """设置 QScrollArea 及其 viewport、内容 widget 的背景色跟随主题

        三管齐下确保深色模式下不出现灰白背景：
        1. QScrollArea 本身 — scoped QSS
        2. viewport — QPalette + autoFillBackground（最可靠）+ QSS 兜底
        3. 内容 widget — scoped QSS（用 objectName 避免级联到子控件）+ QPalette
        """
        bg = self._colors['bg_primary']
        bg_color = QColor(bg)

        # 1. QScrollArea 本身
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {bg}; border: none; }}"
        )

        # 2. viewport — QAbstractScrollArea 的 viewport 是内部特殊 widget，
        #    QSS 不可靠，必须用 QPalette + autoFillBackground 才能稳定生效
        viewport = self._scroll.viewport()
        viewport.setAutoFillBackground(True)
        pal = viewport.palette()
        pal.setColor(QPalette.ColorRole.Window, bg_color)
        viewport.setPalette(pal)
        # QSS 作为额外兜底
        viewport.setStyleSheet(f"background-color: {bg};")

        # 3. 内容 widget — 用 objectName 限定 QSS 范围，避免级联到子控件
        if hasattr(self, '_content'):
            self._content.setAutoFillBackground(True)
            pal2 = self._content.palette()
            pal2.setColor(QPalette.ColorRole.Window, bg_color)
            self._content.setPalette(pal2)
            self._content.setStyleSheet(
                f"#dashboard_scroll_content {{ background-color: {bg}; }}"
            )

    def _apply_cache_frame_style(self):
        """缓存命中率图表区域样式（已移至额度管理页面，保留空方法避免外部调用报错）"""
        pass

    def _range_btn_style_active(self) -> str:
        """选中状态按钮样式（已移至额度管理页面）"""
        c = self._colors
        s = self._scale
        pad_v = int(6 * s)
        pad_h = int(16 * s)
        font_size = int(13 * s)
        return (
            f"QPushButton {{ background-color: {c['accent']}; color: #FFFFFF; "
            f"border: none; padding: {pad_v}px {pad_h}px; border-radius: 6px; font-size: {font_size}px; }}"
        )

    def _range_btn_style_normal(self) -> str:
        """未选中状态按钮样式（已移至额度管理页面）"""
        c = self._colors
        s = self._scale
        pad_v = int(6 * s)
        pad_h = int(16 * s)
        font_size = int(13 * s)
        return (
            f"QPushButton {{ background-color: {c['bg_tertiary']}; color: {c['text_secondary']}; "
            f"border: none; padding: {pad_v}px {pad_h}px; border-radius: 6px; font-size: {font_size}px; }}"
            f"QPushButton:hover {{ background-color: {c['bg_hover']}; }}"
        )

    def apply_theme(self):
        """主题切换时刷新所有颜色"""
        self._colors = _current_theme_colors()

        # QScrollArea 背景跟随主题（viewport 默认灰白不跟主题）
        self._apply_scroll_background()

        # 统计卡片
        for card in self._all_cards:
            card.apply_theme(self._colors)

        # 刷新代理按钮样式
        self._apply_toggle_btn_style()

        # 重新应用响应式缩放（会刷新所有带缩放的样式）
        self._apply_responsive_scale()

    # === 数字格式化（保留静态方法供其他页面调用） ===

    @staticmethod
    def _format_token_count(value: int) -> str:
        """将 Token/数字按大小格式化为中文单位，保留 2 位小数"""
        v = float(value)
        if v < 10_000:
            return f"{int(v):,}"
        if v < 1_000_000:
            return f"{v / 10_000:.2f}万"
        if v < 100_000_000:
            return f"{v / 1_000_000:.2f}百万"
        return f"{v / 100_000_000:.2f}亿"

    # === 图例渲染（已移至额度管理页面，保留空方法避免外部调用报错） ===

    def _render_legend(self, key: str):
        pass

    def _update_legend(self, key: str, value: str):
        pass

    def _refresh_legend_colors(self):
        pass

    # === 事件回调 ===

    def _on_range_changed(self, btn):
        """时间范围切换回调（已移至额度管理页面）"""
        pass

    def _refresh_usage(self):
        """刷新使用情况数据（已移至额度管理页面）"""
        pass

    def _refresh_data(self):
        """刷新仪表盘数据"""
        self._refresh_credits()

    def _load_cached_credits(self):
        """从本地缓存加载积分余额（不请求后端）"""
        try:
            db = ProxyDatabase.get_instance()
            cached = db.get_cached_credits()
            if cached:
                self._render_credits(cached)
            else:
                self._quota_value_label.setText("--")
                self._quota_packages_label.setText("点击 🔄 刷新查询")
                self._quota_badge_label.setText("--")
                self._quota_progress.setValue(0)
        except Exception:
            pass

    def _render_credits(self, data: dict):
        """渲染积分余额到 UI"""
        if not data or "credits" not in data:
            return
        credits = float(data.get("credits", 0))
        total_recharged = float(data.get("totalRecharged", 0))
        total_used = float(data.get("totalUsed", 0))
        today_used = float(data.get("todayUsed", 0))

        self._quota_value_label.setText(f"{credits:.2f}")
        self._quota_packages_label.setText(
            f"累计充值 {total_recharged:.0f} · 已用 {total_used:.0f} · 今日 {today_used:.0f}"
        )

        if credits <= 0:
            self._quota_badge_label.setText("已耗尽")
            self._quota_badge_label.setStyleSheet(
                "background-color: rgba(229,62,62,0.12); color: #E53E3E; "
                "border-radius: 12px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
            )
        else:
            self._quota_badge_label.setText(f"剩余 {credits:.0f}")
            self._quota_badge_label.setStyleSheet(
                "background-color: rgba(56,161,105,0.1); color: #38A169; "
                "border-radius: 12px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
            )

        if total_recharged > 0:
            percent = int(min(100, max(0, (credits / total_recharged) * 100)))
            self._quota_progress.setValue(percent)
        else:
            self._quota_progress.setValue(0)

    def _refresh_credits(self):
        """从后端查询积分余额并更新本地缓存"""
        # 防止重复创建线程
        if hasattr(self, '_credits_thread') and self._credits_thread and self._credits_thread.isRunning():
            return

        self._btn_refresh_credits.setEnabled(False)
        self._quota_value_label.setText("⏳")
        self._quota_packages_label.setText("查询中...")
        self._quota_badge_label.setText("--")
        self._quota_progress.setValue(0)

        from PySide6.QtCore import QThread, Signal as QSignal

        class CreditsThread(QThread):
            done = QSignal(object)

            def run(self):
                from ...utils.server_api import get_credits
                result = get_credits()
                self.done.emit(result)

        self._credits_thread = CreditsThread()
        self._credits_thread.done.connect(self._on_credits_done)
        self._credits_thread.finished.connect(lambda: setattr(self, '_credits_thread', None))
        self._credits_thread.start()

    def _on_credits_done(self, result: dict):
        """积分查询完成"""
        self._btn_refresh_credits.setEnabled(True)
        self._credits_loaded = True

        if result and "credits" in result:
            # 保存到本地缓存
            try:
                db = ProxyDatabase.get_instance()
                db.save_cached_credits(result)
            except Exception:
                pass
            self._render_credits(result)
        else:
            err = result.get("error", "无响应") if result else "无响应"
            self._quota_value_label.setText("--")
            self._quota_packages_label.setText(f"查询失败: {err[:40]}")
            self._quota_badge_label.setText("错误")
            self._quota_progress.setValue(0)

    def _activate_card(self):
        """打开激活卡密对话框"""
        from .accounts import AddAccountDialog
        dialog = AddAccountDialog(self)
        dialog.account_added.connect(lambda _: self._refresh_credits())
        dialog.exec()

    def set_proxy_page(self, proxy_page):
        """注入 ApiProxyPage 引用，用于服务控制"""
        self._proxy_page = proxy_page

    def _build_diag_row(self, name: str, desc: str) -> tuple:
        """构建诊断项单行（状态徽章 + 名称 + 描述），返回 (row_layout, badge_label, name_label, desc_label)"""
        row = QHBoxLayout()
        row.setSpacing(12)

        # 状态徽章（初始=灰色"检测中"）
        badge_style = (
            "background-color: rgba(158,164,176,0.12); color: #9BA4B0; "
            "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
        )
        badge = QLabel("检测中")
        badge.setStyleSheet(badge_style)
        badge.setFixedWidth(54)
        badge.setAlignment(Qt.AlignCenter)
        row.addWidget(badge)

        # 右侧：名称 + 描述（垂直堆叠）
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {self._colors['text_primary']};"
        )
        text_col.addWidget(name_label)
        desc_label = QLabel("")
        desc_label.setStyleSheet(
            f"font-size: 12px; color: {self._colors['text_tertiary']};"
        )
        desc_label.setWordWrap(True)
        text_col.addWidget(desc_label)
        row.addLayout(text_col, 1)

        return (row, badge, name_label, desc_label)

    def _set_diag_row_status(self, idx: int, status: str, kind: str):
        """更新诊断项的状态徽章颜色"""
        if idx >= len(self._diag_rows):
            return
        badge = self._diag_rows[idx][1]
        badge.setText(status)
        if kind == "success":
            badge.setStyleSheet(
                "background-color: rgba(56,161,105,0.15); color: #38A169; "
                "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
            )
        elif kind == "error":
            badge.setStyleSheet(
                "background-color: rgba(229,62,62,0.12); color: #E53E3E; "
                "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
            )
        else:  # pending
            badge.setStyleSheet(
                "background-color: rgba(158,164,176,0.12); color: #9BA4B0; "
                "border-radius: 6px; padding: 4px 12px; font-size: 12px; font-weight: 600;"
            )

    def _show_diag_dialog(self, port: int):
        """创建并显示诊断弹窗"""
        self._diag_dialog = QDialog(self)
        self._diag_dialog.setWindowTitle("服务启动中")
        self._diag_dialog.setModal(True)
        self._diag_dialog.setMinimumWidth(420)
        self._diag_dialog.setWindowFlags(
            self._diag_dialog.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self._diag_dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self._diag_title = QLabel("🔍 服务启动中...")
        self._diag_title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {self._colors['text_primary']};"
        )
        layout.addWidget(self._diag_title)

        # 构建诊断行
        self._diag_rows = []
        for name, desc_template in self._diag_items_def:
            row, badge, name_label, desc_label = self._build_diag_row(name, "")
            layout.addLayout(row)
            self._diag_rows.append((row, badge, name_label, desc_label))

        self._diag_dialog.show()

    def _close_diag_dialog(self):
        """关闭诊断弹窗"""
        if self._diag_dialog:
            self._diag_dialog.close()
            self._diag_dialog.deleteLater()
            self._diag_dialog = None

    def _run_diag_animation(self, port: int):
        """逐条展示诊断进度（过渡动画），完成后触发获取 BuddyKey"""
        from PySide6.QtCore import QTimer

        self._diag_step = 0

        def _advance():
            idx = self._diag_step
            if idx < len(self._diag_items_def):
                name, desc_template = self._diag_items_def[idx]
                desc = desc_template.replace("{port}", str(port))
                # 更新描述
                desc_label = self._diag_rows[idx][3]
                desc_label.setText(desc)
                # 标记为通过
                self._set_diag_row_status(idx, "通过", "success")
                self._diag_step += 1
                # 继续下一项
                QTimer.singleShot(400, _advance)
            else:
                # 全部完成 → 获取 BuddyKey
                self._fetch_buddykey()

        _advance()

    def _toggle_proxy_service(self):
        """启动/停止代理服务"""
        if not self._proxy_page:
            return

        ps = self._proxy_page._proxy_server
        if ps and ps.is_running:
            # 服务运行中 → 停止
            self._proxy_page._toggle_service()
            self._sync_proxy_status()
            return

        # 服务未运行 → 同步模型前缀到 ProxyDatabase
        model_prefix = self._model_prefix_input.text().strip()
        save_setting("model_prefix", model_prefix)
        try:
            db = ProxyDatabase.get_instance()
            db.update_settings({"model_prefix": model_prefix})
        except Exception:
            pass

        # 服务未运行 → 显示诊断弹窗
        port = self._port_spin.value()
        self._show_diag_dialog(port)
        self._toggle_proxy_btn.setEnabled(False)
        self._proxy_status_label.setText("⏳ 正在启动...")
        self._proxy_status_label.setStyleSheet("font-weight: 600; color: #D69E2E;")

        # 启动诊断动画
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, lambda: self._run_diag_animation(port))

    def _fetch_buddykey(self):
        """后台请求 BuddyKey"""
        from PySide6.QtCore import QThread, Signal as QSignal

        class BuddyKeyThread(QThread):
            done = QSignal(object)

            def run(self):
                from ...utils.server_api import get_buddykey
                try:
                    result = get_buddykey()
                    self.done.emit(result)
                except Exception as e:
                    self.done.emit({"success": False, "message": str(e)})

        self._buddykey_thread = BuddyKeyThread()
        self._buddykey_thread.done.connect(self._on_buddykey_done)
        self._buddykey_thread.finished.connect(lambda: setattr(self, '_buddykey_thread', None))
        self._buddykey_thread.start()

    def _on_buddykey_done(self, result: dict):
        """获取 BuddyKey 完成"""
        if not result or not result.get("success"):
            err = (result or {}).get("error") or (result or {}).get("message") or "未知错误"
            self._diag_title.setText("❌ 启动失败")
            self._proxy_status_label.setText("⏹ 已停止")
            self._proxy_status_label.setStyleSheet("font-weight: 600; color: #9BA4B0;")
            self._toggle_proxy_btn.setEnabled(True)
            self._close_diag_dialog()
            QMessageBox.warning(self, "启动失败", f"无法获取激活码：{err}")
            return

        buddy_key = result.get("buddyKey", "")
        if not buddy_key:
            self._diag_title.setText("❌ 启动失败")
            self._proxy_status_label.setText("⏹ 已停止")
            self._proxy_status_label.setStyleSheet("font-weight: 600; color: #9BA4B0;")
            self._toggle_proxy_btn.setEnabled(True)
            self._close_diag_dialog()
            QMessageBox.warning(self, "启动失败", "服务端未返回激活码")
            return

        # 在后台线程中处理 key 写入和服务启动，避免主线程阻塞
        from PySide6.QtCore import QThread, Signal as QSignal

        balance = result.get("balance", 0)

        class StartServiceThread(QThread):
            done = QSignal(bool)

            def __init__(self, dashboard_page, buddy_key_str, balance_val):
                super().__init__()
                self._dashboard = dashboard_page
                self._buddy_key = buddy_key_str
                self._balance = balance_val

            def run(self):
                try:
                    import secrets as _sec
                    from datetime import datetime
                    db = self._dashboard._proxy_page._db

                    # 清除旧的上游 key
                    for k in db.get_upstream_keys():
                        db.delete_upstream_key(k.get("key_id", ""))

                    db.add_upstream_key({
                        "key_id": f"bk_{_sec.token_hex(4)}",
                        "api_key": self._buddy_key,
                        "label": f"BuddyKey (余额 {self._balance:.1f})",
                        "status": "active",
                        "used_count": 0,
                        "points": str(self._balance),
                        "points_updated_at": datetime.now().isoformat(),
                        "created_at": datetime.now().isoformat(),
                    })
                    self._dashboard._proxy_page._invalidate_proxy_auth_cache()
                    self.done.emit(True)
                except Exception as e:
                    logger.error(f"启动服务失败: {e}")
                    self.done.emit(False)

        self._start_service_thread = StartServiceThread(self, buddy_key, balance)
        self._start_service_thread.done.connect(self._on_service_started)
        self._start_service_thread.finished.connect(lambda: setattr(self, '_start_service_thread', None))
        self._start_service_thread.start()

    def _on_service_started(self, success: bool):
        """服务启动完成回调（在主线程执行）"""
        if not success:
            self._diag_title.setText("❌ 启动失败")
            self._proxy_status_label.setText("⏹ 已停止")
            self._proxy_status_label.setStyleSheet("font-weight: 600; color: #9BA4B0;")
            self._toggle_proxy_btn.setEnabled(True)
            self._close_diag_dialog()
            QMessageBox.warning(self, "启动失败", "服务启动过程中发生错误")
            return

        # 启动代理服务（快速操作，不阻塞）
        self._proxy_page._toggle_service()
        self._toggle_proxy_btn.setEnabled(True)
        self._sync_proxy_status()

        # 关闭诊断弹窗
        self._close_diag_dialog()

    def _apply_toggle_btn_style(self):
        """根据服务状态设置按钮内联样式"""
        if not self._proxy_page:
            return
        ps = self._proxy_page._proxy_server
        if ps and ps.is_running:
            self._toggle_proxy_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self._colors['error']};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {self._colors['error']};
                    opacity: 0.9;
                }}
            """)
        else:
            self._toggle_proxy_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self._colors['accent']};
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {self._colors['accent_hover']};
                }}
            """)

    def _copy_proxy_url(self):
        """复制服务地址 — 转发给 ApiProxyPage"""
        if self._proxy_page:
            self._proxy_page._copy_url()
        else:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._proxy_url_label.text())

    def _copy_subkey(self):
        """复制子 API Key"""
        from PySide6.QtWidgets import QApplication
        key = self._subkey_label.text()
        if key and key != "sk-":
            QApplication.clipboard().setText(key)

    def _regen_subkey(self):
        """重新生成子 API Key"""
        if not self._proxy_page:
            return
        reply = QMessageBox.question(
            self, "确认",
            "重新生成后旧的 API Key 将失效，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        import secrets as _sec
        from datetime import datetime
        db = self._proxy_page._db

        # 删除旧的子 key，创建新的
        for sk in db.get_sub_api_keys():
            db.delete_sub_api_key(sk.get("key_id", ""))

        new_key = f"sk-{_sec.token_urlsafe(32)}"
        sub_key_data = {
            "key_id": f"sk_{_sec.token_hex(4)}",
            "api_key": new_key,
            "label": "",
            "is_active": True,
            "allowed_models": [],
            "allowed_key_ids": [],
            "max_usage": 0,
            "used_count": 0,
            "rate_limit_rpm": 1000,
            "key_mode": 1,
            "created_at": datetime.now().isoformat(),
        }
        db.add_sub_api_key(sub_key_data)
        self._proxy_page._invalidate_proxy_auth_cache()
        self._refresh_subkey_display()

    def _refresh_subkey_display(self):
        """刷新子 API Key 显示"""
        if not self._proxy_page:
            return
        sub_keys = self._proxy_page._db.get_sub_api_keys()
        if sub_keys:
            self._subkey_label.setText(sub_keys[0].get("api_key", "sk-"))
        else:
            self._subkey_label.setText("sk-（点击重新生成创建）")

    def _open_backup_dir(self):
        """打开备份目录"""
        import os
        from pathlib import Path
        backup_dir = Path.home() / ".buddy-tool" / "config_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(backup_dir)) if hasattr(os, 'startfile') else None

    def _save_client_config(self):
        """保存客户端配置选项"""
        save_setting("config_target_workbuddy", "true" if self._chk_workbuddy.isChecked() else "false")
        save_setting("config_target_codebuddy", "true" if self._chk_codebuddy.isChecked() else "false")
        save_setting("config_auto_backup", "true" if self._chk_auto_backup.isChecked() else "false")
        model_prefix = self._model_prefix_input.text().strip()
        save_setting("model_prefix", model_prefix)
        # 同步写入 ProxyDatabase，代理服务请求上游时用这个去掉前缀
        try:
            db = ProxyDatabase.get_instance()
            db.update_settings({"model_prefix": model_prefix})
        except Exception:
            pass

    def _build_config_json(self) -> str:
        """根据当前端口、子 API Key 和服务端模型列表生成配置 JSON"""
        import json
        import secrets as _sec
        from datetime import datetime
        from ...modules.proxy_server import SUPPORTED_MODELS, MODEL_CONTEXT_LENGTHS, MODEL_MAX_OUTPUT_TOKENS

        port = self._port_spin.value()
        sub_keys = self._proxy_page._db.get_sub_api_keys() if self._proxy_page else []
        api_key = sub_keys[0].get("api_key", "") if sub_keys else ""

        # 如果没有子 API Key，自动生成一个
        if not api_key and self._proxy_page:
            api_key = f"sk-{_sec.token_urlsafe(32)}"
            self._proxy_page._db.add_sub_api_key({
                "key_id": f"sk_{_sec.token_hex(4)}",
                "api_key": api_key,
                "label": "",
                "is_active": True,
                "allowed_models": [],
                "allowed_key_ids": [],
                "max_usage": 0,
                "used_count": 0,
                "rate_limit_rpm": 1000,
                "key_mode": 1,
                "created_at": datetime.now().isoformat(),
            })
            self._proxy_page._invalidate_proxy_auth_cache()
            self._refresh_subkey_display()

        url = f"http://127.0.0.1:{port}/v1/chat/completions"

        # 模型前缀
        prefix = self._model_prefix_input.text().strip()

        # 优先从服务端获取模型列表
        models = []
        try:
            from ...utils.server_api import get_models_list
            result = get_models_list()
            if result and not result.get("error") and result.get("models"):
                for m in result["models"]:
                    model_id = m.get("id", "")
                    if not model_id:
                        continue
                    models.append({
                        "id": f"{prefix}{model_id}" if prefix else model_id,
                        "name": m.get("name", model_id),
                        "vendor": "Buddy",
                        "apiKey": api_key,
                        "url": url,
                        "maxInputTokens": m.get("maxInputTokens", 128000),
                        "maxOutputTokens": m.get("maxOutputTokens", 8192),
                        "supportsToolCall": m.get("supportsToolCall", True),
                        "supportsImages": m.get("supportsImages", True),
                        "supportsReasoning": m.get("supportsReasoning", True),
                    })
        except Exception as e:
            logger.warning(f"从服务端获取模型列表失败: {e}")

        # 服务端获取失败时，使用本地硬编码模型列表作为 fallback
        if not models:
            _name_map = {
                "auto": "自动模式（智能选择）",
                "deepseek-v4-pro": "DeepSeek V4 Pro",
                "deepseek-v4-flash": "DeepSeek V4 Flash",
                "deepseek-v3-2-volc": "DeepSeek V3.2",
                "deepseek-v3-1": "DeepSeek V3.1",
                "deepseek-v3-0324": "DeepSeek V3-0324",
                "deepseek-r1": "DeepSeek R1",
                "glm-5.2": "GLM-5.2",
                "glm-5.1": "GLM-5.1",
                "glm-5.0": "GLM-5.0",
                "glm-5.0-turbo": "GLM-5.0 Turbo",
                "glm-5v-turbo": "GLM-5v Turbo",
                "glm-4.7": "GLM-4.7",
                "glm-4.6": "GLM-4.6",
                "minimax-m3": "MiniMax M3",
                "minimax-m2.7": "MiniMax M2.7",
                "minimax-m2.5": "MiniMax M2.5",
                "kimi-k2.6": "Kimi K2.6",
                "kimi-k2.5": "Kimi K2.5",
                "kimi-k2.7": "Kimi K2.7",
                "hy3": "Hy3",
                "hy3-preview": "Hy3 Preview",
                "hunyuan-chat": "Hunyuan Chat",
                "hunyuan-2.0-thinking": "Hunyuan 2.0 Thinking",
            }
            for m in SUPPORTED_MODELS:
                models.append({
                    "id": f"{prefix}{m}" if prefix else m,
                    "name": _name_map.get(m, m),
                    "vendor": "Buddy",
                    "apiKey": api_key,
                    "url": url,
                    "maxInputTokens": MODEL_CONTEXT_LENGTHS.get(m, 128000),
                    "maxOutputTokens": MODEL_MAX_OUTPUT_TOKENS.get(m, 8192),
                    "supportsToolCall": True,
                    "supportsImages": True,
                    "supportsReasoning": True,
                })

        return json.dumps({"models": models}, ensure_ascii=False, indent=2)

    def _copy_config(self):
        """复制配置 JSON 到剪贴板"""
        self._save_client_config()
        from PySide6.QtWidgets import QApplication
        config_json = self._build_config_json()
        QApplication.clipboard().setText(config_json)
        QMessageBox.information(self, "复制成功", "配置 JSON 已复制到剪贴板")

    def _delete_config(self):
        """删除配置"""
        self._save_client_config()
        if not self._proxy_page:
            return

        targets = []
        if self._chk_workbuddy.isChecked():
            targets.append("WorkBuddy")
        if self._chk_codebuddy.isChecked():
            targets.append("CodeBuddy")

        if not targets:
            QMessageBox.warning(self, "提示", "请先选择要删除的目标客户端")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除 {' + '.join(targets)} 的配置文件吗？\n\n删除后这些客户端将无法使用已配置的模型。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._chk_workbuddy.isChecked() and hasattr(self._proxy_page, '_delete_workbuddy_config'):
            try:
                self._proxy_page._delete_workbuddy_config()
            except Exception as e:
                logger.error(f"删除 WorkBuddy 配置失败: {e}")
        if self._chk_codebuddy.isChecked() and hasattr(self._proxy_page, '_delete_codebuddy_config'):
            try:
                self._proxy_page._delete_codebuddy_config()
            except Exception as e:
                logger.error(f"删除 CodeBuddy 配置失败: {e}")

    def _apply_config(self):
        """立即配置 — 生成 JSON 并写入所选客户端的 models.json"""
        self._save_client_config()
        if not self._proxy_page:
            return

        from pathlib import Path
        import os
        from datetime import datetime
        from shutil import copy2

        config_json = self._build_config_json()
        success_clients = []

        targets = []
        if self._chk_workbuddy.isChecked():
            targets.append(("WorkBuddy", Path.home() / ".workbuddy"))
        if self._chk_codebuddy.isChecked():
            targets.append(("CodeBuddy", Path.home() / ".codebuddy"))

        if not targets:
            QMessageBox.warning(self, "提示", "请先勾选目标客户端")
            return

        # 确认弹窗
        client_names = ' + '.join(name for name, _ in targets)
        reply = QMessageBox.question(
            self, "确认配置",
            f"是否立即配置并重启 {client_names}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 自动备份
        if self._chk_auto_backup.isChecked():
            backup_root = Path.home() / ".buddy-tool" / "config_backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            for name, target_dir in targets:
                src = target_dir / "models.json"
                if src.exists():
                    dst = backup_root / f"{name.lower()}_{ts}.json"
                    try:
                        copy2(str(src), str(dst))
                    except Exception as e:
                        logger.warning(f"备份 {name} 配置失败: {e}")

        # 写入配置
        for name, target_dir in targets:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / "models.json"
                target_path.write_text(config_json, encoding="utf-8")
                success_clients.append(name)
            except Exception as e:
                logger.error(f"配置 {name} 失败: {e}")

        if success_clients:
            # 如果勾选了 WorkBuddy，后台配置调试端口并重启
            if self._chk_workbuddy.isChecked():
                from PySide6.QtCore import QThread, Signal as QSignal

                class _WorkbuddySetupThread(QThread):
                    done = QSignal(bool, str)

                    def run(self):
                        try:
                            from ...utils.setup_debug_port import setup_and_restart
                            ok, msg = setup_and_restart()
                            self.done.emit(ok, msg)
                        except Exception as e:
                            self.done.emit(False, str(e))

                self._workbuddy_setup_thread = _WorkbuddySetupThread()
                self._workbuddy_setup_thread.done.connect(self._on_workbuddy_setup_done)
                self._workbuddy_setup_thread.finished.connect(
                    lambda: setattr(self, '_workbuddy_setup_thread', None)
                )
                self._workbuddy_setup_thread.start()
            else:
                # 没勾选 WorkBuddy，直接弹提示
                QMessageBox.information(self, "提示", "配置已更新，请启动服务开始使用")

    def _on_workbuddy_setup_done(self, ok: bool, msg: str):
        """WorkBuddy 调试端口配置完成 — 等待 WorkBuddy 启动后弹提示"""
        from PySide6.QtCore import QThread, Signal as QSignal

        class _WaitWorkbuddyThread(QThread):
            """等待 WorkBuddy 启动（检测 CDP 端口），最多5秒"""
            done = QSignal()

            def run(self):
                import time
                import urllib.request
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=1).read()
                        break
                    except Exception:
                        time.sleep(0.5)
                self.done.emit()

        self._wait_workbuddy_thread = _WaitWorkbuddyThread()
        self._wait_workbuddy_thread.done.connect(lambda: QMessageBox.information(
            self, "提示", "配置已更新，请启动服务开始使用"
        ))
        self._wait_workbuddy_thread.finished.connect(
            lambda: setattr(self, '_wait_workbuddy_thread', None)
        )
        self._wait_workbuddy_thread.start()

    def _on_port_changed(self):
        """端口变化时更新 URL 显示"""
        port = self._port_spin.value()
        if self._proxy_page:
            ips = self._proxy_page._get_local_ips()
        else:
            ips = []
        host = ips[0] if ips else "0.0.0.0"
        self._proxy_url_label.setText(f"http://127.0.0.1:{port}/v1/chat/completions")

    def _sync_proxy_status(self):
        """从 ApiProxyPage 同步服务状态到仪表盘"""
        if not self._proxy_page:
            return
        ps = self._proxy_page._proxy_server
        if ps and ps.is_running:
            port = self._port_spin.value()
            ips = self._proxy_page._get_local_ips()
            host = ips[0] if ips else "0.0.0.0"
            self._proxy_status_label.setText(f"▶ 运行中 :{port}")
            self._proxy_status_label.setStyleSheet("font-weight: 600; color: #38A169;")
            self._toggle_proxy_btn.setText("⏹ 停止服务")
            self._port_spin.setEnabled(False)
            self._proxy_url_label.setText(f"http://127.0.0.1:{port}/v1/chat/completions")
        else:
            self._proxy_status_label.setText("⏹ 已停止")
            self._proxy_status_label.setStyleSheet("font-weight: 600; color: #9BA4B0;")
            self._toggle_proxy_btn.setText("▶ 启动服务")
            self._port_spin.setEnabled(True)
        self._apply_toggle_btn_style()

    def showEvent(self, event):
        """页面显示时刷新数据并应用缩放"""
        super().showEvent(event)
        # 安全网：确保 QScrollArea viewport 背景跟随主题（Qt 内部可能重置 viewport palette）
        self._apply_scroll_background()
        self._apply_responsive_scale()
        self._sync_proxy_status()
        self._refresh_subkey_display()
        # 积分：首次打开从后端查询，后续切页面用本地缓存
        if not self._credits_loaded:
            self._refresh_credits()
        else:
            self._load_cached_credits()
