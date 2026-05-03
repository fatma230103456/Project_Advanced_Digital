"""Evidence table widget — displays EXIF rows with anomaly badges."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ...core.exif_extractor import ExifData


SEVERITY_BG = {
    "critical": QColor("#8B0000"),
    "high": QColor("#D32F2F"),
    "medium": QColor("#F57C00"),
    "low": QColor("#1976D2"),
    "info": QColor("#9E9E9E"),
}

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class EvidenceTable(QTableWidget):
    """Lists ingested ExifData items in a sortable table."""

    rowSelected = pyqtSignal(object)  # emits ExifData or None

    HEADERS = [
        "File", "Format", "Dimensions", "Camera",
        "Software", "Captured", "GPS", "Anomaly",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ExifData] = []
        self._anomaly_index: dict[str, str] = {}
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        h = self.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(self.HEADERS)):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.itemSelectionChanged.connect(self._emit_selection)

    # ---------- public API ----------

    def set_items(self, items: list[ExifData],
                  anomaly_index: Optional[dict[str, str]] = None) -> None:
        self._items = list(items)
        self._anomaly_index = anomaly_index or {}
        self.setSortingEnabled(False)
        self.setRowCount(len(self._items))
        for row, d in enumerate(self._items):
            self._populate_row(row, d)
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def update_anomaly_index(self, anomaly_index: dict[str, str]) -> None:
        self._anomaly_index = anomaly_index or {}
        for row in range(self.rowCount()):
            path_item = self.item(row, 0)
            if path_item is None:
                continue
            d = path_item.data(Qt.UserRole)
            if not d:
                continue
            sv = self._anomaly_index.get(d.file_path)
            self._set_anomaly_cell(row, sv)

    def selected_item(self) -> Optional[ExifData]:
        rows = self.selectionModel().selectedRows() if self.selectionModel() else []
        if not rows:
            return None
        item = self.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    # ---------- helpers ----------

    def _populate_row(self, row: int, d: ExifData) -> None:
        gps_text = "-"
        if d.gps and d.gps.is_valid():
            gps_text = f"{d.gps.latitude:.5f}, {d.gps.longitude:.5f}"
        cells = [
            d.file_name,
            d.image_format or "-",
            f"{d.image_width or '-'}x{d.image_height or '-'}",
            " ".join(filter(None, [d.camera_make, d.camera_model])) or "-",
            d.software or "-",
            d.datetime_original.isoformat() if d.datetime_original else "-",
            gps_text,
            "",
        ]
        for col, value in enumerate(cells):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            if col == 0:
                item.setData(Qt.UserRole, d)
                item.setToolTip(d.file_path)
            self.setItem(row, col, item)
        sv = self._anomaly_index.get(d.file_path)
        self._set_anomaly_cell(row, sv)

    def _set_anomaly_cell(self, row: int, severity: Optional[str]) -> None:
        cell = self.item(row, len(self.HEADERS) - 1)
        if cell is None:
            return
        if severity:
            cell.setText(severity.upper())
            color = SEVERITY_BG.get(severity, QColor("#9E9E9E"))
            cell.setBackground(QBrush(color))
            cell.setForeground(QBrush(QColor("white")))
            cell.setData(Qt.UserRole, SEVERITY_RANK.get(severity, 0))
        else:
            cell.setText("OK")
            cell.setBackground(QBrush(QColor("#E8F5E9")))
            cell.setForeground(QBrush(QColor("#2E7D32")))
            cell.setData(Qt.UserRole, -1)

    def _emit_selection(self) -> None:
        self.rowSelected.emit(self.selected_item())
