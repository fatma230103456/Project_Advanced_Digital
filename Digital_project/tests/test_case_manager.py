"""Tests for src.db.case_manager."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.anomaly_detector import Anomaly, AnomalySeverity
from src.db.case_manager import CaseManager


@pytest.fixture
def manager(tmp_path: Path) -> CaseManager:
    return CaseManager(tmp_path / "test.db")


def test_create_and_list_cases(manager: CaseManager):
    case = manager.create_case("Op Falcon", "field test", "agent007")
    assert case.id is not None
    assert case.name == "Op Falcon"
    assert case.investigator == "agent007"
    assert case.created_at is not None

    cases = manager.list_cases()
    assert len(cases) == 1
    assert cases[0].id == case.id


def test_get_case_returns_none_when_missing(manager: CaseManager):
    assert manager.get_case(9999) is None


def test_update_case(manager: CaseManager):
    case = manager.create_case("Old name")
    manager.update_case(case.id, name="New name", investigator="alice")
    fresh = manager.get_case(case.id)
    assert fresh.name == "New name"
    assert fresh.investigator == "alice"


def test_delete_case_cascades_evidence(manager: CaseManager):
    case = manager.create_case("Case A")
    manager.add_evidence(
        case.id, file_path="/tmp/a.jpg", file_name="a.jpg",
        sha256="a" * 64, md5="b" * 32, sha1="c" * 40,
        file_size=10, has_exif=True,
    )
    assert len(manager.list_evidence(case.id)) == 1
    manager.delete_case(case.id)
    assert manager.get_case(case.id) is None
    assert manager.list_evidence(case.id) == []


def test_add_evidence_dedups_on_sha256(manager: CaseManager):
    case = manager.create_case("Case")
    eid_1 = manager.add_evidence(
        case.id, file_path="/old/path.jpg", file_name="path.jpg",
        sha256="z" * 64, has_exif=True,
    )
    eid_2 = manager.add_evidence(
        case.id, file_path="/new/path.jpg", file_name="path.jpg",
        sha256="z" * 64, has_exif=True,
    )
    assert eid_1 == eid_2
    assert len(manager.list_evidence(case.id)) == 1
    rec = manager.list_evidence(case.id)[0]
    assert rec.file_path == "/new/path.jpg"


def test_evidence_round_trip(manager: CaseManager):
    case = manager.create_case("C")
    manager.add_evidence(
        case.id,
        file_path="/p/img.jpg", file_name="img.jpg",
        sha256="d" * 64, md5="e" * 32, sha1="f" * 40,
        file_size=2048, image_format="JPEG", width=4000, height=3000,
        camera_make="Canon", camera_model="EOS", software="Canon FW",
        datetime_original="2023-06-15T12:30:00",
        latitude=30.04, longitude=31.23, altitude=20.0,
        has_exif=True, exif_dict={"raw_tag_count": 12, "iso": 400},
    )
    rec = manager.list_evidence(case.id)[0]
    assert rec.file_name == "img.jpg"
    assert rec.camera_model == "EOS"
    assert rec.has_exif is True
    assert rec.latitude == pytest.approx(30.04)
    assert rec.exif_dict["iso"] == 400


def test_add_anomalies_persists_and_lists(manager: CaseManager):
    case = manager.create_case("C")
    eid = manager.add_evidence(
        case.id, file_path="/p/img.jpg", file_name="img.jpg",
        sha256="x" * 64, has_exif=False,
    )
    anomaly = Anomaly(
        code="EXIF_STRIPPED", severity=AnomalySeverity.MEDIUM,
        title="EXIF missing", description="...",
        file_path="/p/img.jpg",
    )
    manager.add_anomalies(case.id, eid, [anomaly])
    rows = manager.list_anomalies(case.id)
    assert len(rows) == 1
    assert rows[0]["code"] == "EXIF_STRIPPED"
    assert rows[0]["severity"] == "medium"
    assert rows[0]["evidence_id"] == eid


def test_clear_anomalies(manager: CaseManager):
    case = manager.create_case("C")
    a = Anomaly(code="X", severity=AnomalySeverity.LOW, title="t", description="d")
    manager.add_anomalies(case.id, None, [a])
    assert len(manager.list_anomalies(case.id)) == 1
    manager.clear_anomalies(case.id)
    assert manager.list_anomalies(case.id) == []


def test_audit_log_records_actions(manager: CaseManager):
    case = manager.create_case("Op X", investigator="ana")
    manager.log_action(case.id, "ana", "report_generated",
                       target="report.pdf", payload={"path": "/tmp/r.pdf"})
    audit = manager.list_audit(case.id)
    actions = [row["action"] for row in audit]
    assert "case_created" in actions
    assert "report_generated" in actions
    rep = next(r for r in audit if r["action"] == "report_generated")
    assert rep["payload"]["path"] == "/tmp/r.pdf"
