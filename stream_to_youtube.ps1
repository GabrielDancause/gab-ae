# ============================================================
# stream_to_youtube.ps1  --  Toujours en Route, 24/7 live stream
# La vie de tous les jours et musique ambiante
#
# STATUS: LIVE as of 2026-05-26
# Broadcast: https://www.youtube.com/watch?v=K5FBpML9AO0
#
# HOW IT WORKS:
#   1. Build-Playlist: picks 50 smallest clips from hot\, validates each
#      with ffprobe (skips corrupt files), then re-encodes each to exactly
#      $ClipDuration seconds into stream_tmp\ with clean timestamps:
#        - setpts=PTS-STARTPTS  -> every clip starts at PTS=0
#        - -bf 0                -> no B-frames, so DTS always equals PTS
#        - -video_track_timescale 90000  -> consistent timebase across all clips
#      This pre-cut step is the key to stable transitions. Without it,
#      the concat demuxer sees non-monotonic DTS at clip boundaries and
#      YouTube drops the stream every ~60-90 seconds.
#
#   2. Stream loop: reads pre-cut clips via concat demuxer (-c:v copy, no
#      re-encoding), layers ambient music on top, pushes via RTMPS port 443.
#      Using RTMPS (not RTMP) bypasses ISP throttling on port 1935.
#
#   3. ensure_broadcast.py is called before each connect to auto-recreate
#      the YouTube broadcast if YouTube ended it (needs Python + Google API).
#
# WHAT DIDN'T WORK (for reference):
#   - Streaming directly from Z: -- network file open latency causes gaps
#   - outpoint in concat list -- leaves encoder in dirty state at boundaries
#   - -c:v copy without setpts -- non-monotonic DTS from source clips
#   - RTMP on port 1935 -- ISP throttling caused WSAECONNABORTED (-10053)
# ============================================================

param(
    [string]$SourceDir = "C:\gab-ae\hot",
    [string]$MusicFile = "C:\gab-ae\music\background.mp3"
)

# --- Config ---
$FFmpeg       = "C:\ffmpeg\bin\ffmpeg.exe"
$FFprobe      = "C:\ffmpeg\bin\ffprobe.exe"
$Python       = "C:\Users\gabri\AppData\Local\Programs\Python\Python312\python.exe"
$StateFile    = "C:\gab-ae\broadcast_state.json"
$ConcatFile   = "C:\gab-ae\stream_list.txt"
$TmpDir       = "C:\gab-ae\stream_tmp"
$LogFile      = "C:\gab-ae\stream.log"
$MinSizeMB    = 5        # skip files smaller than this (test clips, thumbnails)
$ClipDuration = 15       # seconds per clip
$ClipsPerList = 50       # clips per playlist before reshuffling (~25 min)
$RestartDelay = 10       # seconds to wait before reconnecting after a drop

# --- Logging ---
function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# --- Preflight ---
if (-not (Test-Path $FFmpeg))    { Log "ERROR: ffmpeg not found at $FFmpeg"; exit 1 }
if (-not (Test-Path $MusicFile)) { Log "ERROR: Music not found at $MusicFile"; exit 1 }
if (-not (Test-Path $SourceDir)) { Log "ERROR: Source dir not found: $SourceDir"; exit 1 }
if (-not (Test-Path $StateFile)) { Log "ERROR: broadcast_state.json not found at $StateFile"; exit 1 }

# --- Get stream key: call ensure_broadcast.py (recreates broadcast if ended) ---
function Get-StreamKey {
    $key = & $Python "C:\gab-ae\ensure_broadcast.py" 2>$null
    if (-not $key) {
        # Fallback: read directly from state file
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        $key   = $state.stream_key
    }
    if (-not $key) { Log "ERROR: could not get stream key"; exit 1 }
    return $key.Trim()
}

# --- Build playlist: pre-cut each clip to exactly $ClipDuration seconds ---
# Pre-cutting creates clean standalone files with proper timestamps.
# No outpoint in the concat list = no encoder gaps at transitions.
function Build-Playlist {
    Log "Scanning $SourceDir for clips..."
    $candidates = Get-ChildItem $SourceDir -Filter "*.mp4" |
        Where-Object { $_.Length -gt ($MinSizeMB * 1MB) } |
        Sort-Object Length |
        Select-Object -First $ClipsPerList |
        Sort-Object { Get-Random }

    if ($candidates.Count -eq 0) { Log "ERROR: No clips found in $SourceDir"; exit 1 }

    # Wipe and recreate tmp dir (these are working copies, not originals)
    if (Test-Path $TmpDir) { Remove-Item "$TmpDir\*.mp4" -Force -ErrorAction SilentlyContinue }
    else { New-Item -ItemType Directory -Path $TmpDir | Out-Null }

    $lines = [System.Collections.Generic.List[string]]::new()
    $built = 0; $skipped = 0; $i = 0
    foreach ($f in $candidates) {
        $dur = & $FFprobe -v error -show_entries format=duration `
            -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null
        if (-not ($dur -match '^\d') -or [double]$dur -lt 3) {
            Log "SKIP (bad): $($f.Name)"; $skipped++; continue
        }
        $out = "$TmpDir\clip_$($i.ToString('000')).mp4"
        & $FFmpeg -y -i $f.FullName -t $ClipDuration `
            -vf "setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
            -c:v h264_nvenc -preset p1 -rc cbr -b:v 4500k -maxrate 5000k -bufsize 9000k `
            -bf 0 -g 30 -keyint_min 30 -sc_threshold 0 `
            -video_track_timescale 90000 `
            -an -avoid_negative_ts make_zero $out 2>$null
        if (Test-Path $out) {
            $lines.Add("file '$($out.Replace('\','/'))'")
            $built++
        }
        $i++
    }

    if ($built -eq 0) { Log "ERROR: No clips pre-cut successfully"; exit 1 }
    [System.IO.File]::WriteAllLines($ConcatFile, $lines, [System.Text.UTF8Encoding]::new($false))
    Log "$built clips pre-cut to ${ClipDuration}s ($skipped skipped) -- clean transitions"
}

Log "Toujours en Route -- La vie de tous les jours et musique ambiante -- starting"
Build-Playlist

# --- Stream loop (runs forever, restarts on any failure) ---
while ($true) {
    $StreamKey  = Get-StreamKey
    $YoutubeUrl = "rtmps://a.rtmps.youtube.com/live2/$StreamKey"
    Log "Going live -> $StreamKey (RTMPS)"

    & $FFmpeg `
        -loglevel warning `
        -re `
        -f concat -safe 0 `
        -i $ConcatFile `
        -stream_loop -1 -i $MusicFile `
        -map "0:v:0" `
        -map "1:a:0" `
        -c:v copy `
        -c:a aac -b:a 192k -ar 44100 `
        -f flv `
        $YoutubeUrl 2>> "C:\gab-ae\ffmpeg.log"

    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Log "Playlist finished -- reshuffling"
    } else {
        Log "Stream dropped (exit $code) -- reconnecting in $RestartDelay s"
        Start-Sleep -Seconds $RestartDelay
    }
    Build-Playlist
}
