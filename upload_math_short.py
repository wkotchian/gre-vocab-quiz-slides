#!/usr/bin/env python3
"""Render and upload the next GRE Quant or SAT Math Short (questions from the apps) via the official YouTube Data API.

Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN   (same GitHub secrets as the vocab Shorts)
Args: [--privacy public|private|unlisted] [--num N] [--dry-run]

Safety rules built in:
  * official YouTube Data API only; refuses unless the authorized channel is "Vince Kotchian Test Prep"
  * does nothing before the start date in math/start_date.txt (set the day GRE Math Knight 2.0 is live)
  * at most ONE GRE Quant Short per 16 hours; never re-uploads a number already on the channel or in math_shorts.log
  * stops on any API error instead of retrying in a loop
"""
import json, os, re, sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_math_short  # noqa: E402
from upload_short import http, access_token, arg, API, EXPECTED_CHANNEL  # noqa: E402

MIN_GAP_HOURS = 16
CFG = {
    "gre": {"title": "GRE Quant", "game": "GRE Math Knight", "url": "https://apps.apple.com/app/id1535485326",
            "start": "start_date.txt", "log": "math_shorts.log",
            "tags": ["GRE", "GRE quant", "GRE math", "GRE prep"], "hashtags": "#GRE #GREquant #GREmath #GREprep #Shorts",
            "help": "https://vincekotchian.com/gre/free-gre-resources/"},
    "sat": {"title": "SAT Math", "game": "SAT Math Swordsman", "url": "https://apps.apple.com/app/id6835253506",
            "start": "sat_start_date.txt", "log": "sat_shorts.log", "auto_live": True,
            "tags": ["SAT", "SAT math", "digital SAT", "SAT prep"], "hashtags": "#SAT #SATmath #DigitalSAT #SATprep #Shorts",
            "help": None},
    "act": {"title": "ACT Math", "game": "ACT Math Adventurer", "url": "https://apps.apple.com/app/id6835253855",
            "start": "act_start_date.txt", "log": "act_shorts.log", "auto_live": True,
            "tags": ["ACT", "ACT math", "ACT prep", "ACT test"], "hashtags": "#ACT #ACTmath #ACTprep #Shorts",
            "help": None},
}
APP = arg("--app", "gre")
C = CFG[APP]
TITLE_RE = re.compile(re.escape(C["title"]) + r" #(\d+)\b")


def app_is_live():
    """True once the app shows up in Apple's public lookup (it only does after release)."""
    import urllib.request
    app_id = C["url"].rsplit("id", 1)[1]
    try:
        with urllib.request.urlopen(f"https://itunes.apple.com/lookup?id={app_id}&country=us", timeout=30) as r:
            return json.load(r).get("resultCount", 0) > 0
    except Exception as e:  # noqa: BLE001
        print(f"lookup failed: {e}")
        return False


def start_date():
    raw = open(os.path.join(HERE, "math", C["start"])).read().strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    # SAT and ACT start by themselves the day Apple lists the app; GRE waits for a date (2.0 is an update, not a new app)
    if C.get("auto_live") and app_is_live():
        print("app is live on the App Store: starting today")
        return datetime.now(timezone.utc).date()
    return None


def logged_nums():
    p = os.path.join(HERE, C["log"])
    if not os.path.exists(p):
        return set()
    return {int(m.group(1)) for m in re.finditer(r"UPLOADED #(\d+)", open(p).read())}


def main():
    dry = "--dry-run" in sys.argv
    privacy = arg("--privacy", "public")
    forced = int(arg("--num")) if arg("--num") else None
    start = start_date()
    today = datetime.now(timezone.utc).date()
    if not forced and (start is None or today < start):
        print(f"NOT STARTED: start date is {start or 'not set'} (set math/{C['start']})")
        return

    tok = access_token()
    ch = http("GET", f"{API}/channels?part=snippet,contentDetails&mine=true", tok)["items"]
    if not ch or ch[0]["snippet"]["title"] != EXPECTED_CHANNEL:
        sys.exit(f"Wrong channel authorized: {[c['snippet']['title'] for c in ch]} (expected {EXPECTED_CHANNEL})")
    uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = http("GET", f"{API}/playlistItems?part=snippet&maxResults=50&playlistId={uploads}", tok).get("items", [])

    make_math_short.use_app(APP)
    queue = json.load(open(os.path.join(HERE, make_math_short.APP["queue"])))
    done, last_time = logged_nums(), None
    for it in items:
        m = TITLE_RE.search(it["snippet"]["title"])
        if m:
            done.add(int(m.group(1)))
            ts = datetime.strptime(it["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            last_time = max(last_time or ts, ts)
    if last_time and not forced:
        hours = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
        print(f"last {C['title']} Short uploaded {hours:.1f}h ago")
        if hours < MIN_GAP_HOURS and not dry:
            print(f"SKIP: too soon since last {C['title']} Short")
            return

    if forced:
        q = next(x for x in queue if x["num"] == forced)
    else:
        nxt = [x for x in queue if x["num"] not in done and x["num"] > max(done or {0})]
        if not nxt:
            print(f"QUEUE EMPTY: all {C['title']} Shorts uploaded")
            return
        q = nxt[0]
    if q["num"] in done:
        sys.exit(f"{C['title']} #{q['num']} is already on the channel; refusing to re-upload")

    skill = q.get("skill") or C["title"]
    title = f"{C['title']} #{q['num']}: {skill} #Shorts"[:100]
    desc = ("Solve it before the countdown ends, or pause the video if you need more time. "
            "Then see the answer and the trap answer people pick.\n\n"
            "Got it right? Comment ✅ or ❌.\n\n"
            f"This question is from my game, {C['game']}. It has hundreds more like it, and it shows the "
            f"mistake behind every wrong answer. Search \"{C['game']}\" in the App Store: {C['url']}\n\n"
            + (f"More free GRE help: {C['help']}\n\n" if C["help"] else "")
            + C["hashtags"])
    print(f"next: {C['title']} #{q['num']} {q['id']} (privacy: {privacy})")
    if dry:
        print("DRY RUN: nothing uploaded"); print("title:", title); return

    out = os.path.join(HERE, f"{APP}-math-short-{q['num']}.mp4")
    make_math_short.make(q["num"], out, app=APP)
    meta = {"snippet": {"title": title, "description": desc, "categoryId": "27",
                        "tags": C["tags"] + [skill.lower()]},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    size = os.path.getsize(out)
    r = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
             tok, data=json.dumps(meta).encode(), raw=True,
             headers={"Content-Type": "application/json; charset=UTF-8",
                      "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    loc = r.headers["Location"]
    with open(out, "rb") as f:
        v = http("PUT", loc, tok, data=f.read(), headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    print(f"UPLOADED #{q['num']} {q['id']} ({privacy}): https://youtube.com/shorts/{v['id']}")


if __name__ == "__main__":
    main()
