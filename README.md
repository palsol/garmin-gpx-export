# garmin-gpx-export

Lightweight console tool to export GPS tracks from a Garmin watch (via USB) into merged GPX files for geotagging photos in Lightroom.

## Features

- Auto-detects Garmin device connected via USB
- Reads .FIT activity files directly from the watch
- Converts and merges tracks into a single dated GPX file
- Tracks export history with statistics
- Skips activities without GPS data

## Requirements

- Python 3.10+
- Garmin watch connected via USB (tested with Fenix 6X)

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Export new tracks from connected Garmin device
python garmin_export.py export

# Show export statistics
python garmin_export.py stats

# List past exports
python garmin_export.py history

# Show details of a specific export
python garmin_export.py history 2026-03-17

# Backfill history from existing GPX files
python garmin_export.py backfill
```
