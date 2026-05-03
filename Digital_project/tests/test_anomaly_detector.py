"""Tests for src.core.anomaly_detector."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from src.core.anomaly_detector import AnomalyDetector, AnomalySeverity
from src.core.exif_extractor import ExifData, ExifExtractor
from src.core.gps_decoder import GPSCoordinate


def _bare(file_path: str = "/tmp/x.jpg", **kw) -> ExifData:
    base = dict(
        file_path=file_path, file_name=Path(file_path).name,
        file_size=1, file_mtime=datetime(2023, 1, 1, 12, 0, 0),
        image_format="JPEG", image_width=4000, image_height=3000,
        image_mode="RGB",
    )
    base.update(kw)
    return ExifData(**base)


def test_detects_exif_stripping_on_no_exif_image(jpeg_no_exif: Path):
    data = ExifExtractor().extract(jpeg_no_exif)
    findings = AnomalyDetector().detect_for_image(data)
    codes = [f.code for f in findings]
    assert "EXIF_STRIPPED" in codes


def test_detects_editing_software_on_photoshop_image(jpeg_edited: Path):
    data = ExifExtractor().extract(jpeg_edited)
    findings = AnomalyDetector().detect_for_image(data)
    codes = [f.code for f in findings]
    assert "EDITING_SOFTWARE" in codes
    sw_finding = next(f for f in findings if f.code == "EDITING_SOFTWARE")
    assert sw_finding.severity == AnomalySeverity.HIGH


def test_clean_image_has_no_anomalies(jpeg_with_gps: Path):
    data = ExifExtractor().extract(jpeg_with_gps)
    findings = AnomalyDetector().detect_for_image(data)
    codes = [f.code for f in findings]
    assert "EXIF_STRIPPED" not in codes
    assert "EDITING_SOFTWARE" not in codes
    assert "GPS_INVALID" not in codes


def test_detects_invalid_gps(jpeg_invalid_gps: Path):
    data = ExifExtractor().extract(jpeg_invalid_gps)
    findings = AnomalyDetector().detect_for_image(data)
    codes = [f.code for f in findings]
    assert "GPS_INVALID" in codes


def test_detects_timestamp_mismatch():
    d = _bare(
        has_exif=True, camera_make="X", camera_model="Y",
        datetime_original=datetime(2023, 1, 1, 10, 0, 0),
        datetime_digitized=datetime(2023, 1, 1, 11, 0, 0),
    )
    findings = AnomalyDetector().detect_for_image(d)
    codes = [f.code for f in findings]
    assert "TS_ORIG_DIGI_MISMATCH" in codes


def test_detects_future_timestamp():
    future = datetime.now() + timedelta(days=30)
    d = _bare(
        has_exif=True, camera_make="X", camera_model="Y",
        datetime_original=future,
    )
    findings = AnomalyDetector().detect_for_image(d)
    codes = [f.code for f in findings]
    assert "TS_FUTURE" in codes


def test_detects_gps_without_camera():
    d = _bare(
        has_exif=True, camera_make=None, camera_model=None,
        gps=GPSCoordinate(30.0, 31.0),
    )
    findings = AnomalyDetector().detect_for_image(d)
    codes = [f.code for f in findings]
    assert "GPS_NO_CAMERA" in codes


def test_detects_impossible_travel_in_collection():
    a = _bare(
        file_path="/tmp/a.jpg", has_exif=True,
        camera_make="C", camera_model="M",
        datetime_original=datetime(2023, 7, 1, 9, 0, 0),
        gps=GPSCoordinate(30.0444, 31.2357),
    )
    b = _bare(
        file_path="/tmp/b.jpg", has_exif=True,
        camera_make="C", camera_model="M",
        datetime_original=datetime(2023, 7, 1, 9, 30, 0),
        gps=GPSCoordinate(35.6895, 139.6917),
    )
    findings = AnomalyDetector().detect_for_collection([a, b])
    codes = [f.code for f in findings]
    assert "IMPOSSIBLE_TRAVEL" in codes
    travel = next(f for f in findings if f.code == "IMPOSSIBLE_TRAVEL")
    assert travel.severity == AnomalySeverity.CRITICAL


def test_detects_duplicate_timestamps():
    ts = datetime(2023, 6, 1, 12, 0, 0)
    a = _bare(file_path="/tmp/a.jpg", has_exif=True,
              camera_make="C", camera_model="M", datetime_original=ts)
    b = _bare(file_path="/tmp/b.jpg", has_exif=True,
              camera_make="C", camera_model="M", datetime_original=ts)
    findings = AnomalyDetector().detect_for_collection([a, b])
    codes = [f.code for f in findings]
    assert "DUPLICATE_TIMESTAMP" in codes


def test_anomaly_to_dict_round_trip():
    d = _bare(has_exif=False)
    findings = AnomalyDetector().detect_for_image(d)
    assert findings
    payload = findings[0].to_dict()
    assert payload["code"] == "EXIF_STRIPPED"
    assert payload["severity"] in {"info", "low", "medium", "high", "critical"}
