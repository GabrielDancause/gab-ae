# Status — LIVE and stable
Last updated: 2026-05-26 ~15:40

---

## Stream
- **Status:** LIVE
- **Broadcast:** https://www.youtube.com/watch?v=K5FBpML9AO0
- **Stream key:** `jce2-7rps-xxuq-zre2-2xd9` (in broadcast_state.json)
- **Protocol:** RTMPS port 443 (bypasses ISP RTMP throttling on 1935)
- **Source:** C:\gab-ae\hot\ — 104 local clips pre-encoded from Z: footage
- **Format:** 15s clips, shuffled random, 1080p h264 4500k CBR, ambient music layered
- **Pre-cut pipeline:** Each playlist build re-encodes 48 clips to 15s with clean timestamps
  - setpts=PTS-STARTPTS (reset to 0), -bf 0 (no B-frames), -video_track_timescale 90000
  - Stored in C:\gab-ae\stream_tmp\ (working copies, safe to delete/rebuild)
  - Takes ~2.5 min to build, then streams with -c:v copy (no GPU load during stream)
- **Bad files (skipped automatically):**
  - 100MEDIA_DJI_0140.mp4 — moov atom not found (corrupt encode)
  - Only_Videos_DJI_0621.mp4 — moov atom not found (corrupt encode)
- **Check live:** `netstat -n | findstr :443` look for 142.250.x.x ESTABLISHED
- **If not live:** `Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1'`

## Hot Folder
- **Status:** 104 clips in C:\gab-ae\hot\ (DO NOT DELETE — originals safe on Z:)
- **Cron:** Task Scheduler "GabHotFeed" runs every hour, adds 4 clips from Z:
- **Z: originals:** Never touched — hot_feed only reads Z:, writes new encodes to hot\
- **Hot\ management:** Capped at 100 clips, oldest hot\ copies rotated out (not Z: originals)

## Daily Uploads
- **Task Scheduler:** GabDailyUpload runs at 10 AM daily
- **Tracking:** C:\gab-ae\uploaded.txt
- **Videos live:**
  - https://youtu.be/qVgBp2FHt98 -- Boracay, Philippines | Ambient
  - https://youtu.be/tJHLiEoMCIA -- Charlevoix, Quebec | Ambient (4K)

## Compilation Video (INCOMPLETE -- needs re-stitch)
- **Segments:** 60 x 1-min segments in C:\gab-ae\comp_tmp\
- **Fix:**
  ```
  C:\ffmpeg\bin\ffmpeg.exe -y -f concat -safe 0 -i C:\gab-ae\comp_tmp\concat.txt -stream_loop -1 -i C:\gab-ae\music\background.mp3 -map 0:v:0 -map 1:a:0 -t 3600 -c:v copy -c:a aac -b:a 320k -ar 44100 -movflags +faststart C:\gab-ae\output\compilation_60min.mp4
  ```

## Key files
```
C:\gab-ae\
  stream_to_youtube.ps1   -- main stream script
  broadcast_state.json    -- current broadcast ID + stream key
  ensure_broadcast.py     -- auto-recreates YouTube broadcast if ended
  hot_feed.ps1            -- hourly cron, feeds hot folder from Z:
  daily_upload.ps1        -- 10 AM daily uploads
  music\background.mp3    -- 3h47m ambient music loop
  hot\                    -- 104 pre-encoded clips (source for stream)
  stream_tmp\             -- 48 pre-cut 15s clips (rebuilt each playlist cycle)
  output\                 -- encoded clips for upload
```
