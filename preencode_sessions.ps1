# ============================================================
# preencode_sessions.ps1 -- encode a session folder to 4K H.264
# for direct -c:v copy streaming on the second computer.
#
# Run on this (encoding) computer. Output lands on the NAS so
# the streaming computer can pick it up without any re-encoding.
#
# Usage:
#   .\preencode_sessions.ps1
#   .\preencode_sessions.ps1 -SessionFolder "Z:\01- Media files\2026\2026-05-22 - Charlevoix"
#   .\preencode_sessions.ps1 -BitrateK 30000   # higher for very fast-motion content
#
# Output: Z:\gab-ae-sessions\<session-name>\clip_000.mp4 ... + playlist.txt
#
# The streaming computer reads playlist.txt with:
#   stream_to_youtube.ps1 -SessionsDir "Z:\gab-ae-sessions\2026-05-22 - Charlevoix"
# ============================================================

param(
    [string]$SessionFolder = "Z:\01- Media files\2026\2026-05-22 - Charlevoix",
    [string]$OutRoot       = "Z:\gab-ae-sessions",
    [int]   $BitrateK      = 20000   # kbps -- 20 Mbps is high quality for 4K 60fps H.264
)

$FFmpeg  = "C:\ffmpeg\bin\ffmpeg.exe"
$FFprobe = "C:\ffmpeg\bin\ffprobe.exe"

if (-not (Test-Path $FFmpeg))         { Write-Error "ffmpeg not found"; exit 1 }
if (-not (Test-Path $SessionFolder))  { Write-Error "Session folder not found: $SessionFolder"; exit 1 }

$SessionName = Split-Path $SessionFolder -Leaf
$SessionOut  = Join-Path $OutRoot $SessionName
New-Item -ItemType Directory -Path $SessionOut -Force | Out-Null
Write-Host "Session  : $SessionName"
Write-Host "Output   : $SessionOut"
Write-Host "Bitrate  : ${BitrateK}k ($([int]($BitrateK/1000)) Mbps)"
Write-Host ""

# Collect all video files in chronological order (sort by full path = folder + name order)
$files = Get-ChildItem $SessionFolder -Recurse -Include "*.mp4","*.MP4","*.mov","*.MOV","*.mts","*.MTS" |
    Where-Object { $_.Length -gt 50MB } |
    Sort-Object FullName

if ($files.Count -eq 0) { Write-Error "No video files found in $SessionFolder"; exit 1 }

Write-Host "Found $($files.Count) file(s) to encode"
Write-Host ""

$lines   = [System.Collections.Generic.List[string]]::new()
$encoded = 0
$failed  = 0
$i       = 0

foreach ($f in $files) {
    $out = Join-Path $SessionOut ("clip_{0:000}.mp4" -f $i)

    # Skip if already encoded and valid
    if (Test-Path $out) {
        $chk = & $FFprobe -v error -show_entries format=duration `
            -of default=noprint_wrappers=1:nokey=1 $out 2>$null
        if ($chk -match '^\d' -and [double]$chk -gt 5) {
            Write-Host "[$($i.ToString('000'))] SKIP (exists): $($f.Name)"
            $lines.Add("file '$($out.Replace('\','/'))'")
            $encoded++
            $i++
            continue
        }
        Remove-Item $out -Force -ErrorAction SilentlyContinue
    }

    # Detect source codec to pick the right hardware decoder
    $srcCodec = & $FFprobe -v error -select_streams v:0 `
        -show_entries stream=codec_name `
        -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null

    $srcCodec = ($srcCodec -split "`n")[0].Trim()

    switch ($srcCodec) {
        'hevc'  { $hwDecArgs = @('-hwaccel','cuda','-hwaccel_output_format','cuda','-c:v','hevc_cuvid') }
        'h264'  { $hwDecArgs = @('-hwaccel','cuda','-hwaccel_output_format','cuda','-c:v','h264_cuvid') }
        default { $hwDecArgs = @('-hwaccel','cuda') }   # software decode, GPU output
    }

    $srcW = & $FFprobe -v error -select_streams v:0 -show_entries stream=width `
        -of default=noprint_wrappers=1:nokey=1 $f.FullName 2>$null
    $srcW = ($srcW -split "`n")[0].Trim()
    $is4k = ($srcW -as [int]) -ge 3840

    # If source is already 4K use scale_cuda; otherwise upscale with padding
    if ($is4k) {
        $vf = "scale_cuda=3840:2160:format=yuv420p"
    } else {
        # Software scale with letterbox/pillarbox for non-4K sources
        $vf = "scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2,format=yuv420p,setpts=PTS-STARTPTS"
        $hwDecArgs = @()   # use software path for non-4K (scale_cuda won't run after CPU filter)
    }

    $mb = [int]($f.Length / 1MB)
    Write-Host "[$($i.ToString('000'))] Encoding ($($i+1)/$($files.Count)): $($f.Name)  (${mb} MB, $srcCodec, ${srcW}w)"

    $ffArgs = $hwDecArgs + @(
        '-y', '-i', $f.FullName,
        '-vf', $vf,
        '-c:v', 'h264_nvenc',
        '-preset', 'p4',
        '-rc', 'cbr',
        '-b:v', "${BitrateK}k",
        '-maxrate', "${BitrateK}k",
        '-bufsize', "$([int]$BitrateK * 2)k",
        '-bf', '0',
        '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
        '-video_track_timescale', '90000',
        '-an',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        $out
    )

    & $FFmpeg @ffArgs

    if ($LASTEXITCODE -eq 0 -and (Test-Path $out) -and (Get-Item $out).Length -gt 0) {
        $outMB = [int]((Get-Item $out).Length / 1MB)
        Write-Host "  -> OK: ${outMB} MB"
        $lines.Add("file '$($out.Replace('\','/'))'")
        $encoded++
    } else {
        Remove-Item $out -ErrorAction SilentlyContinue
        Write-Host "  -> FAILED -- skipping"
        $failed++
    }
    $i++
}

# Write BOM-free playlist for streaming
$playlistFile = Join-Path $SessionOut "playlist.txt"
[System.IO.File]::WriteAllLines($playlistFile, $lines, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "============================================================"
Write-Host "Done: $encoded encoded, $failed failed"
Write-Host "Playlist: $playlistFile"
Write-Host ""
Write-Host "Stream on second computer with:"
Write-Host "  stream_to_youtube.ps1 -SessionsDir '$SessionOut'"
Write-Host "============================================================"
