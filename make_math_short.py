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
APPS = {
    "gre": {"queue": "math_queue.json", "label": "GRE QUANT", "name": "GRE Math Knight",
            "icon": "math/knight_icon.png", "bg": (0, 87, 222), "dark": (0, 52, 150), "end": (0, 30, 92),
            "tag1": "More GRE Quant questions like this,"},
    "sat": {"queue": "sat_queue.json", "label": "SAT MATH", "name": "SAT Math Swordsman",
            "icon": "math/sat_icon.png", "bg": (84, 36, 160), "dark": (52, 18, 110), "end": (34, 10, 74),
            "tag1": "More SAT math questions like this,"},
}
APP = APPS["gre"]
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
    s = s.replace(r"\Rightarrow", r"\Rightarrow ")
    s = re.sub(r"\\le(?![a-zA-Z])", r"\\leq ", s)
    s = re.sub(r"\\ge(?![a-zA-Z])", r"\\geq ", s)
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


def rich_spans(s):
    """Split app rich text into ("text"|"math", str) spans; \\$ is a literal dollar sign, not a delimiter."""
    spans, buf, in_math, k = [], "", False, 0
    while k < len(s):
        ch = s[k]
        if ch == "\\" and k + 1 < len(s) and s[k + 1] == "$":
            buf += "\\$"; k += 2; continue
        if ch == "$":
            if buf:
                spans.append(("math" if in_math else "text", buf))
            buf, in_math = "", not in_math
            k += 1; continue
        buf += ch; k += 1
    if buf:
        spans.append(("math" if in_math else "text", buf))
    return spans


def rich_tokens(s):
    """Words, with each $...$ math span kept whole (never broken across lines); punctuation stays glued."""
    out, glue = [], False
    for kind, part in rich_spans(s):
        if kind == "math":
            tok = "$" + part + "$"
            if out and glue:
                out[-1] += tok
            else:
                out.append(tok)
            glue = True
        else:
            pieces = re.split(r"(\s+)", part)
            for w in pieces:
                if not w:
                    continue
                if w.isspace():
                    glue = False
                    continue
                if out and glue:
                    out[-1] += w
                else:
                    out.append(w)
                glue = True
    return out


def rich_to_mathtext(s):
    """Rich text -> matplotlib string. \\text{...} inside math becomes plain text (keeps hyphens as hyphens)."""
    out = ""
    for kind, part in rich_spans(s):
        if kind == "text":
            out += part
            continue
        # split top-level \\text{...} out as plain text; nested ones (e.g. inside \\frac) stay as math
        segs, depth, k, cur = [], 0, 0, ""
        while k < len(part):
            if part.startswith("\\text{", k) and depth == 0:
                e = part.index("}", k)
                segs.append(("m", cur)); segs.append(("t", part[k + 6:e])); cur = ""; k = e + 1; continue
            depth += part[k] == "{"
            depth -= part[k] == "}"
            cur += part[k]; k += 1
        segs.append(("m", cur))
        for kind2, b in segs:
            if kind2 == "t":
                out += b.replace("$", "\\$")
            elif b.strip():
                out += "$" + to_mathtext(b) + "$"
            else:
                out += b
    return out


TEXT_FP = None


def text_fp():
    global TEXT_FP
    if TEXT_FP is None:
        from matplotlib.font_manager import FontProperties
        p = FONT.format(w="SemiBold")
        TEXT_FP = FontProperties(fname=p) if os.path.exists(p) else FontProperties(family="DejaVu Sans")
    return TEXT_FP


def rich_line_img(s, px, color):
    import io
    fig = Figure(figsize=(0.01, 0.01), dpi=100, facecolor="none")
    FigureCanvasAgg(fig)
    fp = text_fp().copy()
    fp.set_size(px * 0.72)
    fig.text(0, 0, rich_to_mathtext(s), color=tuple(c / 255 for c in color), fontproperties=fp)
    b = io.BytesIO()
    fig.savefig(b, dpi=100, transparent=True, bbox_inches="tight", pad_inches=0.06, format="png")
    b.seek(0)
    return Image.open(b).convert("RGBA")


def rich_imgs(s, px, color, maxw):
    """Wrap a rich line (words plus $math$) to maxw; returns one image per line."""
    toks, lines, cur = rich_tokens(s), [], ""
    for t in toks:
        cand = (cur + " " + t).strip()
        if cur and rich_line_img(cand, px, color).width > maxw:
            lines.append(cur); cur = t
        else:
            cur = cand
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        im = rich_line_img(ln, px, color)
        if im.width > maxw:
            im = im.resize((maxw, int(im.height * maxw / im.width)), Image.LANCZOS)
        out.append(im)
    return out


class Canvas:
    def __init__(self, bg=None):
        bg = bg or APP["bg"]
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

    def rich(self, s, px, y, color, left=SAFE_L, right=SAFE_R, center=False, gap=6):
        for im in rich_imgs(s, px, color, right - left):
            x = left + (right - left - im.width) // 2 if center else left
            self.im.paste(im, (x, y), im)
            y += im.height + gap
        return y

    def line(self, s, f, px, y, fill, left=SAFE_L, right=SAFE_R, center=False):
        """A stem/solution line: rich lines ($math$ inside words), pure LaTeX lines, or plain text."""
        if "$" in s:
            only_math = s.strip().startswith("$") and s.strip().endswith("$") and s.count("$") == 2
            if only_math:
                return self.math(s.strip()[1:-1], px, y, fill, left, right, center=True) + 14
            return self.rich(s, int(px * 0.8), y, fill, left, right, center=center) + 8
        if is_math(s):
            return self.math(s, px, y, fill, left, right, center=center or True) + 14
        return self.para(s, f, y, fill, left, right, center=center) + 6


def header(c, q):
    c.center(f"{APP['label']} #{q['num']}", font("Black", 54), 120, GOLD)
    sk, sf = q.get("skill", ""), font("SemiBold", 34)
    while c.d.textlength(sk, font=sf) > SAFE_R - SAFE_L and sf.size > 22:
        sf = font("SemiBold", sf.size - 2)
    c.center(sk, sf, 190, WHITE)
    return 270


def stem(c, q, y, k=1.0):
    f = font("SemiBold", int(54 * k))
    if q["kind"] == "qc":
        for g in q["given"]:
            y = c.line(g, f, int(70 * k), y, WHITE, center=True)
        y += 10
        colw = (SAFE_R - SAFE_L - 30) // 2
        for i, (lab, val) in enumerate((("Quantity A", q["A"]), ("Quantity B", q["B"]))):
            x0 = SAFE_L + i * (colw + 30)
            c.d.rounded_rectangle((x0, y, x0 + colw, y + 190), radius=22, fill=APP["dark"], outline=WHITE, width=3)
            c.center(lab, font("Bold", 38), y + 18, GOLD, x0, x0 + colw)
            if is_math(val) or len(val) < 12:
                c.math(val, 80, y + 78, WHITE, x0 + 10, x0 + colw - 10)
            else:
                c.para(val, font("SemiBold", 36), y + 80, WHITE, x0 + 16, x0 + colw - 16, center=True)
        y += 220
        return y
    for s in q["lines"]:
        y = c.line(s, f, int(84 * k), y, WHITE, center=is_math(s) and "$" not in s)
    return y + 10


def choice_img(ch, px, color=WHITE):
    if "$" in ch:
        t = ch.strip()
        if t.startswith("$") and t.endswith("$") and t.count("$") == 2:
            return math_img(t[1:-1], px, color)
        return rich_line_img(ch, int(px * 0.8), color)
    return math_img(ch, px, color)


def choices(c, q, y, reveal=False):
    letters = "ABCDE"
    f = font("SemiBold", 50 if q["kind"] == "mc" else 42)
    lf = font("Black", 48)
    for i, ch in enumerate(q["choices"]):
        is_ans, is_trap = i == q["answer"], i == q["trap"]
        fill, outline = APP["dark"], WHITE
        if reveal and is_ans:
            fill, outline = GREEN, WHITE
        elif reveal and is_trap:
            fill, outline = RED, WHITE
        if "$" in ch or q.get("choice_math", [False] * 5)[i]:
            m = choice_img(ch, 66)
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


def question_frame(q, count, top=None, k=1.0):
    c = Canvas()
    header(c, q)
    y = top if top is not None else 300
    y = stem(c, q, y, k)
    y = choices(c, q, y + 10)
    y += 26
    label = f"Solve it…  {count}" if count else "Solve it…"
    pf = font("Black", 62)
    pw = c.d.textlength(label, font=pf)
    px = SAFE_L + (SAFE_R - SAFE_L - pw) / 2 - 40
    c.d.rounded_rectangle((px, y, px + pw + 80, y + 100), radius=50, fill=GOLD)
    c.d.text((px + 40, y + 14), label, font=pf, fill=APP["end"])
    y += 118
    c.center("Need more time? Pause the video.", font("SemiBold", 40), y, WHITE)
    y += 50
    if top is None:
        used = y + 100 - 300
        if 300 + used > BOTTOM and k > 0.65:
            return question_frame(q, count, None, round(k - 0.08, 2))
        return question_frame(q, count, top=max(300, 300 + (BOTTOM - 300 - used) // 2), k=k)
    return c.im


def answer_frame(q, top=None, k=1.0):
    c = Canvas()
    header(c, q)
    y = top if top is not None else 300
    letters = "ABCDE"
    a, t = q["answer"], q["trap"]
    ans_txt = q["choices"][a]
    c.center("ANSWER", font("Black", 58), y, GOLD); y += 80
    is_m = lambda i: "$" in q["choices"][i] or q.get("choice_math", [False] * 5)[i]
    if is_m(a):
        m = choice_img(ans_txt, 96)
        lab = font("Black", 96)
        lw = c.d.textlength(f"({letters[a]})  ", font=lab)
        room = SAFE_R - SAFE_L - lw
        if m.width > room:
            m = m.resize((int(room), int(m.height * room / m.width)), Image.LANCZOS)
        x = SAFE_L + (SAFE_R - SAFE_L - lw - m.width) // 2
        c.d.text((x, y), f"({letters[a]})", font=lab, fill=WHITE)
        c.im.paste(m, (int(x + lw), y + max(0, (110 - m.height) // 2)), m)
        y += max(120, m.height + 10)
    else:
        y = c.para(f"({letters[a]}) {ans_txt}", font("Black", 62), y, WHITE, center=True)
    y += 30
    c.d.text((SAFE_L, y), "How:", font=font("Bold", 50), fill=GOLD); y += 70
    f = font("SemiBold", int(48 * k))
    for kind, s in q["sol"]:
        if "$" in s:
            y = c.line(s, f, int(70 * k), y, WHITE) + 4
        elif kind == "latex" or is_math(s):
            y = c.math(s, int(70 * k), y, WHITE) + 18
        else:
            y = c.para(s, f, y, WHITE) + 8
    y += 24
    # trap box
    tf = font("SemiBold", 46)
    if "$" in q["trap_note"]:
        note_imgs = rich_imgs(q["trap_note"], 44, WHITE, SAFE_R - SAFE_L - 60)
        note_lines = []
        bh = 100 + sum(im.height + 4 for im in note_imgs) + 20
    else:
        note_imgs = []
        note_lines = wrap_px(c.d, q["trap_note"], tf, SAFE_R - SAFE_L - 60)
        bh = 100 + int(tf.size * 1.3) * len(note_lines) + 20
    c.d.rounded_rectangle((SAFE_L, y, SAFE_R, y + bh), radius=26, fill=RED)
    trap_txt = q["choices"][t]
    head = f"Trap: ({letters[t]}) "
    hf = font("Black", 52)
    c.d.text((SAFE_L + 30, y + 22), head, font=hf, fill=WHITE)
    hx = SAFE_L + 30 + c.d.textlength(head, font=hf)
    if is_m(t):
        m = choice_img(trap_txt, 60)
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
    for im in note_imgs:
        c.im.paste(im, (SAFE_L + 24, yy), im); yy += im.height + 4
    if top is None:
        used = y + bh - 300
        if 300 + used > BOTTOM and k > 0.65:
            return answer_frame(q, None, round(k - 0.08, 2))
        return answer_frame(q, top=max(300, 300 + (BOTTOM - 300 - used) // 2), k=k)
    return c.im


def end_frame():
    c = Canvas(APP["end"])
    icon = os.path.join(HERE, APP["icon"])
    if os.path.exists(icon):
        ic = Image.open(icon).convert("RGB").resize((420, 420), Image.LANCZOS)
        mask = Image.new("L", ic.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 420, 420), radius=90, fill=255)
        c.im.paste(ic, ((W - 420) // 2, 360), mask)
    nf = font("Black", 88)
    while c.d.textlength(APP["name"], font=nf) > SAFE_R - SAFE_L:
        nf = font("Black", nf.size - 4)
    c.center(APP["name"], nf, 840, WHITE)
    c.center(APP["tag1"], font("SemiBold", 46), 980, GOLD)
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


def use_app(app):
    global APP
    APP = APPS[app]


def get(num):
    return next(x for x in json.load(open(os.path.join(HERE, APP["queue"]))) if x["num"] == num)


def make(num, out, stills=None, app="gre"):
    use_app(app)
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
    app = os.environ.get("APP", "gre")
    q = make(num, out, stills=os.environ.get("STILLS"), app=app)
    print(f"rendered {APPS[app]['label']} #{num} {q['id']} -> {out}")
