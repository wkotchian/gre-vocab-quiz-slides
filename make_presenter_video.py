#!/usr/bin/env python3
"""Build the presenter version of a personal statement examples video.

Input: ps_videos/<slug>.json (segments with slides and narration) and a HeyGen clip of the presenter
reading every segment's narration in order. The clip's audio runs the whole time. Whisper word timings
locate each segment in the clip; the presenter is on screen only for short bursts listed in
cfg["presenter"] ({segment index: max seconds}); slides fill the rest.
Usage: python3 make_presenter_video.py SLUG CLIP.mp4
Writes out/<slug>.mp4, out/<slug>-thumb.jpg, out/<slug>-chapters.json, out/<slug>-shots.json
"""
import difflib, json, os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw
import make_ps_video as mv

W, H = 1920, 1080


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def duration(p):
    err = subprocess.run(["ffmpeg", "-i", p], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def norm(w):
    w = w.lower().replace("’", "'")
    w = re.sub(r"[^a-z0-9']", "", w)
    return {"4500": "4500", "one": "1", "two": "2", "three": "3", "four": "4", "six": "6", "ten": "10"}.get(w, w)


def words_of(text):
    return [n for n in (norm(x) for x in re.split(r"[\s\-]+", text.replace(",", ""))) if n]


def transcribe(wav):
    if os.environ.get("FAKE_ALIGN"):   # local test: spread the script evenly over the clip
        cfg = json.load(open(os.path.join(mv.HERE, "ps_videos", os.environ["FAKE_ALIGN"] + ".json")))
        ws = [w for s in cfg["segments"] for w in words_of(s["say"])]
        tot = duration(wav); step = tot / len(ws)
        return [(w, k * step, (k + 1) * step) for k, w in enumerate(ws)]
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(wav, word_timestamps=True, vad_filter=False, beam_size=5)
    out = []
    for s in segs:
        for w in s.words:
            for piece in re.split(r"[\s\-]+", w.word.replace(",", "")):
                n = norm(piece)
                if n:
                    out.append((n, w.start, w.end))
    return out


def segment_starts(cfg, heard, total):
    script, owner = [], []
    for i, s in enumerate(cfg["segments"]):
        ws = words_of(s["say"])
        script += ws; owner += [i] * len(ws)
    sm = difflib.SequenceMatcher(None, script, [h[0] for h in heard], autojunk=False)
    t_of = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            t_of[a + k] = heard[b + k][1]
    n = len(cfg["segments"])
    starts = []
    for i in range(n):
        idx = [k for k in range(len(script)) if owner[k] == i]
        first = idx[0]
        hit = next(((k, t_of[k]) for k in idx if k in t_of), None)
        if hit is None:
            starts.append(None); continue
        k, t = hit
        starts.append(max(0.0, t - 0.33 * (k - first)))   # back up ~0.33 s per unmatched leading word
    # fill gaps by interpolation, force order
    starts[0] = 0.0
    for i in range(1, n):
        if starts[i] is None:
            nxt = next((j for j in range(i + 1, n) if starts[j] is not None), None)
            starts[i] = starts[i - 1] + ((starts[nxt] - starts[i - 1]) / (nxt - i + 1) if nxt else 3.0)
        starts[i] = max(starts[i], starts[i - 1] + 0.5)
    # cut a little before the first word of each segment, in the breath
    starts = [0.0] + [max(starts[i - 1] + 0.5, s - 0.12) for i, s in enumerate(starts) if i > 0]
    matched = sum(1 for k in range(len(script)) if k in t_of) / len(script)
    return starts, matched


def avatar_filter(clip, tmp):
    p = os.path.join(tmp, "probe.png")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", clip, "-frames:v", "1", p])
    im = Image.open(p).convert("L"); w, h = im.size; px = im.load()
    white = lambda x: all(px[x, y] > 245 for y in range(0, h, max(1, h // 40)))
    left = next((x for x in range(w) if not white(x)), 0)
    right = next((x for x in range(w - 1, -1, -1) if not white(x)), w - 1)
    cw = right - left + 1
    if cw / h < 1.2:   # portrait or padded portrait: sharp centre column on a blurred fill
        return (f"crop={cw}:{h}:{left}:0,split[fg0][bg0];"
                f"[bg0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.10[bg1];"
                f"[fg0]scale=-2:{H}[fg1];[bg1][fg1]overlay=(W-w)/2:0,setsar=1,fps=30"), (left, cw, w, h)
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30", (left, cw, w, h)


def lower_third(text_top, text_main, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f1, f2 = mv.font("Bold", 34), mv.font("Black", 64)
    wbox = max(d.textlength(text_top.upper(), font=f1), d.textlength(text_main, font=f2)) + 100
    y = H - 300
    d.rounded_rectangle((90, y, 90 + wbox, y + 170), radius=24, fill=(24, 10, 66, 235))
    d.rectangle((90, y, 104, y + 170), fill=mv.YEL)
    d.text((140, y + 26), text_top.upper(), font=f1, fill=mv.YEL)
    d.text((140, y + 70), text_main, font=f2, fill=mv.INK)
    im.save(path)


def thumbnail(clip, box, lines, path, tmp):
    p = os.path.join(tmp, "thumbsrc.png")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "2.5", "-i", clip, "-frames:v", "1", p])
    left, cw, w, h = box
    face = Image.open(p).convert("RGB").crop((left, 0, left + cw, h))
    face = face.resize((int(cw * 720 / h), 720))
    im = Image.new("RGB", (1280, 720), mv.BG)
    im.paste(face, (1280 - face.width, 0))
    d = ImageDraw.Draw(im)
    tw = 1280 - face.width - 60
    f1 = mv.font("Black", 70)
    while d.textlength(lines[0], font=f1) > tw and f1.size > 40:
        f1 = mv.font("Black", f1.size - 4)
    d.text((50, 170), lines[0], font=f1, fill=mv.INK)
    f2 = mv.font("Black", 118)
    while d.textlength(lines[1], font=f2) > tw - 20 and f2.size > 60:
        f2 = mv.font("Black", f2.size - 6)
    bw = d.textlength(lines[1], font=f2)
    d.rounded_rectangle((40, 280, 70 + bw, 280 + f2.size + 40), radius=22, fill=mv.YEL)
    d.text((55, 290), lines[1], font=f2, fill=mv.YEL_INK)
    d.text((50, 470), lines[2], font=mv.font("SemiBold", 52), fill=mv.MUTED)
    im.save(path, quality=92)


def main():
    slug, clip = sys.argv[1], sys.argv[2]
    cfg = json.load(open(os.path.join(mv.HERE, "ps_videos", slug + ".json"), encoding="utf-8"))
    out = os.path.join(mv.HERE, "out"); os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    total = duration(clip)
    wav = os.path.join(tmp, "a.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-ac", "1", "-ar", "16000", wav])
    starts, matched = segment_starts(cfg, transcribe(wav), total)
    print(f"total {total:.1f}s, script words matched {matched:.0%}")
    if matched < 0.6:
        sys.exit("alignment too weak; refusing to cut")
    ends = starts[1:] + [total]
    pres = {int(k): v for k, v in cfg["presenter"].items()}
    afilt, box = avatar_filter(clip, tmp)

    starts = [round(t * 30) / 30 for t in starts]; ends = starts[1:] + [total]   # frame-aligned cuts keep A/V sync
    shots = []   # (kind, start, end, segment)
    for i, (a, b) in enumerate(zip(starts, ends)):
        if i in pres:
            cut = round(min(b, a + pres[i]) * 30) / 30 if pres[i] else b
            if b - cut < 1.5:
                cut = b
            shots.append(("A", a, cut, i))
            if cut < b:
                shots.append(("S", cut, b, i))
        else:
            shots.append(("S", a, b, i))

    preset = os.environ.get("X264_PRESET", "medium")
    enc = ["-c:v", "libx264", "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-an"]
    pieces = []
    for j, (kind, a, b, i) in enumerate(shots):
        seg = cfg["segments"][i]
        piece = os.path.join(tmp, f"p{j:03d}.mp4"); d = b - a
        if kind == "A":
            if seg["slide"]["type"] == "section":
                lt = os.path.join(tmp, f"lt{j}.png"); lower_third(seg["slide"]["n"], seg["slide"]["title"], lt)
                run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", clip, "-loop", "1", "-i", lt,
                     "-filter_complex", f"[0:v]{afilt}[a];[1:v]format=rgba[o];[a][o]overlay=0:0:shortest=1,format=yuv420p[v]",
                     "-map", "[v]", "-t", f"{d:.3f}", *enc, piece])
            else:
                run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", clip,
                     "-filter_complex", f"[0:v]{afilt},format=yuv420p[v]", "-map", "[v]", "-t", f"{d:.3f}", *enc, piece])
        else:
            png = os.path.join(tmp, f"s{j}.png"); mv.slide(seg["slide"]).save(png)
            run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-vf", f"scale={W}:{H},setsar=1,fps=30",
                 "-t", f"{d:.3f}", "-tune", "stillimage", *enc, piece])
        pieces.append(piece)
    lst = os.path.join(tmp, "list.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in pieces))
    vid = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])
    final = os.path.join(out, slug + ".mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", clip, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", final])
    chapters = [[int(starts[i]), s["chapter"]] for i, s in enumerate(cfg["segments"]) if s.get("chapter")]
    json.dump(chapters, open(os.path.join(out, slug + "-chapters.json"), "w"))
    json.dump([[k, round(a, 2), round(b, 2), i] for k, a, b, i in shots], open(os.path.join(out, slug + "-shots.json"), "w"))
    thumbnail(clip, box, cfg["thumb"], os.path.join(out, slug + "-thumb.jpg"), tmp)
    on = sum(b - a for k, a, b, _ in shots if k == "A")
    print(f"rendered {final}: {len(shots)} shots, presenter on screen {on:.0f}s of {total:.0f}s")


if __name__ == "__main__":
    main()
