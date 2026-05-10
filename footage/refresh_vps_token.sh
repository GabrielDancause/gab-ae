#!/bin/bash
# Refresh wrangler OAuth token and push fresh one to VPS
# Runs every 45 min via crontab; wrangler auto-refreshes when token expires
cd /Users/gab/Desktop/gab-ae

# Trigger wrangler — it will auto-refresh the token if expired (using its internal PKCE refresh)
npx wrangler d1 list --remote > /dev/null 2>&1 || true

# Read token from config (may be fresh if wrangler just refreshed it)
NEW_TOKEN=$(python3 -c "
import tomllib, pathlib
p = pathlib.Path.home() / 'Library/Preferences/.wrangler/config/default.toml'
with open(p, 'rb') as f:
    cfg = tomllib.load(f)
print(cfg['oauth_token'])
")

if [ -n "$NEW_TOKEN" ] && [ ${#NEW_TOKEN} -lt 200 ]; then
  ssh root@178.105.50.213 "echo '$NEW_TOKEN' > /tmp/cf_token.txt"
  echo "$(date -u): Token pushed (${#NEW_TOKEN} chars) → VPS"
else
  echo "$(date -u): ERROR - bad token (${#NEW_TOKEN} chars): $NEW_TOKEN"
fi
