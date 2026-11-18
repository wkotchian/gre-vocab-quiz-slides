#!/usr/bin/env python3
"""Build sat_queue.json (or act_queue.json) for daily math Shorts from the SAT/ACT app question sheets.

Usage: python3 build_sat_queue.py sat PROBLEMS_CSV VARIANTS_CSV
Reads the app's master-config CSVs (one question = a row with a Question id plus the rows under it).
Keeps multiple-choice items without figures or tables that fit on a phone; main questions first, then variants.
Text keeps the app's "rich" format: plain words with $...$ math.
"""
import csv, json, os, re, sys


def blocks(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    cur = None
    for r in rows:
        if r["Question"]:
            if cur:
                yield cur
            cur = {"head": r, "stem": [], "sol": []}
        if cur is None:
            continue
        if r["Question Text"]:
            cur["stem"].append((r["Content Type"], r["Question Text"]))
        if r["Solution Instructions"]:
            cur["sol"].append((r["Solution Content Type"], r["Solution Instructions"]))
    if cur:
        yield cur


def convert(b):
    h = b["head"]
    if h["Answer Type"] == "type_in" or h["Task"] not in ("question", "boss", ""):
        return None
    if any(k in ("table", "figure") for k, _ in b["stem"]):
        return None
    wrong = [h[f"Wrong {i}"] for i in range(1, 5) if h[f"Wrong {i}"]]
    notes = [h[f"Wrong {i} Error"] for i in range(1, 5) if h[f"Wrong {i}"]]
    if len(wrong) != 3 or not all(notes):
        return None
    pos = int(h["Correct Position"] or 1) - 1
    choices = wrong[:]
    choices.insert(pos, h["Correct Answer"])
    sol = [s for _, s in b["sol"] if not s.startswith("Rule:")]
    lines = [s for _, s in b["stem"]]
    plain = lambda s: re.sub(r"\$[^$]*\$", "xx", s)
    if sum(len(plain(s)) for s in lines) > 320 or sum(len(plain(s)) for s in sol) > 300 or len(sol) > 4:
        return None
    if any(len(plain(c)) > 40 for c in choices) or len(plain(notes[0])) > 120:
        return None
    return {"id": h["Question"], "kind": "mc", "lines": lines, "choices": choices,
            "answer": pos, "trap": choices.index(wrong[0]), "trap_note": notes[0],
            "sol": [["rich", s] for s in sol], "skill": h.get("Skill", "")}


def main(app, probs, variants):
    mains = [r for r in (convert(b) for b in blocks(probs)) if r]
    vars_ = [r for r in (convert(b) for b in blocks(variants)) if r]
    out = mains + vars_
    for i, r in enumerate(out, 1):
        r["num"] = i
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{app}_queue.json")
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"{app}: {len(mains)} questions + {len(vars_)} fresh versions = {len(out)} -> {os.path.basename(path)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
