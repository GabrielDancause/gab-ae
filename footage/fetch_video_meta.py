#!/usr/bin/env python3
"""
Fetch width, height, duration for every video in catalog.db using Drive API.
No downloading — pure metadata. Safe to run multiple times (skips already-done).

Usage:
  python3 fetch_video_meta.py          # fetch all missing metadata
  python3 fetch_video_meta.py --stats  # just print vertical/horizontal breakdown
"""

import sys
import time
import sqlite3
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DRIVE_TOKEN = '/opt/gab/footage/token.json'
CATALOG_DB  = '/opt/gab/footage/catalog.db'
BATCH_SIZE  = 50  # API calls between saves


def get_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds)


def init_columns(conn):
    """Add metadata columns if they don't exist yet."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(files)").fetchall()]
    if 'width' not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN width INTEGER")
    if 'height' not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN height INTEGER")
    if 'duration_ms' not in cols:
        conn.execute("ALTER TABLE files ADD COLUMN duration_ms INTEGER")
    conn.commit()


def print_stats(conn):
    total = conn.execute(
        "SELECT COUNT(*) FROM files WHERE mime_type LIKE 'video/%'"
    ).fetchone()[0]

    done = conn.execute(
        "SELECT COUNT(*) FROM files WHERE mime_type LIKE 'video/%' AND width IS NOT NULL"
    ).fetchone()[0]

    vertical = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM files "
        "WHERE mime_type LIKE 'video/%' AND height > width AND width > 0"
    ).fetchone()

    short_vertical = conn.execute(
        "SELECT COUNT(*) FROM files "
        "WHERE mime_type LIKE 'video/%' AND height > width AND width > 0 AND duration_ms < 60000"
    ).fetchone()[0]

    horizontal = conn.execute(
        "SELECT COUNT(*) FROM files "
        "WHERE mime_type LIKE 'video/%' AND width >= height AND width > 0"
    ).fetchone()[0]

    square = conn.execute(
        "SELECT COUNT(*) FROM files "
        "WHERE mime_type LIKE 'video/%' AND width = height AND width > 0"
    ).fetchone()[0]

    no_meta = conn.execute(
        "SELECT COUNT(*) FROM files "
        "WHERE mime_type LIKE 'video/%' AND width = -1"
    ).fetchone()[0]

    print("\n=== Video Metadata Summary ===")
    print("  Total videos      : {:,}".format(total))
    print("  Metadata fetched  : {:,}  ({} remaining)".format(done, total - done))
    print("  No Drive metadata : {:,}  (large/raw files — need ffprobe)".format(no_meta))
    print()
    print("  Vertical (h>w)    : {:,}  ({:.1f} GB)".format(vertical[0], vertical[1]/1024**3))
    print("  Vertical <60s     : {:,}  ← Shorts-ready, no crop needed".format(short_vertical))
    print("  Horizontal        : {:,}".format(horizontal))
    print("  Square            : {:,}".format(square))

    print("\nTop vertical footage folders:")
    for r in conn.execute("""
        SELECT folder_name, COUNT(*) n,
               SUM(CASE WHEN duration_ms < 60000 THEN 1 ELSE 0 END) short_n
        FROM files
        WHERE mime_type LIKE 'video/%' AND height > width AND width > 0
        GROUP BY folder_name ORDER BY n DESC LIMIT 15
    """):
        print("  {:4d} vertical ({:3d} <60s)  {}".format(r[1], r[2] if r[2] is not None else 0, r[0]))


def fetch_metadata():
    svc  = get_service()
    conn = sqlite3.connect(CATALOG_DB)
    init_columns(conn)

    # Get all videos missing metadata
    rows = conn.execute("""
        SELECT drive_id, name FROM files
        WHERE mime_type LIKE 'video/%' AND width IS NULL
        ORDER BY size_bytes ASC
    """).fetchall()

    total   = len(rows)
    done    = 0
    skipped = 0

    print("Fetching metadata for {:,} videos (no downloads)...\n".format(total))

    for i, (drive_id, name) in enumerate(rows):
        for attempt in range(3):
            try:
                f = svc.files().get(
                    fileId=drive_id,
                    fields='id,videoMediaMetadata'
                ).execute()
                break
            except HttpError as e:
                if e.resp.status == 429:
                    wait = 30 * (attempt + 1)
                    print("  Rate limited — sleeping {}s...".format(wait))
                    time.sleep(wait)
                elif e.resp.status == 404:
                    skipped += 1
                    break
                else:
                    raise
        else:
            skipped += 1
            continue

        meta = f.get('videoMediaMetadata', {})
        width    = meta.get('width')
        height   = meta.get('height')
        dur_ms   = meta.get('durationMillis')

        # Use -1 as sentinel when Drive has no metadata (large/unprocessed files)
        # so they don't keep appearing in the "width IS NULL" queue
        conn.execute(
            "UPDATE files SET width=?, height=?, duration_ms=? WHERE drive_id=?",
            (
                int(width) if width else -1,
                int(height) if height else -1,
                int(dur_ms) if dur_ms else None,
                drive_id
            )
        )
        done += 1

        # Save every BATCH_SIZE files
        if done % BATCH_SIZE == 0:
            conn.commit()
            orientation = '↕' if (height and width and height > width) else '↔'
            dur_s = int(dur_ms) // 1000 if dur_ms else 0
            print("  [{:5d}/{:5d}]  {}  {:4d}s  {}".format(
                i+1, total, orientation, dur_s, name[:50]))

        time.sleep(0.05)  # gentle pacing

    conn.commit()
    print("\nDone. {} fetched, {} skipped/not found.\n".format(done, skipped))
    print_stats(conn)
    conn.close()


if __name__ == '__main__':
    if '--stats' in sys.argv:
        conn = sqlite3.connect(CATALOG_DB)
        init_columns(conn)
        print_stats(conn)
        conn.close()
    else:
        fetch_metadata()
