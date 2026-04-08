# YouTube Shorts Uploader — Setup Guide

## 1. Install dependencies

```bash
cd shorts-uploader
pip install -r requirements.txt
```

## 2. Create Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable these two APIs:
   - **Google Drive API**
   - **YouTube Data API v3**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
5. Application type: **Desktop app**
6. Download the JSON file and save it as `credentials.json` in this folder (`shorts-uploader/`)

## 3. First run (OAuth login)

```bash
python upload_shorts.py --list
```

A browser window will open asking you to sign in with the Google account that owns the Drive folder **and** the YouTube channel. Grant both permissions.

> **Note:** The Drive folder and YouTube channel must be owned by the same Google account, OR you must add the uploader account as a manager on the YouTube channel.

## 4. Test with one upload

```bash
python upload_shorts.py --count 1
```

Check your YouTube Studio to confirm the Short appears.

## 5. Schedule 6 uploads per day with cron

Open your crontab:
```bash
crontab -e
```

Add these 6 lines (uploads at 6am, 8am, 10am, 12pm, 2pm, 4pm):
```
0 6  * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
0 8  * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
0 10 * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
0 12 * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
0 14 * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
0 16 * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && python upload_shorts.py >> cron.log 2>&1
```

> **Quota warning:** 6 uploads/day = ~9,600 of 10,000 API units. If you hit the limit,
> reduce to 5/day or request a quota increase in Google Cloud Console.

## 6. Useful commands

```bash
# See all pending and uploaded videos
python upload_shorts.py --list

# Upload the next 3 right now
python upload_shorts.py --count 3

# Retry a failed upload (use the Drive file ID shown in --list)
python upload_shorts.py --reset 1AbCdEfGhIjKlMnOpQrStUv

# Check cron logs
tail -f cron.log
```

## Files in this folder

| File | Purpose |
|------|---------|
| `credentials.json` | OAuth client secret (you create this — keep it private) |
| `token.json` | Your OAuth token (auto-created on first run — keep it private) |
| `state.json` | Tracks which videos have been uploaded (auto-created) |
| `cron.log` | Cron job output log (auto-created) |

**Never commit `credentials.json` or `token.json` to git.**
