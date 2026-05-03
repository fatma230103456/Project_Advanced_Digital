"""Tests for src.core.correlator."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.core.correlator import (
    build_timeline, correlate_by_time, correlate_by_location,
)
from src.core.exif_extractor import ExifData
from src.core.gps_decoder import GPSCoordinate


def _data(name: str, ts: datetime, gps=None, make="X", model="Y") -> ExifData:
    return ExifData(
        file_path=f"/tmp/{name}", file_name=name,
        file_size=1, file_mtime=ts,
        image_format="JPEG", image_width=64, image_height=48,
        image_mode="RGB", has_exif=True,
        camera_make=make, camera_model=model,
        datetime_original=ts, gps=gps,
    )


def test_build_timeline_sorts_chronologically():
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0))
    b = _data("b.jpg", datetime(2023, 1, 1, 9, 0))
    c = _data("c.jpg", datetime(2023, 1, 1, 15, 0))
    timeline = build_timeline([a, b, c])
    assert [e.file_name for e in timeline] == ["b.jpg", "a.jpg", "c.jpg"]


def test_build_timeline_skips_items_without_timestamp():
    no_ts = ExifData(
        file_path="/tmp/x.jpg", file_name="x.jpg",
        file_size=1, file_mtime=None,
        image_format="JPEG", image_width=10, image_height=10,
        image_mode="RGB",
    )
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0))
    timeline = build_timeline([no_ts, a])
    assert len(timeline) == 1
    assert timeline[0].file_name == "a.jpg"


def test_build_timeline_drops_invalid_gps():
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0),
              gps=GPSCoordinate(0.0, 0.0))
    timeline = build_timeline([a])
    assert timeline[0].gps is None


def test_build_timeline_keeps_valid_gps():
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0),
              gps=GPSCoordinate(30.0, 31.0))
    timeline = build_timeline([a])
    assert timeline[0].gps is not None


def test_correlate_by_time_groups_close_in_time():
    base = datetime(2023, 1, 1, 12, 0)
    a = _data("a.jpg", base)
    b = _data("b.jpg", base + timedelta(seconds=30))
    c = _data("c.jpg", base + timedelta(hours=2))
    clusters = correlate_by_time([a, b, c], window=timedelta(minutes=5))
    assert len(clusters) == 2
    sizes = sorted(len(g) for g in clusters)
    assert sizes == [1, 2]


def test_correlate_by_location_groups_nearby():
    a = _data("a.jpg", datetime(2023, 1, 1), gps=GPSCoordinate(30.000, 31.000))
    b = _data("b.jpg", datetime(2023, 1, 1), gps=GPSCoordinate(30.0001, 31.0001))
    c = _data("c.jpg", datetime(2023, 1, 1), gps=GPSCoordinate(35.0, 139.0))
    clusters = correlate_by_location([a, b, c], radius_km=0.5)
    sizes = sorted(len(g) for g in clusters)
    assert sizes == [1, 2]


def test_correlate_by_location_ignores_invalid():
    a = _data("a.jpg", datetime(2023, 1, 1), gps=GPSCoordinate(0.0, 0.0))
    clusters = correlate_by_location([a])
    assert clusters == []


def test_timeline_entry_to_dict():
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0),
              gps=GPSCoordinate(30.0, 31.0))
    timeline = build_timeline([a])
    d = timeline[0].to_dict()
    assert d["file_name"] == "a.jpg"
    assert d["gps"]["latitude"] == 30.0
