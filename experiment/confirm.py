"""Phase two: a close paired comparison of one parameter, on fresh lists.

Screening says where to look, on 24 of the 48 tune lists and one seed each.
This settles a value: the other 24 tune lists, several seeds, the same lists and
seeds for every setting so the comparison is paired throughout.

Only if a difference survives here does it go to the held-out half.

    python3 experiment/confirm.py --param relax --values 3 10 --seeds 3
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--param", default="relax")
    parser.add_argument("--values", nargs="+", type=float, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--split", default="tune", choices=("tune", "hold"))
    parser.add_argument("--styles", nargs="+", default=None,
                        help="only these styles, so an interrupted run can be "
                             "finished without repeating what it did")
    parser.add_argument("--out", default="experiment/confirm.jsonl")
    args = parser.parse_args()

    every = [l for l in json.load(open("experiment/lists.json"))["lists"]
             if l["split"] == args.split]
    if args.split == "tune":
        # The half screening did not touch: it used the first two of each
        # (style, size) cell, so this takes the rest.
        seen, lists = {}, []
        for entry in every:
            key = (entry["style"], entry["size"])
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 2:
                lists.append(entry)
    else:
        lists = every
    if args.styles:
        lists = [l for l in lists if l["style"] in args.styles]
    print(f"{len(lists)} lists, {args.seeds} seeds, values {args.values}",
          file=sys.stderr)

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

    got = []
    with open(args.out, "a", encoding="utf-8") as handle:
        for entry in lists:
            patterns, rules = shelves[entry["style"]]
            for seed in range(args.seeds):
                for value in args.values:
                    kind = int(value) if float(value).is_integer() else value
                    result = coverage.best_over_library(
                        patterns, index, entry["words"], rules,
                        time_limit=args.seconds, seed=seed,
                        **{args.param: kind})
                    row = {"param": args.param, "value": kind,
                           "split": args.split, "list": entry["id"],
                           "style": entry["style"], "size": entry["size"],
                           "seed": seed, "ok": bool(result.ok),
                           "seated": result.n, "ceiling": result.ceiling,
                           "quality": round(result.quality, 4)}
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
                    got.append(row)
            print(f"  {entry['id']}", file=sys.stderr, flush=True)

    def eff(r):
        return (r["seated"] / r["ceiling"] if r["ceiling"] else 0.0) if r["ok"] else 0.0

    print(f"\n{args.param}, {args.split} lists, paired on list and seed\n")
    print(f"{'style':10}" + "".join(f"{v:>18}" for v in args.values))
    for style in STYLES:
        line = ""
        for value in args.values:
            kind = int(value) if float(value).is_integer() else value
            sub = [r for r in got if r["style"] == style and r["value"] == kind]
            if sub:
                line += (f"{s.mean([eff(r) for r in sub]):>10.3f}"
                         f"{sum(r['ok'] for r in sub) / len(sub):>8.0%}")
        print(f"{style:10}" + line)


if __name__ == "__main__":
    main()
