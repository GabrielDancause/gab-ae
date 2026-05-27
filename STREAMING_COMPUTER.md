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

### Option B — Full session (4K, no re-encoding)
Streams a pre-encoded session directly at 4K with -c:v copy. Session must be pre-encoded
by the encoding computer first (run preencode_sessions.ps1 there).
```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json -SessionsDir "Z:\gab-ae-sessions\2026-05-22 - Charlevoix"'
```

## What to expect
- Option A: build takes ~90 seconds, then it goes live automatically
- Option B: goes live immediately (no pre-encoding on this computer)
- Stream 2 broadcast: https://www.youtube.com/watch?v=UymSi9F5p8Y
- Clips come from Z:\gab-ae-hot\ (Option A) or Z:\gab-ae-sessions\ (Option B)
- Logs: C:\gab-ae\stream.log and C:\gab-ae\ffmpeg.log
