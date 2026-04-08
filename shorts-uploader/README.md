# Shorts Uploader

Automated YouTube Shorts publisher. Picks videos from a Google Drive folder and uploads them to YouTube on a schedule.

## How it works

1. Videos are placed in a Google Drive folder under `01-todo/`
2. A cron job runs `upload_shorts.py` every 6 hours
3. The script downloads the next video from `01-todo/`, uploads it to YouTube as a Short, then moves it to `02-done/`
4. Titles are cleaned up automatically (leading numbers like "302 - " are stripped, truncated to 100 chars)

## Google Drive structure

```
Parent folder (1SujQQeplJmOq_tRMUul0N7xz6_Nn-yjM)
  01-todo/   <-- put new videos here
  02-done/   <-- videos move here after upload
```

The Drive folder belongs to `imperiale.alexandra@gmail.com`.

## YouTube channel

Uploads go to the channel associated with the authenticated Google account (`imperiale.alexandra@gmail.com`).
This is currently: https://www.youtube.com/@pleasure_education

## Auth

- OAuth 2.0 Desktop App flow via `credentials.json` (from Google Cloud Console, project: `gen-lang-client-0470855939` / "openclaw")
- Token is saved in `token.json` (auto-refreshes)
- Scopes: `drive` (read + move files) and `youtube.upload`
- If `token.json` is deleted, re-running the script will open a browser for re-auth. Log in with `imperiale.alexandra@gmail.com`.
- The Google Cloud app must be in **Testing** mode with `imperiale.alexandra@gmail.com` as a test user (brand accounts can't auth in testing mode)

## Files

| File | Purpose | Git tracked? |
|------|---------|-------------|
| `upload_shorts.py` | Main script | Yes |
| `credentials.json` | OAuth client ID/secret from Google Cloud | **No** (gitignored) |
| `token.json` | OAuth refresh token, auto-generated on first run | **No** (gitignored) |
| `cron.log` | Output log from cron runs | No |
| `requirements.txt` | Python dependencies | Yes |

## Commands

```bash
# Upload next video (default)
python3 upload_shorts.py

# Upload next 3 videos
python3 upload_shorts.py --count 3

# List what's in todo/done
python3 upload_shorts.py --list
```

## Cron schedule

Runs every 6 hours (00:00, 06:00, 12:00, 18:00), uploads 1 video per run:

```
0 */6 * * * cd /Users/gab/Desktop/gab-ae/shorts-uploader && /usr/bin/python3 upload_shorts.py --count 1 >> cron.log 2>&1
```

## YouTube API quota

- Each upload costs ~1,600 units
- Daily limit: 10,000 units
- 4 uploads/day (every 6h) = 6,400 units -- safe
- Check `cron.log` if uploads stop working (likely quota exceeded)

## Troubleshooting

- **"quotaExceeded"**: Wait until tomorrow, quota resets daily
- **Auth errors**: Delete `token.json` and re-run to re-authenticate
- **No videos uploaded**: Check `01-todo/` has video files in Drive
- **Wrong channel**: The upload goes to whichever YouTube channel the OAuth token is tied to. To change, delete `token.json` and re-auth with a different account
