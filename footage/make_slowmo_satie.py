#!/usr/bin/env python3
"""
make_slowmo_satie.py — Slow-motion + Eric Satie music for a folder of phone clips.

For each video in the input folder:
  - Detects source FPS and slows down to 24fps output
    (60fps source → 2.5× slower, 30fps source → 1.25× slower)
  - Adds Eric Satie music (cycles through Gymnopedie 1/2/3, Gnossienne 1)
  - Keeps original resolution and aspect ratio — no crop
  - Outputs numbered MP4s to <input_folder> - Slowmo Satie/
  - Optionally publishes graded clips to Internet Archive + gab.ae (--publish)
  - Optionally backs up raw originals to a private IA item (--raw-backup)

Usage:
  python3 footage/make_slowmo_satie.py "/path/to/folder"
  python3 footage/make_slowmo_satie.py "/path/to/folder" --top 15
  python3 footage/make_slowmo_satie.py "/path/to/folder" --out "/path/to/output"
  python3 footage/make_slowmo_satie.py "/path/to/folder" --publish --ia-id my-ia-identifier --series my-series
  python3 footage/make_slowmo_satie.py "/path/to/folder" --raw-backup --raw-ia-id my-raw-backup-id
  python3 footage/make_slowmo_satie.py "/path/to/folder" --raw-backup --raw-ia-id my-raw-id --publish --ia-id my-pub-id --series my-series
"""

import argparse
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# ── Config ─────────────────────────────────────────────────────────────────
FOOTAGE_DIR = Path(__file__).parent
MUSIC_DIR   = FOOTAGE_DIR / 'music'
OUTPUT_FPS  = 24

SATIE_TRACKS = [
    'gymnopedie_no1.mp3',
    'gymnopedie_no2.mp3',
    'gymnopedie_no3.mp3',
    'gnossienne_no1.mp3',
    'gymnopedie_no1_macloed.mp3',
]

VIDEO_EXTS = {'.mov', '.mp4', '.MP4', '.MOV'}


# ── Helpers ─────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def probe(path):
    """Return (duration, width, height, fps) for a video file."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-show_format', str(path)],
        capture_output=True, text=True
    )
    d  = json.loads(r.stdout)
    vs = next((s for s in d['streams'] if s.get('codec_type') == 'video'), None)
    if not vs:
        raise ValueError("No video stream found")
    dur = float(d.get('format', {}).get('duration', vs.get('duration', 0)))
    w, h = int(vs['width']), int(vs['height'])
    rot  = int(vs.get('tags', {}).get('rotate', 0))
    if rot in (90, 270):
        w, h = h, w
    num, den = vs.get('r_frame_rate', '30/1').split('/')
    fps = round(int(num) / int(den))
    return dur, w, h, fps


def score_clip(path, dur):
    """Score a clip by sharpness (Laplacian variance). Higher = sharper."""
    scores = []
    for t in [dur * 0.2, dur * 0.4, dur * 0.6, dur * 0.8]:
        r = subprocess.run([
            'ffmpeg', '-ss', str(t), '-i', str(path), '-vframes', '1',
            '-vf', 'scale=320:240:force_original_aspect_ratio=increase',
            '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'
        ], capture_output=True)
        if not r.stdout:
            continue
        try:
            img   = Image.open(io.BytesIO(r.stdout)).convert('L')
            arr   = np.array(img, dtype=float)
            mean  = arr.mean()
            edges = np.array(img.filter(ImageFilter.FIND_EDGES), dtype=float)
            if 20 < mean < 235:
                scores.append(float(edges.var()))
        except Exception:
            pass
    return sum(scores) / len(scores) if scores else 0.0


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder',           help='Input folder containing video clips')
    parser.add_argument('--top',  type=int, default=None,
                        help='Only process the top N clips by sharpness score (default: all)')
    parser.add_argument('--out',  default=None,
                        help='Output folder (default: <input> - Slowmo Satie)')
    parser.add_argument('--publish',  action='store_true',
                        help='After processing, upload graded clips to Internet Archive and seed gab.ae')
    parser.add_argument('--ia-id',    default=None,
                        help='Internet Archive item identifier (required with --publish)')
    parser.add_argument('--ia-title', default=None,
                        help='Internet Archive item title (default: derived from folder name)')
    parser.add_argument('--series',   default=None,
                        help='gab.ae shorts series slug (default: derived from --ia-id)')
    parser.add_argument('--raw-backup', action='store_true',
                        help='Upload raw original clips to a private Internet Archive item (no grading)')
    parser.add_argument('--raw-ia-id',  default=None,
                        help='Internet Archive item identifier for raw backup (required with --raw-backup)')
    parser.add_argument('--raw-ia-title', default=None,
                        help='Title for the raw IA item (default: derived from folder name + " — Raw")')
    args = parser.parse_args()

    src_dir = Path(args.folder).expanduser().resolve()
    if not src_dir.is_dir():
        print(f"ERROR: not a folder: {src_dir}")
        sys.exit(1)

    out_dir = Path(args.out).expanduser().resolve() if args.out \
              else src_dir.parent / (src_dir.name + ' - Slowmo Satie')
    out_dir.mkdir(parents=True, exist_ok=True)

    # Collect video files
    videos = sorted([f for f in src_dir.iterdir()
                     if f.suffix in VIDEO_EXTS and not f.name.startswith('.')])
    if not videos:
        print(f"No video files found in {src_dir}")
        sys.exit(1)

    log(f"Found {len(videos)} video(s) in {src_dir.name}")
    log(f"Output → {out_dir}")

    # Probe + score
    clips = []
    log("Scanning clips...")
    for v in videos:
        try:
            dur, w, h, fps = probe(v)
            if dur < 2:
                log(f"  SKIP {v.name} ({dur:.1f}s — too short)")
                continue
            score = score_clip(v, dur)
            slowdown = fps / OUTPUT_FPS          # e.g. 60/24 = 2.5
            out_dur  = dur * slowdown
            log(f"  {score:6.0f}  {fps}fps  {dur:.1f}s → {out_dur:.1f}s  {v.name}")
            clips.append({
                'path': v, 'score': score, 'fps': fps,
                'dur': dur, 'out_dur': out_dur, 'slowdown': slowdown,
            })
        except Exception as e:
            log(f"  SKIP {v.name} — {e}")

    if not clips:
        print("No usable clips found.")
        sys.exit(1)

    # Sort by sharpness, optionally limit
    clips.sort(key=lambda c: c['score'], reverse=True)
    if args.top:
        clips = clips[:args.top]
        log(f"\nUsing top {len(clips)} clips by sharpness")

    # Process
    log(f"\nProcessing {len(clips)} clip(s)...")
    for i, clip in enumerate(clips):
        track = MUSIC_DIR / SATIE_TRACKS[i % len(SATIE_TRACKS)]
        if not track.exists():
            print(f"ERROR: music file not found: {track}")
            sys.exit(1)

        out = out_dir / f"{i+1:02d}_{clip['path'].stem}.mp4"
        out_dur   = clip['out_dur']
        slowdown  = clip['slowdown']
        log(f"[{i+1}/{len(clips)}] {clip['path'].name}  ×{slowdown:.2f} slow  + {track.name}")

        result = subprocess.run([
            'ffmpeg', '-y',
            '-i', str(clip['path']),
            '-i', str(track),
            '-t', str(out_dur),
            '-filter_complex',
            f'[0:v]setpts={slowdown}*PTS[v];'
            f'[1:a]volume=0.85,'
            f'afade=t=in:st=0:d=1.5,'
            f'afade=t=out:st={max(0, out_dur-2):.2f}:d=2[a]',
            '-map', '[v]', '-map', '[a]',
            '-r', str(OUTPUT_FPS),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-c:a', 'aac', '-b:a', '192k',
            str(out)
        ], capture_output=True)

        if result.returncode != 0:
            log(f"  ERROR: {result.stderr.decode()[-300:]}")
            continue

        mb = out.stat().st_size / 1024 ** 2
        log(f"  ✓ {out.name}  {out_dur:.1f}s  {mb:.0f} MB")

    log(f"\nDone. {len(clips)} clip(s) in {out_dir}")

    if args.raw_backup:
        if not args.raw_ia_id:
            log("ERROR: --raw-ia-id is required with --raw-backup")
            sys.exit(1)
        raw_title = args.raw_ia_title or (src_dir.name + ' — Raw')
        raw_backup(src_dir, args.raw_ia_id, raw_title)

    if args.publish:
        if not args.ia_id:
            log("ERROR: --ia-id is required with --publish")
            sys.exit(1)
        publish(out_dir, args.ia_id, args.ia_title, args.series)


def raw_backup(src_dir, ia_id, ia_title=None):
    """Upload raw originals to a private Internet Archive item."""
    src_dir = Path(src_dir)
    clips   = sorted([f for f in src_dir.iterdir()
                      if f.suffix in VIDEO_EXTS and not f.name.startswith('.')])
    if not clips:
        log("raw_backup: no clips found")
        return

    ia_title = ia_title or src_dir.name
    log(f"\n[raw-backup] Uploading {len(clips)} raw clip(s) to IA: {ia_id} (private)")
    ia_cmd = [
        'ia', 'upload', ia_id, *[str(c) for c in clips],
        '--metadata=mediatype:movies',
        f'--metadata=title:{ia_title}',
        '--metadata=access:private',
        '--metadata=noindex:true',
    ]
    result = subprocess.run(ia_cmd, cwd=str(src_dir))
    if result.returncode != 0:
        log("  ERROR: ia raw backup upload failed")
        return
    log(f"  ✓ Raw backup complete — https://archive.org/details/{ia_id}")


def publish(out_dir, ia_id, ia_title=None, series=None):
    """Upload graded clips to Internet Archive and seed gab.ae shorts table."""
    out_dir = Path(out_dir)
    clips   = sorted(out_dir.glob('[0-9]*.mp4'))
    if not clips:
        log("publish: no clips found in output folder")
        return

    ia_title = ia_title or out_dir.name
    series   = series or ia_id

    # ── 1. Internet Archive upload ──────────────────────────────────────────
    log(f"\n[publish] Uploading {len(clips)} clips to Internet Archive: {ia_id}")
    ia_cmd = [
        'ia', 'upload', ia_id, *[str(c) for c in clips],
        '--metadata=mediatype:movies',
        f'--metadata=title:{ia_title}',
        '--metadata=licenseurl:https://creativecommons.org/licenses/by/4.0/',
    ]
    result = subprocess.run(ia_cmd, cwd=str(out_dir.parent))
    if result.returncode != 0:
        log("  ERROR: ia upload failed")
        return
    log("  ✓ Internet Archive upload complete")

    # ── 2. Extract thumbnails ───────────────────────────────────────────────
    log("\n[publish] Extracting thumbnails...")
    thumb_dir = Path(tempfile.mkdtemp())
    for clip in clips:
        dur = float(subprocess.check_output(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', str(clip)]
        ).strip())
        t   = dur * 0.4
        out = thumb_dir / (clip.stem + '.jpg')
        subprocess.run([
            'ffmpeg', '-y', '-ss', str(t), '-i', str(clip),
            '-frames:v', '1', '-vf', 'scale=270:480:force_original_aspect_ratio=increase,crop=270:480',
            '-q:v', '4', str(out), '-loglevel', 'quiet'
        ])
    log(f"  ✓ {len(list(thumb_dir.glob('*.jpg')))} thumbnails extracted")

    # ── 3. Seed gab.ae D1 ──────────────────────────────────────────────────
    log("\n[publish] Seeding gab.ae shorts table...")
    sql_lines = ['CREATE TABLE IF NOT EXISTS shorts (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL, series TEXT, thumb_b64 TEXT, video_url TEXT, published_at TEXT DEFAULT (datetime(\'now\')), status TEXT DEFAULT \'live\');']
    for i, clip in enumerate(clips, 1):
        slug      = f"{series}-{i:02d}"
        title     = f"{series.replace('-', ' ').title()} · {i:02d}"
        ia_embed  = f"https://archive.org/embed/{ia_id}/{clip.name}?autoplay=1"
        thumb_path = thumb_dir / (clip.stem + '.jpg')
        if not thumb_path.exists():
            log(f"  WARNING: no thumb for {clip.name}, skipping")
            continue
        b64 = base64.b64encode(thumb_path.read_bytes()).decode().replace("'", "''")
        sql_lines.append(
            f"INSERT OR REPLACE INTO shorts (slug, title, series, thumb_b64, video_url, status) "
            f"VALUES ('{slug}', '{title}', '{series}', '{b64}', '{ia_embed}', 'live');"
        )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write('\n'.join(sql_lines))
        sql_path = f.name

    result = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', 'gab-ae-prod', '--remote', '--file', sql_path],
        cwd=str(Path(__file__).parent.parent),
    )
    os.unlink(sql_path)
    if result.returncode != 0:
        log("  ERROR: wrangler d1 execute failed")
        return
    log(f"  ✓ {len(clips)} shorts seeded to gab.ae")
    log(f"\n[publish] All done!")
    log(f"  IA:     https://archive.org/details/{ia_id}")
    log(f"  Site:   https://gab.ae/")


if __name__ == '__main__':
    main()
