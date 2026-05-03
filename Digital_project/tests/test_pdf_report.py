"""Tests for src.reporting.pdf_report."""
from __future__ import annotations

from pathlib import Path

from src.core.anomaly_detector import AnomalyDetector
from src.core.exif_extractor import ExifExtractor
from src.reporting.pdf_report import ForensicReport, ReportContext


def test_generate_pdf_minimal(tmp_path: Path):
    out = tmp_path / "report.pdf"
    ctx = ReportContext(
        case_name="Empty Case",
        case_description="No items provided.",
        investigator="agent007",
        case_id=1,
    )
    result = ForensicReport().generate(ctx, out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 1000
    head = out.read_bytes()[:5]
    assert head.startswith(b"%PDF-")


def test_generate_pdf_with_evidence(tmp_path: Path, jpeg_with_gps, jpeg_edited, jpeg_no_exif):
    extractor = ExifExtractor()
    detector = AnomalyDetector()
    items = [
        extractor.extract(jpeg_with_gps),
        extractor.extract(jpeg_edited),
        extractor.extract(jpeg_no_exif),
    ]
    anomalies = []
    for d in items:
        anomalies.extend(detector.detect_for_image(d))
    anomalies.extend(detector.detect_for_collection(items))

    out = tmp_path / "full_report.pdf"
    ctx = ReportContext(
        case_name="Investigation 42",
        case_description="Three exhibits collected from the field.",
        investigator="agent.morgan",
        case_id=42,
        items=items,
        anomalies=anomalies,
        audit_log=[
            {
                "id": 1, "case_id": 42,
                "timestamp": "2023-01-01T12:00:00",
                "actor": "agent.morgan", "action": "case_created",
                "target": "Investigation 42", "payload": {},
            }
        ],
    )
    ForensicReport().generate(ctx, out)
    assert out.exists()
    assert out.stat().st_size > 5000
    assert out.read_bytes().startswith(b"%PDF-")


def test_generate_pdf_creates_parent_dirs(tmp_path: Path):
    out = tmp_path / "nested" / "deeper" / "r.pdf"
    ctx = ReportContext(
        case_name="X", case_description="", investigator="",
    )
    ForensicReport().generate(ctx, out)
    assert out.exists()
