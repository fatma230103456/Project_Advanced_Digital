"""EXIF metadata extraction supporting JPEG, PNG, TIFF, HEIC, WebP, BMP."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import exifread
from PIL import Image, ExifTags, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:  # pragma: no cover
    HEIF_SUPPORTED = False

from .gps_decoder import GPSCoordinate, GPSDecoder
from ..utils.constants import DATETIME_FORMATS, SUPPORTED_EXTENSIONS


@dataclass
class ExifData:
    file_path: str
    file_name: str
    file_size: int
    file_mtime: Optional[datetime]
    image_format: Optional[str]
    image_width: Optional[int]
    image_height: Optional[int]
    image_mode: Optional[str]
    has_exif: bool = False
    raw_tags: dict[str, str] = field(default_factory=dict)
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    software: Optional[str] = None
    artist: Optional[str] = None
    copyright: Optional[str] = None
    datetime_original: Optional[datetime] = None
    datetime_digitized: Optional[datetime] = None
    datetime_modified: Optional[datetime] = None
    orientation: Optional[int] = None
    iso: Optional[int] = None
    exposure_time: Optional[str] = None
    f_number: Optional[float] = None
    focal_length: Optional[float] = None
    flash: Optional[str] = None
    gps: Optional[GPSCoordinate] = None
    thumbnail_bytes: Optional[bytes] = None
    extraction_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_mtime": self.file_mtime.isoformat() if self.file_mtime else None,
            "image_format": self.image_format,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "image_mode": self.image_mode,
            "has_exif": self.has_exif,
            "camera_make": self.camera_make,
            "camera_model": self.camera_model,
            "lens_model": self.lens_model,
            "software": self.software,
            "artist": self.artist,
            "copyright": self.copyright,
            "datetime_original": self.datetime_original.isoformat() if self.datetime_original else None,
            "datetime_digitized": self.datetime_digitized.isoformat() if self.datetime_digitized else None,
            "datetime_modified": self.datetime_modified.isoformat() if self.datetime_modified else None,
            "orientation": self.orientation,
            "iso": self.iso,
            "exposure_time": self.exposure_time,
            "f_number": self.f_number,
            "focal_length": self.focal_length,
            "flash": self.flash,
            "gps": self.gps.to_dict() if self.gps else None,
            "raw_tag_count": len(self.raw_tags),
            "extraction_errors": list(self.extraction_errors),
        }
        return d


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.startswith("0000"):
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().strip("\x00").strip()
    return s or None


class ExifExtractor:
    """Extract EXIF metadata from supported image formats."""

    def __init__(self, include_thumbnail: bool = True):
        self.include_thumbnail = include_thumbnail

    @staticmethod
    def is_supported(path: str | os.PathLike) -> bool:
        return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS

    def extract(self, path: str | os.PathLike) -> ExifData:
        p = Path(path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Image not found: {path}")
        stat = p.stat()
        data = ExifData(
            file_path=str(p.resolve()),
            file_name=p.name,
            file_size=stat.st_size,
            file_mtime=datetime.fromtimestamp(stat.st_mtime),
            image_format=None,
            image_width=None,
            image_height=None,
            image_mode=None,
        )
        self._read_image_basics(p, data)
        self._read_with_exifread(p, data)
        self._read_with_pillow(p, data)
        return data

    def _read_image_basics(self, p: Path, data: ExifData) -> None:
        try:
            with Image.open(p) as img:
                data.image_format = img.format
                data.image_width = img.width
                data.image_height = img.height
                data.image_mode = img.mode
        except (UnidentifiedImageError, OSError) as exc:
            data.extraction_errors.append(f"Pillow open failed: {exc}")


    def _read_with_exifread(self, p: Path, data: ExifData) -> None:
        try:
            with open(p, "rb") as fp:
                tags = exifread.process_file(fp, details=True)
        except Exception as exc:
            data.extraction_errors.append(f"exifread failed: {exc}")
            return
        if not tags:
            return
        data.has_exif = True
        for key, value in tags.items():
            if key in ("JPEGThumbnail", "TIFFThumbnail"):
                if self.include_thumbnail and isinstance(value, (bytes, bytearray)) and value:
                    data.thumbnail_bytes = bytes(value)
                continue
            try:
                data.raw_tags[key] = str(value)
            except Exception:
                data.raw_tags[key] = "<unreadable>"
        data.camera_make = _str_or_none(tags.get("Image Make"))
        data.camera_model = _str_or_none(tags.get("Image Model"))
        data.lens_model = _str_or_none(
            tags.get("EXIF LensModel") or tags.get("MakerNote LensType")
        )
        data.software = _str_or_none(tags.get("Image Software"))
        data.artist = _str_or_none(tags.get("Image Artist"))
        data.copyright = _str_or_none(tags.get("Image Copyright"))
        data.datetime_original = _parse_datetime(tags.get("EXIF DateTimeOriginal"))
        data.datetime_digitized = _parse_datetime(tags.get("EXIF DateTimeDigitized"))
        data.datetime_modified = _parse_datetime(tags.get("Image DateTime"))
        try:
            o = tags.get("Image Orientation")
            if o is not None and getattr(o, "values", None):
                data.orientation = int(o.values[0])
        except (TypeError, ValueError, IndexError):
            pass
        try:
            iso = tags.get("EXIF ISOSpeedRatings")
            if iso is not None and getattr(iso, "values", None):
                data.iso = int(iso.values[0])
        except (TypeError, ValueError, IndexError):
            pass
        data.exposure_time = _str_or_none(tags.get("EXIF ExposureTime"))
        f_num = tags.get("EXIF FNumber")
        data.f_number = GPSDecoder._to_float(
            f_num.values[0] if f_num is not None and getattr(f_num, "values", None) else None
        )
        focal = tags.get("EXIF FocalLength")
        data.focal_length = GPSDecoder._to_float(
            focal.values[0] if focal is not None and getattr(focal, "values", None) else None
        )
        data.flash = _str_or_none(tags.get("EXIF Flash"))
        data.gps = GPSDecoder.from_exifread_tags(tags)

    def _read_with_pillow(self, p: Path, data: ExifData) -> None:
        """Fallback for formats exifread does not handle (HEIC, some PNG)."""
        if data.has_exif and data.gps is not None:
            return
        try:
            with Image.open(p) as img:
                exif = img.getexif()
                if not exif:
                    return
                data.has_exif = True
                tag_map = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
                if data.camera_make is None:
                    data.camera_make = _str_or_none(tag_map.get("Make"))
                if data.camera_model is None:
                    data.camera_model = _str_or_none(tag_map.get("Model"))
                if data.software is None:
                    data.software = _str_or_none(tag_map.get("Software"))
                if data.datetime_original is None:
                    data.datetime_original = _parse_datetime(tag_map.get("DateTimeOriginal"))
                if data.datetime_digitized is None:
                    data.datetime_digitized = _parse_datetime(tag_map.get("DateTimeDigitized"))
                if data.datetime_modified is None:
                    data.datetime_modified = _parse_datetime(tag_map.get("DateTime"))
                gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(ExifTags, "IFD") else {}
                if gps_ifd and data.gps is None:
                    data.gps = self._gps_from_pillow(gps_ifd)
                for k, v in tag_map.items():
                    data.raw_tags.setdefault(f"PIL {k}", str(v)[:512])
        except Exception as exc:
            data.extraction_errors.append(f"Pillow EXIF failed: {exc}")

    @staticmethod
    def _gps_from_pillow(gps_ifd: dict) -> Optional[GPSCoordinate]:
        gps_tags = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in gps_ifd.items()}
        lat = gps_tags.get("GPSLatitude")
        lon = gps_tags.get("GPSLongitude")
        lat_ref = gps_tags.get("GPSLatitudeRef")
        lon_ref = gps_tags.get("GPSLongitudeRef")
        if not (lat and lon):
            return None

        def to_decimal(dms, ref):
            try:
                d = float(dms[0]); m = float(dms[1]); s = float(dms[2])
                dec = abs(d) + m / 60.0 + s / 3600.0
                if str(ref).upper() in ("S", "W"):
                    dec = -dec
                return dec
            except (TypeError, ValueError, IndexError, ZeroDivisionError):
                return None

        latd = to_decimal(lat, lat_ref)
        lond = to_decimal(lon, lon_ref)
        if latd is None or lond is None:
            return None
        alt = gps_tags.get("GPSAltitude")
        alt_ref = gps_tags.get("GPSAltitudeRef")
        try:
            alt_f = float(alt) if alt is not None else None
        except (TypeError, ValueError):
            alt_f = None
        try:
            alt_ref_i = int(alt_ref) if alt_ref is not None else None
        except (TypeError, ValueError):
            alt_ref_i = None
        if alt_f is not None and alt_ref_i == 1:
            alt_f = -alt_f
        return GPSCoordinate(
            latitude=latd, longitude=lond,
            altitude=alt_f, altitude_ref=alt_ref_i,
            timestamp=str(gps_tags.get("GPSTimeStamp")) if gps_tags.get("GPSTimeStamp") else None,
            map_datum=_str_or_none(gps_tags.get("GPSMapDatum")),
        )
