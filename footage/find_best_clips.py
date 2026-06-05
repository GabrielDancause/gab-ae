#!/usr/bin/env python3
"""
find_best_clips.py — Score all Drive footage and extract best 5s clips.

Priority:
  1. Phone MOV files (already portrait 9:16) — download originals
  2. Action cam LRF proxies (horizontal → center crop to 9:16)

Scoring pipeline per clip:
  Phase 1 — fast, ffmpeg-based:
    - Extract 1 frame/sec as JPEG
    - Sharpness: PIL FIND_EDGES variance (Laplacian proxy)
    - Exposure: reject mean < 30 (dark) or > 220 (blown out)
    - Find best 5s sliding window by average frame score
  Phase 2 — GPT-4o-mini (only survivors of phase 1):
    - Send single best frame as image
    - Score 1-10 for aesthetic/content quality
    - Keep if score >= GPT_MIN_SCORE

Output:
  mac_ready/ clips, queued to mac_ready_queue.json, then uploaded.

Usage:
  python3 -m footage.find_best_clips
  python3 -m footage.find_best_clips --phase phone
  python3 -m footage.find_best_clips --phase lrf
  python3 -m footage.find_best_clips --dry-run
  python3 -m footage.find_best_clips --max 30        # limit clips to process
"""

import argparse
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ── Config ─────────────────────────────────────────────────────────────────────
CLIP_DURATION   = 5.0      # seconds per output clip
GPT_MIN_SCORE   = 6        # minimum GPT-4o-mini score to keep (1-10)
SHARP_MIN       = 30.0     # minimum Laplacian variance (reject blurry) — GPT does the real cut
EXPOSURE_MIN    = 20       # min mean pixel value
EXPOSURE_MAX    = 235      # max mean pixel value
MAX_PHONE_MB    = 600      # skip phone files larger than this (likely long video)
MIN_LRF_MB      = 8
MAX_LRF_MB      = 150

TARGET_W, TARGET_H = 1080, 1920
FPS_OUT = 30

FOOTAGE_DIR = Path(__file__).parent
READY_DIR   = FOOTAGE_DIR / 'mac_ready'
READY_QUEUE = FOOTAGE_DIR / 'mac_ready_queue.json'
STATE_FILE  = FOOTAGE_DIR / 'best_clips_state.json'

DRIVE_TOKEN = str(FOOTAGE_DIR / 'token.json')

# Drive source folders — phone + LRF
DRIVE_SOURCES = [
    # Priority 1 — phone MOV files
    {'id': '1oY_24nVrwlSJPM1CMCZgu2r8MSa7p3NA', 'name': 'phone/glasses/action cam',      'priority': 1},
    {'id': '1SG8dpXogB90OKojNZgTmPCjOryoJqv01', 'name': '4-Review (May 08)',              'priority': 1},
    # Priority 2 — LRF action cam proxies
    {'id': '1wlAdkaBqjgCNXMqV4Yd7kZK352TRjmW2', 'name': '2026-05-03 - Paris afternoon',  'priority': 2},
    {'id': '1Pdq10ebAWzX7ffYpPwYtGa3RAeDK0wtE', 'name': '2026-05-02 - Paris',            'priority': 2},
    {'id': '1StRm7lQciPuI6ZxP-MKE3s78aMJ9zcNv', 'name': '2026-05-06 - Chaos in Paris',  'priority': 2},
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
    return json.loads(p.read_text()) if p.exists() else (default if default is not None else {})

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))

def drive_svc():
    creds = Credentials.from_authorized_user_file(DRIVE_TOKEN)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)

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
        w, h = int(vs['width']), int(vs['height'])
        # iPhone stores portrait video as landscape with rotation metadata
        rotation = int(vs.get('tags', {}).get('rotate', 0))
        if rotation in (90, 270):
            w, h = h, w   # swap to reflect actual displayed orientation
        return dur, w, h
    except Exception:
        return None


# ── Crop filters ───────────────────────────────────────────────────────────────

def is_portrait(w, h):
    return h >= w

def portrait_filter(w, h):
    """Already portrait — just scale to target."""
    return f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2"

def landscape_center_crop_filter(w, h):
    """Crop center 9:16 strip from landscape frame."""
    cw = int(h * TARGET_W / TARGET_H)
    ch = h
    if cw > w:
        cw = w
        ch = int(w * TARGET_H / TARGET_W)
    cx = (w - cw) // 2
    cy = (h - ch) // 2
    return f"crop={cw}:{ch}:{cx}:{cy},scale={TARGET_W}:{TARGET_H}"


# ── Drive helpers ───────────────────────────────────────────────────────────────

def list_files_recursive(svc, folder_id, depth=0):
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
        log(f"  Drive error: {e}")
        return []
    for f in r.get('files', []):
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            files.extend(list_files_recursive(svc, f['id'], depth + 1))
        else:
            files.append(f)
    return files

def classify(f):
    """Return 'phone', 'lrf', or None."""
    name = f['name'].upper()
    mb   = int(f.get('size', 0)) / 1024 ** 2
    if name.endswith('.MOV') and mb <= MAX_PHONE_MB:
        return 'phone'
    if name.endswith('.LRF') or '_LRF_' in name or (name.endswith('.LRF')):
        if MIN_LRF_MB <= mb <= MAX_LRF_MB:
            return 'lrf'
    return None

def download_file(svc, file_id, dest):
    req = svc.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl  = MediaIoBaseDownload(buf, req, chunksize=16 * 1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest.write_bytes(buf.getvalue())


# ── Scoring ─────────────────────────────────────────────────────────────────────

def score_frame(jpeg_path):
    """Returns (sharpness, exposure_ok, mean_px)."""
    try:
        img  = Image.open(jpeg_path).convert('L')
        arr  = np.array(img, dtype=float)
        mean = arr.mean()
        # Laplacian via FIND_EDGES filter
        edges     = np.array(img.filter(ImageFilter.FIND_EDGES), dtype=float)
        sharpness = float(edges.var())
        exposure_ok = EXPOSURE_MIN < mean < EXPOSURE_MAX
        return sharpness, exposure_ok, mean
    except Exception:
        return 0.0, False, 0.0

def find_best_window(frame_scores, window=5):
    """
    frame_scores: list of (sharpness, exposure_ok) per second.
    Returns (best_start_sec, best_avg_score).
    """
    n = len(frame_scores)
    if n < window:
        window = n
    best_score = -1
    best_start = 0
    for i in range(n - window + 1):
        w = frame_scores[i:i + window]
        # Zero out non-exposed frames
        scores = [s if ok else 0 for s, ok in w]
        avg = sum(scores) / len(scores)
        if avg > best_score:
            best_score = avg
            best_start = i
    return best_start, best_score

def gpt_available():
    return bool(os.environ.get('OPENAI_API_KEY'))

def gpt_score_frame(frame_path):
    """Send JPEG to GPT-4o-mini. Returns (score, reason) or (None, '') on error/unavailable."""
    if not gpt_available():
        return None, 'no key'
    try:
        from openai import OpenAI
        client = OpenAI()
        with open(frame_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': (
                            'Rate this frame from a Paris travel video for use as a 9:16 Short. '
                            'Consider: sharpness, lighting/exposure, composition, visual interest. '
                            'Reply with JSON only: {"score": 1-10, "reason": "one sentence"}'
                        )
                    },
                    {
                        'type':      'image_url',
                        'image_url': {'url': f'data:image/jpeg;base64,{b64}', 'detail': 'low'}
                    }
                ]
            }],
            max_tokens=80,
        )
        text = resp.choices[0].message.content.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        data = json.loads(text)
        return int(data.get('score', 0)), data.get('reason', '')
    except Exception as e:
        log(f"    GPT error: {e}")
        return None, ''


# ── Clip extraction ─────────────────────────────────────────────────────────────

def extract_clip(src, start_s, duration_s, out_path, vf):
    r = run(['ffmpeg', '-y',
              '-ss', str(start_s), '-i', str(src), '-t', str(duration_s),
              '-vf', vf,
              '-r', str(FPS_OUT),
              '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
              '-an', str(out_path)])
    return out_path if r.returncode == 0 else None


# ── Process one file ────────────────────────────────────────────────────────────

def process_file(video_path, file_type, file_name, dry_run=False):
    """
    Score a video file and extract the best 5s clip.
    Returns dict with results, or None if rejected.
    """
    info = probe_video(video_path)
    if not info:
        log(f"  Cannot probe — skip")
        return None
    total_dur, w, h = info

    if total_dur < CLIP_DURATION:
        log(f"  Too short ({total_dur:.1f}s) — skip")
        return None

    portrait = is_portrait(w, h)
    vf = portrait_filter(w, h) if portrait else landscape_center_crop_filter(w, h)

    log(f"  {total_dur:.1f}s  {w}x{h}  {'portrait' if portrait else 'landscape→crop'}")

    if dry_run:
        return {'dry_run': True, 'duration': total_dur, 'portrait': portrait}

    # ── Phase 1: extract frames and score ──
    with tempfile.TemporaryDirectory(prefix='bclip_') as fdir:
        fdir = Path(fdir)

        # Extract 1 frame per second
        r = run(['ffmpeg', '-y', '-i', str(video_path),
                  '-vf', 'fps=1', '-q:v', '3',
                  str(fdir / 'f%04d.jpg')])
        if r.returncode != 0:
            log(f"  Frame extraction failed — skip")
            return None

        frames = sorted(fdir.glob('f*.jpg'))
        if not frames:
            return None

        # Score each frame
        frame_scores = []
        for fr in frames:
            sharpness, exp_ok, mean_px = score_frame(fr)
            frame_scores.append((sharpness, exp_ok))

        # Find best window
        best_start, best_avg = find_best_window(frame_scores, window=int(CLIP_DURATION))

        if best_avg < SHARP_MIN:
            log(f"  Too blurry (score={best_avg:.0f} < {SHARP_MIN}) — skip")
            return None

        # Pick the sharpest frame within the best window for GPT
        window_frames = frames[best_start: best_start + int(CLIP_DURATION)]
        if not window_frames:
            window_frames = frames
        best_frame_in_window = max(
            window_frames,
            key=lambda f: score_frame(f)[0]
        )

        # ── Phase 2: GPT score (optional) ──
        gpt_reason = ''
        if gpt_available():
            gpt_s, gpt_reason = gpt_score_frame(best_frame_in_window)
            if gpt_s is None:
                gpt_s = GPT_MIN_SCORE
            log(f"  GPT score: {gpt_s}/10 — {gpt_reason}")
            if gpt_s < GPT_MIN_SCORE:
                log(f"  GPT rejected ({gpt_s} < {GPT_MIN_SCORE}) — skip")
                return None
        else:
            gpt_s = GPT_MIN_SCORE  # pass through; sharpness filter is the gate

        # ── Extract the clip ──
        READY_DIR.mkdir(exist_ok=True)
        safe     = re.sub(r'[^a-zA-Z0-9]+', '_', Path(file_name).stem)[:30]
        out_name = f"best_{int(time.time())}_{safe}.mp4"
        out_path = READY_DIR / out_name

        result = extract_clip(video_path, float(best_start), CLIP_DURATION, out_path, vf)
        if not result:
            log(f"  Extraction failed — skip")
            return None

        size_mb = out_path.stat().st_size / 1024 ** 2
        log(f"  ✓ Extracted → {out_name} ({size_mb:.0f} MB, gpt={gpt_s})")

        return {
            'output':     str(out_path),
            'out_name':   out_name,
            'start_s':    best_start,
            'gpt_score':  gpt_s,
            'gpt_reason': gpt_reason,
            'sharp_score': best_avg,
            'portrait':   portrait,
            'source_name': file_name,
        }


# ── Queue ────────────────────────────────────────────────────────────────────────

def queue_clip(result):
    q = load_json(READY_QUEUE, [])
    entry = {
        'drive_id':     f'bestclip_{int(time.time())}',
        'name':         'Paris',
        'title':        'Paris',
        'description':  'Paris.\n\n#shorts #paris #travel #france',
        'channel':      'gab2',
        'local_file':   result['output'],
        'ts_processed': ts(),
        'uploaded':     False,
        'source':       'find_best_clips',
        'gpt_score':    result['gpt_score'],
    }
    q.append(entry)
    save_json(READY_QUEUE, q)


# ── Upload loop (at the end) ────────────────────────────────────────────────────

def upload_all():
    log("\nUploading queued clips...")
    for attempt in range(200):
        q       = load_json(READY_QUEUE, [])
        pending = [e for e in q if not e.get('uploaded') and e.get('source') == 'find_best_clips']
        if not pending:
            log("All clips uploaded!")
            break
        log(f"  {len(pending)} left — running upload_scheduler...")
        r = subprocess.run(
            [sys.executable, '-m', 'footage.mac_upload_scheduler'],
            cwd=str(Path(__file__).parent.parent),
        )
        if r.returncode != 0:
            log("  Upload stopped (quota or error) — remaining clips will upload on next run")
            break


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--phase', choices=['phone', 'lrf', 'both'], default='both')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--max', type=int, default=9999, help='Max clips to process')
    ap.add_argument('--no-upload', action='store_true', help='Skip upload at end')
    args = ap.parse_args()

    # Load .env for OpenAI key — check several locations
    for env_path in [
        Path(__file__).parent.parent / '.env',
        Path(__file__).parent.parent / 'shorts-uploader' / '.env',
        Path.home() / '.env',
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if '=' in line and not line.startswith('#'):
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    state = load_json(STATE_FILE, {'processed': [], 'extracted': []})
    processed_ids = set(state.get('processed', []))

    svc = drive_svc()

    # ── Collect candidates ──
    candidates = []  # list of {id, name, size_mb, file_type, folder}
    for src in sorted(DRIVE_SOURCES, key=lambda x: x['priority']):
        log(f"\nScanning {src['name']}...")
        files = list_files_recursive(svc, src['id'])
        for f in files:
            if f['id'] in processed_ids:
                continue
            ftype = classify(f)
            if ftype == 'phone' and args.phase in ('phone', 'both'):
                candidates.append({**f, 'file_type': 'phone', 'folder': src['name']})
            elif ftype == 'lrf' and args.phase in ('lrf', 'both'):
                candidates.append({**f, 'file_type': 'lrf', 'folder': src['name']})

    # Sort: phone first (priority 1), then LRF
    candidates.sort(key=lambda c: (0 if c['file_type'] == 'phone' else 1, c['name']))

    log(f"\nFound {len(candidates)} candidates "
        f"({sum(1 for c in candidates if c['file_type']=='phone')} phone, "
        f"{sum(1 for c in candidates if c['file_type']=='lrf')} LRF)")

    if args.dry_run:
        for c in candidates[:20]:
            mb = int(c.get('size', 0)) / 1024**2
            print(f"  [{c['file_type']:5s}] {c['name'][:60]}  ({mb:.0f} MB)")
        print(f"  ... {len(candidates)} total")
        return

    # ── Process each candidate ──
    n_kept = 0
    n_processed = 0

    for c in candidates:
        if n_processed >= args.max:
            break

        mb = int(c.get('size', 0)) / 1024**2
        log(f"\n[{n_processed+1}/{min(len(candidates), args.max)}] "
            f"[{c['file_type']}] {c['name'][:55]} ({mb:.0f} MB)")

        with tempfile.TemporaryDirectory(prefix='dl_') as td:
            dl_path = Path(td) / c['name']
            try:
                log(f"  Downloading...")
                download_file(svc, c['id'], dl_path)
            except Exception as e:
                log(f"  Download failed: {e} — skip")
                processed_ids.add(c['id'])
                continue

            result = process_file(dl_path, c['file_type'], c['name'])

        # Mark processed regardless of outcome
        processed_ids.add(c['id'])
        state['processed'] = list(processed_ids)
        n_processed += 1

        if result and not result.get('dry_run'):
            n_kept += 1
            state['extracted'].append({
                'id':         c['id'],
                'name':       c['name'],
                'output':     result['output'],
                'gpt_score':  result['gpt_score'],
                'ts':         ts(),
            })
            queue_clip(result)

        save_json(STATE_FILE, state)
        log(f"  Progress: {n_kept} clips kept / {n_processed} processed")

    log(f"\n{'='*55}")
    log(f"Done. Kept {n_kept} / {n_processed} clips.")

    if n_kept > 0 and not args.no_upload:
        upload_all()


if __name__ == '__main__':
    main()
