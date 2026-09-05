"""A second, harder tier of benchmark lists.

    python3 make_benchmark_hard.py [corpus_dir]

The original 44 lists have stopped discriminating: most reach their ceiling at
any setting, so a change that helps or hurts shows up on two or three lists at
most.  What made them easy is size.  A 14-word theme sits in a 28-entry grid
with fourteen ordinary entries to absorb the crossings; a 26-word theme leaves
almost none, and the targets have to agree with each other letter by letter.

So this tier is dense: 20 to 30 targets, where the words themselves are most of
the grid.  Every list is `feasible` in the sense the first tier uses -- the
words co-occurred in one published puzzle whose grid is in the library -- so a
known-achievable optimum exists and any shortfall is the search's.

Written once and committed, and kept separate from benchmark/lists.json so the
original stays frozen for paired comparison.
"""

import collections
import glob
import json
import os
import random
import sys
import warnings

warnings.filterwarnings("ignore")

from crossword import coverage, library
from crossword.words import _fold

SIZES = (20, 24, 28)
PER_SIZE = 8
OUT = os.path.join("benchmark", "lists-hard.json")


def solutions(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data["dimensions"]["cols"] != 15 or data["dimensions"]["rows"] != 15:
        return None, None
    words = []
    for entry in data["entries"]:
        text = _fold(entry.get("solution") or "")
        if 3 <= len(text) <= 15 and len(text) == entry["length"]:
            words.append(text)
    return os.path.basename(path).split(".")[0], words


def main(corpus="guardian-cc-master/crosswords"):
    rng = random.Random(20260905)
    patterns = library.load()
    in_library = {p.source for p in patterns}

    usable = []
    for path in sorted(glob.glob(os.path.join(corpus, "**", "*.JSON"),
                                 recursive=True)):
        try:
            source, words = solutions(path)
        except (KeyError, ValueError, json.JSONDecodeError, OSError):
            continue
        if source and words and len(words) >= max(SIZES) and source in in_library:
            usable.append((source, sorted(set(words))))
    rng.shuffle(usable)
    print(f"{len(usable)} published puzzles carry {max(SIZES)}+ usable answers")

    lists, cursor = [], 0
    for size in SIZES:
        for _ in range(PER_SIZE):
            source, words = usable[cursor % len(usable)]
            cursor += 1
            target = rng.sample(words, size)
            ceiling = max(coverage.ceiling(p.profile(), target) for p in patterns)
            lists.append({
                "id": f"dense-{size:02d}-{len(lists):02d}",
                "size": size,
                "stratum": "dense",
                "note": f"answers of Guardian {source}",
                "known_optimum": size,
                "library_ceiling": ceiling,
                "words": sorted(target),
            })

    os.makedirs("benchmark", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({
            "generated_by": "make_benchmark_hard.py",
            "seed": 20260905,
            "note": "Dense lists where the targets are most of the grid. "
                    "Frozen: do not regenerate to chase a result.",
            "lists": lists,
        }, handle, indent=1)

    tight = sum(1 for item in lists if item["library_ceiling"] < item["size"])
    print(f"wrote {len(lists)} lists to {OUT}")
    print(f"{tight} of them are capped by the library on lengths alone")
    for size in SIZES:
        sel = [i for i in lists if i["size"] == size]
        mean = sum(i["library_ceiling"] for i in sel) / len(sel)
        print(f"  {size} words: mean library ceiling {mean:.1f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
