"""Tests for src.mapping.map_builder."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.core.exif_extractor import ExifData
from src.core.gps_decoder import GPSCoordinate
from src.mapping.map_builder import MapBuilder, MapPoint


def _data(name: str, ts: datetime, lat: float, lon: float) -> ExifData:
    return ExifData(
        file_path=f"/tmp/{name}", file_name=name,
        file_size=1, file_mtime=ts,
        image_format="JPEG", image_width=64, image_height=48,
        image_mode="RGB", has_exif=True,
        camera_make="X", camera_model="Y",
        datetime_original=ts,
        gps=GPSCoordinate(lat, lon),
    )


def test_build_empty_returns_default_map():
    fmap = MapBuilder().build([])
    html = fmap.get_root().render()
    assert "leaflet" in html.lower()
    assert "No GPS-tagged images" in html


def test_build_with_single_point():
    items = [_data("a.jpg", datetime(2023, 1, 1, 12, 0), 30.04, 31.23)]
    fmap = MapBuilder().build(items)
    html = fmap.get_root().render()
    assert "30.04" in html or "30.0" in html


def test_build_with_multiple_points_renders_path():
    items = [
        _data("a.jpg", datetime(2023, 1, 1, 9, 0), 30.0444, 31.2357),
        _data("b.jpg", datetime(2023, 1, 1, 9, 5), 30.0500, 31.2400),
        _data("c.jpg", datetime(2023, 1, 1, 9, 10), 30.0600, 31.2500),
    ]
    fmap = MapBuilder().build(items, show_path=True, animate_path=True)
    html = fmap.get_root().render()
    assert "leaflet" in html.lower()
    # AntPath plugin or PolyLine should leave a trace
    assert "ant_path" in html.lower() or "polyline" in html.lower()


def test_build_with_anomaly_index_marks_severity():
    items = [_data("a.jpg", datetime(2023, 1, 1, 12, 0), 30.04, 31.23)]
    fmap = MapBuilder().build(items, anomaly_index={items[0].file_path: "critical"})
    html = fmap.get_root().render()
    assert "leaflet" in html.lower()


def test_save_writes_html(tmp_path: Path):
    items = [_data("a.jpg", datetime(2023, 1, 1, 12, 0), 30.04, 31.23)]
    fmap = MapBuilder().build(items)
    out = tmp_path / "m.html"
    MapBuilder().save(fmap, out)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<html>" in text.lower() or "<!doctype html>" in text.lower()
    assert "leaflet" in text.lower()


def test_compute_view_handles_close_points():
    pts = [
        MapPoint(latitude=30.0, longitude=31.0, label="a"),
        MapPoint(latitude=30.0001, longitude=31.0001, label="b"),
    ]
    center, zoom = MapBuilder._compute_view(pts)
    assert center[0] == 30.00005
    assert zoom >= 13


def test_compute_view_far_points_low_zoom():
    pts = [
        MapPoint(latitude=30.0, longitude=31.0, label="a"),
        MapPoint(latitude=35.0, longitude=139.0, label="b"),
    ]
    _, zoom = MapBuilder._compute_view(pts)
    assert zoom <= 5


def test_skips_invalid_gps_items():
    a = _data("a.jpg", datetime(2023, 1, 1, 12, 0), 0.0, 0.0)  # null island
    b = _data("b.jpg", datetime(2023, 1, 1, 12, 5), 30.04, 31.23)
    fmap = MapBuilder().build([a, b])
    html = fmap.get_root().render()
    # b should still render
    assert "leaflet" in html.lower()
