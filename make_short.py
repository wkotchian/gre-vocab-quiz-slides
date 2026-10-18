#!/usr/bin/env python3
"""Render a vertical YouTube Short (1080x1920) for one quiz, laid out for phone legibility.

  0-1s  : title card (word + question + options)
  1-9s  : same card with an 8..1 "think" countdown (soft tick each second)
  9-16s : answer: big "ANSWER: X" + definition in large type, then the full cartoon (chime)

All key text stays inside YouTube Shorts' safe area (clear of the right-side buttons and the
bottom title/channel overlay). Usage: python3 make_short.py NUM [out.mp4]
Needs Pillow + ffmpeg. Audio is synthesized here (no third-party music).
"""
import json, math, os, struct, subprocess, sys, tempfile, textwrap, wave
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
SAFE_L, SAFE_R = 120, 960          # centered on the 1080 frame; right edge stays clear of the Shorts buttons
PURPLE, PURPLE_DARK = (89, 0, 204), (52, 0, 125)
YELLOW, WHITE = (255, 194, 14), (255, 255, 255)
FONT = os.path.join(HERE, "fonts", "Inter-{w}.otf")  # bundled (SIL Open Font License)
FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SR = 44100
THINK_SECS, ANSWER_SECS = 8, 7


def font(weight, size):
    p = FONT.format(w=weight)
    return ImageFont.truetype(p if os.path.exists(p) else FALLBACK, size)


def fit(d, text, weight, size, maxw, minsize=40):
    while size > minsize and d.textlength(text, font=font(weight, size)) > maxw:
        size -= 4
    return font(weight, size)


def center_x(d, text, f, y, fill, left=SAFE_L, right=SAFE_R):
    x = left + (right - left - d.textlength(text, font=f)) / 2
    d.text((x, y), text, font=f, fill=fill)


def wrap_px(d, text, f, maxw):
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


def teaser(q, height):
    """Text-free bottom of the cartoon (rows from 55% down), full width."""
    a = Image.open(os.path.join(HERE, q["slides"][1])).convert("RGB")
    crop = a.crop((0, int(1350 * 0.55), W, 1350))
    return crop.crop((0, 0, W, min(height, crop.height)))


def question_frame(q, count):
    im = Image.new("RGB", (W, H), PURPLE)
    d = ImageDraw.Draw(im)
    y = 150
    center_x(d, f"GRE POP QUIZ #{q['num']}", font("Bold", 50), y, YELLOW); y += 80
    wf = fit(d, q["word"].upper(), "Black", 150, SAFE_R - SAFE_L)
    center_x(d, q["word"].upper(), wf, y, WHITE); y += wf.size + 25
    sub = f"({q['pos']})  “{q['pron']}”" if q.get("pron") else f"({q['pos']})"
    center_x(d, sub, fit(d, sub, "Regular", 46, SAFE_R - SAFE_L, 30), y, WHITE); y += 85
    center_x(d, "What does it mean?", font("Bold", 58), y, YELLOW); y += 105
    of, lf = font("SemiBold", 50), font("Black", 54)
    for i, opt in enumerate(q["options"]):
        lines = wrap_px(d, opt, of, SAFE_R - SAFE_L - 120)[:3]
        bh = 36 + 62 * len(lines)
        d.rounded_rectangle((SAFE_L, y, SAFE_R, y + bh), radius=26, fill=PURPLE_DARK, outline=WHITE, width=4)
        d.text((SAFE_L + 28, y + 20), "ABCD"[i], font=lf, fill=YELLOW)
        for j, ln in enumerate(lines):
            d.text((SAFE_L + 100, y + 22 + 62 * j), ln, font=of, fill=WHITE)
        y += bh + 22
    # countdown pill
    y += 18
    label = f"Think…  {count}" if count else "Think about it…"
    pf = font("Black", 64)
    pw = d.textlength(label, font=pf)
    px = SAFE_L + (SAFE_R - SAFE_L - pw) / 2 - 40
    d.rounded_rectangle((px, y, px + pw + 80, y + 100), radius=50, fill=YELLOW)
    d.text((px + 40, y + 14), label, font=pf, fill=PURPLE_DARK)
    y += 130
    t = teaser(q, H - y)
    im.paste(t, (0, H - t.height))
    return im


def answer_frame(q):
    """Reveal = just the flashcard, as big as the screen allows (full width, 1080x1350).
    Placed high so the card's own text block sits above YouTube's button column."""
    im = Image.new("RGB", (W, H), PURPLE)
    a = Image.open(os.path.join(HERE, q["slides"][1])).convert("RGB").resize((W, 1350), Image.LANCZOS)
    im.paste(a, (0, 170))
    return im


def tone(freq, dur, vol, decay):
    return [vol * math.exp(-decay * i / SR) * math.sin(2 * math.pi * freq * i / SR) for i in range(int(SR * dur))]


def audio(path, q_secs, total):
    buf = [0.0] * int(SR * total)
    def mix(s, at):
        o = int(SR * at)
        for i, v in enumerate(s):
            if o + i < len(buf):
                buf[o + i] += v
    for k in range(THINK_SECS):
        mix(tone(1200, 0.05, 0.22, 70), 1 + k)
    for fr, dl in ((880, 0), (1320, 0.09), (1760, 0.18)):
        mix(tone(fr, 0.9, 0.25, 4), q_secs + dl)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in buf))


def make(num, out):
    q = next(x for x in json.load(open(os.path.join(HERE, "queue.json"))) if x["num"] == num)
    tmp = tempfile.mkdtemp()
    frames = [(question_frame(q, 0), 1)]
    for n in range(THINK_SECS, 0, -1):
        frames.append((question_frame(q, n), 1))
    frames.append((answer_frame(q), ANSWER_SECS))
    q_secs = 1 + THINK_SECS
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fl:
        for i, (im, dur) in enumerate(frames):
            p = os.path.join(tmp, f"f{i:02d}.png"); im.save(p)
            fl.write(f"file '{p}'\nduration {dur}\n")
        fl.write(f"file '{p}'\n")
    wav = os.path.join(tmp, "a.wav")
    audio(wav, q_secs, q_secs + ANSWER_SECS)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    return q


if __name__ == "__main__":
    num = int(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else f"short-{num}.mp4"
    q = make(num, out)
    print(f"rendered #{num} {q['word']} -> {out}")
