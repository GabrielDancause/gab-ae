#!/usr/bin/env python3
"""
make_highlight_reel.py — builds a beat-synced highlight reel Short.

Structure:
  - One best clip per session (AI-picked best moment)
  - Cuts land on music beats
  - Hero clip (longest/best session) gets a slow-mo treatment
  - Total runtime: ~45-58s

Usage:
  python3 -m footage.make_highlight_reel "2026-05-08 - Paris, France"
  python3 -m footage.make_highlight_reel "2026-05-08 - Paris, France" --hero-session 5
  python3 -m footage.make_highlight_reel "2026-05-08 - Paris, France" --dry-run
"""

import argparse
import base64
import json
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
LIBRARY     = Path(__file__).parent / 'library.json'
READY_QUEUE = Path(__file__).parent / 'mac_ready_queue.json'

SESSION_GAP_MIN = 30
TARGET_W, TARGET_H = 1080, 1920   # 9:16 HD
FPS_OUT = 30


# ── Utils ──────────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ts():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def run(cmd, quiet=True):
    kwargs = dict(capture_output=True) if quiet else {}
    return subprocess.run(cmd, check=True, **kwargs)


def probe_video(path):
    """Return (duration, width, height, fps) or None."""
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-show_format', str(path)],
        capture_output=True, text=True
    )
    try:
        d = json.loads(r.stdout)
    except Exception:
        return None
    vs = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not vs:
        return None
    try:
        dur = float(d.get('format', {}).get('duration', vs.get('duration', 0)))
        w, h = int(vs['width']), int(vs['height'])
        fps_s = vs.get('r_frame_rate', '30/1')
        num, den = fps_s.split('/')
        fps = float(num) / float(den)
        return dur, w, h, fps
    except Exception:
        return None


def extract_timestamp(name):
    m = re.search(r'(\d{8})(\d{6})', name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
    except Exception:
        return None


def split_into_sessions(files, gap_min=SESSION_GAP_MIN):
    files = sorted(files, key=lambda f: extract_timestamp(f.name) or datetime.min)
    sessions, cur, prev_ts = [], [], None
    for f in files:
        t = extract_timestamp(f.name)
        if prev_ts and t and (t - prev_ts).total_seconds() > gap_min * 60:
            sessions.append(cur)
            cur = []
        cur.append(f)
        prev_ts = t
    if cur:
        sessions.append(cur)
    return sessions


# ── Beat detection ─────────────────────────────────────────────────────────────

def detect_beats(music_path, limit_s=65.0):
    """Return sorted list of beat timestamps (seconds) within limit_s."""
    log(f"Detecting beats in {Path(music_path).name}...")
    try:
        import librosa
        y, sr = librosa.load(str(music_path), sr=None, duration=limit_s)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        beats = [float(b) for b in beats if b < limit_s]
        log(f"  {len(beats)} beats detected")
        return beats
    except Exception as e:
        log(f"  Beat detection failed ({e}), using 120 BPM fallback")
        interval = 60.0 / 120
        return [i * interval for i in range(int(limit_s / interval))]


# ── AI frame picker ────────────────────────────────────────────────────────────

def pick_best_moment(video_path, n=6):
    """
    Sample n frames across the middle 60% of the clip.
    Use GPT-4o-mini to pick the most cinematic one.
    Returns best timestamp in seconds.
    """
    info = probe_video(video_path)
    if not info:
        return None
    dur, w, h, fps = info
    if dur < 4:
        return None

    # Sample points across 20%-80% of duration
    lo, hi = dur * 0.20, dur * 0.80
    candidates = [lo + (hi - lo) * i / max(n - 1, 1) for i in range(n)]

    with tempfile.TemporaryDirectory() as td:
        frames = []
        for i, t in enumerate(candidates):
            out = Path(td) / f"frame_{i:02d}.jpg"
            subprocess.run(
                ['ffmpeg', '-y', '-ss', str(t), '-i', str(video_path),
                 '-frames:v', '1', '-q:v', '4', '-vf', 'scale=480:-1', str(out)],
                capture_output=True
            )
            if out.exists():
                frames.append((t, out.read_bytes()))

        if not frames:
            return candidates[len(candidates) // 2]

        try:
            from openai import OpenAI
            client = OpenAI()
            content = [{
                "type": "text",
                "text": (
                    "You are a film editor choosing clips for a cinematic travel Short. "
                    f"These {len(frames)} frames are from the same video. "
                    "Pick the single most visually striking and cinematic frame — "
                    "consider: strong composition, interesting action, good light, emotional impact. "
                    "Reply with ONLY the zero-based index number of the best frame."
                )
            }]
            for i, (t, data) in enumerate(frames):
                b64 = base64.b64encode(data).decode()
                content.append({"type": "image_url",
                                 "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                               "detail": "low"}})
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": content}],
                max_tokens=5,
            )
            raw = resp.choices[0].message.content.strip()
            idx = int(re.search(r'\d+', raw).group())
            idx = max(0, min(idx, len(frames) - 1))
            log(f"    AI picked frame {idx} (t={frames[idx][0]:.1f}s)")
            return frames[idx][0]
        except Exception as e:
            log(f"    AI pick failed ({e}), using middle frame")
            return frames[len(frames) // 2][0]


# ── Clip extraction ────────────────────────────────────────────────────────────

def make_crop_filter(w, h):
    """Center-crop to 9:16, scale to TARGET_W × TARGET_H."""
    crop_w = int(h * TARGET_W / TARGET_H)
    crop_h = h
    if crop_w > w:          # already taller than wide (e.g. iPhone portrait)
        crop_w = w
        crop_h = int(w * TARGET_H / TARGET_W)
    crop_x = (w - crop_w) // 2
    crop_y = (h - crop_h) // 2
    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={TARGET_W}:{TARGET_H}"


def extract_clip(src, center_t, duration, out_path, slow_mo=False):
    """
    Extract `duration` seconds centered on center_t from src.
    If slow_mo=True, grabs 2× source duration and plays at half speed (60fps→30fps).
    Encodes to 9:16 H.264 ultrafast.
    """
    info = probe_video(src)
    if not info:
        raise RuntimeError(f"Can't probe {src}")
    dur_total, w, h, fps = info

    if slow_mo:
        src_dur = duration * 2          # grab 2x source
        start = max(0.0, center_t - src_dur / 2)
        start = min(start, dur_total - src_dur - 0.1)
        vf = make_crop_filter(w, h) + ",setpts=2.0*PTS"
        af = "atempo=0.5"
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start), '-i', str(src), '-t', str(src_dur),
            '-vf', vf, '-af', af,
            '-r', str(FPS_OUT),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-c:a', 'aac', '-ar', '44100', '-b:a', '128k',
            str(out_path),
        ]
    else:
        start = max(0.0, center_t - duration / 2)
        start = min(start, dur_total - duration - 0.1)
        vf = make_crop_filter(w, h)
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start), '-i', str(src), '-t', str(duration),
            '-vf', vf,
            '-r', str(FPS_OUT),
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22',
            '-c:a', 'aac', '-ar', '44100', '-b:a', '128k',
            str(out_path),
        ]
    run(cmd)
    size_mb = Path(out_path).stat().st_size / 1024 / 1024
    log(f"    → {Path(out_path).name} ({size_mb:.0f} MB, {'slow-mo' if slow_mo else 'normal'})")
    return out_path


# ── Assembly ──────────────────────────────────────────────────────────────────

def concat_clips(clip_paths, out_path):
    """Losslessly concatenate clips using the concat demuxer."""
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
        list_file = f.name
    try:
        run([
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            str(out_path),
        ])
    finally:
        os.unlink(list_file)


def mix_music(video_path, music_path, out_path, fade_out_s=2.0):
    """Replace audio with music, fade out at end."""
    info = probe_video(video_path)
    if not info:
        raise RuntimeError("Can't probe assembled video")
    total_dur = info[0]
    fade_start = max(0, total_dur - fade_out_s)

    run([
        'ffmpeg', '-y',
        '-i', str(video_path),
        '-i', str(music_path),
        '-filter_complex',
        (f'[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,'
         f'afade=t=out:st={fade_start:.2f}:d={fade_out_s}[music];'
         f'[0:a]volume=0.08[orig];'          # faint original audio underneath
         f'[music][orig]amix=inputs=2:duration=first[aout]'),
        '-map', '0:v', '-map', '[aout]',
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        str(out_path),
    ])


def pick_music():
    """Pick a random track from library.json."""
    try:
        lib = json.loads(LIBRARY.read_text())
        track = lib[0] if lib else None
        if track:
            p = Path(track['path'].replace('~', str(Path.home())))
            if p.exists():
                return p
    except Exception:
        pass
    # Fallback: any mp3 in music dir
    mp3s = list(MUSIC_DIR.glob('*.mp3'))
    return mp3s[0] if mp3s else None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder', help='Folder name, e.g. "2026-05-08 - Paris, France"')
    ap.add_argument('--hero-session', type=int, default=0,
                    help='Which session (1-based) gets the slow-mo hero treatment (0=auto=largest)')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    folder_path = DONE_DIR / args.folder
    if not folder_path.exists():
        # Also check processing dir
        proc = Path.home() / 'Downloads' / '_Pipeline' / '_processing' / args.folder
        if proc.exists():
            folder_path = proc
        else:
            print(f"ERROR: folder not found: {folder_path}")
            sys.exit(1)

    log(f"Highlight reel: {args.folder}")

    # ── Collect DJI files (most cinematic, 4K 60fps) ──
    dji_files = sorted(folder_path.glob('dji_mimo_20260507*.MP4'))
    if not dji_files:
        # Fallback: any DJI file from the day
        dji_files = sorted(folder_path.glob('dji_mimo_*.MP4'))
    if not dji_files:
        print("ERROR: no DJI files found")
        sys.exit(1)

    # ── Split into sessions ──
    sessions = split_into_sessions(dji_files)
    log(f"Found {len(dji_files)} DJI clips across {len(sessions)} sessions")

    if args.dry_run:
        for i, sess in enumerate(sessions, 1):
            gb = sum(probe_video(f)[0] for f in sess if probe_video(f)) / 60
            print(f"  Session {i}: {len(sess)} files, ~{gb:.0f} min")
        return

    # ── Pick music & detect beats ──
    music_path = pick_music()
    if not music_path:
        print("ERROR: no music found")
        sys.exit(1)
    log(f"Music: {music_path.name}")
    beats = detect_beats(music_path)

    # ── Build clip list: multiple files per session, proportional to size ──
    # Target 7-8 clips total. Hero = longest clip in biggest session, slow-mo.
    TARGET_CLIPS = 8
    REGULAR_DUR  = 4.0
    HERO_DUR     = 8.0   # slow-mo output duration (grabs 4s of 60fps source)

    # For each session, assign how many clips to pull
    total_files = sum(len(s) for s in sessions)
    clips_per_session = []
    for sess in sessions:
        n = max(1, round(len(sess) / total_files * TARGET_CLIPS))
        clips_per_session.append(n)
    # Adjust so total = TARGET_CLIPS
    while sum(clips_per_session) > TARGET_CLIPS:
        clips_per_session[clips_per_session.index(max(clips_per_session))] -= 1
    while sum(clips_per_session) < TARGET_CLIPS - 1:
        clips_per_session[clips_per_session.index(min(clips_per_session))] += 1

    # Hero session = biggest session
    hero_sess_idx = max(range(len(sessions)),
                        key=lambda i: sum(probe_video(f)[0] or 0 for f in sessions[i]))
    log(f"Hero session: {hero_sess_idx + 1} ({clips_per_session[hero_sess_idx]} clips, one slow-mo)")

    # Build ordered (sess_idx, file, is_hero) list
    # Hero clip inserted near position 5/6 of the total list
    clip_plan = []   # (file_path, is_hero)
    for sess_idx, (sess, n_clips) in enumerate(zip(sessions, clips_per_session)):
        probed = [(probe_video(f), f) for f in sess]
        probed = [(p, f) for p, f in probed if p]
        # Sort by duration descending — longer files = more interesting content
        probed.sort(key=lambda x: x[0][0], reverse=True)
        picks = probed[:n_clips]
        for i, (info, f) in enumerate(picks):
            is_hero = (sess_idx == hero_sess_idx and i == 0)  # longest file in hero session
            clip_plan.append((f, is_hero))

    # Reorder: hero clip at position ~2/3 through the reel
    hero_items = [(f, True) for f, h in clip_plan if h]
    other_items = [(f, False) for f, h in clip_plan if not h]
    insert_pos = max(3, len(other_items) * 2 // 3)
    ordered_plan = other_items[:insert_pos] + hero_items + other_items[insert_pos:]

    # ── Assign music beat slots ──
    cut_times = []   # (file, is_hero, music_start_t, clip_dur)
    music_t = beats[1] if len(beats) > 1 else 1.0

    for (src_file, is_hero) in ordered_plan:
        dur = HERO_DUR if is_hero else REGULAR_DUR
        cut_times.append((src_file, is_hero, music_t, dur))
        clip_end = music_t + dur
        next_beat = next((b for b in beats if b > clip_end), clip_end + 0.5)
        music_t = next_beat

    total_music = music_t + 1.5
    log(f"Reel: {len(cut_times)} clips, ~{total_music:.0f}s total")
    for i, (f, hero, mt, dur) in enumerate(cut_times):
        log(f"  Clip {i+1}: {f.name[:40]} {'[HERO slow-mo]' if hero else ''} "
            f"at t={mt:.1f}s for {dur:.0f}s")

    # ── Extract clips ──
    log("\nExtracting clips (ultrafast encode)...")
    READY_DIR.mkdir(exist_ok=True)

    extracted = []
    with tempfile.TemporaryDirectory(prefix='reel_') as td:
        td = Path(td)

        for clip_i, (src_file, is_hero, music_t, clip_dur) in enumerate(cut_times):
            log(f"\nClip {clip_i+1}/{len(cut_times)}: {src_file.name[:50]}")
            info = probe_video(src_file)
            if not info:
                log("  Can't probe — skipping")
                continue

            log(f"  Picking best moment...")
            center_t = pick_best_moment(src_file)
            if center_t is None:
                center_t = info[0] / 2

            out = td / f"clip_{clip_i:02d}.mp4"
            extract_clip(src_file, center_t, clip_dur, out, slow_mo=is_hero)
            extracted.append((out, music_t, clip_dur))

        if not extracted:
            log("ERROR: no clips extracted")
            sys.exit(1)

        # ── Concatenate ──
        log("\nConcatenating clips...")
        concat_path = td / 'concat.mp4'
        concat_clips([str(p) for p, _, _ in extracted], concat_path)

        # ── Mix music ──
        log("Mixing music...")
        folder_safe = args.folder.replace(' ', '_').replace(',', '')
        out_name = f"{folder_safe}_highlight.mp4"
        final_path = READY_DIR / out_name
        mix_music(concat_path, music_path, final_path)

    size_mb = final_path.stat().st_size / 1024 / 1024
    log(f"\n{'='*50}")
    log(f"Done! → {final_path.name} ({size_mb:.0f} MB)")
    log(f"Duration: ~{total_music:.0f}s")

    # ── Queue for upload ──
    location = re.sub(r'^\d{4}-\d{2}-\d{2}\s*-\s*', '', args.folder).strip()
    city = location.split(',')[0].strip()
    hashtags = ' '.join(f'#{w.lower()}' for w in location.replace(',', '').split())

    entry = {
        'drive_id':    args.folder + '_highlight',
        'name':        args.folder,
        'title':       f'{location} — highlights',
        'description': f'Shot in {location}.\n\n#shorts {hashtags} #travel #pov #highlights',
        'channel':     'gab2',
        'local_file':  str(final_path),
        'ts_processed': ts(),
        'uploaded':    False,
    }

    q_path = READY_QUEUE
    q = json.loads(q_path.read_text()) if q_path.exists() else []
    q.append(entry)
    q_path.write_text(json.dumps(q, indent=2))
    log(f"Queued: '{entry['title']}'")
    log(f"Upload with: python3 -m footage.mac_upload_scheduler")


if __name__ == '__main__':
    main()
