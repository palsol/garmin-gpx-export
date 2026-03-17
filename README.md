# garmin-gpx-export

Lightweight console tool to export GPS tracks from a Garmin watch (via USB) into merged GPX files for geotagging photos in Lightroom.

## Why

Garmin BaseCamp works for merging and exporting tracks, but the UI is clunky for a simple recurring task: grab new tracks from the watch and save them as a single GPX file. This script does exactly that from the command line.

## Features

- Auto-detects Garmin device connected via USB
- Reads `.FIT` activity files directly from the watch (`GARMIN/Activity/` and `GARMIN/Activity/Archive/`)
- Converts FIT to GPX and merges all new tracks into a single dated file
- Tracks export history with statistics — never exports the same activity twice
- Skips activities without GPS data (strength training, indoor workouts, etc.)
- Backfill support for existing GPX files exported from BaseCamp

## Requirements

- Python 3.10+
- Garmin watch connected via USB (tested with Fenix 6X)

## Installation

```bash
git clone https://github.com/palsol/garmin-gpx-export.git
cd garmin-gpx-export
pip install -r requirements.txt
```

Dependencies: `fitdecode`, `gpxpy`

## Usage

### Export new tracks

Connect your Garmin watch via USB, then:

```bash
python garmin_export.py export
```

The script will:
1. Auto-detect the Garmin drive (or specify with `--drive E:\`)
2. Find all `.FIT` files not yet exported
3. Parse each file, extract GPS trackpoints, skip non-GPS activities
4. Show a summary table and ask for confirmation
5. Merge all tracks into a single `YYYY-MM-DD.gpx` file
6. Save to the output directory and update export history

Example output:

```
Found Garmin device at E:\
Found 14 new FIT file(s). Parsing...

    #  Date               Type          Distance    Duration    Points
  ---  -----------------  ------------  ----------  ----------  --------
    1  2026-01-15 14:30   walking          5.2 km      62 min      3720
    2  2026-01-18 07:15   running          8.1 km      45 min      2700
    3  2026-01-20 10:00   hiking          12.3 km     180 min      5400
  ...

Export 14 activities? [Y/n]: y

Saved: \\10.0.0.1\Foto\Geo_info\2026-03-17.gpx
  14 tracks, 45,230 trackpoints, 87.4 km total
Ready for Lightroom geotagging!
```

### Show statistics

```bash
python garmin_export.py stats
```

```
Export History Summary
========================================
  Total exports:      28
  Total activities:   294
  Total distance:     5,551.2 km
  Total trackpoints:  480,171
  Date range:         2025-02-18 to 2026-01-12

  Date          File                       Activities    Distance
  ------------  -------------------------  ----------  ----------
  2025-09-23    2025-09-23.gpx                     14    454.9 km
  2025-11-16    2025-11-16.gpx                     19    270.0 km
  2026-01-03    2026-01-03.gpx                     11    410.4 km
  2026-01-12    2026-01-12.gpx                      3    290.4 km
```

### View export history

```bash
# List all exports
python garmin_export.py history

# Show details for a specific export
python garmin_export.py history 2026-01-12
```

### Backfill from existing GPX files

If you have GPX files previously exported from BaseCamp, import them into the history:

```bash
python garmin_export.py backfill
```

This parses each GPX file to extract track count, distance, duration, and trackpoint count. Files named `YYYY-MM-DD.gpx` use the filename as the export date; others use the file modification time.

## Options

| Flag | Description |
|---|---|
| `--output`, `-o` | Output directory for GPX files (default: `\\10.0.0.1\Foto\Geo_info`) |
| `--drive`, `-d` | Garmin device drive letter (e.g., `E:\`). Auto-detected if not specified |

## How it works

### FIT file reading

Garmin watches record activities in `.FIT` (Flexible and Interoperable Data Transfer) format. The script reads these files using `fitdecode`, extracting:

- GPS coordinates (converted from Garmin's semicircle format to degrees)
- Elevation
- Timestamps
- Activity type, distance, and duration from the session record

### Deduplication

The script tracks every exported FIT filename in `export_history.json`. On each run, it compares files on the watch against this list and only processes new ones.

### GPX output

All tracks are merged into a single GPX 1.1 file with one `<trk>` element per activity. Each track is named with its start timestamp and activity type. The output is compatible with Lightroom's Map module for auto-geotagging photos based on timestamp matching.

### Garmin device folder structure

```
[Drive]:\
  GARMIN\
    Activity\          <- Completed activity .FIT files
      Archive\         <- Older auto-archived activities
```

## Lightroom geotagging workflow

1. Connect Garmin watch, run `python garmin_export.py export`
2. In Lightroom, go to Map module
3. Load the exported GPX tracklog via the GPS Tracklogs panel
4. Select photos, right-click > "Auto-Tag Photos"
5. Lightroom matches photo timestamps to GPS positions

Make sure your camera clock is reasonably synced with GPS time. Lightroom handles UTC conversion from the GPX timestamps automatically.

## License

MIT
