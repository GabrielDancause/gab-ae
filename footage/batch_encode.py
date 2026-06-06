#!/usr/bin/env python3
"""
Batch encode random clips from all footage folders.
Encodes at 1080p60, crops square sources to 16:9, rsyncs to server.

Usage:
    python3 batch_encode.py
    python3 batch_encode.py --prefix nh --no-push
    python3 batch_encode.py --base "/Volumes/obiwan/North Hatley" --prefix nh
    python3 batch_encode.py --clips 3 --min 5 --max 20
    python3 batch_encode.py --vertical --prefix v --out /Volumes/obiwan/broadcast_vertical

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
    --vertical        Output 1080x1920 (9:16) for vertical stream.
                      Portrait clips → scale; square clips → crop centre strip;
                      landscape clips → pillarbox with blurred sides.
                      Rsyncs to /opt/broadcast_vertical/ instead of /opt/broadcast/.
"""

import argparse, os, glob, random, subprocess, json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_BASE    = os.environ.get("ENCODE_BASE", "/Volumes/obiwan/2026-06-03 - Multiple exports")
DEFAULT_OUT_DIR = os.environ.get("ENCODE_OUT",  "/Volumes/obiwan/broadcast_ready")
SERVER          = "root@138.201.21.95"
SERVER_DIR_H    = "/opt/broadcast"           # landscape
SERVER_DIR_V    = "/opt/broadcast_vertical"  # vertical


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


def build_vf(w, h, vertical=False):
    """Return the ffmpeg -vf string for this source resolution."""
    if vertical:
        # Target: 1080x1920 (9:16)
        if w == h:
            # Square → crop centre vertical strip (9:16)
            new_h = h
            new_w = int(h * 9 / 16)
            x_off = int((w - new_w) / 2)
            return f"crop={new_w}:{new_h}:{x_off}:0,scale=1080:1920"
        elif h > w:
            # Portrait — already 9:16-ish, just scale
            return "scale=1080:1920"
        else:
            # Landscape → pillarbox: blur + scale background, overlay scaled clip centred
            return (
                "split=2[bg][fg];"
                "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,boxblur=20:20[blurred];"
                "[fg]scale=-2:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black[fg_padded];"
                "[blurred][fg_padded]overlay=0:0"
            )
    else:
        # Target: 1920x1080 (16:9)
        if w == h:
            # Square → crop top/bottom to 16:9
            return "crop={}:{}:0:{},scale=1920:1080".format(
                w, int(w * 9 / 16), int((h - w * 9 / 16) / 2))
        elif w < h:
            # Portrait → crop sides to 16:9
            new_w = int(h * 16 / 9)
            x_off = int((w - new_w) / 2)
            return "crop={}:{}:{}:0,scale=1920:1080".format(new_w, h, x_off)
        else:
            # Landscape → scale to 1080p
            return "scale=1920:1080"


def should_include(w, h, vertical):
    """Filter sources by orientation for each stream."""
    if vertical:
        # Include portrait and square; skip pure landscape
        return h >= w
    else:
        # Include landscape and square; skip pure portrait
        return w >= h


def process(src, idx, out_dir, prefix, clips_per_file, clip_min_dur, clip_max_dur, vertical):
    try:
        dur, w, h = probe(src)
    except Exception:
        return []

    if dur < clip_min_dur + 2:
        return []

    if not should_include(w, h, vertical):
        return []

    vf = build_vf(w, h, vertical)
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
    parser.add_argument("--prefix",   default="",              help="Output filename prefix (e.g. 'nh' → nh_0001_0.mp4)")
    parser.add_argument("--base",     default=DEFAULT_BASE,    help="Source footage directory")
    parser.add_argument("--out",      default=DEFAULT_OUT_DIR, help="Output directory for encoded clips")
    parser.add_argument("--clips",    type=int, default=2,     help="Clips per source file (default: 2)")
    parser.add_argument("--min",      type=int, default=8,     help="Min clip duration seconds (default: 8)")
    parser.add_argument("--max",      type=int, default=25,    help="Max clip duration seconds (default: 25)")
    parser.add_argument("--parallel", type=int, default=6,     help="Parallel encoding workers (default: 6)")
    parser.add_argument("--no-push",  action="store_true",     help="Skip rsync and service restart")
    parser.add_argument("--vertical", action="store_true",     help="Encode for vertical stream (1080x1920)")
    args = parser.parse_args()

    # Default out dir gets a _vertical suffix when in vertical mode
    out_dir = args.out
    if args.vertical and out_dir == DEFAULT_OUT_DIR:
        out_dir = DEFAULT_OUT_DIR.rstrip("/") + "_vertical"
    os.makedirs(out_dir, exist_ok=True)

    server_dir = SERVER_DIR_V if args.vertical else SERVER_DIR_H
    service    = "musique_vertical" if args.vertical else "musique"
    mode_label = "VERTICAL 1080×1920" if args.vertical else "LANDSCAPE 1920×1080"

    sources = []
    subdirs = sorted([d for d in os.listdir(args.base) if os.path.isdir(os.path.join(args.base, d))])
    search_dirs = [os.path.join(args.base, d) for d in subdirs] if subdirs else [args.base]
    for sd in search_dirs:
        sources += sorted(glob.glob(os.path.join(sd, "**", "*.MP4"), recursive=True))
        sources += sorted(glob.glob(os.path.join(sd, "**", "*.mp4"), recursive=True))
    sources = [s for s in sources if not s.upper().endswith(".LRF")]
    sources = sorted(set(sources))

    prefix_label = f"[prefix={args.prefix}] " if args.prefix else ""
    print(f"[{mode_label}] Found {len(sources)} source files → ~{len(sources)*args.clips} clips  {prefix_label}")
    print(f"Output: {out_dir}")
    if args.no_push:
        print("  --no-push: will NOT rsync or restart service\n")
    else:
        print()

    all_clips = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        futs = {
            ex.submit(process, src, i, out_dir, args.prefix,
                      args.clips, args.min, args.max, args.vertical): src
            for i, src in enumerate(sources)
        }
        for fut in as_completed(futs):
            all_clips.extend(fut.result())

    print(f"\n{len(all_clips)} clips encoded.")

    if args.no_push:
        print(f"Skipping push (--no-push). Clips are in: {out_dir}")
        print("To push manually: rsync -av --exclude '*.wip.mp4' " +
              f"{out_dir}/ {SERVER}:{server_dir}/")
        return

    print("Rsyncing to server...")
    subprocess.run([
        "rsync", "-av", "--progress",
        "--exclude", "*.wip.mp4",
        out_dir + "/",
        f"{SERVER}:{server_dir}/"
    ], check=True)

    print(f"\nRestarting {service} service...")
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", SERVER,
                    f"systemctl restart {service}"], check=True)
    print("Done! Stream updated.")


if __name__ == "__main__":
    main()
