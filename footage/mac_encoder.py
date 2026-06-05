#!/usr/bin/env python3
"""
Mac encoder — streams continuously to VPS nginx-rtmp.
VideoToolbox hardware decode → H.264 encode → push to rtmp://VPS:1935/live
VPS relays to YouTube. When this disconnects, VPS falls back to musique service.

Architecture: single long-running ffmpeg that reads from a named FIFO pipe.
A producer loop feeds raw video frames into the pipe, picking random clips.
Audio is a separate looping music track — no cuts between clips.
"""

import os, sys, random, subprocess, signal, time, glob, json, threading, struct

FOOTAGE_DIRS = [
    "/Volumes/obiwan/2026-06-03 - Multiple exports/1",
    "/Volumes/obiwan/2026-06-03 - Multiple exports/2",
    "/Volumes/obiwan/2026-06-03 - Multiple exports/DCIM",
]
MUSIC_DIR  = "/Users/gab/Desktop/gab-ae/footage/music"
VPS_RTMP   = "rtmp://138.201.21.95:1935/live"
FIFO_PATH  = "/tmp/mac_encoder_fifo"
CLIP_DUR   = 20      # seconds per clip
MIN_OFFSET = 5
WIDTH, HEIGHT, FPS = 1920, 1080, 30


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


def make_fifo():
    if os.path.exists(FIFO_PATH):
        os.unlink(FIFO_PATH)
    os.mkfifo(FIFO_PATH)


def producer(videos, stop_event):
    """Feed raw yuv420p frames into FIFO — one clip at a time, seamlessly."""
    clip_n = 0
    while not stop_event.is_set():
        video = random.choice(videos)
        dur   = get_duration(video)
        max_s = max(0, dur - CLIP_DUR - MIN_OFFSET)
        start = random.uniform(MIN_OFFSET, max_s) if max_s > MIN_OFFSET else 0
        clip_n += 1
        print(f"  [{clip_n}] {os.path.basename(video)} @{start:.0f}s", flush=True)

        cmd = [
            "ffmpeg", "-y",
            "-hwaccel", "videotoolbox",
            "-ss", str(start), "-t", str(CLIP_DUR),
            "-i", video,
            "-vf", (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                    f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps={FPS},format=yuv420p"),
            "-f", "rawvideo",
            "-an",
            FIFO_PATH,
        ]
        proc = subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
        proc.wait()

        if stop_event.is_set():
            break


def run():
    print("=== Mac Encoder → VPS nginx-rtmp ===")
    print(f"VPS: {VPS_RTMP}")

    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    videos = find_videos()
    if not videos:
        print("No footage found — is obiwan mounted?")
        sys.exit(1)
    print(f"Found {len(videos)} clips")

    music = pick_music()
    if not music:
        print("No music in", MUSIC_DIR)
        sys.exit(1)
    print(f"Music: {os.path.basename(music)}")

    make_fifo()

    stop_event = threading.Event()
    prod_thread = threading.Thread(target=producer, args=(videos, stop_event), daemon=True)
    prod_thread.start()

    # Consumer: read raw frames from FIFO, encode H.264, mix music, push to VPS
    cmd = [
        "ffmpeg", "-y",
        # Raw video from producer
        "-f", "rawvideo",
        "-pix_fmt", "yuv420p",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS),
        "-i", FIFO_PATH,
        # Music loops forever
        "-stream_loop", "-1", "-i", music,
        "-filter_complex",
        "[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "4000k",
        "-pix_fmt", "yuv420p", "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-f", "flv", VPS_RTMP,
    ]

    errors = 0
    while True:
        print("Starting ffmpeg consumer...", flush=True)
        proc = subprocess.run(cmd, stderr=subprocess.PIPE)
        err = proc.stderr.decode()[-500:] if proc.returncode != 0 else ""

        stop_event.set()
        errors += 1
        wait = min(errors * 5, 30)
        print(f"ffmpeg exited ({proc.returncode}), restarting in {wait}s...")
        if err:
            print(err)

        time.sleep(wait)

        # Reset for retry
        stop_event.clear()
        videos = find_videos()
        music  = pick_music()
        make_fifo()
        prod_thread = threading.Thread(target=producer, args=(videos, stop_event), daemon=True)
        prod_thread.start()


if __name__ == "__main__":
    run()
