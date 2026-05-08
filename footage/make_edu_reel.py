#!/usr/bin/env python3
"""
make_edu_reel.py — educational text-over-footage Short.

Usage:
  python3 -m footage.make_edu_reel
  python3 -m footage.make_edu_reel --dry-run
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
DONE_DIR    = Path.home() / 'Downloads' / '_Pipeline' / '_done'
READY_DIR   = Path(__file__).parent / 'mac_ready'
MUSIC_DIR   = Path(__file__).parent / 'music'
READY_QUEUE = Path(__file__).parent / 'mac_ready_queue.json'

TARGET_W, TARGET_H = 1080, 1920
FPS_OUT = 30

# ── Script ────────────────────────────────────────────────────────────────────
TITLE    = "France changed everything. Even that."
MUSIC    = "outside_the_hotel.mp3"    # moody, slower — fits the subject

SCRIPT = [
    # (text, duration_s, style)
    # style: "hook" | "fact" | "punch" | "stat" | "close"
    ("France decriminalized homosexuality\nin 1791.",                  5.0, "hook"),
    ("During the Revolution,\nthey rewrote the entire legal\ncode from scratch.", 4.5, "fact"),
    ("Their principle:\nno act between consenting adults\ncould be a crime.",     4.5, "fact"),
    ("Homosexuality wasn't banned.\nIt simply wasn't mentioned.",                  4.0, "fact"),
    ("The UK kept it illegal\nuntil 1967.",                            3.5, "stat"),
    ("176 years later.",                                               3.0, "punch"),
    ("The US didn't fully\ndecriminalize until 2003.",                 3.5, "stat"),
    ("212 years later.",                                               3.0, "punch"),
    ("France didn't legalize\nsame-sex marriage until 2013\n— but that's another story.", 5.0, "fact"),
    ("The Revolution changed\neverything.\n\nEven that.",             5.0, "close"),
]

# ── Style config per card type ─────────────────────────────────────────────────
STYLES = {
    "hook":  {"font_size": 72, "pill_alpha": 200, "text_color": (255, 255, 255), "y_frac": 0.18},
    "fact":  {"font_size": 58, "pill_alpha": 170, "text_color": (255, 255, 255), "y_frac": 0.72},
    "stat":  {"font_size": 62, "pill_alpha": 170, "text_color": (255, 220, 120), "y_frac": 0.72},
    "punch": {"font_size": 88, "pill_alpha": 200, "text_color": (255, 255, 255), "y_frac": 0.72},
    "close": {"font_size": 66, "pill_alpha": 200, "text_color": (255, 255, 255), "y_frac": 0.50},
}


# ── Utils ─────────────────────────────────────────────────────────────────────

def log(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
def ts():     return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=quiet)
    if r.returncode != 0 and not quiet:
        raise subprocess.CalledProcessError(r.returncode, cmd)
    return r

def probe_video(path):
    r = subprocess.run(
        ['ffprobe','-v','quiet','-print_format','json',
         '-show_streams','-show_format', str(path)],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        vs = next((s for s in d.get('streams',[]) if s.get('codec_type')=='video'), None)
        if not vs: return None
        dur = float(d.get('format',{}).get('duration', vs.get('duration',0)))
        w,h = int(vs['width']), int(vs['height'])
        fps_s = vs.get('r_frame_rate','30/1')
        n,dv = fps_s.split('/')
        return dur, w, h, float(n)/float(dv)
    except: return None

def extract_ts(name):
    m = re.search(r'(\d{8})(\d{6})', name)
    if not m: return None
    try: return datetime.strptime(m.group(1)+m.group(2),'%Y%m%d%H%M%S')
    except: return None


# ── Text overlay rendering ────────────────────────────────────────────────────

def render_text_overlay(text, style_key, out_png, fade_in=0.4):
    """
    Render a text card as a 1080×1920 RGBA PNG using Pillow.
    Returns the PNG path.
    """
    from PIL import Image, ImageDraw, ImageFont

    style = STYLES[style_key]
    font_size   = style["font_size"]
    pill_alpha  = style["pill_alpha"]
    text_color  = style["text_color"]
    y_frac      = style["y_frac"]

    # Load font
    font_path = '/System/Library/Fonts/HelveticaNeue.ttc'
    if not Path(font_path).exists():
        font_path = '/System/Library/Fonts/Supplemental/Arial.ttf'
    try:
        font = ImageFont.truetype(font_path, font_size)
        font_small = ImageFont.truetype(font_path, max(24, font_size - 16))
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    W, H = TARGET_W, TARGET_H
    img  = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    lines = text.split('\n')
    padding_x = 48
    padding_y = 22
    line_gap  = 10
    corner_r  = 20

    # Measure each line
    line_sizes = []
    for line in lines:
        if line.strip():
            bbox = draw.textbbox((0, 0), line, font=font)
            line_sizes.append((bbox[2]-bbox[0], bbox[3]-bbox[1]))
        else:
            line_sizes.append((0, font_size // 2))

    block_w = max(w for w,_ in line_sizes) + padding_x * 2
    block_h = sum(h for _,h in line_sizes) + line_gap * (len(lines)-1) + padding_y * 2
    block_w = min(block_w, W - 80)   # never wider than screen

    x0 = (W - block_w) // 2
    y0 = int(H * y_frac - block_h / 2)
    y0 = max(60, min(y0, H - block_h - 60))
    x1, y1 = x0 + block_w, y0 + block_h

    # Draw pill background
    pill = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    pdraw.rounded_rectangle([x0, y0, x1, y1],
                              radius=corner_r,
                              fill=(0, 0, 0, pill_alpha))
    img = Image.alpha_composite(img, pill)
    draw = ImageDraw.Draw(img)

    # Draw text lines
    ty = y0 + padding_y
    for i, (line, (lw, lh)) in enumerate(zip(lines, line_sizes)):
        tx = (W - lw) // 2
        if line.strip():
            # Shadow
            draw.text((tx+2, ty+2), line, font=font, fill=(0,0,0,160))
            # Main
            draw.text((tx, ty), line, font=font, fill=text_color+(255,))
        ty += lh + line_gap

    img.save(str(out_png), 'PNG')
    return out_png


def render_animated_overlay(text, style_key, duration_s, out_path, fps=FPS_OUT):
    """
    Build a video overlay: transparent background, text fades in over 0.4s then holds.
    Uses apng sequence → ffmpeg.
    Actually: render ONE png and use ffmpeg fade filter.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        png = td / 'overlay.png'
        render_text_overlay(text, style_key, png)

        # Build video from still image with alpha fade-in
        fade_in_s = 0.4
        # ffmpeg: image → video with geq for alpha fade-in
        run(['ffmpeg', '-y',
             '-loop', '1', '-i', str(png),
             '-t', str(duration_s),
             '-vf', (f'geq=r=\'r(X,Y)\':g=\'g(X,Y)\':b=\'b(X,Y)\':'
                     f'a=\'if(lt(T,{fade_in_s}),T/{fade_in_s},1)*alpha(X,Y)\''),
             '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
             '-pix_fmt', 'yuva420p',
             '-r', str(fps),
             str(out_path)], quiet=True)
    return out_path


# ── Clip extraction ────────────────────────────────────────────────────────────

def crop_filter(w, h):
    cw = int(h * TARGET_W / TARGET_H)
    ch = h
    if cw > w: cw=w; ch=int(w*TARGET_H/TARGET_W)
    cx=(w-cw)//2; cy=(h-ch)//2
    return f"crop={cw}:{ch}:{cx}:{cy},scale={TARGET_W}:{TARGET_H}"

def extract_clip(src, center_t, duration, out_path):
    info = probe_video(src)
    if not info: raise RuntimeError(f"Can't probe {src}")
    total, w, h, fps = info
    start = max(0.0, min(center_t - duration/2, total - duration - 0.1))
    vf = crop_filter(w, h)
    run(['ffmpeg','-y',
         '-ss', str(start), '-i', str(src), '-t', str(duration),
         '-vf', vf,
         '-r', str(FPS_OUT),
         '-c:v','libx264','-preset','ultrafast','-crf','21',
         '-an',                      # no audio — we'll add music at the end
         str(out_path)], quiet=True)
    return out_path

def overlay_text_on_clip(video, text_vid, out_path):
    """Composite text overlay (with alpha) onto video clip."""
    run(['ffmpeg','-y',
         '-i', str(video),
         '-i', str(text_vid),
         '-filter_complex',
         '[0:v][1:v]overlay=0:0:format=auto',
         '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20',
         '-an',
         str(out_path)], quiet=True)
    return out_path


# ── Beat detection ─────────────────────────────────────────────────────────────

def detect_beats(music_path, limit_s=65.0):
    try:
        import librosa
        y, sr = librosa.load(str(music_path), sr=None, duration=limit_s)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = [float(b) for b in librosa.frames_to_time(beat_frames, sr=sr) if b < limit_s]
        log(f"  {len(beats)} beats detected in {Path(music_path).name}")
        return beats
    except Exception as e:
        log(f"  Beat detection failed ({e}), fixed 0.8s intervals")
        return [i * 0.8 for i in range(int(limit_s / 0.8))]


# ── Source files ───────────────────────────────────────────────────────────────

def pick_source_files(folder_name, n_needed):
    """Pick n_needed diverse DJI clips from _done/folder_name."""
    folder = DONE_DIR / folder_name
    if not folder.exists():
        raise RuntimeError(f"Folder not found: {folder}")

    dji = sorted(folder.glob('dji_mimo_20260507*.MP4'))
    if not dji:
        dji = sorted(folder.glob('dji_mimo_*.MP4'))

    if not dji:
        raise RuntimeError("No DJI files found")

    # Pick evenly spaced files for variety
    if len(dji) <= n_needed:
        return dji * (n_needed // len(dji) + 1)

    step = len(dji) / n_needed
    picks = [dji[int(i * step)] for i in range(n_needed)]
    return picks


def pick_center_time(src_path, i, total):
    """Spread extraction points across each clip for variety."""
    info = probe_video(src_path)
    if not info: return 30.0
    dur = info[0]
    # Divide clip into sections, pick middle of each section
    frac = 0.2 + 0.6 * (i / max(total - 1, 1))
    return dur * frac


# ── Music mix ─────────────────────────────────────────────────────────────────

def mix_music(video, music, out, fade_s=2.0):
    info = probe_video(video)
    total = info[0] if info else 60.0
    fade_start = max(0, total - fade_s)
    run(['ffmpeg','-y',
         '-i', str(video),
         '-i', str(music),
         '-filter_complex',
         (f'[1:a]atrim=0:{total},asetpts=PTS-STARTPTS,'
          f'afade=t=out:st={fade_start:.2f}:d={fade_s},'
          f'volume=1.2[aout]'),
         '-map', '0:v', '-map', '[aout]',
         '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k', '-shortest',
         str(out)], quiet=False)


def concat_clips(paths, out):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        for p in paths: f.write(f"file '{p}'\n")
        lst = f.name
    try:
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',lst,
             '-c','copy', str(out)])
    finally:
        os.unlink(lst)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folder', default='2026-05-08 - Paris, France')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    total_dur = sum(d for _,d,_ in SCRIPT)
    log(f"Edu reel: {len(SCRIPT)} cards, ~{total_dur:.0f}s total")
    log(f"Subject: {TITLE}")

    music_path = MUSIC_DIR / MUSIC
    if not music_path.exists():
        # Fallback
        mp3s = list(MUSIC_DIR.glob('*.mp3'))
        music_path = mp3s[0] if mp3s else None
    if not music_path:
        print("ERROR: no music"); sys.exit(1)
    log(f"Music: {music_path.name}")

    beats = detect_beats(music_path)

    if args.dry_run:
        for i, (text, dur, style) in enumerate(SCRIPT):
            print(f"\nCard {i+1} [{style}] ({dur}s):")
            print(f"  {repr(text)}")
        print(f"\nTotal: {total_dur:.0f}s")
        return

    # ── Source clips: one per script card ──
    sources = pick_source_files(args.folder, len(SCRIPT))
    log(f"Using {len(sources)} source clips from {args.folder}")

    READY_DIR.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='edu_') as td:
        td = Path(td)
        final_clips = []

        for i, (text, dur, style) in enumerate(SCRIPT):
            src = sources[i % len(sources)]
            log(f"\nCard {i+1}/{len(SCRIPT)} [{style}]: {src.name[:45]}")

            # Extract video clip
            center_t = pick_center_time(src, i, len(SCRIPT))
            clip_raw = td / f'clip_{i:02d}_raw.mp4'
            log(f"  Extracting {dur}s at t={center_t:.1f}s...")
            extract_clip(src, center_t, dur, clip_raw)

            # Render text overlay
            log(f"  Rendering text overlay...")
            text_vid = td / f'text_{i:02d}.mp4'
            render_animated_overlay(text, style, dur, text_vid)

            # Composite
            log(f"  Compositing...")
            final_clip = td / f'card_{i:02d}.mp4'
            overlay_text_on_clip(clip_raw, text_vid, final_clip)
            final_clips.append(final_clip)

        # ── Concatenate all cards ──
        log(f"\nConcatenating {len(final_clips)} cards...")
        concat_raw = td / 'concat.mp4'
        concat_clips([str(p) for p in final_clips], concat_raw)

        # ── Mix music ──
        log("Mixing music...")
        safe = re.sub(r'[^a-zA-Z0-9]+','_', TITLE).strip('_')[:40]
        out_name = f"edu_{safe}.mp4"
        final_path = READY_DIR / out_name
        mix_music(concat_raw, music_path, final_path)

    size_mb = final_path.stat().st_size / 1024**2
    log(f"\n{'='*55}")
    log(f"Done! → {out_name}  ({size_mb:.0f} MB, {total_dur:.0f}s)")

    # Queue
    entry = {
        'drive_id':     f'edu_{safe}',
        'name':         TITLE,
        'title':        TITLE,
        'description':  ('The French Revolution changed everything. Even that.\n\n'
                         '#shorts #france #paris #history #lgbtq #facts #didyouknow'),
        'channel':      'gab2',
        'local_file':   str(final_path),
        'ts_processed': ts(),
        'uploaded':     False,
    }
    q = json.loads(READY_QUEUE.read_text()) if READY_QUEUE.exists() else []
    q.append(entry)
    READY_QUEUE.write_text(json.dumps(q, indent=2))
    log(f"Queued: '{entry['title']}'")


if __name__ == '__main__':
    main()
