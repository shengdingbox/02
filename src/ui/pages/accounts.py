"""账号管理页面"""

import secrets
import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLineEdit,
    QDialog, QTextEdit, QFileDialog, QMessageBox,
    QMenu, QAbstractItemView, QSpinBox, QProgressBar,
    QGridLayout, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor

from ...i18n import t
from ...models import Account, Platform, AccountStatus, ResourcePackage
from ...utils.store import load_accounts, save_account, delete_account, save_setting, load_setting
from ...modules.api_client import ApiClient, check_api_key_chat_status
from ..styles.theme import DARK_THEME, LIGHT_THEME
from .dashboard import StatCard, CacheHitRateChart

logger = logging.getLogger(__name__)

PAGE_SIZE = 100  # 每页显示条数


def _current_theme_colors() -> dict:
    """获取当前主题色板（亮/暗），用于 viewport 等需要动态背景色的地方"""
    from PySide6.QtWidgets import QApplication
    theme = load_setting("theme", "system")
    if theme == "system":
        app = QApplication.instance()
        is_dark = bool(app and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
        theme = "dark" if is_dark else "light"
    return DARK_THEME if theme == "dark" else LIGHT_THEME


class AddAccountDialog(QDialog):
    """激活卡密对话框

    输入卡密，调用服务端 /api/redeem 接口激活，
    激活成功后卡密和返回的 userKey 存到本地。
    """

    account_added = Signal(Account)

    REDEEM_URL = "https://buddy.shengdingit.com/api/redeem"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("激活卡密")
        self.setMinimumWidth(460)
        self._redeem_thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 说明
        hint = QLabel("输入卡密激活，激活后卡密将保存到本地")
        hint.setStyleSheet("color: #718096; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 卡密输入框（单行）
        self._input = QLineEdit()
        self._input.setPlaceholderText("CK_XXXXX_XXXXX_1000")
        self._input.setMinimumHeight(36)
        self._input.returnPressed.connect(self._do_redeem)
        layout.addWidget(self._input)

        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #9BA4B0; font-size: 12px;")
        layout.addWidget(self._status_label)

        # 按钮行
        btn_row = QHBoxLayout()

        self._btn_redeem = QPushButton("🚀 激活")
        self._btn_redeem.setObjectName("primary_btn")
        self._btn_redeem.setCursor(Qt.PointingHandCursor)
        self._btn_redeem.setMinimumHeight(36)
        self._btn_redeem.clicked.connect(self._do_redeem)
        btn_row.addWidget(self._btn_redeem)

        btn_cancel = QPushButton(t("common.cancel"))
        btn_cancel.setObjectName("secondary_btn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_row.addStretch()

        layout.addLayout(btn_row)

    def _do_redeem(self):
        """调用服务端激活卡密"""
        card_key = self._input.text().strip()
        if not card_key:
            QMessageBox.warning(self, t("common.warning"), "请输入卡密")
            return

        self._btn_redeem.setEnabled(False)
        self._status_label.setText("⏳ 正在激活卡密...")
        self._status_label.setStyleSheet("color: #D69E2E; font-size: 12px;")

        from PySide6.QtCore import QThread, Signal as QSignal
        from ...utils.server_api import redeem

        class RedeemThread(QThread):
            done = QSignal(object)  # result dict or None

            def __init__(self, card_key_str):
                super().__init__()
                self._card_key = card_key_str

            def run(self):
                try:
                    result = redeem(self._card_key)
                    self.done.emit(result)
                except Exception as e:
                    self.done.emit({"success": False, "message": str(e)})

        self._redeem_thread = RedeemThread(card_key)
        self._redeem_thread.done.connect(self._on_redeem_done)
        self._redeem_thread.start()

    def _on_redeem_done(self, result: dict):
        """激活完成回调"""
        self._btn_redeem.setEnabled(True)

        if not result:
            self._status_label.setText("❌ 激活失败：无响应")
            self._status_label.setStyleSheet("color: #E53E3E; font-size: 12px;")
            return

        success = result.get("success", False) or result.get("code") == 0
        if not success:
            msg = result.get("message") or result.get("msg") or "未知错误"
            self._status_label.setText(f"❌ 激活失败：{msg}")
            self._status_label.setStyleSheet("color: #E53E3E; font-size: 12px;")
            return

        # 激活成功，获取 userKey
        user_key = result.get("userKey") or result.get("user_key") or ""
        card_key = self._input.text().strip()
        nickname = f"卡密_{secrets.token_hex(4)}"

        # 保存到本地数据库
        account = Account(
            uid=card_key,
            nickname=nickname,
            platform=Platform.CODEBUDDY,
            auth_token=user_key or card_key,
            domain="www.codebuddy.cn",
            ck=card_key,
            api_key=user_key or card_key,
        )
        save_account(account)

        # 同步上游 Key 池
        try:
            from ...modules.proxy_server import ProxyDatabase
            proxy_db = ProxyDatabase.get_instance()
            existing_api_keys = {k.get("api_key", "") for k in proxy_db.get_upstream_keys()}
            api_key = user_key or card_key
            if api_key and api_key not in existing_api_keys:
                proxy_db.add_upstream_key({
                    "key_id": f"ck_{secrets.token_hex(4)}",
                    "api_key": api_key,
                    "label": nickname,
                    "status": "active",
                    "used_count": 0,
                    "points": "",
                    "points_updated_at": "",
                    "created_at": datetime.now().isoformat(),
                })
        except Exception:
            pass

        # 通知刷新
        self.account_added.emit(account)

        msg = f"✅ 激活成功: {nickname}"
        if user_key:
            msg += f"\n🔑 userKey: {user_key[:20]}..."
        self._status_label.setText(msg)
        self._status_label.setStyleSheet("color: #38A169; font-size: 12px;")

        # 完成
        self.accept()


class CreditsDetailDialog(QDialog):
    """积分明细对话框 - 显示每个积分包的详细信息"""

    def __init__(self, account: Account, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 积分明细")
        self.setMinimumWidth(620)
        self.setMinimumHeight(400)
        self._account = account
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 标题：手机号/UID
        header = QLabel(f"📱 {self._account.uid}")
        header.setStyleSheet("font-size: 16px; font-weight: 700; padding: 4px 0;")
        layout.addWidget(header)

        # 积分包表格
        self._pkg_table = QTableWidget()
        self._pkg_table.setColumnCount(5)
        self._pkg_table.setHorizontalHeaderLabels(["积分包", "类型", "剩余", "总量", "过期时间"])
        self._pkg_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._pkg_table.setAlternatingRowColors(True)
        self._pkg_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pkg_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._pkg_table)

        # 填充数据
        packages: list[ResourcePackage] = self._account.quota.packages
        self._pkg_table.setRowCount(len(packages))

        total_remain = 0.0
        base_remain = 0.0
        activity_remain = 0.0

        for row, pkg in enumerate(packages):
            self._pkg_table.setItem(row, 0, QTableWidgetItem(pkg.package_name))

            # 类型标签
            type_map = {"1": "基础", "2": "付费", "4": "体验"}
            type_text = type_map.get(pkg.package_type, pkg.package_type)
            self._pkg_table.setItem(row, 1, QTableWidgetItem(type_text))

            # 剩余（用 cycle_remain 周期剩余，capacity_remain 对基础包不更新）
            remain_item = QTableWidgetItem(f"{pkg.cycle_remain:.1f}")
            if pkg.cycle_remain <= 0:
                remain_item.setForeground(Qt.red)
            self._pkg_table.setItem(row, 2, remain_item)

            # 总量
            self._pkg_table.setItem(row, 3, QTableWidgetItem(f"{pkg.cycle_size:.1f}"))

            # 过期时间
            expire_text = self._format_expire(pkg.cycle_end)
            expire_item = QTableWidgetItem(expire_text)
            self._pkg_table.setItem(row, 4, expire_item)

            # 统计（用 cycle_remain 统计）
            total_remain += pkg.cycle_remain
            if pkg.package_type in ("1", "4"):
                base_remain += pkg.cycle_remain
            elif pkg.package_type == "2":
                activity_remain += pkg.cycle_remain
            else:
                activity_remain += pkg.cycle_remain

        # 如果没有积分包数据但有总量信息
        if not packages and (self._account.quota.credits_total > 0 or self._account.quota.credits_remaining > 0):
            total_remain = self._account.quota.credits_remaining
            base_remain = total_remain

        # 汇总信息
        summary_frame = QFrame()
        summary_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(43, 108, 176, 0.06);
                border: 1px solid rgba(43, 108, 176, 0.15);
                border-radius: 8px;
                padding: 10px 16px;
            }
        """)
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(16, 10, 16, 10)
        summary_layout.setSpacing(4)

        total_label = QLabel(f"<b>总剩余:</b> {total_remain:.1f}")
        total_label.setStyleSheet("font-size: 14px;")
        summary_layout.addWidget(total_label)

        detail_parts = []
        if base_remain > 0:
            detail_parts.append(f"基础: {base_remain:.1f}")
        if activity_remain > 0:
            detail_parts.append(f"活动: {activity_remain:.1f}")
        if detail_parts:
            detail_label = QLabel("　".join(detail_parts))
            detail_label.setStyleSheet("color: #5F6B7A; font-size: 12px;")
            summary_layout.addWidget(detail_label)

        layout.addWidget(summary_frame)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.setObjectName("primary_btn")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    @staticmethod
    def _format_expire(cycle_end: str) -> str:
        """格式化过期时间，附带剩余天数"""
        if not cycle_end:
            return "-"
        try:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(cycle_end[:19] if len(cycle_end) > 19 else cycle_end, fmt)
                    break
                except ValueError:
                    continue
            else:
                return cycle_end

            now = datetime.now()
            diff = dt - now
            days = diff.days

            time_str = dt.strftime("%Y-%m-%d %H:%M")
            if days < 0:
                return f"{time_str} (已过期)"
            elif days == 0:
                return f"{time_str} (今天过期)"
            else:
                return f"{time_str} ({days}天后)"
        except Exception:
            return cycle_end


class AccountsPage(QWidget):
    """账号管理页面"""

    quota_updated = Signal()  # 积分更新信号，通知其他页面刷新

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("content_area")
        self._accounts = []
        self._filtered_accounts = []
        self._usage_logs = []
        self._current_page = 0
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
        self._usage_range = "today"  # 使用情况时间范围: today/7d/30d/all
        self._colors = _current_theme_colors()
        self._scale = 1.0
        self._all_usage_cards = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel(t("accounts.title"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("积分额度与消耗明细")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # 内容区域
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(16)

        # 隐藏控件（保留引用避免报错）
        self._btn_batch_del = QPushButton()
        self._btn_batch_del.setVisible(False)
        self._btn_batch_export = QPushButton()
        self._btn_batch_export.setVisible(False)
        self._btn_query_all = QPushButton()
        self._btn_query_all.setVisible(False)
        self._btn_check_status = QPushButton()
        self._btn_check_status.setVisible(False)
        self._btn_stop_query = QPushButton()
        self._btn_stop_query.setVisible(False)
        # 积分进度条隐藏控件（保留引用，逻辑中会更新）
        self._quota_value_label = QLabel("--")
        self._quota_packages_label = QLabel("")
        self._quota_badge_label = QLabel("--")
        self._quota_progress = QProgressBar()
        self._quota_progress.setVisible(False)

        # === 使用情况图表区域 ===
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
        self._usage_grid = QGridLayout()
        self._usage_grid.setSpacing(16)

        self._usage_card_credits = StatCard("消耗积分", "--", "💰", "warning")
        self._usage_card_prompt = StatCard("输入", "--", "⬆️", "accent")
        self._usage_card_completion = StatCard("输出", "--", "⬇️", "success")
        self._usage_card_total = StatCard("总Token", "--", "🔢", "accent")
        self._usage_card_count = StatCard("请求数量", "--", "📈", "accent")

        self._usage_grid.addWidget(self._usage_card_credits, 0, 0)
        self._usage_grid.addWidget(self._usage_card_prompt, 0, 1)
        self._usage_grid.addWidget(self._usage_card_completion, 0, 2)
        self._usage_grid.addWidget(self._usage_card_total, 0, 3)
        self._usage_grid.addWidget(self._usage_card_count, 0, 4)

        content_layout.addLayout(self._usage_grid)
        self._all_usage_cards = [
            self._usage_card_credits, self._usage_card_prompt, self._usage_card_completion,
            self._usage_card_total, self._usage_card_count,
        ]

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

        # === 消耗明细 ===
        usage_card = QFrame()
        usage_card.setObjectName("card")
        usage_layout = QVBoxLayout(usage_card)
        usage_layout.setSpacing(8)

        usage_header = QHBoxLayout()
        usage_icon = QLabel("📊")
        usage_icon.setStyleSheet("font-size: 18px;")
        usage_header.addWidget(usage_icon)

        usage_title = QLabel("消耗明细")
        usage_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        usage_header.addWidget(usage_title)
        usage_header.addStretch()
        usage_layout.addLayout(usage_header)

        usage_subtitle = QLabel("每次调用的模型与 Token 消耗")
        usage_subtitle.setStyleSheet("color: #9BA4B0; font-size: 12px;")
        usage_layout.addWidget(usage_subtitle)

        self._usage_table = QTableWidget()
        self._usage_table.setColumnCount(6)
        self._usage_table.setHorizontalHeaderLabels([
            "时间", "模型", "请求Token", "响应Token", "总Token", "扣除积分"
        ])
        usage_header_obj = self._usage_table.horizontalHeader()
        usage_header_obj.setSectionResizeMode(QHeaderView.Stretch)
        self._usage_table.setAlternatingRowColors(True)
        self._usage_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._usage_table.setSelectionBehavior(QTableWidget.SelectRows)
        # 至少展示10行（表头 + 10行数据）
        self._usage_table.setMinimumHeight(10 * 30 + 30)
        usage_layout.addWidget(self._usage_table)

        # 消耗明细翻页栏
        pager_row = QHBoxLayout()
        self._btn_prev = QPushButton("◀ 上一页")
        self._btn_prev.setObjectName("secondary_btn")
        self._btn_prev.clicked.connect(self._prev_page)
        pager_row.addWidget(self._btn_prev)

        self._page_label = QLabel("0 / 0")
        self._page_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        self._page_label.setAlignment(Qt.AlignCenter)
        pager_row.addWidget(self._page_label)

        self._btn_next = QPushButton("下一页 ▶")
        self._btn_next.setObjectName("secondary_btn")
        self._btn_next.clicked.connect(self._next_page)
        pager_row.addWidget(self._btn_next)

        pager_row.addStretch()

        pager_row.addWidget(QLabel("跳到:"))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, 1)
        self._page_spin.setFixedWidth(70)
        self._page_spin.valueChanged.connect(self._goto_page)
        pager_row.addWidget(self._page_spin)

        usage_layout.addLayout(pager_row)

        content_layout.addWidget(usage_card)

        # 进度条和日志（隐藏控件，保留引用避免报错）
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._log_edit = QTextEdit()
        self._log_edit.setVisible(False)

        # 用滚动区域包裹内容，确保表格不被压缩
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _load_accounts(self):
        self._accounts = load_accounts()

    def _apply_filter(self):
        filtered = self._accounts

        self._filtered_accounts = filtered
        self._apply_sort()

    def _account_sort_value(self, account: Account, column: int):
        if column == 0:
            return account.quota.credits_remaining
        if column == 1:
            return account.auth_token.lower()
        if column == 2:
            return (
                0 if account.status == AccountStatus.ACTIVE else 1,
                0 if account.api_key else 1,
                account.status.value,
            )
        return ""

    def _apply_sort(self):
        if self._sort_column is None:
            return
        reverse = self._sort_order == Qt.DescendingOrder
        self._filtered_accounts.sort(
            key=lambda account: self._account_sort_value(account, self._sort_column),
            reverse=reverse,
        )

    # === 使用情况图表相关方法 ===

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

    def _apply_cache_frame_style(self):
        """缓存命中率图表区域样式"""
        c = self._colors
        self._cache_frame.setStyleSheet(
            f"QFrame {{ background-color: {c['bg_secondary']}; "
            f"border: 1px solid {c['border']}; border-radius: 8px; }}"
        )

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
        from ...modules.proxy_server import ProxyDatabase
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

    # === 消耗明细分页逻辑 ===

    @property
    def _total_pages(self) -> int:
        return max(1, (len(self._usage_logs) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _update_pager(self):
        total = self._total_pages
        self._page_label.setText(f"{self._current_page + 1} / {total}")
        self._btn_prev.setEnabled(self._current_page > 0)
        self._btn_next.setEnabled(self._current_page < total - 1)
        self._page_spin.setRange(1, total)
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(self._current_page + 1)
        self._page_spin.blockSignals(False)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_usage_page()

    def _next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._render_usage_page()

    def _goto_page(self, page: int):
        if page >= 1 and page <= self._total_pages:
            self._current_page = page - 1
            self._render_usage_page()

    def _render_usage_page(self):
        """渲染当前页的消耗明细"""
        start = self._current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_logs = self._usage_logs[start:end]

        self._usage_table.setRowCount(len(page_logs))
        for row, log in enumerate(reversed(page_logs)):
            ts = log.get("timestamp", 0)
            ts_text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
            self._usage_table.setItem(row, 0, QTableWidgetItem(ts_text))
            self._usage_table.setItem(row, 1, QTableWidgetItem(log.get("model", "-")))
            self._usage_table.setItem(row, 2, QTableWidgetItem(str(log.get("prompt_tokens", 0))))
            self._usage_table.setItem(row, 3, QTableWidgetItem(str(log.get("completion_tokens", 0))))
            total_tokens = log.get("prompt_tokens", 0) + log.get("completion_tokens", 0)
            self._usage_table.setItem(row, 4, QTableWidgetItem(str(total_tokens)))
            credits = log.get("credits", 0)
            self._usage_table.setItem(row, 5, QTableWidgetItem(f"{credits:.2f}" if credits else "-"))
        self._update_pager()

    def _on_header_sort(self, section: int):
        if self._sort_column == section:
            self._sort_order = Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self._sort_column = section
            self._sort_order = Qt.AscendingOrder
        self._table.horizontalHeader().setSortIndicator(section, self._sort_order)
        self._apply_sort()
        self._render_page()

    def _render_page(self):
        """渲染全部账号"""
        page_accounts = self._filtered_accounts
        self._table.setRowCount(len(page_accounts))

        for row, account in enumerate(page_accounts):
            # 积分列
            if account.quota.credits_total > 0:
                credits_text = f"{account.quota.credits_remaining:.0f}/{account.quota.credits_total:.0f}"
                credits_item = QTableWidgetItem(credits_text)
                if account.quota.credits_total > 0 and (account.quota.credits_remaining / account.quota.credits_total) < 0.2:
                    credits_item.setForeground(Qt.red)
                elif account.quota.credits_total > 0:
                    credits_item.setForeground(Qt.darkGreen)
            elif account.auth_token:
                credits_item = QTableWidgetItem("未查询")
                credits_item.setForeground(Qt.gray)
            else:
                credits_item = QTableWidgetItem("无Token")
                credits_item.setForeground(Qt.gray)
            self._table.setItem(row, 0, credits_item)

            # TK列 (auth_token 截断显示)
            tk_text = account.auth_token
            if tk_text:
                tk_display = tk_text[:20] + "..." if len(tk_text) > 20 else tk_text
            else:
                tk_display = ""
            tk_item = QTableWidgetItem(tk_display)
            tk_item.setToolTip(tk_text if tk_text else "")
            if not tk_text:
                tk_item.setForeground(Qt.gray)
            self._table.setItem(row, 1, tk_item)

            has_api = bool(account.api_key)
            is_normal = account.status == AccountStatus.ACTIVE
            api_status_text = ("有API" if has_api else "无API") + " · " + ("正常" if is_normal else "异常")
            api_status_item = QTableWidgetItem(api_status_text)
            if is_normal and has_api:
                api_status_item.setForeground(Qt.darkGreen)
            elif not is_normal:
                api_status_item.setForeground(Qt.red)
            else:
                api_status_item.setForeground(Qt.gray)
            if account.status_reason:
                api_status_item.setToolTip(account.status_reason)
            self._table.setItem(row, 2, api_status_item)

        self._update_pager()

    def _refresh_table(self):
        """刷新（加载账号数据 + 使用情况图表 + 消耗明细 + 积分卡片）"""
        self._load_accounts()
        self._filtered_accounts = self._accounts
        self._refresh_usage()
        self._refresh_usage_table()
        self._update_quota_card()

    def _refresh_usage_table(self):
        """刷新消耗明细表格（从 ProxyDatabase 读取最近的 request_logs）"""
        from ...modules.proxy_server import ProxyDatabase
        try:
            db = ProxyDatabase.get_instance()
            logs = db.get_request_logs(limit=1000)
        except Exception:
            logs = []

        # 过滤掉输入和输出都为 0 的记录
        self._usage_logs = [l for l in logs if l.get("prompt_tokens", 0) > 0 or l.get("completion_tokens", 0) > 0]
        self._current_page = 0
        self._render_usage_page()

    def _on_filter_changed(self):
        """筛选变化时重新渲染"""
        self._apply_filter()
        self._render_page()

    # === 双击/右键操作 ===

    def _on_table_double_click(self, index):
        """双击行查看积分明细"""
        page_accounts = self._filtered_accounts
        row = index.row()
        if row >= len(page_accounts):
            return
        account = page_accounts[row]
        self._show_credits_detail(account)

    def _get_selected_accounts(self) -> list[Account]:
        """获取当前选中的账号列表"""
        page_accounts = self._filtered_accounts
        selected_rows = set()
        for item in self._table.selectedItems():
            selected_rows.add(item.row())
        accounts = []
        for row in sorted(selected_rows):
            if row < len(page_accounts):
                accounts.append(page_accounts[row])
        return accounts

    def _on_selection_changed(self):
        pass

    def _update_quota_card(self):
        """更新积分包余额（从本地缓存读取，不请求后端）"""
        try:
            from ...modules.proxy_server import ProxyDatabase
            db = ProxyDatabase.get_instance()
            cached = db.get_cached_credits()
            if cached and "credits" in cached:
                self._on_credits_done(cached)
            else:
                self._quota_value_label.setText("--")
                self._quota_packages_label.setText("暂无数据")
                self._quota_badge_label.setText("--")
                self._quota_progress.setValue(0)
        except Exception:
            pass

    def _on_credits_done(self, result: dict):
        """积分查询完成"""
        if result and "credits" in result:
            credits = result.get("credits", 0)
            total_recharged = result.get("totalRecharged", 0)
            total_used = result.get("totalUsed", 0)
            today_used = result.get("todayUsed", 0)

            self._quota_value_label.setText(f"{credits:.2f}")
            self._quota_packages_label.setText(
                f"累计充值 {total_recharged:.0f} · 已用 {total_used:.0f} · 今日 {today_used:.0f}"
            )
            self._quota_badge_label.setText(f"剩余 {credits:.0f}")

            if total_recharged > 0:
                percent = int(min(100, max(0, (credits / total_recharged) * 100)))
                self._quota_progress.setValue(percent)
            else:
                self._quota_progress.setValue(0)
        else:
            err = result.get("error", "查询失败") if result else "无响应"
            self._quota_value_label.setText("--")
            self._quota_packages_label.setText(f"查询失败: {err[:30]}")
            self._quota_badge_label.setText("错误")
            self._quota_progress.setValue(0)

    def _show_context_menu(self, pos):
        """右键菜单"""
        selected = self._get_selected_accounts()
        if not selected:
            return

        menu = QMenu(self)

        if len(selected) == 1:
            account = selected[0]
            action_detail = menu.addAction("📊 查看积分明细")
            action_detail.triggered.connect(lambda: self._show_credits_detail(account))
            menu.addSeparator()
            action_query = menu.addAction("💎 查询积分")
            action_query.triggered.connect(lambda: self._query_single_quota(account))
            menu.addSeparator()
            action_copy_api = menu.addAction("📋 复制 API Key")
            action_copy_api.triggered.connect(lambda: self._copy_field(account.api_key, "API Key"))
            menu.addSeparator()
            action_export = menu.addAction("批量导出")
            action_export.triggered.connect(lambda: self._export_selected_accounts())
            menu.addSeparator()
            action_del = menu.addAction("🗑️ 删除账号")
            action_del.triggered.connect(lambda: self._delete_account(account))
        else:
            action_export = menu.addAction(f"批量导出 ({len(selected)} 个账号)")
            action_export.triggered.connect(lambda: self._export_selected_accounts())
            menu.addSeparator()
            action_batch = menu.addAction(f"🗑️ 批量删除 ({len(selected)} 个账号)")
            action_batch.triggered.connect(lambda: self._batch_delete())

        menu.exec(QCursor.pos())

    def _show_credits_detail(self, account: Account):
        """显示积分明细弹窗"""
        if not account.quota.packages and account.auth_token:
            self._query_and_show_detail(account)
            return

        dialog = CreditsDetailDialog(account, self)
        dialog.exec()

    def _query_and_show_detail(self, account: Account):
        """查询积分后显示明细弹窗"""
        if not account.auth_token:
            QMessageBox.warning(self, "提示", "该账号无 Token，无法查询积分明细")
            return

        from PySide6.QtCore import QThread, Signal as QSignal

        class DetailQueryThread(QThread):
            result_ready = QSignal(object, object)

            def __init__(self, acc, proxy=None):
                super().__init__()
                self._acc = acc
                self._proxy = proxy

            def run(self):
                client = ApiClient.from_account(self._acc, proxy=self._proxy)
                result = client.get_user_resource()
                self.result_ready.emit(self._acc, result)

        from ...utils.proxy import get_proxy_from_settings
        try:
            _proxy = get_proxy_from_settings()
        except Exception:
            _proxy = None
        thread = DetailQueryThread(account, proxy=_proxy)
        thread.result_ready.connect(self._on_detail_query_result)
        thread.start()
        self._detail_thread = thread

    def _on_detail_query_result(self, account: Account, result: dict):
        if result.get("success"):
            packages = result.get("packages", [])
            remaining = result.get("remaining_credits", 0)
            total = result.get("total_credits", 0)

            account.quota.credits_remaining = remaining
            account.quota.credits_total = total
            account.quota.packages = packages
            account.quota.last_updated = datetime.now()
            save_account(account)

            # 联动更新上游 Key 池
            try:
                from ...modules.proxy_server import ProxyDatabase
                db = ProxyDatabase.get_instance()
                db.sync_quota_to_key(
                    api_key_or_token=getattr(account, "api_key", None) or account.auth_token,
                    remaining_credits=remaining,
                    total_credits=total,
                    packages=packages,
                )
            except Exception:
                pass

            self.quota_updated.emit()  # 通知其他页面刷新

            dialog = CreditsDetailDialog(account, self)
            dialog.exec()
            self._render_page()
        else:
            QMessageBox.warning(self, "查询失败", "无法获取积分明细，请检查 Token 是否有效")

    def _query_single_quota(self, account: Account):
        """查询单个账号的积分（右键触发）"""
        if not account.auth_token:
            QMessageBox.warning(self, "提示", "该账号无 Token，无法查询积分")
            return

        from PySide6.QtCore import QThread, Signal as QSignal

        class QuotaThread(QThread):
            result_ready = QSignal(object, object)  # (account, result_dict)

            def __init__(self, acc, proxy=None):
                super().__init__()
                self._acc = acc
                self._proxy = proxy

            def run(self):
                client = ApiClient.from_account(self._acc, proxy=self._proxy)
                result = client.get_user_resource()
                self.result_ready.emit(self._acc, result)

        from ...utils.proxy import get_proxy_from_settings
        try:
            _proxy = get_proxy_from_settings()
        except Exception:
            _proxy = None
        thread = QuotaThread(account, proxy=_proxy)
        thread.result_ready.connect(self._on_single_quota_result)
        thread.start()
        self._quota_thread = thread

    def _on_single_quota_result(self, account: Account, result: dict):
        """单号积分查询结果"""
        if result.get("success"):
            packages = result.get("packages", [])
            remaining = result.get("remaining_credits", 0)
            total = result.get("total_credits", 0)

            # 通过 UID 匹配更新
            for acc in self._accounts:
                if acc.uid == account.uid:
                    acc.quota.credits_remaining = remaining
                    acc.quota.credits_total = total
                    acc.quota.packages = packages
                    acc.quota.last_updated = datetime.now()
                    save_account(acc)
                    # 联动更新上游 Key 池
                    try:
                        from ...modules.proxy_server import ProxyDatabase
                        db = ProxyDatabase.get_instance()
                        db.sync_quota_to_key(
                            api_key_or_token=getattr(acc, "api_key", None) or acc.auth_token,
                            remaining_credits=remaining,
                            total_credits=total,
                            packages=packages,
                        )
                    except Exception:
                        pass
                    self.quota_updated.emit()  # 通知其他页面刷新
                    break

            self._apply_filter()
            self._render_page()
        else:
            QMessageBox.warning(self, "查询失败", "无法获取积分，请检查 Token 是否有效")

    def _query_all_quotas(self):
        """批量查询所有账号积分 — 并发执行"""
        self._load_accounts()
        accounts_with_token = [a for a in self._accounts if a.auth_token]
        if not accounts_with_token:
            return

        max_workers = 5

        self._btn_query_all.setVisible(False)
        self._btn_stop_query.setVisible(True)

        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, len(accounts_with_token))
        self._progress_bar.setValue(0)

        self._log_edit.clear()
        self._log_edit.setVisible(True)
        from ...utils.proxy import describe_proxy_status
        self._append_log(f"🌐 {describe_proxy_status()}")
        self._append_log(f"🚀 开始查询 {len(accounts_with_token)} 个账号积分，并发数: {max_workers}")

        from PySide6.QtCore import QThread, Signal as QSignal
        from concurrent.futures import ThreadPoolExecutor, as_completed

        class BatchQuotaWorker(QThread):
            progress = QSignal(str, bool, str)  # uid, success, status_text
            finished_all = Signal()

            def __init__(self, accs, max_workers=5, proxy=None):
                super().__init__()
                self._accounts = accs
                self.max_workers = max_workers
                self._proxy = proxy
                self._stop_flag = False

            def stop(self):
                self._stop_flag = True

            def _query_one(self, acc):
                # 每次查询前重新获取代理 IP（API 模式：每账号一个新 IP）
                from ...utils.proxy import get_proxy_with_info
                _current_proxy, _proxy_info = get_proxy_with_info()

                uid_short = acc.uid[:10] if acc.uid else "?"
                proxy_tag = f"代理[{_proxy_info}]" if _proxy_info else "直连"
                logger.info(f"📡 {uid_short} 使用{proxy_tag}查询积分")

                try:
                    client = ApiClient.from_account(acc, proxy=_current_proxy)
                    result = client.get_user_resource()
                    result["uid"] = acc.uid
                    result["_proxy_info"] = _proxy_info
                    return (acc.uid, result)
                except Exception as e:
                    return (acc.uid, {"success": False, "uid": acc.uid, "error": str(e), "_proxy_info": _proxy_info})

            def run(self):
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(self._query_one, acc): acc
                               for acc in self._accounts}
                    for future in as_completed(futures):
                        if self._stop_flag:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        try:
                            uid, result = future.result()
                            proxy_info = result.get("_proxy_info", "")
                            status = "✅ 成功" if result.get("success") else f"❌ 失败: {result.get('error', '未知错误')}"
                            if proxy_info:
                                status = f"代理[{proxy_info}] {status}"
                            self.progress.emit(uid, result.get("success", False), status)
                            # 更新数据
                            if result.get("success"):
                                for acc in self._accounts:
                                    if acc.uid == uid:
                                        remaining = result.get("remaining_credits", 0)
                                        total = result.get("total_credits", 0)
                                        acc.quota.credits_remaining = remaining
                                        acc.quota.credits_total = total
                                        acc.quota.packages = result.get("packages", [])
                                        acc.quota.last_updated = datetime.now()
                                        save_account(acc)
                                        # 联动更新上游 Key 池
                                        try:
                                            from ...modules.proxy_server import ProxyDatabase
                                            db = ProxyDatabase.get_instance()
                                            db.sync_quota_to_key(
                                                api_key_or_token=getattr(acc, "api_key", None) or acc.auth_token,
                                                remaining_credits=remaining,
                                                total_credits=total,
                                                packages=result.get("packages", []),
                                            )
                                        except Exception:
                                            pass
                                        break
                        except Exception:
                            pass
                self.finished_all.emit()

        from ...utils.proxy import get_proxy_from_settings, ProxyConfigError
        # 预检代理配置是否可用（不缓存 IP，每账号单独提取）
        try:
            get_proxy_from_settings()
        except ProxyConfigError as e:
            QMessageBox.warning(self, "代理配置错误", str(e))
            return

        self._batch_worker = BatchQuotaWorker(accounts_with_token, max_workers=max_workers, proxy=None)
        self._batch_worker.progress.connect(self._on_batch_quota_progress)
        self._batch_worker.finished_all.connect(self._on_batch_quota_done)
        self._batch_worker.start()

    def _stop_query(self):
        """停止查询/检测"""
        if hasattr(self, '_batch_worker') and self._batch_worker:
            self._batch_worker.stop()
            self._append_log("⏹ 正在停止查询...")
        if hasattr(self, '_status_check_worker') and self._status_check_worker:
            self._status_check_worker.stop()
            self._append_log("⏹ 正在停止检测...")
        self._btn_stop_query.setEnabled(False)

    def _append_log(self, text: str):
        """追加日志并自动滚到底部"""
        self._log_edit.append(text)
        scrollbar = self._log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_batch_quota_progress(self, uid: str, success: bool, status_text: str = ""):
        """批量查询进度"""
        current = self._progress_bar.value() + 1
        self._progress_bar.setValue(current)
        icon = "✅" if success else "❌"
        text = status_text if status_text else ("成功" if success else "失败")
        self._append_log(f"{icon} {uid[:10]}... {text}")

    def _on_batch_quota_done(self):
        """批量查询完成"""
        self._progress_bar.setVisible(False)
        self._btn_query_all.setVisible(True)
        self._btn_stop_query.setVisible(False)
        self._btn_stop_query.setEnabled(True)
        self._append_log("📊 查询完成！")
        self._apply_filter()
        self._render_page()
        self.quota_updated.emit()  # 通知其他页面刷新

    def _check_all_status(self):
        """检查所有账号的 API Key 状态（风控/失效），同步到上游 Key 池"""
        from PySide6.QtCore import QThread, Signal as QSignal
        from concurrent.futures import ThreadPoolExecutor, as_completed

        self._load_accounts()
        accounts_with_key = [a for a in self._accounts if a.api_key]
        if not accounts_with_key:
            QMessageBox.information(self, "提示", "没有配置 API Key 的账号，无需检测")
            return

        max_workers = 5
        self._btn_check_status.setEnabled(False)
        self._btn_query_all.setEnabled(False)
        self._btn_stop_query.setVisible(True)
        self._btn_stop_query.setEnabled(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, len(accounts_with_key))
        self._progress_bar.setValue(0)
        self._log_edit.clear()
        self._log_edit.setVisible(True)
        from ...utils.proxy import describe_proxy_status
        self._append_log(f"🌐 {describe_proxy_status()}")
        self._append_log(f"🔍 开始检测 {len(accounts_with_key)} 个账号状态，并发数: {max_workers}")

        class StatusCheckWorker(QThread):
            """后台并发检测 API Key 风控状态线程"""
            progress = QSignal(str, bool, str)  # nickname, success, status_text
            done = QSignal(int, int, int, list, list)  # (正常, 异常, 失败, 异常key列表, 限流key列表)

            def __init__(self, accounts, max_workers=5, proxy=None):
                super().__init__()
                self._accounts = accounts
                self.max_workers = max_workers
                self._proxy = proxy
                self._stop_flag = False

            def stop(self):
                self._stop_flag = True

            def _check_one(self, acc):
                api_key = acc.api_key
                nickname = acc.nickname or acc.uid
                # 每次检测前重新获取代理 IP（一号一IP）
                from ...utils.proxy import get_proxy_with_info
                _current_proxy, _proxy_info = get_proxy_with_info()
                uid_short = (acc.uid or "?")[:10]
                proxy_tag = f"代理[{_proxy_info}]" if _proxy_info else "直连"
                logger.info(f"📡 {uid_short} 使用{proxy_tag}检测状态")
                try:
                    result = check_api_key_chat_status(api_key, attempts=3, proxy=_current_proxy)
                    status_text = result.get("status_text", "check_failed")
                    if _proxy_info:
                        status_text = f"代理[{_proxy_info}] {status_text}"
                    return (
                        nickname,
                        result.get("success", False),
                        status_text,
                        api_key,
                        result.get("flag"),
                    )
                except Exception as e:
                    return (nickname, False, f"异常: {e}", api_key, None)

            def run(self):
                normal = 0
                abnormal = 0
                failed = 0
                abnormal_keys = []
                rate_limited_keys = []
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(self._check_one, acc): acc
                               for acc in self._accounts}
                    for future in as_completed(futures):
                        if self._stop_flag:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        try:
                            nickname, success, status_text, api_key, flag = future.result()
                            self.progress.emit(nickname, success, status_text)
                            if flag == "abnormal":
                                abnormal += 1
                                abnormal_keys.append(api_key)
                            elif flag == "rate_limited":
                                abnormal += 1
                                rate_limited_keys.append(api_key)
                            elif success:
                                normal += 1
                            else:
                                failed += 1
                        except Exception:
                            failed += 1
                self.done.emit(normal, abnormal, failed, abnormal_keys, rate_limited_keys)

        from ...utils.proxy import get_proxy_from_settings, ProxyConfigError
        # 预检代理配置是否可用（不缓存 IP，每账号单独提取）
        try:
            get_proxy_from_settings()
        except ProxyConfigError as e:
            QMessageBox.warning(self, "代理配置错误", str(e))
            return

        worker = StatusCheckWorker(accounts_with_key, max_workers=max_workers, proxy=None)

        def _on_progress(nickname, success, status_text):
            current = self._progress_bar.value() + 1
            self._progress_bar.setValue(current)
            icon = "✅" if success else ("⚠️" if status_text in ("风控异常", "限流(401)") else "❌")
            self._append_log(f"{icon} {nickname} → {status_text}")

        def _on_done(normal, abnormal, failed, abnormal_keys, rate_limited_keys):
            self._btn_check_status.setEnabled(True)
            self._btn_query_all.setEnabled(True)
            self._btn_stop_query.setVisible(False)
            self._btn_stop_query.setEnabled(True)
            self._progress_bar.setVisible(False)

            # 同步到上游 Key 池
            try:
                from ...modules.proxy_server import ProxyDatabase
                proxy_db = ProxyDatabase.get_instance()
                all_keys = proxy_db.get_upstream_keys()
                for k in all_keys:
                    k_api = k.get("api_key", "")
                    k_id = k.get("key_id", "")
                    k_status = k.get("status", "")
                    # permanent_disabled（永久禁用）的 Key 不被检测覆盖，永不自动恢复
                    if k_status == "permanent_disabled":
                        continue
                    if k_api in abnormal_keys and k_status != "abnormal":
                        proxy_db.update_upstream_key(k_id, {"status": "abnormal"})
                    elif k_api in rate_limited_keys and k_status != "rate_limited":
                        proxy_db.update_upstream_key(k_id, {"status": "rate_limited"})
                    elif (k_api not in abnormal_keys
                          and k_api not in rate_limited_keys
                          and k_status in ("abnormal", "rate_limited")):
                        # 之前异常/限流，本次检测通过 → 恢复 active
                        proxy_db.update_upstream_key(k_id, {"status": "active"})
                proxy_db._dirty = True
                proxy_db._flush_to_disk()
                self._append_log("✅ 上游 Key 池已同步")
            except Exception as e:
                self._append_log(f"⚠️ 同步上游池失败: {e}")

            # 同步到账号表（让"API状态"列实时更新）
            try:
                from ...models import AccountStatus
                changed = 0
                for acc in self._accounts:
                    if not acc.api_key:
                        continue
                    # 用户手动设置的 INACTIVE/EXPIRED/QUOTA_EXHAUSTED 不被检测覆盖
                    if acc.status in (AccountStatus.INACTIVE, AccountStatus.EXPIRED,
                                      AccountStatus.QUOTA_EXHAUSTED):
                        continue
                    if acc.api_key in abnormal_keys:
                        if acc.status != AccountStatus.ERROR or "风控" not in acc.status_reason:
                            acc.status = AccountStatus.ERROR
                            acc.status_reason = "风控异常"
                            save_account(acc)
                            changed += 1
                    elif acc.api_key in rate_limited_keys:
                        if acc.status != AccountStatus.ERROR or "限流" not in acc.status_reason:
                            acc.status = AccountStatus.ERROR
                            acc.status_reason = "限流(401)"
                            save_account(acc)
                            changed += 1
                    else:
                        # 本次检测通过，且账号是 ERROR 状态（之前被检测标过）→ 恢复 ACTIVE
                        if acc.status == AccountStatus.ERROR:
                            acc.status = AccountStatus.ACTIVE
                            acc.status_reason = ""
                            save_account(acc)
                            changed += 1
                if changed:
                    self._append_log(f"✅ 账号表已同步（{changed} 个状态变更）")
                    self._refresh_table()
            except Exception as e:
                self._append_log(f"⚠️ 同步账号表失败: {e}")

            rate_limited_count = len(rate_limited_keys)
            msg = f"检测完成：✅ 正常 {normal} 个"
            if abnormal > 0:
                msg += f"，⚠️ 异常 {abnormal} 个（已标记到上游池）"
            if rate_limited_count > 0:
                msg += f"，⚠️ 限流 {rate_limited_count} 个（已标记限流）"
            if failed > 0:
                msg += f"，❓ 失败 {failed} 个"
            self._append_log(msg)
            QMessageBox.information(self, "检测完成", msg)

        worker.progress.connect(_on_progress)
        worker.done.connect(_on_done)
        self._status_check_worker = worker
        worker.start()

    def _copy_field(self, value: str, label: str):
        """复制指定字段到剪贴板"""
        if not value:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(value)

    def _export_selected_accounts(self):
        selected = self._get_selected_accounts()
        rows = [
            f"{account.display_name}----{account.api_key}"
            for account in selected
            if account.api_key
        ]
        if not selected:
            return
        if not rows:
            QMessageBox.warning(self, t("common.warning"), "选中的账号没有可导出的 API Key")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出账号 API Key",
            "accounts_api_keys.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(rows))
            QMessageBox.information(self, "导出完成", f"已导出 {len(rows)} 个 API Key")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"无法写入文件：{e}")

    def _sync_delete_key_pool(self, account: Account):
        """删除账号时同步删除 Key 池中对应的 Key"""
        try:
            from ...modules.proxy_server import ProxyDatabase
            proxy_db = ProxyDatabase.get_instance()
            keys = proxy_db.get_upstream_keys()
            # 用 api_key 或 auth_token 匹配
            tokens_to_remove = set()
            if account.api_key:
                tokens_to_remove.add(account.api_key)
            if account.auth_token:
                tokens_to_remove.add(account.auth_token)
            for k in keys:
                if k.get("api_key", "") in tokens_to_remove:
                    proxy_db.delete_upstream_key(k["key_id"])
        except Exception:
            pass  # Key池删除失败不影响账号删除

    def _delete_account(self, account: Account):
        reply = QMessageBox.question(
            self, t("common.confirm"),
            f"确定要删除账号 {account.display_name} 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # 同步删除 Key 池中对应的 Key
            self._sync_delete_key_pool(account)
            delete_account(account.uid)
            self._refresh_table()

    def _batch_delete(self):
        selected = self._get_selected_accounts()
        if not selected:
            return

        names = [a.display_name for a in selected]
        if len(names) <= 10:
            name_list = "\n".join(f"  • {n}" for n in names)
        else:
            name_list = "\n".join(f"  • {n}" for n in names[:10])
            name_list += f"\n  ... 还有 {len(names) - 10} 个账号"

        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除以下 {len(selected)} 个账号吗？\n\n{name_list}\n\n"
            f"此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for account in selected:
                self._sync_delete_key_pool(account)
                delete_account(account.uid)
            self._refresh_table()

    def _add_account(self):
        """添加单个账号"""
        dialog = AddAccountDialog(self)
        dialog.account_added.connect(self._on_account_added)
        dialog.exec()

    def _on_account_added(self, account: Account):
        """添加账号后刷新表格"""
        self._refresh_table()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_table()
