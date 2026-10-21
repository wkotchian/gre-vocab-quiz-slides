#!/usr/bin/env python3
"""One-off: report the YouTube token's OAuth scopes and add given videos to the quiz playlist.
Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. Args: video ids. Prints one line per result; never prints the token."""
import json, os, sys, urllib.parse, urllib.request

PLAYLIST = "PLWEAzawLBpKE"
body = urllib.parse.urlencode({
    "client_id": os.environ["YT_CLIENT_ID"].strip(),
    "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
    "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
    "grant_type": "refresh_token"}).encode()
with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=60) as r:
    tok = json.load(r)["access_token"]
try:
    with urllib.request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?access_token={tok}", timeout=60) as r:
        print("SCOPES " + json.load(r).get("scope", "?"))
except Exception as e:  # noqa: BLE001
    print(f"SCOPES unknown ({e})")
for vid in sys.argv[1:]:
    data = json.dumps({"snippet": {"playlistId": PLAYLIST, "resourceId": {"kind": "youtube#video", "videoId": vid}}}).encode()
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet", data=data, method="POST",
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=60):
            print(f"PLAYLIST added {vid}")
    except Exception as e:  # noqa: BLE001
        d = e.read().decode(errors="replace") if hasattr(e, "read") else str(e)
        print(f"PLAYLIST not added {vid} ({getattr(e, 'code', '')}): {' '.join(d.split())[:400]}")
