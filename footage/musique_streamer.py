#!/usr/bin/env python3
"""
Musique et scènes mondaines — YouTube 24/7 Live Streamer
Single ffmpeg: loops all pre-transcoded clips, copies video (no re-encode), streams music.
"""

import os, sys, random, subprocess, signal, time, glob

FOOTAGE_DIR = "/opt/footage_1080p"
MUSIC_DIR   = "/opt/music"
RTMP_FILE   = "/opt/rtmp_url.txt"
PLAYLIST    = "/tmp/musique_playlist.txt"


def get_rtmp_url():
    with open(RTMP_FILE) as f:
        return f.read().strip()

def find_videos():
    files = []
    for pat in ["*.mp4", "*.MP4"]:
        files.extend(glob.glob(os.path.join(FOOTAGE_DIR, "**", pat), recursive=True))
    return sorted(f for f in files if "_wip" not in f)

def pick_music():
    tracks = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    return random.choice(tracks) if tracks else None

def write_playlist(videos):
    with open(PLAYLIST, "w") as f:
        for v in videos:
            f.write(f"file '{v}'\n")

def run():
    print("=== Musique et scènes mondaines ===")
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    errors = 0
    while True:
        videos = find_videos()
        if not videos:
            print("No footage yet, waiting...")
            time.sleep(15)
            continue

        music = pick_music()
        if not music:
            print("No music, waiting...")
            time.sleep(15)
            continue

        random.shuffle(videos)
        write_playlist(videos)
        rtmp_url = get_rtmp_url()

        print(f"Starting stream — {len(videos)} clips, music: {os.path.basename(music)}")

        cmd = [
            "ffmpeg", "-y",
            # Video: loop playlist forever
            "-stream_loop", "-1",
            "-f", "concat", "-safe", "0", "-i", PLAYLIST,
            # Audio: music loops forever
            "-stream_loop", "-1", "-i", music,
            "-filter_complex", "[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            # Copy video — no re-encoding, zero CPU
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-f", "flv", rtmp_url,
        ]

        proc = subprocess.run(cmd, stderr=subprocess.PIPE)
        err = proc.stderr.decode()[-300:] if proc.returncode != 0 else ""

        errors += 1
        wait = min(errors * 5, 30)
        print(f"ffmpeg exited ({proc.returncode}), restarting in {wait}s...")
        if err:
            print(err)
        time.sleep(wait)

if __name__ == "__main__":
    run()
