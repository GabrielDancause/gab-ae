#!/usr/bin/env python3
"""
gap_filler.py — Keep the Shorts queue full at a 70-min cadence.

Runs every 35 min (cron). If the next scheduled Short is more than
PUBLISH_INTERVAL seconds away (and we're within publishing hours),
downloads LRF proxy files from old Drive folders and builds a
beat-synced highlight reel.

Cron (VPS):
  */35 * * * * cd /opt/gab && python3 -m footage.gap_filler >> /var/log/gab/gap_filler.log 2>&1
"""

import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Config ─────────────────────────────────────────────────────────────────────
PUBLISH_INTERVAL   = 70 * 60   # 70 min between Shorts
GAP_THRESHOLD      = 70 * 60   # generate if next slot is this far away
PUBLISH_HOUR_START = 6         # UTC — 8am Paris
PUBLISH_HOUR_END   = 22        # UTC — midnight Paris

MIN_LRF_MB    = 8
MAX_LRF_MB    = 150
N_CLIPS       = 12             # clips per reel
REEL_DURATION = 45.0           # seconds

FOOTAGE_DIR = Path('/opt/gab/footage')
MUSIC_DIR   = FOOTAGE_DIR / 'music'
READY_DIR   = FOOTAGE_DIR / 'ready'
READY_QUEUE = FOOTAGE_DIR / 'ready_queue.json'
STATE_FILE  = FOOTAGE_DIR / 'pipeline_state.json'
GAP_STATE   = FOOTAGE_DIR / 'gap_filler_state.json'

DRIVE_TOKEN = str(FOOTAGE_DIR / 'token.json')
YT_TOKEN    = str(FOOTAGE_DIR / 'token_uc59_full.json')

TARGET_W, TARGET_H = 1080, 1920
FPS = 30

# Drive source folders — Published + Review (good source material)
DRIVE_SOURCES = [
    {'id': '1Pdq10ebAWzX7ffYpPwYtGa3RAeDK0wtE', 'name': '2026-05-02 - Paris'},
    {'id': '1AF1MsKHjcwXGaaE64KN45qu9pmwfjCTE', 'name': '2026-05-03 - Biking around Paris'},
    {'id': '1wlAdkaBqjgCNXMqV4Yd7kZK352TRjmW2', 'name': '2026-05-03 - Paris afternoon evening'},
    {'id': '1StRm7lQciPuI6ZxP-MKE3s78aMJ9zcNv', 'name': '2026-05-06 - Chaos in Paris'},
    {'id': '1oY_24nVrwlSJPM1CMCZgu2r8MSa7p3NA', 'name': '2026-05-94 - Paris POV glasses'},
    # Review folders (already processed by VPS, great source)
    {'id': '1SG8dpXogB90OKojNZgTmPCjOryoJqv01', 'name': '4-Review (all sessions)'},
]


# ── Utils ──────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def ts():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def run(cmd, quiet=True):
    return subprocess.run(cmd, capture_output=quiet)

def load_json(path, default=None):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return default if default is not None else {}

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))

def drive_svc():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


# ── Schedule logic ─────────────────────────────────────────────────────────────

def within_hours():
    h = datetime.now(timezone.utc).hour
    return PUBLISH_HOUR_START <= h < PUBLISH_HOUR_END

def seconds_until_next_slot():
    """
    Returns seconds until the next scheduled slot.
    Negative = last slot was in the past (gap exists).
    +inf     = no slot ever scheduled (gap exists).
    """
    state = load_json(STATE_FILE, {})
    next_at = state.get('next_publish_at')
    if not next_at:
        return float('inf')
    try:
        next_epoch = time.mktime(time.strptime(next_at, '%Y-%m-%dT%H:%M:%S.000Z'))
        return next_epoch - time.time()
    except Exception:
        return float('inf')

def next_publish_time():
    state = load_json(STATE_FILE, {})
    last = state.get('next_publish_at')
    now  = time.time()
    if last:
        try:
            last_epoch = time.mktime(time.strptime(last, '%Y-%m-%dT%H:%M:%S.000Z'))
            base = max(last_epoch, now)
        except Exception:
            base = now
    else:
        base = now
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(base + PUBLISH_INTERVAL))


# ── Source selection ────────────────────────────────────────────────────────────

def pick_source():
    """Rotate through DRIVE_SOURCES, avoiding recent repeats."""
    state = load_json(GAP_STATE, {})
    recent = state.get('recent', [])
    counts = state.get('used_count', {})

    # Skip sources used in last 3 runs
    available = [s for s in DRIVE_SOURCES if s['id'] not in recent[-3:]]
    if not available:
        available = DRIVE_SOURCES[:]

    # Weight toward least-used
    weights = [1.0 / (counts.get(s['id'], 0) + 1) for s in available]
    total   = sum(weights)
    r       = random.random() * total
    cumul   = 0
    chosen  = available[0]
    for s, w in zip(available, weights):
        cumul += w
        if r <= cumul:
            chosen = s
            break

    recent.append(chosen['id'])
    state['recent']     = recent[-10:]
    state['used_count'] = counts
    state['used_count'][chosen['id']] = counts.get(chosen['id'], 0) + 1
    save_json(GAP_STATE, state)
    return chosen


# ── Drive helpers ───────────────────────────────────────────────────────────────

def list_lrf_recursive(svc, folder_id, depth=0):
    """Return list of {id, name, size_mb} for LRF files (recursive)."""
    if depth > 3:
        return []
    files = []
    try:
        r = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id,name,size,mimeType)",
            pageSize=100,
        ).execute()
    except Exception as e:
        log(f"  Drive list error: {e}")
        return []

    for f in r.get('files', []):
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            files.extend(list_lrf_recursive(svc, f['id'], depth + 1))
        else:
            name_up = f['name'].upper()
            if name_up.endswith('.LRF') or '_LRF_' in name_up or 'LRF' in name_up:
                size_mb = int(f.get('size', 0)) / 1024 ** 2
                if MIN_LRF_MB <= size_mb <= MAX_LRF_MB:
                    files.append({'id': f['id'], 'name': f['name'], 'size_mb': size_mb})
    return files

def download_file(svc, file_id, dest):
    req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl  = MediaIoBaseDownload(buf, req, chunksize=8 * 1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest.write_bytes(buf.getvalue())


# ── Video processing ────────────────────────────────────────────────────────────

def probe_video(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-show_format', str(path)],
        capture_output=True, text=True)
    try:
        d  = json.loads(r.stdout)
        vs = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
        if not vs:
            return None
        dur = float(d.get('format', {}).get('duration', vs.get('duration', 0)))
        return dur, int(vs['width']), int(vs['height'])
    except Exception:
        return None

def crop_filter(w, h):
    cw = int(h * TARGET_W / TARGET_H)
    ch = h
    if cw > w:
        cw = w
        ch = int(w * TARGET_H / TARGET_W)
    cx = (w - cw) // 2
    cy = (h - ch) // 2
    return f"crop={cw}:{ch}:{cx}:{cy},scale={TARGET_W}:{TARGET_H}"

def extract_clip(src, start_s, duration_s, out_path):
    info = probe_video(src)
    if not info:
        return None
    total, w, h = info
    start_s = max(0.0, min(start_s, total - duration_s - 0.1))
    vf = crop_filter(w, h)
    r = run(['ffmpeg', '-y',
              '-ss', str(start_s), '-i', str(src), '-t', str(duration_s),
              '-vf', vf, '-r', str(FPS),
              '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '21',
              '-an', str(out_path)])
    return out_path if r.returncode == 0 else None

def detect_beats(music_path, limit=65.0):
    try:
        import librosa
        y, sr = librosa.load(str(music_path), sr=None, duration=limit)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = [float(b) for b in librosa.frames_to_time(beat_frames, sr=sr) if b < limit]
        log(f"  {len(beats)} beats in {Path(music_path).name}")
        return beats
    except Exception as e:
        log(f"  Beat detection failed ({e}), using fixed 0.8s intervals")
        return [i * 0.8 for i in range(int(limit / 0.8))]

def beat_durations(beats, n_clips, total_dur):
    """Assign beat-snapped durations for n_clips summing to ~total_dur."""
    per_clip = total_dur / n_clips
    durations = []
    accumulated = 0.0
    for i in range(n_clips):
        target = accumulated + per_clip
        candidates = [b for b in beats if b > accumulated + 0.5]
        if candidates:
            dur = min(candidates, key=lambda b: abs(b - target)) - accumulated
            dur = max(1.5, min(dur, 6.0))
        else:
            dur = per_clip
        durations.append(round(dur, 3))
        accumulated += dur
        if accumulated >= total_dur:
            break
    return durations

def concat_clips(paths, out):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        for p in paths:
            f.write(f"file '{p}'\n")
        lst = f.name
    try:
        run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
             '-i', lst, '-c', 'copy', str(out)])
    finally:
        os.unlink(lst)

def mix_music(video, music_path, out, fade_s=2.0):
    info = probe_video(video)
    total = info[0] if info else REEL_DURATION
    fade_start = max(0, total - fade_s)
    run(['ffmpeg', '-y',
         '-i', str(video), '-i', str(music_path),
         '-filter_complex',
         f'[1:a]atrim=0:{total},asetpts=PTS-STARTPTS,'
         f'afade=t=out:st={fade_start:.2f}:d={fade_s},volume=1.3[aout]',
         '-map', '0:v', '-map', '[aout]',
         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest',
         str(out)], quiet=False)


# ── Queue ───────────────────────────────────────────────────────────────────────

def queue_result(local_file, title, description):
    q          = load_json(READY_QUEUE, [])
    state      = load_json(STATE_FILE, {})
    publish_at = next_publish_time()

    entry = {
        'drive_id':     f'gap_{int(time.time())}',
        'name':         title,
        'title':        title,
        'description':  description,
        'channel':      'gab2',
        'local_file':   str(local_file),
        'ts_processed': ts(),
        'uploaded':     False,
        'source':       'gap_filler',
    }
    q.append(entry)
    save_json(READY_QUEUE, q)

    state['next_publish_at'] = publish_at
    save_json(STATE_FILE, state)
    log(f"Queued: '{title}'  →  slot {publish_at}")


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    log("=== gap_filler start ===")

    if not within_hours():
        log(f"Outside publishing hours ({datetime.now(timezone.utc).hour}h UTC) — done")
        return

    secs = seconds_until_next_slot()
    if secs == float('inf') or secs < 0:
        log(f"Last slot was {abs(secs)/60:.0f} min ago — gap confirmed")
    else:
        log(f"Next slot in {secs/60:.0f} min")

    # No gap if a slot is scheduled within the next PUBLISH_INTERVAL
    if 0 < secs <= GAP_THRESHOLD:
        log("No gap — done")
        return

    # ── Pick source folder ──
    source = pick_source()
    log(f"Source: {source['name']}")
    svc = drive_svc()

    lrfs = list_lrf_recursive(svc, source['id'])
    if not lrfs:
        log("No LRF files in primary source, trying others...")
        for s in DRIVE_SOURCES:
            if s['id'] == source['id']:
                continue
            lrfs = list_lrf_recursive(svc, s['id'])
            if lrfs:
                source = s
                log(f"Fallback: {source['name']}")
                break

    if not lrfs:
        log("No LRF files found anywhere — cannot fill gap")
        return

    log(f"Found {len(lrfs)} LRF files")
    random.shuffle(lrfs)
    to_download = lrfs[:min(N_CLIPS + 4, len(lrfs))]

    # ── Pick music ──
    mp3s = list(MUSIC_DIR.glob('*.mp3')) if MUSIC_DIR.exists() else []
    if not mp3s:
        log("No music files — cannot fill gap")
        return
    music = random.choice(mp3s)
    log(f"Music: {music.name}")

    beats    = detect_beats(music, limit=REEL_DURATION + 5)
    durations = beat_durations(beats, N_CLIPS, REEL_DURATION)

    location = source['name'].split(' - ', 1)[1] if ' - ' in source['name'] else source['name']
    title    = location

    # ── Build reel ──
    with tempfile.TemporaryDirectory(prefix='gap_') as td:
        td          = Path(td)
        final_clips = []
        dl_idx      = 0

        for i, dur in enumerate(durations):
            clip_made = None
            while clip_made is None and dl_idx < len(to_download):
                lrf = to_download[dl_idx]
                dl_idx += 1

                dl_path = td / lrf['name']
                log(f"  [{i+1}/{len(durations)}] {lrf['name']} ({lrf['size_mb']:.0f} MB)...")
                try:
                    download_file(svc, lrf['id'], dl_path)
                except Exception as e:
                    log(f"    Download failed: {e}")
                    continue

                info = probe_video(dl_path)
                if not info:
                    dl_path.unlink(missing_ok=True)
                    continue

                total_dur, w, h = info
                if total_dur < dur + 0.5:
                    dl_path.unlink(missing_ok=True)
                    continue

                start = max(0.0, (total_dur - dur) * random.uniform(0.1, 0.85))
                out   = td / f'clip_{i:02d}.mp4'
                clip_made = extract_clip(dl_path, start, dur, out)
                dl_path.unlink(missing_ok=True)  # free space

            if clip_made:
                final_clips.append(clip_made)

        if len(final_clips) < 4:
            log(f"Only {len(final_clips)} clips extracted — aborting")
            return

        log(f"Concatenating {len(final_clips)} clips...")
        concat_raw = td / 'concat.mp4'
        concat_clips([str(p) for p in final_clips], concat_raw)

        log("Mixing music...")
        READY_DIR.mkdir(exist_ok=True)
        safe     = re.sub(r'[^a-zA-Z0-9]+', '_', title).strip('_')[:40]
        out_name = f"gap_{int(time.time())}_{safe}.mp4"
        final_path = READY_DIR / out_name
        mix_music(concat_raw, music, final_path)

    size_mb = final_path.stat().st_size / 1024 ** 2
    log(f"Output: {out_name} ({size_mb:.0f} MB, {len(final_clips)} clips)")

    desc = f"Highlights from {location}.\n\n#shorts #paris #travel #france"
    queue_result(final_path, title, desc)
    log("=== Done ===")


if __name__ == '__main__':
    main()
