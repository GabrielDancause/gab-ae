param(
    [string]$SourceDir = "$env:USERPROFILE\Downloads"
)

$FFmpeg   = "C:\ffmpeg\bin\ffmpeg.exe"
$OutFile  = "C:\gab-ae\music\background.mp3"
$ListFile = "C:\gab-ae\music\music_list.txt"

$tracks = Get-ChildItem $SourceDir -Filter "*.mp3" | Sort-Object Name

if ($tracks.Count -eq 0) {
    Write-Error "No mp3 files found in $SourceDir"
    exit 1
}

Write-Host "$($tracks.Count) tracks found:"
$tracks | ForEach-Object { Write-Host "  $($_.Name)" }

$lines = $tracks | ForEach-Object {
    $path = $_.FullName.Replace('\', '/').Replace("'", "'\''")
    "file '$path'"
}
[System.IO.File]::WriteAllLines($ListFile, $lines, [System.Text.UTF8Encoding]::new($false))

$totalMB = [math]::Round(($tracks | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host "Total input: $totalMB MB -- concatenating into background.mp3..."
Write-Host "(This takes a few minutes)"
Write-Host ""

& $FFmpeg -y `
    -f concat -safe 0 `
    -i $ListFile `
    -c:a libmp3lame `
    -b:a 192k `
    -ar 44100 `
    $OutFile

$code = $LASTEXITCODE
if ($code -eq 0) {
    $outMB = [math]::Round((Get-Item $OutFile).Length / 1MB, 1)
    Write-Host ""
    Write-Host "Done: $OutFile -- $outMB MB"
    Write-Host "Run .\stream_to_youtube.ps1 to go live."
} else {
    Write-Error "ffmpeg failed -- exit code $code"
}
