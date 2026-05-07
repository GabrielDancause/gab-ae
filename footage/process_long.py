#!/usr/bin/env python3
"""
process_long.py v2 — multi-camera folder processor.

Handles folders with any mix of:
  dji_mimo_*.mp4   → DJI Action Cam 6 (square day / 16:9 night)
  video-*_singular_display.mov / od_video-*_singular_display.mov → Meta glasses
  IMG_*.MOV        → iPhone (Shorts only)
  DJI_*.MP4        → DJI SD card (legacy folders, always square)
  *.LRF / *.HEIC / *.PNG → skipped without downloading

Per folder produces
  Long-form (→ ready_long_queue.json, daily upload):
    • DJI square clips  → 4K 16:9 crop → stitch → Satie → AI title
    • DJI 16:9 clips    → stitch as-is  → Satie → AI title
    • Meta glasses      → 3 × 3-min preview (16:9 crop / pillarbox / 9:16)

  Shorts (→ ready_queue.json, hourly upload, max 15):
    • iPhone clips (4–28 s) → scale 1080×1920, 2× slow-mo if 60 fps, Satie
    • DJI square clips      → AI picks best 12 s chunk → 9:16 crop, 2× slow-mo, Satie

Improvements over v1:
  ✓ LRF / HEIC / PNG skipped without downloading
  ✓ Parallel download/encode (downloads N+1 while encoding N)
  ✓ Multi-camera classification
  ✓ Short extraction from long DJI clips (one download, two outputs)
  ✓ iPhone → Short pipeline

Manual:
  python3 process_long.py --list
  python3 process_long.py --dry-run
  python3 process_long.py
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
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Constants ──────────────────────────────────────────────────────────────────
DRIVE_TOKEN    = '/opt/gab/footage/token.json'
ENV_FILE       = '/opt/gab/.env'
DUMP_FOLDER_ID = '1DyeasST-nK6j7evn4iR7JWBSFc3lQF29'   # 1 - Dump/
REVIEW_ID      = '1SG8dpXogB90OKojNZgTmPCjOryoJqv01'   # 4 - Review/
MUSIC_LIBRARY  = '/opt/gab/music/library.json'
READY_DIR      = '/opt/gab/footage/ready'               # Shorts
READY_LONG_DIR = '/opt/gab/footage/ready_long'
READY_QUEUE    = '/opt/gab/footage/ready_queue.json'
READY_LONG_Q   = '/opt/gab/footage/ready_long_queue.json'
WORKDIR        = '/tmp/long'
LOCK_FILE      = '/tmp/process_long.lock'
MAX_SHORTS     = 15
SHORT_CLIP_SECS = 12   # seconds extracted from long DJI clip for a Short

OPENROUTER_MODELS = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
]

SKIP_EXTENSIONS = {'.lrf', '.heic', '.png', '.jpg', '.jpeg', '.dng', '.raw'}

META_PREFIXES = ('video-', 'od_video-')

# (name, ffmpeg_vf) — applied to the stitched meta glasses footage
META_VARIANTS = [
    ('native',
     'scale=1440:1920'),
    ('16x9',
     'crop=iw:iw*9/16:0:(ih-iw*9/16)/2,scale=1920:1080'),
    ('9x16',
     'crop=ih*9/16:ih:(iw-ih*9/16)/2:0'),
]


# ── Resume cache helpers ───────────────────────────────────────────────────────
WORKDIR_MARKER = os.path.join(WORKDIR, '.folder_id')


def is_cached(path):
    """True if path exists and is non-empty."""
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


def cached_download(path, drive_size):
    """True if file is already fully downloaded (within 0.5% of Drive-reported size)."""
    p = Path(path)
    if not p.exists():
        return False
    local = p.stat().st_size
    if local == 0:
        return False
    if drive_size and local < int(drive_size) * 0.995:
        return False
    return True


def workdir_init(folder_id):
    """Prepare WORKDIR for this folder.

    If WORKDIR contains leftover data from a *different* folder, wipe it first.
    Writes a marker so the next invocation can detect the same situation.
    """
    os.makedirs(WORKDIR, exist_ok=True)
    marker = Path(WORKDIR_MARKER)
    if marker.exists():
        prev = marker.read_text().strip()
        if prev != folder_id:
            print(f"  [resume] WORKDIR has stale data from {prev}, cleaning...")
            shutil.rmtree(WORKDIR)
            os.makedirs(WORKDIR)
    marker.write_text(folder_id)


# ── Lock ───────────────────────────────────────────────────────────────────────
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


# ── Drive ──────────────────────────────────────────────────────────────────────
def drive_service():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def list_subfolders(svc, parent_id):
    q = (f"'{parent_id}' in parents "
         "and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false")
    r = svc.files().list(
        q=q, fields='files(id,name,createdTime)', pageSize=50
    ).execute()
    return sorted(r.get('files', []), key=lambda f: f.get('createdTime', ''))


def list_folder_files(svc, folder_id):
    q = f"'{folder_id}' in parents and trashed = false"
    results, token = [], None
    while True:
        r = svc.files().list(
            q=q,
            fields='nextPageToken,files(id,name,size,mimeType,videoMediaMetadata)',
            pageSize=100, pageToken=token,
        ).execute()
        results.extend(r.get('files', []))
        token = r.get('nextPageToken')
        if not token:
            break
    return results


def download_file(svc, file_id, dest_path):
    request = svc.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as fh:
        dl = MediaIoBaseDownload(fh, request, chunksize=64 * 1024 * 1024)
        done = False
        while not done:
            status, done = dl.next_chunk()
            if status:
                print(f"    {int(status.progress() * 100)}%", end='\r')
    print()


def move_folder(svc, folder_id, from_parent, to_parent):
    svc.files().update(
        fileId=folder_id,
        addParents=to_parent,
        removeParents=from_parent,
        fields='id',
    ).execute()


def move_file(svc, file_id, from_parent, to_parent):
    svc.files().update(
        fileId=file_id,
        addParents=to_parent,
        removeParents=from_parent,
        fields='id',
    ).execute()


def quarantine_duplicates(svc, files, folder_id):
    """Move duplicate filenames (keeping the first) into a _duplicates/ subfolder.

    Returns the deduplicated file list.
    """
    seen = {}
    dupes = []
    for f in files:
        name = f['name']
        if name in seen:
            dupes.append(f)
        else:
            seen[name] = f

    if not dupes:
        return files

    # Create _duplicates/ subfolder (or find existing)
    existing = svc.files().list(
        q=f"'{folder_id}' in parents and name='_duplicates' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields='files(id)',
        pageSize=1,
    ).execute().get('files', [])

    if existing:
        dup_folder_id = existing[0]['id']
    else:
        dup_folder_id = svc.files().create(
            body={'name': '_duplicates', 'mimeType': 'application/vnd.google-apps.folder',
                  'parents': [folder_id]},
            fields='id',
        ).execute()['id']

    print(f"\n  [Duplicates] {len(dupes)} file(s) → _duplicates/")
    for f in dupes:
        print(f"    {f['name']}")
        move_file(svc, f['id'], folder_id, dup_folder_id)

    return [f for f in files if f not in dupes]


# ── File classification ────────────────────────────────────────────────────────
def classify_files(files):
    """
    Returns dict with lists:
      dji_square     → DJI square (day): re-encode crop to 4K 16:9
      dji_horizontal → DJI 16:9 (night): concat as-is
      dji_unknown    → DJI no metadata: probe dimensions after download
      meta_glasses   → Meta glasses .mov files
      phone          → iPhone IMG_*.MOV clips
      skip           → LRF, HEIC, PNG, photos, etc.
    """
    groups = {k: [] for k in
              ('dji_square', 'dji_horizontal', 'dji_unknown',
               'meta_glasses', 'phone', 'skip')}

    for f in files:
        name = f['name']
        ext  = Path(name).suffix.lower()
        low  = name.lower()

        if ext in SKIP_EXTENSIONS:
            groups['skip'].append(f)
            continue

        if low.startswith('dji_mimo_') or low.startswith('dji_'):
            if ext not in ('.mp4', '.mov'):
                groups['skip'].append(f)
                continue
            meta = f.get('videoMediaMetadata', {})
            w = int(meta.get('width', 0))
            h = int(meta.get('height', 0))
            if w > 0 and h > 0:
                groups['dji_square' if abs(w - h) < 20 else 'dji_horizontal'].append(f)
            else:
                groups['dji_unknown'].append(f)

        elif any(low.startswith(p) for p in META_PREFIXES):
            groups['meta_glasses' if ext in ('.mov', '.mp4') else 'skip'].append(f)

        elif low.startswith('img_'):
            groups['phone' if ext in ('.mov', '.mp4') else 'skip'].append(f)

        else:
            groups['skip'].append(f)

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


# ── FFmpeg helpers ─────────────────────────────────────────────────────────────
def crop_to_4k(src, dst):
    """Crop DJI square to 4K 16:9. For 16:9 sources this is a no-op scale."""
    w, h = get_dimensions(src)
    print(f"  Source: {w}x{h}")
    vf = ('crop=iw:iw*9/16:0:(ih-iw*9/16)/2,scale=3840:2160'
          if abs(w - h) < 20 else 'scale=3840:2160')
    r = subprocess.run([
        'ffmpeg', '-y', '-i', src,
        '-vf', vf,
        '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast',
        '-maxrate', '80M', '-bufsize', '160M', '-an', dst,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Crop error: {r.stderr[-300:]}")
        return False
    gb  = os.path.getsize(dst) / 1024**3
    dur = get_duration(dst)
    print(f"  Cropped: {gb:.2f} GB, {dur:.0f}s")
    return True


def concat_clips(paths, dst):
    """Concat clips with hard cuts. Tries stream-copy first, re-encodes on failure."""
    list_file = dst + '.txt'
    with open(list_file, 'w') as f:
        for p in paths:
            f.write(f"file '{p}'\n")
    try:
        for extra in ([], ['-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-an']):
            cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                   '-i', list_file] + (extra or ['-c', 'copy', '-an']) + [dst]
            r = subprocess.run(cmd, capture_output=True, text=True)
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
    """Mix a random Satie track over the video."""
    library   = json.loads(Path(MUSIC_LIBRARY).read_text())
    track     = random.choice(library)
    music_path = track.get('path') or track.get('file')
    vid_dur    = get_duration(src)
    music_dur  = get_duration(music_path)
    max_offset = max(0, music_dur - vid_dur - 10)
    offset     = random.uniform(0, max_offset) if max_offset > 0 else 0
    print(f"  Music: {track.get('filename','?')} offset={offset:.0f}s")
    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', src,
        '-ss', str(offset), '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-filter:a', 'volume=0.5',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(vid_dur), dst,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  Audio mix error: {r.stderr[-200:]}")
        return False, track
    gb = os.path.getsize(dst) / 1024**3
    print(f"  With audio: {gb:.2f} GB")
    return True, track


def add_short_music(src, dst):
    """Add Satie music to a Short clip (loops if needed)."""
    library    = json.loads(Path(MUSIC_LIBRARY).read_text())
    track      = random.choice(library)
    music_path = track.get('path') or track.get('file')
    dur        = get_duration(src)
    r = subprocess.run([
        'ffmpeg', '-y',
        '-i', src,
        '-stream_loop', '-1', '-i', music_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-filter:a', 'volume=0.5',
        '-c:a', 'aac', '-b:a', '192k',
        '-t', str(dur), '-shortest', dst,
    ], capture_output=True, text=True)
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
    """Return list of base64-encoded JPEG frames sampled across the video."""
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
    return frames  # list of (timestamp, b64_jpeg)


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
                    {"type": "image_url", "image_url":
                     {"url": f"data:image/jpeg;base64,{b64}"}}]

    for model in OPENROUTER_MODELS:
        for attempt in range(3):
            try:
                print(f"  AI title: {model}" + (f" attempt {attempt+1}" if attempt else ""))
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.3,
                )
                text = resp.choices[0].message.content.strip()
                m    = re.search(r'\{[\s\S]*\}', text)
                if not m:
                    raise ValueError("no JSON in response")
                data = json.loads(m.group(0))
                print(f"  Title: {data['title']}")
                return data['title'], data.get('description', ''), data.get('tags', [])
            except Exception as e:
                print(f"  {model} failed: {str(e)[:80]}")
                time.sleep(8)

    return f"{location} 🎬", f"Exploring {location}", []


def generate_title_short(video_path, location, env, n_frames=3):
    """Generate a clickbait YouTube Shorts title from video frames."""
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1',
                    api_key=env['OPENROUTER_API_KEY'])

    frames = _sample_frames(video_path, n_frames)
    if not frames:
        return f"You won't believe this in {location} 😱", f"Shot in {location}."

    prompt = (f"You're writing a YouTube Shorts title for a travel clip shot in {location}.\n"
              f"I show you {len(frames)} frames from the clip.\n"
              f"Rules: reaction/curiosity-gap style (POV: / Nobody told me / Wait... WHAT / "
              f"This is WILD / You won't believe), max 80 chars, 1 emoji, CAPS on 1 key word.\n"
              f"NEVER invent specific events, people, or stories that may not have happened. "
              f"Describe only what is visually present or use a generic reaction hook.\n"
              f"No hashtags. Also write one punchy sentence for the description.\n"
              f'Respond ONLY with JSON: {{"title":"...","description":"..."}}')

    content = [{"type": "text", "text": prompt}]
    for i, (_, b64) in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url":
                     {"url": f"data:image/jpeg;base64,{b64}"}}]

    for model in OPENROUTER_MODELS:
        for attempt in range(3):
            try:
                print(f"  AI short title: {model}" + (f" attempt {attempt+1}" if attempt else ""))
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.7,
                )
                text = resp.choices[0].message.content.strip()
                m    = re.search(r'\{[\s\S]*\}', text)
                if not m:
                    raise ValueError("no JSON")
                data = json.loads(m.group(0))
                print(f"  Title: {data['title']}")
                return data['title'], data.get('description', f'Shot in {location}.')
            except Exception as e:
                print(f"  {model} failed: {str(e)[:80]}")
                time.sleep(8)

    return f"You won't believe this in {location} 😱", f"Shot in {location}."


def ai_pick_best_frame(frames, location, env):
    """Given list of (ts, b64) frames, return index of most interesting one."""
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1',
                    api_key=env['OPENROUTER_API_KEY'])

    n = len(frames)
    prompt = (f"You are picking frames from a travel video about {location} for a YouTube Short. "
              f"I show you {n} frames. Pick the single most visually dynamic and interesting one. "
              f"Reply with ONLY a number from 1 to {n}. Nothing else.")

    content = [{"type": "text", "text": prompt}]
    for i, (_, b64) in enumerate(frames):
        content += [{"type": "text", "text": f"Frame {i+1}:"},
                    {"type": "image_url", "image_url":
                     {"url": f"data:image/jpeg;base64,{b64}"}}]

    for model in OPENROUTER_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=0.1,
            )
            text = resp.choices[0].message.content.strip()
            idx  = int(re.search(r'\d+', text).group(0)) - 1
            return max(0, min(idx, n - 1))
        except Exception as e:
            print(f"  Frame pick failed ({model}): {str(e)[:60]}")

    return n // 2  # fallback: middle frame


# ── Short production ───────────────────────────────────────────────────────────
def extract_dji_short(raw_path, location, env, out_path):
    """AI picks best 12 s chunk from long DJI square clip → 9:16 crop, 2× slow-mo."""
    dur = get_duration(raw_path)
    fps = get_fps(raw_path)
    if dur < SHORT_CLIP_SECS + 10:
        print(f"  Clip too short for Short extraction ({dur:.0f}s)")
        return False

    print(f"  Sampling frames for Short extraction ({dur:.0f}s @ {fps:.0f}fps)...")
    frames = _sample_frames(raw_path, 8)
    if not frames:
        return False

    best_idx = ai_pick_best_frame(frames, location, env)
    best_ts  = frames[best_idx][0]
    start    = max(0, best_ts - SHORT_CLIP_SECS / 2)
    if start + SHORT_CLIP_SECS > dur:
        start = max(0, dur - SHORT_CLIP_SECS)

    print(f"  Extracting {SHORT_CLIP_SECS}s from t={start:.0f}s")

    # 9:16 crop from square, 2× slow-mo if 60fps, scale to 1080×1920
    vf = 'crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920'
    if fps >= 50:
        vf += ',setpts=2.0*PTS'

    r = subprocess.run([
        'ffmpeg', '-y',
        '-ss', str(start), '-i', raw_path,
        '-t', str(SHORT_CLIP_SECS),
        '-vf', vf, '-r', '30',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-an',
        out_path,
    ], capture_output=True, text=True)

    if r.returncode != 0:
        print(f"  Short extraction failed: {r.stderr[-200:]}")
        return False

    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  Short extracted: {mb:.0f} MB")
    return True


def make_phone_short(raw_path, out_path):
    """Scale iPhone clip to 1080×1920, 2× slow-mo if 60 fps."""
    fps = get_fps(raw_path)
    dur = get_duration(raw_path)
    print(f"  Phone clip: {dur:.1f}s @ {fps:.0f}fps")

    vf = 'scale=1080:1920'
    if fps >= 50:
        vf += ',setpts=2.0*PTS'

    r = subprocess.run([
        'ffmpeg', '-y', '-i', raw_path,
        '-vf', vf, '-r', '30',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-an',
        out_path,
    ], capture_output=True, text=True)

    return r.returncode == 0


def make_meta_stitch(raw_paths, folder_id):
    """Normalize all meta clips to 1440×1920 and stitch into one file. Returns path or None."""
    stitched = os.path.join(WORKDIR, f'meta_stitched_{folder_id}.mp4')
    if is_cached(stitched):
        dur = get_duration(stitched)
        gb  = os.path.getsize(stitched) / 1024**3
        print(f"  Stitch cached: {gb:.2f} GB, {dur:.0f}s")
        return stitched

    norm_paths = []
    for p in raw_paths:
        norm = p + '.norm.mp4'
        if is_cached(norm):
            print(f"  Norm cached: {Path(p).name}")
            norm_paths.append(norm)
            continue
        r = subprocess.run([
            'ffmpeg', '-y', '-i', p,
            '-vf', 'scale=1440:-2,pad=1440:1920:0:(1920-ih)/2:black',
            '-c:v', 'libx264', '-crf', '20', '-preset', 'ultrafast', '-an',
            norm,
        ], capture_output=True, text=True)
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

    dur = get_duration(stitched)
    gb = os.path.getsize(stitched) / 1024**3
    print(f"  Stitched: {gb:.2f} GB, {dur:.0f}s")
    return stitched


def make_meta_preview(stitched_path, variant_name, vf, dst):
    """Apply variant filter to stitched meta file and cut to 3 min."""
    dur = min(get_duration(stitched_path), 180)
    r = subprocess.run([
        'ffmpeg', '-y', '-i', stitched_path,
        '-vf', vf, '-t', str(dur),
        '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-an',
        dst,
    ], capture_output=True, text=True)

    if r.returncode != 0:
        print(f"  Preview error ({variant_name}): {r.stderr[-200:]}")
        return False

    mb = os.path.getsize(dst) / 1024 / 1024
    print(f"  Preview {variant_name}: {mb:.0f} MB")
    return True


# ── Parallel download/encode ───────────────────────────────────────────────────
def parallel_download_process(svc, files, process_fn):
    """
    Background thread downloads files one at a time into a buffer (maxsize=1).
    Main thread processes each file as it arrives.
    process_fn(f, raw_path) → None   (process_fn handles its own cleanup)
    """
    dl_q = tqueue.Queue(maxsize=1)

    def downloader():
        for f in files:
            raw = os.path.join(WORKDIR, f['name'])
            drive_size = int(f.get('size', 0))
            if cached_download(raw, drive_size):
                print(f"\n  ↓ {f['name']} (cached)")
                dl_q.put((f, raw))
                continue
            size_gb = drive_size / 1024**3
            print(f"\n  ↓ {f['name']} ({size_gb:.1f} GB)")
            try:
                download_file(svc, f['id'], raw)
                dl_q.put((f, raw))
            except Exception as e:
                print(f"  Download failed: {e}")
                Path(raw).unlink(missing_ok=True)
                dl_q.put((f, None))
        dl_q.put(None)  # sentinel

    t = threading.Thread(target=downloader, daemon=True)
    t.start()

    while True:
        item = dl_q.get()
        if item is None:
            break
        f, raw_path = item
        if raw_path is None:
            continue
        try:
            process_fn(f, raw_path)
        except Exception as e:
            print(f"  Processing error ({f['name']}): {e}")
            Path(raw_path).unlink(missing_ok=True)

    t.join()


# ── Queue helpers ──────────────────────────────────────────────────────────────
def load_queue(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else []


def save_queue(queue, path):
    Path(path).write_text(json.dumps(queue, indent=2))


def already_queued(folder_id):
    return any(e.get('drive_folder_id') == folder_id
               for e in load_queue(READY_LONG_Q))


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def parse_location(folder_name):
    m = re.match(r'^\d{4}-\d{2}-\d{2}\s*-\s*(.+)$', folder_name)
    desc = m.group(1).strip() if m else folder_name

    # After preposition — consecutive title-case words (no end-anchor)
    m2 = re.search(r'\b(?:in|around|through|across|over)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)', desc)
    if m2:
        return m2.group(1).strip()

    # Leading title-case words before lowercase context ("Paris afternoon and...")
    m3 = re.match(r'^([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+[a-z]', desc)
    if m3:
        return m3.group(1).strip()

    # Title-case words at end of string ("exploring Los Angeles")
    m4 = re.search(r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s*$', desc)
    if m4:
        return m4.group(1).strip()

    return desc


# ── Main ───────────────────────────────────────────────────────────────────────
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
    svc     = drive_service()
    folders = [f for f in list_subfolders(svc, DUMP_FOLDER_ID)
               if not already_queued(f['id'])]

    if list_mode:
        if not folders:
            print("No subfolders in 1 - Dump/")
            return
        for folder in folders:
            files   = list_folder_files(svc, folder['id'])
            dupes   = [f['name'] for f in files if [g['name'] for g in files].count(f['name']) > 1]
            classed = classify_files(files)
            print(f"\n  {folder['name']}")
            if dupes:
                print(f"    {'duplicates':16s}: {len(dupes)//2:3d} pair(s)  → would move to _duplicates/")
            for cam, lst in classed.items():
                if cam != 'skip' and lst:
                    gb = sum(int(f.get('size', 0)) for f in lst) / 1024**3
                    print(f"    {cam:16s}: {len(lst):3d} file(s)  {gb:.1f} GB")
        return

    if not folders:
        print("No subfolders to process in 1 - Dump/")
        return

    folder   = folders[0]
    location = parse_location(folder['name'])
    files    = list_folder_files(svc, folder['id'])
    files    = quarantine_duplicates(svc, files, folder['id'])
    classed  = classify_files(files)

    print(f"\nFolder  : {folder['name']}")
    print(f"Location: {location}")
    for cam, lst in classed.items():
        if lst:
            gb = sum(int(f.get('size', 0)) for f in lst) / 1024**3
            print(f"  {cam:16s}: {len(lst):3d} file(s)  {gb:.1f} GB")

    if dry_run:
        return

    workdir_init(folder['id'])
    os.makedirs(READY_DIR, exist_ok=True)
    os.makedirs(READY_LONG_DIR, exist_ok=True)
    env = load_env()

    dji_square_cropped = []   # for long-form stitch
    dji_horiz_paths    = []   # for long-form stitch (no re-encode)
    short_no_music     = []   # video-only short clips (music added at end)
    meta_raw_paths     = []

    short_count = [0]  # mutable so closures can modify

    # ── 1. DJI (square + unknown) — parallel download/encode ──────────────────
    dji_files = sorted(
        classed['dji_square'] + classed['dji_unknown'],
        key=lambda f: f['name']
    )

    if dji_files:
        print(f"\n[DJI: {len(dji_files)} file(s) — download+encode in parallel]")

        def process_dji(f, raw_path):
            stem    = Path(f['name']).stem
            sq_path = os.path.join(WORKDIR, 'sq_' + f['name'])
            hz_path = os.path.join(WORKDIR, 'hz_' + f['name'])

            # Resume: crop already done — no need to re-probe or re-encode
            if is_cached(sq_path):
                print(f"  → Square (cached crop): {f['name']}")
                dji_square_cropped.append(sq_path)
                cached_short = next(Path(WORKDIR).glob(f'short_*_dji_{stem}.mp4'), None)
                if cached_short and is_cached(str(cached_short)) and short_count[0] < MAX_SHORTS:
                    print(f"  → Short cached: {cached_short.name}")
                    short_no_music.append(str(cached_short))
                    short_count[0] += 1
                if raw_path != sq_path:
                    Path(raw_path).unlink(missing_ok=True)
                return

            # Resume: horizontal already moved
            if is_cached(hz_path):
                print(f"  → Horizontal (cached): {f['name']}")
                dji_horiz_paths.append(hz_path)
                if raw_path != hz_path:
                    Path(raw_path).unlink(missing_ok=True)
                return

            # Fresh processing — probe actual dimensions (resolves 'unknown' files)
            w, h = get_dimensions(raw_path)
            fps  = get_fps(raw_path)
            dur  = get_duration(raw_path)

            if w > 0 and h > 0 and (w - h) > 100:
                # Turned out to be horizontal — keep raw for stitching
                shutil.move(raw_path, hz_path)
                dji_horiz_paths.append(hz_path)
                print(f"  → Horizontal ({w}x{h}), kept for stitch")
                return

            # Square (or unknown → assume square)
            print(f"  → Square ({w}x{h}, {dur:.0f}s, {fps:.0f}fps)")

            # Crop to 4K 16:9 for long-form
            if crop_to_4k(raw_path, sq_path):
                dji_square_cropped.append(sq_path)

            # Extract Short from long clips
            if short_count[0] < MAX_SHORTS and dur > SHORT_CLIP_SECS + 10:
                short_path = os.path.join(
                    WORKDIR,
                    f'short_{short_count[0]:02d}_dji_{stem}.mp4'
                )
                if extract_dji_short(raw_path, location, env, short_path):
                    short_no_music.append(short_path)
                    short_count[0] += 1

            Path(raw_path).unlink(missing_ok=True)

        parallel_download_process(svc, dji_files, process_dji)

    # ── 2. DJI Horizontal — download sequentially (kept for stitch) ───────────
    horiz_files = sorted(classed['dji_horizontal'], key=lambda f: f['name'])
    if horiz_files:
        print(f"\n[DJI horizontal: {len(horiz_files)} file(s)]")
        for f in horiz_files:
            raw = os.path.join(WORKDIR, 'hz_' + f['name'])
            if cached_download(raw, int(f.get('size', 0))):
                print(f"\n  ↓ {f['name']} (cached)")
            else:
                size_gb = int(f.get('size', 0)) / 1024**3
                print(f"\n  ↓ {f['name']} ({size_gb:.1f} GB)")
                download_file(svc, f['id'], raw)
            dji_horiz_paths.append(raw)

    # ── 3. Meta glasses — download sequentially ───────────────────────────────
    meta_files = sorted(classed['meta_glasses'], key=lambda f: f['name'])
    if meta_files:
        print(f"\n[Meta glasses: {len(meta_files)} file(s)]")
        for f in meta_files:
            raw = os.path.join(WORKDIR, f['name'])
            if cached_download(raw, int(f.get('size', 0))):
                print(f"\n  ↓ {f['name']} (cached)")
            else:
                size_gb = int(f.get('size', 0)) / 1024**3
                print(f"\n  ↓ {f['name']} ({size_gb:.1f} GB)")
                download_file(svc, f['id'], raw)
            meta_raw_paths.append(raw)

    # ── 4. Phone Shorts — parallel download/process ───────────────────────────
    phone_files = []
    for f in sorted(classed['phone'], key=lambda x: x['name']):
        meta  = f.get('videoMediaMetadata', {})
        dur_s = int(meta.get('durationMillis', 0)) / 1000
        if dur_s == 0 or 4 <= dur_s <= 28:  # 0 = unknown, include and check after dl
            phone_files.append(f)

    if phone_files and short_count[0] < MAX_SHORTS:
        print(f"\n[Phone Shorts: {len(phone_files)} candidate(s)]")

        def process_phone(f, raw_path):
            if short_count[0] >= MAX_SHORTS:
                Path(raw_path).unlink(missing_ok=True)
                return
            dur = get_duration(raw_path)
            if dur < 4 or dur > 28:
                print(f"  Skip {f['name']} ({dur:.1f}s — out of 4-28s range)")
                Path(raw_path).unlink(missing_ok=True)
                return
            out = os.path.join(
                WORKDIR,
                f'short_{short_count[0]:02d}_phone_{Path(f["name"]).stem}.mp4'
            )
            if make_phone_short(raw_path, out):
                short_no_music.append(out)
                short_count[0] += 1
            Path(raw_path).unlink(missing_ok=True)

        parallel_download_process(svc, phone_files, process_phone)

    # ── 5. Add music to all Shorts and write to queue ─────────────────────────
    queued_shorts = 0
    final_shorts  = short_no_music[:MAX_SHORTS]
    if final_shorts:
        print(f"\n[Mixing music + AI titles for {len(final_shorts)} Short(s)...]")
        city = location.split()[-1].title()
        tags = f'#shorts #{city.lower()} #travel #pov'
        for i, sp in enumerate(final_shorts):
            final = os.path.join(READY_DIR, f'{folder["id"]}_short_{i:02d}.mp4')
            # Resume: skip if final already exists and queued
            short_q = load_queue(READY_QUEUE)
            if is_cached(final) and any(e.get('local_file') == final for e in short_q):
                print(f"  Short {i+1}: already queued, skipping")
                Path(sp).unlink(missing_ok=True)
                queued_shorts += 1
                continue
            if add_short_music(sp, final):
                mb = os.path.getsize(final) / 1024 / 1024
                print(f"  Short {i+1}: {mb:.0f} MB → {Path(final).name}")
                title, desc = generate_title_short(final, city, env)
                short_q.append({
                    'drive_id':     folder['id'],
                    'name':         folder['name'],
                    'title':        title,
                    'description':  f'{desc}\n\n{tags}',
                    'channel':      'gab2',
                    'local_file':   final,
                    'ts_processed': ts(),
                    'uploaded':     False,
                })
                save_queue(short_q, READY_QUEUE)
                queued_shorts += 1
            Path(sp).unlink(missing_ok=True)
        print(f"  {queued_shorts} Short(s) queued")

    queued_long = 0

    def _queue_long(entry):
        """Append one long-form entry to the queue immediately (crash-safe)."""
        nonlocal queued_long
        q = load_queue(READY_LONG_Q)
        if any(e.get('local_file') == entry['local_file'] for e in q):
            return  # already queued from a previous partial run
        q.append(entry)
        save_queue(q, READY_LONG_Q)
        queued_long += 1

    # ── 6. DJI square long-form ───────────────────────────────────────────────
    final_sq = os.path.join(READY_LONG_DIR, f'{folder["id"]}_sq.mp4')
    if is_cached(final_sq):
        print(f"\n[DJI square long-form: output exists, re-queuing if needed]")
        _queue_long({
            'drive_folder_id': folder['id'], 'folder_name': folder['name'],
            'location': location, 'type': 'dji_square',
            'title': f'{location} 🎬', 'description': f'Exploring {location}',
            'local_file': final_sq, 'ts_processed': ts(), 'uploaded': False,
        })
    elif dji_square_cropped:
        dji_square_cropped.sort()
        print(f"\n[DJI square long-form: stitching {len(dji_square_cropped)} clip(s)...]")
        stitched = os.path.join(WORKDIR, f'sq_stitched_{folder["id"]}.mp4')
        if is_cached(stitched):
            print(f"  Stitch cached")
        elif not concat_clips(dji_square_cropped, stitched):
            stitched = None
        if stitched:
            for p in dji_square_cropped:
                Path(p).unlink(missing_ok=True)
            audio = os.path.join(WORKDIR, f'sq_audio_{folder["id"]}.mp4')
            ok, track = mix_satie(stitched, audio)
            Path(stitched).unlink(missing_ok=True)
            if ok:
                print(f"\n[AI title for DJI square long-form...]")
                title, desc, tags = generate_title(audio, f'{location} (day)', env)
                attr = track.get('attribution', '')
                if attr:
                    desc += f'\n\n{attr}'
                shutil.move(audio, final_sq)
                print(f"  Saved: {final_sq}")
                _queue_long({
                    'drive_folder_id': folder['id'], 'folder_name': folder['name'],
                    'location': location, 'type': 'dji_square',
                    'title': title, 'description': desc,
                    'local_file': final_sq, 'ts_processed': ts(), 'uploaded': False,
                })

    # ── 7. DJI horizontal long-form ───────────────────────────────────────────
    final_hz = os.path.join(READY_LONG_DIR, f'{folder["id"]}_hz.mp4')
    if is_cached(final_hz):
        print(f"\n[DJI horizontal long-form: output exists, re-queuing if needed]")
        _queue_long({
            'drive_folder_id': folder['id'], 'folder_name': folder['name'],
            'location': location, 'type': 'dji_horizontal',
            'title': f'{location} 🎬', 'description': f'Exploring {location}',
            'local_file': final_hz, 'ts_processed': ts(), 'uploaded': False,
        })
    elif dji_horiz_paths:
        dji_horiz_paths.sort()
        print(f"\n[DJI horizontal long-form: stitching {len(dji_horiz_paths)} clip(s)...]")
        stitched = os.path.join(WORKDIR, f'hz_stitched_{folder["id"]}.mp4')
        if is_cached(stitched):
            print(f"  Stitch cached")
        elif not concat_clips(dji_horiz_paths, stitched):
            stitched = None
        if stitched:
            for p in dji_horiz_paths:
                Path(p).unlink(missing_ok=True)
            audio = os.path.join(WORKDIR, f'hz_audio_{folder["id"]}.mp4')
            ok, track = mix_satie(stitched, audio)
            Path(stitched).unlink(missing_ok=True)
            if ok:
                print(f"\n[AI title for DJI horizontal long-form...]")
                title, desc, tags = generate_title(audio, f'{location} (night)', env)
                attr = track.get('attribution', '')
                if attr:
                    desc += f'\n\n{attr}'
                shutil.move(audio, final_hz)
                print(f"  Saved: {final_hz}")
                _queue_long({
                    'drive_folder_id': folder['id'], 'folder_name': folder['name'],
                    'location': location, 'type': 'dji_horizontal',
                    'title': title, 'description': desc,
                    'local_file': final_hz, 'ts_processed': ts(), 'uploaded': False,
                })

    # ── 8. Meta glasses — normalize+stitch once, then fan out to variants ────
    if meta_raw_paths:
        print(f"\n[Meta glasses: normalizing + stitching {len(meta_raw_paths)} clip(s)...]")
        stitched = make_meta_stitch(meta_raw_paths, folder['id'])
        for p in meta_raw_paths:
            Path(p).unlink(missing_ok=True)

        if stitched:
            meta_title = None
            meta_desc  = None
            print(f"\n[Generating {len(META_VARIANTS)} variant preview(s)...]")
            for variant_name, vf in META_VARIANTS:
                print(f"\n  Variant: {variant_name}")
                final_meta = os.path.join(READY_LONG_DIR,
                                          f'{folder["id"]}_meta_{variant_name}.mp4')
                # Resume: variant already mixed and saved
                if is_cached(final_meta):
                    print(f"  Already in ready_long/, re-queuing if needed")
                    if meta_title is None:
                        meta_title, meta_desc, _ = generate_title(
                            final_meta, f'{location} POV glasses', env)
                    _queue_long({
                        'drive_folder_id': folder['id'], 'folder_name': folder['name'],
                        'location': location, 'type': f'meta_preview_{variant_name}',
                        'title': meta_title,
                        'description': meta_desc + f'\n\nFormat: {variant_name}.',
                        'local_file': final_meta, 'ts_processed': ts(), 'uploaded': False,
                    })
                    continue
                prev = os.path.join(WORKDIR, f'meta_{variant_name}_{folder["id"]}.mp4')
                if not make_meta_preview(stitched, variant_name, vf, prev):
                    continue
                if meta_title is None:
                    print(f"\n[AI title for Meta glasses long-form...]")
                    meta_title, meta_desc, _ = generate_title(
                        prev, f'{location} POV glasses', env)
                ok, track = mix_satie(prev, final_meta)
                Path(prev).unlink(missing_ok=True)
                if ok:
                    print(f"  Saved: {final_meta}")
                    _queue_long({
                        'drive_folder_id': folder['id'], 'folder_name': folder['name'],
                        'location': location, 'type': f'meta_preview_{variant_name}',
                        'title': meta_title,
                        'description': meta_desc + f'\n\nFormat: {variant_name}.',
                        'local_file': final_meta, 'ts_processed': ts(), 'uploaded': False,
                    })
            Path(stitched).unlink(missing_ok=True)

    # ── 9. Move Drive folder → 4 - Review/ ───────────────────────────────────
    move_folder(svc, folder['id'], DUMP_FOLDER_ID, REVIEW_ID)
    print(f"\n  Moved '{folder['name']}' to 4 - Review/")

    print(f"\n{'--'*30}")
    print(f"Done!")
    print(f"  Long-form : {queued_long} video(s) queued")
    print(f"  Shorts    : {queued_shorts} clip(s) queued")


if __name__ == '__main__':
    main()
