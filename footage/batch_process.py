#!/usr/bin/env python3
"""
batch_process.py — Process all unprocessed footage sessions from Google Drive.

For each session in SESSIONS (in order):
  1. Check VPS free disk — skip if not enough headroom
  2. rclone copy Drive folder → /opt/gab/footage/<local_name>/
  3. Run process_session.py (vault upload + grade + publish)
  4. rclone moveto Drive folder → _Done/<folder>
  5. Delete local copy

Run on VPS:
  python3 /opt/gab/gab-adventures/footage/batch_process.py
  nohup python3 /opt/gab/gab-adventures/footage/batch_process.py > /tmp/batch_process.log 2>&1 &
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OPENROUTER_KEY = '${OPENROUTER_API_KEY}'
CF_API_TOKEN   = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN') or ''
CF_ACCOUNT_ID  = 'f8a9c8de1fcedb10d25b24325a6f8727'
CF_DB_ID       = '4e23e386-b430-4ffc-bf84-246a4e7bcdd1'
SCRIPT_DIR     = Path(__file__).parent
PROCESS_SCRIPT = SCRIPT_DIR / 'process_session.py'
FOOTAGE_DIR    = Path('/opt/gab/footage')
MIN_FREE_GB    = 10
STATE_FILE     = Path('/tmp/pipeline_state.json')

# Sessions to process, in order.
# drive_folder: exact name in Google Drive root
# local_name:   local subfolder name under /opt/gab/footage/
# vault_ia_id:  Internet Archive item ID for raw private backup
# pub_ia_id:    Internet Archive item ID for public long-form
# pub_title:    human-readable title for the long-form
# series:       gab.ae series slug
# context:      location context for AI tagging
SESSIONS = [
    {
        'drive_folder': '2026-05-09 - Phone, Paris, France',
        'local_name':   'phone-paris-may9',
        'vault_ia_id':  'gab-raw-phone-paris-may9',
        'pub_ia_id':    'gab-phone-paris-may9',
        'pub_title':    'Paris — Phone, May 9, 2026',
        'series':       'phone-paris-may9',
        'context':      'Paris, France, May 2026',
        'size_gb':      1.4,
    },
    {
        'drive_folder': '2026-05-09 Action cam, Paris, France',
        'local_name':   'action-cam-paris-may9',
        'vault_ia_id':  'gab-raw-action-cam-paris-may9',
        'pub_ia_id':    'gab-action-cam-paris-may9',
        'pub_title':    'Paris — Action Cam, May 9, 2026',
        'series':       'action-cam-paris-may9',
        'context':      'Paris, France, May 2026',
        'size_gb':      20,
    },
    {
        'drive_folder': '2026-05-03 - Action cam Paris',
        'local_name':   'action-cam-paris-may3',
        'vault_ia_id':  'gab-raw-action-cam-paris-may3',
        'pub_ia_id':    'gab-action-cam-paris-may3',
        'pub_title':    'Paris — Action Cam, May 3, 2026',
        'series':       'action-cam-paris-may3',
        'context':      'Paris, France, May 2026',
        'size_gb':      22,
    },
    {
        'drive_folder': '2026-04-30 - Square action cam 6 footage',
        'local_name':   'action-cam-apr30',
        'vault_ia_id':  'gab-raw-action-cam-apr30',
        'pub_ia_id':    'gab-action-cam-apr30',
        'pub_title':    'Paris — Action Cam, April 30, 2026',
        'series':       'action-cam-apr30',
        'context':      'Paris, France, April 2026',
        'size_gb':      30,
    },
    {
        'drive_folder': '2026-05-01 - Square action cam 6 footage',
        'local_name':   'action-cam-may1-square',
        'vault_ia_id':  'gab-raw-action-cam-may1-sq',
        'pub_ia_id':    'gab-action-cam-may1-sq',
        'pub_title':    'Paris — Action Cam Square, May 1, 2026',
        'series':       'action-cam-may1-sq',
        'context':      'Paris, France, May 2026',
        'size_gb':      36,
    },
    {
        'drive_folder': '2026-03-02 - Gab phone',
        'local_name':   'gab-phone-mar2',
        'vault_ia_id':  'gab-raw-phone-mar2',
        'pub_ia_id':    'gab-phone-mar2',
        'pub_title':    'Gab — Phone, March 2, 2026',
        'series':       'gab-phone-mar2',
        'context':      'Montreal or Paris, early 2026',
        'size_gb':      10,
    },
    # Large sessions — need ~150 GB free each; expand VPS disk first
    {
        'drive_folder': '2026-04-27 - DJI Gab',
        'local_name':   'dji-gab-apr27',
        'vault_ia_id':  'gab-raw-dji-apr27',
        'pub_ia_id':    'gab-dji-apr27',
        'pub_title':    'Paris — DJI, April 27, 2026',
        'series':       'dji-apr27',
        'context':      'Paris, France, April 2026 — DJI drone/gimbal footage',
        'size_gb':      140,
    },
    {
        'drive_folder': '2026-05-01 - Action cam not squared',
        'local_name':   'action-cam-may1-wide',
        'vault_ia_id':  'gab-raw-action-cam-may1-wide',
        'pub_ia_id':    'gab-action-cam-may1-wide',
        'pub_title':    'Paris — Action Cam Wide, May 1, 2026',
        'series':       'action-cam-may1-wide',
        'context':      'Paris, France, May 2026',
        'size_gb':      115,
    },
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def free_gb():
    return shutil.disk_usage('/').free / 1024 ** 3


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def run(cmd, **kwargs):
    log(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def write_state(sessions_state):
    state = {
        'updated':    now_iso(),
        'vps_free_gb': round(free_gb(), 1),
        'sessions':   sessions_state,
    }
    state_json = json.dumps(state, indent=2)
    STATE_FILE.write_text(state_json)
    _write_state_d1(state_json)


def _write_state_d1(state_json):
    if not CF_API_TOKEN:
        return
    sql    = "INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) VALUES ('current', ?, datetime('now'))"
    url    = f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query'
    body   = json.dumps({'sql': sql, 'params': [state_json]}).encode()
    req    = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Authorization', f'Bearer {CF_API_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if not result.get('success'):
                log(f'  [state] D1 write error: {result.get("errors")}')
    except Exception as e:
        log(f'  [state] D1 write failed: {e}')


def main():
    FOOTAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Build initial state — all queued
    sessions_state = []
    for s in SESSIONS:
        sessions_state.append({
            'name':         s['drive_folder'],
            'series':       s['series'],
            'vault_ia_id':  s['vault_ia_id'],
            'size_gb':      s['size_gb'],
            'status':       'queued',
            'clips':        None,
            'started':      None,
            'finished':     None,
            'error':        None,
        })
    write_state(sessions_state)

    total = len(SESSIONS)
    for i, s in enumerate(SESSIONS, 1):
        st = sessions_state[i - 1]
        log(f"\n{'='*60}")
        log(f"[{i}/{total}] {s['drive_folder']}  ({s['size_gb']:.0f} GB)")

        available = free_gb()
        needed    = s['size_gb'] + MIN_FREE_GB
        if available < needed:
            log(f"  SKIP — need {needed:.0f} GB free, have {available:.0f} GB")
            st['status'] = 'skipped'
            st['error']  = f"need {needed:.0f} GB, have {available:.0f} GB"
            write_state(sessions_state)
            continue

        local_dir  = FOOTAGE_DIR / s['local_name']
        drive_src  = f"gab-drive:{s['drive_folder']}"
        drive_done = f"gab-drive:_Done/{s['drive_folder']}"

        # 1. Download
        st['status']  = 'downloading'
        st['started'] = now_iso()
        write_state(sessions_state)

        log(f"  Downloading {drive_src} → {local_dir}")
        r = run(['rclone', 'copy', drive_src, str(local_dir), '--progress', '--transfers=4'])
        if r.returncode != 0:
            log(f"  ERROR: rclone copy failed — skipping")
            st['status'] = 'error'
            st['error']  = 'rclone copy failed'
            write_state(sessions_state)
            continue

        n_files = sum(1 for _ in local_dir.rglob('*') if _.is_file())
        st['clips'] = n_files
        log(f"  Downloaded {n_files} file(s)  ({free_gb():.1f} GB free remaining)")

        # 2. Process
        st['status'] = 'processing'
        write_state(sessions_state)

        log(f"  Running process_session.py...")
        cmd = [
            'python3', str(PROCESS_SCRIPT),
            str(local_dir),
            '--vault-ia-id',    s['vault_ia_id'],
            '--pub-ia-id',      s['pub_ia_id'],
            '--pub-title',      s['pub_title'],
            '--series',         s['series'],
            '--context',        s['context'],
            '--openrouter-key', OPENROUTER_KEY,
        ] + (['--cf-api-token', CF_API_TOKEN] if CF_API_TOKEN else [])
        r = run(cmd)
        if r.returncode != 0:
            log(f"  WARNING: process_session.py exited {r.returncode} — continuing anyway")

        # 3. Move to _Done in Drive
        st['status'] = 'moving'
        write_state(sessions_state)
        log(f"  Moving Drive folder to _Done/...")
        run(['rclone', 'moveto', drive_src, drive_done])

        # 4. Delete local copy
        log(f"  Deleting local copy {local_dir}")
        shutil.rmtree(local_dir, ignore_errors=True)

        st['status']   = 'done'
        st['finished'] = now_iso()
        write_state(sessions_state)
        log(f"  Done. {free_gb():.1f} GB free")

    sessions_state_final = sessions_state
    log(f"\n{'='*60}")
    log("Batch complete.")


if __name__ == '__main__':
    main()
