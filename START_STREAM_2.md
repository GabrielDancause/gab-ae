# Stream 2 — Start Instructions

Read this file and follow the steps in order. Do not ask questions, just execute.

## Step 1 — Map Z: to the NAS
Make sure Z: is mapped to the NAS. If not mapped yet:
```powershell
net use Z: \\YOUR-NAS-IP\share /persistent:yes
```

## Step 2 — Clone the repo
```powershell
git clone https://github.com/GabrielDancause/gab-ae.git C:\gab-ae
```

## Step 3 — Run setup (as Administrator)
```powershell
C:\gab-ae\setup.ps1
```
This installs ffmpeg, Python, all dependencies, and copies secrets + music from the NAS.

## Step 4 — Start the stream
```powershell
Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json -SessionsDir "Z:\gab-ae-sessions\2026-05-22 - Charlevoix"'
```

## What to expect
- Goes live in seconds — no build step, no re-encoding
- Streams the Charlevoix 2026-05-22 session at 4K 60fps with ambient music
- Loops the full session continuously
- Broadcast: https://www.youtube.com/watch?v=UymSi9F5p8Y
- Logs: C:\gab-ae\stream.log and C:\gab-ae\ffmpeg.log

## If something goes wrong
Check the log:
```powershell
Get-Content C:\gab-ae\stream.log -Tail 20
```
