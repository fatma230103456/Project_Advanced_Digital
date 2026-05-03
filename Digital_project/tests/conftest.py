"""Shared test fixtures and synthetic image factories."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import piexif
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _to_dms_rationals(decimal: float):
    decimal = abs(decimal)
    deg = int(decimal)
    min_float = (decimal - deg) * 60
    minutes = int(min_float)
    seconds = round((min_float - minutes) * 60 * 100)
    return ((deg, 1), (minutes, 1), (seconds, 100))


def make_jpeg(
    path: Path,
    *,
    size: tuple[int, int] = (64, 48),
    color: tuple[int, int, int] = (180, 60, 60),
    make: Optional[str] = "TestCam",
    model: Optional[str] = "Model X",
    software: Optional[str] = None,
    datetime_original: Optional[datetime] = None,
    datetime_digitized: Optional[datetime] = None,
    datetime_modified: Optional[datetime] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    altitude: Optional[float] = None,
    artist: Optional[str] = None,
    iso: Optional[int] = None,
    include_exif: bool = True,
) -> Path:
    """Create a JPEG with optional EXIF tags using piexif."""
    img = Image.new("RGB", size, color=color)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not include_exif:
        img.save(str(path), "JPEG", quality=85)
        return path

    zeroth: dict = {}
    exif_ifd: dict = {}
    gps_ifd: dict = {}

    if make:
        zeroth[piexif.ImageIFD.Make] = make.encode()
    if model:
        zeroth[piexif.ImageIFD.Model] = model.encode()
    if software:
        zeroth[piexif.ImageIFD.Software] = software.encode()
    if artist:
        zeroth[piexif.ImageIFD.Artist] = artist.encode()
    if datetime_modified:
        zeroth[piexif.ImageIFD.DateTime] = datetime_modified.strftime("%Y:%m:%d %H:%M:%S").encode()
    if datetime_original:
        exif_ifd[piexif.ExifIFD.DateTimeOriginal] = datetime_original.strftime("%Y:%m:%d %H:%M:%S").encode()
    if datetime_digitized:
        exif_ifd[piexif.ExifIFD.DateTimeDigitized] = datetime_digitized.strftime("%Y:%m:%d %H:%M:%S").encode()
    if iso is not None:
        exif_ifd[piexif.ExifIFD.ISOSpeedRatings] = iso

    if latitude is not None and longitude is not None:
        gps_ifd[piexif.GPSIFD.GPSLatitudeRef] = b"N" if latitude >= 0 else b"S"
        gps_ifd[piexif.GPSIFD.GPSLatitude] = _to_dms_rationals(latitude)
        gps_ifd[piexif.GPSIFD.GPSLongitudeRef] = b"E" if longitude >= 0 else b"W"
        gps_ifd[piexif.GPSIFD.GPSLongitude] = _to_dms_rationals(longitude)
        if altitude is not None:
            gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0 if altitude >= 0 else 1
            gps_ifd[piexif.GPSIFD.GPSAltitude] = (int(abs(altitude) * 100), 100)

    exif_dict = {"0th": zeroth, "Exif": exif_ifd, "GPS": gps_ifd, "1st": {}, "thumbnail": None}
    exif_bytes = piexif.dump(exif_dict)
    img.save(str(path), "JPEG", exif=exif_bytes, quality=85)
    return path


@pytest.fixture
def tmp_image_dir(tmp_path: Path) -> Path:
    d = tmp_path / "images"
    d.mkdir()
    return d


@pytest.fixture
def jpeg_with_gps(tmp_image_dir: Path) -> Path:
    return make_jpeg(
        tmp_image_dir / "with_gps.jpg",
        make="Canon", model="EOS 80D", software="Canon Firmware 1.0",
        datetime_original=datetime(2023, 6, 15, 12, 30, 0),
        datetime_digitized=datetime(2023, 6, 15, 12, 30, 0),
        latitude=30.0444, longitude=31.2357, altitude=25.0,
        iso=400,
    )


@pytest.fixture
def jpeg_no_exif(tmp_image_dir: Path) -> Path:
    return make_jpeg(tmp_image_dir / "stripped.jpg", include_exif=False)


@pytest.fixture
def jpeg_edited(tmp_image_dir: Path) -> Path:
    return make_jpeg(
        tmp_image_dir / "edited.jpg",
        make="Apple", model="iPhone 13",
        software="Adobe Photoshop 24.0",
        datetime_original=datetime(2023, 1, 1, 10, 0, 0),
    )


@pytest.fixture
def jpeg_invalid_gps(tmp_image_dir: Path) -> Path:
    return make_jpeg(
        tmp_image_dir / "null_island.jpg",
        make="Sony", model="A7",
        datetime_original=datetime(2023, 5, 1, 8, 0, 0),
        latitude=0.0, longitude=0.0,
    )


@pytest.fixture
def jpeg_pair_impossible_travel(tmp_image_dir: Path):
    a = make_jpeg(
        tmp_image_dir / "cairo.jpg",
        make="Canon", model="EOS",
        datetime_original=datetime(2023, 7, 1, 9, 0, 0),
        latitude=30.0444, longitude=31.2357,
    )
    b = make_jpeg(
        tmp_image_dir / "tokyo.jpg",
        make="Canon", model="EOS",
        datetime_original=datetime(2023, 7, 1, 9, 30, 0),
        latitude=35.6895, longitude=139.6917,
    )
    return a, b
