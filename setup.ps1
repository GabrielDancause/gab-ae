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

# 5. Copy secrets from the encoding computer (gitignored, must be copied manually):
#   - client_secrets.json   -> C:\gab-ae\client_secrets.json
#   - token_youtube.json    -> C:\gab-ae\token_youtube.json
#   - music\background.mp3  -> C:\gab-ae\music\background.mp3

Write-Host ""
Write-Host "Setup complete. Manual steps remaining:"
Write-Host "  1. Copy client_secrets.json and token_youtube.json from the encoding computer"
Write-Host "  2. Copy music\background.mp3"
Write-Host "  3. Make sure Z: is mapped to the NAS"
Write-Host ""
Write-Host "Then start streaming with:"
Write-Host "  Start-Process powershell -ArgumentList '-NonInteractive -WindowStyle Normal -ExecutionPolicy Bypass -File C:\gab-ae\stream_to_youtube.ps1 -StateFile C:\gab-ae\broadcast_state2.json'"
