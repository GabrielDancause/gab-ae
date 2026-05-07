#!/usr/bin/env python3
"""
Re-auth the YouTube token for channel-uc59 with full 'youtube' scope.
Run locally — opens a browser for OAuth consent.
Saves token to ./token_uc59_full.json, then you can scp it to the VPS.
"""

from google_auth_oauthlib.flow import InstalledAppFlow
import json

CLIENT_SECRET = '/Users/gab/Downloads/client_secret_66635002173-s9l6nrdd3q4ghnciehf61htudoa96pdl.apps.googleusercontent.com.json'
OUT_TOKEN     = '/Users/gab/Desktop/gab-ae/footage/token_uc59_full.json'

SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.upload',
]

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
creds = flow.run_local_server(port=0)

with open(OUT_TOKEN, 'w') as f:
    f.write(creds.to_json())

print(f'\nToken saved to {OUT_TOKEN}')
print('Now run:')
print(f'  scp {OUT_TOKEN} root@178.105.50.213:/opt/gab/channel-uc59/token.json')
