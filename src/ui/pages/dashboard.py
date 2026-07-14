"""仪表盘页面 — 支持响应式缩放，窗口缩小时文字和UI同步缩小"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QButtonGroup, QApplication, QScrollArea, QSpinBox, QComboBox,
    QMessageBox, QCheckBox
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


class DashboardPage(QWidget):
    """仪表盘页面 — 纯本地数据概览，不自动发网络请求，支持响应式缩放"""

    _REF_WIDTH = 980    # 参考宽度（100%缩放时的可用内容宽度）
    _MIN_SCALE = 0.7    # 最小缩放比例

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("content_area")
        self._usage_range = "today"  # 使用情况时间范围: today/7d/30d/all
        self._colors = _current_theme_colors()
        self._scale = 1.0
        self._all_cards = []
        self._proxy_page = None  # ApiProxyPage 引用，由 MainWindow 注入
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel(t("nav.dashboard"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("全局概览（本地数据，需查询请前往对应页面）")
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

        # 统计卡片网格
        grid = QGridLayout()
        grid.setSpacing(16)

        self._card_total = StatCard("总账号数", "--", "👥", "accent")
        self._card_active = StatCard("活跃账号", "--", "✅", "success")
        self._card_quota = StatCard("总剩余积分", "--", "💎", "accent")

        grid.addWidget(self._card_total, 0, 0)
        grid.addWidget(self._card_active, 0, 1)
        grid.addWidget(self._card_quota, 0, 2)

        content_layout.addLayout(grid)
        self._account_grid = grid

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
        self._proxy_url_label = QLabel("http://127.0.0.1:8002/v1/chat/completions")
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

        client_title = QLabel("选择目标客户端（可多选）")
        client_title.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {self._colors['text_primary']};"
        )
        proxy_ctrl_layout.addWidget(client_title)

        # 复选框样式 — 带对号
        _chk_style = f"""
            QCheckBox {{
                color: {self._colors['text_primary']};
                font-size: 13px;
                spacing: 8px;
                padding: 4px 0;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {self._colors['border']};
                border-radius: 4px;
                background-color: transparent;
            }}
            QCheckBox::indicator:hover {{
                border-color: {self._colors['accent']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self._colors['accent']};
                border-color: {self._colors['accent']};
                image: none;
            }}
        """

        # WorkBuddy
        self._chk_workbuddy = QCheckBox(f"WorkBuddy  腾讯代码助手桌面版  ✓ C:\\Users\\{_username}\\.workbuddy")
        self._chk_workbuddy.setChecked(load_setting("config_target_workbuddy", "true") == "true")
        self._chk_workbuddy.setStyleSheet(_chk_style)
        proxy_ctrl_layout.addWidget(self._chk_workbuddy)

        # CodeBuddy
        self._chk_codebuddy = QCheckBox(f"CodeBuddy  腾讯云 AI IDE 插件  ✓ C:\\Users\\{_username}\\.codebuddy")
        self._chk_codebuddy.setChecked(load_setting("config_target_codebuddy", "true") == "true")
        self._chk_codebuddy.setStyleSheet(_chk_style)
        proxy_ctrl_layout.addWidget(self._chk_codebuddy)

        # 自动备份 + 打开备份目录
        self._chk_auto_backup = QCheckBox("配置前自动备份原文件（推荐）")
        self._chk_auto_backup.setChecked(load_setting("config_auto_backup", "true") == "true")
        self._chk_auto_backup.setStyleSheet(_chk_style)

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

        # === 使用情况区域 ===
        self._usage_title = QLabel("📊 使用情况")
        self._usage_title.setStyleSheet(
            f"font-size: 16px; font-weight: 600; margin-top: 8px; color: {self._colors['text_primary']};"
        )
        content_layout.addWidget(self._usage_title)

        # 时间范围切换按钮
        range_layout = QHBoxLayout()
        range_layout.setSpacing(8)

        self._range_btn_group = QButtonGroup(self)
        self._range_btn_group.setExclusive(True)

        range_configs = [
            ("today", "今日"),
            ("7d", "近7天"),
            ("30d", "近30天"),
            ("all", "总计"),
        ]
        self._range_buttons = []
        for key, label_text in range_configs:
            btn = QPushButton(label_text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("range_key", key)
            if key == self._usage_range:
                btn.setChecked(True)
                btn.setStyleSheet(self._range_btn_style_active())
            else:
                btn.setStyleSheet(self._range_btn_style_normal())
            self._range_btn_group.addButton(btn)
            self._range_buttons.append(btn)
            range_layout.addWidget(btn)

        range_layout.addStretch()
        content_layout.addLayout(range_layout)

        self._range_btn_group.buttonClicked.connect(self._on_range_changed)

        # 使用情况统计卡片（5个）
        usage_grid = QGridLayout()
        usage_grid.setSpacing(16)

        self._usage_card_credits = StatCard("消耗积分", "--", "💰", "warning")
        self._usage_card_prompt = StatCard("输入", "--", "⬆️", "accent")
        self._usage_card_completion = StatCard("输出", "--", "⬇️", "success")
        self._usage_card_total = StatCard("总Token", "--", "🔢", "accent")
        self._usage_card_count = StatCard("请求数量", "--", "📈", "accent")

        usage_grid.addWidget(self._usage_card_credits, 0, 0)
        usage_grid.addWidget(self._usage_card_prompt, 0, 1)
        usage_grid.addWidget(self._usage_card_completion, 0, 2)
        usage_grid.addWidget(self._usage_card_total, 0, 3)
        usage_grid.addWidget(self._usage_card_count, 0, 4)

        content_layout.addLayout(usage_grid)
        self._usage_grid = usage_grid

        # 缓存命中率图表区域
        self._cache_frame = QFrame()
        self._apply_cache_frame_style()
        cache_layout = QHBoxLayout(self._cache_frame)
        cache_layout.setContentsMargins(20, 16, 20, 16)
        cache_layout.setSpacing(20)

        # 环形图
        self._cache_chart = CacheHitRateChart()

        # 右侧：标题 + 命中详情
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        self._cache_title = QLabel("命中率统计")
        self._cache_title.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {self._colors['text_primary']};"
        )
        right_layout.addWidget(self._cache_title)

        # 6 项命中指标（3行 x 2列）
        self._legend_labels = {}
        self._legend_values = {}
        legend_grid = QGridLayout()
        legend_grid.setSpacing(8)

        legend_items = [
            ("input_hit", "输入命中", "success"),
            ("input_rate", "输入命中率", "success"),
            ("output_hit", "输出命中", "text_tertiary"),
            ("output_rate", "输出命中率", "text_tertiary"),
            ("total_hit", "总命中", "accent"),
            ("total_rate", "总命中率", "accent"),
        ]
        for idx, (key, label_text, color_key) in enumerate(legend_items):
            row = idx // 2
            col = idx % 2
            label = QLabel()
            label.setTextFormat(Qt.TextFormat.RichText)
            legend_grid.addWidget(label, row, col)
            self._legend_labels[key] = (label, color_key, label_text)
            self._legend_values[key] = "--"
            self._render_legend(key)

        right_layout.addLayout(legend_grid)
        right_layout.addStretch()

        cache_layout.addWidget(self._cache_chart)
        cache_layout.addWidget(right_panel, 1)
        content_layout.addWidget(self._cache_frame)

        content_layout.addStretch()

        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        # 显式设置背景色（必须在 setWidget 之后，QScrollArea viewport 默认用系统 palette 不跟主题）
        self._apply_scroll_background()

        # 收集所有静态卡片用于缩放
        self._all_cards = [
            self._card_total, self._card_active, self._card_quota,
            self._usage_card_credits, self._usage_card_prompt, self._usage_card_completion,
            self._usage_card_total, self._usage_card_count,
        ]

    # === 响应式缩放 ===

    def resizeEvent(self, event):
        """窗口大小变化时重新计算缩放比例"""
        super().resizeEvent(event)
        self._apply_responsive_scale()

    def _apply_responsive_scale(self):
        """根据当前可用宽度计算缩放比例并应用到所有UI元素"""
        # 安全检查：UI 未完全初始化时跳过（resizeEvent 可能在 _setup_ui 期间被触发）
        if not getattr(self, '_all_cards', None) or not hasattr(self, '_cache_chart'):
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

        # 缩放环形图
        self._cache_chart.apply_scale(s)

        # 缩放网格间距
        spacing = int(16 * s)
        self._account_grid.setSpacing(spacing)
        self._usage_grid.setSpacing(spacing)

        # 缩放区域标题
        self._usage_title.setStyleSheet(
            f"font-size: {int(16 * s)}px; font-weight: 600; margin-top: 8px; color: {self._colors['text_primary']};"
        )

        # 缩放缓存区域标题
        self._cache_title.setStyleSheet(
            f"font-size: {int(14 * s)}px; font-weight: 600; color: {self._colors['text_primary']};"
        )

        # 缩放图例文字（重新渲染，带缩放后的字号）
        for key in self._legend_labels:
            self._render_legend(key)

        # 缩放时间范围按钮
        for btn in self._range_buttons:
            if btn.isChecked():
                btn.setStyleSheet(self._range_btn_style_active())
            else:
                btn.setStyleSheet(self._range_btn_style_normal())

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
        """缓存命中率图表区域样式"""
        c = self._colors
        self._cache_frame.setStyleSheet(
            f"QFrame {{ background-color: {c['bg_secondary']}; "
            f"border: 1px solid {c['border']}; border-radius: 8px; }}"
        )

    def _range_btn_style_active(self) -> str:
        """选中状态按钮样式（跟随缩放）"""
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
        """未选中状态按钮样式（跟随缩放）"""
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

        # 缓存命中率图表
        self._cache_chart.apply_theme(self._colors)
        self._apply_cache_frame_style()

        # 统计卡片
        for card in self._all_cards:
            card.apply_theme(self._colors)

        # 刷新代理按钮样式
        self._apply_toggle_btn_style()

        # 重新应用响应式缩放（会刷新所有带缩放的样式）
        self._apply_responsive_scale()

    # === 数字格式化 ===

    @staticmethod
    def _format_token_count(value: int) -> str:
        """将 Token/数字按大小格式化为中文单位，保留 2 位小数

        规则：
        - < 1万：原样显示（千分位）
        - 1万 ~ < 1百万：以"万"为单位（如 12.34万）
        - 1百万 ~ < 1亿：以"百万"为单位（如 12.34百万）
        - >= 1亿：以"亿"为单位（如 1.23亿）
        """
        v = float(value)
        if v < 10_000:
            return f"{int(v):,}"
        if v < 1_000_000:
            return f"{v / 10_000:.2f}万"
        if v < 100_000_000:
            return f"{v / 1_000_000:.2f}百万"
        return f"{v / 100_000_000:.2f}亿"

    # === 图例渲染 ===

    def _render_legend(self, key: str):
        """渲染单项图例（富文本：彩色圆点 + 标签 + 值，字号跟随缩放）"""
        if key not in self._legend_labels:
            return
        label, color_key, label_text = self._legend_labels[key]
        value = self._legend_values.get(key, "--")
        color_val = self._colors.get(color_key, self._colors["accent"])
        text_col = self._colors["text_secondary"]
        font_size = int(13 * self._scale)
        label.setText(
            f'<span style="color:{color_val}; font-size:{font_size}px;">●</span> '
            f'<span style="color:{text_col}; font-size:{font_size}px;">{label_text}  {value}</span>'
        )

    def _update_legend(self, key: str, value: str):
        """更新单项图例的数值"""
        if key in self._legend_labels:
            self._legend_values[key] = value
            self._render_legend(key)

    def _refresh_legend_colors(self):
        """主题切换后刷新所有图例颜色（保持数值不变）"""
        for key in self._legend_labels:
            self._render_legend(key)

    # === 事件回调 ===

    def _on_range_changed(self, btn):
        """时间范围切换回调"""
        key = btn.property("range_key")
        if key and key != self._usage_range:
            self._usage_range = key
            for b in self._range_buttons:
                if b.isChecked():
                    b.setStyleSheet(self._range_btn_style_active())
                else:
                    b.setStyleSheet(self._range_btn_style_normal())
            self._refresh_usage()

    def _refresh_usage(self):
        """刷新使用情况数据"""
        db = ProxyDatabase.get_instance()
        days_map = {"today": 1, "7d": 7, "30d": 30, "all": None}
        days = days_map.get(self._usage_range, 1)
        summary = db.get_usage_summary(days=days)

        # 更新5个统计卡片
        prompt = summary["prompt_tokens"]
        completion = summary["completion_tokens"]
        total_tokens = prompt + completion
        cached = summary["cached_tokens"]

        self._usage_card_credits.set_value(f"{summary['credits']:,.2f}")
        self._usage_card_prompt.set_value(self._format_token_count(prompt))
        self._usage_card_completion.set_value(self._format_token_count(completion))
        self._usage_card_total.set_value(self._format_token_count(total_tokens))
        self._usage_card_count.set_value(self._format_token_count(summary["count"]))

        # 计算各项命中率
        input_hit = cached
        input_rate = cached / prompt if prompt > 0 else 0.0
        output_hit = 0  # 输出无缓存命中机制
        output_rate = 0.0
        total_hit = cached  # 输入命中 + 输出命中(0)
        total_rate = cached / total_tokens if total_tokens > 0 else 0.0

        # 更新环形图（中心显示总命中率）
        self._cache_chart.set_rate(total_rate)

        # 更新 6 项图例
        self._update_legend("input_hit", self._format_token_count(input_hit))
        self._update_legend("input_rate", f"{input_rate * 100:.1f}%")
        self._update_legend("output_hit", self._format_token_count(output_hit))
        self._update_legend("output_rate", f"{output_rate * 100:.1f}%")
        self._update_legend("total_hit", self._format_token_count(total_hit))
        self._update_legend("total_rate", f"{total_rate * 100:.1f}%")

    def _refresh_data(self):
        """刷新仪表盘数据（纯本地，不联网）"""
        accounts = load_accounts()

        # 统计卡片
        total = len(accounts)
        active = len([a for a in accounts if a.status == AccountStatus.ACTIVE])

        # 计算总积分（仅统计已查询过的）
        has_queried = [a for a in accounts if a.quota.credits_total > 0]
        total_credits = sum(a.quota.credits_remaining for a in has_queried)

        self._card_total.set_value(str(total))
        self._card_active.set_value(str(active))
        if has_queried:
            self._card_quota.set_value(f"{total_credits:.0f}")
        else:
            self._card_quota.set_value("--")

        # 刷新使用情况
        self._refresh_usage()

    def set_proxy_page(self, proxy_page):
        """注入 ApiProxyPage 引用，用于服务控制"""
        self._proxy_page = proxy_page

    def _toggle_proxy_service(self):
        """启动/停止代理服务 — 转发给 ApiProxyPage"""
        if self._proxy_page:
            self._proxy_page._toggle_service()
            self._sync_proxy_status()

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

    def _build_config_json(self) -> str:
        """根据当前端口、子 API Key 和 SUPPORTED_MODELS 生成配置 JSON"""
        import json
        from ...modules.proxy_server import SUPPORTED_MODELS, MODEL_CONTEXT_LENGTHS, MODEL_MAX_OUTPUT_TOKENS

        port = self._port_spin.value()
        sub_keys = self._proxy_page._db.get_sub_api_keys() if self._proxy_page else []
        api_key = sub_keys[0].get("api_key", "") if sub_keys else ""
        url = f"http://127.0.0.1:{port}/v1/chat/completions"

        # 模型名称映射
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

        models = []
        for m in SUPPORTED_MODELS:
            models.append({
                "id": m,
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
            QMessageBox.information(
                self, "配置完成",
                f"已配置 {' + '.join(success_clients)}！\n请重启对应的客户端使配置生效。"
            )

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
        self._refresh_data()
