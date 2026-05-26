$FFmpeg = "C:\ffmpeg\bin\ffmpeg.exe"
$OutDir = "C:\gab-ae\encoded"

$files = Get-ChildItem "L:\DCIM\100MEDIA\*.MP4" | Sort-Object Name

foreach ($f in $files) {
    $out = Join-Path $OutDir $f.Name
    if (Test-Path $out) {
        Write-Host "SKIP (exists): $($f.Name)"
        continue
    }
    Write-Host "Encoding: $($f.Name) ..."
    & $FFmpeg -y `
        -hwaccel cuda `
        -hwaccel_output_format cuda `
        -c:v hevc_cuvid `
        -i $f.FullName `
        -vf "scale_cuda=3840:2160:format=yuv420p" `
        -c:v h264_nvenc `
        -preset p4 `
        -rc cbr `
        -b:v 23500k `
        -maxrate 25000k `
        -bufsize 47000k `
        -g 60 `
        -c:a aac `
        -b:a 192k `
        -ar 44100 `
        -movflags +faststart `
        $out
    Write-Host "Done: $($f.Name)"
}

Write-Host "`nAll done. Files in $OutDir"
