"""Dialog windows for case management."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox,
    QListWidget, QListWidgetItem, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QMessageBox,
)

from ...db.case_manager import Case, CaseManager


class NewCaseDialog(QDialog):
    """Collect name / description / investigator for a new case."""

    def __init__(self, parent=None, defaults: Optional[Case] = None):
        super().__init__(parent)
        self.setWindowTitle("New Case" if defaults is None else "Edit Case")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(defaults.name if defaults else "")
        self.investigator_edit = QLineEdit(defaults.investigator if defaults else "")
        self.description_edit = QTextEdit(defaults.description if defaults else "")
        self.description_edit.setMinimumHeight(100)
        layout.addRow("Case name *", self.name_edit)
        layout.addRow("Investigator", self.investigator_edit)
        layout.addRow("Description", self.description_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation",
                                "Case name is required.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "investigator": self.investigator_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
        }


class OpenCaseDialog(QDialog):
    """List existing cases and let the user pick or delete one."""

    def __init__(self, manager: CaseManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._cases: list[Case] = []
        self.selected_case: Optional[Case] = None
        self.setWindowTitle("Open Case")
        self.resize(560, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Cases</b>"))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open)
        layout.addWidget(self.list, 1)

        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("Open")
        self.btn_open.clicked.connect(self._open)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete)
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        self._cases = self._manager.list_cases()
        for c in self._cases:
            updated = c.updated_at.strftime("%Y-%m-%d %H:%M") if c.updated_at else "-"
            item = QListWidgetItem(
                f"#{c.id}  {c.name}    [{c.investigator or '-'}]    "
                f"updated {updated}"
            )
            item.setData(0x0100, c.id)  # Qt.UserRole
            self.list.addItem(item)

    def _selected(self) -> Optional[Case]:
        item = self.list.currentItem()
        if not item:
            return None
        cid = item.data(0x0100)
        return next((c for c in self._cases if c.id == cid), None)

    def _open(self) -> None:
        c = self._selected()
        if not c:
            QMessageBox.information(self, "Open", "Select a case first.")
            return
        self.selected_case = c
        self.accept()

    def _delete(self) -> None:
        c = self._selected()
        if not c:
            return
        confirm = QMessageBox.question(
            self, "Delete case",
            f"Delete case '{c.name}' and all its evidence?\n"
            f"This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self._manager.delete_case(c.id)
        self.refresh()
