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
#   3. Zero-gap reshuffle: while playlist A is streaming, playlist B is
#      pre-built in a background job. When A finishes, B swaps in instantly.
#      Only on stream drops (non-zero exit) does it reconnect without reshuffling.
#
#   4. ensure_broadcast.py is called before each connect to auto-recreate
#      the YouTube broadcast if YouTube ended it (needs Python + Google API).
#
# WHAT DIDN'T WORK (for reference):
#   - Streaming directly from Z: -- network file open latency causes gaps
#   - outpoint in concat list -- leaves encoder in dirty state at boundaries
#   - -c:v copy without setpts -- non-monotonic DTS from source clips
#   - RTMP on port 1935 -- ISP throttling caused WSAECONNABORTED (-10053)
#   - Rebuilding playlist on every reconnect -- causes 2.5 min gap every 12 min
# ============================================================

param(
    [string]$SourceDir   = "Z:\gab-ae-hot",
    [string]$MusicFile   = "C:\gab-ae\music\background.mp3",
    [string]$StateFile   = "C:\gab-ae\broadcast_state.json",
    [string]$TmpDir      = "C:\gab-ae\stream_tmp",
    [string]$ConcatFile  = "C:\gab-ae\stream_list.txt",
    # Sessions mode: point at a pre-encoded session folder (Z:\gab-ae-sessions\<name>).
    # Skips all pre-encoding -- files are already 4K H.264, streamed with -c:v copy directly.
    [string]$SessionsDir = ""
)

# --- Config ---
$FFmpeg       = "C:\ffmpeg\bin\ffmpeg.exe"
$FFprobe      = "C:\ffmpeg\bin\ffprobe.exe"
$Python       = (Get-Command python -ErrorAction SilentlyContinue)?.Source ?? "python"
$LogFile      = "C:\gab-ae\stream.log"
$MinSizeMB    = 5        # skip files smaller than this (test clips, thumbnails)
$ClipDuration = 15       # seconds per clip
$ClipsPerList = 300      # clips per playlist -- random sample from full hot\ pool
$RestartDelay = 10       # seconds to wait before reconnecting after a drop

# Derived paths for the background (ping-pong) pre-build
$TmpDirNext   = $TmpDir + "_next"
$ConcatNext   = $ConcatFile -replace '\.txt$', '_next.txt'

# --- Logging ---
function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# --- Preflight ---
if (-not (Test-Path $FFmpeg))    { Log "ERROR: ffmpeg not found at $FFmpeg"; exit 1 }
if (-not (Test-Path $MusicFile)) { Log "ERROR: Music not found at $MusicFile"; exit 1 }
if (-not (Test-Path $StateFile)) { Log "ERROR: broadcast_state.json not found at $StateFile"; exit 1 }
if ($SessionsDir) {
    if (-not (Test-Path $SessionsDir)) { Log "ERROR: SessionsDir not found: $SessionsDir"; exit 1 }
    Log "Sessions mode: reading pre-encoded files from $SessionsDir"
} else {
    if (-not (Test-Path $SourceDir)) { Log "ERROR: Source dir not found: $SourceDir"; exit 1 }
}

# --- Sessions mode: build concat list directly from pre-encoded files ---
function Build-Sessions-Playlist {
    $files = Get-ChildItem $SessionsDir -Filter "*.mp4" | Sort-Object Name
    if ($files.Count -eq 0) { Log "ERROR: No .mp4 files in $SessionsDir"; exit 1 }
    $lines = $files | ForEach-Object { "file '$($_.FullName.Replace('\','/'))'" }
    [System.IO.File]::WriteAllLines($ConcatFile, $lines, [System.Text.UTF8Encoding]::new($false))
    Log "Sessions playlist: $($files.Count) pre-encoded files -> $ConcatFile"
}

# --- Get stream key: call ensure_broadcast.py (recreates broadcast if ended) ---
function Get-StreamKey {
    $key = & $Python "C:\gab-ae\ensure_broadcast.py" --state-file $StateFile 2>$null
    if (-not $key) {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        $key   = $state.stream_key
    }
    if (-not $key) { Log "ERROR: could not get stream key"; exit 1 }
    return $key.Trim()
}

# --- Build playlist synchronously into a given TmpDir/ConcatFile ---
function Build-Playlist-To {
    param([string]$TargetTmpDir, [string]$TargetConcatFile)

    Log "Scanning $SourceDir for clips -> $TargetTmpDir"
    $candidates = Get-ChildItem $SourceDir -Filter "*.mp4" |
        Where-Object { $_.Length -gt ($MinSizeMB * 1MB) } |
        Sort-Object { Get-Random } |
        Select-Object -First $ClipsPerList

    if ($candidates.Count -eq 0) { Log "ERROR: No clips found in $SourceDir"; exit 1 }

    if (Test-Path $TargetTmpDir) { Remove-Item "$TargetTmpDir\*.mp4" -Force -ErrorAction SilentlyContinue }
    else { New-Item -ItemType Directory -Path $TargetTmpDir | Out-Null }

    $lines = [System.Collections.Generic.List[string]]::new()
    $built = 0; $skipped = 0; $i = 0
    foreach ($f in $candidates) {
        $dur = & $FFprobe -v error -show_entries format=duration `
            -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null
        if (-not ($dur -match '^\d') -or [double]$dur -lt 3) {
            Log "SKIP (bad): $($f.Name)"; $skipped++; continue
        }
        $out = "$TargetTmpDir\clip_$($i.ToString('000')).mp4"
        & $FFmpeg -y -i $f.FullName -t $ClipDuration `
            -vf "setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
            -c:v h264_nvenc -preset p1 -rc cbr -b:v 4500k -maxrate 5000k -bufsize 9000k `
            -bf 0 -g 30 -keyint_min 30 -sc_threshold 0 `
            -video_track_timescale 90000 `
            -an -avoid_negative_ts make_zero $out 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) {
            $lines.Add("file '$($out.Replace('\','/'))'")
            $built++
        } else {
            Remove-Item $out -ErrorAction SilentlyContinue
        }
        $i++
    }

    if ($built -eq 0) { Log "ERROR: No clips pre-cut successfully"; exit 1 }
    [System.IO.File]::WriteAllLines($TargetConcatFile, $lines, [System.Text.UTF8Encoding]::new($false))
    Log "$built clips pre-cut to ${ClipDuration}s ($skipped skipped) -> $TargetTmpDir"
}

# --- Start background pre-build job (runs in parallel while streaming) ---
function Start-BackgroundBuild {
    param([string]$TargetTmpDir, [string]$TargetConcatFile)

    $job = Start-Job -ScriptBlock {
        param($ffmpeg, $ffprobe, $srcDir, $tmpDir, $concatFile, $minSizeMB, $clipDur, $clipsPerList)

        $candidates = Get-ChildItem $srcDir -Filter "*.mp4" |
            Where-Object { $_.Length -gt ($minSizeMB * 1MB) } |
            Sort-Object { Get-Random } |
            Select-Object -First $clipsPerList

        if (Test-Path $tmpDir) { Remove-Item "$tmpDir\*.mp4" -Force -ErrorAction SilentlyContinue }
        else { New-Item -ItemType Directory -Path $tmpDir | Out-Null }

        $lines = [System.Collections.Generic.List[string]]::new()
        $built = 0; $i = 0
        foreach ($f in $candidates) {
            $dur = & $ffprobe -v error -show_entries format=duration `
                -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null
            if (-not ($dur -match '^\d') -or [double]$dur -lt 3) { $i++; continue }
            $out = "$tmpDir\clip_$($i.ToString('000')).mp4"
            & $ffmpeg -y -i $f.FullName -t $clipDur `
                -vf "setpts=PTS-STARTPTS,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
                -c:v h264_nvenc -preset p1 -rc cbr -b:v 4500k -maxrate 5000k -bufsize 9000k `
                -bf 0 -g 30 -keyint_min 30 -sc_threshold 0 `
                -video_track_timescale 90000 `
                -an -avoid_negative_ts make_zero $out 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path $out)) {
                $lines.Add("file '$($out.Replace('\','/'))'")
                $built++
            } else {
                Remove-Item $out -ErrorAction SilentlyContinue
            }
            $i++
        }
        [System.IO.File]::WriteAllLines($concatFile, $lines, [System.Text.UTF8Encoding]::new($false))
        Write-Output $built
    } -ArgumentList $FFmpeg, $FFprobe, $SourceDir, $TargetTmpDir, $TargetConcatFile, $MinSizeMB, $ClipDuration, $ClipsPerList

    return $job
}

# --- Swap pre-built next playlist into current slot ---
# Moves clips from TmpDirNext -> TmpDir, rewrites ConcatFile with corrected paths.
function Swap-Playlist {
    param($job)

    # Wait up to 5 min if somehow still building
    if ($job.State -ne 'Completed') {
        Log "Waiting for background pre-build..."
        Wait-Job $job -Timeout 300 | Out-Null
    }

    $built = Receive-Job $job 2>$null
    Remove-Job $job

    if (-not (Test-Path $ConcatNext) -or $built -lt 1) {
        Log "WARNING: pre-build failed or empty -- doing sync build"
        Build-Playlist-To $TmpDir $ConcatFile
        return
    }

    # Move clips across (TmpDir is safe to clear -- ffmpeg just finished with it)
    Remove-Item "$TmpDir\*.mp4" -Force -ErrorAction SilentlyContinue
    Get-ChildItem $TmpDirNext -Filter "*.mp4" | ForEach-Object {
        Move-Item $_.FullName "$TmpDir\$($_.Name)" -Force
    }

    # Rewrite concat file with corrected paths (TmpDirNext -> TmpDir)
    # Use WriteAllLines (no BOM) -- Set-Content -Encoding UTF8 in PS 5.1 adds a BOM
    # that breaks ffmpeg's concat demuxer parser.
    $nextSlash    = $TmpDirNext.Replace('\', '/')
    $currentSlash = $TmpDir.Replace('\', '/')
    $fixedLines   = (Get-Content $ConcatNext) -replace [regex]::Escape($nextSlash), $currentSlash
    [System.IO.File]::WriteAllLines($ConcatFile, $fixedLines, [System.Text.UTF8Encoding]::new($false))

    Log "Swapped pre-built playlist ($built clips) -- zero gap"
}

# ============================================================
# Main
# ============================================================
Log "Toujours en Route -- La vie de tous les jours et musique ambiante -- starting"

if ($SessionsDir) {
    # ── Sessions mode: pre-encoded files on NAS, no local pre-encoding ──────────
    Build-Sessions-Playlist

    while ($true) {
        $StreamKey  = Get-StreamKey
        $YoutubeUrl = "rtmps://a.rtmps.youtube.com/live2/$StreamKey"
        Log "Going live (sessions) -> $StreamKey (RTMPS)"

        $startedAt = Get-Date
        & $FFmpeg `
            -loglevel warning `
            -re `
            -f concat -safe 0 -stream_loop -1 `
            -i $ConcatFile `
            -stream_loop -1 -i $MusicFile `
            -map "0:v:0" `
            -map "1:a:0" `
            -c:v copy `
            -c:a aac -b:a 192k -ar 44100 `
            -f flv `
            $YoutubeUrl 2>> "C:\gab-ae\ffmpeg.log"

        $code   = $LASTEXITCODE
        $ranFor = (Get-Date) - $startedAt
        if ($ranFor.TotalSeconds -lt 10) {
            Log "Fast exit ($([int]$ranFor.TotalSeconds)s, code $code) -- rebuilding playlist and reconnecting"
            Build-Sessions-Playlist
        } else {
            Log "Stream dropped (exit $code) -- reconnecting in $RestartDelay s"
            Start-Sleep -Seconds $RestartDelay
        }
    }
}

# ── Clip mode (default): random clips from hot\, pre-encoded locally ─────────

# First playlist: sync build
Build-Playlist-To $TmpDir $ConcatFile

# Immediately kick off background pre-build for next cycle
$nextJob = Start-BackgroundBuild $TmpDirNext $ConcatNext
Log "Background pre-build started for next playlist"

# --- Stream loop (runs forever) ---
while ($true) {
    $StreamKey  = Get-StreamKey
    $YoutubeUrl = "rtmps://a.rtmps.youtube.com/live2/$StreamKey"
    Log "Going live -> $StreamKey (RTMPS)"

    $startedAt = Get-Date
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

    $code     = $LASTEXITCODE
    $ranFor   = (Get-Date) - $startedAt
    $fastExit = $ranFor.TotalSeconds -lt 10

    if ($fastExit) {
        # Exited in under 10s -- broken concat file or bad state. Force a clean rebuild.
        Log "Fast exit ($([int]$ranFor.TotalSeconds)s, code $code) -- forcing sync rebuild"
        Remove-Job $nextJob -Force -ErrorAction SilentlyContinue
        Build-Playlist-To $TmpDir $ConcatFile
        $nextJob = Start-BackgroundBuild $TmpDirNext $ConcatNext
        Log "Background pre-build started for next playlist"
    } elseif ($code -eq 0) {
        Log "Playlist finished -- swapping to pre-built"
        Swap-Playlist $nextJob
        $nextJob = Start-BackgroundBuild $TmpDirNext $ConcatNext
        Log "Background pre-build started for next playlist"
    } else {
        Log "Stream dropped (exit $code) -- reconnecting in $RestartDelay s"
        Start-Sleep -Seconds $RestartDelay
        # Don't reshuffle on drops -- reconnect with same playlist immediately
    }
}
