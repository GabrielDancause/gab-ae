#!/usr/bin/env python3
"""
mac_process_long.py — Mac-side footage handler.

For each folder dropped in ~/Downloads/_Pipeline/<name>/:
  1. Encode Shorts from local files (CPU) ──┐  in parallel
  2. Upload raws → Drive 0 - Uploading/    ──┘
  3. Write _mac_shorts.json marker into Drive folder
  4. Move Drive folder 0 - Uploading/ → 1 - Dump/  (VPS picks up, does long-form only)
  5. Local folder → _done/

VPS skips Short generation when it sees _mac_shorts.json in the folder.

Usage (called by mac_watcher.py):
  python3 -m footage.mac_process_long <local_folder_path>

Manual:
  python3 -m footage.mac_process_long "~/Downloads/_Pipeline/2026-05-08 - Berlin" --dry-run
  python3 -m footage.mac_process_long "~/Downloads/_Pipeline/2026-05-08 - Berlin" --list
"""

import base64
import json
import os
import queue as tqueue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent          # ~/Desktop/gab-ae/footage/
DRIVE_TOKEN    = str(BASE_DIR / 'token.json')
ENV_FILE       = str(BASE_DIR.parent / '.env')
MUSIC_LIBRARY  = str(BASE_DIR / 'library.json')
READY_DIR      = str(BASE_DIR / 'mac_ready')
READY_LONG_DIR = str(BASE_DIR / 'mac_ready_long')
READY_QUEUE    = str(BASE_DIR / 'mac_ready_queue.json')
READY_LONG_Q   = str(BASE_DIR / 'mac_ready_long_queue.json')
WORKDIR        = '/tmp/gab_footage_workdir'
LOCK_FILE      = '/tmp/mac_process_long.lock'

# ── Drive ──────────────────────────────────────────────────────────────────────
DUMP_ID        = '1DyeasST-nK6j7evn4iR7JWBSFc3lQF29'   # 1 - Dump/ (VPS watches here)

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_SHORTS      = 15
SHORT_CLIP_SECS = 12
AI_TITLES       = False
SESSION_GAP_MIN = 30

SKIP_EXTENSIONS = {'.lrf', '.heic', '.png', '.jpg', '.jpeg', '.dng', '.raw'}
META_PREFIXES   = ('video-', 'od_video-')

OPENROUTER_MODELS = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]

META_VARIANTS = [
    ('native', 'scale=1440:1920'),
    ('16x9',   'crop=iw:iw*9/16:0:(ih-iw*9/16)/2,scale=1920:1080'),
    ('9x16',   'crop=ih*9/16:ih:(iw-ih*9/16)/2:0'),
]


# ── Resume cache helpers ───────────────────────────────────────────────────────
WORKDIR_MARKER = os.path.join(WORKDIR, '.folder_id')


def is_cached(path):
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def workdir_init(marker_key):
    os.makedirs(WORKDIR, exist_ok=True)
    marker = Path(WORKDIR_MARKER)
    if marker.exists():
        prev = marker.read_text().strip()
        if prev != marker_key:
            print(f"  [resume] WORKDIR has stale data from {prev}, cleaning...")
            shutil.rmtree(WORKDIR)
            os.makedirs(WORKDIR)
    marker.write_text(marker_key)


def workdir_clear():
    for p in Path(WORKDIR).iterdir():
        if p.is_file():
            p.unlink()


# ── Lock ───────────────────────────────────────────────────────────────────────
def acquire_lock():
    lf = Path(LOCK_FILE)
    if lf.exists():
        pid = lf.read_text().strip()
        if pid and Path(f'/proc/{pid}').exists():
            print(f"Already running (pid {pid}) — exiting")
            return False
        lf.unlink()
    lf.write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        Path(LOCK_FILE).unlink()
    except FileNotFoundError:
        pass


# ── Drive (for raw backup upload) ─────────────────────────────────────────────
def drive_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def drive_create_folder(svc, name, parent_id):
    """Create a subfolder in Drive, return its ID."""
    existing = svc.files().list(
        q=(f"'{parent_id}' in parents and name='{name}' "
           "and mimeType='application/vnd.google-apps.folder' and trashed=false"),
        fields='files(id)', pageSize=1,
    ).execute().get('files', [])
    if existing:
        return existing[0]['id']
    return svc.files().create(
        body={'name': name,
              'mimeType': 'application/vnd.google-apps.folder',
              'parents': [parent_id]},
        fields='id',
    ).execute()['id']


def drive_upload_file(svc, local_path, parent_id):
    """Upload a local file to Drive folder. Resumes if already uploaded."""
    name = Path(local_path).name
    size_mb = os.path.getsize(local_path) / 1024 / 1024
    print(f"  ↑ {name} ({size_mb:.0f} MB)")
    media = MediaFileUpload(local_path, resumable=True, chunksize=64 * 1024 * 1024)
    svc.files().create(
        body={'name': name, 'parents': [parent_id]},
        media_body=media,
        fields='id',
    ).execute()


def write_mac_shorts_marker(folder_name, shorts_count):
    """Find the Drive folder by name in 1 - Dump/ and write _mac_shorts.json.

    Called after Mac finishes encoding Shorts so VPS knows to skip Short generation.
    Returns True on success, False if folder not found or error.
    """
    try:
        svc = drive_service()
        results = svc.files().list(
            q=(f"'{DUMP_ID}' in parents and name='{folder_name}' "
               "and mimeType='application/vnd.google-apps.folder' and trashed=false"),
            fields='files(id)',
            pageSize=1,
        ).execute().get('files', [])
        if not results:
            return False
        folder_id = results[0]['id']
        marker = {'shorts_count': shorts_count, 'ts': ts(), 'source': 'mac'}
        with open('/tmp/_mac_shorts.json', 'w') as fh:
            json.dump(marker, fh)
        drive_upload_file(svc, '/tmp/_mac_shorts.json', folder_id)
        print(f"  _mac_shorts.json → Drive/1-Dump/{folder_name}/ ({shorts_count} Shorts) ✓")
        return True
    except Exception as e:
        print(f"  Marker write error: {e}")
        return False


def _marker_thread(folder_name, shorts_count):
    """Background: retry writing the Drive marker until the folder appears (max 30 min)."""
    delays = [0, 60, 120, 300, 600, 900]  # seconds between retries
    for delay in delays:
        if delay:
            time.sleep(delay)
        if write_mac_shorts_marker(folder_name, shorts_count):
            return
    print(f"  Marker not written — Drive folder '{folder_name}' not found in 1-Dump/ after 30 min")


# ── Local file classification ──────────────────────────────────────────────────
def classify_files_local(folder_path):
    """Classify local files into camera groups.

    Returns dict of lists, each item is {'name': str, 'path': str, 'size': int}.
    DJI files without Drive metadata are probed immediately (no download needed).
    """
    groups = {k: [] for k in
              ('dji_square', 'dji_horizontal', 'dji_unknown',
               'meta_glasses', 'phone', 'skip')}

    for p in sorted(Path(folder_path).iterdir()):
        if not p.is_file():
            continue
        name = p.name
        ext  = p.suffix.lower()
        low  = name.lower()
        info = {'name': name, 'path': str(p), 'size': p.stat().st_size}

        if ext in SKIP_EXTENSIONS:
            groups['skip'].append(info)
            continue

        if low.startswith('dji_mimo_') or low.startswith('dji_'):
            if ext not in ('.mp4', '.mov'):
                groups['skip'].append(info)
                continue
            # Probe locally — no waiting for Drive metadata
            w, h = get_dimensions(str(p))
            if w > 0 and h > 0:
                groups['dji_square' if abs(w - h) < 20 else 'dji_horizontal'].append(info)
            else:
                groups['dji_unknown'].append(info)  # unreadable, treat as square

        elif any(low.startswith(pre) for pre in META_PREFIXES):
            groups['meta_glasses' if ext in ('.mov', '.mp4') else 'skip'].append(info)

        elif low.startswith('img_'):
            groups['phone' if ext in ('.mov', '.mp4') else 'skip'].append(info)

        else:
            groups['skip'].append(info)

    return groups


# ── ffprobe helpers ────────────────────────────────────────────────────────────
def _probe_stream(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-select_streams', 'v:0', path],
        capture_output=True, text=True
    )
    try:
        return json.loads(r.stdout).get('streams', [{}])[0]
    except Exception:
        return {}


def get_duration(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
        capture_output=True, text=True
    )
    try:
        return float(json.loads(r.stdout).get('format', {}).get('duration', 0))
    except Exception:
        return 0.0


def get_dimensions(path):
    s = _probe_stream(path)
    return int(s.get('width', 0)), int(s.get('height', 0))


def get_fps(path):
    s = _probe_stream(path)
    fr = s.get('r_frame_rate', '0/1')
    try:
        n, d = fr.split('/')
        return float(n) / float(d) if float(d) else 0.0
    except Exception:
        return 0.0


# ── FFmpeg progress runner ────────────────────────────────────────────────────
def _fmt_time(secs):
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def run_ffmpeg(cmd, total_secs=None):
    """Run ffmpeg with live progress line. Returns object with .returncode and .stderr."""
    proc = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
        text=True, bufsize=1,
    )
    stderr_buf = []
    for line in proc.stderr:
        stderr_buf.append(line)
        if 'time=' not in line or 'bitrate=' not in line:
            continue
        m_time  = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
        m_speed = re.search(r'speed=\s*(\S+)', line)
        if not m_time:
            continue
        h, m, s  = int(m_time.group(1)), int(m_time.group(2)), float(m_time.group(3))
        current  = h * 3600 + m * 60 + s
        speed    = m_speed.group(1) if m_speed else '?'
        if total_secs and total_secs > 0:
            pct = min(100.0, current / total_secs * 100)
            eta = ''
            try:
                sp = float(speed.rstrip('x'))
                if sp > 0:
                    eta = f"  ETA {_fmt_time((total_secs - current) / sp)}"
            except ValueError:
                pass
            print(f"\r  {pct:5.1f}%  {_fmt_time(current)} / {_fmt_time(total_secs)}"
                  f"  speed={speed}{eta}   ", end='', flush=True)
        else:
            print(f"\r  {_fmt_time(current)}  speed={speed}   ", end='', flush=True)
    proc.wait()
    print(flush=True)

    class _Result:
        returncode = proc.returncode
        stderr     = ''.join(stderr_buf)
        stdout     = ''
    return _Result()


# ── FFmpeg helpers ─────────────────────────────────────────────────────────────
def crop_to_4k(src, dst):
    w, h = get_dimensions(src)
    dur  = get_duration(src)
    print(f"  Source: {w}x{h}, {dur:.0f}s")
    vf = ('crop=iw:iw*9/16:0:(ih-iw*9/16)/2,scale=3840:2160'
          if abs(w - h) < 20 else 'scale=3840:2160')
    r = run_ffmpeg([
        'ffmpeg', '-y', '-i', src,
        '-vf', vf,
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast',
        '-maxrate', '80M', '-bufsize', '160M', '-an', dst,
    ], total_secs=dur)
    if r.returncode != 0:
        print(f"  Crop error: {r.stderr[-300:]}")
        return False
    gb = os.path.getsize(dst) / 1024**3
    print(f"  Cropped: {gb:.2f} GB")
    return True


def concat_clips(paths, dst):
    list_file = dst + '.txt'
    with open(list_file, 'w') as f:
        for p in paths:
            f.write(f"file '{p}'\n")
    try:
        for extra in ([], ['-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an']):
            cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                   '-i', list_file] + (extra or ['-c', 'copy', '-an']) + [dst]
            r = run_ffmpeg(cmd)
            if r.returncode == 0:
                gb  = os.path.getsize(dst) / 1024**3
                dur = get_duration(dst)
                print(f"  Stitched: {gb:.2f} GB, {dur:.0f}s")
                return True
            print(f"  Concat attempt failed, retrying with re-encode...")
        print(f"  Concat failed: {r.stderr[-300:]}")
        return False
    finally:
        Path(list_file).unlink(missing_ok=True)


def mix_satie(src, dst):
    library    = json.loads(Path(MUSIC_LIBRARY).read_text())
    track      = random.choice(library)
    music_path = track.get('path') or track.get('file')
    vid_dur    = get_duration(src)
    music_dur  = get_duration(music_path)
    max_offset = max(0, music_dur - vid_dur - 10)
    offset     = random.uniform(0, max_offset) if max_offset > 0 else 0
    print(f"  Music: {track.get('filename','?')} offset={offset:.0f}s")
    r = run_ffmpeg([
        'ffmpeg', '-y',
        '-i', src,
        '-ss', str(offset), '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-filter:a', 'volume=0.5',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(vid_dur), dst,
    ], total_secs=vid_dur)
    if r.returncode != 0:
        print(f"  Audio mix error: {r.stderr[-200:]}")
        return False, track
    gb = os.path.getsize(dst) / 1024**3
    print(f"  With audio: {gb:.2f} GB")
    return True, track


def add_short_music(src, dst):
    library    = json.loads(Path(MUSIC_LIBRARY).read_text())
    track      = random.choice(library)
    music_path = track.get('path') or track.get('file')
    dur        = get_duration(src)
    r = run_ffmpeg([
        'ffmpeg', '-y',
        '-i', src,
        '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-filter:a', 'volume=0.5',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(dur), '-shortest', dst,
    ], total_secs=dur)
    return r.returncode == 0


# ── AI helpers ─────────────────────────────────────────────────────────────────
def load_env():
    env = {}
    if Path(ENV_FILE).exists():
        for line in Path(ENV_FILE).read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def _sample_frames(video_path, n, start_pct=0.05, end_pct=0.95):
    dur    = get_duration(video_path)
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = dur * (start_pct + (end_pct - start_pct) * i / max(1, n - 1))
            p = os.path.join(tmp, f'f{i:02d}.jpg')
            subprocess.run(
                ['ffmpeg', '-y', '-ss', str(t), '-i', video_path,
                 '-vframes', '1', '-q:v', '4', p],
                capture_output=True
            )
            if os.path.exists(p) and os.path.getsize(p) > 0:
                frames.append((t, base64.b64encode(Path(p).read_bytes()).decode()))
    return frames


def generate_title(video_path, location, env, n_frames=6):
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1',
                    api_key=env['OPENROUTER_API_KEY'])
    frames = _sample_frames(video_path, n_frames)
    if not frames:
        return f"{location} 🎬", f"Exploring {location}", []
    prompt = (f"Title a long-form YouTube travel video about: {location}.\n"
              f"I show you {len(frames)} frames. Generate a clickbait title — "
              f"emotional, specific. CAPS on 1-2 words. 1 emoji. Max 70 chars. No hashtags.\n"
              f"Also write a 2-3 sentence description and 5 tags.\n"
              f'Respond ONLY with JSON: {{"title":"...","description":"...","tags":["..."]}}')
    content = [{"type": "text", "text": prompt}]
    for i, (_, b64) in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    for model in OPENROUTER_MODELS:
        for attempt in range(3):
            try:
                resp = OpenAI(base_url='https://openrouter.ai/api/v1',
                              api_key=env['OPENROUTER_API_KEY']).chat.completions.create(
                    model=model, messages=[{"role": "user", "content": content}], temperature=0.3)
                data = json.loads(re.search(r'\{[\s\S]*\}', resp.choices[0].message.content).group(0))
                return data['title'], data.get('description', ''), data.get('tags', [])
            except Exception as e:
                print(f"  {model} failed: {str(e)[:80]}")
                time.sleep(8)
    return f"{location} 🎬", f"Exploring {location}", []


def generate_title_short(video_path, location, env, n_frames=3):
    from openai import OpenAI
    frames = _sample_frames(video_path, n_frames)
    if not frames:
        return f"You won't believe this in {location} 😱", f"Shot in {location}."
    prompt = (f"YouTube Shorts title for travel clip in {location}. "
              f"Reaction/curiosity-gap style. Max 80 chars, 1 emoji, CAPS on 1 key word. No hashtags. "
              f'JSON only: {{"title":"...","description":"..."}}')
    content = [{"type": "text", "text": prompt}]
    for i, (_, b64) in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    for model in OPENROUTER_MODELS:
        try:
            resp = OpenAI(base_url='https://openrouter.ai/api/v1',
                          api_key=env['OPENROUTER_API_KEY']).chat.completions.create(
                model=model, messages=[{"role": "user", "content": content}], temperature=0.7)
            data = json.loads(re.search(r'\{[\s\S]*\}', resp.choices[0].message.content).group(0))
            return data['title'], data.get('description', f'Shot in {location}.')
        except Exception as e:
            print(f"  {model} failed: {str(e)[:80]}")
    return f"You won't believe this in {location} 😱", f"Shot in {location}."


def ai_pick_best_frame(frames, location, env):
    try:
        from openai import OpenAI
    except ImportError:
        return len(frames) // 2  # fallback: pick middle frame
    n = len(frames)
    prompt = (f"Pick the most visually interesting frame from a {location} travel video. "
              f"Reply with ONLY a number from 1 to {n}.")
    content = [{"type": "text", "text": prompt}]
    for i, (_, b64) in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    for model in OPENROUTER_MODELS:
        try:
            resp = OpenAI(base_url='https://openrouter.ai/api/v1',
                          api_key=env['OPENROUTER_API_KEY']).chat.completions.create(
                model=model, messages=[{"role": "user", "content": content}], temperature=0.1)
            idx = int(re.search(r'\d+', resp.choices[0].message.content).group(0)) - 1
            return max(0, min(idx, n - 1))
        except Exception:
            pass
    return n // 2


# ── Short production ───────────────────────────────────────────────────────────
def extract_dji_short(raw_path, location, env, out_path):
    dur = get_duration(raw_path)
    fps = get_fps(raw_path)
    if dur < SHORT_CLIP_SECS + 10:
        return False
    frames   = _sample_frames(raw_path, 8)
    if not frames:
        return False
    best_idx = ai_pick_best_frame(frames, location, env)
    best_ts  = frames[best_idx][0]
    start    = max(0, best_ts - SHORT_CLIP_SECS / 2)
    if start + SHORT_CLIP_SECS > dur:
        start = max(0, dur - SHORT_CLIP_SECS)
    vf = 'crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920'
    if fps >= 50:
        vf += ',setpts=2.0*PTS'
    r = run_ffmpeg([
        'ffmpeg', '-y', '-ss', str(start), '-i', raw_path,
        '-t', str(SHORT_CLIP_SECS),
        '-vf', vf, '-r', '30',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an',
        out_path,
    ], total_secs=SHORT_CLIP_SECS)
    if r.returncode != 0:
        return False
    print(f"  Short extracted: {os.path.getsize(out_path) // 1024 // 1024} MB")
    return True


def make_phone_short(raw_path, out_path):
    fps = get_fps(raw_path)
    dur = get_duration(raw_path)
    print(f"  Phone clip: {dur:.1f}s @ {fps:.0f}fps")
    vf = 'scale=1080:1920'
    if fps >= 50:
        vf += ',setpts=2.0*PTS'
    r = run_ffmpeg([
        'ffmpeg', '-y', '-i', raw_path,
        '-vf', vf, '-r', '30',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an',
        out_path,
    ], total_secs=dur)
    return r.returncode == 0


def make_meta_stitch(raw_paths, key):
    stitched = os.path.join(WORKDIR, f'meta_stitched_{key}.mp4')
    if is_cached(stitched):
        dur = get_duration(stitched)
        gb  = os.path.getsize(stitched) / 1024**3
        print(f"  Stitch cached: {gb:.2f} GB, {dur:.0f}s")
        return stitched
    norm_paths = []
    for p in raw_paths:
        norm = p + '.norm.mp4'
        if is_cached(norm):
            norm_paths.append(norm)
            continue
        r = run_ffmpeg([
            'ffmpeg', '-y', '-i', p,
            '-vf', 'scale=1440:-2,pad=1440:1920:0:(1920-ih)/2:black',
            '-c:v', 'libx264', '-crf', '20', '-preset', 'fast', '-an', norm,
        ], total_secs=get_duration(p))
        if r.returncode == 0:
            norm_paths.append(norm)
    if not norm_paths:
        return None
    if len(norm_paths) == 1:
        shutil.copy2(norm_paths[0], stitched)
    else:
        if not concat_clips(norm_paths, stitched):
            for p in norm_paths:
                Path(p).unlink(missing_ok=True)
            return None
    for p in norm_paths:
        Path(p).unlink(missing_ok=True)
    return stitched


def make_meta_preview(stitched_path, variant_name, vf, dst):
    dur = min(get_duration(stitched_path), 180)
    r = run_ffmpeg([
        'ffmpeg', '-y', '-i', stitched_path,
        '-vf', vf, '-t', str(dur),
        '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-an', dst,
    ], total_secs=dur)
    if r.returncode != 0:
        print(f"  Preview error ({variant_name}): {r.stderr[-200:]}")
        return False
    print(f"  Preview {variant_name}: {os.path.getsize(dst) // 1024 // 1024} MB")
    return True


# ── Parallel process (no download needed — files already local) ────────────────
def parallel_process_local(files, process_fn):
    """Process local files: encode current while pre-loading next into OS cache."""
    q = tqueue.Queue(maxsize=1)

    def preloader():
        for f in files:
            q.put(f)
        q.put(None)

    t = threading.Thread(target=preloader, daemon=True)
    t.start()

    while True:
        f = q.get()
        if f is None:
            break
        print(f"\n  → {f['name']}")
        try:
            process_fn(f)
        except Exception as e:
            print(f"  Processing error ({f['name']}): {e}")

    t.join()


# ── Queue helpers ──────────────────────────────────────────────────────────────
def load_queue(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else []


def save_queue(queue, path):
    Path(path).write_text(json.dumps(queue, indent=2))


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# ── Location parsing ───────────────────────────────────────────────────────────
def parse_location(folder_name):
    """Extract location from folder name like '2026-05-08 - Paris, France'."""
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s*-\s*(.+)$', folder_name)
    return m.group(1).strip() if m else folder_name


# ── Session helpers ────────────────────────────────────────────────────────────
def extract_file_timestamp(filename):
    m = re.search(r'(\d{8})_(\d{6})', filename)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
        except ValueError:
            return None
    return None


def split_into_sessions(files, gap_minutes=SESSION_GAP_MIN):
    timed   = [(extract_file_timestamp(f['name']), f) for f in files]
    stamped = sorted([(t, f) for t, f in timed if t is not None], key=lambda x: x[0])
    untimed = [f for t, f in timed if t is None]
    if not stamped:
        return [untimed] if untimed else []
    sessions, current, last_ts = [], [], None
    for t, f in stamped:
        if last_ts is None or (t - last_ts).total_seconds() > gap_minutes * 60:
            if current:
                sessions.append(current)
            current = [f]
        else:
            current.append(f)
        last_ts = t
    if current:
        sessions.append(current)
    if untimed:
        sessions[-1].extend(untimed)
    return sessions


# ── Per-session processor (local) ──────────────────────────────────────────────
def process_session_local(folder_name, session_num, session_files, location, env, short_count,
                          shorts_only=False):
    """Encode one session's local files, queue outputs. Returns (shorts, long)."""
    session_key = f'{folder_name}_s{session_num}'
    workdir_init(session_key)

    classed  = classify_files_local_subset(session_files)
    gb_total = sum(f['size'] for f in session_files) / 1024**3
    ts_list  = sorted(t for f in session_files if (t := extract_file_timestamp(f['name'])))
    tr = (f" [{ts_list[0].strftime('%H:%M')}–{ts_list[-1].strftime('%H:%M')}]"
          if ts_list else '')

    print(f"\n{'='*60}")
    print(f"Session {session_num}{tr} — {len(session_files)} file(s), {gb_total:.1f} GB")
    for cam, lst in classed.items():
        if lst:
            gb = sum(f['size'] for f in lst) / 1024**3
            print(f"  {cam:16s}: {len(lst):3d} file(s)  {gb:.1f} GB")

    dji_square_cropped = []
    dji_horiz_paths    = []
    short_no_music     = []
    meta_raw_paths     = []

    # ── 1. DJI square + unknown ──────────────────────────────────────────────
    dji_files = sorted(classed['dji_square'] + classed['dji_unknown'],
                       key=lambda f: f['name'])
    if dji_files:
        print(f"\n[DJI: {len(dji_files)} file(s) — encode in parallel]")

        def process_dji(f):
            raw_path = f['path']
            stem     = Path(f['name']).stem
            sq_path  = os.path.join(WORKDIR, 'sq_' + f['name'])
            hz_path  = os.path.join(WORKDIR, 'hz_' + f['name'])

            if is_cached(sq_path) and not shorts_only:
                print(f"  → Square (cached crop): {f['name']}")
                dji_square_cropped.append(sq_path)
                cached_short = next(Path(WORKDIR).glob(f'short_*_dji_{stem}.mp4'), None)
                if cached_short and is_cached(str(cached_short)) and short_count[0] < MAX_SHORTS:
                    short_no_music.append(str(cached_short))
                    short_count[0] += 1
                return

            if is_cached(hz_path):
                print(f"  → Horizontal (cached)")
                dji_horiz_paths.append(hz_path)
                return

            w, h = get_dimensions(raw_path)
            fps  = get_fps(raw_path)
            dur  = get_duration(raw_path)

            if w > 0 and h > 0 and (w - h) > 100:
                shutil.copy2(raw_path, hz_path)
                dji_horiz_paths.append(hz_path)
                print(f"  → Horizontal ({w}x{h}), copied for stitch")
                return

            print(f"  → Square ({w}x{h}, {dur:.0f}s, {fps:.0f}fps)")

            # crop_to_4k is only needed for long-form stitching — skip when Shorts-only
            if not shorts_only:
                if crop_to_4k(raw_path, sq_path):
                    dji_square_cropped.append(sq_path)

            if short_count[0] < MAX_SHORTS and dur > SHORT_CLIP_SECS + 10:
                short_path = os.path.join(WORKDIR, f'short_{short_count[0]:02d}_dji_{stem}.mp4')
                if extract_dji_short(raw_path, location, env, short_path):
                    short_no_music.append(short_path)
                    short_count[0] += 1

        parallel_process_local(dji_files, process_dji)

    # ── 2. DJI horizontal ────────────────────────────────────────────────────
    # Skip in shorts_only mode — horizontal files are only needed for long-form stitching
    if not shorts_only:
        for f in sorted(classed['dji_horizontal'], key=lambda f: f['name']):
            hz_path = os.path.join(WORKDIR, 'hz_' + f['name'])
            if is_cached(hz_path):
                print(f"  hz cached: {f['name']}")
            else:
                shutil.copy2(f['path'], hz_path)
                print(f"  Copied hz: {f['name']}")
            dji_horiz_paths.append(hz_path)
    elif classed['dji_horizontal']:
        print(f"  DJI horizontal: {len(classed['dji_horizontal'])} file(s) — skipped (Shorts-only)")

    # ── 3. Meta glasses ──────────────────────────────────────────────────────
    for f in sorted(classed['meta_glasses'], key=lambda f: f['name']):
        meta_raw_paths.append(f['path'])
        print(f"  Meta: {f['name']}")

    # ── 4. Phone Shorts ──────────────────────────────────────────────────────
    phone_candidates = [f for f in classed['phone']
                        if (dur := get_duration(f['path'])) == 0 or 4 <= dur <= 28]
    if phone_candidates and short_count[0] < MAX_SHORTS:
        print(f"\n[Phone Shorts: {len(phone_candidates)} candidate(s)]")
        for f in sorted(phone_candidates, key=lambda f: f['name']):
            if short_count[0] >= MAX_SHORTS:
                break
            dur = get_duration(f['path'])
            if dur < 4 or dur > 28:
                continue
            out = os.path.join(WORKDIR,
                               f'short_{short_count[0]:02d}_phone_{Path(f["name"]).stem}.mp4')
            if make_phone_short(f['path'], out):
                short_no_music.append(out)
                short_count[0] += 1

    # ── 5. Add music to Shorts + queue ───────────────────────────────────────
    queued_shorts = 0
    if short_no_music:
        print(f"\n[Mixing music for {len(short_no_music)} Short(s)...]")
        city = location.split(',')[0].strip()  # "Paris, France" → "Paris"
        tags = f'#shorts #{city.lower()} #travel #pov'
        for i, sp in enumerate(short_no_music):
            final = os.path.join(READY_DIR, f'{session_key}_short_{i:02d}.mp4')
            sq = load_queue(READY_QUEUE)
            if is_cached(final) and any(e.get('local_file') == final for e in sq):
                Path(sp).unlink(missing_ok=True)
                queued_shorts += 1
                continue
            if add_short_music(sp, final):
                mb = os.path.getsize(final) / 1024 / 1024
                print(f"  Short {i+1}: {mb:.0f} MB → {Path(final).name}")
                title, desc = (generate_title_short(final, city, env)
                               if AI_TITLES else (city, f'Shot in {city}.'))
                sq.append({
                    'drive_id':     session_key,
                    'name':         folder_name,
                    'title':        title,
                    'description':  f'{desc}\n\n{tags}',
                    'channel':      'gab2',
                    'local_file':   final,
                    'ts_processed': ts(),
                    'uploaded':     False,
                })
                save_queue(sq, READY_QUEUE)
                queued_shorts += 1
            Path(sp).unlink(missing_ok=True)
        print(f"  {queued_shorts} Short(s) queued")

    queued_long = 0

    if shorts_only:
        workdir_clear()
        print(f"  Session {session_num} done (Shorts-only mode)")
        return queued_shorts, 0

    def _queue_long(entry):
        nonlocal queued_long
        q = load_queue(READY_LONG_Q)
        if any(e.get('local_file') == entry['local_file'] for e in q):
            return
        q.append(entry)
        save_queue(q, READY_LONG_Q)
        queued_long += 1

    # ── 6. DJI square long-form ──────────────────────────────────────────────
    final_sq = os.path.join(READY_LONG_DIR, f'{session_key}_sq.mp4')
    if is_cached(final_sq):
        _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                     'location': location, 'type': 'dji_square', 'title': location,
                     'description': f'Exploring {location}.', 'local_file': final_sq,
                     'ts_processed': ts(), 'uploaded': False})
    elif dji_square_cropped:
        dji_square_cropped.sort()
        print(f"\n[DJI square long-form: stitching {len(dji_square_cropped)} clip(s)...]")
        stitched = os.path.join(WORKDIR, f'sq_stitched_{session_key}.mp4')
        if not is_cached(stitched) and not concat_clips(dji_square_cropped, stitched):
            stitched = None
        if stitched:
            for p in dji_square_cropped:
                Path(p).unlink(missing_ok=True)
            audio = os.path.join(WORKDIR, f'sq_audio_{session_key}.mp4')
            ok, track = mix_satie(stitched, audio)
            Path(stitched).unlink(missing_ok=True)
            if ok:
                title, desc, _ = (generate_title(audio, f'{location} (day)', env)
                                   if AI_TITLES else (location, f'Exploring {location}.', []))
                attr = track.get('attribution', '')
                if attr:
                    desc += f'\n\n{attr}'
                shutil.move(audio, final_sq)
                print(f"  Saved: {final_sq}")
                _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                             'location': location, 'type': 'dji_square', 'title': title,
                             'description': desc, 'local_file': final_sq,
                             'ts_processed': ts(), 'uploaded': False})

    # ── 7. DJI horizontal long-form ──────────────────────────────────────────
    final_hz = os.path.join(READY_LONG_DIR, f'{session_key}_hz.mp4')
    if is_cached(final_hz):
        _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                     'location': location, 'type': 'dji_horizontal', 'title': location,
                     'description': f'Exploring {location}.', 'local_file': final_hz,
                     'ts_processed': ts(), 'uploaded': False})
    elif dji_horiz_paths:
        dji_horiz_paths.sort()
        print(f"\n[DJI horizontal long-form: stitching {len(dji_horiz_paths)} clip(s)...]")
        stitched = os.path.join(WORKDIR, f'hz_stitched_{session_key}.mp4')
        if not is_cached(stitched) and not concat_clips(dji_horiz_paths, stitched):
            stitched = None
        if stitched:
            for p in dji_horiz_paths:
                Path(p).unlink(missing_ok=True)
            audio = os.path.join(WORKDIR, f'hz_audio_{session_key}.mp4')
            ok, track = mix_satie(stitched, audio)
            Path(stitched).unlink(missing_ok=True)
            if ok:
                title, desc, _ = (generate_title(audio, f'{location} (night)', env)
                                   if AI_TITLES else (location, f'Exploring {location}.', []))
                attr = track.get('attribution', '')
                if attr:
                    desc += f'\n\n{attr}'
                shutil.move(audio, final_hz)
                print(f"  Saved: {final_hz}")
                _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                             'location': location, 'type': 'dji_horizontal', 'title': title,
                             'description': desc, 'local_file': final_hz,
                             'ts_processed': ts(), 'uploaded': False})

    # ── 8. Meta glasses ──────────────────────────────────────────────────────
    if meta_raw_paths:
        print(f"\n[Meta glasses: {len(meta_raw_paths)} clip(s)...]")
        stitched = make_meta_stitch(meta_raw_paths, session_key)
        if stitched:
            meta_title = meta_desc = None
            for variant_name, vf in META_VARIANTS:
                print(f"\n  Variant: {variant_name}")
                final_meta = os.path.join(READY_LONG_DIR,
                                          f'{session_key}_meta_{variant_name}.mp4')
                if is_cached(final_meta):
                    if meta_title is None:
                        meta_title, meta_desc = (
                            generate_title(final_meta, f'{location} POV glasses', env)[:2]
                            if AI_TITLES else (location, f'Exploring {location}.'))
                    _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                                 'location': location, 'type': f'meta_preview_{variant_name}',
                                 'title': meta_title,
                                 'description': meta_desc + f'\n\nFormat: {variant_name}.',
                                 'local_file': final_meta, 'ts_processed': ts(), 'uploaded': False})
                    continue
                prev = os.path.join(WORKDIR, f'meta_{variant_name}_{session_key}.mp4')
                if not make_meta_preview(stitched, variant_name, vf, prev):
                    continue
                if meta_title is None:
                    meta_title, meta_desc = (
                        generate_title(prev, f'{location} POV glasses', env)[:2]
                        if AI_TITLES else (location, f'Exploring {location}.'))
                ok, track = mix_satie(prev, final_meta)
                Path(prev).unlink(missing_ok=True)
                if ok:
                    print(f"  Saved: {final_meta}")
                    _queue_long({'drive_folder_id': session_key, 'folder_name': folder_name,
                                 'location': location, 'type': f'meta_preview_{variant_name}',
                                 'title': meta_title,
                                 'description': meta_desc + f'\n\nFormat: {variant_name}.',
                                 'local_file': final_meta, 'ts_processed': ts(), 'uploaded': False})
            Path(stitched).unlink(missing_ok=True)

    workdir_clear()
    print(f"  Session {session_num} done")
    return queued_shorts, queued_long


def classify_files_local_subset(file_list):
    """Re-classify a subset of already-classified local file dicts."""
    groups = {k: [] for k in
              ('dji_square', 'dji_horizontal', 'dji_unknown',
               'meta_glasses', 'phone', 'skip')}
    for f in file_list:
        name = f['name']
        ext  = Path(name).suffix.lower()
        low  = name.lower()
        if ext in SKIP_EXTENSIONS:
            groups['skip'].append(f)
        elif low.startswith('dji_mimo_') or low.startswith('dji_'):
            w, h = get_dimensions(f['path'])
            if w > 0 and h > 0:
                groups['dji_square' if abs(w - h) < 20 else 'dji_horizontal'].append(f)
            else:
                groups['dji_unknown'].append(f)
        elif any(low.startswith(p) for p in META_PREFIXES):
            groups['meta_glasses'].append(f)
        elif low.startswith('img_'):
            groups['phone'].append(f)
        else:
            groups['skip'].append(f)
    return groups


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m footage.mac_process_long <local_folder_path> [--dry-run] [--list]")
        sys.exit(1)

    local_path = Path(sys.argv[1]).expanduser().resolve()
    dry_run    = '--dry-run' in sys.argv
    list_mode  = '--list'    in sys.argv

    if not local_path.is_dir():
        print(f"Error: {local_path} is not a directory")
        sys.exit(1)

    if not (dry_run or list_mode):
        if not acquire_lock():
            sys.exit(0)
    try:
        _main(local_path, dry_run, list_mode)
    finally:
        if not (dry_run or list_mode):
            release_lock()


def _main(local_path, dry_run, list_mode):
    folder_name = local_path.name
    location    = parse_location(folder_name)

    all_files = classify_files_local(str(local_path))
    processable = [f for cam, lst in all_files.items() if cam != 'skip' for f in lst]

    print(f"\nFolder  : {folder_name}")
    print(f"Location: {location}")
    for cam, lst in all_files.items():
        if lst:
            gb = sum(f['size'] for f in lst) / 1024**3
            print(f"  {cam:16s}: {len(lst):3d} file(s)  {gb:.1f} GB")

    if not processable:
        print("No processable video files — skipping (photos-only, VPS handles backup).")
        return

    sessions = split_into_sessions(processable)
    print(f"\nSessions: {len(sessions)} detected (gap ≥ {SESSION_GAP_MIN} min)")
    for i, sess in enumerate(sessions, 1):
        gb = sum(f['size'] for f in sess) / 1024**3
        ts_list = sorted(t for f in sess if (t := extract_file_timestamp(f['name'])))
        tr = (f" [{ts_list[0].strftime('%H:%M')}–{ts_list[-1].strftime('%H:%M')}]"
              if ts_list else '')
        print(f"  Session {i}{tr}: {len(sess)} file(s), {gb:.1f} GB")

    if dry_run or list_mode:
        return

    os.makedirs(READY_DIR, exist_ok=True)
    os.makedirs(READY_LONG_DIR, exist_ok=True)
    env = load_env()

    # ── Encode Shorts only — VPS handles long-form from Drive
    short_count  = [0]
    total_shorts = 0

    for i, session_files in enumerate(sessions, 1):
        s, _ = process_session_local(folder_name, i, session_files, location, env,
                                     short_count, shorts_only=True)
        total_shorts += s

    print(f"\n{'--'*30}")
    print(f"Done!")
    print(f"  Sessions  : {len(sessions)}")
    print(f"  Shorts    : {total_shorts} clip(s) queued → YouTube")
    print(f"  Long-form : VPS will handle from Drive")

    # ── Upload all queued Shorts to YouTube (inline — no separate cron needed)
    pending = [e for e in load_queue(READY_QUEUE) if not e.get('uploaded')]
    if pending:
        print(f"\nUploading {len(pending)} Short(s) to YouTube...")
        for _ in range(len(pending) + 3):  # small buffer for any pre-existing items
            result = subprocess.run(
                [sys.executable, '-m', 'footage.mac_upload_scheduler'],
                cwd=str(Path.home() / 'Desktop' / 'gab-ae'),
            )
            if result.returncode != 0:
                print("  Upload stopped (quota or error) — remaining clips will upload next run")
                break
            still_pending = [e for e in load_queue(READY_QUEUE) if not e.get('uploaded')]
            if not still_pending:
                print("  All Shorts uploaded to YouTube!")
                break

    # ── Write _mac_shorts.json marker to Drive so VPS skips Short generation
    # Runs in background — retries until the Drive folder appears (user may still be uploading)
    if total_shorts > 0:
        t = threading.Thread(target=_marker_thread, args=(folder_name, total_shorts), daemon=True)
        t.start()
        t.join(timeout=5)  # give it 5s for the common case (folder already in Drive)
        # If not done yet, it keeps retrying silently in the background


if __name__ == '__main__':
    main()
