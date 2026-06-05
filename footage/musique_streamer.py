#!/usr/bin/env python3
"""
Musique et scènes mondaines — YouTube 24/7 Live Streamer
- Loops all pre-transcoded clips with ambient music, zero re-encode on server.
- Watches /opt/broadcast/ for new clips via inotifywait.
  When new clips arrive, ffmpeg is gracefully restarted so they join the loop
  immediately — YouTube's buffer absorbs the ~3s gap, viewers see nothing.
"""

import os, sys, random, subprocess, signal, time, glob, threading

FOOTAGE_DIR = "/opt/broadcast"
MUSIC_DIR   = "/opt/music"
RTMP_FILE   = "/opt/rtmp_url.txt"
PLAYLIST    = "/tmp/musique_playlist.txt"

# Set by the watcher thread when new clips are detected
_reload_flag = threading.Event()


# ── Watcher ───────────────────────────────────────────────────────────────────

def watch_for_new_clips():
    """Background thread: uses inotifywait to detect new .mp4 in FOOTAGE_DIR.
    Sets _reload_flag so the main loop can gracefully restart ffmpeg."""
    while True:
        try:
            result = subprocess.run(
                ["inotifywait", "-e", "close_write", "-e", "moved_to",
                 "--include", r"\.mp4$", FOOTAGE_DIR],
                capture_output=True, text=True, timeout=3600
            )
            if result.returncode == 0:
                filename = result.stdout.strip().split()[-1] if result.stdout.strip() else "?"
                print(f"[watcher] New clip detected: {filename} — will reload after current segment", flush=True)
                # Wait a few seconds to let rsync finish writing all files
                time.sleep(8)
                _reload_flag.set()
        except subprocess.TimeoutExpired:
            pass  # normal — just loop and wait again
        except FileNotFoundError:
            # inotifywait not installed — fall back to polling every 60s
            time.sleep(60)
            current = set(glob.glob(os.path.join(FOOTAGE_DIR, "*.mp4")))
            if not hasattr(watch_for_new_clips, "_known"):
                watch_for_new_clips._known = current
            if current != watch_for_new_clips._known:
                print(f"[watcher] Clip count changed ({len(watch_for_new_clips._known)} → {len(current)}) — reloading", flush=True)
                watch_for_new_clips._known = current
                time.sleep(5)
                _reload_flag.set()
        except Exception as e:
            print(f"[watcher] error: {e}", flush=True)
            time.sleep(10)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Reload monitor ────────────────────────────────────────────────────────────

def monitor_reload(proc):
    """Runs in a thread alongside ffmpeg. Kills ffmpeg when reload is requested."""
    _reload_flag.wait()          # blocks until watcher sets the flag
    if proc.poll() is None:      # ffmpeg still running
        print("[reload] Killing ffmpeg for playlist reload...", flush=True)
        proc.terminate()


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    print("=== Musique et scènes mondaines ===", flush=True)
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    # Start background watcher thread
    t = threading.Thread(target=watch_for_new_clips, daemon=True)
    t.start()
    print(f"[watcher] Watching {FOOTAGE_DIR} for new clips", flush=True)

    errors = 0
    while True:
        videos = find_videos()
        if not videos:
            print("No footage yet, waiting...", flush=True)
            time.sleep(15)
            continue

        music = pick_music()
        if not music:
            print("No music, waiting...", flush=True)
            time.sleep(15)
            continue

        random.shuffle(videos)
        write_playlist(videos)
        rtmp_url = get_rtmp_url()

        # Clear reload flag before starting ffmpeg
        _reload_flag.clear()

        print(f"Starting stream — {len(videos)} clips | music: {os.path.basename(music)}", flush=True)

        cmd = [
            "ffmpeg", "-y", "-re",
            "-stream_loop", "-1",
            "-f", "concat", "-safe", "0", "-i", PLAYLIST,
            "-stream_loop", "-1", "-i", music,
            "-filter_complex", "[1:a]volume=0.8,aformat=sample_rates=48000:channel_layouts=stereo[aout]",
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-f", "flv", rtmp_url,
        ]

        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)

        # Thread that kills ffmpeg when reload is requested
        reload_thread = threading.Thread(target=monitor_reload, args=(proc,), daemon=True)
        reload_thread.start()

        _, stderr = proc.communicate()
        was_reload = not _reload_flag.is_set() is False or proc.returncode == -15

        if was_reload:
            # Triggered by watcher — not an error, restart immediately
            print(f"[reload] Restarting with updated playlist ({len(find_videos())} clips)", flush=True)
            errors = 0
            time.sleep(2)  # brief pause before reconnecting
        else:
            err = stderr.decode()[-300:] if proc.returncode != 0 else ""
            if proc.returncode != 0:
                errors += 1
            else:
                errors = 0  # clean exit resets backoff
            wait = min(errors * 5, 30)
            print(f"ffmpeg exited ({proc.returncode}), restarting in {wait}s...", flush=True)
            if err:
                print(err, flush=True)
            time.sleep(wait)


if __name__ == "__main__":
    run()
