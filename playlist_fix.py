#!/usr/bin/env python3
"""One-off: report the YouTube token's OAuth scopes and add given videos to the quiz playlist.
Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. Args: video ids. Prints one line per result; never prints the token."""
import json, sys, urllib.request
import upload_short as u

tok = u.access_token()
try:
    with urllib.request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?access_token={tok}", timeout=60) as r:
        print("SCOPES " + json.load(r).get("scope", "?"))
except Exception as e:  # noqa: BLE001
    print(f"SCOPES unknown ({e})")
for vid in sys.argv[1:]:
    u.add_to_playlist(tok, vid)
