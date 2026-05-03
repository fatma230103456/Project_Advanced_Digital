# Digital Image Forensics — Metadata Extraction & Geolocation Analysis

A desktop forensic tool that extracts EXIF metadata from digital images, decodes
GPS coordinates, visualises locations on an interactive map, detects signs of
metadata tampering, and produces court-ready PDF reports with a verifiable
chain-of-custody.

> Built with **Python 3.12 · PyQt5 · Pillow · exifread · folium · ReportLab**.

---

## Market Problem

Digital images carry hidden metadata (EXIF) that reveals camera identity,
capture time, software signatures, and GPS coordinates. Investigators need a
structured way to **extract, verify, correlate, and report** this evidence
while keeping a tamper-evident chain of custody.

## Solution

This tool ingests batches of images and provides:

1. Deep EXIF extraction across all common formats.
2. GPS decoding with validity checks and inter-image distance/speed analysis.
3. An interactive Leaflet map with timeline, polyline trail, and severity-coded
   markers.
4. An anomaly engine flagging stripped EXIF, editing software, timestamp
   contradictions, impossible travel, and more.
5. A signed PDF forensic report with hashes, audit log, and embedded findings.

---

## Key Features

| # | Requirement | Implementation |
|---|---|---|
| 1 | EXIF extraction (all formats) | `src/core/exif_extractor.py` — JPEG, PNG, TIFF, HEIC/HEIF, WebP, BMP |
| 2 | GPS decoding & verification | `src/core/gps_decoder.py` — DMS→decimal, range checks, haversine distance |
| 3 | Interactive map + timeline | `src/mapping/map_builder.py` + `src/core/correlator.py` — Folium markers, AntPath, HeatMap, MarkerCluster |
| 4 | Anomaly detection | `src/core/anomaly_detector.py` — 11 detector rules across single image and collection scope |
| 5 | Forensic report + chain-of-custody | `src/reporting/pdf_report.py` + `src/db/case_manager.py` — MD5/SHA-1/SHA-256 hashes, ReportLab PDF, SQLite audit log |

### Detected Anomalies

- `EXIF_STRIPPED`, `EDITING_SOFTWARE`
- `TS_ORIG_DIGI_MISMATCH`, `TS_FILE_BEFORE_ORIG`, `TS_MOD_BEFORE_ORIG`, `TS_FUTURE`
- `GPS_NO_CAMERA`, `GPS_INVALID`, `THUMBNAIL_RATIO_MISMATCH`
- `IMPOSSIBLE_TRAVEL`, `DUPLICATE_TIMESTAMP`

---

## Project Structure

```
Digital_project/
├── main.py                       # Application entry point
├── generate_samples.py           # Generates 10 synthetic test images
├── requirements.txt
├── README.md
├── src/
│   ├── core/                     # EXIF, GPS, hasher, correlator, anomaly engine
│   ├── db/                       # SQLite case manager (cases, evidence, anomalies, audit)
│   ├── mapping/                  # Folium map builder
│   ├── reporting/                # ReportLab PDF generator
│   ├── gui/                      # PyQt5 main window + widgets + background workers
│   └── utils/                    # Constants
├── tests/                        # 61 pytest unit + integration tests
├── samples/                      # Generated synthetic images (after running script)
└── data/                         # Runtime SQLite database
```

---

## Installation

### Prerequisites

- Python 3.10 or higher (tested on 3.12.6)
- Windows, macOS, or Linux desktop environment

### Setup

```bash
# Clone the repository
git clone https://github.com/<your-user>/Digital_project.git
cd Digital_project

# Create and activate a virtual environment
python -m venv venv
# Windows PowerShell
venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Launch the GUI

```bash
python main.py
```

### Quick walkthrough

1. **File → New Case** — create a case (name, description, investigator).
2. **Evidence → Add Directory…** — select a folder of images. The background
   ingestor hashes each file, extracts EXIF, runs anomaly checks, and stores
   everything in the case database.
3. **Evidence tab** — browse the file list; click a row to see all EXIF tags,
   thumbnails, and per-file findings.
4. **Map tab** — visualise GPS-tagged images, timeline polyline, and severity
   markers.
5. **Timeline tab** — chronological view of all evidence.
6. **Anomalies tab** — sortable list of all detected issues per case.
7. **Report → Generate PDF Report…** — produces a signed PDF with hashes,
   evidence summary, anomalies, and audit log.

### Generate sample images for testing

```bash
python generate_samples.py
```

This creates 10 JPEGs in `samples/` covering every detector rule (clean shots,
Photoshop signature, stripped EXIF, null-island GPS, future date, impossible
travel, duplicate timestamp, etc.).

---

## Testing

```bash
pytest tests -v
```

Runs **61 tests** across all modules (extractor, GPS, anomalies, hasher,
correlator, map builder, case manager, PDF report, and an end-to-end smoke
test).

---

## License

This project is released for academic and educational use.

## Author

Developed as part of a Digital Forensics coursework project.
