#!/usr/bin/env python3
"""
batch_process.py — Process all sessions in gab-drive:_Todo/

Flow per session:
  _Todo/<folder> → _Doing/<folder> → download → process → _Done/<folder>

Add new sessions by dropping folders into gab-drive:_Todo/
On startup, anything stuck in _Doing/ is moved back to _Todo/ for retry.
"""

import json, re, shutil, subprocess, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

FOOTAGE_DIR    = Path('/opt/gab/footage')
PROCESS_SCRIPT = Path(__file__).parent / 'process_session.py'
STATE_FILE     = Path('/tmp/pipeline_state.json')
BATCH_LOG      = Path('/tmp/batch_process.log')
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '')
CF_ACCOUNT_ID  = 'f8a9c8de1fcedb10d25b24325a6f8727'
CF_DB_ID       = '4e23e386-b430-4ffc-bf84-246a4e7bcdd1'
TOKEN_FILE     = Path('/tmp/cf_token.txt')
MIN_FREE_GB    = 30

DRIVE_TODO  = 'gab-drive:_Todo'
DRIVE_DOING = 'gab-drive:_Doing'
DRIVE_DONE  = 'gab-drive:_Done'


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(BATCH_LOG, 'a') as f:
        f.write(line + '\n')


def now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def free_gb():
    return shutil.disk_usage('/').free / 1024**3


def get_cf_token():
    return TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ''


def slugify(name):
    s = name.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:60]


def list_drive_folders(drive_path):
    r = subprocess.run(['rclone', 'lsd', drive_path, '--max-depth', '1'],
                       capture_output=True, text=True)
    folders = []
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 4)
        if len(parts) >= 5:
            folders.append(parts[4])
    return sorted(folders)


def folder_size_gb(drive_path):
    r = subprocess.run(['rclone', 'size', drive_path, '--json'],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get('bytes', 0) / 1024**3
    except Exception:
        return 0


def push_state_d1(state):
    token = get_cf_token()
    if not token:
        return
    try:
        val = json.dumps(state).replace("'", "''")
        sql = f"INSERT OR REPLACE INTO pipeline_state (key, value, updated_at) VALUES ('current', '{val}', datetime('now'));"
        url = f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query'
        body = json.dumps({"sql": sql}).encode()
        req = urllib.request.Request(url, data=body,
              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
              method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            pass
    except Exception as e:
        log(f"  D1 state push error: {e}")


def write_state(sessions):
    state = {
        'updated':     now_iso(),
        'vps_free_gb': round(free_gb(), 1),
        'sessions':    sessions,
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    push_state_d1(state)


def run(cmd, **kwargs):
    log(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def main():
    FOOTAGE_DIR.mkdir(parents=True, exist_ok=True)
    log("Batch starting")

    # Recover anything stuck in _Doing → move back to _Todo
    stuck = list_drive_folders(DRIVE_DOING)
    for folder in stuck:
        log(f"  Recovering stuck folder: {folder} → _Todo/")
        run(['rclone', 'moveto', f"{DRIVE_DOING}/{folder}", f"{DRIVE_TODO}/{folder}"])

    todo = list_drive_folders(DRIVE_TODO)
    if not todo:
        log("Nothing in _Todo/ — done.")
        return

    log(f"Found {len(todo)} folder(s): {todo}")

    # Build initial state
    sessions_state = []
    for folder_name in todo:
        slug    = slugify(folder_name)
        size_gb = folder_size_gb(f"{DRIVE_TODO}/{folder_name}")
        sessions_state.append({
            'name':        folder_name,
            'series':      slug,
            'vault_ia_id': f"gab-raw-{slug}",
            'size_gb':     round(size_gb, 1),
            'status':      'queued',
            'clips':       None,
            'started':     None,
            'finished':    None,
            'error':       None,
        })
    write_state(sessions_state)

    for st in sessions_state:
        folder_name = st['name']
        slug        = st['series']
        vault_ia_id = st['vault_ia_id']
        pub_ia_id   = f"gab-{slug}"
        local_dir   = FOOTAGE_DIR / slug

        log(f"\n{'='*60}")
        log(f"Processing: {folder_name}  ({st['size_gb']:.1f} GB)")

        available = free_gb()
        needed    = st['size_gb'] + MIN_FREE_GB
        if available < needed:
            log(f"  SKIP — need {needed:.0f} GB free, have {available:.0f} GB")
            st['status'] = 'skipped'
            st['error']  = f"need {needed:.0f} GB, have {available:.0f} GB"
            write_state(sessions_state)
            continue

        # _Todo → _Doing
        log(f"  Moving to _Doing/")
        r = run(['rclone', 'moveto', f"{DRIVE_TODO}/{folder_name}", f"{DRIVE_DOING}/{folder_name}"])
        if r.returncode != 0:
            log("  ERROR: could not move to _Doing/"); continue

        # Download
        st['status']  = 'downloading'
        st['started'] = now_iso()
        write_state(sessions_state)
        log(f"  Downloading → {local_dir}")
        r = run(['rclone', 'copy', f"{DRIVE_DOING}/{folder_name}", str(local_dir),
                 '--progress', '--transfers=4'])
        if r.returncode != 0:
            log("  ERROR: download failed — moving back to _Todo/")
            st['status'] = 'error'
            st['error']  = 'rclone copy failed'
            run(['rclone', 'moveto', f"{DRIVE_DOING}/{folder_name}", f"{DRIVE_TODO}/{folder_name}"])
            write_state(sessions_state)
            continue

        n_files = sum(1 for _ in local_dir.rglob('*') if _.is_file())
        st['clips'] = n_files
        log(f"  Downloaded {n_files} file(s)  ({free_gb():.1f} GB free)")

        # Process
        st['status'] = 'processing'
        write_state(sessions_state)
        token = get_cf_token()
        cmd = [
            'python3', str(PROCESS_SCRIPT), str(local_dir),
            '--vault-ia-id',   vault_ia_id,
            '--pub-ia-id',     pub_ia_id,
            '--pub-title',     folder_name,
            '--series',        slug,
            '--context',       folder_name,
            '--openrouter-key', OPENROUTER_KEY,
        ]
        if token:
            cmd += ['--cf-api-token', token]
        run(cmd)

        # _Doing → _Done
        st['status'] = 'moving'
        write_state(sessions_state)
        run(['rclone', 'moveto', f"{DRIVE_DOING}/{folder_name}", f"{DRIVE_DONE}/{folder_name}"])

        # Delete local
        log(f"  Deleting local {local_dir}")
        shutil.rmtree(local_dir, ignore_errors=True)

        st['status']   = 'done'
        st['finished'] = now_iso()
        write_state(sessions_state)
        log(f"  Done. {free_gb():.1f} GB free")

    log(f"\n{'='*60}")
    log("Batch complete.")


if __name__ == '__main__':
    main()
