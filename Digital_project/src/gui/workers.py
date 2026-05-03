"""Background worker threads for the GUI."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from ..core.exif_extractor import ExifExtractor, ExifData
from ..core.hasher import compute_hashes, FileHashes
from ..core.anomaly_detector import AnomalyDetector, Anomaly
from ..db.case_manager import CaseManager


class IngestWorker(QThread):
    """Hash, extract EXIF, detect anomalies, and persist evidence."""

    progress = pyqtSignal(int, int, str)  # current, total, file_name
    fileDone = pyqtSignal(object, object, list)  # ExifData, FileHashes, [Anomaly]
    finished_all = pyqtSignal(list, list)  # [ExifData], [Anomaly]
    error = pyqtSignal(str, str)  # file_name, message

    def __init__(self, paths: list[str], case_id: int,
                 manager: CaseManager, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._paths = list(paths)
        self._case_id = case_id
        self._manager = manager
        self._extractor = ExifExtractor()
        self._detector = AnomalyDetector()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        all_items: list[ExifData] = []
        all_anomalies: list[Anomaly] = []
        total = len(self._paths)
        for i, path in enumerate(self._paths, start=1):
            if self._cancelled:
                break
            name = Path(path).name
            self.progress.emit(i, total, name)
            try:
                hashes = compute_hashes(path)
                data = self._extractor.extract(path)
                anomalies = self._detector.detect_for_image(data)
                self._persist(data, hashes, anomalies)
                all_items.append(data)
                all_anomalies.extend(anomalies)
                self.fileDone.emit(data, hashes, anomalies)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(name, str(exc))
        if not self._cancelled and all_items:
            collection_anomalies = self._detector.detect_for_collection(all_items)
            if collection_anomalies:
                self._manager.add_anomalies(self._case_id, None, collection_anomalies)
                all_anomalies.extend(collection_anomalies)
        self.finished_all.emit(all_items, all_anomalies)

    def _persist(self, data: ExifData, hashes: FileHashes,
                 anomalies: list[Anomaly]) -> None:
        ev_id = self._manager.add_evidence(
            self._case_id,
            file_path=data.file_path,
            file_name=data.file_name,
            sha256=hashes.sha256,
            md5=hashes.md5,
            sha1=hashes.sha1,
            file_size=hashes.size,
            image_format=data.image_format,
            width=data.image_width,
            height=data.image_height,
            camera_make=data.camera_make,
            camera_model=data.camera_model,
            software=data.software,
            datetime_original=(
                data.datetime_original.isoformat()
                if data.datetime_original else None
            ),
            latitude=data.gps.latitude if data.gps else None,
            longitude=data.gps.longitude if data.gps else None,
            altitude=data.gps.altitude if data.gps else None,
            has_exif=data.has_exif,
            exif_dict=data.to_dict(),
        )
        if anomalies:
            self._manager.add_anomalies(self._case_id, ev_id, anomalies)
