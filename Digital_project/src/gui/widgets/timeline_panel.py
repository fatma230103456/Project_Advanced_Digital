"""Chronological timeline panel."""
from __future__ import annotations

from typing import Iterable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)

from ...core.exif_extractor import ExifData
from ...core.correlator import build_timeline


class TimelinePanel(QWidget):
    """Chronologically ordered evidence with elapsed time between events."""

    fileActivated = pyqtSignal(str)

    HEADERS = ["#", "Timestamp", "File", "Camera", "GPS", "Δ Time"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        header = QHBoxLayout()
        self.title_label = QLabel("<b>Timeline</b>")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.range_label = QLabel("")
        header.addWidget(self.range_label)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._activate_row)
        layout.addWidget(self.table)

    # ---------- public API ----------

    def set_items(self, items: Iterable[ExifData]) -> None:
        entries = build_timeline(items)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        prev = None
        gap_warn = QBrush(QColor("#FFF3CD"))
        for row, e in enumerate(entries):
            gps_text = "-"
            if e.gps and e.gps.is_valid():
                gps_text = f"{e.gps.latitude:.5f}, {e.gps.longitude:.5f}"
            delta = ""
            if prev is not None:
                d = (e.timestamp - prev.timestamp).total_seconds()
                delta = self._format_delta(d)
            cells = [
                str(row + 1),
                e.timestamp.isoformat(sep=" "),
                e.file_name,
                e.camera or "-",
                gps_text,
                delta,
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col == 2:
                    item.setData(Qt.UserRole, e.file_path)
                    item.setToolTip(e.file_path)
                self.table.setItem(row, col, item)
            if prev is not None:
                gap = (e.timestamp - prev.timestamp).total_seconds()
                if gap > 86400:
                    self.table.item(row, 5).setBackground(gap_warn)
            prev = e
        self.table.setSortingEnabled(True)
        if entries:
            self.title_label.setText(f"<b>Timeline:</b> {len(entries)} entries")
            self.range_label.setText(
                f"From {entries[0].timestamp.isoformat(sep=' ')} "
                f"to {entries[-1].timestamp.isoformat(sep=' ')}"
            )
        else:
            self.title_label.setText("<b>Timeline:</b> no dated items")
            self.range_label.setText("")

    @staticmethod
    def _format_delta(seconds: float) -> str:
        if seconds < 60:
            return f"+{seconds:.0f}s"
        if seconds < 3600:
            return f"+{seconds / 60:.1f} min"
        if seconds < 86400:
            return f"+{seconds / 3600:.1f} h"
        return f"+{seconds / 86400:.1f} d"

    def _activate_row(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 2)
        path = item.data(Qt.UserRole) if item else None
        if path:
            self.fileActivated.emit(path)
