#!/usr/bin/env python3
"""
Long-form upload scheduler — reads ready_long_queue.json, uploads ONE processed
long-form video to YouTube per run, scheduled 24 hours after the last published slot.

  - Quota error  →  stays in queue, retries next run
  - Success      →  moves Drive folder 4 - Review/ → 5 - Published/, deletes local file

Cron (every 5 min):
  */5 * * * * python3 /opt/gab/footage/upload_long.py >> /var/log/gab/pipeline_long.log 2>&1

Manual:
  python3 upload_long.py           # upload next ready long-form video
  python3 upload_long.py --list    # show ready queue
  python3 upload_long.py --status  # show full state summary
"""

import json
import os
import sys
import time
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DRIVE_TOKEN   = '/opt/gab/footage/token.json'
YT_TOKEN_GAB2 = '/opt/gab/channel-uc59/token.json'
REVIEW_ID     = '1SG8dpXogB90OKojNZgTmPCjOryoJqv01'   # 4 - Review/
PUBLISHED_ID  = '1Hlnqh4sKTXHA2cfq9B1inNG6l8zbiQWU'   # 5 - Published/
READY_QUEUE   = '/opt/gab/footage/ready_long_queue.json'
STATE_FILE    = '/opt/gab/footage/pipeline_long_state.json'

QUOTA_ERRORS  = ('uploadLimitExceeded', 'forbidden', 'quotaExceeded')

# 24 hours between long-form videos
PUBLISH_INTERVAL_SECS = 24 * 3600


def drive_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def yt_service():
    creds = Credentials.from_authorized_user_file(YT_TOKEN_GAB2)
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def move_folder(svc, folder_id, from_parent, to_parent):
    svc.files().update(
        fileId=folder_id,
        addParents=to_parent,
        removeParents=from_parent,
        fields='id',
    ).execute()


def load_queue():
    p = Path(READY_QUEUE)
    return json.loads(p.read_text()) if p.exists() else []


def save_queue(queue):
    Path(READY_QUEUE).write_text(json.dumps(queue, indent=2))


def load_state():
    p = Path(STATE_FILE)
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def next_publish_time(state):
    last = state.get('next_publish_at')
    now  = time.time()
    if last:
        last_epoch = time.mktime(time.strptime(last, '%Y-%m-%dT%H:%M:%S.000Z'))
        base = max(last_epoch, now)
    else:
        base = now
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(base + PUBLISH_INTERVAL_SECS))


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def upload_to_youtube(video_path, title, description, publish_at, unlisted=False):
    svc = yt_service()
    if unlisted:
        print(f"  Privacy: unlisted")
        status_body = {'privacyStatus': 'unlisted'}
    else:
        print(f"  Scheduled for: {publish_at}")
        status_body = {'privacyStatus': 'private', 'publishAt': publish_at}
    body = {
        'snippet': {
            'title':       title,
            'description': description,
            'tags':        ['paris', 'travel', 'france', 'vlog', '4k'],
            'categoryId':  '19',   # Travel & Events
        },
        'status': status_body,
    }
    media   = MediaFileUpload(video_path, mimetype='video/mp4', resumable=True, chunksize=32*1024*1024)
    request = svc.videos().insert(part='snippet,status', body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload: {int(status.progress() * 100)}%", end='\r')
    print()
    return response['id']


def main():
    list_mode   = '--list'   in sys.argv
    status_mode = '--status' in sys.argv

    queue = load_queue()
    state = load_state()

    if status_mode:
        pending   = [e for e in queue if not e.get('uploaded')]
        completed = [e for e in queue if e.get('uploaded')]
        print(f"Ready to upload : {len(pending)} long-form video(s)")
        print(f"Uploaded        : {len(completed)} long-form video(s)")
        print(f"Next slot       : {state.get('next_publish_at', 'not set')}")
        print()
        for e in pending:
            size_mb = os.path.getsize(e['local_file']) / 1024 / 1024 if Path(e.get('local_file', '')).exists() else 0
            print(f"  [ ] {e['title']}  ({size_mb:.0f} MB)  ({e.get('ts_processed', '?')})")
        for e in completed[-5:]:
            print(f"  [x] {e['title']} → {e.get('youtube_url', '?')}")
        return

    pending = [e for e in queue if not e.get('uploaded')]

    if list_mode:
        if not pending:
            print("Ready queue is empty — nothing to upload")
            return
        print(f"{len(pending)} long-form video(s) ready to upload:\n")
        for e in pending:
            local = e.get('local_file', '?')
            exists = Path(local).exists() if local != '?' else False
            size_mb = os.path.getsize(local) / 1024 / 1024 if exists else 0
            print(f"  {e['title']}")
            print(f"    file : {local} ({'ok — {:.0f} MB'.format(size_mb) if exists else 'MISSING'})")
            print(f"    added: {e.get('ts_processed', '?')}")
        return

    if not pending:
        print("QUEUE_EMPTY — nothing to upload")
        return

    entry      = pending[0]
    local_file = entry.get('local_file', '')

    if not Path(local_file).exists():
        print(f"  ERROR: local file missing: {local_file}")
        print(f"  Remove this entry from ready_long_queue.json and reprocess the folder.")
        sys.exit(1)

    is_meta = entry.get('type', '').startswith('meta_preview')
    publish_at = next_publish_time(state)
    size_mb    = os.path.getsize(local_file) / 1024 / 1024

    print(f"\n  {entry['title']}")
    print(f"  File   : {local_file}  ({size_mb:.0f} MB)")
    print(f"  Slot   : {'unlisted' if is_meta else publish_at}")
    print(f"  Queue  : {len(pending) - 1} more after this")

    try:
        yt_id  = upload_to_youtube(
            local_file,
            entry['title'],
            entry.get('description', ''),
            publish_at,
            unlisted=is_meta,
        )
        yt_url = f"https://www.youtube.com/watch?v={yt_id}"
    except Exception as e:
        err = str(e)
        if any(q in err for q in QUOTA_ERRORS):
            print(f"\n  YouTube quota exceeded — will retry next run")
        else:
            print(f"\n  Upload error: {err[:200]}")
        sys.exit(1)

    # Move Drive folder 4 - Review/ → 5 - Published/
    folder_id = entry.get('drive_folder_id') or entry.get('drive_id', '')
    try:
        svc = drive_service()
        move_folder(svc, folder_id, REVIEW_ID, PUBLISHED_ID)
        print(f"  Moved to 5 - Published/ in Drive")
    except Exception as e:
        print(f"  Warning: Drive move failed: {e}")

    # Delete local processed file
    try:
        Path(local_file).unlink()
        print(f"  Deleted local file")
    except Exception:
        pass

    # Mark only this specific entry as uploaded (match by local_file path)
    for e in queue:
        if e.get('local_file') == local_file:
            e['uploaded']    = True
            e['youtube_url'] = yt_url
            e['publish_at']  = publish_at
            e['ts_uploaded'] = ts()
    save_queue(queue)

    state['next_publish_at'] = publish_at
    state.setdefault('done', []).append({
        'id':          folder_id,
        'name':        entry.get('folder_name', entry.get('name', '')),
        'title':       entry['title'],
        'youtube_url': yt_url,
        'publish_at':  publish_at,
        'ts':          ts(),
    })
    save_state(state)

    print(f"\n  Done!")
    print(f"  YouTube : {yt_url}")
    print(f"  Next slot will be: {next_publish_time(state)}")


if __name__ == '__main__':
    main()
