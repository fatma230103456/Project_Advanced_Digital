"""Folium map view embedded in QWebEngineView."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from PyQt5.QtCore import QUrl, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLabel,
    QFileDialog, QMessageBox,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
    WEB_OK = True
except ImportError:  # pragma: no cover
    WEB_OK = False
    QWebEngineView = None  # type: ignore

from ...core.exif_extractor import ExifData
from ...mapping.map_builder import MapBuilder


class MapView(QWidget):
    """Map tab — renders the latest folium map and allows export."""

    statusMessage = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._builder = MapBuilder()
        self._items: list[ExifData] = []
        self._anomaly_index: dict[str, str] = {}
        self._tmpdir = Path(tempfile.mkdtemp(prefix="forensics_map_"))
        self._current_html: Optional[Path] = None
        self._build_ui()
        self._render_empty()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        self.cb_clusters = QCheckBox("Clusters")
        self.cb_clusters.setChecked(True)
        self.cb_path = QCheckBox("Path")
        self.cb_path.setChecked(True)
        self.cb_animate = QCheckBox("Animate path")
        self.cb_animate.setChecked(True)
        self.cb_heat = QCheckBox("Heatmap")
        self.cb_heat.setChecked(True)
        for cb in (self.cb_clusters, self.cb_path, self.cb_animate, self.cb_heat):
            cb.toggled.connect(self.refresh)
            toolbar.addWidget(cb)
        toolbar.addStretch(1)
        self.btn_export = QPushButton("Export HTML…")
        self.btn_export.clicked.connect(self._export_html)
        toolbar.addWidget(self.btn_export)
        self.btn_open = QPushButton("Open in browser")
        self.btn_open.clicked.connect(self._open_in_browser)
        toolbar.addWidget(self.btn_open)
        layout.addLayout(toolbar)

        if WEB_OK:
            self.web = QWebEngineView()
            layout.addWidget(self.web, 1)
        else:
            self.web = None
            warn = QLabel(
                "QtWebEngine is not available — install PyQtWebEngine to render maps.\n"
                "Use the 'Open in browser' button to view the generated map."
            )
            warn.setStyleSheet("padding:20px; color:#a00;")
            layout.addWidget(warn, 1)

    # ---------- public API ----------

    def set_items(self, items: Iterable[ExifData],
                  anomaly_index: Optional[dict[str, str]] = None) -> None:
        self._items = list(items)
        self._anomaly_index = anomaly_index or {}
        self.refresh()

    def refresh(self) -> None:
        fmap = self._builder.build(
            self._items,
            anomaly_index=self._anomaly_index,
            show_path=self.cb_path.isChecked(),
            show_heatmap=self.cb_heat.isChecked(),
            show_clusters=self.cb_clusters.isChecked(),
            animate_path=self.cb_animate.isChecked(),
        )
        out = self._tmpdir / "current_map.html"
        self._builder.save(fmap, out)
        self._current_html = out
        if self.web is not None:
            self.web.load(QUrl.fromLocalFile(str(out.resolve())))
        self.statusMessage.emit(f"Map rendered ({len(self._items)} items)")

    def current_html(self) -> Optional[Path]:
        return self._current_html

    # ---------- actions ----------

    def _render_empty(self) -> None:
        self.refresh()

    def _export_html(self) -> None:
        if not self._current_html or not self._current_html.exists():
            QMessageBox.information(self, "Export map", "No map to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export map as HTML", "forensic_map.html",
            "HTML files (*.html)")
        if not path:
            return
        Path(path).write_bytes(self._current_html.read_bytes())
        self.statusMessage.emit(f"Map exported to {path}")

    def _open_in_browser(self) -> None:
        if not self._current_html or not self._current_html.exists():
            return
        import webbrowser
        webbrowser.open(self._current_html.resolve().as_uri())
