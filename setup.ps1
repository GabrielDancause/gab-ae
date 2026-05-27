# setup.ps1 -- run once on a new machine to prepare for streaming
# Run in PowerShell as Administrator

# 1. ffmpeg
if (-not (Test-Path "C:\ffmpeg\bin\ffmpeg.exe")) {
    Write-Host "Installing ffmpeg..."
    winget install Gyan.FFmpeg --location "C:\ffmpeg" -e --silent
} else { Write-Host "ffmpeg already installed." }

# 2. Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Python 3.12..."
    winget install Python.Python.3.12 -e --silent
} else { Write-Host "Python already installed: $((Get-Command python).Source)" }

# 3. Python packages
Write-Host "Installing Python packages..."
python -m pip install -r "$PSScriptRoot\requirements.txt"

# 4. Map Z: (NAS) -- update the UNC path to match your NAS
# Uncomment and set your NAS path:
# net use Z: \\YOUR-NAS-IP\share /persistent:yes

# 5. Copy secrets and music from the NAS (put there by the encoding computer)
Write-Host "Copying secrets and music from NAS..."
if (Test-Path "Z:\gab-ae-setup") {
    Copy-Item "Z:\gab-ae-setup\client_secrets.json" "$PSScriptRoot\client_secrets.json" -Force
    Copy-Item "Z:\gab-ae-setup\token_youtube.json"  "$PSScriptRoot\token_youtube.json"  -Force
    New-Item -ItemType Directory -Path "$PSScriptRoot\music" -Force | Out-Null
    Copy-Item "Z:\gab-ae-setup\background.mp3"      "$PSScriptRoot\music\background.mp3" -Force
    Write-Host "Secrets and music copied."
} else {
    Write-Host "WARNING: Z:\gab-ae-setup not found -- make sure Z: is mapped to the NAS first."
}

Write-Host ""
Write-Host "Setup complete. Start streaming with:"
Write-Host "  Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json'"
