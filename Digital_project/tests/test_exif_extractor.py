"""Tests for src.core.exif_extractor."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.core.exif_extractor import ExifData, ExifExtractor


def test_is_supported_recognizes_common_extensions():
    assert ExifExtractor.is_supported("photo.jpg")
    assert ExifExtractor.is_supported("photo.JPEG")
    assert ExifExtractor.is_supported("photo.png")
    assert ExifExtractor.is_supported("photo.tif")
    assert ExifExtractor.is_supported("photo.heic")
    assert not ExifExtractor.is_supported("notes.txt")
    assert not ExifExtractor.is_supported("video.mp4")


def test_extract_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ExifExtractor().extract(tmp_path / "nope.jpg")


def test_extract_jpeg_with_full_exif(jpeg_with_gps: Path):
    data = ExifExtractor().extract(jpeg_with_gps)

    assert isinstance(data, ExifData)
    assert data.file_name == jpeg_with_gps.name
    assert data.file_size > 0
    assert data.image_format == "JPEG"
    assert data.image_width == 64
    assert data.image_height == 48
    assert data.has_exif is True
    assert data.camera_make == "Canon"
    assert data.camera_model == "EOS 80D"
    assert data.software is not None and "Canon" in data.software
    assert data.datetime_original == datetime(2023, 6, 15, 12, 30, 0)
    assert data.datetime_digitized == datetime(2023, 6, 15, 12, 30, 0)
    assert data.iso == 400
    assert data.gps is not None
    assert data.gps.is_valid()
    assert abs(data.gps.latitude - 30.0444) < 0.01
    assert abs(data.gps.longitude - 31.2357) < 0.01


def test_extract_jpeg_without_exif(jpeg_no_exif: Path):
    data = ExifExtractor().extract(jpeg_no_exif)
    assert data.has_exif is False
    assert data.camera_make is None
    assert data.camera_model is None
    assert data.gps is None
    assert data.image_format == "JPEG"


def test_extract_jpeg_with_editing_software(jpeg_edited: Path):
    data = ExifExtractor().extract(jpeg_edited)
    assert data.software is not None
    assert "photoshop" in data.software.lower()
    assert data.camera_make == "Apple"


def test_extract_jpeg_with_invalid_gps(jpeg_invalid_gps: Path):
    data = ExifExtractor().extract(jpeg_invalid_gps)
    assert data.gps is not None
    assert not data.gps.is_valid()


def test_to_dict_serializable(jpeg_with_gps: Path):
    import json
    data = ExifExtractor().extract(jpeg_with_gps)
    d = data.to_dict()
    payload = json.dumps(d, default=str)
    assert "JPEG" in payload
    assert d["gps"] is not None
    assert d["has_exif"] is True
    assert d["camera_model"] == "EOS 80D"
