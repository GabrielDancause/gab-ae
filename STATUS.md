# Status — LIVE and stable
Last updated: 2026-05-26 ~16:20

---

## Stream 1 — Toujours en Route
- **Status:** LIVE
- **Broadcast:** https://www.youtube.com/watch?v=K5FBpML9AO0
- **Stream key:** `jce2-7rps-xxuq-zre2-2xd9` (in broadcast_state.json)
- **Protocol:** RTMPS port 443 (bypasses ISP RTMP throttling on 1935)
- **Source:** C:\gab-ae\hot\ — 104 local clips pre-encoded from Z: footage
- **Format:** 15s clips, shuffled random, 1080p h264 4500k CBR, ambient music layered
- **Pre-cut pipeline:** Each playlist build re-encodes 48 clips to 15s with clean timestamps
  - setpts=PTS-STARTPTS (reset to 0), -bf 0 (no B-frames), -video_track_timescale 90000
  - Stored in C:\gab-ae\stream_tmp\ (working copies, safe to delete/rebuild)
  - Takes ~50s to build, then streams with -c:v copy (no GPU load during stream)
- **Zero-gap reshuffle:** Next playlist pre-builds in a background job while current streams.
  When playlist finishes (exit 0), swap is instant -- no "No data" gap.
  On network drops (exit non-zero), reconnects immediately with same playlist (no rebuild).
- **Bad files (skipped automatically):**
  - 100MEDIA_DJI_0140.mp4 — moov atom not found (corrupt encode)
  - Only_Videos_DJI_0621.mp4 — moov atom not found (corrupt encode)
- **Check live:** `netstat -n -o | findstr "11236"` (or current ffmpeg PID)
- **If not live:** `Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1'`

## Stream 2 — Gab's Adventures -- Vues du monde (other computer)
- **Broadcast created:** https://www.youtube.com/watch?v=UymSi9F5p8Y
- **Stream key:** `5ke5-0aq8-d58k-7t2j-7ahk` (in broadcast_state2.json)
- **Note:** Two streams from one machine killed stream 1. Run stream 2 from another machine.
- **Command for other machine:**
  ```
  Start-Process powershell -ArgumentList '-NonInteractive -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json -TmpDir C:\gab-ae\stream_tmp2 -ConcatFile C:\gab-ae\stream_list2.txt'
  ```

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
  stream_to_youtube.ps1   -- main stream script (supports -StateFile/-TmpDir/-ConcatFile params)
  broadcast_state.json    -- stream 1 broadcast ID + stream key
  broadcast_state2.json   -- stream 2 broadcast ID + stream key (other machine)
  ensure_broadcast.py     -- auto-recreates YouTube broadcast if ended (supports --state-file)
  hot_feed.ps1            -- hourly cron, feeds hot folder from Z:
  daily_upload.ps1        -- 10 AM daily uploads
  music\background.mp3    -- 3h47m ambient music loop
  hot\                    -- 104 pre-encoded clips (source for stream)
  stream_tmp\             -- 48 pre-cut 15s clips (current playlist)
  stream_tmp_next\        -- 48 pre-cut 15s clips (pre-building next playlist)
  output\                 -- encoded clips for upload
```
