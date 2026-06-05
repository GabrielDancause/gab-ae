#!/usr/bin/env python3
"""
Batch encode random clips from all footage folders.
Encodes at 1080p60, crops square sources to 16:9, rsyncs to server.
"""

import os, glob, random, subprocess, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE    = "/Volumes/obiwan/2026-06-03 - Multiple exports"
OUT_DIR = "/tmp/broadcast_batch"
SERVER  = "root@138.201.21.95"
SERVER_DIR = "/opt/broadcast"

CLIPS_PER_FILE = 2
CLIP_MIN_DUR   = 8
CLIP_MAX_DUR   = 25
PARALLEL       = 6


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, timeout=15)
    d = json.loads(r.stdout)
    dur = float(d["format"]["duration"])
    vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    return dur, int(vs.get("width", 0)), int(vs.get("height", 0))


def encode(src, offset, dur, out, vf):
    tmp = out + ".wip.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(offset), "-t", str(dur),
        "-hwaccel", "videotoolbox",
        "-i", src,
        "-vf", vf,
        "-c:v", "h264_videotoolbox",
        "-b:v", "8000k", "-maxrate", "8000k", "-bufsize", "16000k",
        "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", "60", "-g", "120", "-an",
        tmp,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        os.rename(tmp, out)
        return True
    if os.path.exists(tmp):
        os.unlink(tmp)
    return False


def process(src, idx):
    try:
        dur, w, h = probe(src)
    except Exception:
        return []

    if dur < CLIP_MIN_DUR + 2:
        return []

    # crop square to 16:9, centre-crop portrait to 16:9, scale 16:9 to 1080p
    if w == h:
        # square → crop top/bottom to 16:9
        vf = "crop={}:{}:0:{},scale=1920:1080".format(w, int(w * 9 / 16), int((h - w * 9 / 16) / 2))
    elif w < h:
        # portrait → crop sides to 16:9 (take centre width)
        new_w = int(h * 16 / 9)
        x_off = int((w - new_w) / 2)
        vf = "crop={}:{}:{}:0,scale=1920:1080".format(new_w, h, x_off)
    else:
        # landscape 16:9 → scale to 1080p
        vf = "scale=1920:1080"

    results = []
    max_offset = dur - CLIP_MAX_DUR - 1
    for n in range(CLIPS_PER_FILE):
        clip_dur = random.randint(CLIP_MIN_DUR, CLIP_MAX_DUR)
        offset   = random.uniform(1, max(2, max_offset))
        out      = os.path.join(OUT_DIR, f"clip_{idx:04d}_{n}.mp4")

        if os.path.exists(out):
            results.append(out)
            continue

        ok = encode(src, offset, clip_dur, out, vf)
        label = os.path.basename(src)
        if ok:
            print(f"  ✓ {label} clip {n+1}  ({clip_dur}s @ {offset:.0f}s)", flush=True)
            results.append(out)
        else:
            print(f"  ✗ {label} clip {n+1} FAILED", flush=True)

    return results


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    sources = []
    for d in range(1, 8):
        sources += sorted(glob.glob(os.path.join(BASE, str(d), "**", "*.MP4"), recursive=True))
        sources += sorted(glob.glob(os.path.join(BASE, str(d), "**", "*.mp4"), recursive=True))
    # exclude LRF sidecar files
    sources = [s for s in sources if not s.upper().endswith(".LRF")]
    sources = sorted(set(sources))

    print(f"Found {len(sources)} source files → ~{len(sources)*CLIPS_PER_FILE} clips")
    print(f"Output: {OUT_DIR}\n")

    all_clips = []
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        futs = {ex.submit(process, src, i): src for i, src in enumerate(sources)}
        for fut in as_completed(futs):
            all_clips.extend(fut.result())

    print(f"\n{len(all_clips)} clips encoded. Rsyncing to server...")
    subprocess.run([
        "rsync", "-av", "--progress",
        OUT_DIR + "/",
        f"{SERVER}:{SERVER_DIR}/"
    ], check=True)

    print("\nRestarting musique service...")
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    "systemctl restart musique"], check=True)
    print("Done! Stream updated.")


if __name__ == "__main__":
    main()
