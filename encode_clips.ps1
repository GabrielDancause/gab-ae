# Encode clips for YouTube upload.
# Strips original audio, adds background music, scales to 1080p.
# Usage: .\encode_clips.ps1

$FFmpeg = "C:\ffmpeg\bin\ffmpeg.exe"
$Music  = "C:\gab-ae\music\background.mp3"
$OutDir = "C:\gab-ae\output"

function Encode-Clip {
    param(
        [string]$Title,
        [string[]]$Sources,
        [string]$OutName
    )

    $out = "$OutDir\$OutName"
    if (Test-Path $out) {
        Write-Host "SKIP (exists): $OutName"
        return
    }

    Write-Host ""
    Write-Host "=== $Title ==="

    # build concat list if multiple sources
    if ($Sources.Count -gt 1) {
        $listFile = "$OutDir\_concat_tmp.txt"
        $lines = $Sources | ForEach-Object { "file '$($_.Replace('\','/'))'"}
        [System.IO.File]::WriteAllLines($listFile, $lines, [System.Text.UTF8Encoding]::new($false))
        $inputArgs = @("-f", "concat", "-safe", "0", "-i", $listFile)
    } else {
        $inputArgs = @("-i", $Sources[0])
    }

    & $FFmpeg -y `
        -hwaccel cuda `
        @inputArgs `
        -stream_loop -1 -i $Music `
        -map "0:v:0" `
        -map "1:a:0" `
        -shortest `
        -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" `
        -c:v h264_nvenc `
        -preset p4 `
        -rc cbr `
        -b:v 8000k `
        -maxrate 10000k `
        -bufsize 20000k `
        -g 60 `
        -c:a aac `
        -b:a 192k `
        -ar 44100 `
        -movflags +faststart `
        $out

    if ($LASTEXITCODE -eq 0) {
        $mb = [math]::Round((Get-Item $out).Length / 1MB, 0)
        Write-Host "Done: $OutName ($mb MB)"
    } else {
        Write-Host "FAILED: $OutName (exit $LASTEXITCODE)"
    }
}

# --- Today's 3 clips ---

Encode-Clip `
    -Title "A Day in Bangkok" `
    -Sources @("Z:\01- Media files\2024\2024-03-22 - IRL Bangkok\Slow TV Export\20240322  - A day in bangkok.mp4") `
    -OutName "2024-03-22_A-Day-in-Bangkok.mp4"

Encode-Clip `
    -Title "Night Walk Bangkok" `
    -Sources @(
        "Z:\01- Media files\2024\2024-03-22 - IRL Bangkok\4 - Night Walking in Thailand\GX010175.MP4",
        "Z:\01- Media files\2024\2024-03-22 - IRL Bangkok\4 - Night Walking in Thailand\GX010176.MP4"
    ) `
    -OutName "2024-03-22_Night-Walk-Bangkok.mp4"

Encode-Clip `
    -Title "Ao Nang, Krabi, Thailand" `
    -Sources @("Z:\01- Media files\2024\2024-03-27 - Ao Nang, Krabi, Thailand\DCIM\100GOPRO\GX010221.MP4") `
    -OutName "2024-03-27_Ao-Nang-Krabi-Thailand.mp4"

Write-Host ""
Write-Host "All done. Files in $OutDir"
