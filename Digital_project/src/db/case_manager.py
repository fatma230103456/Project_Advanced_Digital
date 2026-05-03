"""SQLite-backed case management with full audit trail."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from ..utils.constants import DEFAULT_DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    investigator TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER,
    md5 TEXT,
    sha1 TEXT,
    sha256 TEXT NOT NULL,
    image_format TEXT,
    width INTEGER,
    height INTEGER,
    camera_make TEXT,
    camera_model TEXT,
    software TEXT,
    datetime_original TEXT,
    latitude REAL,
    longitude REAL,
    altitude REAL,
    has_exif INTEGER NOT NULL DEFAULT 0,
    exif_json TEXT,
    added_at TEXT NOT NULL,
    UNIQUE(case_id, sha256)
);

CREATE INDEX IF NOT EXISTS idx_evidence_case ON evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence(sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_dto ON evidence(datetime_original);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_id INTEGER REFERENCES evidence(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    details_json TEXT,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomalies_case ON anomalies(case_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    actor TEXT,
    action TEXT NOT NULL,
    target TEXT,
    payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);
"""


@dataclass
class Case:
    id: Optional[int]
    name: str
    description: str = ""
    investigator: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class EvidenceRecord:
    id: Optional[int]
    case_id: int
    file_path: str
    file_name: str
    sha256: str
    md5: Optional[str] = None
    sha1: Optional[str] = None
    file_size: Optional[int] = None
    image_format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    software: Optional[str] = None
    datetime_original: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    has_exif: bool = False
    exif_dict: dict = field(default_factory=dict)
    added_at: Optional[datetime] = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CaseManager:
    """Persistent forensic case repository (SQLite)."""

    def __init__(self, db_path: str | os.PathLike | None = None):
        path = Path(db_path) if db_path else Path(DEFAULT_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        self._initialize()

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---------- cases ----------

    def create_case(self, name: str, description: str = "", investigator: str = "") -> Case:
        ts = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO cases(name, description, investigator, created_at, updated_at) "
                "VALUES (?,?,?,?,?)",
                (name, description, investigator, ts, ts),
            )
            case_id = cur.lastrowid
            self._log(conn, case_id, "system", "case_created", name,
                      {"investigator": investigator})
        return Case(id=case_id, name=name, description=description,
                    investigator=investigator,
                    created_at=datetime.fromisoformat(ts),
                    updated_at=datetime.fromisoformat(ts))

    def list_cases(self) -> list[Case]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cases ORDER BY datetime(updated_at) DESC"
            ).fetchall()
        return [self._row_to_case(r) for r in rows]

    def get_case(self, case_id: int) -> Optional[Case]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return self._row_to_case(row) if row else None

    def update_case(self, case_id: int, *, name: Optional[str] = None,
                    description: Optional[str] = None,
                    investigator: Optional[str] = None) -> None:
        fields, values = [], []
        for col, val in (("name", name), ("description", description),
                         ("investigator", investigator)):
            if val is not None:
                fields.append(f"{col}=?")
                values.append(val)
        if not fields:
            return
        fields.append("updated_at=?")
        values.append(_now_iso())
        values.append(case_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE cases SET {', '.join(fields)} WHERE id=?", values)
            self._log(conn, case_id, "system", "case_updated", None,
                      {"changed_fields": [f.split("=")[0] for f in fields[:-1]]})

    def delete_case(self, case_id: int) -> None:
        with self._connect() as conn:
            self._log(conn, case_id, "system", "case_deleted", None, {})
            conn.execute("DELETE FROM cases WHERE id=?", (case_id,))

    @staticmethod
    def _row_to_case(row: sqlite3.Row) -> Case:
        return Case(
            id=row["id"], name=row["name"],
            description=row["description"] or "",
            investigator=row["investigator"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    # ---------- evidence ----------

    def add_evidence(self, case_id: int, *, file_path: str, file_name: str,
                     sha256: str, md5: Optional[str] = None,
                     sha1: Optional[str] = None,
                     file_size: Optional[int] = None,
                     image_format: Optional[str] = None,
                     width: Optional[int] = None, height: Optional[int] = None,
                     camera_make: Optional[str] = None,
                     camera_model: Optional[str] = None,
                     software: Optional[str] = None,
                     datetime_original: Optional[str] = None,
                     latitude: Optional[float] = None,
                     longitude: Optional[float] = None,
                     altitude: Optional[float] = None,
                     has_exif: bool = False,
                     exif_dict: Optional[dict] = None) -> int:
        added_at = _now_iso()
        exif_json = json.dumps(exif_dict or {}, default=str)
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO evidence
                (case_id, file_path, file_name, file_size, md5, sha1, sha256,
                 image_format, width, height, camera_make, camera_model, software,
                 datetime_original, latitude, longitude, altitude, has_exif,
                 exif_json, added_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(case_id, sha256) DO UPDATE SET
                    file_path=excluded.file_path,
                    file_name=excluded.file_name,
                    exif_json=excluded.exif_json
                """,
                (case_id, file_path, file_name, file_size, md5, sha1, sha256,
                 image_format, width, height, camera_make, camera_model, software,
                 datetime_original, latitude, longitude, altitude, int(has_exif),
                 exif_json, added_at),
            )
            ev_id = cur.lastrowid
            if not ev_id:
                row = conn.execute(
                    "SELECT id FROM evidence WHERE case_id=? AND sha256=?",
                    (case_id, sha256),
                ).fetchone()
                ev_id = row["id"] if row else None
            conn.execute("UPDATE cases SET updated_at=? WHERE id=?",
                         (added_at, case_id))
            self._log(conn, case_id, "system", "evidence_added", file_name,
                      {"sha256": sha256})
        return ev_id

    def list_evidence(self, case_id: int) -> list[EvidenceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE case_id=? ORDER BY datetime_original NULLS LAST, added_at",
                (case_id,),
            ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    def delete_evidence(self, evidence_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT case_id, file_name FROM evidence WHERE id=?", (evidence_id,)
            ).fetchone()
            conn.execute("DELETE FROM evidence WHERE id=?", (evidence_id,))
            if row:
                self._log(conn, row["case_id"], "system", "evidence_deleted",
                          row["file_name"], {})

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> EvidenceRecord:
        try:
            exif_dict = json.loads(row["exif_json"]) if row["exif_json"] else {}
        except (TypeError, ValueError):
            exif_dict = {}
        return EvidenceRecord(
            id=row["id"], case_id=row["case_id"],
            file_path=row["file_path"], file_name=row["file_name"],
            file_size=row["file_size"], md5=row["md5"], sha1=row["sha1"],
            sha256=row["sha256"], image_format=row["image_format"],
            width=row["width"], height=row["height"],
            camera_make=row["camera_make"], camera_model=row["camera_model"],
            software=row["software"],
            datetime_original=row["datetime_original"],
            latitude=row["latitude"], longitude=row["longitude"],
            altitude=row["altitude"], has_exif=bool(row["has_exif"]),
            exif_dict=exif_dict,
            added_at=datetime.fromisoformat(row["added_at"]) if row["added_at"] else None,
        )

    # ---------- anomalies ----------

    def add_anomalies(self, case_id: int, evidence_id: Optional[int],
                      anomalies: Iterable[Any]) -> None:
        ts = _now_iso()
        with self._connect() as conn:
            for a in anomalies:
                d = a.to_dict() if hasattr(a, "to_dict") else dict(a)
                conn.execute(
                    "INSERT INTO anomalies(case_id, evidence_id, code, severity, "
                    "title, description, details_json, detected_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (case_id, evidence_id, d.get("code"), d.get("severity"),
                     d.get("title"), d.get("description"),
                     json.dumps(d.get("details") or {}, default=str), ts),
                )


    def list_anomalies(self, case_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.*, e.file_name FROM anomalies a "
                "LEFT JOIN evidence e ON e.id = a.evidence_id "
                "WHERE a.case_id=? ORDER BY a.id",
                (case_id,),
            ).fetchall()
        out = []
        for r in rows:
            try:
                details = json.loads(r["details_json"]) if r["details_json"] else {}
            except (TypeError, ValueError):
                details = {}
            out.append({
                "id": r["id"], "case_id": r["case_id"],
                "evidence_id": r["evidence_id"], "file_name": r["file_name"],
                "code": r["code"], "severity": r["severity"],
                "title": r["title"], "description": r["description"],
                "details": details, "detected_at": r["detected_at"],
            })
        return out

    def clear_anomalies(self, case_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM anomalies WHERE case_id=?", (case_id,))

    # ---------- audit log ----------

    def _log(self, conn: sqlite3.Connection, case_id: Optional[int],
             actor: str, action: str, target: Optional[str],
             payload: Optional[dict]) -> None:
        conn.execute(
            "INSERT INTO audit_log(case_id, timestamp, actor, action, target, payload_json) "
            "VALUES (?,?,?,?,?,?)",
            (case_id, _now_iso(), actor, action, target,
             json.dumps(payload or {}, default=str)),
        )

    def log_action(self, case_id: Optional[int], actor: str, action: str,
                   target: Optional[str] = None, payload: Optional[dict] = None) -> None:
        with self._connect() as conn:
            self._log(conn, case_id, actor, action, target, payload)

    def list_audit(self, case_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE case_id=? ORDER BY id",
                (case_id,),
            ).fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
            except (TypeError, ValueError):
                payload = {}
            out.append({
                "id": r["id"], "case_id": r["case_id"],
                "timestamp": r["timestamp"], "actor": r["actor"],
                "action": r["action"], "target": r["target"],
                "payload": payload,
            })
        return out
