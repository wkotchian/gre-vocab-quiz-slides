#!/usr/bin/env python3
"""Upload out/<slug>.mp4 (from make_ps_video.py) to the Vince Kotchian Test Prep channel via the YouTube Data API.

Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. Usage: python3 upload_ps_video.py SLUG [--privacy unlisted|private|public]
Refuses to upload the same slug twice (checks ps_videos.log), and refuses if the authorized channel is wrong.
"""
import json, os, sys, urllib.request
from upload_short import http, access_token, API, EXPECTED_CHANNEL, arg

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = "https://vincekotchian.com/personal-statements/personal-statement-checker/"


def ts(s):
    return f"{s // 60}:{s % 60:02d}"


def main():
    slug = sys.argv[1]
    privacy = arg("--privacy", "unlisted")
    cfg = json.load(open(os.path.join(HERE, "ps_videos", slug + ".json"), encoding="utf-8"))
    log = os.path.join(HERE, "ps_videos.log")
    if os.path.exists(log) and any(l.split()[1:2] == [slug] for l in open(log) if l.strip()) and "--again" not in sys.argv:
        sys.exit(f"{slug} already uploaded (see ps_videos.log); pass --again to upload a new version")
    chapters = json.load(open(os.path.join(HERE, "out", slug + "-chapters.json")))
    desc = (cfg["intro"] + "\n\nAll the examples, with notes on each one: " + cfg["page"] + "\n\n"
            + "\n".join(f"{ts(t)} {name}" for t, name in chapters) + "\n\n"
            "We wrote these examples as teaching models. The applicants are invented, and nothing here is a real client's statement. "
            "The narration is AI-generated.\n\n" + cfg["lead"] + "\n\n"
            "Check your draft's length, opening line, and stock phrases with our free personal statement checker: " + CHECKER)
    tok = access_token()
    ch = http("GET", f"{API}/channels?part=snippet&mine=true", tok)["items"]
    if not ch or ch[0]["snippet"]["title"] != EXPECTED_CHANNEL:
        sys.exit(f"Wrong channel authorized: {[c['snippet']['title'] for c in ch]}")
    meta = {"snippet": {"title": cfg["title"][:100], "description": desc[:4900], "categoryId": "27", "tags": cfg["tags"]},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    path = os.path.join(HERE, "out", slug + ".mp4"); size = os.path.getsize(path)
    r = http("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status", tok,
             data=json.dumps(meta).encode(), raw=True,
             headers={"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "video/mp4",
                      "X-Upload-Content-Length": str(size)})
    with open(path, "rb") as f:
        v = http("PUT", r.headers["Location"], tok, data=f.read(), headers={"Content-Type": "video/mp4", "Content-Length": str(size)})
    print(f"UPLOADED {slug} ({privacy}): https://youtu.be/{v['id']}")
    # custom thumbnail: needs a verified channel; never fails the run
    try:
        th = open(os.path.join(HERE, "out", slug + "-thumb.jpg"), "rb").read()
        req = urllib.request.Request(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={v['id']}", data=th,
                                     method="POST", headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"})
        urllib.request.urlopen(req, timeout=60); print("THUMBNAIL set")
    except Exception as e:  # noqa: BLE001
        print("THUMBNAIL not set:", getattr(e, "code", ""), (e.read().decode(errors="replace")[:200] if hasattr(e, "read") else str(e)))


if __name__ == "__main__":
    main()
