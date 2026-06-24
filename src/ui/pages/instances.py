"""多实例管理页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox
)
from PySide6.QtCore import Qt

from ...i18n import t


class InstancesPage(QWidget):
    """多实例管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("content_area")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel(t("instances.title"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("创建隔离的 IDE 实例，支持并行运行")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(16)

        # 工具栏
        toolbar = QHBoxLayout()
        btn_create = QPushButton(f"➕ {t('instances.create')}")
        btn_create.setObjectName("primary_btn")
        btn_create.setCursor(Qt.PointingHandCursor)
        btn_create.clicked.connect(self._create_instance)
        toolbar.addWidget(btn_create)

        btn_batch = QPushButton("⚡ 批量启动")
        btn_batch.setObjectName("secondary_btn")
        btn_batch.setCursor(Qt.PointingHandCursor)
        toolbar.addWidget(btn_batch)

        toolbar.addStretch()
        content_layout.addLayout(toolbar)

        # 实例表格
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "实例名", "用户数据目录", "平台", "状态", "端口", "操作"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        content_layout.addWidget(self._table)

        content_layout.addStretch()
        layout.addWidget(content)

    def _create_instance(self):
        """创建新实例"""
        import uuid
        instance_id = str(uuid.uuid4())[:8]
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(f"instance_{instance_id}"))
        self._table.setItem(row, 1, QTableWidgetItem(f"~/.antigravity/instances/{instance_id}"))
        self._table.setItem(row, 2, QTableWidgetItem("codebuddy"))
        self._table.setItem(row, 3, QTableWidgetItem("⏹ 停止"))

        btn_start = QPushButton("▶ 启动")
        btn_start.setObjectName("secondary_btn")
        self._table.setCellWidget(row, 5, btn_start)
