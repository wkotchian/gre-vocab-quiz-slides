#!/usr/bin/env python3
"""Post the next GRE vocab quiz carousel to Instagram via the official API.

Usage:  IG_TOKEN=... python3 post_next.py [--dry-run] [--num N]

Safety rules built in:
  * official Instagram API only (graph.instagram.com) — no browser automation
  * at most ONE quiz post per 20 hours; skips if a quiz was posted more recently
  * never reposts a quiz number that already appears in recent captions
  * stops on any API error instead of retrying in a loop
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

API = "https://graph.instagram.com/v23.0"
RAW = "https://raw.githubusercontent.com/wkotchian/gre-vocab-quiz-slides/main/"
HERE = os.path.dirname(os.path.abspath(__file__))
MIN_GAP_HOURS = 20


def call(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        body = body.replace(token, "<token>")
        sys.exit(f"API error {e.code} on {method} {path}: {body}")


def main():
    token = os.environ.get("IG_TOKEN", "").strip()
    if not token:
        sys.exit("IG_TOKEN is not set")
    dry = "--dry-run" in sys.argv
    forced = int(sys.argv[sys.argv.index("--num") + 1]) if "--num" in sys.argv else None

    queue = json.load(open(os.path.join(HERE, "queue.json")))
    me = call("GET", "me", token, fields="user_id,username")
    uid = me["user_id"]
    print("account:", me["username"])

    recent = call("GET", f"{uid}/media", token, fields="caption,timestamp", limit=25).get("data", [])
    posted_nums, last_quiz_time = set(), None
    for m in recent:
        cap = m.get("caption") or ""
        for q in queue:
            if cap.startswith(f"Pop quiz #{q['num']}:"):
                posted_nums.add(q["num"])
                t = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
                last_quiz_time = max(last_quiz_time or t, t)

    if last_quiz_time:
        hours = (datetime.now(timezone.utc) - last_quiz_time).total_seconds() / 3600
        print(f"last quiz posted {hours:.1f}h ago")
        if hours < MIN_GAP_HOURS and not dry:
            print("SKIP: too soon since last quiz post")
            return

    if forced:
        item = next(q for q in queue if q["num"] == forced)
    else:
        last = max(posted_nums) if posted_nums else None
        nxt = [q for q in queue if q["num"] not in posted_nums and (last is None or q["num"] > last)]
        if not nxt:
            print("QUEUE EMPTY: all quizzes posted — time to add more cartoons")
            return
        item = nxt[0]
    if item["num"] in posted_nums:
        sys.exit(f"Quiz #{item['num']} already posted; refusing to repost")

    urls = [RAW + p for p in item["slides"]]
    print(f"next: #{item['num']} {item['word']} (answer {item['answer']})")
    for u in urls:
        print("  ", u)
    if dry:
        print("DRY RUN: nothing posted")
        return

    limit = call("GET", f"{uid}/content_publishing_limit", token, fields="quota_usage,config")
    print("publishing limit:", json.dumps(limit.get("data", limit)))

    children = [call("POST", f"{uid}/media", token, image_url=u, is_carousel_item="true")["id"] for u in urls]
    container = call("POST", f"{uid}/media", token, media_type="CAROUSEL",
                     children=",".join(children), caption=item["caption"])["id"]
    for _ in range(30):
        st = call("GET", container, token, fields="status_code")["status_code"]
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"container {container} status {st}")
        time.sleep(5)
    else:
        sys.exit("container never finished processing")
    pub = call("POST", f"{uid}/media_publish", token, creation_id=container)
    link = call("GET", pub["id"], token, fields="permalink").get("permalink")
    print(f"POSTED #{item['num']} {item['word']}: {link}")


if __name__ == "__main__":
    main()
