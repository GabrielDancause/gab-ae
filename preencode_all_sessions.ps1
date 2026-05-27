# ============================================================
# preencode_all_sessions.ps1 -- encode every session on the NAS
# to Z:\gab-ae-sessions\ for direct -c:v copy streaming.
#
# Runs forever, skipping sessions already encoded (playlist.txt exists
# and is non-empty). Safe to stop and restart at any time.
#
# Usage:
#   .\preencode_all_sessions.ps1
#   .\preencode_all_sessions.ps1 -BitrateK 30000
# ============================================================

param(
    [string]$SourceRoot = "Z:\01- Media files",
    [string]$OutRoot    = "Z:\gab-ae-sessions",
    [int]   $BitrateK   = 20000
)

$FFmpeg  = "C:\ffmpeg\bin\ffmpeg.exe"
$FFprobe = "C:\ffmpeg\bin\ffprobe.exe"

if (-not (Test-Path $FFmpeg))     { Write-Error "ffmpeg not found"; exit 1 }
if (-not (Test-Path $SourceRoot)) { Write-Error "Source root not found: $SourceRoot"; exit 1 }

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path "C:\gab-ae\preencode_sessions.log" -Value $line -Encoding UTF8
}

function Encode-Session {
    param([string]$SessionFolder)

    $SessionName = Split-Path $SessionFolder -Leaf
    $SessionOut  = Join-Path $OutRoot $SessionName
    $Playlist    = Join-Path $SessionOut "playlist.txt"

    # Skip if already fully encoded
    if ((Test-Path $Playlist) -and (Get-Item $Playlist).Length -gt 0) {
        Log "SKIP (done): $SessionName"
        return
    }

    $files = Get-ChildItem $SessionFolder -Recurse -Include "*.mp4","*.MP4","*.mov","*.MOV","*.mts","*.MTS" |
        Where-Object { $_.Length -gt 50MB } |
        Sort-Object FullName

    if ($files.Count -eq 0) {
        Log "SKIP (no video): $SessionName"
        return
    }

    New-Item -ItemType Directory -Path $SessionOut -Force | Out-Null
    Log "Encoding: $SessionName ($($files.Count) files)"

    $lines = [System.Collections.Generic.List[string]]::new()
    $encoded = 0; $failed = 0; $i = 0

    foreach ($f in $files) {
        $out = Join-Path $SessionOut ("clip_{0:000}.mp4" -f $i)

        if (Test-Path $out) {
            $chk = & $FFprobe -v error -show_entries format=duration `
                -of default=noprint_wrappers=1:nokey=1 $out 2>$null
            if ($chk -match '^\d' -and [double]$chk -gt 5) {
                $lines.Add("file '$($out.Replace('\','/'))'")
                $encoded++; $i++; continue
            }
            Remove-Item $out -Force -ErrorAction SilentlyContinue
        }

        $srcCodec = (& $FFprobe -v error -select_streams v:0 `
            -show_entries stream=codec_name `
            -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null) -split "`n" |
            Select-Object -First 1

        $srcW = (& $FFprobe -v error -select_streams v:0 `
            -show_entries stream=width `
            -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null) -split "`n" |
            Select-Object -First 1

        switch ($srcCodec.Trim()) {
            'hevc' { $hwDec = @('-hwaccel','cuda','-hwaccel_output_format','cuda','-c:v','hevc_cuvid') }
            'h264' { $hwDec = @('-hwaccel','cuda','-hwaccel_output_format','cuda','-c:v','h264_cuvid') }
            default { $hwDec = @() }
        }

        if (($srcW -as [int]) -ge 3840) {
            $vf = "scale_cuda=3840:2160:format=yuv420p"
        } else {
            $vf = "scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2,format=yuv420p,setpts=PTS-STARTPTS"
            $hwDec = @()
        }

        $mb = [int]($f.Length / 1MB)
        Log "  [$($i.ToString('000'))] $($f.Name) (${mb} MB, $($srcCodec.Trim()))"

        $ffArgs = $hwDec + @(
            '-y', '-i', $f.FullName,
            '-vf', $vf,
            '-c:v', 'h264_nvenc', '-preset', 'p4', '-rc', 'cbr',
            '-b:v', "${BitrateK}k", '-maxrate', "${BitrateK}k", '-bufsize', "$([int]$BitrateK*2)k",
            '-bf', '0', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
            '-video_track_timescale', '90000',
            '-an', '-avoid_negative_ts', 'make_zero', '-movflags', '+faststart',
            $out
        )

        & $FFmpeg @ffArgs 2>$null

        if ($LASTEXITCODE -eq 0 -and (Test-Path $out) -and (Get-Item $out).Length -gt 0) {
            $lines.Add("file '$($out.Replace('\','/'))'")
            $encoded++
        } else {
            Remove-Item $out -ErrorAction SilentlyContinue
            $failed++
            Log "  FAILED: $($f.Name)"
        }
        $i++
    }

    [System.IO.File]::WriteAllLines($Playlist, $lines, [System.Text.UTF8Encoding]::new($false))
    Log "Done: $SessionName — $encoded encoded, $failed failed"
}

# ── Main loop ──────────────────────────────────────────────────────────────────
Log "preencode_all_sessions starting — source: $SourceRoot"

while ($true) {
    $sessionFolders = Get-ChildItem $SourceRoot -Directory |
        Where-Object { $_.Name -match '^\d{4}$' } |
        Sort-Object Name |
        ForEach-Object { Get-ChildItem $_.FullName -Directory } |
        Sort-Object FullName

    $total = $sessionFolders.Count
    $done  = 0

    foreach ($folder in $sessionFolders) {
        $playlist = Join-Path $OutRoot $folder.Name "playlist.txt"
        if ((Test-Path $playlist) -and (Get-Item $playlist).Length -gt 0) {
            $done++
        }
    }

    Log "Status: $done/$total sessions encoded for streaming"

    if ($done -eq $total) {
        Log "All sessions encoded. Sleeping 1h then re-checking for new footage..."
        Start-Sleep -Seconds 3600
        continue
    }

    foreach ($folder in $sessionFolders) {
        Encode-Session -SessionFolder $folder.FullName
    }
}
