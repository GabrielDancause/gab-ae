#!/usr/bin/env python3
"""
make_best_of.py — "WHAT A DAY ON EARTH" — Best of Paris across all days.

Sources:
  - Google Drive: LRF proxy clips from previous days (small, fast download)
  - Local _done/: today's full 4K DJI files (hero shots)

Usage:
  python3 -m footage.make_best_of --title "WHAT A DAY ON EARTH"
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

# ── Config ────────────────────────────────────────────────────────────────────
DONE_DIR    = Path.home() / 'Downloads' / '_Pipeline' / '_done'
READY_DIR   = Path(__file__).parent / 'mac_ready'
MUSIC_DIR   = Path(__file__).parent / 'music'
READY_QUEUE = Path(__file__).parent / 'mac_ready_queue.json'

TARGET_W, TARGET_H = 1080, 1920
FPS_OUT = 30
REGULAR_DUR = 3.5    # seconds per normal clip
HERO_DUR    = 9.0    # slow-mo output (4.5s source × 2)
MAX_LRF_MB  = 150    # skip LRF files larger than this (too slow to download)
MIN_LRF_MB  = 8      # skip tiny stubs (< 5s of content)

# Drive folder IDs with Paris LRF proxies
DRIVE_SOURCES = [
    {'name': '2026-05-02 - Paris',                   'id': '1Pdq10ebAWzX7ffYpPwYtGa3RAeDK0wtE', 'n_clips': 3},
    {'name': '2026-05-03 - Paris afternoon/evening', 'id': '1wlAdkaBqjgCNXMqV4Yd7kZK352TRjmW2', 'n_clips': 3},
]
LOCAL_SOURCES = [
    {'name': '2026-05-08 - Paris, France', 'n_clips': 5, 'hero': True},
]

SESSION_GAP_MIN = 30


# ── Helpers ────────────────────────────────────────────────────────────────────

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

def split_sessions(files, gap_min=SESSION_GAP_MIN):
    files = sorted(files, key=lambda f: extract_ts(f.name) or datetime.min)
    sessions, cur, prev = [], [], None
    for f in files:
        t = extract_ts(f.name)
        if prev and t and (t-prev).total_seconds() > gap_min*60:
            sessions.append(cur); cur=[]
        cur.append(f); prev=t
    if cur: sessions.append(cur)
    return sessions


# ── Drive LRF download ─────────────────────────────────────────────────────────

def drive_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(
        str(Path(__file__).parent / 'token.json'))
    return build('drive','v3',credentials=creds,cache_discovery=False)

def list_lrf_files(svc, folder_id):
    """Return LRF files sorted by size, filtered to usable range."""
    files = []
    page_token = None
    while True:
        r = svc.files().list(
            q=f"'{folder_id}' in parents and name contains '.LRF' and trashed=false",
            fields='files(id,name,size)',
            pageSize=100, pageToken=page_token,
        ).execute()
        files += r.get('files',[])
        page_token = r.get('nextPageToken')
        if not page_token: break
    usable = [f for f in files
              if MIN_LRF_MB*1024**2 < int(f.get('size',0)) < MAX_LRF_MB*1024**2]
    return sorted(usable, key=lambda f: int(f.get('size',0)))

def download_file(svc, file_id, out_path):
    """Stream download a Drive file."""
    from googleapiclient.http import MediaIoBaseDownload
    import io
    req = svc.files().get_media(fileId=file_id)
    buf = io.FileIO(str(out_path), 'wb')
    dl  = MediaIoBaseDownload(buf, req, chunksize=8*1024*1024)
    done = False
    while not done:
        status, done = dl.next_chunk()
        if status:
            pct = int(status.progress()*100)
            print(f"\r    {pct}%", end='', flush=True)
    print()
    buf.close()


# ── AI frame picker ────────────────────────────────────────────────────────────

def pick_best_moment(video_path, n=6, context='cinematic travel'):
    info = probe_video(video_path)
    if not info: return None
    dur, w, h, fps = info
    if dur < 4: return dur/2

    lo, hi = dur*0.15, dur*0.85
    candidates = [lo + (hi-lo)*i/max(n-1,1) for i in range(n)]

    with tempfile.TemporaryDirectory() as td:
        frames = []
        for i, t in enumerate(candidates):
            out = Path(td)/f"f{i:02d}.jpg"
            subprocess.run(
                ['ffmpeg','-y','-ss',str(t),'-i',str(video_path),
                 '-frames:v','1','-q:v','4','-vf','scale=480:-1',str(out)],
                capture_output=True)
            if out.exists():
                frames.append((t, out.read_bytes()))

        if not frames: return candidates[len(candidates)//2]

        try:
            from openai import OpenAI
            client = OpenAI()
            content = [{"type":"text","text":(
                f"Film editor picking clips for a {context} highlight reel. "
                f"From these {len(frames)} frames, pick the most visually striking — "
                "strong composition, interesting motion or subject, cinematic light. "
                "Reply ONLY with the zero-based index number."
            )}]
            for i,(t,data) in enumerate(frames):
                b64 = base64.b64encode(data).decode()
                content.append({"type":"image_url",
                    "image_url":{"url":f"data:image/jpeg;base64,{b64}","detail":"low"}})
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role":"user","content":content}],
                max_tokens=5)
            raw = resp.choices[0].message.content.strip()
            idx = int(re.search(r'\d+', raw).group())
            idx = max(0, min(idx, len(frames)-1))
            log(f"    AI → frame {idx} (t={frames[idx][0]:.1f}s)")
            return frames[idx][0]
        except Exception as e:
            log(f"    AI failed ({e}), using middle")
            return frames[len(frames)//2][0]


# ── Clip extraction ────────────────────────────────────────────────────────────

def crop_filter(w, h):
    cw = int(h * TARGET_W / TARGET_H)
    ch = h
    if cw > w: cw=w; ch=int(w*TARGET_H/TARGET_W)
    cx=(w-cw)//2; cy=(h-ch)//2
    return f"crop={cw}:{ch}:{cx}:{cy},scale={TARGET_W}:{TARGET_H}"

def extract_clip(src, center_t, duration, out_path, slow_mo=False):
    info = probe_video(src)
    if not info: raise RuntimeError(f"Can't probe {src}")
    total, w, h, fps = info
    vf = crop_filter(w, h)

    if slow_mo:
        src_dur = duration / 2        # half-speed: grab half the output duration from source
        start = max(0.0, min(center_t - src_dur/2, total - src_dur - 0.1))
        vf += ",setpts=2.0*PTS"
        cmd = ['ffmpeg','-y','-ss',str(start),'-i',str(src),'-t',str(src_dur),
               '-vf',vf,'-af','atempo=0.5',
               '-r',str(FPS_OUT),'-c:v','libx264','-preset','ultrafast','-crf','21',
               '-c:a','aac','-ar','44100','-b:a','128k', str(out_path)]
    else:
        start = max(0.0, min(center_t - duration/2, total - duration - 0.1))
        cmd = ['ffmpeg','-y','-ss',str(start),'-i',str(src),'-t',str(duration),
               '-vf',vf,
               '-r',str(FPS_OUT),'-c:v','libx264','-preset','ultrafast','-crf','21',
               '-c:a','aac','-ar','44100','-b:a','128k', str(out_path)]
    run(cmd, quiet=True)
    mb = Path(out_path).stat().st_size/1024**2
    log(f"    → {Path(out_path).name} ({mb:.0f} MB, {'slow-mo' if slow_mo else 'normal'})")
    return out_path


# ── Beat detection ─────────────────────────────────────────────────────────────

def detect_beats(music_path, limit_s=70.0):
    log(f"  Beat detection: {Path(music_path).name}...")
    try:
        import librosa
        y, sr = librosa.load(str(music_path), sr=None, duration=limit_s)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = [float(b) for b in librosa.frames_to_time(beat_frames,sr=sr) if b < limit_s]
        log(f"  {len(beats)} beats found")
        return beats
    except Exception as e:
        log(f"  Fallback 100BPM ({e})")
        return [i*0.6 for i in range(int(limit_s/0.6))]


# ── Title card overlay ────────────────────────────────────────────────────────

def add_title_card(video_path, title, out_path, duration_s=2.5):
    """Burn title text over the first `duration_s` seconds. Falls back to copy on error."""
    import shutil

    font_candidates = [
        '/System/Library/Fonts/HelveticaNeue.ttc',
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/SFNSDisplay.ttf',
        '/System/Library/Fonts/Arial.ttf',
        '/Library/Fonts/Arial.ttf',
    ]
    font = next((f for f in font_candidates if Path(f).exists()), None)
    if not font:
        log("  No font found — copying without title card")
        shutil.copy2(video_path, out_path)
        return

    lines = title.split()
    mid   = max(1, len(lines)//2)
    line1 = ' '.join(lines[:mid])
    line2 = ' '.join(lines[mid:])

    # Simple fade-in alpha: 0→1 over first 0.5s, hold, no fade-out
    def text_filter(text, y_expr, size=70):
        alpha = f"min(1,t/0.5)"
        return (
            f"drawtext=fontfile='{font}':text='{text}':"
            f"fontsize={size}:fontcolor=white:borderw=3:bordercolor=black@0.6:"
            f"x=(w-text_w)/2:y={y_expr}:alpha='{alpha}':enable='lte(t,{duration_s})'"
        )

    vf = text_filter(line1, 'h/2-80') + ',' + text_filter(line2, 'h/2+10')

    r = subprocess.run(
        ['ffmpeg','-y','-i',str(video_path),
         '-vf', vf,
         '-c:v','libx264','-preset','ultrafast','-crf','20',
         '-c:a','copy', str(out_path)],
        capture_output=True)

    if r.returncode != 0 or not Path(out_path).exists():
        log(f"  Title card failed ({r.stderr[-200:].decode(errors='ignore').strip()}) — copying without")
        shutil.copy2(video_path, out_path)
    else:
        log(f"  Title card burned ✓")


# ── Assembly ──────────────────────────────────────────────────────────────────

def concat_clips(paths, out):
    with tempfile.NamedTemporaryFile('w',suffix='.txt',delete=False) as f:
        for p in paths: f.write(f"file '{p}'\n")
        lst = f.name
    try:
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',lst,'-c','copy',str(out)])
    finally:
        os.unlink(lst)

def mix_music(video, music, out, fade_s=2.5):
    info = probe_video(video)
    total = info[0] if info else 60.0
    fade_start = max(0, total - fade_s)
    # Simple: replace audio entirely with music (no original audio blend — avoids stream issues)
    run(['ffmpeg','-y',
         '-i', str(video),
         '-i', str(music),
         '-filter_complex',
         (f'[1:a]atrim=0:{total},asetpts=PTS-STARTPTS,'
          f'afade=t=out:st={fade_start:.2f}:d={fade_s},'
          f'volume=1.4[aout]'),
         '-map', '0:v',
         '-map', '[aout]',
         '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k',
         '-shortest',
         str(out)],
        quiet=False)

def pick_music(prefer=None):
    if prefer:
        p = MUSIC_DIR / prefer
        if p.exists(): return p
    # Prefer upbeat/epic tracks by name
    for name in ['magical_day.mp3','dreaming_altitude.mp3','journeys_begin.mp3',
                  'beautiful_things.mp3','beauty_flow.mp3']:
        p = MUSIC_DIR / name
        if p.exists(): return p
    mp3s = list(MUSIC_DIR.glob('*.mp3'))
    return mp3s[0] if mp3s else None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--title',  default='WHAT A DAY ON EARTH')
    ap.add_argument('--music',  default=None, help='specific mp3 filename')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    # Load OpenAI key from .env
    env_file = Path(__file__).parent.parent / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

    log(f"Best of Paris — '{args.title}'")

    music_path = pick_music(args.music)
    if not music_path:
        print("ERROR: no music"); sys.exit(1)
    log(f"Music: {music_path.name}")
    beats = detect_beats(music_path)

    READY_DIR.mkdir(exist_ok=True)

    # ── Collect clips: Drive LRF (previous days) + local 4K (today) ──
    # Format: list of dicts: {src_path, is_hero, day_label}
    # We'll fill this list, then sort chronologically, insert hero near end

    svc = drive_service()
    clip_sources = []   # (Path, is_hero, label)

    with tempfile.TemporaryDirectory(prefix='bestof_') as td:
        td = Path(td)

        # ── Previous days via Drive LRF ──
        for src in DRIVE_SOURCES:
            log(f"\nDrive source: {src['name']}")
            lrfs = list_lrf_files(svc, src['id'])
            log(f"  {len(lrfs)} usable LRF files found")
            picks = lrfs[:src['n_clips']]   # smallest first = fastest download

            for lrf in picks:
                mb = int(lrf.get('size',0))/1024**2
                log(f"  Downloading {lrf['name']} ({mb:.0f} MB)...")
                lrf_path = td / lrf['name']
                download_file(svc, lrf['id'], lrf_path)

                info = probe_video(lrf_path)
                if not info:
                    log("    Can't probe, skipping"); continue
                dur,w,h,fps = info
                log(f"    {dur:.1f}s, {w}×{h} @ {fps:.0f}fps")
                clip_sources.append((lrf_path, False, src['name']))

        # ── Today via local 4K ──
        local_cfg = LOCAL_SOURCES[0]
        local_dir = DONE_DIR / local_cfg['name']
        if local_dir.exists():
            log(f"\nLocal source: {local_cfg['name']}")
            dji_files = sorted(local_dir.glob('dji_mimo_20260507*.MP4'))
            if not dji_files:
                dji_files = sorted(local_dir.glob('dji_mimo_*.MP4'))

            sessions = split_sessions(dji_files)
            log(f"  {len(dji_files)} DJI files, {len(sessions)} sessions")

            # Pick n_clips files spread across sessions; longest session gets hero
            n_local = local_cfg['n_clips']
            hero_sess = max(sessions, key=lambda s: sum(
                (probe_video(f) or (0,))[0] for f in s))

            # Hero = longest file in hero session
            hero_file = max(hero_sess,
                key=lambda f: (probe_video(f) or (0,))[0])
            clip_sources.append((hero_file, True, local_cfg['name']))

            # Regular local clips: pick from different sessions, skip hero file
            added = 0
            for sess in sessions:
                for f in sorted(sess, key=lambda x: (probe_video(x) or (0,))[0], reverse=True):
                    if f == hero_file: continue
                    if added >= n_local - 1: break
                    clip_sources.append((f, False, local_cfg['name']))
                    added += 1
                if added >= n_local - 1: break
        else:
            log(f"  WARNING: local folder not found: {local_dir}")

        log(f"\nTotal sources: {len(clip_sources)}")
        if args.dry_run:
            for p, hero, label in clip_sources:
                info = probe_video(p)
                dur = info[0] if info else 0
                print(f"  {'[HERO] ' if hero else '       '}{p.name[:55]} ({dur:.1f}s) from {label}")
            return

        # ── Assign beat slots ──
        # Order: Drive clips first (older days), then local (today), hero near 2/3
        drive_clips = [(p,h,l) for p,h,l in clip_sources if not h and 'Paris, France' not in l]
        local_clips  = [(p,h,l) for p,h,l in clip_sources if not h and 'Paris, France' in l]
        hero_clips   = [(p,h,l) for p,h,l in clip_sources if h]

        insert_at = max(2, (len(drive_clips)+len(local_clips))*2//3)
        ordered = drive_clips[:insert_at] + hero_clips + drive_clips[insert_at:] + local_clips

        music_t = beats[2] if len(beats)>2 else 1.0   # brief musical intro before first cut
        cut_plan = []
        for (src, is_hero, label) in ordered:
            dur = HERO_DUR if is_hero else REGULAR_DUR
            cut_plan.append((src, is_hero, music_t, dur))
            clip_end = music_t + dur
            next_beat = next((b for b in beats if b > clip_end), clip_end + 0.5)
            music_t = next_beat

        total_dur = music_t + 2.0
        log(f"\nReel plan: {len(cut_plan)} clips, ~{total_dur:.0f}s")
        for i,(f,hero,mt,dur) in enumerate(cut_plan):
            log(f"  {i+1:2d}. {'[HERO] ' if hero else '       '}{f.name[:45]}  t={mt:.1f}s for {dur:.0f}s")

        # ── Extract all clips ──
        log(f"\nExtracting {len(cut_plan)} clips...")
        extracted = []

        for i, (src, is_hero, music_t, clip_dur) in enumerate(cut_plan):
            log(f"\nClip {i+1}/{len(cut_plan)}: {src.name[:55]}")
            center_t = pick_best_moment(src, context='Paris travel, cinematic')
            if center_t is None:
                info = probe_video(src)
                center_t = info[0]/2 if info else 30.0
            out = td / f"clip_{i:02d}.mp4"
            extract_clip(src, center_t, clip_dur, out, slow_mo=is_hero)
            extracted.append(out)

        # ── Concatenate ──
        log("\nConcatenating...")
        raw_concat = td/'concat_raw.mp4'
        concat_clips([str(p) for p in extracted], raw_concat)

        # ── Add title card ──
        log(f"Adding title card: '{args.title}'")
        titled = td/'concat_titled.mp4'
        add_title_card(raw_concat, args.title, titled)

        # ── Mix music ──
        log("Mixing music...")
        safe_title = re.sub(r'[^a-zA-Z0-9]+','_', args.title).strip('_')
        out_name = f"bestof_paris_{safe_title}.mp4"
        final_path = READY_DIR / out_name
        mix_music(titled, music_path, final_path)

    size_mb = final_path.stat().st_size/1024**2
    log(f"\n{'='*55}")
    log(f"Done! → {out_name} ({size_mb:.0f} MB, ~{total_dur:.0f}s)")

    # ── Queue for upload ──
    location = 'Paris, France'
    entry = {
        'drive_id':     f'bestof_paris_{safe_title}',
        'name':         'Best of Paris',
        'title':        args.title,
        'description':  (f'A week in Paris.\n\n'
                         f'#shorts #paris #france #travel #pov #cinematic #highlights'),
        'channel':      'gab2',
        'local_file':   str(final_path),
        'ts_processed': ts(),
        'uploaded':     False,
    }
    q_path = READY_QUEUE
    q = json.loads(q_path.read_text()) if q_path.exists() else []
    q.append(entry)
    q_path.write_text(json.dumps(q, indent=2))
    log(f"Queued: '{entry['title']}'")


if __name__ == '__main__':
    main()
