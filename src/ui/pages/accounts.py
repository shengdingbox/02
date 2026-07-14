"""账号管理页面"""

import secrets
import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLineEdit,
    QDialog, QTextEdit, QFileDialog, QMessageBox,
    QMenu, QAbstractItemView, QSpinBox, QProgressBar
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor

from ...i18n import t
from ...models import Account, Platform, AccountStatus, ResourcePackage
from ...utils.store import load_accounts, save_account, delete_account, save_setting, load_setting
from ...modules.api_client import ApiClient, check_api_key_chat_status

logger = logging.getLogger(__name__)

PAGE_SIZE = 100  # 每页显示条数


class AddAccountDialog(QDialog):
    """添加账号对话框 — 卡密导入（单行）

    只保留一个 apikey 输入框，昵称自动随机生成。
    点击「导入」后自动保存账号、同步上游 Key 池、查询积分。
    """

    account_added = Signal(Account)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("accounts.add_account"))
        self.setMinimumWidth(460)
        self._query_thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 说明
        hint = QLabel("输入 API Key (ck_xxx) 导入，昵称自动生成")
        hint.setStyleSheet("color: #718096; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # API Key 输入框（单行）
        self._input = QLineEdit()
        self._input.setPlaceholderText("ck_xxx")
        self._input.setMinimumHeight(36)
        self._input.returnPressed.connect(self._do_import)
        layout.addWidget(self._input)

        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #9BA4B0; font-size: 12px;")
        layout.addWidget(self._status_label)

        # 按钮行
        btn_row = QHBoxLayout()

        self._btn_import = QPushButton("🚀 导入")
        self._btn_import.setObjectName("primary_btn")
        self._btn_import.setCursor(Qt.PointingHandCursor)
        self._btn_import.setMinimumHeight(36)
        self._btn_import.clicked.connect(self._do_import)
        btn_row.addWidget(self._btn_import)

        btn_cancel = QPushButton(t("common.cancel"))
        btn_cancel.setObjectName("secondary_btn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_row.addStretch()

        layout.addLayout(btn_row)

    def _do_import(self):
        """解析 API Key 并导入"""
        api_key = self._input.text().strip()
        if not api_key:
            QMessageBox.warning(self, t("common.warning"), "请输入 API Key")
            return

        # 随机生成昵称
        nickname = f"账号_{secrets.token_hex(4)}"

        # 1. 保存账号到数据库
        account = Account(
            uid=nickname,
            nickname=nickname,
            platform=Platform.CODEBUDDY,
            auth_token=api_key,
            domain="www.codebuddy.cn",
            ck="",
            api_key=api_key,
        )
        save_account(account)

        # 2. 同步上游 Key 池
        key_pool_added = False
        try:
            from ...modules.proxy_server import ProxyDatabase
            proxy_db = ProxyDatabase.get_instance()
            existing_api_keys = {k.get("api_key", "") for k in proxy_db.get_upstream_keys()}
            if api_key not in existing_api_keys:
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
                key_pool_added = True
        except Exception:
            pass

        # 3. 通知刷新
        self.account_added.emit(account)

        # 4. 查询积分
        self._btn_import.setEnabled(False)
        self._status_label.setText("⏳ 正在查询积分...")
        self._status_label.setStyleSheet("color: #D69E2E; font-size: 12px;")

        from PySide6.QtCore import QThread, Signal as QSignal

        class QuotaQueryThread(QThread):
            done = QSignal(object, object)  # (account, result_dict)

            def __init__(self, acc):
                super().__init__()
                self._acc = acc

            def run(self):
                try:
                    client = ApiClient.from_api_key(self._acc.api_key)
                    result = client.get_user_resource()
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                self.done.emit(self._acc, result)

        self._query_thread = QuotaQueryThread(account)
        self._query_thread.done.connect(
            lambda acc, result: self._on_quota_done(acc, result, key_pool_added)
        )
        self._query_thread.start()

    def _on_quota_done(self, account: Account, result: dict, key_pool_added: bool):
        """积分查询完成"""
        self._btn_import.setEnabled(True)

        if result.get("success"):
            remaining = result.get("remaining_credits", 0)
            total = result.get("total_credits", 0)
            packages = result.get("packages", [])

            account.quota.credits_remaining = remaining
            account.quota.credits_total = total
            account.quota.packages = packages
            account.quota.last_updated = datetime.now()
            save_account(account)

            # 同步上游 Key 池积分
            try:
                from ...modules.proxy_server import ProxyDatabase
                db = ProxyDatabase.get_instance()
                db.sync_quota_to_key(
                    api_key_or_token=account.api_key or account.auth_token,
                    remaining_credits=remaining,
                    total_credits=total,
                    packages=packages,
                )
            except Exception:
                pass

            msg = f"✅ 已导入: {account.nickname}"
            if key_pool_added:
                msg += "\n🔑 已同步到上游 Key 池"
            msg += f"\n💎 积分: {remaining:.0f}/{total:.0f}"
            self._status_label.setText(msg)
            self._status_label.setStyleSheet("color: #38A169; font-size: 12px;")
        else:
            msg = f"✅ 已导入: {account.nickname}"
            if key_pool_added:
                msg += "\n🔑 已同步到上游 Key 池"
            msg += f"\n⚠️ 积分查询失败: {result.get('error', '未知')}"
            self._status_label.setText(msg)
            self._status_label.setStyleSheet("color: #D69E2E; font-size: 12px;")

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
        self._current_page = 0
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel(t("accounts.title"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("管理所有平台的账号 · 双击行查看积分明细 · 右键更多操作")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        # 工具栏
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(16)

        toolbar = QHBoxLayout()

        toolbar.addStretch()

        # 批量删除按钮
        self._btn_batch_del = QPushButton("🗑️ 批量删除")
        self._btn_batch_del.setObjectName("danger_btn")
        self._btn_batch_del.setCursor(Qt.PointingHandCursor)
        self._btn_batch_del.clicked.connect(self._batch_delete)
        self._btn_batch_del.setVisible(False)
        toolbar.addWidget(self._btn_batch_del)

        self._btn_batch_export = QPushButton("批量导出")
        self._btn_batch_export.setObjectName("secondary_btn")
        self._btn_batch_export.setCursor(Qt.PointingHandCursor)
        self._btn_batch_export.clicked.connect(self._export_selected_accounts)
        self._btn_batch_export.setVisible(False)
        toolbar.addWidget(self._btn_batch_export)

        # 操作按钮
        btn_add = QPushButton(f"➕ {t('accounts.add_account')}")
        btn_add.setObjectName("primary_btn")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._add_account)
        toolbar.addWidget(btn_add)

        # 查询全部积分按钮
        self._btn_query_all = QPushButton("💎 查询全部积分")
        self._btn_query_all.setObjectName("primary_btn")
        self._btn_query_all.setCursor(Qt.PointingHandCursor)
        self._btn_query_all.clicked.connect(self._query_all_quotas)
        toolbar.addWidget(self._btn_query_all)

        # 检查账号状态按钮（保留引用但不显示）
        self._btn_check_status = QPushButton("🔍 检查账号状态")
        self._btn_check_status.setObjectName("secondary_btn")
        self._btn_check_status.setVisible(False)

        # 停止按钮
        self._btn_stop_query = QPushButton("⏹ 停止")
        self._btn_stop_query.setObjectName("secondary_btn")
        self._btn_stop_query.setStyleSheet(
            "QPushButton { color: #FC8181; border: 1px solid #FC8181; }"
            "QPushButton:hover { background-color: rgba(229,62,62,0.1); }"
        )
        self._btn_stop_query.setCursor(Qt.PointingHandCursor)
        self._btn_stop_query.setVisible(False)
        self._btn_stop_query.clicked.connect(self._stop_query)
        toolbar.addWidget(self._btn_stop_query)

        content_layout.addLayout(toolbar)

        # 表格 – 列：昵称、UID、积分、TK、API状态
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "昵称", "UID", "积分", "TK", "API状态"
        ])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_sort)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_table_double_click)
        content_layout.addWidget(self._table, 1)

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
        self._usage_table.setColumnCount(5)
        self._usage_table.setHorizontalHeaderLabels([
            "时间", "模型", "请求Token", "响应Token", "总Token"
        ])
        usage_header_obj = self._usage_table.horizontalHeader()
        usage_header_obj.setSectionResizeMode(QHeaderView.Stretch)
        self._usage_table.setAlternatingRowColors(True)
        self._usage_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._usage_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._usage_table.setMaximumHeight(280)
        usage_layout.addWidget(self._usage_table)

        content_layout.addWidget(usage_card)

        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        content_layout.addWidget(self._progress_bar)

        # 查询日志
        self._log_edit = QTextEdit()
        self._log_edit.setObjectName("log_edit")
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumHeight(120)
        self._log_edit.setVisible(False)
        content_layout.addWidget(self._log_edit)

        layout.addWidget(content)

    # === 分页逻辑 ===

    @property
    def _total_pages(self) -> int:
        return max(1, (len(self._filtered_accounts) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _get_page_accounts(self) -> list:
        start = self._current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        return self._filtered_accounts[start:end]

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
            self._render_page()

    def _next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._render_page()

    def _goto_page(self, page: int):
        if page >= 1 and page <= self._total_pages:
            self._current_page = page - 1
            self._render_page()

    # === 数据 & 渲染 ===

    def _load_accounts(self):
        self._accounts = load_accounts()

    def _apply_filter(self):
        filtered = self._accounts

        self._filtered_accounts = filtered
        self._apply_sort()

    def _account_sort_value(self, account: Account, column: int):
        if column == 0:
            return account.display_name.lower()
        if column == 1:
            return account.uid.lower()
        if column == 2:
            return account.quota.credits_remaining
        if column == 3:
            return account.auth_token.lower()
        if column == 4:
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

    def _on_header_sort(self, section: int):
        if self._sort_column == section:
            self._sort_order = Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self._sort_column = section
            self._sort_order = Qt.AscendingOrder
        self._table.horizontalHeader().setSortIndicator(section, self._sort_order)
        self._apply_sort()
        self._current_page = 0
        self._render_page()

    def _render_page(self):
        """只渲染当前页"""
        page_accounts = self._get_page_accounts()
        self._table.setRowCount(len(page_accounts))

        for row, account in enumerate(page_accounts):
            # 昵称
            self._table.setItem(row, 0, QTableWidgetItem(account.display_name))

            # UID
            self._table.setItem(row, 1, QTableWidgetItem(account.uid))

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
            self._table.setItem(row, 2, credits_item)

            # TK列 (auth_token 截断显示)
            tk_text = account.auth_token
            if tk_text:
                tk_display = tk_text[:20] + "..." if len(tk_text) > 20 else tk_text
            else:
                tk_display = ""
            tk_item = QTableWidgetItem(tk_display)
            tk_item.setToolTip(tk_text if tk_text else "")  # 悬停显示完整值
            if not tk_text:
                tk_item.setForeground(Qt.gray)
            self._table.setItem(row, 3, tk_item)

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
            self._table.setItem(row, 4, api_status_item)

        self._update_pager()

    def _refresh_table(self):
        """全量刷新（重新加载+渲染）"""
        self._load_accounts()
        self._apply_filter()
        self._current_page = 0
        self._render_page()
        self._refresh_usage_table()

    def _refresh_usage_table(self):
        """刷新消耗明细表格（从 ProxyDatabase 读取最近的 request_logs）"""
        from ...modules.proxy_server import ProxyDatabase
        try:
            db = ProxyDatabase.get_instance()
            logs = db.get_request_logs(limit=200)
        except Exception:
            logs = []

        # 过滤掉输入和输出都为 0 的记录
        logs = [l for l in logs if l.get("prompt_tokens", 0) > 0 or l.get("completion_tokens", 0) > 0]

        self._usage_table.setRowCount(len(logs))
        for row, log in enumerate(reversed(logs)):
            ts = log.get("timestamp", 0)
            ts_text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
            self._usage_table.setItem(row, 0, QTableWidgetItem(ts_text))
            self._usage_table.setItem(row, 1, QTableWidgetItem(log.get("model", "-")))
            self._usage_table.setItem(row, 2, QTableWidgetItem(str(log.get("prompt_tokens", 0))))
            self._usage_table.setItem(row, 3, QTableWidgetItem(str(log.get("completion_tokens", 0))))
            total_tokens = log.get("prompt_tokens", 0) + log.get("completion_tokens", 0)
            self._usage_table.setItem(row, 4, QTableWidgetItem(str(total_tokens)))

    def _on_filter_changed(self):
        """筛选变化时重置到第一页"""
        self._apply_filter()
        self._current_page = 0
        self._render_page()

    # === 双击/右键操作 ===

    def _on_table_double_click(self, index):
        """双击行查看积分明细"""
        page_accounts = self._get_page_accounts()
        row = index.row()
        if row >= len(page_accounts):
            return
        account = page_accounts[row]
        self._show_credits_detail(account)

    def _get_selected_accounts(self) -> list[Account]:
        """获取当前选中的账号列表"""
        page_accounts = self._get_page_accounts()
        selected_rows = set()
        for item in self._table.selectedItems():
            selected_rows.add(item.row())
        accounts = []
        for row in sorted(selected_rows):
            if row < len(page_accounts):
                accounts.append(page_accounts[row])
        return accounts

    def _on_selection_changed(self):
        selected = self._get_selected_accounts()
        self._btn_batch_export.setVisible(bool(selected))
        if selected:
            self._btn_batch_export.setText(f"批量导出 ({len(selected)})")
        if len(selected) > 1:
            self._btn_batch_del.setVisible(True)
            self._btn_batch_del.setText(f"🗑️ 批量删除 ({len(selected)})")
        else:
            self._btn_batch_del.setVisible(False)

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

            def __init__(self, acc):
                super().__init__()
                self._acc = acc

            def run(self):
                client = ApiClient.from_account(self._acc)
                result = client.get_user_resource()
                self.result_ready.emit(self._acc, result)

        thread = DetailQueryThread(account)
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

            def __init__(self, acc):
                super().__init__()
                self._acc = acc

            def run(self):
                client = ApiClient.from_account(self._acc)
                result = client.get_user_resource()
                self.result_ready.emit(self._acc, result)

        thread = QuotaThread(account)
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
        self._append_log(f"🚀 开始查询 {len(accounts_with_token)} 个账号积分，并发数: {max_workers}")

        from PySide6.QtCore import QThread, Signal as QSignal
        from concurrent.futures import ThreadPoolExecutor, as_completed

        class BatchQuotaWorker(QThread):
            progress = QSignal(str, bool)  # uid, success
            finished_all = Signal()

            def __init__(self, accs, max_workers=5):
                super().__init__()
                self._accounts = accs
                self.max_workers = max_workers
                self._stop_flag = False

            def stop(self):
                self._stop_flag = True

            def _query_one(self, acc):
                try:
                    client = ApiClient.from_account(acc)
                    result = client.get_user_resource()
                    result["uid"] = acc.uid
                    return (acc.uid, result)
                except Exception as e:
                    return (acc.uid, {"success": False, "uid": acc.uid, "error": str(e)})

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
                            self.progress.emit(uid, result.get("success", False))
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

        self._batch_worker = BatchQuotaWorker(accounts_with_token, max_workers=max_workers)
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

    def _on_batch_quota_progress(self, uid: str, success: bool):
        """批量查询进度"""
        current = self._progress_bar.value() + 1
        self._progress_bar.setValue(current)
        icon = "✅" if success else "❌"
        self._append_log(f"{icon} {uid[:12]}... {'成功' if success else '失败'}")

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
        self._append_log(f"🔍 开始检测 {len(accounts_with_key)} 个账号状态，并发数: {max_workers}")

        class StatusCheckWorker(QThread):
            """后台并发检测 API Key 风控状态线程"""
            progress = QSignal(str, bool, str)  # nickname, success, status_text
            done = QSignal(int, int, int, list, list)  # (正常, 异常, 失败, 异常key列表, 限流key列表)

            def __init__(self, accounts, max_workers=5):
                super().__init__()
                self._accounts = accounts
                self.max_workers = max_workers
                self._stop_flag = False

            def stop(self):
                self._stop_flag = True

            def _check_one(self, acc):
                api_key = acc.api_key
                nickname = acc.nickname or acc.uid
                try:
                    result = check_api_key_chat_status(api_key, attempts=3)
                    return (
                        nickname,
                        result.get("success", False),
                        result.get("status_text", "check_failed"),
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

        worker = StatusCheckWorker(accounts_with_key, max_workers=max_workers)

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
                    if k_api in abnormal_keys and k.get("status") != "abnormal":
                        proxy_db.update_upstream_key(k_id, {"status": "abnormal"})
                    elif k_api in rate_limited_keys and k.get("status") != "rate_limited":
                        proxy_db.update_upstream_key(k_id, {"status": "rate_limited"})
                    elif (k_api not in abnormal_keys
                          and k_api not in rate_limited_keys
                          and k.get("status") in ("abnormal", "rate_limited")):
                        # 之前异常/限流，本次检测通过 → 恢复 active
                        proxy_db.update_upstream_key(k_id, {"status": "active"})
                proxy_db._dirty = True
                proxy_db._flush_to_disk()
                self._append_log("✅ 上游 Key 池已同步")
            except Exception as e:
                self._append_log(f"⚠️ 同步上游池失败: {e}")

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
