#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_publisher.py -- detect shooting sessions in Z:\\01- Media files,
stitch each one into a single high-quality video, add ambient music, upload to YouTube.

Usage:
  python session_publisher.py --scan              scan Z: drive, detect all sessions
  python session_publisher.py --status            show progress table (default)
  python session_publisher.py --process           stitch + save/upload next pending session
  python session_publisher.py --process --all     process all pending sessions in order
  python session_publisher.py --session ID        process one specific session by ID
  python session_publisher.py --encode-only       save to Z:\\gab-ae-vod, skip upload
  python session_publisher.py --dry-run --scan    dry-run: show what would be detected
"""

import argparse
import io
import json
import os
import random
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

# Force UTF-8 output
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(r"C:\gab-ae")
SOURCE_ROOT  = Path(r"Z:\01- Media files")
OUTPUT_DIR   = BASE_DIR / "output" / "sessions"
WORK_DIR     = BASE_DIR / "work" / "sessions"
VOD_DIR      = Path(r"Z:\gab-ae-vod")
MUSIC_LIST   = BASE_DIR / "music" / "music_list.txt"
MUSIC_BG     = BASE_DIR / "music" / "background.mp3"
MUSIC_BG_NAS = Path(r"Z:\gab-ae-setup\background.mp3")
FFMPEG       = r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE      = r"C:\ffmpeg\bin\ffprobe.exe"
TOKEN_FILE   = BASE_DIR / "token_youtube.json"
SECRETS_FILE = BASE_DIR / "client_secrets.json"

SESSION_GAP_HOURS = 3
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.mts', '.m4v', '.m2ts'}


# ── Helpers ────────────────────────────────────────────────────────────────────

def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024: return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def human_dur(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f'{h}h{m:02d}m' if h else f'{m}m{s:02d}s'


def bar(pct, width=25):
    filled = int(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


# ── Music ──────────────────────────────────────────────────────────────────────

def load_music_paths():
    def readable(p):
        try: return p.is_file() and os.access(p, os.R_OK)
        except OSError: return False

    if not MUSIC_LIST.exists():
        return [str(MUSIC_BG)] if readable(MUSIC_BG) else []
    paths = []
    for line in MUSIC_LIST.read_text(encoding='utf-8').splitlines():
        m = re.match(r"^file\s+'(.+)'$", line.strip())
        if m:
            p = Path(m.group(1))
            if readable(p): paths.append(str(p))
    if not paths:
        for fallback in (MUSIC_BG, MUSIC_BG_NAS):
            if readable(fallback): paths.append(str(fallback)); break
    return paths


# ── FFprobe / FFmpeg ───────────────────────────────────────────────────────────

def get_duration(path):
    r = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_format', str(path)],
        capture_output=True, text=True)
    try: return float(json.loads(r.stdout).get('format', {}).get('duration', 0))
    except Exception: return 0.0


def run_ffmpeg(cmd, label='', total_secs=None):
    proc = subprocess.Popen(
        cmd + ['-progress', 'pipe:1', '-nostats'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    stderr_lines = []
    t = threading.Thread(target=lambda: [stderr_lines.append(l) for l in proc.stderr], daemon=True)
    t.start()

    out_time, last_print = 0.0, ''
    for line in proc.stdout:
        line = line.strip()
        if line.startswith('out_time_ms='):
            try: out_time = int(line.split('=')[1]) / 1_000_000
            except Exception: pass
        if line == 'progress=end':
            print(f'  {label}  done         ', end='\r'); break
        if out_time > 0 and total_secs:
            pct = min(99, int(out_time / total_secs * 100))
            msg = f'  {label}  [{bar(pct)}] {pct}%  {human_dur(out_time)}'
            if msg != last_print: print(msg, end='\r'); last_print = msg

    proc.wait(); t.join(); print()
    if proc.returncode != 0:
        raise RuntimeError(''.join(stderr_lines[-20:])[-400:].strip())
    return True


# ── Session detection ──────────────────────────────────────────────────────────

def parse_location(folder_name):
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s*[-–]\s*(.+)$', folder_name)
    return m.group(1).strip() if m else folder_name


def collect_videos(folder):
    files = []
    for p in Path(folder).rglob('*'):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            try: files.append((p.stat().st_mtime, p))
            except Exception: pass
    return sorted(files)


def split_sessions(files, gap_hours=SESSION_GAP_HOURS):
    if not files: return []
    sessions, current = [], [files[0]]
    for mtime, path in files[1:]:
        if mtime - current[-1][0] > gap_hours * 3600:
            sessions.append(current); current = [(mtime, path)]
        else:
            current.append((mtime, path))
    sessions.append(current)
    return sessions


def make_session_id(folder_name, start_mtime):
    date_str = datetime.fromtimestamp(start_mtime).strftime('%Y%m%d_%H%M')
    slug = re.sub(r'[^\w]+', '_', folder_name).strip('_')[:40]
    return f'{slug}__{date_str}'


# ── Scan ───────────────────────────────────────────────────────────────────────

def cmd_scan(dry_run=False):
    db.init_db()
    new_count = total_folders = 0
    print(f'Scanning {SOURCE_ROOT} ...\n')

    year_dirs = sorted(p for p in SOURCE_ROOT.iterdir()
                       if p.is_dir() and re.match(r'^\d{4}$', p.name))

    with db.get_conn() as conn:
        existing_ids = {r[0] for r in conn.execute("SELECT id FROM sessions")}

    for year_dir in year_dirs:
        for folder in sorted(year_dir.iterdir()):
            if not folder.is_dir(): continue
            total_folders += 1
            video_files = collect_videos(folder)
            if not video_files: continue
            location = parse_location(folder.name)

            for sess_files in split_sessions(video_files):
                start_mtime = sess_files[0][0]
                end_mtime   = sess_files[-1][0]
                sid = make_session_id(folder.name, start_mtime)
                if sid in existing_ids: continue

                file_paths = [str(p) for _, p in sess_files]
                start_date = datetime.fromtimestamp(start_mtime).strftime('%Y-%m-%d')
                end_date   = datetime.fromtimestamp(end_mtime).strftime('%Y-%m-%d')
                date_label = start_date if start_date == end_date else f'{start_date} to {end_date}'
                total_bytes = sum(p.stat().st_size for _, p in sess_files if p.exists())

                print(f'  + {location:35}  {date_label}  {len(file_paths):3d} clips  {human_size(total_bytes)}')

                if not dry_run:
                    db.upsert_session(sid,
                        folder=str(folder), folder_name=folder.name,
                        location=location, date=start_date, date_label=date_label,
                        file_count=len(file_paths), total_bytes=total_bytes,
                        files=json.dumps(file_paths),
                        vod_status=db.VOD_PENDING, stream_status=db.STREAM_PENDING,
                        ts_found=db.ts())
                new_count += 1

    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    print(f'\n{"[dry-run] " if dry_run else ""}'
          f'{total_folders} folders scanned, {new_count} new sessions added. '
          f'Total: {total}')


# ── Status ─────────────────────────────────────────────────────────────────────

def cmd_status():
    if not db.DB_PATH.exists():
        print('No database yet. Run --scan first.')
        return

    with db.get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if not total:
            print('No sessions. Run --scan first.'); return

        print()
        print(f'  {"PIPELINE":<20}  {"STATUS":<12}  {"COUNT":>6}')
        print('  ' + '─' * 44)
        for label, col, statuses in [
            ('VOD',    'vod_status',    [db.VOD_PENDING, db.VOD_STITCHING, db.VOD_MIXING,
                                         db.VOD_ENCODED, db.VOD_UPLOADED, db.VOD_ERROR]),
            ('Stream', 'stream_status', [db.STREAM_PENDING, db.STREAM_ENCODING,
                                         db.STREAM_READY,   db.STREAM_ERROR]),
        ]:
            for st in statuses:
                n = conn.execute(f"SELECT COUNT(*) FROM sessions WHERE {col}=?", (st,)).fetchone()[0]
                if n: print(f'  {label:<20}  {st:<12}  {n:>6}')

        n_ready = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE vod_status=? AND youtube_url IS NULL",
            (db.VOD_ENCODED,)).fetchone()[0]

        print(f'\n  Total: {total}   Ready to upload: {n_ready}')

        errors = conn.execute(
            "SELECT location, date, vod_error FROM sessions WHERE vod_status=?",(db.VOD_ERROR,)
        ).fetchall()
        if errors:
            print(f'\n  Errors ({len(errors)}):')
            for e in errors[:5]:
                print(f'    ✗ {e["location"][:35]:<35}  {e["date"]}  {(e["vod_error"] or "")[:60]}')

        pending = conn.execute(
            "SELECT location, date_label, file_count, total_bytes FROM sessions "
            "WHERE vod_status=? ORDER BY date LIMIT 10", (db.VOD_PENDING,)
        ).fetchall()
        if pending:
            n_pending = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE vod_status=?", (db.VOD_PENDING,)
            ).fetchone()[0]
            total_bytes = conn.execute(
                "SELECT SUM(total_bytes) FROM sessions WHERE vod_status=?", (db.VOD_PENDING,)
            ).fetchone()[0] or 0
            print(f'\n  VOD pending ({n_pending}, {human_size(total_bytes)} total):')
            for r in pending:
                print(f'    • {r["location"][:32]:<32}  {r["date_label"]:<25}  '
                      f'{r["file_count"]:3d} clips  {human_size(r["total_bytes"])}')
            if n_pending > 10: print(f'    ... and {n_pending - 10} more')
        print()


# ── Stitch + mix ───────────────────────────────────────────────────────────────

def stitch(files, out_path):
    concat_txt = str(out_path) + '.concat.txt'
    with open(concat_txt, 'w', encoding='utf-8') as f:
        for p in files:
            f.write(f"file '{str(p).replace(chr(92), '/').replace(chr(39), chr(92)+chr(39))}'\n")

    total_secs = sum(get_duration(p) for p in files)
    print(f'  Stitching {len(files)} clip(s)  (~{human_dur(total_secs)} total)')
    base_cmd = [FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt]
    try:
        run_ffmpeg(base_cmd + ['-c:v', 'copy', '-an', str(out_path)],
                   label='stitch (copy)', total_secs=total_secs)
    except RuntimeError:
        out_path.unlink(missing_ok=True)
        print('  Stream copy failed, re-encoding at CRF 18...')
        run_ffmpeg(base_cmd + ['-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
                                '-pix_fmt', 'yuv420p', '-an', str(out_path)],
                   label='stitch (encode)', total_secs=total_secs)
    Path(concat_txt).unlink(missing_ok=True)
    print(f'  Stitched: {human_size(out_path.stat().st_size)}, {human_dur(get_duration(out_path))}')


def mix_music(video_path, out_path):
    music_paths = load_music_paths()
    if not music_paths:
        raise RuntimeError('No music files found')
    music = random.choice(music_paths)
    vid_dur = get_duration(video_path)
    music_dur = get_duration(music)
    offset = random.uniform(0, max(0.0, music_dur - vid_dur - 30))
    print(f'  Music: {Path(music).stem}  (offset {offset:.0f}s)')
    run_ffmpeg([FFMPEG, '-y',
        '-i', str(video_path),
        '-ss', str(offset), '-stream_loop', '-1', '-i', music,
        '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k', '-ar', '44100',
        '-t', str(vid_dur), '-movflags', '+faststart', str(out_path)],
        label='mix music', total_secs=vid_dur)
    print(f'  Final: {human_size(out_path.stat().st_size)}')


# ── YouTube upload ─────────────────────────────────────────────────────────────

def make_title(location, date_label):
    try:
        d = datetime.strptime(date_label[:10], '%Y-%m-%d')
        months = ['January','February','March','April','May','June',
                  'July','August','September','October','November','December']
        date_str = f'{months[d.month-1]} {d.year}'
    except Exception:
        date_str = date_label
    return f'{location} | {date_str} | Ambient'


def make_description(title):
    return (f'{title}\n\nGab\'s Adventures — travel, walks, and life on the road.\n'
            'No commentary, just the footage with ambient music.\n\n'
            'Subscribe: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w\n\n'
            '#travel #slowtv #adventure #walkingtour #ambient')


def upload_youtube(file_path, title, description, private=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    SCOPES = ['https://www.googleapis.com/auth/youtube']
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRETS_FILE.exists():
                raise RuntimeError(f'client_secrets.json not found at {SECRETS_FILE}')
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    youtube = build('youtube', 'v3', credentials=creds)
    body = {
        'snippet': {'title': title, 'description': description,
                    'tags': ['travel','slowtv','walkingvlog','adventure','ambient','4k'],
                    'categoryId': '19'},
        'status': {'privacyStatus': 'private' if private else 'public',
                   'selfDeclaredMadeForKids': False},
    }
    file_size = Path(file_path).stat().st_size
    media = MediaFileUpload(str(file_path), chunksize=50*1024*1024, resumable=True)
    req = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response, last_pct = None, -1
    while response is None:
        status_obj, response = req.next_chunk()
        if status_obj:
            pct = int(status_obj.progress() * 100)
            if pct != last_pct:
                mb = int(status_obj.progress() * file_size) // (1024*1024)
                print(f'  [{bar(pct)}] {pct}%  ({mb}/{file_size//(1024*1024)} MB)', end='\r')
                last_pct = pct
    print()
    return response['id']


# ── Upload already-encoded sessions ───────────────────────────────────────────

def upload_encoded(private=False, dry_run=False):
    """Upload sessions that are already encoded (vod_status=encoded, no youtube_url)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE vod_status=? AND youtube_url IS NULL ORDER BY date",
            (db.VOD_ENCODED,)
        ).fetchall()

    print(f'\n  {len(rows)} session(s) to upload.')

    ok = err = 0
    for row in rows:
        sid  = row['id']
        path = Path(row['vod_file']) if row['vod_file'] else None

        print(f'\n{"=" * 65}')
        print(f'  Location : {row["location"]}')
        print(f'  Date     : {row["date_label"]}')
        print(f'  File     : {path}')

        if not path or not path.exists():
            print(f'  SKIP: file missing — {path}')
            err += 1
            continue

        title = make_title(row['location'], row['date_label'])
        desc  = make_description(title)
        print(f'  Uploading ({"private" if private else "public"}): {title}')

        if dry_run:
            print('  [dry-run] would upload'); ok += 1; continue

        try:
            vid_id = upload_youtube(path, title, desc, private=private)
            url    = f'https://www.youtube.com/watch?v={vid_id}'
        except Exception as e:
            db.vod_set_status(sid, db.VOD_ERROR, error=f'Upload: {str(e)[:250]}')
            print(f'  UPLOAD ERROR: {e}')
            err += 1
            continue

        db.vod_set_uploaded(sid, url, vid_id)

        # Move to Uploaded subfolder
        uploaded_dir = path.parent / 'Uploaded'
        uploaded_dir.mkdir(exist_ok=True)
        dest = uploaded_dir / path.name
        path.rename(dest)
        db.upsert_session(sid, vod_file=str(dest))
        print(f'  YouTube: {url}')
        print(f'  Moved  : {dest}')
        ok += 1

    print(f'\nDone: {ok} uploaded, {err} errors.')


# ── Process one session ────────────────────────────────────────────────────────

def process_one(sid, encode_only=False, vod_dir=None, dry_run=False, private=False):
    row = db.get_session(sid)
    if not row:
        print(f'Session not found: {sid}'); return False

    print(f'\n{"=" * 65}')
    print(f'  Location : {row["location"]}')
    print(f'  Date     : {row["date_label"]}')
    print(f'  Folder   : {row["folder"]}')
    print(f'  Clips    : {row["file_count"]}  ({human_size(row["total_bytes"])})')
    print(f'  Mode     : {"encode-only -> " + str(vod_dir or VOD_DIR) if encode_only else "stitch + upload"}')
    print(f'{"=" * 65}')

    if dry_run:
        print(f'  [dry-run] would stitch -> mix -> '
              f'{"save to " + str(vod_dir or VOD_DIR) if encode_only else "upload"}')
        return True

    dest_dir = Path(vod_dir) if vod_dir else VOD_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if encode_only: dest_dir.mkdir(parents=True, exist_ok=True)

    safe = re.sub(r'[^\w\-]', '_', f'{row["date"]}_{row["location"]}')[:80]
    stitched_path = WORK_DIR / f'{safe}__stitched.mp4'
    final_path    = (dest_dir if encode_only else OUTPUT_DIR) / f'{safe}.mp4'

    files = db.get_files(sid)
    existing = [p for p in files if Path(p).exists()]
    missing  = len(files) - len(existing)
    if not existing:
        db.vod_set_status(sid, db.VOD_ERROR, error='All source files missing (Z: not mounted?)')
        print('  ERROR: no source files found. Is Z: mounted?')
        return False
    if missing:
        print(f'  Warning: {missing} file(s) missing — stitching {len(existing)} available')

    # ── 1. Stitch ────────────────────────────────────────────────────────────────
    db.vod_set_status(sid, db.VOD_STITCHING)
    try:
        if stitched_path.exists() and stitched_path.stat().st_size > 0:
            print(f'  Stitch already done ({human_dur(get_duration(stitched_path))}) — skipping')
        else:
            stitch(existing, stitched_path)
    except Exception as e:
        db.vod_set_status(sid, db.VOD_ERROR, error=f'Stitch: {str(e)[:250]}')
        print(f'\n  STITCH ERROR: {e}')
        stitched_path.unlink(missing_ok=True)
        return False

    # ── 2. Mix music ─────────────────────────────────────────────────────────────
    db.vod_set_status(sid, db.VOD_MIXING)
    try:
        if final_path.exists() and final_path.stat().st_size > 0:
            print(f'  Mix already done ({human_size(final_path.stat().st_size)}) — skipping')
        else:
            mix_music(stitched_path, final_path)
        stitched_path.unlink(missing_ok=True)
    except Exception as e:
        db.vod_set_status(sid, db.VOD_ERROR, error=f'Mix: {str(e)[:250]}')
        print(f'\n  MIX ERROR: {e}')
        return False

    if encode_only:
        # ── 3a. Save to disk ──────────────────────────────────────────────────────
        db.vod_set_status(sid, db.VOD_ENCODED, vod_file=str(final_path))
        print(f'\n  Saved: {final_path}  ({human_size(final_path.stat().st_size)})')
        print('  Done!')
        return True

    # ── 3b. Upload ────────────────────────────────────────────────────────────────
    title = make_title(row['location'], row['date_label'])
    desc  = make_description(title)
    print(f'  Uploading ({"private" if private else "public"}): {title}')
    try:
        vid_id = upload_youtube(final_path, title, desc, private=private)
        url    = f'https://www.youtube.com/watch?v={vid_id}'
    except Exception as e:
        db.vod_set_status(sid, db.VOD_ERROR, error=f'Upload: {str(e)[:250]}')
        print(f'\n  UPLOAD ERROR: {e}')
        return False

    db.vod_set_uploaded(sid, url, vid_id)

    # Move to Uploaded subfolder
    uploaded_dir = final_path.parent / 'Uploaded'
    uploaded_dir.mkdir(exist_ok=True)
    dest = uploaded_dir / final_path.name
    final_path.rename(dest)
    db.upsert_session(sid, vod_file=str(dest))
    print(f'\n  YouTube: {url}')
    print(f'  Moved  : {dest}')
    print('  Done!')
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Detect sessions and publish to YouTube')
    ap.add_argument('--scan',        action='store_true')
    ap.add_argument('--status',      action='store_true')
    ap.add_argument('--process',     action='store_true')
    ap.add_argument('--all',         action='store_true')
    ap.add_argument('--count',       type=int, default=1)
    ap.add_argument('--session',     default=None)
    ap.add_argument('--private',     action='store_true')
    ap.add_argument('--encode-only',  action='store_true')
    ap.add_argument('--upload-only',  action='store_true', help='Upload already-encoded VOD files')
    ap.add_argument('--vod-dir',      default=None)
    ap.add_argument('--dry-run',      action='store_true')
    args = ap.parse_args()

    db.init_db()

    if args.scan:
        cmd_scan(dry_run=args.dry_run); return

    if args.upload_only:
        upload_encoded(private=args.private, dry_run=args.dry_run); return

    if args.status or not any([args.process, args.session]):
        cmd_status(); return

    if args.session:
        to_process = [args.session]
    else:
        skip = {db.VOD_ENCODED, db.VOD_UPLOADED} if args.encode_only else {db.VOD_UPLOADED}
        with db.get_conn() as conn:
            rows = conn.execute(
                f"SELECT id FROM sessions WHERE vod_status NOT IN "
                f"({','.join('?'*len(skip))}) ORDER BY date",
                list(skip)
            ).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            print('No pending sessions.'); return
        to_process = ids if args.all else ids[:args.count]

    ok = err = 0
    for sid in to_process:
        success = process_one(sid, encode_only=args.encode_only,
                              vod_dir=args.vod_dir, dry_run=args.dry_run,
                              private=args.private)
        if success: ok += 1
        else:
            err += 1
            if not args.all:
                print(f'\nStopped on error. Retry with:  python session_publisher.py --session "{sid}"')
                break

    if len(to_process) > 1:
        print(f'\nBatch done: {ok} completed, {err} errors.')
    cmd_status()


if __name__ == '__main__':
    main()
