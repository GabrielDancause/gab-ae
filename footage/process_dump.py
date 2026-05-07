#!/usr/bin/env python3
"""
Process dump — scans 1 - Dump/, downloads + encodes ONE clip, hands it off
to the upload scheduler via ready_queue.json.

  - Square clips  →  process (ffmpeg), save to /opt/gab/footage/ready/,
                      move original Dump → 4 - Review/
  - Non-square    →  move Dump → 0 - Unsorted/
  - No metadata   →  skip (Drive not ready), retry next run
  - Lock file     →  never runs two heavy encodes at once

Cron (every 5 min):
  */5 * * * * python3 /opt/gab/footage/process_dump.py >> /var/log/gab/pipeline.log 2>&1

Manual:
  python3 process_dump.py            # process next clip
  python3 process_dump.py --dry-run  # show what would be picked
  python3 process_dump.py --list     # list pending clips in dump
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DRIVE_TOKEN    = '/opt/gab/footage/token.json'
DUMP_FOLDER_ID = '1DyeasST-nK6j7evn4iR7JWBSFc3lQF29'   # 1 - Dump/
UNSORTED_ID    = '15NZqi0siFCjAZxBGSCfbKXp0JVd6Ui66'   # 0 - Unsorted/
REVIEW_ID      = '1SG8dpXogB90OKojNZgTmPCjOryoJqv01'   # 4 - Review/
PROCESS_SCRIPT = '/opt/gab/footage/process_one.py'
READY_DIR      = '/opt/gab/footage/ready'
READY_QUEUE    = '/opt/gab/footage/ready_queue.json'
LOCK_FILE      = '/tmp/process_dump.lock'


def acquire_lock():
    if Path(LOCK_FILE).exists():
        pid = Path(LOCK_FILE).read_text().strip()
        if pid and Path(f'/proc/{pid}').exists():
            print(f"Already running (pid {pid}) — exiting")
            return False
        Path(LOCK_FILE).unlink()
    Path(LOCK_FILE).write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        Path(LOCK_FILE).unlink()
    except FileNotFoundError:
        pass


def drive_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


METADATA_TIMEOUT_SECS = 30 * 60  # fallback to ffprobe after 30 min


def list_video_files(svc, folder_id):
    q = ("'{}' in parents and mimeType contains 'video' "
         "and trashed = false").format(folder_id)
    results, page_token = [], None
    while True:
        r = svc.files().list(
            q=q,
            fields='nextPageToken,files(id,name,size,createdTime,videoMediaMetadata)',
            pageSize=100,
            pageToken=page_token,
        ).execute()
        results.extend(r.get('files', []))
        page_token = r.get('nextPageToken')
        if not page_token:
            break
    return results


def move_file(svc, file_id, from_folder, to_folder):
    svc.files().update(
        fileId=file_id,
        addParents=to_folder,
        removeParents=from_folder,
        fields='id',
    ).execute()


def file_age_secs(f):
    created = f.get('createdTime', '')
    if not created:
        return 0
    t = time.mktime(time.strptime(created[:19], '%Y-%m-%dT%H:%M:%S'))
    return time.time() - t


def probe_dimensions_ffprobe(svc, file_id, filename):
    """Download first 5 MB and run ffprobe to get dimensions. Returns (w, h) or (0, 0)."""
    from googleapiclient.http import MediaIoBaseDownload
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    try:
        request = svc.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(tmp, request, chunksize=5 * 1024 * 1024)
        downloader.next_chunk()  # just the first chunk
        tmp.flush()
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_streams', '-select_streams', 'v:0', tmp.name],
            capture_output=True, text=True
        )
        s = json.loads(r.stdout).get('streams', [{}])[0]
        return s.get('width', 0), s.get('height', 0)
    except Exception as e:
        print(f"  ffprobe fallback failed: {e}")
        return 0, 0
    finally:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)


def is_square(f, svc=None):
    """
    Returns True  — square clip
    Returns False — non-square
    Returns None  — metadata not ready and clip too young to probe

    Resolution order:
    1. Drive videoMediaMetadata (instant, when available)
    2. Filename heuristic: dji_mimo_* → always square (Action Cam 6)
    3. ffprobe on first 5MB chunk (fallback after METADATA_TIMEOUT_SECS)
    """
    meta = f.get('videoMediaMetadata', {})
    w = int(meta.get('width', 0))
    h = int(meta.get('height', 0))
    if w > 0 and h > 0:
        return abs(w - h) < 20

    # DJI Mimo filename → known square format
    if f.get('name', '').lower().startswith('dji_mimo_'):
        return True

    # No Drive metadata — check age before ffprobe
    if file_age_secs(f) < METADATA_TIMEOUT_SECS:
        return None

    # Old enough — try ffprobe as last resort
    if svc is None:
        return None
    print(f"  Drive metadata timeout — probing with ffprobe...")
    w, h = probe_dimensions_ffprobe(svc, f['id'], f['name'])
    if w == 0:
        return None
    print(f"  ffprobe: {w}x{h}")
    return abs(w - h) < 20


def load_queue():
    p = Path(READY_QUEUE)
    return json.loads(p.read_text()) if p.exists() else []


def save_queue(queue):
    Path(READY_QUEUE).write_text(json.dumps(queue, indent=2))


def already_queued(file_id):
    return any(e['drive_id'] == file_id for e in load_queue())


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def main():
    dry_run   = '--dry-run' in sys.argv
    list_mode = '--list'    in sys.argv

    if not (dry_run or list_mode):
        if not acquire_lock():
            sys.exit(0)

    try:
        _main(dry_run, list_mode)
    finally:
        if not (dry_run or list_mode):
            release_lock()


def _main(dry_run, list_mode):
    svc = drive_service()

    files   = list_video_files(svc, DUMP_FOLDER_ID)
    pending = [f for f in files if not already_queued(f['id'])]

    if list_mode:
        if not pending:
            print("1 - Dump/ is empty")
            return
        print(f"{len(pending)} pending clip(s) in Dump:\n")
        for f in pending:
            meta  = f.get('videoMediaMetadata', {})
            w, h  = meta.get('width', '?'), meta.get('height', '?')
            age   = int(file_age_secs(f) / 60)
            sq    = is_square(f)
            label = 'square' if sq is True else ('non-square' if sq is False else f'no metadata ({age}m old)')
            size  = int(f.get('size', 0)) / 1024 / 1024
            print(f"  {f['name']}  {w}x{h}  {size:.0f} MB  [{label}]")
        return

    if not pending:
        print("DUMP_EMPTY")
        return

    # Filter to clips that are resolvable (Drive metadata or old enough for ffprobe)
    ready = [f for f in pending if is_square(f, svc) is not None]
    waiting = len(pending) - len(ready)
    if waiting:
        print(f"  {waiting} clip(s) still waiting for Drive metadata — skipping for now")
    if not ready:
        return

    print(f"  {len(ready)} clip(s) ready to process\n")
    os.makedirs(READY_DIR, exist_ok=True)

    for i, clip in enumerate(ready):
        sq      = is_square(clip, svc)
        meta    = clip.get('videoMediaMetadata', {})
        w, h    = meta.get('width', '?'), meta.get('height', '?')
        size_mb = int(clip.get('size', 0)) / 1024 / 1024

        print(f"\n[{i+1}/{len(ready)}] {clip['name']}  ({size_mb:.0f} MB)  {w}x{h}")

        # Non-square → 0 - Unsorted/
        if not sq:
            print(f"  Non-square → moving to 0 - Unsorted/")
            if not dry_run:
                move_file(svc, clip['id'], DUMP_FOLDER_ID, UNSORTED_ID)
                print("  Moved.")
            continue

        print(f"  Square → processing (ffmpeg only, no upload)")
        if dry_run:
            continue

        cmd = [
            'python3', PROCESS_SCRIPT,
            clip['id'], clip['name'],
            '--channel', 'gab2',
            '--has-ali', 'no',
            '--no-upload',
            '--output-dir', READY_DIR,
        ]
        print(f"  {' '.join(cmd)}\n{'--' * 30}")

        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print(f"  Failed (exit {result.returncode}) — staying in Dump, continuing to next clip")
            continue

        # Parse READY: JSON from output
        ready_data = None
        for line in result.stdout.splitlines():
            if line.startswith('READY:'):
                try:
                    ready_data = json.loads(line[len('READY:'):].strip())
                except json.JSONDecodeError:
                    pass

        if not ready_data:
            print("  ERROR: no READY line in output — staying in Dump")
            continue

        # Add to ready queue
        queue = load_queue()
        queue.append({**ready_data, 'ts_processed': ts(), 'uploaded': False})
        save_queue(queue)

        # Move original Dump → 4 - Review/
        move_file(svc, clip['id'], DUMP_FOLDER_ID, REVIEW_ID)
        print(f"  Moved to 4 - Review/ | queue: {len(queue)} clip(s) ready to upload")

    queue = load_queue()
    print(f"\n{'--' * 30}")
    print(f"Done — {len([e for e in queue if not e.get('uploaded')])} clip(s) ready to upload")


if __name__ == '__main__':
    main()
