import subprocess
import sys
from pathlib import Path

STREAM_KEY = "qmp5-ue0m-38gp-cc2y-7kjs"
YOUTUBE_URL = f"rtmp://a.rtmp.youtube.com/live2/{STREAM_KEY}"
FFMPEG = r"C:\ffmpeg\bin\ffmpeg.exe"

# K: action cam — sort by embedded clip number (_0001_, _0002_, ...)
k_files = sorted(
    Path("K:/DCIM/DJI_001").glob("*.MP4"),
    key=lambda p: int(p.stem.split("_")[2])
)

# L: Mavic 2 — sort by filename (DJI_0183, DJI_0193, ...)
l_files = sorted(Path("L:/DCIM/100MEDIA").glob("*.MP4"))

all_files = list(k_files) + list(l_files)

if not all_files:
    print("No files found. Check that K: and L: are mounted.")
    sys.exit(1)

# Write FFmpeg concat list
concat_path = Path("C:/gab-ae/stream_list.txt")
with open(concat_path, "w", encoding="utf-8") as f:
    for fp in all_files:
        f.write(f"file '{fp.as_posix()}'\n")

print(f"Queued {len(all_files)} files ({len(k_files)} action cam + {len(l_files)} Mavic 2):")
for i, fp in enumerate(all_files, 1):
    source = "K" if i <= len(k_files) else "L"
    print(f"  [{source}] {i:2d}. {fp.name}")

print(f"\nStreaming to YouTube...")

cmd = [
    FFMPEG,
    "-re",                      # real-time playback rate
    "-f", "concat",
    "-safe", "0",
    "-i", str(concat_path),
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-b:v", "8000k",
    "-maxrate", "10000k",
    "-bufsize", "20000k",
    "-pix_fmt", "yuv420p",
    "-g", "60",                 # keyframe every 2s at 30fps
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "44100",
    "-f", "flv",
    YOUTUBE_URL,
]

subprocess.run(cmd, check=True)
