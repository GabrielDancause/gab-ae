# ============================================================
# stream_to_youtube.ps1  --  Toujours en Route, 24/7 live stream
# This is the script we keep improving. All config at the top.
# ============================================================

param(
    [string]$SourceDir = "Z:\01- Media files",
    [string]$MusicFile = "C:\gab-ae\music\background.mp3"
)

# --- Config ---
$StreamKey    = "qmp5-ue0m-38gp-cc2y-7kjs"
$YoutubeUrl   = "rtmp://a.rtmp.youtube.com/live2/$StreamKey"
$FFmpeg       = "C:\ffmpeg\bin\ffmpeg.exe"
$ConcatFile   = "C:\gab-ae\stream_list.txt"
$LogFile      = "C:\gab-ae\stream.log"
$MinSizeMB    = 5        # skip files smaller than this (test clips, thumbnails)
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

# --- Build playlist ---
# MP4 only -- most stable with concat demuxer (avoids AVI/MOV codec mismatches)
# Shuffle every restart for variety
function Build-Playlist {
    Log "Scanning $SourceDir for clips..."
    $files = Get-ChildItem $SourceDir -Recurse |
        Where-Object { $_.Extension -ieq '.MP4' } |
        Where-Object { $_.Length -gt ($MinSizeMB * 1MB) } |
        Sort-Object { Get-Random }

    if ($files.Count -eq 0) { Log "ERROR: No clips found."; exit 1 }

    $lines = $files | ForEach-Object { "file '$($_.FullName.Replace('\','/'))'" }
    [System.IO.File]::WriteAllLines($ConcatFile, $lines, [System.Text.UTF8Encoding]::new($false))
    Log "$($files.Count) clips queued (shuffled)"
}

Log "Toujours en Route -- starting"
Build-Playlist

# --- Stream loop (runs forever, restarts on any failure) ---
while ($true) {
    Log "Going live..."

    & $FFmpeg `
        -loglevel error `
        -re `
        -fflags +genpts+discardcorrupt `
        -err_detect ignore_err `
        -f concat -safe 0 `
        -i $ConcatFile `
        -stream_loop -1 -i $MusicFile `
        -map "0:v:0" `
        -map "1:a:0" `
        -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
        -c:v h264_nvenc `
        -preset p4 `
        -rc cbr `
        -b:v 9000k `
        -maxrate 10000k `
        -bufsize 18000k `
        -g 120 `
        -c:a aac `
        -b:a 192k `
        -ar 44100 `
        -f flv `
        $YoutubeUrl

    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Log "Playlist finished -- reshuffling and restarting"
        Build-Playlist
    } else {
        Log "Stream dropped (exit $code) -- reconnecting in $RestartDelay s"
        Start-Sleep -Seconds $RestartDelay
    }
}
