#!/usr/bin/env python3
"""
Scan all of Google Drive and catalog every file.
Paginated and resumable — saves progress after each page.
Run again to continue from where it left off.
Run with --fresh to start over.

Usage:
  python3 scan_drive.py          # start or resume scan
  python3 scan_drive.py --fresh  # restart from scratch
  python3 scan_drive.py --stats  # print summary without scanning
"""

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

DRIVE_TOKEN = '/opt/gab/footage/token.json'
CATALOG_DB  = '/opt/gab/footage/catalog.db'
RESUME_FILE = '/opt/gab/footage/scan_resume.json'
PAGE_SIZE   = 1000  # max allowed by Drive API


# ── helpers ──────────────────────────────────────────────────────────────────

def get_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds)


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS folders (
        drive_id    TEXT PRIMARY KEY,
        name        TEXT,
        date        TEXT,
        description TEXT,
        scanned_at  TEXT
    );

    CREATE TABLE IF NOT EXISTS files (
        drive_id          TEXT PRIMARY KEY,
        name              TEXT,
        mime_type         TEXT,
        size_bytes        INTEGER,
        folder_id         TEXT,
        folder_name       TEXT,
        date              TEXT,
        modified_at       TEXT,
        status            TEXT DEFAULT 'new',
        proposed_channel  TEXT,
        proposal_drive_id TEXT,
        uploaded_url      TEXT,
        cataloged_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
    CREATE INDEX IF NOT EXISTS idx_files_date   ON files(date);
    CREATE INDEX IF NOT EXISTS idx_files_mime   ON files(mime_type);
    CREATE INDEX IF NOT EXISTS idx_folders_date ON folders(date);
    """)
    conn.commit()


def parse_date_from_name(name):
    """YYYY-MM-DD from '2024-03-15 - Paris walk' style names."""
    m = re.match(r'(\d{4}-\d{2}-\d{2})', name)
    return m.group(1) if m else None


def parse_date_from_dji(name):
    """Date from DJI filenames like dji_mimo_20260501_152658_..."""
    m = re.search(r'_(\d{4})(\d{2})(\d{2})_', name)
    return '{}-{}-{}'.format(m.group(1), m.group(2), m.group(3)) if m else None


def human_bytes(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024:
            return '{:.1f} {}'.format(n, unit)
        n /= 1024
    return '{:.1f} PB'.format(n)


# ── stats ─────────────────────────────────────────────────────────────────────

def print_stats(conn):
    row = conn.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM files").fetchone()
    print("\n=== Catalog ===")
    print("  Total files : {:,}  ({})".format(row[0], human_bytes(row[1])))

    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM files WHERE mime_type LIKE 'video/%'"
    ).fetchone()
    print("  Video files : {:,}  ({})".format(row[0], human_bytes(row[1])))

    row = conn.execute("SELECT COUNT(DISTINCT folder_id) FROM files").fetchone()
    print("  Folders     : {:,}".format(row[0]))

    print("\nTop folders by video count:")
    for r in conn.execute("""
        SELECT folder_name, COUNT(*) n, COALESCE(SUM(size_bytes),0) sz
        FROM files WHERE mime_type LIKE 'video/%'
        GROUP BY folder_name ORDER BY n DESC LIMIT 15
    """):
        print("  {:4d} videos  {:>9s}  {}".format(r[1], human_bytes(r[2]), r[0]))

    print("\nFiles by status:")
    for r in conn.execute(
        "SELECT status, COUNT(*) FROM files GROUP BY status ORDER BY COUNT(*) DESC"
    ):
        print("  {:20s}  {:,}".format(r[0], r[1]))


# ── main scan ─────────────────────────────────────────────────────────────────

def scan(resume=True):
    svc  = get_service()
    conn = sqlite3.connect(CATALOG_DB)
    init_db(conn)

    # Resume state
    resume_data = {}
    if resume and Path(RESUME_FILE).exists():
        resume_data = json.loads(Path(RESUME_FILE).read_text())

    page_token = resume_data.get('next_page_token')
    total_seen = resume_data.get('total_seen', 0)
    page_num   = resume_data.get('page_num', 0)
    folder_cache = {}  # drive_id → name, in-memory only

    if page_token:
        print("Resuming from page {}  ({:,} files indexed so far)".format(page_num, total_seen))
    else:
        print("Starting full Drive scan...")
    print("Ctrl+C to pause — progress saved after every page.\n")

    try:
        while True:
            page_num += 1

            # Fetch a page (with retry on rate-limit)
            for attempt in range(4):
                try:
                    resp = svc.files().list(
                        pageSize=PAGE_SIZE,
                        fields="nextPageToken, files(id,name,mimeType,size,parents,modifiedTime)",
                        pageToken=page_token or None,
                    ).execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429:
                        wait = 30 * (attempt + 1)
                        print("  Rate limited — sleeping {}s...".format(wait))
                        time.sleep(wait)
                    else:
                        raise

            items = resp.get('files', [])
            if not items:
                break

            # Resolve unknown parent folders
            unknown = {
                pid
                for f in items
                for pid in f.get('parents', [])
                if pid not in folder_cache
            }
            for pid in unknown:
                try:
                    fo = svc.files().get(fileId=pid, fields='id,name').execute()
                    folder_cache[pid] = fo['name']
                    date = parse_date_from_name(fo['name'])
                    desc = fo['name'][12:].strip(' -') if date else fo['name']
                    conn.execute(
                        "INSERT OR IGNORE INTO folders VALUES (?,?,?,?,datetime('now'))",
                        (pid, fo['name'], date, desc)
                    )
                except Exception:
                    folder_cache[pid] = '?'

            # Insert files
            for f in items:
                parents     = f.get('parents', [])
                folder_id   = parents[0] if parents else None
                folder_name = folder_cache.get(folder_id, '?') if folder_id else 'root'

                date = (
                    parse_date_from_name(folder_name)
                    or parse_date_from_dji(f['name'])
                    or f.get('modifiedTime', '')[:10]
                )

                conn.execute("""
                    INSERT OR IGNORE INTO files
                        (drive_id, name, mime_type, size_bytes,
                         folder_id, folder_name, date, modified_at)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    f['id'], f['name'], f['mimeType'],
                    int(f.get('size', 0) or 0),
                    folder_id, folder_name, date,
                    f.get('modifiedTime', '')
                ))

            conn.commit()
            total_seen += len(items)
            videos = sum(1 for f in items if 'video' in f.get('mimeType', ''))

            print("Page {:4d} | {:4d} files ({:3d} videos) | total indexed: {:,}".format(
                page_num, len(items), videos, total_seen))

            # Save resume state
            next_token = resp.get('nextPageToken')
            Path(RESUME_FILE).write_text(json.dumps({
                'next_page_token': next_token,
                'total_seen': total_seen,
                'page_num': page_num,
            }))

            if not next_token:
                print("\n✅ Scan complete!")
                Path(RESUME_FILE).unlink(missing_ok=True)
                break

            page_token = next_token
            time.sleep(0.1)  # gentle pacing

    except KeyboardInterrupt:
        print("\nPaused — run again to resume.")

    print_stats(conn)
    conn.close()


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    args = sys.argv[1:]

    if '--stats' in args:
        conn = sqlite3.connect(CATALOG_DB)
        init_db(conn)
        print_stats(conn)
        conn.close()
        sys.exit(0)

    if '--fresh' in args:
        Path(CATALOG_DB).unlink(missing_ok=True)
        Path(RESUME_FILE).unlink(missing_ok=True)
        print("Cleared existing catalog.")

    scan(resume='--fresh' not in args)
