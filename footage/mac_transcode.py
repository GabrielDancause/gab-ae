#!/usr/bin/env python3
"""
Mac transcoder — uses VideoToolbox hardware HEVC decode.
Converts all footage from obiwan to 1080p H.264, rsyncs to VPS as each file completes.
"""

import os
import glob
import subprocess
import json

SRC_ROOT = "/Volumes/obiwan/2026-06-03 - Multiple exports"
SRC_DIRS = [
    os.path.join(SRC_ROOT, d)
    for d in sorted(os.listdir(SRC_ROOT))
    if os.path.isdir(os.path.join(SRC_ROOT, d))
] if os.path.exists("/Volumes/obiwan") else []
DST_LOCAL = "/tmp/footage_1080p"
VPS = "root@138.201.21.95"
VPS_DIR = "/opt/footage_1080p"
VPS_KEY = "/Users/gab/.ssh/id_ed25519"
WIDTH, HEIGHT, FPS = 1920, 1080, 30


def find_sources():
    files = []
    for d in SRC_DIRS:
        for pat in ["*.MP4", "*.mp4", "*.MOV", "*.mov"]:
            files.extend(glob.glob(os.path.join(d, "**", pat), recursive=True))
    return sorted(set(files))


def dst_name(src):
    # Flatten path to a single filename
    rel = src
    for d in SRC_DIRS:
        if src.startswith(d):
            rel = os.path.relpath(src, os.path.dirname(d))
            break
    name = rel.replace(os.sep, "_").replace(" ", "_")
    return name.rsplit(".", 1)[0] + ".mp4"


def transcode(src, dst):
    tmp = dst.replace(".mp4", "_wip.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "videotoolbox",
        "-i", src,
        "-vf", (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={FPS}"),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-an",
        tmp,
    ]
    print(f"  Encoding...")
    proc = subprocess.run(cmd, stderr=subprocess.PIPE)
    if proc.returncode == 0:
        os.rename(tmp, dst)
        return True
    if os.path.exists(tmp):
        os.unlink(tmp)
    print(f"  ERROR: {proc.stderr.decode()[-300:]}")
    return False


def rsync_to_vps(local_file):
    cmd = [
        "rsync", "-av",
        "-e", f"ssh -i {VPS_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15",
        local_file,
        f"{VPS}:{VPS_DIR}/",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def main():
    os.makedirs(DST_LOCAL, exist_ok=True)
    sources = find_sources()
    print(f"Found {len(sources)} source files\n")

    done = 0
    for src in sources:
        name = dst_name(src)
        dst = os.path.join(DST_LOCAL, name)
        vps_dst = f"{VPS}:{VPS_DIR}/{name}"

        # Check if already on VPS (skip if VPS unreachable)
        try:
            check = subprocess.run(
                ["ssh", "-i", VPS_KEY, "-o", "StrictHostKeyChecking=no",
                 "-o", "ConnectTimeout=10",
                 VPS, f"test -f {VPS_DIR}/{name} && echo yes || echo no"],
                capture_output=True, text=True, timeout=15)
            if check.stdout.strip() == "yes":
                print(f"[SKIP] {name} already on VPS")
                done += 1
                continue
        except subprocess.TimeoutExpired:
            print(f"  VPS unreachable, transcoding locally only")

        # Transcode locally
        dur_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", src],
            capture_output=True, text=True)
        try:
            dur = float(json.loads(dur_result.stdout)["format"]["duration"])
        except Exception:
            dur = 0
        if not os.path.exists(src):
            print(f"  SKIP (file disappeared): {src}")
            continue
        size_gb = os.path.getsize(src) / 1024**3

        print(f"\n[{done+1}/{len(sources)}] {os.path.basename(src)}")
        print(f"  {dur:.0f}s  {size_gb:.1f}GB")

        ok = transcode(src, dst)
        if not ok:
            continue

        out_size = os.path.getsize(dst) / 1024**2
        print(f"  -> {name} ({out_size:.0f} MB)")

        print(f"  Uploading to VPS...")
        if rsync_to_vps(dst):
            print(f"  Uploaded. Removing local copy.")
            os.unlink(dst)
            done += 1
        else:
            print(f"  rsync failed — keeping local copy")

    print(f"\nAll done. {done}/{len(sources)} files on VPS.")


if __name__ == "__main__":
    main()
