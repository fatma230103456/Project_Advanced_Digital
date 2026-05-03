"""Application-wide constants."""
from pathlib import Path

APP_NAME = "Digital Image Forensics"
APP_VERSION = "1.0.0"
ORG_NAME = "DigitalForensics"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CASES_DIR = DATA_DIR / "cases"
DEFAULT_DB_PATH = DATA_DIR / "forensics.db"

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".png",
    ".tif", ".tiff",
    ".heic", ".heif",
    ".webp",
    ".bmp",
}

EDITING_SOFTWARE_KEYWORDS = (
    "photoshop", "adobe", "lightroom", "gimp", "paint.net",
    "pixelmator", "affinity", "snapseed", "facetune",
    "picsart", "vsco", "lightleap", "afterlight",
)

# Speed thresholds for impossible travel (km/h)
MAX_REASONABLE_SPEED_KMH = 900.0  # commercial flight
WARNING_SPEED_KMH = 250.0  # high-speed train

DATETIME_FORMATS = (
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
)
