"""GPS coordinate decoding from EXIF data."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class GPSCoordinate:
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    altitude_ref: Optional[int] = None  # 0 = above sea level, 1 = below
    timestamp: Optional[str] = None
    map_datum: Optional[str] = None

    def is_valid(self) -> bool:
        if not (-90.0 <= self.latitude <= 90.0):
            return False
        if not (-180.0 <= self.longitude <= 180.0):
            return False
        if self.latitude == 0.0 and self.longitude == 0.0:
            return False  # Null Island - almost always invalid
        return True

    def as_tuple(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)

    def to_dict(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "altitude_ref": self.altitude_ref,
            "timestamp": self.timestamp,
            "map_datum": self.map_datum,
        }


class GPSDecoder:
    """Decodes GPS data from various EXIF representations."""

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Convert exifread Ratio, IFDRational, tuple, or number to float."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        # exifread Ratio / piexif tuples
        num = getattr(value, "num", None)
        den = getattr(value, "den", None)
        if num is not None and den is not None:
            return float(num) / float(den) if den else 0.0
        if isinstance(value, tuple) and len(value) == 2:
            n, d = value
            return float(n) / float(d) if d else 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _dms_to_decimal(cls, dms: Any, ref: Any) -> Optional[float]:
        """Convert Degrees/Minutes/Seconds + reference to decimal degrees."""
        if dms is None:
            return None
        # exifread returns IfdTag with .values list of 3 Ratio
        values = getattr(dms, "values", dms)
        if len(values) < 3:
            return None
        deg = cls._to_float(values[0])
        minutes = cls._to_float(values[1])
        seconds = cls._to_float(values[2])
        if deg is None or minutes is None or seconds is None:
            return None
        decimal = abs(deg) + minutes / 60.0 + seconds / 3600.0
        ref_str = str(ref).strip().upper() if ref is not None else ""
        if ref_str in ("S", "W"):
            decimal = -decimal
        return decimal

    @classmethod
    def from_exifread_tags(cls, tags: dict) -> Optional[GPSCoordinate]:
        """Build a GPSCoordinate from an exifread tags dict."""
        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")
        if not (lat_tag and lon_tag):
            return None
        lat = cls._dms_to_decimal(lat_tag, lat_ref)
        lon = cls._dms_to_decimal(lon_tag, lon_ref)
        if lat is None or lon is None:
            return None
        alt_tag = tags.get("GPS GPSAltitude")
        alt_ref_tag = tags.get("GPS GPSAltitudeRef")
        alt = None
        if alt_tag is not None:
            values = getattr(alt_tag, "values", [alt_tag])
            alt = cls._to_float(values[0]) if values else None
        alt_ref = None
        if alt_ref_tag is not None:
            values = getattr(alt_ref_tag, "values", [alt_ref_tag])
            try:
                alt_ref = int(values[0]) if values else None
            except (TypeError, ValueError):
                alt_ref = None
        if alt is not None and alt_ref == 1:
            alt = -alt
        ts_tag = tags.get("GPS GPSTimeStamp")
        ds_tag = tags.get("GPS GPSDate") or tags.get("GPS GPSDateStamp")
        timestamp = None
        if ts_tag and ds_tag:
            ts_values = getattr(ts_tag, "values", ts_tag)
            try:
                h = int(cls._to_float(ts_values[0]) or 0)
                m = int(cls._to_float(ts_values[1]) or 0)
                s = int(cls._to_float(ts_values[2]) or 0)
                timestamp = f"{ds_tag} {h:02d}:{m:02d}:{s:02d}"
            except (IndexError, TypeError):
                timestamp = str(ds_tag)
        datum_tag = tags.get("GPS GPSMapDatum")
        return GPSCoordinate(
            latitude=lat,
            longitude=lon,
            altitude=alt,
            altitude_ref=alt_ref,
            timestamp=timestamp,
            map_datum=str(datum_tag) if datum_tag else None,
        )

    @staticmethod
    def haversine_km(a: GPSCoordinate, b: GPSCoordinate) -> float:
        """Great-circle distance between two GPS coordinates in kilometers."""
        r = 6371.0088
        lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
        lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * r * math.asin(math.sqrt(h))
