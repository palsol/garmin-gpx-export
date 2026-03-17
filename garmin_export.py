#!/usr/bin/env python3
"""
garmin-gpx-export: Export GPS tracks from Garmin watch (USB) into merged GPX files.
"""

import argparse
import json
import os
import string
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitdecode
import gpxpy
import gpxpy.gpx

# FIT semicircles to degrees conversion factor
SEMICIRCLE_TO_DEG = 180.0 / (2**31)

# Default output directory for GPX files
DEFAULT_OUTPUT_DIR = r"\\10.0.0.1\Foto\Geo_info"

# History file location (next to the script)
SCRIPT_DIR = Path(__file__).parent.resolve()
HISTORY_FILE = SCRIPT_DIR / "export_history.json"


def find_garmin_drive():
    """Auto-detect Garmin device drive by scanning Windows drive letters."""
    for letter in string.ascii_uppercase:
        activity_path = Path(f"{letter}:\\GARMIN\\Activity")
        if activity_path.exists():
            return Path(f"{letter}:\\")
    return None


def get_fit_files(garmin_drive):
    """Get all .FIT files from Activity and Activity/Archive folders."""
    activity_dir = garmin_drive / "GARMIN" / "Activity"
    files = list(activity_dir.glob("*.fit")) + list(activity_dir.glob("*.FIT"))

    archive_dir = activity_dir / "Archive"
    if archive_dir.exists():
        files += list(archive_dir.glob("*.fit")) + list(archive_dir.glob("*.FIT"))

    return sorted(files, key=lambda f: f.stat().st_mtime)


def load_history():
    """Load export history from JSON file."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {"exports": []}


def save_history(history):
    """Save export history to JSON file."""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_last_export_date(history):
    """Get the date of the last export from history."""
    if history["exports"]:
        last = history["exports"][-1]["date"]
        return datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


def get_exported_fit_files(history):
    """Get set of all previously exported FIT filenames."""
    exported = set()
    for export in history["exports"]:
        for activity in export.get("activities", []):
            exported.add(activity["fit_file"])
    return exported


def parse_fit_file(fit_path):
    """Parse a FIT file and extract GPS trackpoints and metadata.

    Returns (track_info, gpx_segment) or (None, None) if no GPS data.
    """
    points = []
    activity_type = "unknown"
    start_time = None
    total_distance = None
    total_timer_time = None

    try:
        with fitdecode.FitReader(str(fit_path)) as fit:
            for frame in fit:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue

                if frame.name == "session":
                    sport = frame.get_value("sport")
                    if sport:
                        activity_type = str(sport)
                    dist = frame.get_value("total_distance")
                    if dist is not None:
                        total_distance = dist
                    timer = frame.get_value("total_timer_time")
                    if timer is not None:
                        total_timer_time = timer
                    ts = frame.get_value("start_time")
                    if ts and start_time is None:
                        start_time = ts

                elif frame.name == "record":
                    lat = frame.get_value("position_lat")
                    lon = frame.get_value("position_long")
                    if lat is None or lon is None:
                        continue

                    ele = frame.get_value("enhanced_altitude") or frame.get_value("altitude")
                    ts = frame.get_value("timestamp")

                    if start_time is None and ts:
                        start_time = ts

                    points.append(gpxpy.gpx.GPXTrackPoint(
                        latitude=lat * SEMICIRCLE_TO_DEG,
                        longitude=lon * SEMICIRCLE_TO_DEG,
                        elevation=ele,
                        time=ts,
                    ))
    except Exception as e:
        print(f"  Warning: Could not parse {fit_path.name}: {e}")
        return None, None

    if not points:
        return None, None

    segment = gpxpy.gpx.GPXTrackSegment()
    segment.points = points

    distance_km = round(total_distance / 1000, 2) if total_distance else 0
    duration_min = round(total_timer_time / 60, 1) if total_timer_time else 0

    track_info = {
        "fit_file": fit_path.name,
        "date": start_time.isoformat() if start_time else "",
        "type": activity_type,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "trackpoints": len(points),
    }

    return track_info, segment


def merge_to_gpx(segments_with_info):
    """Merge multiple track segments into a single GPX document."""
    gpx = gpxpy.gpx.GPX()
    gpx.creator = "garmin-gpx-export"

    for info, segment in segments_with_info:
        track = gpxpy.gpx.GPXTrack()
        track.name = f"{info['date']} - {info['type']}"
        track.segments.append(segment)
        gpx.tracks.append(track)

    return gpx


def cmd_export(args):
    """Export new tracks from connected Garmin device."""
    output_dir = Path(args.output)
    if not output_dir.exists():
        print(f"Error: Output directory does not exist: {output_dir}")
        return 1

    # Find Garmin device
    if args.drive:
        garmin_drive = Path(args.drive)
        if not (garmin_drive / "GARMIN" / "Activity").exists():
            print(f"Error: No GARMIN/Activity folder found on {args.drive}")
            return 1
    else:
        print("Searching for Garmin device...")
        garmin_drive = find_garmin_drive()
        if not garmin_drive:
            print("Error: No Garmin device found. Is the watch connected via USB?")
            return 1

    print(f"Found Garmin device at {garmin_drive}")

    # Load history and find new files
    history = load_history()
    exported = get_exported_fit_files(history)
    all_fits = get_fit_files(garmin_drive)

    new_fits = [f for f in all_fits if f.name not in exported]

    if not new_fits:
        print("No new activities to export.")
        return 0

    print(f"Found {len(new_fits)} new FIT file(s). Parsing...\n")

    # Parse all new FIT files
    results = []
    skipped = 0
    for fit_path in new_fits:
        info, segment = parse_fit_file(fit_path)
        if info is None:
            skipped += 1
            continue
        results.append((info, segment))

    if not results:
        print("No activities with GPS data found.")
        return 0

    # Display activities
    print(f"  {'#':>3}  {'Date':17}  {'Type':12}  {'Distance':>10}  {'Duration':>10}  {'Points':>8}")
    print(f"  {'-'*3}  {'-'*17}  {'-'*12}  {'-'*10}  {'-'*10}  {'-'*8}")
    for i, (info, _) in enumerate(results, 1):
        date_str = info["date"][:16].replace("T", " ") if info["date"] else "unknown"
        dist = f"{info['distance_km']:.1f} km"
        dur = f"{info['duration_min']:.0f} min"
        print(f"  {i:>3}  {date_str:17}  {info['type']:12}  {dist:>10}  {dur:>10}  {info['trackpoints']:>8}")

    if skipped:
        print(f"\n  Skipped {skipped} file(s) without GPS data.")

    # Confirm export
    print()
    answer = input(f"Export {len(results)} activities? [Y/n]: ").strip().lower()
    if answer and answer != "y":
        print("Cancelled.")
        return 0

    # Merge and save
    gpx = merge_to_gpx(results)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}.gpx"
    output_path = output_dir / filename

    # Handle duplicate filenames
    counter = 1
    while output_path.exists():
        filename = f"{today}_{counter}.gpx"
        output_path = output_dir / filename
        counter += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(gpx.to_xml())

    # Update history
    total_dist = sum(info["distance_km"] for info, _ in results)
    total_pts = sum(info["trackpoints"] for info, _ in results)
    export_record = {
        "date": today,
        "file": filename,
        "total_activities": len(results),
        "total_trackpoints": total_pts,
        "total_distance_km": round(total_dist, 2),
        "activities": [info for info, _ in results],
    }
    history["exports"].append(export_record)
    save_history(history)

    print(f"\nSaved: {output_path}")
    print(f"  {len(results)} tracks, {total_pts:,} trackpoints, {total_dist:.1f} km total")
    print("Ready for Lightroom geotagging!")
    return 0


def cmd_stats(args):
    """Show overall export statistics."""
    history = load_history()

    if not history["exports"]:
        print("No export history yet. Run 'export' first or 'backfill' to import existing GPX files.")
        return 0

    total_exports = len(history["exports"])
    total_activities = sum(e["total_activities"] for e in history["exports"])
    total_distance = sum(e["total_distance_km"] for e in history["exports"])
    total_trackpoints = sum(e["total_trackpoints"] for e in history["exports"])
    first_date = history["exports"][0]["date"]
    last_date = history["exports"][-1]["date"]

    print("\nExport History Summary")
    print("=" * 40)
    print(f"  Total exports:      {total_exports}")
    print(f"  Total activities:   {total_activities}")
    print(f"  Total distance:     {total_distance:,.1f} km")
    print(f"  Total trackpoints:  {total_trackpoints:,}")
    print(f"  Date range:         {first_date} to {last_date}")

    # Last 5 exports
    print(f"\n  {'Date':12}  {'File':25}  {'Activities':>10}  {'Distance':>10}")
    print(f"  {'-'*12}  {'-'*25}  {'-'*10}  {'-'*10}")
    for export in history["exports"][-5:]:
        dist = f"{export['total_distance_km']:.1f} km"
        print(f"  {export['date']:12}  {export['file']:25}  {export['total_activities']:>10}  {dist:>10}")

    return 0


def cmd_history(args):
    """Show export history, optionally for a specific date."""
    history = load_history()

    if not history["exports"]:
        print("No export history yet.")
        return 0

    if args.date:
        # Show detail for specific export
        matches = [e for e in history["exports"] if e["date"] == args.date]
        if not matches:
            print(f"No export found for date: {args.date}")
            return 1

        for export in matches:
            print(f"\nExport: {export['date']} ({export['file']})")
            print(f"  Activities: {export['total_activities']}")
            print(f"  Trackpoints: {export['total_trackpoints']:,}")
            print(f"  Distance: {export['total_distance_km']:.1f} km")

            if export.get("activities"):
                print(f"\n  {'#':>3}  {'Date':17}  {'Type':12}  {'Distance':>10}  {'Duration':>10}  {'Points':>8}")
                print(f"  {'-'*3}  {'-'*17}  {'-'*12}  {'-'*10}  {'-'*10}  {'-'*8}")
                for i, act in enumerate(export["activities"], 1):
                    date_str = act["date"][:16].replace("T", " ") if act["date"] else "unknown"
                    dist = f"{act['distance_km']:.1f} km"
                    dur = f"{act['duration_min']:.0f} min"
                    print(f"  {i:>3}  {date_str:17}  {act['type']:12}  {dist:>10}  {dur:>10}  {act['trackpoints']:>8}")
    else:
        # List all exports
        print(f"\n  {'Date':12}  {'File':25}  {'Activities':>10}  {'Distance':>10}  {'Trackpoints':>12}")
        print(f"  {'-'*12}  {'-'*25}  {'-'*10}  {'-'*10}  {'-'*12}")
        for export in history["exports"]:
            dist = f"{export['total_distance_km']:.1f} km"
            print(f"  {export['date']:12}  {export['file']:25}  {export['total_activities']:>10}  {dist:>10}  {export['total_trackpoints']:>12,}")

    return 0


def cmd_backfill(args):
    """Parse existing GPX files in output directory and add them to history."""
    output_dir = Path(args.output)
    history = load_history()
    existing_files = {e["file"] for e in history["exports"]}

    gpx_files = sorted(output_dir.glob("*.gpx"))
    if not gpx_files:
        print("No GPX files found to backfill.")
        return 0

    new_files = [f for f in gpx_files if f.name not in existing_files]
    if not new_files:
        print("All GPX files are already in history.")
        return 0

    print(f"Found {len(new_files)} GPX file(s) to backfill.\n")

    for gpx_path in new_files:
        print(f"  Parsing {gpx_path.name}...", end=" ", flush=True)
        try:
            with open(gpx_path, "r", encoding="utf-8") as f:
                gpx = gpxpy.parse(f)
        except Exception as e:
            print(f"error: {e}")
            continue

        activities = []
        total_pts = 0
        total_dist = 0.0

        for track in gpx.tracks:
            pts = sum(len(seg.points) for seg in track.segments)
            total_pts += pts

            # Estimate distance from trackpoints
            dist = track.length_3d() or track.length_2d() or 0
            dist_km = round(dist / 1000, 2)
            total_dist += dist_km

            # Get track start time
            start = None
            for seg in track.segments:
                if seg.points and seg.points[0].time:
                    start = seg.points[0].time
                    break

            # Estimate duration
            dur_min = 0
            for seg in track.segments:
                if seg.points and len(seg.points) >= 2:
                    first_t = seg.points[0].time
                    last_t = seg.points[-1].time
                    if first_t and last_t:
                        dur_min += (last_t - first_t).total_seconds() / 60

            activities.append({
                "fit_file": f"backfill:{gpx_path.name}:{track.name or 'track'}",
                "date": start.isoformat() if start else "",
                "type": "unknown",
                "distance_km": dist_km,
                "duration_min": round(dur_min, 1),
                "trackpoints": pts,
            })

        # Derive export date from filename (YYYY-MM-DD.gpx) or file mtime
        date_str = gpx_path.stem[:10]
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            date_str = datetime.fromtimestamp(gpx_path.stat().st_mtime).strftime("%Y-%m-%d")

        export_record = {
            "date": date_str,
            "file": gpx_path.name,
            "total_activities": len(activities),
            "total_trackpoints": total_pts,
            "total_distance_km": round(total_dist, 2),
            "activities": activities,
        }
        history["exports"].append(export_record)
        print(f"{len(activities)} tracks, {total_pts:,} pts, {total_dist:.1f} km")

    # Sort by date
    history["exports"].sort(key=lambda e: e["date"])
    save_history(history)

    print(f"\nBackfilled {len(new_files)} exports into history.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Export GPS tracks from Garmin watch (USB) into merged GPX files."
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for GPX files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--drive", "-d",
        help="Garmin device drive letter (e.g., E:\\). Auto-detected if not specified.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("export", help="Export new tracks from connected Garmin device")
    subparsers.add_parser("stats", help="Show export statistics")

    history_parser = subparsers.add_parser("history", help="Show export history")
    history_parser.add_argument("date", nargs="?", help="Show details for a specific export date (YYYY-MM-DD)")

    subparsers.add_parser("backfill", help="Import existing GPX files into history")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    commands = {
        "export": cmd_export,
        "stats": cmd_stats,
        "history": cmd_history,
        "backfill": cmd_backfill,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
