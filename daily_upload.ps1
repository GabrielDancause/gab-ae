# daily_upload.ps1 -- upload 3 videos to YouTube every day
# Scheduled via Task Scheduler at 10 AM daily.
#
# Picks 3 clips from Z: that have never been uploaded.
# Tracks uploaded files in uploaded.txt -- never re-uploads the same clip.
# Encodes at native resolution with -c:v copy (zero quality loss).
# Title: derived from folder name -- "Location | Month Year | Ambient"

param(
    [string]$SourceDir    = "Z:\01- Media files",
    [string]$MusicFile    = "C:\gab-ae\music\background.mp3",
    [string]$OutDir       = "C:\gab-ae\output",
    [string]$UploadedFile = "C:\gab-ae\uploaded.txt",
    [int]$Count           = 3
)

$FFmpeg  = "C:\ffmpeg\bin\ffmpeg.exe"
$FFprobe = "C:\ffmpeg\bin\ffprobe.exe"
$Python  = "C:\Users\Daryll\AppData\Local\Programs\Python\Python312\python.exe"
$LogFile = "C:\gab-ae\daily_upload.log"

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
if (-not (Test-Path $UploadedFile)) { New-Item $UploadedFile -ItemType File | Out-Null }

$uploaded = Get-Content $UploadedFile -ErrorAction SilentlyContinue

# --- Find candidates: MP4s not yet uploaded, >5 min (worth uploading), >50 MB ---
Log "Scanning for upload candidates..."
$candidates = Get-ChildItem $SourceDir -Recurse |
    Where-Object { $_.Extension -ieq '.MP4' -and $_.Length -gt (50 * 1MB) } |
    Where-Object { $uploaded -notcontains $_.FullName } |
    Sort-Object { Get-Random } |
    Select-Object -First ($Count * 5)   # sample more than needed, filter by duration below

# Filter to clips >= 5 minutes
$picks = @()
foreach ($f in $candidates) {
    if ($picks.Count -ge $Count) { break }
    $dur = & $FFprobe -v quiet -show_entries format=duration -of csv=p=0 $f.FullName 2>$null
    if ([double]$dur -ge 300) { $picks += $f }
}

if ($picks.Count -eq 0) { Log "No candidates found -- all clips uploaded or too short?"; exit 0 }

Log "Picked $($picks.Count) clips to upload today"

# --- Title from folder name ---
function Make-Title($path) {
    $folder = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($path))
    # "2024-03-22 - IRL Bangkok" -> "IRL Bangkok | Mar 2024"
    if ($folder -match '^(\d{4})-(\d{2})-\d{2}\s*-\s*(.+)$') {
        $year  = $Matches[1]
        $month = $Matches[2]
        $label = $Matches[3].Trim()
        $months = @('','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
        return "$label | $($months[[int]$month]) $year | Ambient"
    }
    # Fallback: just use folder name
    return "$folder | Ambient"
}

# --- Encode and upload each pick ---
foreach ($src in $picks) {
    $title   = Make-Title $src.FullName
    $outName = [System.IO.Path]::GetFileNameWithoutExtension($src.FullName) -replace '[^\w\-]','_'
    $outName = $outName.Substring(0, [Math]::Min($outName.Length, 60)) + ".mp4"
    $outPath = Join-Path $OutDir $outName

    Log "--- $title ---"
    Log "Source: $($src.FullName)"

    # Encode: native resolution, video copy, strip audio, add music
    if (-not (Test-Path $outPath)) {
        Log "Encoding..."
        & $FFmpeg -y `
            -i $src.FullName `
            -i $MusicFile `
            -map "0:v:0" `
            -map "1:a:0" `
            -shortest `
            -c:v copy `
            -c:a aac `
            -b:a 320k `
            -ar 44100 `
            -movflags +faststart `
            $outPath 2>$null

        if ($LASTEXITCODE -ne 0) {
            Log "Encode FAILED (exit $LASTEXITCODE) -- skipping"
            Remove-Item $outPath -ErrorAction SilentlyContinue
            continue
        }
        $mb = [math]::Round((Get-Item $outPath).Length / 1MB, 0)
        Log "Encoded: $outName ($mb MB)"
    } else {
        Log "Already encoded: $outName"
    }

    # Upload
    Log "Uploading: $title"
    & $Python "C:\gab-ae\upload_video.py" --file $outPath --title $title 2>&1 | Tee-Object -Variable uploadOut
    $uploadOut | ForEach-Object { Log $_ }

    if ($LASTEXITCODE -eq 0) {
        # Mark as uploaded
        Add-Content -Path $UploadedFile -Value $src.FullName -Encoding UTF8
        Log "Uploaded OK: $title"
        # Clean up encoded file to save space
        Remove-Item $outPath -ErrorAction SilentlyContinue
    } else {
        Log "Upload FAILED -- will retry tomorrow"
    }
}

Log "Daily upload complete."
