#!/usr/bin/env python3
"""Cut a HeyGen avatar clip into short presenter bursts with slides in between.

The avatar's own audio runs the whole time. Sentence groups are mapped to shots:
  group 0 -> avatar, group 1 -> slide, group 2 -> slide, group 3 -> avatar
Cut points snap to the pauses ffmpeg finds nearest to where each group should end.
Usage: python3 make_demo.py NAME CLIP.mp4 SLIDE1.png SLIDE2.png OUT.mp4
"""
import re, subprocess, sys

GROUPS = [
    "Here are three physical therapy personal statement examples for PTCAS, with notes on what makes each one work.",
    "First, the prompt. PTCAS asks how you see yourself having an impact on the profession once you enter the field, and every program reads the same essay.",
    "The first example comes from an adaptive ski instructor, and it opens with a mistake: the ski creeps downhill during a transfer.",
    "Starting with something you got wrong shows you learning from a patient. Readers trust that more than an opening about how inspiring the work was.",
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


def main():
    name, clip, s1, s2, out = sys.argv[1:6]
    total = duration(clip)
    chars = [len(g) for g in GROUPS]
    # speech runs from ~0.2s to ~total-0.3s; expected group ends by character share
    t0, t1 = 0.2, total - 0.3
    exp, acc = [], 0
    for c in chars[:-1]:
        acc += c
        exp.append(t0 + (t1 - t0) * acc / sum(chars))
    ps = pauses(clip)
    cuts = []
    for e in exp:
        near = min(ps, key=lambda p: abs(p - e)) if ps else e
        cuts.append(near if abs(near - e) < 2.5 else e)
    edges = [0.0] + cuts + [total]
    print(name, "total %.2f" % total, "expected", ["%.2f" % e for e in exp], "cuts", ["%.2f" % c for c in cuts])
    # video inputs: 0 = clip, 1 = slide1, 2 = slide2
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30")
    parts, labels = [], []
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        d = b - a
        if i in (0, 3):
            parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,{fit},format=yuv420p[v{i}]")
        else:
            src = 1 if i == 1 else 2
            parts.append(f"[{src}:v]scale={W}:{H},setsar=1,fps=30,trim=duration={d:.3f},setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
        labels.append(f"[v{i}]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-loop", "1", "-i", s1, "-loop", "1", "-i", s2,
         "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", out])
    print("wrote", out)


if __name__ == "__main__":
    main()
