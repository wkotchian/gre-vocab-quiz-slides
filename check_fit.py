#!/usr/bin/env python3
"""Drop queue items whose question or answer frame can't render or won't fit above the caption area.

Usage: python3 check_fit.py gre|sat     (rewrites that app's queue file, renumbered from 1)
"""
import json, os, sys
from PIL import Image, ImageChops
import make_math_short as m


def fits(q):
    for fr in (m.question_frame(q, 30), m.answer_frame(q)):
        crop = fr.crop((0, m.BOTTOM + 20, m.W, m.H))
        if ImageChops.difference(crop, Image.new("RGB", crop.size, m.APP["bg"])).getbbox():
            return False
    return True


def main(app):
    m.use_app(app)
    path = os.path.join(m.HERE, m.APP["queue"])
    queue = json.load(open(path))
    keep, dropped = [], []
    for q in queue:
        try:
            ok = fits(q)
        except Exception as e:  # noqa: BLE001
            ok = False
            print("render error", q["id"], str(e).splitlines()[0][:100])
        (keep if ok else dropped).append(q)
    for i, q in enumerate(keep, 1):
        q["num"] = i
    json.dump(keep, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"{app}: kept {len(keep)}, dropped {len(dropped)}: {[q['id'] for q in dropped]}")


if __name__ == "__main__":
    main(sys.argv[1])
