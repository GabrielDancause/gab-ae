#!/usr/bin/env python3
"""
One-time batch transcoder: converts all raw footage to 1080p H.264.
Run once, leave overnight. Streamer reads from /opt/footage_1080p/.
"""

import os
import glob
import subprocess
import json

SRC_DIR  = "/opt/footage"
DST_DIR  = "/opt/footage_1080p"
WIDTH, HEIGHT, FPS = 1920, 1080, 30


def get_info(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path],
            capture_output=True, text=True, timeout=15)
        d = json.loads(r.stdout)
        duration = float(d["format"]["duration"])
        vs = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
        return duration, vs.get("codec_name", "?"), vs.get("width", 0), vs.get("height", 0)
    except Exception:
        return 0, "?", 0, 0


def transcode(src, dst):
    tmp = dst.rsplit(".mp4", 1)[0] + "_wip.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", src,
        "-vf", (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={FPS}"),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-threads", "8",
        "-pix_fmt", "yuv420p",
        "-an",          # strip audio — music added at stream time
        tmp,
    ]
    proc = subprocess.run(cmd, stderr=subprocess.PIPE)
    if proc.returncode == 0:
        os.rename(tmp, dst)
        return True
    else:
        if os.path.exists(tmp):
            os.unlink(tmp)
        print(f"  ERROR: {proc.stderr.decode()[-500:]}")
        return False


def main():
    os.makedirs(DST_DIR, exist_ok=True)
    sources = []
    for pat in ["*.MP4", "*.mp4", "*.MOV", "*.mov"]:
        sources.extend(glob.glob(os.path.join(SRC_DIR, "**", pat), recursive=True))
    sources = sorted(set(sources))

    print(f"Found {len(sources)} source files")
    done = 0
    skipped = 0

    for src in sources:
        rel = os.path.relpath(src, SRC_DIR)
        dst = os.path.join(DST_DIR, rel.replace(os.sep, "_").replace(" ", "_"))
        dst = dst.rsplit(".", 1)[0] + ".mp4"

        if os.path.exists(dst):
            skipped += 1
            continue

        duration, codec, w, h = get_info(src)
        print(f"\n[{done+1}/{len(sources)-skipped}] {os.path.basename(src)}")
        print(f"  {codec} {w}x{h} {duration:.0f}s")

        ok = transcode(src, dst)
        if ok:
            done += 1
            size = os.path.getsize(dst) / 1024**2
            print(f"  -> {os.path.basename(dst)} ({size:.0f} MB)")

    print(f"\nDone. {done} transcoded, {skipped} skipped.")


if __name__ == "__main__":
    main()
