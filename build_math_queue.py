#!/usr/bin/env python3
"""Build math_queue.json for the daily GRE Quant Shorts/Reels from the GRE Math Knight 2.0 bank.

Usage: python3 build_math_queue.py OUT2_DIR
Keeps only items that read well on a phone: no figure, chart, or image, and short enough to fit.
Each 2.0 question comes first, then its "fresh version" (variant), so the order runs through
all main questions before any variant.
"""
import glob, hashlib, json, os, re, sys
from fractions import Fraction

QC = ["A>B", "A<B", "A=B", "\\text{Unknown}"]
QC_TEXT = {"A>B": "Quantity A is greater.", "A<B": "Quantity B is greater.",
           "A=B": "The two quantities are equal.",
           "\\text{Unknown}": "The relationship cannot be determined from the information given."}


def is_math(s):
    return bool(re.search(r"\\|\^|_\{", s))


def num(s):
    s = s.strip().replace("−", "-").replace(",", "")
    m = re.fullmatch(r"(-?)\\frac\{(-?\d+)\}\{(\d+)\}", s)
    if m:
        return Fraction(int(m.group(2)), int(m.group(3))) * (-1 if m.group(1) else 1)
    try:
        return Fraction(s)
    except (ValueError, ZeroDivisionError):
        return None


def split_top(s):
    depth, cur, out = 0, "", []
    for ch in s:
        if ch == "{": depth += 1
        if ch == "}": depth -= 1
        if ch == "," and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def convert(it, ident):
    q = it["q"]
    is_qc = bool(q) and q[0] == "QUANTITY_A_B"
    if it.get("figure") or it["qtype"] == "image" or (it["qtype"] == "chart" and not is_qc):
        return None
    if any(re.search(r"\S+\.png", x) for x in q):
        return None
    rec = {"id": ident}
    ans, wrong, notes = it["ans"], it["wrong"], it["wrong_notes"]
    if is_qc:
        a, b = split_top(q[1])
        rec.update(kind="qc", A=a, B=b, given=[x for x in q[2:-1]], ask=q[-1])
        choices = QC[:]
        rec["choices"] = [QC_TEXT[c] for c in choices]
        rec["choice_math"] = [False] * 4
    else:
        rec.update(kind="mc", lines=q)
        choices = [ans] + wrong
        vals = [num(c) for c in choices]
        if all(v is not None for v in vals):
            choices = [c for _, c in sorted(zip(vals, choices), key=lambda t: t[0])]
        else:
            h = int(hashlib.md5(ident.encode()).hexdigest(), 16)
            choices = wrong[:]
            choices.insert(h % (len(wrong) + 1), ans)
        rec["choices"] = choices
        rec["choice_math"] = [is_math(c) or num(c) is not None for c in choices]
    rec["answer"] = choices.index(ans) if ans in choices else rec["choices"].index(QC_TEXT[ans])
    # trap: the first wrong answer the writers built from a mistake recipe
    trap = wrong[0]
    rec["trap"] = choices.index(trap) if trap in choices else rec["choices"].index(QC_TEXT[trap])
    rec["trap_note"] = notes[0]
    rec["sol"] = [[k, v] for k, v in it["sol"]]
    # size limits so everything fits at phone-legible sizes
    text_len = sum(len(x) for x in q)
    if text_len > 300 or sum(len(v) for _, v in rec["sol"]) > 300 or len(rec["sol"]) > 4:
        return None
    if rec["kind"] == "mc" and any(len(c) > 28 for c in choices):
        return None
    if len(rec["trap_note"]) > 110:
        return None
    return rec


def main(src):
    bank = []
    for f in sorted(glob.glob(os.path.join(src, "*.json"))):
        bank.extend(json.load(open(f)))
    mains, variants = [], []
    for o in bank:
        r = convert(o["item"], o["id"])
        if r:
            r["skill"] = o.get("skill", "")
            mains.append(r)
        v = o.get("variant")
        if v:
            r = convert(v, o["id"] + "-v1")
            if r:
                r["skill"] = o.get("skill", "")
                variants.append(r)
    out = mains + variants
    for i, r in enumerate(out, 1):
        r["num"] = i
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "math_queue.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"{len(mains)} questions + {len(variants)} fresh versions = {len(out)}")


if __name__ == "__main__":
    main(sys.argv[1])
