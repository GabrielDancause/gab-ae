#!/usr/bin/env python3
"""
Footage pipeline — runs continuously on the VPS.

What it does every 5 minutes:
  1. Scans Google Drive footage/inbox/raw/ for new video files
  2. Detects device from filename, uses Drive createdTime as recording timestamp
  3. Groups clips into sessions (same device, within SESSION_GAP_HOURS of each other)
  4. Processes sessions whose last clip is older than SESSION_GAP_HOURS:
       - Downloads all clips in session
       - FFmpeg: stitch in order + strip audio
       - Uploads stitched output to footage/sessions/{device}/{session_name}/
       - Moves originals to footage/inbox/processed/
       - Deletes local files
  5. Logs everything to SQLite (library.db)

Run on VPS:
    python3 footage/pipeline.py           # run continuously
    python3 footage/pipeline.py --once    # one pass then exit
    python3 footage/pipeline.py --status  # print DB summary

Config: set folder IDs in footage/config.py (copy from config.example.py)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tagger import tag_clip, REQUEST_DELAY_SEC

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REFERENCE_PHOTO = SCRIPT_DIR / "ali_reference.jpg"
CREDENTIALS_FILE = SCRIPT_DIR.parent / "shorts-uploader" / "credentials.json"
TOKEN_FILE = SCRIPT_DIR / "token.json"
DB_FILE = SCRIPT_DIR / "library.db"

SCOPES = ["https://www.googleapis.com/auth/drive"]

SESSION_GAP_HOURS = 0.75    # clips more than 45min apart = different sessions
POLL_INTERVAL_SEC = 300     # check Drive every 5 minutes

try:
    from footage.config import INBOX_RAW_FOLDER_ID, INBOX_PROCESSED_FOLDER_ID, SESSIONS_FOLDER_ID, SHORTS_FOLDER_ID
except ImportError:
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from config import INBOX_RAW_FOLDER_ID, INBOX_PROCESSED_FOLDER_ID, SESSIONS_FOLDER_ID, SHORTS_FOLDER_ID
    except ImportError:
        print("ERROR: footage/config.py not found. Copy config.example.py and fill in folder IDs.")
        sys.exit(1)

VIDEO_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/mpeg",
}

# ── Device detection ──────────────────────────────────────────────────────────

def detect_device(filename: str) -> str:
    name = filename.lower()
    if name.startswith("dji_mimo_"):
        return "dji"
    if name.startswith("od_video-") and "singular_display" in name:
        return "meta"
    if re.match(r"img_\d+", name) or re.match(r"vid_\d+", name):
        return "phone"
    return "unknown"


def parse_drive_time(iso: str) -> str:
    """Parse Drive ISO timestamp to plain UTC string for SQLite."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_dji_time(filename: str) -> str | None:
    """Extract recording time from DJI filename: dji_mimo_YYYYMMDD_HHMMSS_..."""
    m = re.search(r"dji_mimo_(\d{8})_(\d{6})", filename.lower())
    if not m:
        return None
    date, time_ = m.group(1), m.group(2)
    return f"{date[:4]}-{date[4:6]}-{date[6:8]} {time_[:2]}:{time_[2:4]}:{time_[4:6]}"


# ── Database ──────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clips (
            id                  INTEGER PRIMARY KEY,
            drive_file_id       TEXT UNIQUE NOT NULL,
            filename            TEXT NOT NULL,
            device              TEXT NOT NULL,
            recorded_at         TEXT NOT NULL,
            session_id          INTEGER REFERENCES sessions(id),
            duration_seconds    REAL,
            width               INTEGER,
            height              INTEGER,
            fps                 REAL,
            file_size_bytes     INTEGER,
            drive_raw_path      TEXT,
            drive_processed_id  TEXT,
            has_ali             INTEGER,
            gps_lat             REAL,
            gps_lon             REAL,
            location_name       TEXT,
            ai_tags             TEXT,
            processed_at        TEXT,
            created_at          TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id                      INTEGER PRIMARY KEY,
            device                  TEXT NOT NULL,
            started_at              TEXT NOT NULL,
            ended_at                TEXT NOT NULL,
            clip_count              INTEGER DEFAULT 0,
            total_duration_seconds  REAL,
            drive_stitched_id       TEXT,
            drive_stitched_path     TEXT,
            location_name           TEXT,
            notes                   TEXT,
            processed_at            TEXT,
            created_at              TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS publications (
            id              INTEGER PRIMARY KEY,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            platform        TEXT NOT NULL,
            platform_url    TEXT,
            platform_id     TEXT,
            published_at    TEXT,
            revenue_usd     REAL,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_clips_session ON clips(session_id);
        CREATE INDEX IF NOT EXISTS idx_clips_device_time ON clips(device, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_publications_session ON publications(session_id);
    """)
    # Add columns introduced after initial schema — safe to re-run
    for col_sql in [
        "ALTER TABLE sessions ADD COLUMN activity TEXT",
        "ALTER TABLE sessions ADD COLUMN has_ali INTEGER",
        "ALTER TABLE sessions ADD COLUMN time_of_day TEXT",
        "ALTER TABLE sessions ADD COLUMN drive_stitched_deleted_at TEXT",
        "ALTER TABLE clips ADD COLUMN short_drive_id TEXT",
        "ALTER TABLE clips ADD COLUMN short_start_seconds REAL",
        "ALTER TABLE clips ADD COLUMN short_end_seconds REAL",
        "ALTER TABLE clips ADD COLUMN short_score INTEGER",
        "ALTER TABLE clips ADD COLUMN short_reason TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


# ── Drive helpers ─────────────────────────────────────────────────────────────

def list_drive_files(drive, folder_id: str) -> list[dict]:
    files, page_token = [], None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
            pageToken=page_token,
            pageSize=100,
            orderBy="createdTime",
        ).execute()
        for f in resp.get("files", []):
            mime = f.get("mimeType", "")
            if mime in VIDEO_MIME_TYPES or mime.startswith("video/"):
                files.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_file(drive, file_id: str, dest: str, label: str):
    req = drive.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            status, done = dl.next_chunk()
            print(f"  [{label}] {int(status.progress() * 100)}%", end="\r")
    print()


def upload_file(drive, local_path: str, name: str, parent_id: str) -> dict:
    meta = {"name": name, "parents": [parent_id]}
    media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True, chunksize=10 * 1024 * 1024)
    req = drive.files().create(body=meta, media_body=media, fields="id, name, webViewLink")
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  Uploading... {int(status.progress() * 100)}%", end="\r")
    print()
    return resp


def get_or_create_folder(drive, name: str, parent_id: str) -> str:
    resp = drive.files().list(
        q=f"'{parent_id}' in parents and name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)",
        pageSize=1,
    ).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]
    folder = drive.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        fields="id",
    ).execute()
    return folder["id"]


def move_file(drive, file_id: str, from_folder: str, to_folder: str):
    drive.files().update(
        fileId=file_id,
        addParents=to_folder,
        removeParents=from_folder,
        fields="id",
    ).execute()


# ── ffprobe ───────────────────────────────────────────────────────────────────

def probe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {}
    return json.loads(result.stdout)

def extract_metadata(path: str) -> dict:
    data = probe(path)
    meta = {}

    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video_stream:
        meta["width"] = video_stream.get("width")
        meta["height"] = video_stream.get("height")
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        try:
            num, den = r_frame_rate.split("/")
            meta["fps"] = round(int(num) / int(den), 2)
        except Exception:
            pass

    fmt = data.get("format", {})
    meta["duration_seconds"] = float(fmt.get("duration", 0))
    meta["file_size_bytes"] = int(fmt.get("size", 0))

    tags = fmt.get("tags", {})
    creation = tags.get("creation_time")
    if creation:
        meta["recorded_at"] = creation

    location = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
    if location:
        match = re.match(r"([+-]\d+\.\d+)([+-]\d+\.\d+)", location)
        if match:
            meta["gps_lat"] = float(match.group(1))
            meta["gps_lon"] = float(match.group(2))

    return meta


# ── FFmpeg ────────────────────────────────────────────────────────────────────

def stitch(input_paths: list[str], output_path: str):
    concat_file = output_path + ".txt"
    with open(concat_file, "w") as f:
        for p in input_paths:
            f.write(f"file '{p}'\n")

    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-an", "-c:v", "copy", output_path],
        capture_output=True, text=True,
    )
    os.unlink(concat_file)

    if result.returncode != 0:
        print("FFmpeg error:\n" + result.stderr[-2000:])
        return False
    return True


def cut_short(input_path: str, output_path: str, start: float, end: float) -> bool:
    duration = end - start
    if duration < 5:
        print(f"  Short skipped: invalid window {start:.1f}s → {end:.1f}s")
        return False
    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-i", input_path,
         "-t", str(duration), "-an",
         "-filter_complex", "[0:v]scale=1080:1920,boxblur=20:5[bg];[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2",
         "-c:v", "libx264", "-crf", "23", "-preset", "fast",
         "-maxrate", "8M", "-bufsize", "16M",
         output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("FFmpeg short cut error:\n" + result.stderr[-500:])
        return False
    return True


# ── Session grouping ──────────────────────────────────────────────────────────

def assign_sessions(conn: sqlite3.Connection):
    """Group unassigned clips into sessions by device + time proximity."""
    unassigned = conn.execute(
        "SELECT id, device, recorded_at FROM clips WHERE session_id IS NULL ORDER BY device, recorded_at"
    ).fetchall()

    for clip_id, device, recorded_at_str in unassigned:
        recorded_at = datetime.fromisoformat(recorded_at_str)
        gap = timedelta(hours=SESSION_GAP_HOURS)

        # Find an existing open session for this device where this clip fits
        cutoff = (datetime.strptime(recorded_at_str, "%Y-%m-%d %H:%M:%S") - timedelta(hours=SESSION_GAP_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        session = conn.execute("""
            SELECT s.id, s.ended_at FROM sessions s
            WHERE s.device = ?
              AND s.processed_at IS NULL
              AND s.ended_at >= ?
              AND s.started_at <= ?
            ORDER BY s.ended_at DESC LIMIT 1
        """, (device, cutoff, recorded_at_str)).fetchone()

        if session:
            session_id, ended_at_str = session
            ended_at = datetime.strptime(ended_at_str, "%Y-%m-%d %H:%M:%S")
            new_end = max(ended_at, recorded_at).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("UPDATE sessions SET ended_at = ?, clip_count = clip_count + 1 WHERE id = ?",
                         (new_end, session_id))
        else:
            cur = conn.execute(
                "INSERT INTO sessions (device, started_at, ended_at, clip_count) VALUES (?, ?, ?, 1)",
                (device, recorded_at_str, recorded_at_str),
            )
            session_id = cur.lastrowid

        conn.execute("UPDATE clips SET session_id = ? WHERE id = ?", (session_id, clip_id))

    conn.commit()


def sessions_ready(conn: sqlite3.Connection) -> list[int]:
    """Return session IDs whose last clip is older than SESSION_GAP_HOURS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=SESSION_GAP_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute("""
        SELECT id FROM sessions
        WHERE processed_at IS NULL
          AND ended_at < ?
          AND clip_count > 0
    """, (cutoff,)).fetchall()
    return [r[0] for r in rows]


# ── Core pipeline ─────────────────────────────────────────────────────────────

def scan_inbox(drive, conn: sqlite3.Connection):
    """List Drive inbox/raw/ and insert new clips into DB."""
    files = list_drive_files(drive, INBOX_RAW_FOLDER_ID)
    new_count = 0
    for f in files:
        exists = conn.execute("SELECT 1 FROM clips WHERE drive_file_id = ?", (f["id"],)).fetchone()
        if exists:
            continue
        device = detect_device(f["name"])
        recorded_at = (
            parse_dji_time(f["name"]) if device == "dji" else None
        ) or parse_drive_time(f["createdTime"])
        conn.execute("""
            INSERT INTO clips (drive_file_id, filename, device, recorded_at, file_size_bytes, drive_raw_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (f["id"], f["name"], device, recorded_at, int(f.get("size", 0)), f"inbox/raw/{f['name']}"))
        new_count += 1

    if new_count:
        print(f"  Found {new_count} new clip(s)")
    conn.commit()


DISK_SAFETY_BUFFER = 5 * 1024 ** 3   # always keep 5 GB free


def check_disk_space(session_id: int, conn: sqlite3.Connection) -> bool:
    """Return False if there isn't enough disk space to download + stitch this session."""
    total_bytes = conn.execute(
        "SELECT SUM(file_size_bytes) FROM clips WHERE session_id = ?", (session_id,)
    ).fetchone()[0] or 0

    # raw clips + small headroom for encoded shorts + safety buffer
    needed = total_bytes + DISK_SAFETY_BUFFER

    stat = os.statvfs("/tmp")
    available = stat.f_bavail * stat.f_frsize

    if available < needed:
        needed_gb = needed / 1024 ** 3
        avail_gb = available / 1024 ** 3
        print(f"  SKIP: not enough disk space — need {needed_gb:.1f} GB, have {avail_gb:.1f} GB free")
        return False
    return True


def process_session(drive, conn: sqlite3.Connection, session_id: int):
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    cols = [d[0] for d in conn.execute("SELECT * FROM sessions WHERE 0").description]
    s = dict(zip(cols, session))

    clips = conn.execute("""
        SELECT * FROM clips WHERE session_id = ? ORDER BY recorded_at
    """, (session_id,)).fetchall()
    clip_cols = [d[0] for d in conn.execute("SELECT * FROM clips WHERE 0").description]
    clips = [dict(zip(clip_cols, c)) for c in clips]

    session_name = f"{s['device']}_{s['started_at'][:10]}_{s['started_at'][11:16].replace(':', '')}"
    print(f"\nProcessing session {session_name} ({len(clips)} clip(s))")

    if not check_disk_space(session_id, conn):
        return

    with tempfile.TemporaryDirectory() as tmp:
        downloaded = []
        clip_tag_results = []

        date_str = s["started_at"][:10]
        shorts_device_id = get_or_create_folder(drive, s["device"], SHORTS_FOLDER_ID)
        shorts_date_id   = get_or_create_folder(drive, date_str, shorts_device_id)

        for i, clip in enumerate(clips, 1):
            dest = os.path.join(tmp, f"{i:03d}_{clip['filename']}")
            print(f"  Downloading {clip['filename']}")
            download_file(drive, clip["drive_file_id"], dest, f"{i}/{len(clips)}")

            # Update DB with accurate ffprobe metadata
            meta = extract_metadata(dest)
            conn.execute("""
                UPDATE clips SET
                    duration_seconds = ?, width = ?, height = ?, fps = ?,
                    file_size_bytes = COALESCE(?, file_size_bytes),
                    recorded_at = COALESCE(?, recorded_at),
                    gps_lat = ?, gps_lon = ?
                WHERE id = ?
            """, (
                meta.get("duration_seconds"), meta.get("width"), meta.get("height"), meta.get("fps"),
                meta.get("file_size_bytes"), meta.get("recorded_at"),
                meta.get("gps_lat"), meta.get("gps_lon"),
                clip["id"],
            ))

            # AI: tag clip + pick short window
            tag = {"score": 0, "start_time": 0.0, "end_time": 0.0, "reason": "skipped",
                   "has_ali": None, "tags": [], "activity": "", "time_of_day": ""}
            if REFERENCE_PHOTO.exists():
                try:
                    tag = tag_clip(dest, str(REFERENCE_PHOTO))
                    print(f"  [{i}/{len(clips)}] score={tag['score']} | {tag['reason'][:60]}")
                except Exception as e:
                    print(f"  [{i}/{len(clips)}] tagging error: {e}")

            clip_tag_results.append(tag)

            # Update clip with AI results + short metadata
            conn.execute("""
                UPDATE clips SET
                    has_ali = ?, ai_tags = ?,
                    short_score = ?, short_start_seconds = ?, short_end_seconds = ?, short_reason = ?
                WHERE id = ?
            """, (
                int(tag["has_ali"]) if tag["has_ali"] is not None else None,
                json.dumps(tag["tags"]),
                tag["score"], tag["start_time"], tag["end_time"], tag["reason"],
                clip["id"],
            ))

            # Cut and upload short for this clip
            clip_stem = Path(clip["filename"]).stem
            short_name = f"{clip_stem}_short.mp4"
            short_path = os.path.join(tmp, short_name)
            if cut_short(dest, short_path, tag["start_time"], tag["end_time"]):
                try:
                    short_result = upload_file(drive, short_path, short_name, shorts_date_id)
                    conn.execute("UPDATE clips SET short_drive_id = ? WHERE id = ?",
                                 (short_result["id"], clip["id"]))
                    print(f"  Short uploaded: {short_result.get('webViewLink', short_result['id'])}")
                except Exception as e:
                    print(f"  Short upload error: {e}")
                finally:
                    if os.path.exists(short_path):
                        os.unlink(short_path)

            conn.commit()

            if i < len(clips):
                time.sleep(REQUEST_DELAY_SEC)

        # Aggregate session-level tags from all clips
        has_ali_session = any(t.get("has_ali") for t in clip_tag_results)
        activity_counts: dict[str, int] = {}
        time_counts: dict[str, int] = {}
        for t in clip_tag_results:
            a = t.get("activity", "")
            if a:
                activity_counts[a] = activity_counts.get(a, 0) + 1
            tod = t.get("time_of_day", "")
            if tod:
                time_counts[tod] = time_counts.get(tod, 0) + 1
        session_activity = max(activity_counts, key=activity_counts.get) if activity_counts else None
        session_time_of_day = max(time_counts, key=time_counts.get) if time_counts else None

        total_duration = conn.execute(
            "SELECT SUM(duration_seconds) FROM clips WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

        # Move originals to processed/{device}/{date}/session_{time}/
        date_str = s["started_at"][:10]
        time_str = s["started_at"][11:16].replace(":", "")
        device_folder_id = get_or_create_folder(drive, s["device"], INBOX_PROCESSED_FOLDER_ID)
        date_folder_id   = get_or_create_folder(drive, date_str, device_folder_id)
        session_dest_id  = get_or_create_folder(drive, f"session_{time_str}", date_folder_id)

        for clip in clips:
            move_file(drive, clip["drive_file_id"], INBOX_RAW_FOLDER_ID, session_dest_id)
            processed_path = f"processed/{s['device']}/{date_str}/session_{time_str}/{clip['filename']}"
            conn.execute("""
                UPDATE clips SET drive_processed_id = drive_file_id, drive_raw_path = ?, processed_at = datetime('now')
                WHERE id = ?
            """, (processed_path, clip["id"],))

        # Mark session done (no stitch yet)
        conn.execute("""
            UPDATE sessions SET
                processed_at = datetime('now'),
                has_ali = ?, activity = ?, time_of_day = ?, total_duration_seconds = ?
            WHERE id = ?
        """, (
            int(has_ali_session),
            session_activity,
            session_time_of_day,
            total_duration,
            session_id,
        ))
        conn.commit()
        print(f"  Session done — stitching skipped (do later)")

        print(f"  Done: {result.get('webViewLink', result['id'])}")


# ── Status ────────────────────────────────────────────────────────────────────

def print_status(conn: sqlite3.Connection):
    total_clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM sessions WHERE processed_at IS NOT NULL").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM sessions WHERE processed_at IS NULL").fetchone()[0]

    print(f"\n{'─'*40}")
    print(f"  Clips in library : {total_clips}")
    print(f"  Sessions total   : {total_sessions}")
    print(f"  Processed        : {processed}")
    print(f"  Pending          : {pending}")

    by_device = conn.execute(
        "SELECT device, COUNT(*) FROM clips GROUP BY device"
    ).fetchall()
    if by_device:
        print(f"\n  By device:")
        for device, count in by_device:
            print(f"    {device:10} {count} clips")
    print(f"{'─'*40}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_once(drive, conn: sqlite3.Connection):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanning inbox...")
    scan_inbox(drive, conn)
    assign_sessions(conn)
    ready = sessions_ready(conn)
    if ready:
        print(f"  {len(ready)} session(s) ready to process")
        for session_id in ready:
            process_session(drive, conn, session_id)
    else:
        print(f"  No sessions ready yet")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one pass then exit")
    parser.add_argument("--status", action="store_true", help="Print DB summary and exit")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_FILE, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)

    if args.status:
        print_status(conn)
        return

    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds)

    if args.once:
        run_once(drive, conn)
        return

    print("Footage pipeline running. Ctrl+C to stop.")
    while True:
        try:
            run_once(drive, conn)
        except Exception as e:
            print(f"  ERROR: {e}")
        print(f"  Sleeping {POLL_INTERVAL_SEC}s...")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
