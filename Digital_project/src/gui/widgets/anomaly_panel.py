"""Anomaly findings panel."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLabel, QTextEdit, QSplitter,
)

from ...core.anomaly_detector import Anomaly


SEVERITY_BG = {
    "critical": QColor("#8B0000"),
    "high": QColor("#D32F2F"),
    "medium": QColor("#F57C00"),
    "low": QColor("#1976D2"),
    "info": QColor("#9E9E9E"),
}

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class AnomalyPanel(QWidget):
    """Table of anomalies with detail view."""

    fileActivated = pyqtSignal(str)  # emits file_path on row activation

    HEADERS = ["#", "Severity", "Code", "Title", "File"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._anomalies: list[Anomaly] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        header = QHBoxLayout()
        self.title_label = QLabel("<b>Anomalies:</b> 0")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.summary_label = QLabel("")
        header.addWidget(self.summary_label)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Vertical)
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._update_detail)
        self.table.itemDoubleClicked.connect(self._activate_row)
        splitter.addWidget(self.table)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(
            "QTextEdit { background:#fafbfc; font-family:Consolas,monospace; "
            "font-size:11px; }"
        )
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    # ---------- public API ----------

    def set_anomalies(self, anomalies: Iterable[Anomaly]) -> None:
        self._anomalies = list(anomalies)
        self._anomalies.sort(
            key=lambda a: -SEVERITY_RANK.get(self._sev(a), 0))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._anomalies))
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for row, a in enumerate(self._anomalies):
            sv = self._sev(a)
            counts[sv] = counts.get(sv, 0) + 1
            file_name = Path(a.file_path).name if a.file_path else "-"
            cells = [str(row + 1), sv.upper(), a.code, a.title, file_name]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setData(Qt.UserRole, a)
                if col == 1:
                    color = SEVERITY_BG.get(sv, QColor("#9E9E9E"))
                    item.setBackground(QBrush(color))
                    item.setForeground(QBrush(QColor("white")))
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.title_label.setText(f"<b>Anomalies:</b> {len(self._anomalies)}")
        self.summary_label.setText(
            f"Critical: {counts['critical']}   High: {counts['high']}   "
            f"Medium: {counts['medium']}   Low: {counts['low']}"
        )
        self.detail.clear()

    def anomaly_index(self) -> dict[str, str]:
        """Map file_path -> highest severity for use by other widgets."""
        idx: dict[str, str] = {}
        for a in self._anomalies:
            if not a.file_path:
                continue
            sv = self._sev(a)
            if SEVERITY_RANK.get(sv, 0) > SEVERITY_RANK.get(idx.get(a.file_path, "info"), -1):
                idx[a.file_path] = sv
        return idx

    @staticmethod
    def _sev(a: Anomaly) -> str:
        return a.severity.value if hasattr(a.severity, "value") else str(a.severity)

    # ---------- helpers ----------

    def _update_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.detail.clear()
            return
        item = self.table.item(rows[0].row(), 0)
        a = item.data(Qt.UserRole) if item else None
        if not a:
            self.detail.clear()
            return
        details_json = json.dumps(a.details or {}, indent=2, default=str)
        text = (
            f"Code:        {a.code}\n"
            f"Severity:    {self._sev(a).upper()}\n"
            f"Title:       {a.title}\n"
            f"File:        {a.file_path or '-'}\n"
            f"Description: {a.description}\n"
            f"\nDetails:\n{details_json}"
        )
        self.detail.setPlainText(text)

    def _activate_row(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        a = item.data(Qt.UserRole) if item else None
        if a and a.file_path:
            self.fileActivated.emit(a.file_path)
