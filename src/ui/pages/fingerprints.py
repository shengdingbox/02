"""设备指纹页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
)
from PySide6.QtCore import Qt
import uuid

from ...i18n import t


class FingerprintsPage(QWidget):
    """设备指纹管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("content_area")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel(t("fingerprints.title"))
        title.setObjectName("page_title")
        layout.addWidget(title)

        subtitle = QLabel("管理和生成设备指纹，用于多账号隔离")
        subtitle.setObjectName("page_subtitle")
        layout.addWidget(subtitle)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 0, 32, 32)
        content_layout.setSpacing(16)

        # 生成指纹
        gen_card = QFrame()
        gen_card.setObjectName("card")
        gen_layout = QVBoxLayout(gen_card)

        gen_layout.addWidget(QLabel("🔐 生成新指纹"))

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("平台:"))
        platform_input = QLineEdit()
        platform_input.setPlaceholderText("codebuddy / windsurf / codex")
        form_row.addWidget(platform_input)
        gen_layout.addLayout(form_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("备注:"))
        notes_input = QLineEdit()
        notes_input.setPlaceholderText("可选备注")
        notes_row.addWidget(notes_input)
        gen_layout.addLayout(notes_row)

        btn_generate = QPushButton("🎲 生成指纹")
        btn_generate.setObjectName("primary_btn")
        btn_generate.setCursor(Qt.PointingHandCursor)
        btn_generate.clicked.connect(lambda: self._generate_fingerprint(
            platform_input.text(), notes_input.text()
        ))
        gen_layout.addWidget(btn_generate)

        content_layout.addWidget(gen_card)

        # 指纹列表
        list_label = QLabel("📋 已保存的指纹")
        list_label.setStyleSheet("font-size: 16px; font-weight: 600; margin-top: 8px;")
        content_layout.addWidget(list_label)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Device ID", "Machine ID", "平台", "备注", "操作"
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        content_layout.addWidget(self._table)

        content_layout.addStretch()
        layout.addWidget(content)

    def _generate_fingerprint(self, platform: str, notes: str):
        """生成新指纹"""
        device_id = str(uuid.uuid4())
        machine_id = str(uuid.uuid4()).replace("-", "")[:32]

        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(device_id[:16] + "..."))
        self._table.setItem(row, 1, QTableWidgetItem(machine_id[:16] + "..."))
        self._table.setItem(row, 2, QTableWidgetItem(platform or "-"))
        self._table.setItem(row, 3, QTableWidgetItem(notes or "-"))

        btn = QPushButton("📋 复制")
        btn.setObjectName("icon_btn")
        btn.clicked.connect(lambda: self._copy_fingerprint(device_id, machine_id))
        self._table.setCellWidget(row, 4, btn)

    def _copy_fingerprint(self, device_id: str, machine_id: str):
        """复制指纹"""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(f"Device ID: {device_id}\nMachine ID: {machine_id}")
