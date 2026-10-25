#!/usr/bin/env python3
"""Render a 16:9 annotated personal statement examples video from ps_videos/<slug>.json.

Slides: Pillow (bundled Inter fonts). Narration: Kokoro TTS (Apache-2.0, runs locally on the runner).
Usage: python3 make_ps_video.py SLUG [--slides-only]
Writes out/<slug>.mp4, out/<slug>-thumb.jpg, out/<slug>-chapters.json, out/frames/*.png
"""
import json, os, re, subprocess, sys, wave
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1920, 1080
M = 150                                    # side margin
BG, BG2 = (36, 18, 92), (24, 10, 66)        # deep purple
INK, MUTED = (255, 255, 255), (196, 186, 235)
YEL, YEL_INK = (255, 194, 14), (40, 20, 90)
FONT = os.path.join(HERE, "fonts", "Inter-{w}.otf")
SR = 24000
VOICE = os.environ.get("PS_VOICE", "af_heart")
PAD = 0.45                                 # silence after each segment (s)


def font(w, s):
    return ImageFont.truetype(FONT.format(w=w), s)


def wrap(d, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def base(label=None):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, H - 90, W, H), fill=BG2)
    d.text((M, H - 62), "vincekotchian.com", font=font("SemiBold", 30), fill=MUTED)
    if label:
        d.text((M, 96), label.upper(), font=font("Bold", 34), fill=YEL)
    return im, d


def fit_lines(d, text, weight, size, maxw, maxh, lh=1.32, minsize=44):
    while True:
        f = font(weight, size)
        lines = wrap(d, text, f, maxw)
        if len(lines) * size * lh <= maxh or size <= minsize:
            return f, lines, int(size * lh)
        size -= 4


def draw_highlighted(d, lines, f, lh, x, y, hl):
    """Draw wrapped lines; words belonging to the highlight phrase get a yellow box."""
    full = " ".join(lines)
    start = full.find(hl) if hl else -1
    end = start + len(hl) if start >= 0 else -1
    off = 0
    for ln in lines:
        a, b = max(start, off), min(end, off + len(ln))
        if start >= 0 and a < b:
            pre, mid, post = ln[:a - off], ln[a - off:b - off], ln[b - off:]
            x1 = x + d.textlength(pre, font=f)
            x2 = x1 + d.textlength(mid, font=f)
            d.rounded_rectangle((x1 - 10, y + 2, x2 + 10, y + lh - 4), radius=10, fill=YEL)
            d.text((x, y), pre, font=f, fill=INK)
            d.text((x1, y), mid, font=f, fill=YEL_INK)
            d.text((x2, y), post, font=f, fill=INK)
        else:
            d.text((x, y), ln, font=f, fill=INK)
        off += len(ln) + 1
        y += lh
    return y


def slide(s):
    t = s["type"]
    if t == "title":
        im, d = base()
        f, lines, lh = fit_lines(d, s["title"], "Black", 112, W - 2 * M, 420)
        y = 300
        for ln in lines:
            d.text((M, y), ln, font=f, fill=INK); y += lh
        d.rectangle((M, y + 30, M + 160, y + 42), fill=YEL)
        d.text((M, y + 80), s["sub"], font=font("SemiBold", 50), fill=MUTED)
        return im
    if t == "section":
        im, d = base()
        d.text((M, 360), s["n"].upper(), font=font("Bold", 60), fill=YEL)
        f, lines, lh = fit_lines(d, s["title"], "Black", 120, W - 2 * M, 360)
        y = 460
        for ln in lines:
            d.text((M, y), ln, font=f, fill=INK); y += lh
        return im
    if t == "quote":
        im, d = base(s.get("label"))
        size = 96 if s.get("big") else 72
        f, lines, lh = fit_lines(d, s["text"], "SemiBold", size, W - 2 * M - 40, 640)
        top = 190 + max(0, (680 - len(lines) * lh) // 2) - (40 if s.get("foot") else 0)
        d.rectangle((M, top + 10, M + 10, top + len(lines) * lh - 10), fill=YEL)
        draw_highlighted(d, lines, f, lh, M + 50, top, s.get("hl"))
        if s.get("foot"):
            d.text((M + 50, top + len(lines) * lh + 50), s["foot"], font=font("Regular", 42), fill=MUTED)
        return im
    if t == "list":
        im, d = base(s.get("label"))
        items = s["items"]
        f = font("SemiBold", 66 if len(items) <= 3 else 60)
        blocks = [wrap(d, it, f, W - 2 * M - 140) for it in items]
        lh = int(f.size * 1.25)
        total = sum(len(b) * lh for b in blocks) + (len(blocks) - 1) * 46
        y = 200 + max(0, (700 - total) // 2)
        for i, b in enumerate(blocks):
            mark = str(i + 1) if s.get("numbered") else ""
            d.ellipse((M, y + 8, M + 76, y + 84), fill=YEL)
            if mark:
                mf = font("Black", 46)
                d.text((M + 38 - d.textlength(mark, font=mf) / 2, y + 16), mark, font=mf, fill=YEL_INK)
            for ln in b:
                d.text((M + 120, y), ln, font=f, fill=INK); y += lh
            y += 46
        return im
    if t == "versus":
        im, d = base(s.get("label"))
        colw = (W - 2 * M - 80) // 2
        for k, (q, note) in enumerate(((s["a"], s["a_note"]), (s["b"], s["b_note"]))):
            x = M + k * (colw + 80)
            d.rounded_rectangle((x, 230, x + colw, 860), radius=28, fill=BG2)
            f, lines, lh = fit_lines(d, q, "SemiBold", 70, colw - 100, 400)
            y = 300
            for ln in lines:
                d.text((x + 50, y), ln, font=f, fill=INK); y += lh
            d.text((x + 50, 760), note, font=font("Bold", 46), fill=YEL if k else MUTED)
        return im
    if t == "end":
        im, d = base()
        for k, (a, b) in enumerate(((s["a"], s["a_sub"]), (s["b"], s["b_sub"]))):
            y = 230 + k * 330
            d.rounded_rectangle((M, y, W - M, y + 270), radius=28, fill=BG2)
            d.rectangle((M, y, M + 16, y + 270), fill=YEL)
            d.text((M + 70, y + 60), a, font=font("Black", 76), fill=INK)
            d.text((M + 70, y + 170), b, font=font("SemiBold", 48), fill=YEL if k else MUTED)
        return im
    raise ValueError(t)


def thumb(lines):
    im = Image.new("RGB", (1280, 720), BG)
    d = ImageDraw.Draw(im)
    d.text((80, 150), lines[0], font=font("Black", 92), fill=INK)
    d.rounded_rectangle((70, 290, 80 + d.textlength(lines[1], font=font("Black", 150)) + 30, 480), radius=24, fill=YEL)
    d.text((95, 300), lines[1], font=font("Black", 150), fill=YEL_INK)
    d.text((80, 540), lines[2], font=font("SemiBold", 60), fill=MUTED)
    return im


def say_text(cfg, s):
    t = " " + s + " "
    for a, b in cfg.get("say_fix", {}).items():
        t = t.replace(a, b)
    return t.strip()


def tts(texts, outdir):
    from kokoro import KPipeline
    import numpy as np, soundfile as sf
    pipe = KPipeline(lang_code="a")
    paths = []
    for i, t in enumerate(texts):
        chunks = [a for _, _, a in pipe(t, voice=VOICE, speed=0.95)]
        audio = np.concatenate([np.asarray(c, dtype="float32") for c in chunks] + [np.zeros(int(SR * PAD), dtype="float32")])
        p = os.path.join(outdir, f"a{i:02d}.wav"); sf.write(p, audio, SR); paths.append(p)
    return paths


def dur(p):
    with wave.open(p) as w:
        return w.getnframes() / w.getframerate()


def main():
    slug = sys.argv[1]
    cfg = json.load(open(os.path.join(HERE, "ps_videos", slug + ".json"), encoding="utf-8"))
    out = os.path.join(HERE, "out"); fr = os.path.join(out, "frames"); os.makedirs(fr, exist_ok=True)
    segs = cfg["segments"]
    for i, s in enumerate(segs):
        slide(s["slide"]).save(os.path.join(fr, f"s{i:02d}.png"))
    thumb(cfg["thumb"]).save(os.path.join(out, slug + "-thumb.jpg"), quality=92)
    if "--slides-only" in sys.argv:
        print("slides written:", len(segs)); return
    wavs = tts([say_text(cfg, s["say"]) for s in segs], out)
    # chapters from cumulative durations
    t, chapters, parts = 0.0, [], []
    for i, (s, a) in enumerate(zip(segs, wavs)):
        if s.get("chapter"):
            chapters.append([int(t), s["chapter"]])
        seg = os.path.join(out, f"v{i:02d}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", os.path.join(fr, f"s{i:02d}.png"), "-i", a,
                        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
                        "-ar", "48000", "-shortest", seg], check=True)
        parts.append(seg); t += dur(a)
    lst = os.path.join(out, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    final = os.path.join(out, slug + ".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", final], check=True)
    json.dump(chapters, open(os.path.join(out, slug + "-chapters.json"), "w"))
    print(f"rendered {final} ({t:.0f}s, {len(chapters)} chapters)")


if __name__ == "__main__":
    main()
