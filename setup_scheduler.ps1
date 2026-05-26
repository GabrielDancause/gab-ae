# setup_scheduler.ps1 -- register Task Scheduler jobs
# Run once as admin: powershell -ExecutionPolicy Bypass -File C:\gab-ae\setup_scheduler.ps1

$py = "C:\Users\Daryll\AppData\Local\Programs\Python\Python312\python.exe"

# --- 1. hot_feed: encode 4 new clips every hour ---
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\gab-ae\hot_feed.ps1"'
$trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Hours 1) -Once -At (Get-Date)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName "GabHotFeed" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Encodes new clips into hot folder every hour" -Force
Write-Host "Registered: GabHotFeed (every 1 hour)"

# --- 2. Stream: start on login, restart on failure ---
$action2  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\gab-ae\stream_to_youtube.ps1"'
$trigger2 = New-ScheduledTaskTrigger -AtLogOn
$settings2 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "GabStreamLive" -Action $action2 -Trigger $trigger2 -Settings $settings2 `
    -Description "24/7 YouTube live stream -- restarts automatically on any failure" -Force
Write-Host "Registered: GabStreamLive (at login, restart every 1 min on failure)"

# --- 3. Daily upload: 3 videos at 10 AM ---
$action3  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"C:\gab-ae\daily_upload.ps1`""
$trigger3 = New-ScheduledTaskTrigger -Daily -At "10:00AM"
$settings3 = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "GabDailyUpload" -Action $action3 -Trigger $trigger3 -Settings $settings3 `
    -Description "Uploads 3 videos to YouTube every day at 10 AM" -Force
Write-Host "Registered: GabDailyUpload (daily 10 AM)"

Write-Host ""
Write-Host "All tasks registered. Run hot_feed.ps1 manually once to seed the hot folder."
