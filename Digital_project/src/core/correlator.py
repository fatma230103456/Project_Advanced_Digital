"""Correlate evidence images by time and location."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .exif_extractor import ExifData
from .gps_decoder import GPSCoordinate, GPSDecoder


@dataclass
class TimelineEntry:
    timestamp: datetime
    file_path: str
    file_name: str
    gps: Optional[GPSCoordinate]
    camera: Optional[str]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "file_name": self.file_name,
            "gps": self.gps.to_dict() if self.gps else None,
            "camera": self.camera,
        }


def _best_timestamp(d: ExifData) -> Optional[datetime]:
    """Choose the most authoritative timestamp available."""
    return d.datetime_original or d.datetime_digitized or d.datetime_modified or d.file_mtime


def build_timeline(items: Iterable[ExifData]) -> list[TimelineEntry]:
    """Return chronologically-sorted timeline entries (earliest first)."""
    entries: list[TimelineEntry] = []
    for d in items:
        ts = _best_timestamp(d)
        if ts is None:
            continue
        camera = None
        if d.camera_make or d.camera_model:
            camera = " ".join(filter(None, [d.camera_make, d.camera_model]))
        entries.append(TimelineEntry(
            timestamp=ts,
            file_path=d.file_path,
            file_name=d.file_name,
            gps=d.gps if d.gps and d.gps.is_valid() else None,
            camera=camera,
        ))
    entries.sort(key=lambda e: e.timestamp)
    return entries


def correlate_by_time(
    items: Iterable[ExifData],
    window: timedelta = timedelta(minutes=5),
) -> list[list[ExifData]]:
    """Group images that were captured within the given time window of each other."""
    sorted_items = sorted(
        (d for d in items if _best_timestamp(d) is not None),
        key=_best_timestamp,
    )
    clusters: list[list[ExifData]] = []
    current: list[ExifData] = []
    last_ts: Optional[datetime] = None
    for d in sorted_items:
        ts = _best_timestamp(d)
        if last_ts is None or (ts - last_ts) <= window:
            current.append(d)
        else:
            if current:
                clusters.append(current)
            current = [d]
        last_ts = ts
    if current:
        clusters.append(current)
    return clusters


def correlate_by_location(
    items: Iterable[ExifData],
    radius_km: float = 0.5,
) -> list[list[ExifData]]:
    """Group images whose GPS coordinates are within `radius_km` of each other."""
    with_gps = [d for d in items if d.gps and d.gps.is_valid()]
    used: set[int] = set()
    clusters: list[list[ExifData]] = []
    for i, d in enumerate(with_gps):
        if i in used:
            continue
        cluster = [d]
        used.add(i)
        for j in range(i + 1, len(with_gps)):
            if j in used:
                continue
            if GPSDecoder.haversine_km(d.gps, with_gps[j].gps) <= radius_km:
                cluster.append(with_gps[j])
                used.add(j)
        clusters.append(cluster)
    return clusters


def reverse_geocode(
    coord: GPSCoordinate,
    user_agent: str = "digital-image-forensics/1.0",
    timeout: float = 5.0,
) -> Optional[str]:
    """Best-effort reverse geocoding via Nominatim. Returns None on failure/offline."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderUnavailable, GeocoderTimedOut
    except ImportError:
        return None
    try:
        geocoder = Nominatim(user_agent=user_agent, timeout=timeout)
        location = geocoder.reverse((coord.latitude, coord.longitude), language="en", zoom=14)
        return location.address if location else None
    except (GeocoderUnavailable, GeocoderTimedOut, Exception):
        return None
