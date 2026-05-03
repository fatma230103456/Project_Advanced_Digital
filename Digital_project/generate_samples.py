"""Generate a folder of synthetic JPEG samples that exercise every feature
of the forensic tool: GPS, anomalies, impossible travel, edited images,
stripped EXIF, and a clean baseline.

Run once before launching the app:
    python generate_samples.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tests.conftest import make_jpeg

OUT_DIR = Path(__file__).resolve().parent / "samples"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    # 1) Clean shot near Cairo, Egypt
    make_jpeg(
        OUT_DIR / "01_cairo_clean.jpg",
        make="Canon", model="EOS 80D", software="Canon Firmware 1.0.2",
        datetime_original=datetime(2023, 6, 15, 9, 0, 0),
        datetime_digitized=datetime(2023, 6, 15, 9, 0, 0),
        latitude=30.0444, longitude=31.2357, altitude=25.0,
        artist="Officer Hassan", iso=200,
    )

    # 2) Same camera, 30 minutes later, nearby
    make_jpeg(
        OUT_DIR / "02_cairo_nearby.jpg",
        make="Canon", model="EOS 80D", software="Canon Firmware 1.0.2",
        datetime_original=datetime(2023, 6, 15, 9, 30, 0),
        datetime_digitized=datetime(2023, 6, 15, 9, 30, 0),
        latitude=30.0500, longitude=31.2400, altitude=22.0,
        iso=200,
    )

    # 3) iPhone shot edited in Photoshop -> EDITING_SOFTWARE anomaly
    make_jpeg(
        OUT_DIR / "03_photoshop_edit.jpg",
        make="Apple", model="iPhone 13",
        software="Adobe Photoshop 24.0",
        datetime_original=datetime(2023, 6, 15, 11, 0, 0),
        latitude=30.0470, longitude=31.2380,
    )

    # 4) Stripped EXIF -> EXIF_STRIPPED anomaly
    make_jpeg(
        OUT_DIR / "04_stripped.jpg",
        include_exif=False,
    )

    # 5) Null Island -> INVALID_GPS anomaly
    make_jpeg(
        OUT_DIR / "05_null_island.jpg",
        make="Sony", model="A7",
        datetime_original=datetime(2023, 6, 15, 12, 0, 0),
        latitude=0.0, longitude=0.0,
    )

    # 6) Future timestamp -> FUTURE_TIMESTAMP anomaly
    make_jpeg(
        OUT_DIR / "06_future_date.jpg",
        make="Nikon", model="D850",
        datetime_original=datetime(2099, 1, 1, 12, 0, 0),
        latitude=30.0480, longitude=31.2390,
    )

    # 7) DateTimeOriginal != DateTimeDigitized -> TIMESTAMP_MISMATCH
    make_jpeg(
        OUT_DIR / "07_timestamp_mismatch.jpg",
        make="Fujifilm", model="X-T4",
        datetime_original=datetime(2023, 6, 15, 14, 0, 0),
        datetime_digitized=datetime(2020, 1, 1, 0, 0, 0),
        latitude=30.0490, longitude=31.2410,
    )

    # 8) Cairo -> Tokyo in 30 minutes -> IMPOSSIBLE_TRAVEL
    make_jpeg(
        OUT_DIR / "08_cairo_then_tokyo.jpg",
        make="Canon", model="EOS 80D",
        datetime_original=datetime(2023, 6, 15, 15, 0, 0),
        latitude=35.6895, longitude=139.6917,  # Tokyo
    )

    # 9) GPS without camera info -> GPS_WITHOUT_CAMERA
    make_jpeg(
        OUT_DIR / "09_gps_no_camera.jpg",
        make=None, model=None,
        datetime_original=datetime(2023, 6, 15, 16, 0, 0),
        latitude=30.0510, longitude=31.2420,
    )

    # 10) Duplicate timestamp with #2 -> DUPLICATE_TIMESTAMP
    make_jpeg(
        OUT_DIR / "10_duplicate_time.jpg",
        make="Canon", model="EOS 80D",
        datetime_original=datetime(2023, 6, 15, 9, 30, 0),
        latitude=30.0455, longitude=31.2365,
    )

    print(f"Generated {len(list(OUT_DIR.glob('*.jpg')))} samples in {OUT_DIR}")
    for p in sorted(OUT_DIR.glob("*.jpg")):
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
