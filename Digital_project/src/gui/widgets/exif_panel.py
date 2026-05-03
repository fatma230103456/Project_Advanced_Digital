"""EXIF viewer panel (thumbnail + metadata tree)."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QFormLayout, QSizePolicy, QPushButton, QFileDialog, QApplication,
)

from ...core.exif_extractor import ExifData


class ExifPanel(QWidget):
    """Display thumbnail, summary, raw tags, and GPS for one ExifData."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current: Optional[ExifData] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        left = QVBoxLayout()
        self.thumb_label = QLabel("No image selected")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setMinimumSize(280, 220)
        self.thumb_label.setStyleSheet(
            "QLabel { background:#f5f7fa; border:1px solid #cbd5e0; "
            "border-radius:6px; color:#666; }"
        )
        left.addWidget(self.thumb_label)

        summary_box = QGroupBox("Summary")
        form = QFormLayout(summary_box)
        form.setLabelAlignment(Qt.AlignRight)
        self.lbl_file = QLabel("-")
        self.lbl_format = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_camera = QLabel("-")
        self.lbl_software = QLabel("-")
        self.lbl_dto = QLabel("-")
        self.lbl_gps = QLabel("-")
        for w in (self.lbl_file, self.lbl_format, self.lbl_size, self.lbl_camera,
                  self.lbl_software, self.lbl_dto, self.lbl_gps):
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            w.setWordWrap(True)
        form.addRow("File:", self.lbl_file)
        form.addRow("Format:", self.lbl_format)
        form.addRow("Dimensions:", self.lbl_size)
        form.addRow("Camera:", self.lbl_camera)
        form.addRow("Software:", self.lbl_software)
        form.addRow("Captured:", self.lbl_dto)
        form.addRow("GPS:", self.lbl_gps)
        left.addWidget(summary_box)

        self.copy_btn = QPushButton("Copy GPS coordinates")
        self.copy_btn.clicked.connect(self._copy_gps)
        left.addWidget(self.copy_btn)
        self.export_btn = QPushButton("Export tags as JSON…")
        self.export_btn.clicked.connect(self._export_tags)
        left.addWidget(self.export_btn)
        left.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Raw EXIF Tags</b>"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Value"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right.addWidget(self.tree)

        layout.addLayout(left, 0)
        layout.addLayout(right, 1)

    # ---------- public API ----------

    def set_data(self, data: Optional[ExifData]) -> None:
        self._current = data
        self.tree.clear()
        if data is None:
            self.thumb_label.setText("No image selected")
            self.thumb_label.setPixmap(QPixmap())
            for lbl in (self.lbl_file, self.lbl_format, self.lbl_size,
                        self.lbl_camera, self.lbl_software, self.lbl_dto,
                        self.lbl_gps):
                lbl.setText("-")
            return
        if data.thumbnail_bytes:
            pix = QPixmap()
            if pix.loadFromData(data.thumbnail_bytes):
                self.thumb_label.setPixmap(pix.scaled(
                    self.thumb_label.size(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.thumb_label.setText("Thumbnail unreadable")
        else:
            try:
                pix = QPixmap(data.file_path)
                if not pix.isNull():
                    self.thumb_label.setPixmap(pix.scaled(
                        self.thumb_label.size(),
                        Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.thumb_label.setText("(no thumbnail)")
            except Exception:
                self.thumb_label.setText("(no thumbnail)")
        self.lbl_file.setText(data.file_name)
        self.lbl_format.setText(
            f"{data.image_format or '-'}  ({data.image_mode or '-'})")
        self.lbl_size.setText(
            f"{data.image_width or '-'} x {data.image_height or '-'} px"
            f"   |   {(data.file_size or 0):,} bytes")
        self.lbl_camera.setText(
            " ".join(filter(None, [data.camera_make, data.camera_model])) or "-")
        self.lbl_software.setText(data.software or "-")
        self.lbl_dto.setText(
            data.datetime_original.isoformat() if data.datetime_original else "-")
        if data.gps and data.gps.is_valid():
            self.lbl_gps.setText(
                f"{data.gps.latitude:.6f}, {data.gps.longitude:.6f}")
        else:
            self.lbl_gps.setText("-")
        for key in sorted(data.raw_tags):
            QTreeWidgetItem(self.tree, [key, data.raw_tags[key]])
        self.tree.resizeColumnToContents(0)

    # ---------- actions ----------

    def _copy_gps(self) -> None:
        if not self._current or not self._current.gps or not self._current.gps.is_valid():
            return
        coord = f"{self._current.gps.latitude:.6f}, {self._current.gps.longitude:.6f}"
        QApplication.clipboard().setText(coord)

    def _export_tags(self) -> None:
        if not self._current:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export EXIF tags",
            f"{self._current.file_name}.exif.json", "JSON (*.json)")
        if not path:
            return
        import json
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(self._current.to_dict(), fp, indent=2, default=str)
