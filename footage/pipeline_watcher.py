#!/usr/bin/env python3
"""
Dump watcher — scans _Pipeline/1 - Dump/ in Drive every 5 minutes.
  - Square clips (DJI Action Cam 6)  →  process + upload to YouTube (gab2)
                                         then move to 5 - Published/
  - Non-square clips                 →  move to 0 - Unsorted/ (no processing)
  - Upload quota errors              →  move to 7 - Upload Queue/ (retry later)
  - Other errors                     →  stay in Dump (retry next run)
  - Lock file prevents concurrent runs (safe with heavy clips)

Cron (every 5 min):
  */5 * * * * python3 /opt/gab/footage/pipeline_watcher.py >> /var/log/gab/pipeline.log 2>&1

Manual:
  python3 pipeline_watcher.py              # process next clip
  python3 pipeline_watcher.py --dry-run    # show what would be picked, no action
  python3 pipeline_watcher.py --list       # list all pending clips with dimensions
  python3 pipeline_watcher.py --status     # show processed / skipped summary
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DRIVE_TOKEN      = '/opt/gab/footage/token.json'
DUMP_FOLDER_ID   = '1DyeasST-nK6j7evn4iR7JWBSFc3lQF29'   # 1 - Dump/
UNSORTED_ID      = '15NZqi0siFCjAZxBGSCfbKXp0JVd6Ui66'   # 0 - Unsorted/
PUBLISHED_ID     = '1Hlnqh4sKTXHA2cfq9B1inNG6l8zbiQWU'   # 5 - Published/
UPLOAD_QUEUE_ID  = '1UNmWzwmF5jriNofF4jf4LSUiFjHDr8HM'   # 7 - Upload Queue/
PROCESS_SCRIPT   = '/opt/gab/footage/process_one.py'
STATE_FILE       = '/opt/gab/footage/pipeline_state.json'
LOCK_FILE        = '/tmp/pipeline_watcher.lock'

QUOTA_ERRORS = ('uploadLimitExceeded', 'forbidden', 'quotaExceeded')


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


def list_video_files(svc, folder_id):
    q = ("'{}' in parents and mimeType contains 'video' "
         "and trashed = false").format(folder_id)
    results, page_token = [], None
    while True:
        r = svc.files().list(
            q=q,
            fields='nextPageToken,files(id,name,size,videoMediaMetadata)',
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


def is_square(f):
    meta = f.get('videoMediaMetadata', {})
    w = int(meta.get('width', 0))
    h = int(meta.get('height', 0))
    if w == 0 or h == 0:
        return None
    return abs(w - h) < 20


def is_quota_error(output):
    return any(e in output for e in QUOTA_ERRORS)


def load_state():
    p = Path(STATE_FILE)
    return json.loads(p.read_text()) if p.exists() else {'done': [], 'errors': [], 'upload_queue': []}


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def next_publish_time(state):
    last = state.get('next_publish_at')
    now  = time.time()
    if last:
        last_epoch = time.mktime(time.strptime(last, '%Y-%m-%dT%H:%M:%S.000Z'))
        base = max(last_epoch, now)
    else:
        base = now
    slot = base + 3600
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(slot))


def run_process(svc, clip, from_folder, publish_at, state, dry_run):
    """Download, process, and upload one clip. Returns 'done', 'quota', or 'error'."""
    cmd = [
        'python3', PROCESS_SCRIPT,
        clip['id'], clip['name'],
        '--channel', 'gab2',
        '--has-ali', 'no',
        '--publish-at', publish_at,
    ]
    print(f"\n  {' '.join(cmd)}\n{'--' * 30}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    yt_url, title = '', ''
    for line in result.stdout.splitlines():
        if 'YouTube:' in line:
            yt_url = line.split('YouTube:')[-1].strip()
        if 'Title:' in line and not title:
            title = line.split('Title:')[-1].strip()

    if result.returncode != 0:
        combined = result.stdout + result.stderr
        if is_quota_error(combined):
            print(f"\n  YouTube quota exceeded — moving to 7 - Upload Queue/")
            move_file(svc, clip['id'], from_folder, UPLOAD_QUEUE_ID)
            state.setdefault('upload_queue', []).append({
                'id': clip['id'], 'name': clip['name'],
                'publish_at': publish_at, 'ts': ts(),
            })
            save_state(state)
            return 'quota'
        else:
            print(f"\n  Failed (exit {result.returncode}) — staying in {from_folder}, will retry")
            state.setdefault('errors', []).append({
                'id': clip['id'], 'name': clip['name'],
                'error': f"exit {result.returncode}", 'ts': ts(),
            })
            save_state(state)
            return 'error'

    move_file(svc, clip['id'], from_folder, PUBLISHED_ID)
    print(f"  Moved to 5 - Published/")

    state['next_publish_at'] = publish_at
    state['done'].append({
        'id': clip['id'], 'name': clip['name'],
        'title': title, 'youtube_url': yt_url,
        'publish_at': publish_at, 'ts': ts(),
    })
    save_state(state)
    return 'done'


def main():
    dry_run     = '--dry-run' in sys.argv
    list_mode   = '--list'    in sys.argv
    status_mode = '--status'  in sys.argv

    if not (dry_run or list_mode or status_mode):
        if not acquire_lock():
            sys.exit(0)

    try:
        _main(dry_run, list_mode, status_mode)
    finally:
        if not (dry_run or list_mode or status_mode):
            release_lock()


def _main(dry_run, list_mode, status_mode):
    state    = load_state()
    done_ids = {e['id'] if isinstance(e, dict) else e for e in state['done']}

    if status_mode:
        print(f"Processed    : {len(state['done'])} clips")
        uq = state.get('upload_queue', [])
        print(f"Upload Queue : {len(uq)} clip(s) waiting for quota reset")
        if state.get('errors'):
            print(f"Errors       : {len(state['errors'])}")
            for e in state['errors'][-3:]:
                print(f"  x {e.get('name')} -- {e.get('error')}")
        print()
        for e in state['done'][-10:]:
            print(f"  + {e.get('name')} -> {e.get('youtube_url', '?')}")
        return

    svc = drive_service()

    # ── 1. Retry upload queue first ───────────────────────────────────────────
    uq_files = list_video_files(svc, UPLOAD_QUEUE_ID)
    if uq_files:
        clip    = uq_files[0]
        uq_meta = next(
            (e for e in state.get('upload_queue', []) if e['id'] == clip['id']),
            {}
        )
        publish_at = uq_meta.get('publish_at') or next_publish_time(state)
        size_mb    = int(clip.get('size', 0)) / 1024 / 1024

        print(f"\n  [UPLOAD QUEUE] {clip['name']}  ({size_mb:.0f} MB)")
        print(f"  Retrying upload  |  scheduled for {publish_at}")

        if not dry_run:
            outcome = run_process(svc, clip, UPLOAD_QUEUE_ID, publish_at, state, dry_run)
            if outcome == 'done':
                # Remove from upload_queue tracking
                state['upload_queue'] = [
                    e for e in state.get('upload_queue', []) if e['id'] != clip['id']
                ]
                save_state(state)
                remaining_uq = len(list_video_files(svc, UPLOAD_QUEUE_ID)) - 1
                print(f"  Upload Queue: {remaining_uq} clip(s) remaining")
            elif outcome == 'quota':
                print(f"  Still quota-blocked — will retry next run")
        return

    # ── 2. Process next clip from Dump ────────────────────────────────────────
    files   = list_video_files(svc, DUMP_FOLDER_ID)
    pending = [f for f in files if f['id'] not in done_ids]

    if list_mode:
        uq_count = len(uq_files)
        if uq_count:
            print(f"{uq_count} clip(s) in 7 - Upload Queue/ (quota retry)\n")
        if not pending:
            print("1 - Dump/ is empty")
            return
        print(f"{len(pending)} pending clip(s) in Dump:\n")
        for f in pending:
            meta  = f.get('videoMediaMetadata', {})
            w, h  = meta.get('width', '?'), meta.get('height', '?')
            sq    = is_square(f)
            label = 'square' if sq is True else ('non-square' if sq is False else 'no metadata yet')
            size  = int(f.get('size', 0)) / 1024 / 1024
            print(f"  {f['name']}  {w}x{h}  {size:.0f} MB  [{label}]")
        return

    if not pending:
        print("DUMP_EMPTY")
        return

    clip = next((f for f in pending if is_square(f) is not None), None)
    if clip is None:
        print(f"  {len(pending)} clip(s) waiting for Drive metadata — will retry next run")
        return

    sq      = is_square(clip)
    meta    = clip.get('videoMediaMetadata', {})
    w, h    = meta.get('width', '?'), meta.get('height', '?')
    size_mb = int(clip.get('size', 0)) / 1024 / 1024

    print(f"\n{'[DRY RUN] ' if dry_run else ''}"
          f"  {clip['name']}  ({size_mb:.0f} MB)  {w}x{h}  "
          f"({len(pending) - 1} more in dump)")

    if not sq:
        print(f"  Non-square ({w}x{h}) -> moving to 0 - Unsorted/")
        if not dry_run:
            move_file(svc, clip['id'], DUMP_FOLDER_ID, UNSORTED_ID)
            print("  Moved.")
        return

    publish_at = next_publish_time(state)
    print(f"  Square -> processing for gab2  |  scheduled for {publish_at}")
    if dry_run:
        return

    outcome = run_process(svc, clip, DUMP_FOLDER_ID, publish_at, state, dry_run)
    if outcome == 'done':
        print(f"\n{'--' * 30}")
        print(f"Done -- {len(pending) - 1} clip(s) remaining in dump")


if __name__ == '__main__':
    main()
