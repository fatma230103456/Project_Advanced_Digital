"""Main application window."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QFileDialog, QMessageBox, QTabWidget, QStatusBar,
    QProgressBar, QLabel, QSplitter, QWidget, QVBoxLayout,
)

from ..core.exif_extractor import ExifData
from ..core.anomaly_detector import Anomaly
from ..db.case_manager import Case, CaseManager
from ..reporting.pdf_report import ForensicReport, ReportContext
from ..utils.constants import APP_NAME, APP_VERSION, SUPPORTED_EXTENSIONS

from .widgets.evidence_table import EvidenceTable
from .widgets.exif_panel import ExifPanel
from .widgets.anomaly_panel import AnomalyPanel
from .widgets.timeline_panel import TimelinePanel
from .widgets.map_view import MapView
from .widgets.case_dialogs import NewCaseDialog, OpenCaseDialog
from .workers import IngestWorker


class MainWindow(QMainWindow):
    """Top-level forensic analysis window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 820)

        self.manager = CaseManager()
        self.current_case: Optional[Case] = None
        self.items: list[ExifData] = []
        self.anomalies: list[Anomaly] = []
        self._worker: Optional[IngestWorker] = None

        self._build_central()
        self._build_menus()
        self._build_statusbar()
        self._update_window_title()
        self._update_actions_enabled()

    # ---------- UI construction ----------

    def _build_central(self) -> None:
        self.tabs = QTabWidget()

        # Evidence tab: table + EXIF detail
        ev_tab = QWidget()
        ev_layout = QVBoxLayout(ev_tab)
        ev_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Vertical)
        self.evidence_table = EvidenceTable()
        self.exif_panel = ExifPanel()
        splitter.addWidget(self.evidence_table)
        splitter.addWidget(self.exif_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        ev_layout.addWidget(splitter)
        self.tabs.addTab(ev_tab, "Evidence")

        self.map_view = MapView()
        self.tabs.addTab(self.map_view, "Map")

        self.timeline_panel = TimelinePanel()
        self.tabs.addTab(self.timeline_panel, "Timeline")

        self.anomaly_panel = AnomalyPanel()
        self.tabs.addTab(self.anomaly_panel, "Anomalies")

        self.setCentralWidget(self.tabs)

        # signal wiring
        self.evidence_table.rowSelected.connect(self.exif_panel.set_data)
        self.anomaly_panel.fileActivated.connect(self._jump_to_file)
        self.timeline_panel.fileActivated.connect(self._jump_to_file)
        self.map_view.statusMessage.connect(self._set_status)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        self.act_new = QAction("&New Case…", self,
                               shortcut=QKeySequence.New,
                               triggered=self._new_case)
        self.act_open = QAction("&Open Case…", self,
                                shortcut=QKeySequence.Open,
                                triggered=self._open_case)
        self.act_close = QAction("&Close Case", self,
                                 triggered=self._close_case)
        self.act_quit = QAction("E&xit", self,
                                shortcut=QKeySequence.Quit,
                                triggered=self.close)
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_close)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        ev_menu = mb.addMenu("&Evidence")
        self.act_add_files = QAction("Add &Files…", self,
                                     shortcut="Ctrl+I",
                                     triggered=self._add_files)
        self.act_add_dir = QAction("Add &Directory…", self,
                                   triggered=self._add_directory)
        self.act_clear = QAction("Re&load From Database", self,
                                 triggered=self._reload_case)
        ev_menu.addAction(self.act_add_files)
        ev_menu.addAction(self.act_add_dir)
        ev_menu.addSeparator()
        ev_menu.addAction(self.act_clear)

        report_menu = mb.addMenu("&Report")
        self.act_pdf = QAction("Generate &PDF Report…", self,
                               shortcut="Ctrl+R",
                               triggered=self._generate_pdf)
        self.act_export_map = QAction("Export Map (HTML)…", self,
                                      triggered=self.map_view._export_html)
        report_menu.addAction(self.act_pdf)
        report_menu.addAction(self.act_export_map)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction(QAction("About", self, triggered=self._about))

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.case_label = QLabel("No case open")
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setVisible(False)
        sb.addWidget(self.case_label, 1)
        sb.addPermanentWidget(self.progress)
        self.setStatusBar(sb)

    # ---------- case lifecycle ----------

    def _update_window_title(self) -> None:
        suffix = ""
        if self.current_case:
            suffix = f" — {self.current_case.name} (#{self.current_case.id})"
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}{suffix}")
        if self.current_case:
            self.case_label.setText(
                f"Case #{self.current_case.id}: {self.current_case.name}   "
                f"|  Investigator: {self.current_case.investigator or '-'}"
            )
        else:
            self.case_label.setText("No case open")

    def _update_actions_enabled(self) -> None:
        has_case = self.current_case is not None
        for a in (self.act_close, self.act_add_files, self.act_add_dir,
                  self.act_clear, self.act_pdf, self.act_export_map):
            a.setEnabled(has_case)

    def _new_case(self) -> None:
        dlg = NewCaseDialog(self)
        if dlg.exec_() != dlg.Accepted:
            return
        v = dlg.values()
        case = self.manager.create_case(v["name"], v["description"], v["investigator"])
        self._set_current_case(case)
        self._set_status(f"Case '{case.name}' created.")

    def _open_case(self) -> None:
        dlg = OpenCaseDialog(self.manager, self)
        if dlg.exec_() != dlg.Accepted:
            return
        if dlg.selected_case:
            self._set_current_case(dlg.selected_case)
            self._reload_case()

    def _close_case(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Close case",
                                "Cannot close while ingest is running.")
            return
        self.current_case = None
        self.items = []
        self.anomalies = []
        self.evidence_table.set_items([])
        self.anomaly_panel.set_anomalies([])
        self.timeline_panel.set_items([])
        self.map_view.set_items([])
        self.exif_panel.set_data(None)
        self._update_window_title()
        self._update_actions_enabled()
        self._set_status("Case closed.")

    def _set_current_case(self, case: Case) -> None:
        self.current_case = case
        self._update_window_title()
        self._update_actions_enabled()

    # ---------- evidence ingest ----------

    def _add_files(self) -> None:
        if not self.current_case:
            return
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add evidence images", "", f"Images ({exts})")
        if paths:
            self._start_ingest(paths)

    def _add_directory(self) -> None:
        if not self.current_case:
            return
        d = QFileDialog.getExistingDirectory(
            self, "Add evidence from directory")
        if not d:
            return
        paths: list[str] = []
        for root, _, files in os.walk(d):
            for f in files:
                if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS:
                    paths.append(os.path.join(root, f))
        if not paths:
            QMessageBox.information(
                self, "Add directory",
                "No supported images were found in the selected directory.")
            return
        self._start_ingest(paths)

    def _start_ingest(self, paths: list[str]) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(
                self, "Ingest", "An ingest is already running.")
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self._worker = IngestWorker(paths, self.current_case.id, self.manager, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.error.connect(self._on_ingest_error)
        self._worker.finished_all.connect(self._on_ingest_done)
        self._worker.start()
        self._set_status(f"Ingesting {len(paths)} files…")

    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        self._set_status(f"[{current}/{total}] {name}")

    def _on_ingest_error(self, file_name: str, message: str) -> None:
        self._set_status(f"Error in {file_name}: {message}")

    def _on_ingest_done(self, items: list, anomalies: list) -> None:
        self.progress.setVisible(False)
        self._reload_case()
        self._set_status(
            f"Ingest complete: {len(items)} files, {len(anomalies)} anomalies")

    # ---------- refresh from DB ----------

    def _reload_case(self) -> None:
        if not self.current_case:
            return
        # Re-extract from disk for full ExifData (DB stores summary only).
        evidence = self.manager.list_evidence(self.current_case.id)
        from ..core.exif_extractor import ExifExtractor
        from ..core.anomaly_detector import AnomalyDetector
        extractor = ExifExtractor()
        detector = AnomalyDetector()
        items: list[ExifData] = []
        anomalies: list[Anomaly] = []
        for ev in evidence:
            try:
                data = extractor.extract(ev.file_path)
                items.append(data)
                anomalies.extend(detector.detect_for_image(data))
            except FileNotFoundError:
                continue
        anomalies.extend(detector.detect_for_collection(items))
        self.items = items
        self.anomalies = anomalies
        self.anomaly_panel.set_anomalies(anomalies)
        idx = self.anomaly_panel.anomaly_index()
        self.evidence_table.set_items(items, idx)
        self.timeline_panel.set_items(items)
        self.map_view.set_items(items, idx)

    # ---------- helpers ----------

    def _jump_to_file(self, file_path: str) -> None:
        for row in range(self.evidence_table.rowCount()):
            it = self.evidence_table.item(row, 0)
            if it and getattr(it.data(Qt.UserRole), "file_path", None) == file_path:
                self.tabs.setCurrentIndex(0)
                self.evidence_table.selectRow(row)
                self.evidence_table.scrollToItem(it)
                return

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)

    # ---------- reporting ----------

    def _generate_pdf(self) -> None:
        if not self.current_case:
            return
        suggested = f"forensic_report_case_{self.current_case.id}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Generate PDF report", suggested, "PDF (*.pdf)")
        if not path:
            return
        try:
            audit = self.manager.list_audit(self.current_case.id)
            ctx = ReportContext(
                case_name=self.current_case.name,
                case_description=self.current_case.description,
                investigator=self.current_case.investigator,
                case_id=self.current_case.id,
                items=self.items,
                anomalies=self.anomalies,
                audit_log=audit,
            )
            ForensicReport().generate(ctx, path)
            self.manager.log_action(
                self.current_case.id,
                self.current_case.investigator or "system",
                "report_generated", Path(path).name, {"path": path})
            self._set_status(f"Report saved to {path}")
            QMessageBox.information(
                self, "Report generated",
                f"PDF report saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Report error", str(exc))

    def _about(self) -> None:
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            "<p>Digital image metadata forensics — EXIF extraction, "
            "GPS analysis, anomaly detection, and court-ready reporting.</p>"
            "<p><i>For lawful forensic investigation use only.</i></p>"
        )

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        super().closeEvent(event)

