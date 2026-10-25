#!/usr/bin/env python3
"""Cut a HeyGen avatar clip into short presenter bursts with slides in between.

The avatar's own audio runs the whole time. Sentence groups map to shots (A = avatar, S = slide),
so the presenter is on screen only in short bursts. Cut points snap to the pause nearest to where
each group should end. Portrait clips that HeyGen pads with white are cropped and set on a blurred fill.
Usage: python3 make_demo.py NAME CLIP.mp4 OUT.mp4
"""
import os, re, subprocess, sys, tempfile
from PIL import Image
import make_ps_video as mv

SHOTS = [
    ("A", "Here are three physical therapy personal statement examples for PTCAS, with notes on what makes each one work.", None),
    ("S", "First, the prompt. PTCAS asks how you see yourself having an impact on the profession once you enter the field, and every program reads the same essay.",
     {"type": "quote", "label": "The PTCAS prompt", "text": "As a prospective Doctor of Physical Therapy, how do you see yourself having an impact on the profession upon entering the field?", "foot": "4,500 characters, spaces included. Every program reads the same essay."}),
    ("S", "The first example comes from an adaptive ski instructor, and it opens with a mistake: the ski creeps downhill during a transfer.",
     {"type": "quote", "label": "Example 1 · The opening", "text": "The first time I helped a student transfer from his wheelchair into a bi-ski, I did most of it wrong.", "hl": "I did most of it wrong."}),
    ("S", "Starting with something you got wrong shows you learning from a patient.",
     {"type": "list", "label": "Example 1 · Why the opening works", "items": ["It starts with something the applicant got wrong", "It shows the applicant learning from a patient"]}),
    ("A", "Readers trust that more than an opening about how inspiring the work was.", None),
]
W, H = 1920, 1080


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def duration(p):
    err = subprocess.run(["ffmpeg", "-i", p], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def pauses(p):
    err = subprocess.run(["ffmpeg", "-i", p, "-af", "silencedetect=noise=-32dB:d=0.15", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def content_box(clip, tmp):
    """Bounding columns of non-white content (HeyGen pads portrait avatars with white in landscape)."""
    p = os.path.join(tmp, "probe.png")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", clip, "-frames:v", "1", p])
    im = Image.open(p).convert("L"); w, h = im.size
    px = im.load()
    def white_col(x):
        return all(px[x, y] > 245 for y in range(0, h, max(1, h // 40)))
    left = next((x for x in range(w) if not white_col(x)), 0)
    right = next((x for x in range(w - 1, -1, -1) if not white_col(x)), w - 1)
    return w, h, left, right


def main():
    name, clip, out = sys.argv[1:4]
    tmp = tempfile.mkdtemp()
    total = duration(clip)
    chars = [len(t) for _, t, _ in SHOTS]
    t0, t1 = 0.2, total - 0.3
    exp, acc = [], 0
    for c in chars[:-1]:
        acc += c
        exp.append(t0 + (t1 - t0) * acc / sum(chars))
    ps = pauses(clip)
    cuts, prev = [], 0.0
    for e in exp:
        ok = [p for p in ps if p > prev + 0.8 and abs(p - e) < 2.0]
        c = min(ok, key=lambda p: abs(p - e)) if ok else max(e, prev + 0.8)
        cuts.append(c); prev = c
    edges = [0.0] + cuts + [total]
    print(name, "total %.2f" % total, "cuts", ["%.2f" % c for c in cuts])

    w, h, left, right = content_box(clip, tmp)
    padded = (right - left) < 0.8 * w
    if padded:
        cw = right - left + 1
        avatar = (f"crop={cw}:{h}:{left}:0,split[fg0][bg0];"
                  f"[bg0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.08[bg1];"
                  f"[fg0]scale=-2:{H}[fg1];[bg1][fg1]overlay=(W-w)/2:0,setsar=1,fps=30")
    else:
        avatar = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30"
    print("padded" if padded else "full-frame", left, right, w)

    inputs, parts, labels, slide_idx = ["-i", clip], [], [], 1
    for i, ((kind, _, spec), a, b) in enumerate(zip(SHOTS, edges[:-1], edges[1:])):
        if kind == "A":
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,{avatar},format=yuv420p[v{i}]")
        else:
            png = os.path.join(tmp, f"s{i}.png"); mv.slide(spec).save(png)
            inputs += ["-loop", "1", "-i", png]
            parts.append(f"[{slide_idx}:v]scale={W}:{H},setsar=1,fps=30,trim=duration={b - a:.3f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
            slide_idx += 1
        labels.append(f"[v{i}]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
         "-movflags", "+faststart", out])
    print("wrote", out)


if __name__ == "__main__":
    main()
