"""Is the dictionary still the constraint, or has it saturated?

Adding a bigger dictionary adds words at the *obscure* end: Wiktionary's
inflections and rare forms, not more common English. So the way to ask what
another million words would buy is to take them away from the end they would
arrive at -- fill using only the most familiar X% of what we have -- and see
whether performance is still climbing as X reaches 100.

If it is, more vocabulary will keep paying. If it flattened at 70%, the words
beyond that are not what the search is short of, and a larger dictionary buys
little however large it is.

    python3 experiment/vocabulary.py --fractions 0.25 0.5 0.75 1.0
"""

import argparse
import json
import os
import statistics as s
import sys

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fractions", nargs="+", type=float,
                        default=[0.25, 0.5, 0.75, 1.0])
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--per-cell", type=int, default=2)
    parser.add_argument("--out", default="experiment/vocabulary.jsonl")
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

    # Trimmed within each length, not overall: taking the most familiar 25% of
    # the whole dictionary would delete almost every long word, and would be
    # measuring length rather than familiarity.
    by_length = {}
    for entry in entries:
        by_length.setdefault(len(entry.text), []).append(entry)
    for group in by_length.values():
        group.sort(key=lambda e: -scores.get(e.text, 0.0))

    shelves = {name: (library.load(spec["path"], style=spec["style"]),
                      library.rules_for(spec["style"]))
               for name, spec in STYLES.items()}

    indexes = {}
    for fraction in args.fractions:
        kept = []
        for group in by_length.values():
            kept.extend(group[:max(1, int(len(group) * fraction))])
        indexes[fraction] = (Index(kept, scores), len(kept))
        print(f"  {fraction:.0%} of each length: {len(kept):,} words",
              file=sys.stderr)

    with open(args.out, "a", encoding="utf-8") as handle:
        for entry in lists:
            patterns, rules = shelves[entry["style"]]
            for seed in range(args.seeds):
                for fraction in args.fractions:
                    index, size = indexes[fraction]
                    got = coverage.best_over_library(
                        patterns, index, entry["words"], rules,
                        time_limit=args.seconds, seed=seed, relax=10)
                    handle.write(json.dumps({
                        "fraction": fraction, "words": size,
                        "list": entry["id"], "style": entry["style"],
                        "size": entry["size"], "seed": seed,
                        "ok": bool(got.ok), "seated": got.n,
                        "ceiling": got.ceiling}) + "\n")
                    handle.flush()
            print(f"  {entry['id']}", file=sys.stderr, flush=True)

    rows = [json.loads(l) for l in open(args.out, encoding="utf-8")]
    def eff(r):
        return (r["seated"] / r["ceiling"] if r["ceiling"] else 0) if r["ok"] else 0
    print(f"\n{'style':10}" + "".join(f"{f:>18.0%}" for f in args.fractions))
    for style in STYLES:
        line = ""
        for fraction in args.fractions:
            sub = [r for r in rows
                   if r["style"] == style and r["fraction"] == fraction]
            if sub:
                line += (f"{s.mean([eff(r) for r in sub]):>10.3f}"
                         f"{sum(r['ok'] for r in sub) / len(sub):>8.0%}")
        print(f"{style:10}" + line)


if __name__ == "__main__":
    main()
