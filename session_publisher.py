#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_publisher.py -- detect shooting sessions in Z:\\01- Media files,
stitch each one into a single high-quality video, add ambient music, upload to YouTube.

Each folder may contain footage from MANY different days (e.g. you uploaded a full
SD card at once). This script splits those into per-day sessions automatically by
looking at the gap between file timestamps.

Usage:
  python session_publisher.py --scan              scan Z: drive, detect all sessions
  python session_publisher.py --status            show progress table (default)
  python session_publisher.py --process           stitch + upload next pending session
  python session_publisher.py --process --all     process all pending sessions in order
  python session_publisher.py --session ID        process one specific session by ID
  python session_publisher.py --dry-run --scan    dry-run: show what would be detected

Run --scan once, then --process (or loop it) to publish everything.
"""

import argparse
import io
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 output so Unicode chars (accents, box-drawing) print on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(r"C:\gab-ae")
SOURCE_ROOT = Path(r"Z:\01- Media files")
OUTPUT_DIR  = BASE_DIR / "output" / "sessions"
WORK_DIR    = BASE_DIR / "work" / "sessions"
STATE_FILE  = BASE_DIR / "sessions_state.json"
MUSIC_LIST  = BASE_DIR / "music" / "music_list.txt"
MUSIC_BG    = BASE_DIR / "music" / "background.mp3"
FFMPEG      = r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE     = r"C:\ffmpeg\bin\ffprobe.exe"
TOKEN_FILE  = BASE_DIR / "token_youtube.json"
SECRETS_FILE = BASE_DIR / "client_secrets.json"

# ── Config ─────────────────────────────────────────────────────────────────────
SESSION_GAP_HOURS = 3       # gap that marks a new session
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.mts', '.m4v', '.m2ts'}
SKIP_EXTS  = {'.lrf', '.heic', '.dng', '.jpg', '.jpeg', '.png', '.raw',
              '.arw', '.cr2', '.nef', '.tif', '.tiff', '.xmp', '.aae',
              '.lrcat', '.pdf', '.txt', '.xml', '.srt'}


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {"sessions": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def human_dur(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}h{m:02d}m'
    return f'{m}m{s:02d}s'


def bar(pct, width=25):
    filled = int(pct / 100 * width)
    return '█' * filled + '░' * (width - filled)


# ── Music library ──────────────────────────────────────────────────────────────

def load_music_paths():
    """Parse music_list.txt (ffmpeg concat format) → list of existing file paths."""
    if not MUSIC_LIST.exists():
        return [str(MUSIC_BG)] if MUSIC_BG.exists() else []
    paths = []
    for line in MUSIC_LIST.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        m = re.match(r"^file\s+'(.+)'$", line)
        if m:
            p = Path(m.group(1))
            if p.exists():
                paths.append(str(p))
    if not paths and MUSIC_BG.exists():
        paths.append(str(MUSIC_BG))
    return paths


# ── FFprobe ────────────────────────────────────────────────────────────────────

def get_duration(path):
    r = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_format', str(path)],
        capture_output=True, text=True
    )
    try:
        return float(json.loads(r.stdout).get('format', {}).get('duration', 0))
    except Exception:
        return 0.0


def get_video_codec(path):
    r = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-select_streams', 'v:0', str(path)],
        capture_output=True, text=True
    )
    try:
        streams = json.loads(r.stdout).get('streams', [{}])
        return streams[0].get('codec_name', '') if streams else ''
    except Exception:
        return ''


# ── FFmpeg with live progress ──────────────────────────────────────────────────

def run_ffmpeg(cmd, label='', total_secs=None):
    """Run ffmpeg and show live progress. Returns True on success."""
    # Add progress pipe so we can read real-time stats
    progress_cmd = cmd + ['-progress', 'pipe:1', '-nostats']
    proc = subprocess.Popen(
        progress_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    out_time = 0.0
    last_print = ''
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith('out_time_ms='):
            try:
                out_time = int(line.split('=')[1]) / 1_000_000
            except Exception:
                pass
        if line == 'progress=end':
            print(f'  {label}  done         ', end='\r')
            break
        if out_time > 0 and total_secs and total_secs > 0:
            pct = min(99, int(out_time / total_secs * 100))
            msg = f'  {label}  [{bar(pct)}] {pct}%  {human_dur(out_time)}'
            if msg != last_print:
                print(msg, end='\r')
                last_print = msg

    proc.wait()
    print()
    if proc.returncode != 0:
        err = proc.stderr.read() if proc.stderr else ''
        raise RuntimeError(err[-400:].strip())
    return True


# ── Location parsing ───────────────────────────────────────────────────────────

def parse_location(folder_name):
    """Extract readable location from '2024-01-30 - Multiple day in Sutton and Montreal'."""
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s*[-–]\s*(.+)$', folder_name)
    return m.group(1).strip() if m else folder_name


# ── Session detection ──────────────────────────────────────────────────────────

def collect_videos(folder):
    """Recursively collect video files, sorted by file mtime."""
    files = []
    for p in Path(folder).rglob('*'):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in VIDEO_EXTS:
            try:
                mtime = p.stat().st_mtime
                files.append((mtime, p))
            except Exception:
                pass
        # silently ignore photos and other non-video files
    return sorted(files)


def split_sessions(files, gap_hours=SESSION_GAP_HOURS):
    """Split sorted (mtime, path) list into sessions by time gap."""
    if not files:
        return []
    sessions, current = [], [files[0]]
    gap = gap_hours * 3600
    for mtime, path in files[1:]:
        if mtime - current[-1][0] > gap:
            sessions.append(current)
            current = [(mtime, path)]
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
    state = load_state()
    new_count = 0
    total_folders = 0

    print(f'Scanning {SOURCE_ROOT} ...\n')

    year_dirs = sorted(
        p for p in SOURCE_ROOT.iterdir()
        if p.is_dir() and re.match(r'^\d{4}$', p.name)
    )

    for year_dir in year_dirs:
        for folder in sorted(year_dir.iterdir()):
            if not folder.is_dir():
                continue
            total_folders += 1

            video_files = collect_videos(folder)
            if not video_files:
                continue

            sessions = split_sessions(video_files)
            location = parse_location(folder.name)

            for sess_files in sessions:
                start_mtime = sess_files[0][0]
                end_mtime   = sess_files[-1][0]
                sid = make_session_id(folder.name, start_mtime)

                if sid in state['sessions']:
                    continue  # already tracked

                file_paths = [str(p) for _, p in sess_files]
                start_date = datetime.fromtimestamp(start_mtime).strftime('%Y-%m-%d')
                end_date   = datetime.fromtimestamp(end_mtime).strftime('%Y-%m-%d')
                date_label = start_date if start_date == end_date else f'{start_date} to {end_date}'

                total_bytes = sum(p.stat().st_size for _, p in sess_files if p.exists())

                print(f'  + {location:35}  {date_label}  '
                      f'{len(file_paths):3d} clips  {human_size(total_bytes)}')

                if not dry_run:
                    state['sessions'][sid] = {
                        'folder':      str(folder),
                        'folder_name': folder.name,
                        'location':    location,
                        'date':        start_date,
                        'date_label':  date_label,
                        'files':       file_paths,
                        'file_count':  len(file_paths),
                        'total_bytes': total_bytes,
                        'status':      'pending',
                        'output_file': None,
                        'youtube_url': None,
                        'error':       None,
                        'ts_found':    ts(),
                        'ts_done':     None,
                    }
                new_count += 1

    if not dry_run:
        save_state(state)

    print(f'\n{"[dry-run] " if dry_run else ""}'
          f'{total_folders} folders scanned, {new_count} new sessions {"would be " if dry_run else ""}added.')
    print(f'Total sessions in state: {len(state["sessions"])}')


# ── Status ─────────────────────────────────────────────────────────────────────

def cmd_status():
    state = load_state()
    sessions = state['sessions']

    if not sessions:
        print('No sessions tracked yet. Run:  python session_publisher.py --scan')
        return

    by_status = {}
    for sid, s in sessions.items():
        by_status.setdefault(s['status'], []).append((sid, s))

    print()
    print(f'  {"STATUS":<14}  {"COUNT":>6}')
    print('  ' + '─' * 25)
    for st in ('pending', 'stitching', 'mixing', 'uploading', 'done', 'error'):
        items = by_status.get(st, [])
        if items:
            print(f'  {st:<14}  {len(items):>6}')
    print()

    done = sorted(by_status.get('done', []),
                  key=lambda x: x[1].get('ts_done', ''), reverse=True)
    if done:
        print(f'  Recent uploads ({min(5, len(done))} of {len(done)}):')
        for _, s in done[:5]:
            url = s.get('youtube_url', '—')
            print(f'    ✓ {s["location"][:30]:<30}  {s["date"]}  {url}')
        print()

    errors = by_status.get('error', [])
    if errors:
        print(f'  Errors ({len(errors)}):')
        for _, s in errors[:5]:
            print(f'    ✗ {s["location"][:30]:<30}  {s["date"]}  {s.get("error","")[:70]}')
        print()

    pending = sorted(by_status.get('pending', []), key=lambda x: x[1]['date'])
    if pending:
        total_bytes = sum(s['total_bytes'] for _, s in pending)
        print(f'  Pending ({len(pending)} sessions, {human_size(total_bytes)} total):')
        for _, s in pending[:15]:
            print(f'    • {s["location"][:32]:<32}  {s["date_label"]:<25}  '
                  f'{s["file_count"]:3d} clips  {human_size(s["total_bytes"])}')
        if len(pending) > 15:
            print(f'    ... and {len(pending) - 15} more')
        print()


# ── Stitch ─────────────────────────────────────────────────────────────────────

def stitch(files, out_path):
    """Concatenate video files (lossless copy; fallback re-encode if needed)."""
    concat_txt = str(out_path) + '.concat.txt'
    with open(concat_txt, 'w', encoding='utf-8') as f:
        for p in files:
            # ffmpeg concat list: escape backslashes and single quotes
            safe = str(p).replace('\\', '/').replace("'", r"\'")
            f.write(f"file '{safe}'\n")

    total_secs = sum(get_duration(p) for p in files)
    print(f'  Stitching {len(files)} clip(s)  (~{human_dur(total_secs)} total)')

    base_cmd = [FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt]

    # Try stream copy first (lossless, fast)
    try:
        run_ffmpeg(base_cmd + ['-c:v', 'copy', '-an', str(out_path)],
                   label='stitch (copy)', total_secs=total_secs)
    except RuntimeError as e:
        if out_path.exists():
            out_path.unlink()
        print(f'  Stream copy failed, re-encoding at CRF 18 (this is slower)...')
        run_ffmpeg(base_cmd + [
            '-c:v', 'libx264', '-crf', '18', '-preset', 'slow',
            '-pix_fmt', 'yuv420p', '-an', str(out_path),
        ], label='stitch (encode)', total_secs=total_secs)

    Path(concat_txt).unlink(missing_ok=True)
    size = out_path.stat().st_size
    dur  = get_duration(out_path)
    print(f'  Stitched: {human_size(size)}, {human_dur(dur)}')
    return dur


def mix_music(video_path, out_path):
    """Layer a random ambient track over a muted video."""
    music_paths = load_music_paths()
    if not music_paths:
        raise RuntimeError('No music files found (checked music_list.txt and music/background.mp3)')

    music = random.choice(music_paths)
    track_name = Path(music).stem

    vid_dur   = get_duration(video_path)
    music_dur = get_duration(music)

    # Pick a random start in the music track (stay 30s from the end)
    max_offset = max(0.0, music_dur - vid_dur - 30)
    offset = random.uniform(0, max_offset) if max_offset > 0 else 0.0

    print(f'  Music: {track_name}  (offset {offset:.0f}s)')

    run_ffmpeg([
        FFMPEG, '-y',
        '-i', str(video_path),
        '-ss', str(offset), '-stream_loop', '-1', '-i', music,
        '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '320k', '-ar', '44100',
        '-t', str(vid_dur),
        '-movflags', '+faststart',
        str(out_path),
    ], label='mix music', total_secs=vid_dur)

    size = out_path.stat().st_size
    print(f'  Final:  {human_size(size)}')


# ── Upload ─────────────────────────────────────────────────────────────────────

def make_title(location, date_label):
    try:
        d = datetime.strptime(date_label[:10], '%Y-%m-%d')
        months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        date_str = f'{months[d.month - 1]} {d.year}'
    except Exception:
        date_str = date_label
    return f'{location} | {date_str} | Ambient'


def make_description(title):
    return (
        f'{title}\n\n'
        "Gab's Adventures — travel, walks, and life on the road.\n"
        "No commentary, just the footage with ambient music.\n\n"
        "Subscribe: https://www.youtube.com/channel/UCFUjYzVjRjweKhfs480xR4w\n\n"
        '#travel #slowtv #adventure #walkingtour #ambient'
    )


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
                raise RuntimeError(
                    f'client_secrets.json not found at {SECRETS_FILE}.\n'
                    'Download OAuth credentials from Google Cloud Console and save there.'
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    youtube = build('youtube', 'v3', credentials=creds)

    body = {
        'snippet': {
            'title':       title,
            'description': description,
            'tags':        ['travel', 'slowtv', 'walkingvlog', 'adventure', 'ambient', '4k'],
            'categoryId':  '19',
        },
        'status': {
            'privacyStatus':           'private' if private else 'public',
            'selfDeclaredMadeForKids': False,
        },
    }

    file_size = Path(file_path).stat().st_size
    media   = MediaFileUpload(str(file_path), chunksize=50 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)

    response  = None
    last_pct  = -1
    while response is None:
        status_obj, response = request.next_chunk()
        if status_obj:
            pct = int(status_obj.progress() * 100)
            if pct != last_pct:
                mb_done  = int(status_obj.progress() * file_size) // (1024 * 1024)
                mb_total = file_size // (1024 * 1024)
                print(f'  [{bar(pct)}] {pct}%  ({mb_done}/{mb_total} MB)', end='\r')
                last_pct = pct
    print()
    return response['id']


# ── Process one session ────────────────────────────────────────────────────────

def process_one(sid, s, state, dry_run=False, private=False):
    print(f'\n{"=" * 65}')
    print(f'  Location : {s["location"]}')
    print(f'  Date     : {s["date_label"]}')
    print(f'  Folder   : {s["folder"]}')
    print(f'  Clips    : {s["file_count"]}  ({human_size(s["total_bytes"])})')
    print(f'{"=" * 65}')

    if dry_run:
        privacy_label = 'private' if private else 'public'
        print(f'  [dry-run] would stitch -> mix music -> upload ({privacy_label})')
        return True

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    safe = re.sub(r'[^\w\-]', '_', f'{s["date"]}_{s["location"]}')[:80]
    stitched_path = WORK_DIR / f'{safe}__stitched.mp4'
    final_path    = OUTPUT_DIR / f'{safe}.mp4'

    # Filter to actually existing files
    existing = [p for p in s['files'] if Path(p).exists()]
    missing  = len(s['files']) - len(existing)
    if not existing:
        s['status'] = 'error'
        s['error']  = 'All source files are missing (drive not connected?)'
        save_state(state)
        print(f'  ERROR: no source files found. Is Z: mounted?')
        return False
    if missing:
        print(f'  Warning: {missing} file(s) missing — stitching {len(existing)} available')

    # ── 1. Stitch ────────────────────────────────────────────────────────────
    s['status'] = 'stitching'
    save_state(state)

    try:
        if stitched_path.exists() and stitched_path.stat().st_size > 0:
            dur = get_duration(stitched_path)
            print(f'  Stitch already done ({human_dur(dur)}) — skipping')
        else:
            stitch(existing, stitched_path)
    except Exception as e:
        s['status'] = 'error'
        s['error']  = f'Stitch: {str(e)[:250]}'
        save_state(state)
        print(f'\n  STITCH ERROR: {e}')
        stitched_path.unlink(missing_ok=True)
        return False

    # ── 2. Mix music ─────────────────────────────────────────────────────────
    s['status'] = 'mixing'
    save_state(state)

    try:
        if final_path.exists() and final_path.stat().st_size > 0:
            print(f'  Music mix already done ({human_size(final_path.stat().st_size)}) — skipping')
        else:
            mix_music(stitched_path, final_path)
        stitched_path.unlink(missing_ok=True)
    except Exception as e:
        s['status'] = 'error'
        s['error']  = f'Mix: {str(e)[:250]}'
        save_state(state)
        print(f'\n  MIX ERROR: {e}')
        return False

    # ── 3. Upload ─────────────────────────────────────────────────────────────
    s['status']      = 'uploading'
    s['output_file'] = str(final_path)
    save_state(state)

    title = make_title(s['location'], s['date_label'])
    desc  = make_description(title)
    privacy_label = 'private' if private else 'public'
    print(f'  Uploading ({privacy_label}): {title}')

    try:
        vid_id = upload_youtube(final_path, title, desc, private=private)
        url    = f'https://www.youtube.com/watch?v={vid_id}'
    except Exception as e:
        s['status'] = 'error'
        s['error']  = f'Upload: {str(e)[:250]}'
        save_state(state)
        print(f'\n  UPLOAD ERROR: {e}')
        return False

    # ── Done ──────────────────────────────────────────────────────────────────
    s['status']      = 'done'
    s['youtube_url'] = url
    s['ts_done']     = ts()
    s['error']       = None
    save_state(state)

    final_path.unlink(missing_ok=True)

    print(f'\n  YouTube : {url}')
    print(f'  Done!')
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Detect shooting sessions in Z: and publish to YouTube',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.strip(),
    )
    ap.add_argument('--scan',    action='store_true', help='Scan Z: drive for sessions')
    ap.add_argument('--status',  action='store_true', help='Show status table')
    ap.add_argument('--process', action='store_true', help='Stitch + upload next pending session')
    ap.add_argument('--all',     action='store_true', help='Process ALL pending sessions')
    ap.add_argument('--count',   type=int, default=1, help='How many sessions to process (default 1)')
    ap.add_argument('--session', default=None,        help='Process a specific session by ID')
    ap.add_argument('--private', action='store_true', help='Upload as private (default: public)')
    ap.add_argument('--dry-run', action='store_true', help='Simulate without writing/uploading')
    args = ap.parse_args()

    if args.scan:
        cmd_scan(dry_run=args.dry_run)
        return

    if args.status or not any([args.process, args.session]):
        cmd_status()
        return

    # Process
    state = load_state()

    if args.session:
        if args.session not in state['sessions']:
            print(f'Session not found: {args.session}')
            print('Run --status to list known sessions.')
            sys.exit(1)
        to_process = [(args.session, state['sessions'][args.session])]
    else:
        pending = [
            (sid, s) for sid, s in state['sessions'].items()
            if s['status'] in ('pending', 'stitching', 'mixing')  # resume partial too
        ]
        pending.sort(key=lambda x: x[1]['date'])
        if not pending:
            print('No pending sessions. Run --scan first, or check --status.')
            return
        count = len(pending) if args.all else args.count
        to_process = pending[:count]

    ok_count = err_count = 0
    for sid, s in to_process:
        ok = process_one(sid, s, state, dry_run=args.dry_run, private=args.private)
        if ok:
            ok_count += 1
        else:
            err_count += 1
            if not args.all:
                print(f'\nStopped on error. Retry this session with:')
                print(f'  python session_publisher.py --session "{sid}"')
                break

    if len(to_process) > 1:
        print(f'\nBatch done: {ok_count} uploaded, {err_count} errors.')

    cmd_status()


if __name__ == '__main__':
    main()
