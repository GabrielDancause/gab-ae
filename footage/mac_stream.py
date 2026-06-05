#!/usr/bin/env python3
"""
Musique et scènes mondaines — Mac direct streamer.
Uses VideoToolbox hardware HEVC decode. Streams random 15s clips to YouTube forever.
"""

import os, sys, random, subprocess, signal, time, glob, json

FOOTAGE_DIRS = [
    "/Volumes/obiwan/2026-06-03 - Multiple exports/1",
    "/Volumes/obiwan/2026-06-03 - Multiple exports/2",
    "/Volumes/obiwan/2026-06-03 - Multiple exports/DCIM",
]
MUSIC_DIR   = "/Users/gab/Desktop/gab-ae/footage/music"
RTMP_FILE   = "/tmp/broadcast_info.json"
CLIP_DURATION = 15
MIN_OFFSET    = 5


def get_rtmp_url():
    with open(RTMP_FILE) as f:
        info = json.load(f)
    return info["rtmp_url"]

def find_videos():
    files = []
    for d in FOOTAGE_DIRS:
        if not os.path.exists(d):
            continue
        for pat in ["*.MP4", "*.mp4", "*.MOV", "*.mov"]:
            files.extend(glob.glob(os.path.join(d, "**", pat), recursive=True))
    return files

def get_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=10)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 120.0

def pick_music():
    tracks = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    return random.choice(tracks) if tracks else None

def stream_clip(video, start, music, rtmp_url):
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "videotoolbox",
        "-ss", str(start), "-t", str(CLIP_DURATION),
        "-i", video,
        "-stream_loop", "-1", "-i", music,
        "-filter_complex",
        "[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]",
        "-map", "0:v:0", "-map", "[aout]",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4000k",
        "-pix_fmt", "yuv420p", "-g", "60",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-f", "flv", rtmp_url,
    ]
    proc = subprocess.run(cmd, stderr=subprocess.DEVNULL)
    return proc.returncode

def run():
    print("=== Musique et scènes mondaines — Mac Streamer ===")
    rtmp_url = get_rtmp_url()
    print(f"RTMP: {rtmp_url[:60]}...")
    print(f"Music: {MUSIC_DIR}")

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    clip_n = 0
    errors = 0

    while True:
        videos = find_videos()
        if not videos:
            print("No footage found — check that obiwan is mounted")
            time.sleep(15)
            continue

        video  = random.choice(videos)
        dur    = get_duration(video)
        max_s  = max(0, dur - CLIP_DURATION - MIN_OFFSET)
        start  = random.uniform(MIN_OFFSET, max_s) if max_s > MIN_OFFSET else 0
        music  = pick_music()
        clip_n += 1

        print(f"[{clip_n}] {os.path.basename(video)} @{start:.0f}s  music={os.path.basename(music)}")
        ret = stream_clip(video, start, music, rtmp_url)

        if ret != 0:
            errors += 1
            wait = min(errors * 3, 30)
            print(f"  ffmpeg exit {ret} — waiting {wait}s")
            time.sleep(wait)
        else:
            errors = 0

if __name__ == "__main__":
    run()
