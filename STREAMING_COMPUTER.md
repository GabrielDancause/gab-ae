# Streaming Computer Setup

Read this file and follow the steps in order.

## Step 1 — Map Z: to the NAS
Make sure Z: is mapped to the NAS before anything else.

## Step 2 — Clone the repo
```powershell
git clone https://github.com/GabrielDancause/gab-ae.git C:\gab-ae
```

## Step 3 — Run setup (as Administrator)
```powershell
C:\gab-ae\setup.ps1
```
This installs ffmpeg, Python, all dependencies, and copies secrets + music from the NAS automatically.

## Step 4 — Start the stream

### Option A — Random clips (default)
Picks random 15s clips from Z:\gab-ae-hot\ (filled by the encoding computer).
```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json'
```

### Option B — Full session, 4K, no re-encoding (READY NOW)
Streams the pre-encoded Charlevoix 2026-05-22 session at 4K with -c:v copy.
No build step — goes live in seconds.

Before starting, verify the session is fully encoded on the encoding computer:
- Z:\gab-ae-sessions\2026-05-22 - Charlevoix\ should have 29 clip_*.mp4 files
- playlist.txt must exist and not be empty (0 bytes = encoding still in progress)

```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json -SessionsDir "Z:\gab-ae-sessions\2026-05-22 - Charlevoix"'
```

To stream a different session later, replace the -SessionsDir path with any folder under Z:\gab-ae-sessions\.

## What to expect
- Option A: build takes ~90 seconds, then it goes live automatically
- Option B: goes live in seconds, streams the full session on loop with ambient music
- Stream 2 broadcast: https://www.youtube.com/watch?v=UymSi9F5p8Y
- Quality: 4K 60fps H.264 at 20 Mbps — YouTube will show 2160p60 in the quality selector
- Logs: C:\gab-ae\stream.log and C:\gab-ae\ffmpeg.log
