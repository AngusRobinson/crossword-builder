"""Build the word lists the parameter study runs on.

Fresh lists, because benchmark/lists.json cannot serve as a held-out set: it
has been tuned against throughout this project's history, so a setting that
suits it may only suit it. That file stays as a legacy regression check, looked
at once at the end.

Lists are drawn per style, because a style's entry lengths decide what a
plausible theme looks like: a 12x12 barred grid has nothing shorter than four
and nothing longer than twelve, and a 21x21 jumbo reaches nineteen. Sampling
lengths from the style's own supply keeps every list one that style could in
principle hold.

The tune/hold split is made here, once, and written into the file. Nothing in
the study may look at the held-out half until the end.
"""

import json
import os
import random
import sys
from collections import Counter

# Runnable from anywhere: the study lives in a subdirectory but reads the
# project's data files by their paths from the root.
if os.path.basename(os.getcwd()) == "experiment":
    os.chdir("..")
sys.path.insert(0, os.getcwd())

from crossword import library
from crossword.words import load

STYLES = {
    "british": dict(style="british", path=None),
    "barred": dict(style="barred", path=None),
    "jumbo": dict(style="british", path="crossword/grids-21.txt"),
    "us": dict(style="us", path=None),
}
SIZES = (8, 20, 60)          # small, medium, large themes
PER_CELL = 8                 # lists per (style, size); half tune, half held out
SEED = 20260906


def length_supply(patterns, min_length):
    """How many entries of each length the style offers, over its library."""
    supply = Counter()
    for pattern in patterns[:60]:
        for slot in pattern.grid().slots(min_length):
            supply[slot.length] += 1
    return supply


def main():
    entries = load("crossword/UKACD.txt", max_length=21)
    scores = {}
    with open("crossword/scores.txt", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#") and line.strip():
                word, value = line.split()
                scores[word] = float(value)
    # Words a setter might actually choose as a theme: known enough to be worth
    # hiding, not so obscure that the list is a stunt.
    pool = [e.text for e in entries if scores.get(e.text, 0.0) > 1.5]
    by_length = {}
    for word in pool:
        by_length.setdefault(len(word), []).append(word)

    rng = random.Random(SEED)
    out = []
    for name, spec in STYLES.items():
        patterns = library.load(spec["path"], style=spec["style"])
        rules = library.rules_for(spec["style"])
        supply = length_supply(patterns, rules.min_entry_length)
        lengths = [n for n in supply if by_length.get(n)]
        weights = [supply[n] for n in lengths]
        for size in SIZES:
            for i in range(PER_CELL):
                words, seen = [], set()
                while len(words) < size:
                    n = rng.choices(lengths, weights)[0]
                    word = rng.choice(by_length[n])
                    if word not in seen:
                        seen.add(word)
                        words.append(word)
                out.append({
                    "id": f"{name}-{size:02d}-{i:02d}",
                    "style": name,
                    "size": size,
                    # Half of each cell held out, decided here and never
                    # revisited.
                    "split": "tune" if i < PER_CELL // 2 else "hold",
                    "words": sorted(words),
                })

    document = {
        "generated_by": "experiment/make_lists.py",
        "seed": SEED,
        "note": "Fresh lists for the parameter study. The split is fixed here; "
                "the held-out half is not to be looked at until the end.",
        "lists": out,
    }
    with open("experiment/lists.json", "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
    counts = Counter((l["style"], l["split"]) for l in out)
    print(f"{len(out)} lists -> experiment/lists.json")
    for key in sorted(counts):
        print(f"  {key[0]:8} {key[1]:5} {counts[key]}")


if __name__ == "__main__":
    main()
