#!/usr/bin/env python3
"""Post the next GRE vocab quiz Reel to Instagram via the official API.

Usage:  IG_TOKEN=... GITHUB_TOKEN=... python3 post_reel.py [--dry-run] [--test-container] [--num N] [--verify]

Reels use the same ~16-second video as the YouTube Shorts (make_short.py) and work through
queue.json from the END (#1675, #1674, ...), while carousels and Shorts count up from #471,
so followers never see the same word twice in one day.

Safety rules built in:
  * official Instagram API only (graph.instagram.com) - no browser automation
  * at most ONE Reel per 16 hours; skips if a Reel was posted more recently
  * never reposts a quiz number that already has a Reel, and skips numbers already used by a
    carousel ("Pop quiz #N:") among the account's 50 most recent media
  * stops on any API error instead of retrying in a loop
  * the token is never printed (it is masked in every error message)

Flags:
  --dry-run          no render, no hosting, no API writes
  --test-container   do everything up to a FINISHED container, then stop WITHOUT publishing
  --num N            manual override of the quiz number
  --verify           read-only: print the newest Reels, their type/caption/permalink, and the publishing limit

Env REEL_HOSTING=raw (default) serves the file from raw.githubusercontent.com (branch reel-files);
REEL_HOSTING=pages serves it from GitHub Pages on that same branch.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

API = "https://graph.instagram.com/v23.0"
REPO = "wkotchian/gre-vocab-quiz-slides"
BRANCH = "reel-files"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MIN_GAP_HOURS = 16
THUMB_OFFSET_MS = 1500  # the quiz screen (countdown running) as the grid thumbnail


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


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
    except urllib.error.URLError as e:
        sys.exit(f"Network error on {method} {path}: {str(e).replace(token, '<token>')}")


def video_url(num):
    if os.environ.get("REEL_HOSTING", "raw") == "pages":
        return f"https://wkotchian.github.io/gre-vocab-quiz-slides/{num:04d}.mp4"
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{num:04d}.mp4"


def host_file(path, num):
    """Force-push an orphan branch holding ONLY NNNN.mp4 (one commit, replaced every run)."""
    gh = os.environ.get("GITHUB_TOKEN", "").strip()
    if not gh:
        sys.exit("GITHUB_TOKEN is not set (needed to push the reel-files branch)")
    tmp = tempfile.mkdtemp()
    name = f"{num:04d}.mp4"
    shutil.copy(path, os.path.join(tmp, name))

    def git(*a):
        r = subprocess.run(["git", *a], cwd=tmp, capture_output=True, text=True)
        if r.returncode:
            sys.exit("git failed: " + (r.stdout + r.stderr).replace(gh, "<token>"))

    git("init", "-q", "-b", BRANCH)
    git("add", name)
    git("-c", "user.name=gre-quiz-bot", "-c", "user.email=actions@users.noreply.github.com",
        "commit", "-q", "-m", f"reel file #{num}")
    git("push", "-q", "-f", f"https://x-access-token:{gh}@github.com/{REPO}.git", f"{BRANCH}:{BRANCH}")
    print(f"pushed orphan branch {BRANCH} with {name}")


def wait_for_url(url, size, max_secs):
    """Wait until the URL returns 200 with the right byte size (and, for Pages, video/mp4)."""
    end = time.time() + max_secs
    last = None
    while time.time() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=30) as r:
                length = int(r.headers.get("Content-Length") or -1)
                ctype = r.headers.get("Content-Type")
                last = f"{r.status} {ctype} {length}"
                if r.status == 200 and length == size:
                    print(f"video URL ready: {last}")
                    return
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
        except Exception as e:  # network blips: keep waiting until the deadline
            last = type(e).__name__
        time.sleep(5)
    sys.exit(f"video URL never became ready ({last}): {url}")


def log_reel_nums():
    nums = set()
    try:
        for line in open(os.path.join(HERE, "reels.log")):
            m = re.search(r"POSTED REEL #(\d+)", line)
            if m:
                nums.add(int(m.group(1)))
    except FileNotFoundError:
        pass
    return nums


def main():
    token = os.environ.get("IG_TOKEN", "").strip()
    if not token:
        sys.exit("IG_TOKEN is not set")
    dry = "--dry-run" in sys.argv
    test = "--test-container" in sys.argv
    forced = int(arg("--num")) if arg("--num") else None

    queue = json.load(open(os.path.join(HERE, "queue.json")))
    by_num = {q["num"]: q for q in queue}
    me = call("GET", "me", token, fields="user_id,username")
    uid = me["user_id"]
    print("account:", me["username"])

    recent = call("GET", f"{uid}/media", token, fields="caption,timestamp,media_product_type", limit=50).get("data", [])

    if "--verify" in sys.argv:
        for m in recent:
            if (m.get("caption") or "").startswith("Reel quiz #") or m.get("media_product_type") == "REELS":
                full = call("GET", m["id"], token, fields="media_product_type,permalink,timestamp,caption")
                print(f"{full['timestamp']} {full['media_product_type']} {full.get('permalink')} | {(full.get('caption') or '')[:40]!r}")
        limit = call("GET", f"{uid}/content_publishing_limit", token, fields="quota_usage,config")
        print("publishing limit:", json.dumps(limit.get("data", limit)))
        return

    reel_nums, carousel_nums, last_reel_time = set(), set(), None
    for m in recent:
        cap = m.get("caption") or ""
        r = re.match(r"Reel quiz #(\d+):", cap)
        c = re.match(r"Pop quiz #(\d+):", cap)
        if r:
            reel_nums.add(int(r.group(1)))
            t = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            last_reel_time = max(last_reel_time or t, t)
        if c:
            carousel_nums.add(int(c.group(1)))
    reel_nums |= log_reel_nums()  # reels.log covers Reels older than the 50 most recent media

    if last_reel_time:
        hours = (datetime.now(timezone.utc) - last_reel_time).total_seconds() / 3600
        print(f"last reel posted {hours:.1f}h ago")
        if hours < MIN_GAP_HOURS and not dry and not test:
            print("SKIP: too soon since last reel")
            return

    if forced:
        if forced not in by_num:
            sys.exit(f"Quiz #{forced} is not in queue.json")
        num = forced
    else:
        lowest = min(reel_nums) if reel_nums else None
        cands = sorted((n for n in by_num if (lowest is None or n < lowest) and n not in carousel_nums), reverse=True)
        if not cands:
            print("QUEUE EMPTY: all quizzes have a Reel - time to add more cartoons")
            return
        num = cands[0]
    if num in reel_nums:
        sys.exit(f"Quiz #{num} already has a Reel; refusing to repost")

    item = by_num[num]
    caption = (f"Reel quiz #{num}: what does {item['word'].upper()} mean? \U0001F914\n\n"
               "Pick A, B, C, or D before the countdown ends, then see the cartoon that makes it stick. "
               "Comment your answer \U0001F447\n\n"
               "Want hundreds more? The GRE Vocab Cartoons app is in our bio.\n\n"
               "#GRE #GREvocabulary #GREprep #vocabulary #testprep #reels")
    url = video_url(num)
    print(f"next: Reel #{num} {item['word']} (answer {item['answer']})")
    print("  video:", url)
    if dry:
        print("DRY RUN: nothing rendered or posted")
        return

    import make_short  # needs Pillow + ffmpeg
    out = os.path.join(HERE, f"reel-{num:04d}.mp4")
    make_short.make(num, out)
    size = os.path.getsize(out)
    print(f"rendered {out} ({size} bytes)")
    host_file(out, num)
    wait_for_url(url, size, 180 if os.environ.get("REEL_HOSTING", "raw") == "raw" else 300)

    container = call("POST", f"{uid}/media", token, media_type="REELS", video_url=url, caption=caption,
                     share_to_feed="true", thumb_offset=THUMB_OFFSET_MS)["id"]
    print("container:", container)
    for _ in range(60):  # 10 s x 60 = 10 minutes
        st = call("GET", container, token, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            sys.exit(f"container {container} status: {json.dumps(st)}")
        time.sleep(10)
    else:
        sys.exit(f"container {container} never finished processing (last status {json.dumps(st)})")

    if test:
        print("TEST OK: container finished, NOT published")
        return

    limit = call("GET", f"{uid}/content_publishing_limit", token, fields="quota_usage,config")
    print("publishing limit before:", json.dumps(limit.get("data", limit)))
    pub = call("POST", f"{uid}/media_publish", token, creation_id=container)
    link = call("GET", pub["id"], token, fields="permalink").get("permalink")
    limit = call("GET", f"{uid}/content_publishing_limit", token, fields="quota_usage,config")
    print("publishing limit after:", json.dumps(limit.get("data", limit)))
    print(f"POSTED REEL #{num} {item['word']}: {link}")


if __name__ == "__main__":
    main()
