#!/usr/bin/env python3
"""
process_session.py — Full footage pipeline for a session folder.

For each horizontal (non-portrait) video clip found:
  1. Upload raw to Internet Archive (private, noindex) — vault backup
  2. Score frames → pick best thumbnail
  3. Tag with OpenRouter vision model
  4. Seed gab.ae D1 (videos table, status='vault') → appears at /vault

Then stitch the best segments across all clips:
  5. Grade + concat + Satie music → long-form MP4
  6. Upload to Internet Archive (public)
  7. Tag long-form
  8. Seed D1 (status='live') → appears at /videos

Usage:
  python3 footage/process_session.py /path/to/session \
      --vault-ia-id  gab-raw-paris-2026-05-09 \
      --pub-ia-id    gab-paris-may9 \
      --pub-title    "Paris — May 9, 2026" \
      --series       paris-may9 \
      --openrouter-key sk-or-...

  # Skip long-form stitch (vault only):
  python3 footage/process_session.py /path/to/session \
      --vault-ia-id gab-raw-paris-2026-05-09 --no-publish

  # Skip vault (publish only from existing graded file):
  python3 footage/process_session.py /path/to/session \
      --pub-ia-id gab-paris-may9 --no-vault
"""

import argparse, base64, io, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# ── Config ───────────────────────────────────────────────────────────────────
FOOTAGE_DIR  = Path(__file__).parent
MUSIC_DIR    = FOOTAGE_DIR / 'music'
WRANGLER_CWD  = FOOTAGE_DIR.parent
DB_NAME       = 'gab-ae-prod'
CF_ACCOUNT_ID = 'f8a9c8de1fcedb10d25b24325a6f8727'
CF_DB_ID      = '4e23e386-b430-4ffc-bf84-246a4e7bcdd1'
OR_MODEL     = 'nvidia/nemotron-nano-12b-v2-vl:free'
VIDEO_EXTS   = {'.mov', '.mp4', '.MP4', '.MOV', '.MTS', '.m2ts'}
GRADE        = (
    "curves=r='0/0.01 0.25/0.25 0.5/0.53 0.75/0.78 1/0.98'"
    ":g='0/0.01 0.25/0.24 0.5/0.50 0.75/0.75 1/0.96'"
    ":b='0/0.10 0.25/0.25 0.5/0.52 0.75/0.78 1/0.95',"
    "eq=contrast=1.12:brightness=0.01:saturation=1.45:gamma=0.96,"
    "unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.6,"
    "vignette=PI/5"
)
SATIE_TRACKS = [
    'gymnopedie_no1.mp3', 'gymnopedie_no2.mp3',
    'gymnopedie_no3.mp3', 'gnossienne_no1.mp3',
]
XFADE_DUR    = 1.5
SEG_DUR      = 75       # seconds per clip in long-form
MIN_CLIP_DUR = 10       # skip clips shorter than this


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Video probing ─────────────────────────────────────────────────────────────

def probe(path):
    """Return (duration, width, height, rotation) or raise."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-show_format', str(path)],
        capture_output=True, text=True
    )
    d  = json.loads(r.stdout)
    vs = next((s for s in d['streams'] if s.get('codec_type') == 'video'), None)
    if not vs:
        raise ValueError("no video stream")
    dur = float(d.get('format', {}).get('duration', vs.get('duration', 0)))
    w, h = int(vs['width']), int(vs['height'])
    rot = 0
    for sd in vs.get('side_data_list', []):
        if 'rotation' in sd:
            rot = int(sd['rotation'])
    return dur, w, h, rot


def is_horizontal(w, h, rot):
    if rot in (90, -90, 270, -270):
        w, h = h, w
    return w > h


# ── Frame scoring ─────────────────────────────────────────────────────────────

def score_frame(path, t):
    r = subprocess.run([
        'ffmpeg', '-y', '-ss', str(t), '-i', str(path), '-vframes', '1',
        '-vf', 'scale=320:180:force_original_aspect_ratio=increase,crop=320:180',
        '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', '8', '-'
    ], capture_output=True)
    if not r.stdout:
        return 0
    img   = Image.open(io.BytesIO(r.stdout)).convert('L')
    arr   = np.array(img, dtype=float)
    mean  = arr.mean()
    edges = np.array(img.filter(ImageFilter.FIND_EDGES), dtype=float)
    return float(edges.var()) if 15 < mean < 240 else 0


def best_frame(path, dur, n_candidates=12):
    timestamps = [dur * i / (n_candidates - 1) for i in range(n_candidates)]
    best_score, best_t = 0, timestamps[len(timestamps) // 3]
    for t in timestamps:
        s = score_frame(path, t)
        if s > best_score:
            best_score, best_t = s, t
    return best_t, best_score


def best_segment_start(path, dur, seg=SEG_DUR, n=6):
    """Find the start of the sharpest SEG-second window."""
    candidates = [dur * i / (n - 1) for i in range(n)]
    best_score, best_start = 0, 0
    for t in candidates:
        start = min(t, max(0, dur - seg))
        s = score_frame(path, start + seg * 0.4)
        if s > best_score:
            best_score, best_start = s, start
    return best_start, min(seg, dur - best_start)


# ── Thumbnail extraction ──────────────────────────────────────────────────────

def extract_thumb(path, t, out_path, w=640, h=360):
    subprocess.run([
        'ffmpeg', '-y', '-ss', str(t), '-i', str(path), '-vframes', '1',
        '-vf', f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}',
        '-q:v', '6', str(out_path), '-loglevel', 'quiet'
    ], capture_output=True)
    return Path(out_path)


# ── OpenRouter tagging ────────────────────────────────────────────────────────

def tag_clip(path, dur, api_key, context="Paris, France"):
    frames_b64 = []
    for t in [int(dur * i / 8) for i in range(9)]:
        r = subprocess.run([
            'ffmpeg', '-y', '-ss', str(t), '-i', str(path), '-vframes', '1',
            '-vf', 'scale=640:360:force_original_aspect_ratio=increase,crop=640:360',
            '-f', 'image2pipe', '-vcodec', 'mjpeg', '-q:v', '5', '-'
        ], capture_output=True)
        if r.stdout:
            frames_b64.append(base64.b64encode(r.stdout).decode())

    if not frames_b64:
        return {}

    content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
               for b in frames_b64]
    content.append({"type": "text", "text": f"""Frames from a video clip filmed in {context}.
Return ONLY valid JSON (no markdown):
{{
  "tags": ["tag1","tag2",...20+ specific tags],
  "location": "specific place if identifiable",
  "time_of_day": "night/day/golden hour/etc",
  "mood": "short mood phrase",
  "subjects": ["subjects visible"],
  "activity": "what is happening",
  "weather": "conditions",
  "camera_motion": "static/panning/walking/etc",
  "description": "2-sentence description"
}}"""})

    payload = json.dumps({
        "model": OR_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 900, "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://gab.ae"}
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read())
        content = result["choices"][0]["message"].get("content") or ""
        raw = content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        log(f"  tagging error: {e}")
        return {}


# ── D1 seeding ────────────────────────────────────────────────────────────────

def seed_d1(slug, title, series, thumb_path, embed_url, status, tags_dict, cf_api_token=None):
    thumb_b64 = base64.b64encode(Path(thumb_path).read_bytes()).decode().replace("'", "''")
    tags_json = json.dumps(tags_dict).replace("'", "''") if tags_dict else ''
    title_safe = str(title).replace("'", "''")
    series_safe = str(series).replace("'", "''")
    embed_safe  = str(embed_url).replace("'", "''")
    sql = (
        f"INSERT OR REPLACE INTO videos (slug, title, series, thumb_b64, video_url, status, tags) "
        f"VALUES ('{slug}', '{title_safe}', '{series_safe}', '{thumb_b64}', '{embed_safe}', '{status}', '{tags_json}');"
    )
    token = cf_api_token or os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    if token:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DB_ID}/query"
        body = json.dumps({"sql": sql}).encode()
        req  = urllib.request.Request(url, data=body,
               headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
               method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            if result.get('success'):
                return True
            log(f"  D1 error: {result.get('errors')}")
            return False
        except Exception as e:
            log(f"  D1 error: {e}")
            return False
    # fallback: wrangler CLI
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(sql); path = f.name
    r = subprocess.run(
        ['npx', 'wrangler', 'd1', 'execute', DB_NAME, '--remote', '--file', path],
        cwd=str(WRANGLER_CWD), capture_output=True, text=True
    )
    os.unlink(path)
    if r.returncode != 0:
        log(f"  D1 error: {r.stderr[-200:]}")
        return False
    return True


# ── IA upload ─────────────────────────────────────────────────────────────────

def ia_upload(ia_id, files, title, public=False, extra_meta=None):
    cmd = ['ia', 'upload', ia_id] + [str(f) for f in files]
    cmd += ['--metadata=mediatype:movies', f'--metadata=title:{title}']
    if not public:
        cmd += ['--metadata=access:private', '--metadata=noindex:true']
    else:
        cmd += ['--metadata=licenseurl:https://creativecommons.org/licenses/by/4.0/']
    if extra_meta:
        for k, v in extra_meta.items():
            cmd.append(f'--metadata={k}:{v}')
    r = subprocess.run(cmd)
    return r.returncode == 0


# ── Long-form stitch ──────────────────────────────────────────────────────────

def stitch(segments, out_path, pub_title):
    """Grade + xfade-concat segments + Satie music."""
    n     = len(segments)
    track = MUSIC_DIR / SATIE_TRACKS[0]
    total = sum(s['dur'] for s in segments)

    cmd = ['ffmpeg', '-y']
    for s in segments:
        cmd += ['-ss', str(s['start']), '-t', str(s['dur']), '-i', s['path']]
    cmd += ['-i', str(track)]

    fc = []
    for i in range(n):
        fc.append(f'[{i}:v]{GRADE}[g{i}]')

    offset = 0.0
    prev = 'g0'
    for i in range(1, n):
        offset += segments[i-1]['dur'] - XFADE_DUR
        label = f'xf{i}' if i < n - 1 else 'vout'
        fc.append(f'[{prev}][g{i}]xfade=transition=fade:duration={XFADE_DUR}:offset={offset:.2f}[{label}]')
        prev = f'xf{i}'

    fc.append(f'[{n}:a]volume=0.8,afade=t=in:st=0:d=2,afade=t=out:st={total-3:.1f}:d=3[aout]')

    cmd += [
        '-filter_complex', ';'.join(fc),
        '-map', '[vout]', '-map', '[aout]',
        '-t', str(total),
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-c:a', 'aac', '-b:a', '192k',
        str(out_path)
    ]

    log(f"Stitching {n} segments ({total:.0f}s total)...")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        log(f"  stitch error: {r.stderr.decode()[-400:]}")
        return False
    mb = Path(out_path).stat().st_size / 1024**2
    log(f"  done — {mb:.0f}MB")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folder',              help='Session folder with raw video clips')
    parser.add_argument('--vault-ia-id',       default=None, help='IA item ID for raw private backup')
    parser.add_argument('--pub-ia-id',         default=None, help='IA item ID for public long-form')
    parser.add_argument('--pub-title',         default=None, help='Title for public long-form video')
    parser.add_argument('--series',            default='footage', help='gab.ae series slug')
    parser.add_argument('--context',           default='Paris, France', help='Location context for tagging')
    parser.add_argument('--openrouter-key',    default=os.environ.get('OPENROUTER_API_KEY'), help='OpenRouter API key')
    parser.add_argument('--cf-api-token',      default=os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN'), help='Cloudflare API token for D1 writes')
    parser.add_argument('--no-vault',          action='store_true', help='Skip per-clip vault upload')
    parser.add_argument('--no-publish',        action='store_true', help='Skip long-form stitch + publish')
    parser.add_argument('--seg-dur',           type=int, default=SEG_DUR, help='Segment duration for long-form (s)')
    parser.add_argument('--max-clips',         type=int, default=None, help='Max clips to include in long-form')
    args = parser.parse_args()

    src_dir = Path(args.folder).expanduser().resolve()
    if not src_dir.is_dir():
        print(f"ERROR: not a folder: {src_dir}"); sys.exit(1)

    api_key = args.openrouter_key
    if not api_key:
        print("ERROR: --openrouter-key or OPENROUTER_API_KEY env var required"); sys.exit(1)

    # ── Scan clips ──────────────────────────────────────────────────────────
    log(f"Scanning {src_dir.name}...")
    clips = []
    for f in sorted(src_dir.rglob('*')):
        if f.suffix not in VIDEO_EXTS or f.name.startswith('.'): continue
        try:
            dur, w, h, rot = probe(f)
            if dur < MIN_CLIP_DUR: continue
            horiz = is_horizontal(w, h, rot)
            clips.append({'path': str(f), 'dur': dur, 'w': w, 'h': h, 'horizontal': horiz})
            log(f"  {f.name}  {dur:.0f}s  {w}x{h}{'  [portrait]' if not horiz else ''}")
        except Exception as e:
            log(f"  SKIP {f.name} — {e}")

    if not clips:
        print("No video clips found."); sys.exit(1)
    h_clips = [c for c in clips if c['horizontal']]
    log(f"{len(clips)} clip(s) found ({len(h_clips)} horizontal, {len(clips)-len(h_clips)} portrait)")

    tmp = Path(tempfile.mkdtemp())
    segments = []

    # ── Per-clip vault pipeline ──────────────────────────────────────────────
    if not args.no_vault:
        if not args.vault_ia_id:
            print("ERROR: --vault-ia-id required (or use --no-vault)"); sys.exit(1)

        log(f"\n── Vault upload → {args.vault_ia_id} ──")
        ia_upload(args.vault_ia_id, [c['path'] for c in clips],
                  title=src_dir.name + ' — Raw',
                  public=False)
        log("  IA upload complete")

        for i, clip in enumerate(clips, 1):
            path = Path(clip['path'])
            slug = f"{args.series}-raw-{i:02d}"
            log(f"\n[{i}/{len(clips)}] {path.name}")

            best_t, _ = best_frame(path, clip['dur'])
            thumb_path = tmp / f"thumb_{i:02d}.jpg"
            extract_thumb(path, best_t, thumb_path)
            log(f"  thumb at t={best_t:.0f}s ({thumb_path.stat().st_size//1024}KB)")

            log("  tagging...")
            meta = tag_clip(path, clip['dur'], api_key, args.context)
            if meta:
                log(f"  → {meta.get('location','?')} · {meta.get('time_of_day','?')} · {meta.get('mood','?')}")

            fname   = path.name
            embed   = f"https://archive.org/embed/{args.vault_ia_id}/{urllib.request.quote(fname)}?autoplay=1"
            title   = meta.get('location', path.stem)[:60] if meta else path.stem
            ok = seed_d1(slug, title, args.series, thumb_path, embed, 'vault', meta, args.cf_api_token)
            log(f"  D1: {'OK' if ok else 'FAILED'}")

            if clip['horizontal']:
                seg_start, seg_dur = best_segment_start(path, clip['dur'], args.seg_dur)
                segments.append({'path': str(path), 'start': seg_start, 'dur': seg_dur})

    else:
        # Still need segments for stitch even if skipping vault
        for clip in h_clips:
            path = Path(clip['path'])
            seg_start, seg_dur = best_segment_start(path, clip['dur'], args.seg_dur)
            segments.append({'path': str(path), 'start': seg_start, 'dur': seg_dur})

    # ── Long-form stitch + publish ───────────────────────────────────────────
    if not args.no_publish:
        if not segments:
            log("No horizontal clips — skipping long-form stitch.")
            sys.exit(0)
        if not args.pub_ia_id:
            print("ERROR: --pub-ia-id required (or use --no-publish)"); sys.exit(1)

        if args.max_clips:
            segments = segments[:args.max_clips]

        pub_title = args.pub_title or src_dir.name
        out_path  = tmp / f"{args.pub_ia_id}.mp4"

        log(f"\n── Long-form stitch ──")
        if not stitch(segments, out_path, pub_title):
            sys.exit(1)

        log(f"\n── Public upload → {args.pub_ia_id} ──")
        ok = ia_upload(args.pub_ia_id, [out_path], title=pub_title, public=True,
                       extra_meta={'subject': 'Paris', 'subject': 'travel'})
        if not ok:
            log("  IA upload failed"); sys.exit(1)
        log("  IA upload complete")

        log("  tagging long-form...")
        best_t, _ = best_frame(out_path, sum(s['dur'] for s in segments))
        thumb_path = tmp / 'longform_thumb.jpg'
        extract_thumb(out_path, best_t, thumb_path)
        meta = tag_clip(out_path, sum(s['dur'] for s in segments), api_key, args.context)
        if meta:
            log(f"  → {meta.get('description','')[:80]}")

        fname = out_path.name
        embed = f"https://archive.org/embed/{args.pub_ia_id}/{urllib.request.quote(fname)}?autoplay=1"
        slug  = args.pub_ia_id
        ok = seed_d1(slug, pub_title, args.series, thumb_path, embed, 'processed', meta, args.cf_api_token)
        log(f"  D1: {'OK' if ok else 'FAILED'}")

        log(f"\n✓ Published: https://archive.org/details/{args.pub_ia_id}")
        log(f"✓ Live at:   https://gab.ae/videos")

    log(f"\n✓ Vault:     https://gab.ae/vault")
    log("All done.")


if __name__ == '__main__':
    main()
