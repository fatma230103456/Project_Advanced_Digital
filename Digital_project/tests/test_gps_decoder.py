"""Tests for src.core.gps_decoder."""
from __future__ import annotations

from src.core.gps_decoder import GPSCoordinate, GPSDecoder


class _FakeIFDTag:
    def __init__(self, values):
        self.values = values


class _Ratio:
    def __init__(self, num, den):
        self.num = num
        self.den = den

    def __repr__(self):
        return f"{self.num}/{self.den}"


def test_gpscoordinate_validity_bounds():
    assert GPSCoordinate(0.0001, 0.0001).is_valid()
    assert not GPSCoordinate(91.0, 0.0).is_valid()
    assert not GPSCoordinate(0.0, 181.0).is_valid()
    assert not GPSCoordinate(-91.0, 0.0).is_valid()
    assert not GPSCoordinate(0.0, 0.0).is_valid()  # null island


def test_gpscoordinate_to_dict():
    c = GPSCoordinate(10.5, -20.25, altitude=100.0, altitude_ref=0)
    d = c.to_dict()
    assert d["latitude"] == 10.5
    assert d["longitude"] == -20.25
    assert d["altitude"] == 100.0


def test_to_float_handles_various_types():
    assert GPSDecoder._to_float(None) is None
    assert GPSDecoder._to_float(3) == 3.0
    assert GPSDecoder._to_float(3.5) == 3.5
    assert GPSDecoder._to_float(_Ratio(10, 4)) == 2.5
    assert GPSDecoder._to_float((7, 2)) == 3.5
    assert GPSDecoder._to_float("not a number") is None
    # division by zero den should yield 0.0, not raise
    assert GPSDecoder._to_float(_Ratio(10, 0)) == 0.0


def test_dms_to_decimal_north_east():
    dms = _FakeIFDTag([_Ratio(30, 1), _Ratio(2, 1), _Ratio(40, 1)])
    decimal = GPSDecoder._dms_to_decimal(dms, "N")
    expected = 30 + 2 / 60 + 40 / 3600
    assert abs(decimal - expected) < 1e-6


def test_dms_to_decimal_south_west_negates():
    dms = _FakeIFDTag([_Ratio(45, 1), _Ratio(0, 1), _Ratio(0, 1)])
    assert GPSDecoder._dms_to_decimal(dms, "S") == -45.0
    assert GPSDecoder._dms_to_decimal(dms, "W") == -45.0


def test_from_exifread_tags_full():
    tags = {
        "GPS GPSLatitude": _FakeIFDTag([_Ratio(30, 1), _Ratio(2, 1), _Ratio(40, 1)]),
        "GPS GPSLatitudeRef": "N",
        "GPS GPSLongitude": _FakeIFDTag([_Ratio(31, 1), _Ratio(14, 1), _Ratio(8, 1)]),
        "GPS GPSLongitudeRef": "E",
        "GPS GPSAltitude": _FakeIFDTag([_Ratio(100, 1)]),
        "GPS GPSAltitudeRef": _FakeIFDTag([0]),
        "GPS GPSMapDatum": "WGS-84",
    }
    coord = GPSDecoder.from_exifread_tags(tags)
    assert coord is not None
    assert coord.is_valid()
    assert abs(coord.latitude - (30 + 2 / 60 + 40 / 3600)) < 1e-6
    assert coord.altitude == 100.0
    assert coord.map_datum == "WGS-84"


def test_from_exifread_tags_missing_returns_none():
    assert GPSDecoder.from_exifread_tags({}) is None


def test_from_exifread_tags_below_sea_level_negates_altitude():
    tags = {
        "GPS GPSLatitude": _FakeIFDTag([_Ratio(10, 1), _Ratio(0, 1), _Ratio(0, 1)]),
        "GPS GPSLatitudeRef": "N",
        "GPS GPSLongitude": _FakeIFDTag([_Ratio(20, 1), _Ratio(0, 1), _Ratio(0, 1)]),
        "GPS GPSLongitudeRef": "E",
        "GPS GPSAltitude": _FakeIFDTag([_Ratio(50, 1)]),
        "GPS GPSAltitudeRef": _FakeIFDTag([1]),
    }
    coord = GPSDecoder.from_exifread_tags(tags)
    assert coord is not None
    assert coord.altitude == -50.0
    assert coord.altitude_ref == 1


def test_haversine_known_distance():
    cairo = GPSCoordinate(30.0444, 31.2357)
    tokyo = GPSCoordinate(35.6895, 139.6917)
    dist = GPSDecoder.haversine_km(cairo, tokyo)
    # known great-circle distance ~ 9580 km, allow tolerance
    assert 9000 < dist < 10100


def test_haversine_zero_distance():
    p = GPSCoordinate(10.0, 20.0)
    assert GPSDecoder.haversine_km(p, p) == 0.0
