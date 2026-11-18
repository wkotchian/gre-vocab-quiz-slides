#!/usr/bin/env python3
"""Render a vertical GRE Quant Short/Reel (1080x1920) for one question from math_queue.json.

  0-1s   : question card (question + answer choices)
  1-31s  : same card with a 30..1 "solve it" countdown (soft tick each second) and a pause hint
  31-41s : answer, the short solution, and one trap answer with the mistake behind it (chime)
  41-44s : end card: GRE Math Knight

Questions come from GRE Math Knight 2.0. Key text stays inside the Shorts/Reels safe area
(clear of the right-side buttons and the bottom caption overlay).
Usage: python3 make_math_short.py NUM [out.mp4]      Needs Pillow, matplotlib, ffmpeg.
"""
import json, math, os, re, struct, subprocess, sys, tempfile, wave
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
from matplotlib import mathtext, font_manager  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1080, 1920
SAFE_L, SAFE_R = 110, 970
BLUE, BLUE_DARK, NAVY = (0, 87, 222), (0, 52, 150), (0, 30, 92)
GOLD, WHITE, RED, GREEN = (255, 196, 30), (255, 255, 255), (214, 40, 40), (32, 170, 90)
FONT = os.path.join(HERE, "fonts", "Inter-{w}.otf")
FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ICON = os.path.join(HERE, "math", "knight_icon.png")
SR = 44100
THINK_SECS, ANSWER_SECS, END_SECS = 30, 10, 3
matplotlib.rcParams["mathtext.fontset"] = "dejavusans"


def font(weight, size):
    p = FONT.format(w=weight)
    return ImageFont.truetype(p if os.path.exists(p) else FALLBACK, size)


def is_math(s):
    return bool(re.search(r"\\|\^|_\{", s))


def to_mathtext(s):
    """App LaTeX -> matplotlib mathtext."""
    s = re.sub(r"\\text\{([^}]*)\}", lambda m: r"\mathrm{" + m.group(1).replace(" ", r"\ ") + "}", s)
    s = s.replace(r"\Rightarrow", r"\Rightarrow ").replace(r"\le ", r"\leq ").replace(r"\ge ", r"\geq ")
    s = s.replace(r"\dfrac", r"\frac").replace(r"\left", "").replace(r"\right", "")
    s = s.replace(r"\%", r"\%")
    return s


def math_img(tex, px, color):
    """Render one LaTeX line to a transparent RGBA image (px is roughly the cap-line size)."""
    import io
    fig = Figure(figsize=(0.01, 0.01), dpi=100, facecolor="none")
    FigureCanvasAgg(fig)
    rgb = tuple(c / 255 for c in color)
    fig.text(0, 0, "$" + to_mathtext(tex) + "$", fontsize=px * 0.72, color=rgb)
    b = io.BytesIO()
    fig.savefig(b, dpi=100, transparent=True, bbox_inches="tight", pad_inches=0.06, format="png")
    b.seek(0)
    return Image.open(b).convert("RGBA")


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


class Canvas:
    def __init__(self, bg=BLUE):
        self.im = Image.new("RGB", (W, H), bg)
        self.d = ImageDraw.Draw(self.im)

    def center(self, text, f, y, fill, left=SAFE_L, right=SAFE_R):
        x = left + (right - left - self.d.textlength(text, font=f)) / 2
        self.d.text((x, y), text, font=f, fill=fill)

    def para(self, text, f, y, fill, left=SAFE_L, right=SAFE_R, gap=1.28, center=False):
        for ln in wrap_px(self.d, text, f, right - left):
            if center:
                self.center(ln, f, y, fill, left, right)
            else:
                self.d.text((left, y), ln, font=f, fill=fill)
            y += int(f.size * gap)
        return y

    def math(self, tex, px, y, color, left=SAFE_L, right=SAFE_R, center=True):
        m = math_img(tex, px, color)
        maxw = right - left
        if m.width > maxw:
            m = m.resize((maxw, int(m.height * maxw / m.width)), Image.LANCZOS)
        x = left + (maxw - m.width) // 2 if center else left
        self.im.paste(m, (x, y), m)
        return y + m.height

    def line(self, s, f, px, y, fill, left=SAFE_L, right=SAFE_R, center=False):
        """A stem/solution line: LaTeX lines render as math, plain lines as wrapped text."""
        if is_math(s):
            return self.math(s, px, y, fill, left, right, center=center or True) + 14
        return self.para(s, f, y, fill, left, right, center=center) + 6


def header(c, q):
    c.center(f"GRE QUANT #{q['num']}", font("Black", 54), 120, GOLD)
    c.center(q.get("skill", ""), font("SemiBold", 34), 190, WHITE)
    return 270


def stem(c, q, y):
    f = font("SemiBold", 54)
    if q["kind"] == "qc":
        for g in q["given"]:
            y = c.line(g, f, 70, y, WHITE, center=True)
        y += 10
        colw = (SAFE_R - SAFE_L - 30) // 2
        for i, (lab, val) in enumerate((("Quantity A", q["A"]), ("Quantity B", q["B"]))):
            x0 = SAFE_L + i * (colw + 30)
            c.d.rounded_rectangle((x0, y, x0 + colw, y + 190), radius=22, fill=BLUE_DARK, outline=WHITE, width=3)
            c.center(lab, font("Bold", 38), y + 18, GOLD, x0, x0 + colw)
            if is_math(val) or len(val) < 12:
                c.math(val, 80, y + 78, WHITE, x0 + 10, x0 + colw - 10)
            else:
                c.para(val, font("SemiBold", 36), y + 80, WHITE, x0 + 16, x0 + colw - 16, center=True)
        y += 220
        return y
    for s in q["lines"]:
        y = c.line(s, f, 84, y, WHITE, center=is_math(s))
    return y + 10


def choices(c, q, y, reveal=False):
    letters = "ABCDE"
    f = font("SemiBold", 50 if q["kind"] == "mc" else 42)
    lf = font("Black", 48)
    for i, ch in enumerate(q["choices"]):
        is_ans, is_trap = i == q["answer"], i == q["trap"]
        fill, outline = BLUE_DARK, WHITE
        if reveal and is_ans:
            fill, outline = GREEN, WHITE
        elif reveal and is_trap:
            fill, outline = RED, WHITE
        if q["choice_math"][i]:
            m = math_img(ch, 66, WHITE)
            bh = max(100, m.height + 28)
            c.d.rounded_rectangle((SAFE_L, y, SAFE_R, y + bh), radius=22, fill=fill, outline=outline, width=3)
            c.d.text((SAFE_L + 26, y + (bh - 58) // 2), letters[i], font=lf, fill=GOLD)
            c.im.paste(m, (SAFE_L + 100, y + (bh - m.height) // 2), m)
        else:
            lines = wrap_px(c.d, ch, f, SAFE_R - SAFE_L - 130)[:3]
            bh = 30 + int(f.size * 1.25) * len(lines)
            c.d.rounded_rectangle((SAFE_L, y, SAFE_R, y + bh), radius=22, fill=fill, outline=outline, width=3)
            c.d.text((SAFE_L + 26, y + (bh - 58) // 2), letters[i], font=lf, fill=GOLD)
            for j, ln in enumerate(lines):
                c.d.text((SAFE_L + 100, y + 15 + int(f.size * 1.25) * j), ln, font=f, fill=WHITE)
        y += bh + 16
    return y


BOTTOM = 1580  # keep everything above the Shorts/Reels caption overlay


def question_frame(q, count, top=None):
    c = Canvas()
    header(c, q)
    y = top if top is not None else 300
    y = stem(c, q, y)
    y = choices(c, q, y + 10)
    y += 26
    label = f"Solve it…  {count}" if count else "Solve it…"
    pf = font("Black", 62)
    pw = c.d.textlength(label, font=pf)
    px = SAFE_L + (SAFE_R - SAFE_L - pw) / 2 - 40
    c.d.rounded_rectangle((px, y, px + pw + 80, y + 100), radius=50, fill=GOLD)
    c.d.text((px + 40, y + 14), label, font=pf, fill=NAVY)
    y += 118
    c.center("Need more time? Pause the video.", font("SemiBold", 40), y, WHITE)
    y += 50
    if top is None:
        used = y + 100 - 300
        return question_frame(q, count, top=max(300, 300 + (BOTTOM - 300 - used) // 2))
    return c.im


def answer_frame(q, top=None):
    c = Canvas()
    header(c, q)
    y = top if top is not None else 300
    letters = "ABCDE"
    a, t = q["answer"], q["trap"]
    ans_txt = q["choices"][a]
    c.center("ANSWER", font("Black", 58), y, GOLD); y += 80
    if q["choice_math"][a]:
        m = math_img(ans_txt, 96, WHITE)
        lab = font("Black", 96)
        lw = c.d.textlength(f"({letters[a]})  ", font=lab)
        x = SAFE_L + (SAFE_R - SAFE_L - lw - m.width) // 2
        c.d.text((x, y), f"({letters[a]})", font=lab, fill=WHITE)
        c.im.paste(m, (int(x + lw), y + max(0, (110 - m.height) // 2)), m)
        y += max(120, m.height + 10)
    else:
        y = c.para(f"({letters[a]}) {ans_txt}", font("Black", 62), y, WHITE, center=True)
    y += 30
    c.d.text((SAFE_L, y), "How:", font=font("Bold", 50), fill=GOLD); y += 70
    f = font("SemiBold", 48)
    for kind, s in q["sol"]:
        if kind == "latex" or is_math(s):
            y = c.math(s, 70, y, WHITE) + 18
        else:
            y = c.para(s, f, y, WHITE) + 8
    y += 24
    # trap box
    tf = font("SemiBold", 46)
    note_lines = wrap_px(c.d, q["trap_note"], tf, SAFE_R - SAFE_L - 60)
    bh = 100 + int(tf.size * 1.3) * len(note_lines) + 20
    c.d.rounded_rectangle((SAFE_L, y, SAFE_R, y + bh), radius=26, fill=RED)
    trap_txt = q["choices"][t]
    head = f"Trap: ({letters[t]}) "
    hf = font("Black", 52)
    c.d.text((SAFE_L + 30, y + 22), head, font=hf, fill=WHITE)
    hx = SAFE_L + 30 + c.d.textlength(head, font=hf)
    if q["choice_math"][t]:
        m = math_img(trap_txt, 60, WHITE)
        c.im.paste(m, (int(hx), y + 22 + max(0, (56 - m.height) // 2)), m)
    else:
        if len(trap_txt) < 30:
            sz = 52
            while sz > 30 and hx + c.d.textlength(trap_txt, font=font("Black", sz)) > SAFE_R - 20:
                sz -= 2
            c.d.text((hx, y + 22 + (52 - sz) // 2), trap_txt, font=font("Black", sz), fill=WHITE)
    yy = y + 100
    for ln in note_lines:
        c.d.text((SAFE_L + 30, yy), ln, font=tf, fill=WHITE); yy += int(tf.size * 1.3)
    if top is None:
        used = y + bh - 300
        return answer_frame(q, top=max(300, 300 + (BOTTOM - 300 - used) // 2))
    return c.im


def end_frame():
    c = Canvas(NAVY)
    if os.path.exists(ICON):
        ic = Image.open(ICON).convert("RGB").resize((420, 420), Image.LANCZOS)
        mask = Image.new("L", ic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 420, 420), radius=90, fill=255)
        c.im.paste(ic, ((W - 420) // 2, 360), mask)
    c.center("GRE Math Knight", font("Black", 88), 840, WHITE)
    c.center("More GRE Quant questions like this,", font("SemiBold", 46), 980, GOLD)
    c.center("with the mistake behind each wrong answer.", font("SemiBold", 46), 1045, GOLD)
    c.center("On the App Store", font("Bold", 52), 1180, WHITE)
    return c.im


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
        mix(tone(1200, 0.05, 0.20, 70), 1 + k)
    for fr, dl in ((880, 0), (1320, 0.09), (1760, 0.18)):
        mix(tone(fr, 0.9, 0.25, 4), q_secs + dl)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in buf))


def get(num):
    return next(x for x in json.load(open(os.path.join(HERE, "math_queue.json"))) if x["num"] == num)


def make(num, out, stills=None):
    q = get(num)
    tmp = tempfile.mkdtemp()
    frames = [(question_frame(q, 0), 1)]
    for n in range(THINK_SECS, 0, -1):
        frames.append((question_frame(q, n), 1))
    frames.append((answer_frame(q), ANSWER_SECS))
    frames.append((end_frame(), END_SECS))
    if stills:
        frames[1][0].save(stills + "-q.png"); frames[-2][0].save(stills + "-a.png"); frames[-1][0].save(stills + "-end.png")
    q_secs = 1 + THINK_SECS
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fl:
        for i, (im, dur) in enumerate(frames):
            p = os.path.join(tmp, f"f{i:02d}.png"); im.save(p)
            fl.write(f"file '{p}'\nduration {dur}\n")
        fl.write(f"file '{p}'\n")
    wav = os.path.join(tmp, "a.wav")
    audio(wav, q_secs, q_secs + ANSWER_SECS + END_SECS)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    return q


if __name__ == "__main__":
    num = int(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else f"math-short-{num}.mp4"
    q = make(num, out, stills=os.environ.get("STILLS"))
    print(f"rendered GRE Quant #{num} {q['id']} -> {out}")
