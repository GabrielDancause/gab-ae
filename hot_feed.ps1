# hot_feed.ps1 -- keeps C:\gab-ae\hot\ topped up with streaming-ready clips
# Run via Task Scheduler every 60 minutes.
#
# How it works:
#   - hot_queue.txt holds all source clips in shuffled order (built once, rebuilt when empty)
#   - Each run: encode the next $AddPerRun clips from the queue into hot\
#   - If hot\ exceeds $TargetClips, delete the oldest ones
#   - When queue is exhausted (~80 days), reshuffle and start over

param(
    [string]$SourceDir   = "Z:\01- Media files",
    [string]$HotDir      = "Z:\gab-ae-hot",
    [string]$QueueFile   = "C:\gab-ae\hot_queue.txt",
    [string]$MusicFile   = "C:\gab-ae\music\background.mp3",
    [int]$TargetClips    = 1000,  # keep this many clips ready in hot\
    [int]$AddPerRun      = 10     # encode this many new clips per run
)

$FFmpeg  = "C:\ffmpeg\bin\ffmpeg.exe"
$LogFile = "C:\gab-ae\hot_feed.log"

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

New-Item -ItemType Directory -Path $HotDir -Force | Out-Null

# --- Build or rebuild the queue ---
function Build-Queue {
    Log "Building shuffle queue from $SourceDir..."
    $files = Get-ChildItem $SourceDir -Recurse |
        Where-Object { $_.Extension -ieq '.MP4' -and $_.Length -gt (5 * 1MB) } |
        Sort-Object { Get-Random }
    if ($files.Count -eq 0) { Log "ERROR: no source clips found"; exit 1 }
    [System.IO.File]::WriteAllLines($QueueFile, ($files | ForEach-Object { $_.FullName }), [System.Text.UTF8Encoding]::new($false))
    Log "Queue built: $($files.Count) clips (~$([math]::Round($files.Count * 17.6 / 60 / 24, 0)) days of footage)"
}

if (-not (Test-Path $QueueFile) -or (Get-Content $QueueFile -TotalCount 1) -eq $null) {
    Build-Queue
}

# --- Trim hot folder if over target ---
$hotClips = Get-ChildItem $HotDir -Filter "*.mp4" -ErrorAction SilentlyContinue | Sort-Object CreationTime
if ($hotClips.Count -gt $TargetClips) {
    $trim = $hotClips.Count - $TargetClips
    $hotClips | Select-Object -First $trim | ForEach-Object {
        Remove-Item $_.FullName -Force
        Log "Retired: $($_.Name)"
    }
}

# --- Encode next clips from queue ---
$queue    = [System.Collections.Generic.List[string]](Get-Content $QueueFile)
$hotNames = (Get-ChildItem $HotDir -Filter "*.mp4" -ErrorAction SilentlyContinue).Name
$added    = 0
$skip     = 0

while ($added -lt $AddPerRun -and $queue.Count -gt 0) {
    $src = $queue[0]
    $queue.RemoveAt(0)

    if (-not (Test-Path $src)) { $skip++; continue }

    # Safe output filename: use parent folder date + original name
    $folder  = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($src))
    $stem    = [System.IO.Path]::GetFileNameWithoutExtension($src)
    $outName = ($folder + "_" + $stem) -replace '[^\w\-]', '_'
    $outName = $outName.Substring(0, [Math]::Min($outName.Length, 80)) + ".mp4"
    $outPath = Join-Path $HotDir $outName

    if ($hotNames -contains $outName -or (Test-Path $outPath)) {
        Log "Skip (exists): $outName"
        continue
    }

    Log "Encoding [$($added+1)/$AddPerRun]: $([System.IO.Path]::GetFileName($src))"

    & $FFmpeg -y `
        -hwaccel cuda `
        -i $src `
        -i $MusicFile `
        -map "0:v:0" `
        -map "1:a:0" `
        -shortest `
        -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
        -c:v h264_nvenc `
        -preset p4 `
        -rc cbr `
        -b:v 9000k `
        -maxrate 9000k `
        -bufsize 18000k `
        -g 60 `
        -keyint_min 60 `
        -sc_threshold 0 `
        -c:a aac `
        -b:a 192k `
        -ar 44100 `
        -movflags +faststart `
        $outPath 2>$null

    if ($LASTEXITCODE -eq 0) {
        $mb = [math]::Round((Get-Item $outPath).Length / 1MB, 0)
        Log "Ready: $outName ($mb MB)"
        $added++
    } else {
        Log "FAILED (exit $LASTEXITCODE): $([System.IO.Path]::GetFileName($src)) -- skipping"
        Remove-Item $outPath -ErrorAction SilentlyContinue
    }
}

# --- Save remaining queue (clips we haven't encoded yet) ---
if ($queue.Count -gt 0) {
    [System.IO.File]::WriteAllLines($QueueFile, $queue, [System.Text.UTF8Encoding]::new($false))
} else {
    Log "Queue exhausted after ~80 days -- reshuffling for next cycle"
    Build-Queue
}

$finalCount = (Get-ChildItem $HotDir -Filter "*.mp4" -ErrorAction SilentlyContinue).Count
$remaining  = (Get-Content $QueueFile | Measure-Object -Line).Lines
Log "Done. Hot: $finalCount clips | Queue: $remaining remaining | Skipped: $skip bad files"
