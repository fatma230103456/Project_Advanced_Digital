"""Detect signs of EXIF tampering, manipulation, or impossible scenarios."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Iterable, Optional

from PIL import Image

from .exif_extractor import ExifData
from .gps_decoder import GPSCoordinate, GPSDecoder
from ..utils.constants import (
    EDITING_SOFTWARE_KEYWORDS,
    MAX_REASONABLE_SPEED_KMH,
    WARNING_SPEED_KMH,
)


class AnomalySeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    code: str
    severity: AnomalySeverity
    title: str
    description: str
    file_path: Optional[str] = None
    related_files: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "related_files": list(self.related_files),
            "details": dict(self.details),
        }


class AnomalyDetector:
    """Inspect ExifData (single + collections) and report anomalies."""

    def detect_for_image(self, data: ExifData) -> list[Anomaly]:
        findings: list[Anomaly] = []
        findings.extend(self._check_exif_stripping(data))
        findings.extend(self._check_editing_software(data))
        findings.extend(self._check_timestamp_mismatch(data))
        findings.extend(self._check_gps_without_camera(data))
        findings.extend(self._check_invalid_gps(data))
        findings.extend(self._check_thumbnail_mismatch(data))
        findings.extend(self._check_future_date(data))
        return findings

    def detect_for_collection(self, items: Iterable[ExifData]) -> list[Anomaly]:
        items = list(items)
        findings: list[Anomaly] = []
        findings.extend(self._check_impossible_travel(items))
        findings.extend(self._check_duplicate_timestamps(items))
        return findings

    # -------- per-image checks --------

    def _check_exif_stripping(self, d: ExifData) -> list[Anomaly]:
        if d.has_exif:
            return []
        return [Anomaly(
            code="EXIF_STRIPPED",
            severity=AnomalySeverity.MEDIUM,
            title="EXIF metadata missing",
            description=(
                "The image contains no EXIF metadata. This may indicate the file was "
                "re-saved by a social network, screenshotted, or deliberately stripped."
            ),
            file_path=d.file_path,
        )]

    def _check_editing_software(self, d: ExifData) -> list[Anomaly]:
        if not d.software:
            return []
        sw_low = d.software.lower()
        for keyword in EDITING_SOFTWARE_KEYWORDS:
            if keyword in sw_low:
                return [Anomaly(
                    code="EDITING_SOFTWARE",
                    severity=AnomalySeverity.HIGH,
                    title=f"Editing software detected: {d.software}",
                    description=(
                        "The Software EXIF tag references a known image editing tool. "
                        "The image may have been modified after capture."
                    ),
                    file_path=d.file_path,
                    details={"software": d.software, "matched": keyword},
                )]
        return []

    def _check_timestamp_mismatch(self, d: ExifData) -> list[Anomaly]:
        ts_o = d.datetime_original
        ts_d = d.datetime_digitized
        ts_m = d.datetime_modified
        ts_file = d.file_mtime
        out: list[Anomaly] = []
        if ts_o and ts_d and abs((ts_o - ts_d).total_seconds()) > 60:
            out.append(Anomaly(
                code="TS_ORIG_DIGI_MISMATCH",
                severity=AnomalySeverity.MEDIUM,
                title="DateTimeOriginal vs DateTimeDigitized differ",
                description="Capture and digitization timestamps differ by more than a minute.",
                file_path=d.file_path,
                details={"original": ts_o.isoformat(), "digitized": ts_d.isoformat()},
            ))
        if ts_o and ts_file and (ts_file - ts_o) < timedelta(seconds=-60):
            out.append(Anomaly(
                code="TS_FILE_BEFORE_ORIG",
                severity=AnomalySeverity.HIGH,
                title="File modified time predates capture time",
                description="The filesystem mtime is earlier than the EXIF capture time.",
                file_path=d.file_path,
                details={"original": ts_o.isoformat(), "file_mtime": ts_file.isoformat()},
            ))
        if ts_o and ts_m and ts_m < ts_o - timedelta(seconds=60):
            out.append(Anomaly(
                code="TS_MOD_BEFORE_ORIG",
                severity=AnomalySeverity.MEDIUM,
                title="EXIF modification time precedes capture",
                description="DateTime tag (modified) is earlier than DateTimeOriginal.",
                file_path=d.file_path,
                details={"original": ts_o.isoformat(), "modified": ts_m.isoformat()},
            ))
        return out

    def _check_gps_without_camera(self, d: ExifData) -> list[Anomaly]:
        if d.gps and d.gps.is_valid() and not d.camera_make and not d.camera_model:
            return [Anomaly(
                code="GPS_NO_CAMERA",
                severity=AnomalySeverity.MEDIUM,
                title="GPS present but camera identity missing",
                description=(
                    "GPS coordinates were found, but no camera Make/Model is recorded. "
                    "GPS metadata may have been injected post-capture."
                ),
                file_path=d.file_path,
                details=d.gps.to_dict(),
            )]
        return []

    def _check_invalid_gps(self, d: ExifData) -> list[Anomaly]:
        if d.gps is None:
            return []
        if not d.gps.is_valid():
            return [Anomaly(
                code="GPS_INVALID",
                severity=AnomalySeverity.HIGH,
                title="GPS coordinates invalid or null",
                description="Decoded GPS coordinates are out-of-range or point to (0,0).",
                file_path=d.file_path,
                details=d.gps.to_dict(),
            )]
        return []

    def _check_thumbnail_mismatch(self, d: ExifData) -> list[Anomaly]:
        if not d.thumbnail_bytes:
            return []
        try:
            with Image.open(io.BytesIO(d.thumbnail_bytes)) as thumb:
                tw, th = thumb.size
        except Exception:
            return []
        if not (d.image_width and d.image_height):
            return []
        thumb_ratio = tw / th if th else 0
        full_ratio = d.image_width / d.image_height if d.image_height else 0
        if thumb_ratio and full_ratio and abs(thumb_ratio - full_ratio) > 0.15:
            return [Anomaly(
                code="THUMBNAIL_RATIO_MISMATCH",
                severity=AnomalySeverity.HIGH,
                title="Embedded thumbnail aspect ratio mismatch",
                description=(
                    "The EXIF thumbnail's aspect ratio differs significantly from the "
                    "main image. This commonly occurs after cropping or compositing."
                ),
                file_path=d.file_path,
                details={
                    "thumbnail_size": [tw, th],
                    "image_size": [d.image_width, d.image_height],
                },
            )]
        return []

    def _check_future_date(self, d: ExifData) -> list[Anomaly]:
        from datetime import datetime
        now = datetime.now()
        out = []
        for label, ts in (
            ("DateTimeOriginal", d.datetime_original),
            ("DateTimeDigitized", d.datetime_digitized),
        ):
            if ts and ts > now + timedelta(days=1):
                out.append(Anomaly(
                    code="TS_FUTURE",
                    severity=AnomalySeverity.HIGH,
                    title=f"{label} is set in the future",
                    description=f"{label}={ts.isoformat()} is later than the current system time.",
                    file_path=d.file_path,
                    details={"timestamp": ts.isoformat(), "now": now.isoformat()},
                ))
        return out

    # -------- collection checks --------

    def _check_impossible_travel(self, items: list[ExifData]) -> list[Anomaly]:
        with_gps = [d for d in items if d.gps and d.gps.is_valid() and d.datetime_original]
        with_gps.sort(key=lambda d: d.datetime_original)
        out: list[Anomaly] = []
        for prev, curr in zip(with_gps, with_gps[1:]):
            dt = (curr.datetime_original - prev.datetime_original).total_seconds()
            if dt <= 0:
                continue
            distance = GPSDecoder.haversine_km(prev.gps, curr.gps)
            speed_kmh = distance / (dt / 3600.0)
            if speed_kmh > MAX_REASONABLE_SPEED_KMH:
                severity = AnomalySeverity.CRITICAL
                title = "Impossible travel speed between images"
            elif speed_kmh > WARNING_SPEED_KMH:
                severity = AnomalySeverity.MEDIUM
                title = "High travel speed between images"
            else:
                continue
            out.append(Anomaly(
                code="IMPOSSIBLE_TRAVEL",
                severity=severity,
                title=title,
                description=(
                    f"Distance {distance:.1f} km traveled in {dt/60:.1f} min "
                    f"(~{speed_kmh:.0f} km/h)."
                ),
                file_path=curr.file_path,
                related_files=[prev.file_path],
                details={
                    "distance_km": round(distance, 3),
                    "duration_seconds": dt,
                    "speed_kmh": round(speed_kmh, 1),
                    "from": prev.gps.to_dict(),
                    "to": curr.gps.to_dict(),
                },
            ))
        return out

    def _check_duplicate_timestamps(self, items: list[ExifData]) -> list[Anomaly]:
        seen: dict = {}
        out: list[Anomaly] = []
        for d in items:
            if not d.datetime_original:
                continue
            key = d.datetime_original.replace(microsecond=0)
            seen.setdefault(key, []).append(d.file_path)
        for key, paths in seen.items():
            if len(paths) > 1:
                out.append(Anomaly(
                    code="DUPLICATE_TIMESTAMP",
                    severity=AnomalySeverity.LOW,
                    title="Multiple images share the same capture timestamp",
                    description=(
                        f"{len(paths)} images report DateTimeOriginal={key.isoformat()}."
                    ),
                    file_path=paths[0],
                    related_files=paths[1:],
                    details={"timestamp": key.isoformat(), "count": len(paths)},
                ))
        return out
