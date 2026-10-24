"""Daily GRE Word Puzzle email feed (RSS) for Mailchimp.

The puzzle lives on https://vincekotchian.com/blog/gre/gre-words-of-the-day/#puzzle (puzzle #1 = 2026-11-16,
visitor's local date). Mailchimp's daily RSS campaign (sent to the GRE audience's "puzzle" tag) reads
docs/puzzle/feed.xml, served by GitHub Pages at
https://wkotchian.github.io/gre-vocab-quiz-slides/puzzle/feed.xml

Each item = one day's puzzle: the picture half of the cartoon (word hidden), part of speech, definition,
the starter letters exactly as the puzzle shows them, a Play button, yesterday's answer with its full
cartoon, and the app line. The feed keeps the last KEEP days; older teaser images are removed.

Run daily (GitHub Actions, daily-puzzle-feed.yml) before Mailchimp's send time.
  python3 puzzle_feed.py                 # today (Pacific date)
  python3 puzzle_feed.py --date 2026-11-20 --out /tmp/x   # test a given date into another folder
"""
import argparse, html, io, json, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCH = date(2026, 11, 16)                      # puzzle #1 (must match LAUNCH in the site's puzzle script)
KEEP = 14                                        # days kept in the feed
PAGES = "https://wkotchian.github.io/gre-vocab-quiz-slides/puzzle"
MEDIA = "https://vincekotchian.com/media/"
PLAY = "https://vincekotchian.com/blog/gre/gre-words-of-the-day/?utm_source=mailchimp&utm_medium=email&utm_campaign=daily_puzzle#puzzle"
IOS = "https://apps.apple.com/us/app/id1527155688?pt=121940396&ct=puzzle-email&mt=8"
ANDROID = ("https://play.google.com/store/apps/details?id=co.thkp.gre_flashcards.pro"
           "&referrer=utm_source%3Dmailchimp%26utm_medium%3Demail%26utm_campaign%3Ddaily_puzzle")
APP_WORDS = "1,359"
PURPLE = "#6a1b9a"


def rnd(x):  # JavaScript Math.round (Python's round() rounds halves to even)
    return int(x + 0.5)


def given_spots(L):  # same as givenSpots() in the site's puzzle script
    G = max(2, rnd(L * 0.4))
    out = []
    for k in range(G):
        i = rnd(k * L / G)
        if i not in out and i < L:
            out.append(i)
    return out


def puzzle(P, n):
    e = P[(n - 1) % len(P)]
    return dict(n=n, w=e["w"].upper(), pos=e["pos"], d=e["d"], u=e["u"])


def teaser(pz, folder):
    """Bottom 45% of the cartoon (the picture, no text), 600 px wide JPEG."""
    path = os.path.join(folder, f"t{pz['n']}.jpg")
    if os.path.exists(path):
        return
    from PIL import Image
    url = MEDIA + pz["u"] + "?width=1200&format=jpg&quality=90"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "vktp-puzzle-feed"}), timeout=60) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    w, h = im.size
    im = im.crop((0, round(h * 0.55), w, h)).resize((600, round(600 * (h * 0.45) / w)), Image.LANCZOS)
    im.save(path, "JPEG", quality=78, optimize=True, progressive=True)


def item_html(pz, prev):
    e = html.escape
    spots = given_spots(len(pz["w"]))
    tiles = "".join(
        f'<td style="width:34px;height:40px;border:2px solid {PURPLE if i in spots else "#cfcfcf"};'
        f'background:{"#ede7f2" if i in spots else "#ffffff"};color:{PURPLE};font:bold 20px Arial,sans-serif;'
        f'text-align:center;border-radius:6px">{e(c) if i in spots else "&nbsp;"}</td>'
        f'<td style="width:4px"></td>'
        for i, c in enumerate(pz["w"]))
    h = (f'<div style="max-width:560px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;color:#222;text-align:center">'
         f'<p style="font-size:14px;color:#555;margin:0 0 10px">Unscramble today\'s GRE word. Some letters are already in place.</p>'
         f'<a href="{e(PLAY)}"><img src="{PAGES}/t{pz["n"]}.jpg" width="560" alt="Cartoon clue for puzzle #{pz["n"]} (the word is hidden)" '
         f'style="width:100%;max-width:560px;height:auto;border-radius:10px;display:block;border:0"></a>'
         f'<p style="font-size:18px;line-height:1.4;margin:14px 0 12px">({e(pz["pos"])}) '
         f'<strong style="color:{PURPLE}">{e(pz["d"])}</strong></p>'
         f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto"><tr>{tiles}</tr></table>'
         f'<p style="font-size:13px;color:#666;margin:8px 0 18px">{len(pz["w"])} letters</p>'
         f'<a href="{e(PLAY)}" style="display:inline-block;background:{PURPLE};color:#ffffff;text-decoration:none;'
         f'font-weight:bold;font-size:17px;padding:13px 28px;border-radius:24px">Play puzzle #{pz["n"]}</a>')
    if prev:
        h += (f'<hr style="border:0;border-top:1px solid #e3e3e3;margin:28px 0 18px">'
              f'<p style="font-size:16px;margin:0 0 10px">Yesterday\'s word: <strong>{e(prev["w"].lower())}</strong> '
              f'({e(prev["pos"])}), {e(prev["d"])}.</p>'
              f'<img src="{MEDIA}{prev["u"]}?width=600&amp;format=jpg&amp;quality=80" width="400" '
              f'alt="{e(prev["w"].lower())} GRE vocabulary cartoon" style="width:100%;max-width:400px;height:auto;border-radius:10px;border:0">')
    h += (f'<p style="font-size:14px;line-height:1.5;color:#444;margin:22px 0 0">Every puzzle word comes from my GRE Vocab '
          f'Cartoons app, which has all {APP_WORDS} cartoons and keeps bringing back the ones you miss until you know them: '
          f'<a href="{e(IOS)}" style="color:{PURPLE}">iPhone</a> or <a href="{e(ANDROID)}" style="color:{PURPLE}">Android</a>.</p>'
          f'</div>')
    return h


def build(today, out):
    P = json.load(open(os.path.join(HERE, "puzzle", "schedule.json"), encoding="utf-8"))
    os.makedirs(out, exist_ok=True)
    n_today = (today - LAUNCH).days + 1
    first = max(1, n_today - KEEP + 1)
    items, keep = [], set()
    days = list(range(n_today, first - 1, -1))       # newest first
    preview = n_today < 1
    if preview:
        # Before launch: one sample item (puzzle #1) dated in the past, so Mailchimp can validate the feed and
        # build the campaign. Mailchimp only sends items published after its last send, so this is never mailed.
        days = [1]
    for n in days:
        pz = puzzle(P, n)
        prev = puzzle(P, n - 1) if n > 1 else None
        teaser(pz, out)
        keep.add(f"t{n}.jpg")
        d = LAUNCH + timedelta(days=n - 1)
        pub = datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)   # 3 am Pacific, before the morning send
        if preview:
            pub = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        L = len(pz["w"])
        art = "an" if L in (8, 11, 18) else "a"
        title = f"GRE Word Puzzle #{n}: {art} {L}-letter {pz['pos']} starting with {pz['w'][0]}"
        body = item_html(pz, prev)
        items.append(
            f"<item><title>{html.escape(title)}</title><link>{html.escape(PLAY)}</link>"
            f"<guid isPermaLink=\"false\">vktp-gre-word-puzzle-{'preview' if preview else n}</guid><pubDate>{format_datetime(pub)}</pubDate>"
            f"<description><![CDATA[{body}]]></description><content:encoded><![CDATA[{body}]]></content:encoded></item>")
    for f in os.listdir(out):                          # drop teasers that left the feed
        if f.startswith("t") and f.endswith(".jpg") and f not in keep:
            os.remove(os.path.join(out, f))
    now = format_datetime(datetime.now(timezone.utc))
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">'
           '<channel><title>GRE Word Puzzle</title>'
           '<link>https://vincekotchian.com/blog/gre/gre-words-of-the-day/#puzzle</link>'
           f'<atom:link href="{PAGES}/feed.xml" rel="self" type="application/rss+xml"/>'
           '<description>One GRE word puzzle a day from Vince Kotchian Test Prep.</description>'
           f'<language>en-us</language><lastBuildDate>{now}</lastBuildDate>{"".join(items)}</channel></rss>\n')
    open(os.path.join(out, "feed.xml"), "w", encoding="utf-8").write(rss)
    print(f"feed: {'PREVIEW (before launch)' if preview else f'puzzle #{n_today}'} ({today}), {len(items)} items")
    return n_today


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: today in Pacific time)")
    ap.add_argument("--out", default=os.path.join(HERE, "docs", "puzzle"))
    a = ap.parse_args()
    today = date.fromisoformat(a.date) if a.date else datetime.now(ZoneInfo("America/Los_Angeles")).date()
    build(today, a.out)
