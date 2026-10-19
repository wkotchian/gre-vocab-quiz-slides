#!/usr/bin/env python3
"""Render and upload the next GRE vocab quiz Short via the official YouTube Data API.

Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   (GitHub secrets)
Args: [--privacy public|private|unlisted] [--num N] [--dry-run]

Safety rules built in:
  * official YouTube Data API only — no browser automation
  * refuses to upload unless the authorized channel is "Vince Kotchian Test Prep"
  * at most ONE quiz Short per 16 hours; never re-uploads a quiz number already on the channel
  * stops on any API error instead of retrying in a loop
"""
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_short  # noqa: E402

EXPECTED_CHANNEL = "Vince Kotchian Test Prep"
MIN_GAP_HOURS = 16
API = "https://www.googleapis.com/youtube/v3"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def http(method, url, token=None, data=None, headers=None, raw=False):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r if raw else json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"API error {e.code} on {method} {url.split('?')[0]}: {e.read().decode(errors='replace')[:800]}")


def access_token():
    body = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"}).encode()
    return http("POST", "https://oauth2.googleapis.com/token", data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"})["access_token"]


def main():
    dry = "--dry-run" in sys.argv
    privacy = arg("--privacy", "public")
    forced = int(arg("--num")) if arg("--num") else None
    tok = access_token()

    ch = http("GET", f"{API}/channels?part=snippet,contentDetails&mine=true", tok)["items"]
    if not ch or ch[0]["snippet"]["title"] != EXPECTED_CHANNEL:
        sys.exit(f"Wrong channel authorized: {[c['snippet']['title'] for c in ch]} (expected {EXPECTED_CHANNEL})")
    uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print("channel:", ch[0]["snippet"]["title"])

    items = http("GET", f"{API}/playlistItems?part=snippet&maxResults=50&playlistId={uploads}", tok).get("items", [])
    queue = json.load(open(os.path.join(HERE, "queue.json")))
    nums = {q["num"] for q in queue}
    done, last_time = set(), None
    for it in items:
        t = it["snippet"]["title"]
        m = re.search(r"GRE vocab quiz #(\d+)", t, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if n in nums:
                done.add(n)
                ts = datetime.strptime(it["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                last_time = max(last_time or ts, ts)

    if last_time and not forced:
        hours = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
        print(f"last quiz Short uploaded {hours:.1f}h ago")
        if hours < MIN_GAP_HOURS and not dry:
            print("SKIP: too soon since last quiz Short")
            return

    if forced:
        item = next(q for q in queue if q["num"] == forced)
    else:
        last = max(done) if done else None
        nxt = [q for q in queue if q["num"] not in done and (last is None or q["num"] > last)]
        if not nxt:
            print("QUEUE EMPTY: all quiz Shorts uploaded")
            return
        item = nxt[0]
    if item["num"] in done:
        sys.exit(f"Quiz #{item['num']} is already on the channel; refusing to re-upload")

    word = item["word"].upper()
    # Word first: people search "<word> meaning". The parser above matches "GRE vocab quiz #N" in old and new titles.
    title = f"{word} meaning: GRE vocab quiz #{item['num']} #Shorts"[:100]
    desc = (f"What does {word} mean? Pick A, B, C, or D before the countdown ends, then see the cartoon "
            "that makes it stick.\n\nGot it right? Comment ✅ or ❌.\n\n"
            "Learn 1,200+ GRE words with funny cartoons in the GRE Vocab Cartoons app. "
            "Search \"GRE Vocabulary Cartoons\" in the App Store or \"GRE Vocab Cartoons Flashcards\" on Google Play.\n\n"
            "More free GRE help: https://vincekotchian.com/gre/free-gre-resources/\n\n#GRE #GREvocabulary #GREprep #vocabulary #Shorts")
    print(f"next: #{item['num']} {item['word']} (privacy: {privacy})")
    if dry:
        print("DRY RUN: nothing uploaded"); print("title:", title); return

    out = os.path.join(HERE, f"short-{item['num']}.mp4")
    make_short.make(item["num"], out)
    meta = {"snippet": {"title": title, "description": desc, "categoryId": "27",
                        "tags": ["GRE", "GRE vocabulary", "GRE prep", "vocabulary quiz", word.lower()]},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    size = os.path.getsize(out)
    r = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
             tok, data=json.dumps(meta).encode(), raw=True,
             headers={"Content-Type": "application/json; charset=UTF-8",
                      "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    loc = r.headers["Location"]
    with open(out, "rb") as f:
        v = http("PUT", loc, tok, data=f.read(), headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    print(f"UPLOADED #{item['num']} {item['word']} ({privacy}): https://youtube.com/shorts/{v['id']}")


if __name__ == "__main__":
    main()
