#!/usr/bin/env python3
"""Cross-check the dataset against the BradyGames THUG2 strategy guide (2004).

The guide is an independent, contemporaneous source: it was written from the
retail game rather than from the scripts, so it catches things a script parser
missed by looking in the wrong shape. Running it is what turned up the ten
double-tap tricks whose definitions use a fused `Trigger_Extra_Grab` token
instead of `Scr=GrabTrick` (BS Shifty, Tuck Knee, 360 Hardflip and friends).

The guide is not included in this repository. Supply your own scan:

    # one .txt per page, from a scanned copy you own
    ls pages/*.jpg | xargs -P 8 -I{} sh -c 'tesseract {} txt/$(basename {} .jpg)'
    python3 harness/xcheck_guide.py txt/

The guide prints its trick tables as "<Name> <score>/<switch score>", where the
first number is the base score and the second is exactly 1.2x it. That ratio is
used to tell real table rows apart from page numbers and other stray digits.

OCR is noisy, so this is a lead generator, not an oracle. Every line it prints
is something to check by eye against the scripts, which remain the authority:
the guide has its own errors, and a disagreement is as likely to be a typo in a
20-year-old book as a bug here.
"""
import json, re, sys, glob, os
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
guide_dir = sys.argv[1] if len(sys.argv) > 1 else "guide-txt"
data_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    HERE, os.pardir, "data", "thug2-tricks.json")

if not os.path.isdir(guide_dir):
    sys.exit(__doc__.strip().split("\n\n")[2] + "\n\nNo such directory: " + guide_dir)

d = json.load(open(data_path))
known = {}


def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", "", s)


def add(name, score):
    k = norm(name or "")
    if k and (k not in known or known[k][1] is None):
        known[k] = (name, score)


def walk(node):
    """Collect every name-bearing entry anywhere in the dataset.

    Swept by shape rather than by naming the sections, because listing sections
    by hand is the exact mistake this dataset has already paid for twice: a
    parser that reads only the lists it knows about cannot report what it never
    looked at.
    """
    if isinstance(node, dict):
        if isinstance(node.get("name"), str):
            add(node["name"], node.get("score"))
        for k, v in node.items():
            if isinstance(v, str) and k in ("doubleTap", "tapsAgainInto", "trick",
                                            "trick2", "grind", "jump"):
                add(v, None)
            walk(v)
    elif isinstance(node, list):
        for v in node:
            add(v, None) if isinstance(v, str) else walk(v)


walk(d)

PAIR = re.compile(r"([A-Za-z][A-Za-z0-9 '’\-\.]{2,42}?)\s+(\d{2,4})\s*/\s*(\d{2,4})")
found = {}
for f in sorted(glob.glob(os.path.join(guide_dir, "*.txt"))):
    page = re.sub(r"\D", "", os.path.basename(f))[-3:] or "?"
    for m in PAIR.finditer(open(f, encoding="utf8", errors="replace").read()):
        raw, base, switch = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        if round(base * 1.2) != switch:
            continue
        raw = re.sub(r"^(and|the|a|or)\s+", "", raw, flags=re.I).strip()
        if len(norm(raw)) >= 3:
            found.setdefault(norm(raw), (raw, base, page))

agree, disagree, unmatched = [], [], []
for k, (raw, gscore, page) in sorted(found.items()):
    if k in known:
        name, dscore = known[k]
        if dscore is not None:
            (agree if dscore == gscore else disagree).append((name, dscore, gscore, page))
    else:
        near, ratio = max(((kk, SequenceMatcher(None, k, kk).ratio()) for kk in known),
                          key=lambda x: x[1], default=("", 0.0))
        unmatched.append((raw, gscore, page, known.get(near, ("-",))[0], ratio))

print("dataset: %d named tricks     guide: %d scored rows\n" % (len(known), len(found)))
print("scores agree: %d" % len(agree))
print("scores disagree: %d" % len(disagree))
for name, ds, gs, page in disagree:
    print("   %-34s dataset=%-7s guide=%-7s (p%s)" % (name, ds, gs, page))

print("\nin guide, unmatched here: %d" % len(unmatched))
print("   (a high ratio means OCR mangling of a name we already have)")
for raw, gs, page, near, ratio in sorted(unmatched, key=lambda x: -x[4]):
    print("   [%s] %-34s %-6s p%s  nearest: %-28s %.2f"
          % ("ocr?" if ratio > 0.82 else "LOOK", raw[:34], gs, page, near[:28], ratio))
