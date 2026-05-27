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
```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json'
```

## What to expect
- Build takes ~90 seconds, then it goes live automatically
- Stream 2 broadcast: https://www.youtube.com/watch?v=UymSi9F5p8Y
- Clips come from Z:\gab-ae-hot\ (filled by the encoding computer)
- Logs: C:\gab-ae\stream.log and C:\gab-ae\ffmpeg.log
