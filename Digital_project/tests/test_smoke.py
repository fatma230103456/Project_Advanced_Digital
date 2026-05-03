"""End-to-end smoke test exercising ingest -> persist -> report."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.core.anomaly_detector import AnomalyDetector
from src.core.exif_extractor import ExifExtractor
from src.core.hasher import compute_hashes
from src.db.case_manager import CaseManager
from src.mapping.map_builder import MapBuilder
from src.reporting.pdf_report import ForensicReport, ReportContext

from .conftest import make_jpeg


def test_full_pipeline(tmp_path: Path):
    images_dir = tmp_path / "evidence"
    images_dir.mkdir()

    a = make_jpeg(
        images_dir / "scene_1.jpg",
        make="Canon", model="EOS 80D", software="Canon FW 1.0",
        datetime_original=datetime(2023, 6, 15, 12, 0, 0),
        latitude=30.0444, longitude=31.2357, altitude=15.0,
    )
    b = make_jpeg(
        images_dir / "scene_2.jpg",
        make="Canon", model="EOS 80D",
        datetime_original=datetime(2023, 6, 15, 12, 30, 0),
        latitude=30.0500, longitude=31.2400,
    )
    c = make_jpeg(
        images_dir / "tampered.jpg",
        make="Apple", model="iPhone 13",
        software="Adobe Photoshop 24.0",
        datetime_original=datetime(2023, 6, 15, 13, 0, 0),
    )
    d = make_jpeg(images_dir / "stripped.jpg", include_exif=False)

    extractor = ExifExtractor()
    detector = AnomalyDetector()
    manager = CaseManager(tmp_path / "forensics.db")

    case = manager.create_case(
        "Smoke Test Case",
        "End-to-end pipeline verification",
        "ci-bot",
    )

    items = []
    all_anomalies = []
    for path in (a, b, c, d):
        hashes = compute_hashes(path)
        data = extractor.extract(path)
        anomalies = detector.detect_for_image(data)
        ev_id = manager.add_evidence(
            case.id,
            file_path=data.file_path, file_name=data.file_name,
            sha256=hashes.sha256, md5=hashes.md5, sha1=hashes.sha1,
            file_size=hashes.size,
            image_format=data.image_format,
            width=data.image_width, height=data.image_height,
            camera_make=data.camera_make, camera_model=data.camera_model,
            software=data.software,
            datetime_original=data.datetime_original.isoformat() if data.datetime_original else None,
            latitude=data.gps.latitude if data.gps else None,
            longitude=data.gps.longitude if data.gps else None,
            has_exif=data.has_exif,
            exif_dict=data.to_dict(),
        )
        if anomalies:
            manager.add_anomalies(case.id, ev_id, anomalies)
        items.append(data)
        all_anomalies.extend(anomalies)

    collection_findings = detector.detect_for_collection(items)
    if collection_findings:
        manager.add_anomalies(case.id, None, collection_findings)
        all_anomalies.extend(collection_findings)

    # DB integrity
    persisted = manager.list_evidence(case.id)
    assert len(persisted) == 4
    persisted_codes = {row["code"] for row in manager.list_anomalies(case.id)}
    assert "EXIF_STRIPPED" in persisted_codes
    assert "EDITING_SOFTWARE" in persisted_codes

    # Map builds without errors
    fmap = MapBuilder().build(items)
    map_html = tmp_path / "map.html"
    MapBuilder().save(fmap, map_html)
    assert map_html.exists() and map_html.stat().st_size > 1000

    # PDF report
    pdf_out = tmp_path / "report.pdf"
    audit = manager.list_audit(case.id)
    ctx = ReportContext(
        case_name=case.name, case_description=case.description,
        investigator=case.investigator, case_id=case.id,
        items=items, anomalies=all_anomalies, audit_log=audit,
    )
    ForensicReport().generate(ctx, pdf_out)
    assert pdf_out.exists()
    assert pdf_out.read_bytes().startswith(b"%PDF-")
    manager.log_action(case.id, case.investigator, "report_generated",
                       target=pdf_out.name)

    final_audit = manager.list_audit(case.id)
    actions = {row["action"] for row in final_audit}
    assert {"case_created", "evidence_added", "report_generated"} <= actions
