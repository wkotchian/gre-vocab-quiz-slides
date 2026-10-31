#!/usr/bin/env python3
"""Weekly performance snapshot of the GRE vocab quiz posts. Read-only: it never posts or edits.

Instagram (official API, graph.instagram.com): followers, plus per-post views, reach, likes,
comments, saves, shares and (Reels) average watch time, for posts since START.
YouTube (official Data API): subscribers and channel views, plus per-video views, likes and
comments, for uploads since START.

Env: IG_TOKEN (the live token, from ig_token.py export), YT_CLIENT_ID, YT_CLIENT_SECRET,
YT_REFRESH_TOKEN. A platform whose token is missing or refused is recorded as an error and
the other platform still runs.

Writes: stats/YYYY-MM-DD.json (full snapshot), appends to stats/posts.csv (one row per post
per run) and stats/accounts.csv (one row per platform per run), and prints a short summary.
"""
import csv, json, os, re, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "stats")
START = "2026-10-15"  # the automated posting began on 2026-10-18
IG_API = "https://graph.instagram.com/v23.0"
YT_API = "https://www.googleapis.com/youtube/v3"
EXPECTED_CHANNEL = "Vince Kotchian Test Prep"

FEED_METRICS = ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions"]
REEL_METRICS = FEED_METRICS + ["ig_reels_avg_watch_time"]

POST_COLS = ["date", "platform", "kind", "id", "num", "word", "published", "url",
             "views", "reach", "likes", "comments", "saves", "shares", "interactions",
             "avg_watch_sec", "error"]
ACCOUNT_COLS = ["date", "platform", "followers", "total_views", "media_count", "error"]


class ApiError(Exception):
    pass


def get_json(url, headers=None, secret=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if secret:
            body = body.replace(secret, "<token>")
        raise ApiError(f"{e.code}: {body[:400]}")
    except urllib.error.URLError as e:
        raise ApiError(f"network: {e}")


def log_labels():
    """Map Instagram shortcodes and YouTube video ids to (num, word) from the posting logs."""
    labels = {}
    pat = re.compile(r"#(\d+) (\S+?):?(?: \([a-z]+\):?)? (https?://\S+)")
    for name in ("posted.log", "reels.log", "shorts.log"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            m = pat.search(line)
            if not m:
                continue
            num, word, url = m.group(1), m.group(2).rstrip(":"), m.group(3)
            key = url.rstrip("/").split("/")[-1].split("?")[0]
            labels[key] = (num, word)
    return labels


# ---------------- Instagram ----------------

def ig_call(path, token, **params):
    params["access_token"] = token
    return get_json(f"{IG_API}/{path}?{urllib.parse.urlencode(params)}", secret=token)


def ig_insights(media_id, metrics, token):
    """Ask for all metrics; if the API refuses the set, fall back to one metric at a time."""
    try:
        data = ig_call(f"{media_id}/insights", token, metric=",".join(metrics)).get("data", [])
        return {d["name"]: (d.get("values") or [{}])[0].get("value") for d in data}, ""
    except ApiError as e:
        first_err = str(e)
    out, errs = {}, []
    for m in metrics:
        try:
            data = ig_call(f"{media_id}/insights", token, metric=m).get("data", [])
            for d in data:
                out[d["name"]] = (d.get("values") or [{}])[0].get("value")
        except ApiError as e:
            errs.append(m)
    err = "" if out else first_err
    if out and errs:
        err = "unavailable: " + ",".join(errs)
    return out, err


def instagram(today, labels):
    token = os.environ.get("IG_TOKEN", "").strip()
    if not token:
        return {"error": "IG_TOKEN not set"}, []
    try:
        me = ig_call("me", token, fields="user_id,username,followers_count,media_count")
    except ApiError as e:
        return {"error": f"account: {e}"}, []
    uid = me.get("user_id") or me.get("id")
    acct = {"followers": me.get("followers_count"), "media_count": me.get("media_count"),
            "username": me.get("username"), "error": ""}
    rows, url = [], None
    params = dict(fields="id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count",
                  limit=50)
    try:
        page = ig_call(f"{uid}/media", token, **params)
    except ApiError as e:
        acct["error"] = f"media list: {e}"
        return acct, []
    while True:
        stop = False
        for m in page.get("data", []):
            ts = m.get("timestamp", "")[:10]
            if ts < START:
                stop = True
                break
            reel = m.get("media_product_type") == "REELS"
            kind = "reel" if reel else ("carousel" if m.get("media_type") == "CAROUSEL_ALBUM" else "post")
            ins, err = ig_insights(m["id"], REEL_METRICS if reel else FEED_METRICS, token)
            code = (m.get("permalink") or "").rstrip("/").split("/")[-1]
            num, word = labels.get(code, ("", ""))
            watch = ins.get("ig_reels_avg_watch_time")
            rows.append({
                "date": today, "platform": "instagram", "kind": kind, "id": m["id"], "num": num, "word": word,
                "published": m.get("timestamp", ""), "url": m.get("permalink", ""),
                "views": ins.get("views"), "reach": ins.get("reach"),
                "likes": ins.get("likes", m.get("like_count")),
                "comments": ins.get("comments", m.get("comments_count")),
                "saves": ins.get("saved"), "shares": ins.get("shares"),
                "interactions": ins.get("total_interactions"),
                "avg_watch_sec": round(watch / 1000, 1) if isinstance(watch, (int, float)) else "",
                "error": err})
        nxt = page.get("paging", {}).get("next")
        if stop or not nxt:
            break
        try:
            page = get_json(nxt, secret=token)
        except ApiError as e:
            acct["error"] = f"media page: {e}"
            break
    return acct, rows


# ---------------- YouTube ----------------

def yt_token():
    body = urllib.parse.urlencode({
        "client_id": os.environ["YT_CLIENT_ID"].strip(),
        "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"}).encode()
    return get_json("https://oauth2.googleapis.com/token", data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"})["access_token"]


def youtube(today, labels):
    if not all(os.environ.get(k, "").strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
        return {"error": "YouTube secrets not set"}, []
    try:
        tok = yt_token()
        h = {"Authorization": f"Bearer {tok}"}
        ch = get_json(f"{YT_API}/channels?part=snippet,statistics,contentDetails&mine=true", h, tok)["items"]
    except (ApiError, KeyError) as e:
        return {"error": f"account: {e}"}, []
    if not ch or ch[0]["snippet"]["title"] != EXPECTED_CHANNEL:
        return {"error": f"wrong channel: {[c['snippet']['title'] for c in ch]}"}, []
    st = ch[0]["statistics"]
    acct = {"followers": st.get("subscriberCount"), "total_views": st.get("viewCount"),
            "media_count": st.get("videoCount"), "error": ""}
    uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token_page = [], ""
    try:
        while True:
            q = f"{YT_API}/playlistItems?part=contentDetails&maxResults=50&playlistId={uploads}"
            if token_page:
                q += f"&pageToken={token_page}"
            page = get_json(q, h, tok)
            batch = [(i["contentDetails"]["videoId"], i["contentDetails"].get("videoPublishedAt", ""))
                     for i in page.get("items", [])]
            ids += [v for v, p in batch if p[:10] >= START]
            token_page = page.get("nextPageToken")
            if not token_page or any(p and p[:10] < START for _, p in batch):
                break
    except ApiError as e:
        acct["error"] = f"uploads list: {e}"
        return acct, []
    rows = []
    for i in range(0, len(ids), 50):
        try:
            vids = get_json(f"{YT_API}/videos?part=snippet,statistics,contentDetails&id={','.join(ids[i:i+50])}",
                            h, tok).get("items", [])
        except ApiError as e:
            acct["error"] = f"videos: {e}"
            break
        for v in vids:
            title = v["snippet"]["title"]
            m = re.search(r"quiz #(\d+)", title, re.IGNORECASE)
            num, word = labels.get(v["id"], (m.group(1) if m else "", ""))
            s = v.get("statistics", {})
            rows.append({
                "date": today, "platform": "youtube", "kind": "short" if m else "video", "id": v["id"],
                "num": num, "word": word, "published": v["snippet"].get("publishedAt", ""),
                "url": f"https://youtube.com/shorts/{v['id']}" if m else f"https://youtu.be/{v['id']}",
                "views": s.get("viewCount"), "reach": "", "likes": s.get("likeCount"),
                "comments": s.get("commentCount"), "saves": "", "shares": "", "interactions": "",
                "avg_watch_sec": "", "error": ""})
    return acct, rows


def append_csv(path, cols, rows):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    labels = log_labels()
    ig_acct, ig_rows = instagram(today, labels)
    yt_acct, yt_rows = youtube(today, labels)
    os.makedirs(OUT, exist_ok=True)
    snap = {"date": today, "start": START, "instagram": {"account": ig_acct, "posts": ig_rows},
            "youtube": {"account": yt_acct, "videos": yt_rows}}
    with open(os.path.join(OUT, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
        f.write("\n")
    append_csv(os.path.join(OUT, "posts.csv"), POST_COLS, ig_rows + yt_rows)
    append_csv(os.path.join(OUT, "accounts.csv"), ACCOUNT_COLS, [
        dict(ig_acct, date=today, platform="instagram"), dict(yt_acct, date=today, platform="youtube")])

    ig_err = sum(1 for r in ig_rows if r["error"])
    print(f"STATS {today}: instagram {len(ig_rows)} posts (followers {ig_acct.get('followers')}, "
          f"{ig_err} with insight errors{', account error: ' + ig_acct['error'] if ig_acct.get('error') else ''}); "
          f"youtube {len(yt_rows)} videos (subscribers {yt_acct.get('followers')}"
          f"{', error: ' + yt_acct['error'] if yt_acct.get('error') else ''})")
    if ig_err:
        print("first instagram insight error:", next(r["error"] for r in ig_rows if r["error"])[:300])
    # Fail the run only if both platforms returned nothing, so a partial result is still saved.
    if not ig_rows and not yt_rows and (ig_acct.get("error") or yt_acct.get("error")):
        sys.exit(1)


if __name__ == "__main__":
    main()
