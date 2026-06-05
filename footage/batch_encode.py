#!/usr/bin/env python3
"""
Batch encode random clips from all footage folders.
Encodes at 1080p60, crops square sources to 16:9, rsyncs to server.

Usage:
    python3 batch_encode.py
    python3 batch_encode.py --prefix nh --no-push
    python3 batch_encode.py --base "/Volumes/obiwan/North Hatley" --prefix nh
    python3 batch_encode.py --clips 3 --min 5 --max 20

Flags:
    --prefix SLUG     Prefix for output files: {prefix}_{idx:04d}_{n}.mp4
                      Prevents naming collisions when mixing multiple encode batches.
    --base DIR        Override source directory (default: ENCODE_BASE env var)
    --out DIR         Override output directory (default: ENCODE_OUT env var)
    --clips N         Clips per source file (default: 2)
    --min N           Min clip duration in seconds (default: 8)
    --max N           Max clip duration in seconds (default: 25)
    --parallel N      Parallel encodes (default: 6)
    --no-push         Encode locally only — skip rsync and service restart.
                      Useful for staging a special broadcast before swapping live.
"""

import argparse, os, glob, random, subprocess, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_BASE    = os.environ.get("ENCODE_BASE", "/Volumes/obiwan/2026-06-03 - Multiple exports")
DEFAULT_OUT_DIR = os.environ.get("ENCODE_OUT",  "/tmp/broadcast_batch")
SERVER          = "root@138.201.21.95"
SERVER_DIR      = "/opt/broadcast"


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


def process(src, idx, out_dir, prefix, clips_per_file, clip_min_dur, clip_max_dur):
    try:
        dur, w, h = probe(src)
    except Exception:
        return []

    if dur < clip_min_dur + 2:
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

    stem = f"{prefix}_{idx:04d}" if prefix else f"clip_{idx:04d}"

    results = []
    max_offset = dur - clip_max_dur - 1
    for n in range(clips_per_file):
        clip_dur = random.randint(clip_min_dur, clip_max_dur)
        offset   = random.uniform(1, max(2, max_offset))
        out      = os.path.join(out_dir, f"{stem}_{n}.mp4")

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
    parser = argparse.ArgumentParser(description="Batch-encode footage clips for 24/7 broadcast")
    parser.add_argument("--prefix",   default="",           help="Output filename prefix (e.g. 'nh' → nh_0001_0.mp4)")
    parser.add_argument("--base",     default=DEFAULT_BASE, help="Source footage directory")
    parser.add_argument("--out",      default=DEFAULT_OUT_DIR, help="Output directory for encoded clips")
    parser.add_argument("--clips",    type=int, default=2,  help="Clips per source file (default: 2)")
    parser.add_argument("--min",      type=int, default=8,  help="Min clip duration seconds (default: 8)")
    parser.add_argument("--max",      type=int, default=25, help="Max clip duration seconds (default: 25)")
    parser.add_argument("--parallel", type=int, default=6,  help="Parallel encoding workers (default: 6)")
    parser.add_argument("--no-push",  action="store_true",  help="Skip rsync and service restart")
    args = parser.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    sources = []
    # Try numbered subdirs first, fall back to scanning BASE directly
    subdirs = sorted([d for d in os.listdir(args.base) if os.path.isdir(os.path.join(args.base, d))])
    search_dirs = [os.path.join(args.base, d) for d in subdirs] if subdirs else [args.base]
    for sd in search_dirs:
        sources += sorted(glob.glob(os.path.join(sd, "**", "*.MP4"), recursive=True))
        sources += sorted(glob.glob(os.path.join(sd, "**", "*.mp4"), recursive=True))
    # exclude LRF sidecar files
    sources = [s for s in sources if not s.upper().endswith(".LRF")]
    sources = sorted(set(sources))

    prefix_label = f"[prefix={args.prefix}] " if args.prefix else ""
    print(f"Found {len(sources)} source files → ~{len(sources)*args.clips} clips  {prefix_label}")
    print(f"Output: {out_dir}")
    if args.no_push:
        print("  --no-push: will NOT rsync or restart service\n")
    else:
        print()

    all_clips = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {
            ex.submit(process, src, i, out_dir, args.prefix, args.clips, args.min, args.max): src
            for i, src in enumerate(sources)
        }
        for fut in as_completed(futs):
            all_clips.extend(fut.result())

    print(f"\n{len(all_clips)} clips encoded.")

    if args.no_push:
        print(f"Skipping push (--no-push). Clips are in: {out_dir}")
        print("To push manually: rsync -av --exclude '*.wip.mp4' " +
              f"{out_dir}/ {SERVER}:{SERVER_DIR}/")
        return

    print("Rsyncing to server...")
    subprocess.run([
        "rsync", "-av", "--progress",
        "--exclude", "*.wip.mp4",
        out_dir + "/",
        f"{SERVER}:{SERVER_DIR}/"
    ], check=True)

    print("\nRestarting musique service...")
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    "systemctl restart musique"], check=True)
    print("Done! Stream updated.")


if __name__ == "__main__":
    main()
