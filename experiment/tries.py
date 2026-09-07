"""Does running the search again beat running it longer?

`--tries N` runs the whole search N times from fresh seeds and keeps the best.
It was measured by comparing one run against the best of N, each at full time --
so N runs got N times the clock, and the comparison was between one budget and
another rather than between two ways of spending one. What a user actually
faces is a fixed total: is it better spent as one long search or several short
ones?

That needs no extra runs to answer for every N at once. A run given T passes
through exactly the states a run given T/N would, so recording the improvement
curve of S seeds at the full budget lets the best of any N <= S at T/N be read
straight off the curves. Which is what this does.

    python3 experiment/tries.py --seeds 8 --seconds 60
"""

import argparse
import json
import os
import statistics as s
import sys
import time

if os.path.basename(os.getcwd()) == "experiment":
    os.chdir("..")
sys.path.insert(0, os.getcwd())

from crossword import coverage, library
from crossword.index import Index
from crossword.words import load

STYLES = {
    "british": dict(style="british", path=None),
    "barred": dict(style="barred", path=None),
    "jumbo": dict(style="british", path="crossword/grids-21.txt"),
    "us": dict(style="us", path=None),
}


def reached(curve, seconds, ceiling):
    """Effective coverage by `seconds`: completed grids only."""
    best = 0
    for moment, seated, ok, _q in curve:
        if moment <= seconds and ok:
            best = max(best, seated)
    return best / ceiling if ceiling else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--per-cell", type=int, default=2)
    parser.add_argument("--out", default="experiment/tries.jsonl")
    args = parser.parse_args()

    every = [l for l in json.load(open("experiment/lists.json"))["lists"]
             if l["split"] == "tune"]
    lists, taken = [], {}
    for entry in every:
        key = (entry["style"], entry["size"])
        if taken.get(key, 0) < args.per_cell:
            taken[key] = taken.get(key, 0) + 1
            lists.append(entry)

    entries = load("crossword/UKACD.txt", max_length=21)
    scores = {}
    with open("crossword/scores.txt", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#") and line.strip():
                word, value = line.split()
                scores[word] = float(value)
    index = Index(entries, scores)
    shelves = {name: (library.load(spec["path"], style=spec["style"]),
                      library.rules_for(spec["style"]))
               for name, spec in STYLES.items()}

    print(f"{len(lists)} lists x {args.seeds} seeds at {args.seconds:.0f}s",
          file=sys.stderr)
    with open(args.out, "a", encoding="utf-8") as handle:
        for entry in lists:
            patterns, rules = shelves[entry["style"]]
            for seed in range(args.seeds):
                curve = []
                got = coverage.best_over_library(
                    patterns, index, entry["words"], rules,
                    time_limit=args.seconds, seed=seed,
                    on_improve=lambda t, c: curve.append(
                        [round(t, 2), c.n, bool(c.ok), round(c.quality, 4)]))
                handle.write(json.dumps({
                    "list": entry["id"], "style": entry["style"],
                    "size": entry["size"], "seed": seed,
                    "ok": bool(got.ok), "seated": got.n,
                    "ceiling": got.ceiling, "curve": curve}) + "\n")
                handle.flush()
            print(f"  {entry['id']}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
