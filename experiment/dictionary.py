"""Does an American dictionary fix the American style?

The parameter study left the US style at about a third of grids filling, and
immovable: every search parameter and an eightfold increase in time left it
between 0.29 and 0.33. That is the signature of a vocabulary that does not
contain the fills rather than a search that cannot find them, and the length
histogram says where the gap is -- UKACD has 1,245 three-letter entries against
Spread the Wordlist's 4,308, at exactly the slots a fully-checked grid leans on.

So: the same lists, the same library, the same defaults, one dictionary
swapped. Completion is the metric, because it is the one that was stuck.

Run on the **held-out** lists. The hypothesis came from the tune split, so
testing it there would be marking my own homework.

    python3 experiment/dictionary.py --seconds 45 --out experiment/dictionary.jsonl
"""

import argparse
import inspect
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crossword import coverage, library
from crossword.fill import Filler
from crossword.index import Index
from crossword.words import load

from run import STYLES, SPACE

DICTIONARIES = {
    "ukacd": ("crossword/UKACD.txt", "crossword/scores.txt"),
    "american": ("american.txt", "american-scores.txt"),
}


def read_scores(path):
    scores = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#") and line.strip():
                word, value = line.split()
                scores[word] = float(value)
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--split", default="hold")
    parser.add_argument("--styles", default="british,barred,jumbo,us")
    parser.add_argument("--out", default="experiment/dictionary.jsonl")
    args = parser.parse_args()

    wanted = set(args.styles.split(","))
    lists = [l for l in json.load(open("experiment/lists.json"))["lists"]
             if l["split"] == args.split and l["style"] in wanted]
    print(f"{len(lists)} {args.split} lists across {sorted(wanted)}",
          file=sys.stderr)

    indexes = {}
    for name, (words, scores) in DICTIONARIES.items():
        entries = load(words, max_length=21, strict=False)
        indexes[name] = Index(entries, read_scores(scores))
        print(f"{name}: {len(entries):,} entries", file=sys.stderr)

    shelves = {name: (library.load(spec["path"], style=spec["style"]),
                      library.rules_for(spec["style"]))
               for name, spec in STYLES.items() if name in wanted}

    # Spread the Wordlist stops at fifteen letters, because a 15x15 is the
    # American grid. A 21x21 jumbo has twenty-one-letter entries, so the pair
    # is not merely worse, it is unusable -- record that rather than crash
    # eight runs into the style.
    served = {}
    for style, (patterns, rules) in shelves.items():
        needed = {slot.length for pattern in patterns
                  for slot in pattern.grid().slots(rules.min_entry_length)}
        for name, index in indexes.items():
            missing = sorted(length for length in needed
                             if not index.lengths.get(length,
                                                      None) or not
                             index.lengths[length].words)
            served[(style, name)] = missing
            if missing:
                print(f"{name} cannot serve {style}: no entries of length "
                      f"{missing}", file=sys.stderr)

    # Today's defaults, read off the functions rather than from SPACE, whose
    # first values are the study's starting point and have since drifted:
    # `relax` was adopted at 10 and SPACE still opens at 3. The parameters are
    # spread down the call chain, so each name is resolved against it in turn.
    chain = [coverage.best_over_library, coverage.cover, Filler.__init__]
    defaults = {}
    for name in SPACE:
        for function in chain:
            parameter = inspect.signature(function).parameters.get(name)
            if parameter is not None and parameter.default is not inspect.Parameter.empty:
                defaults[name] = parameter.default
                break
    missing = sorted(set(SPACE) - set(defaults))
    if missing:
        parser.error(f"no default found in the call chain for {missing}")
    print(f"defaults: {defaults}", file=sys.stderr)

    # Resume on the identity of a run, not on a count of them. A count only
    # works while the iteration order never changes, and it changed the moment
    # a dictionary turned out not to serve a style.
    already = set()
    if os.path.exists(args.out):
        for line in open(args.out):
            row = json.loads(line)
            already.add((row["list"], row["dictionary"], row["seed"]))
        print(f"resuming: {len(already)} runs recorded", file=sys.stderr)

    total = len(lists) * len(DICTIONARIES) * args.seeds
    began = time.time()
    n = 0
    with open(args.out, "a", encoding="utf-8") as handle:
        for entry in lists:
            patterns, rules = shelves[entry["style"]]
            for dictionary, index in indexes.items():
                for seed in range(args.seeds):
                    n += 1
                    if (entry["id"], dictionary, seed) in already:
                        continue
                    missing = served[(entry["style"], dictionary)]
                    if missing:
                        handle.write(json.dumps({
                            "list": entry["id"], "style": entry["style"],
                            "size": entry["size"], "dictionary": dictionary,
                            "seed": seed, "ok": None,
                            "unserved": missing,
                        }) + "\n")
                        handle.flush()
                        continue
                    started = time.time()
                    got = coverage.best_over_library(
                        patterns, index, entry["words"], rules,
                        time_limit=args.seconds, seed=seed, **defaults)
                    handle.write(json.dumps({
                        "list": entry["id"], "style": entry["style"],
                        "size": entry["size"], "dictionary": dictionary,
                        "seed": seed, "ok": bool(got.ok), "seated": got.n,
                        "ceiling": got.ceiling,
                        "quality": round(got.quality, 4),
                        "elapsed": round(time.time() - started, 2),
                    }) + "\n")
                    handle.flush()
                    print(f"  {n}/{total} {entry['id']:<12} {dictionary:<9} "
                          f"ok={bool(got.ok)} seated={got.n}/{got.ceiling} "
                          f"[{time.time() - began:.0f}s]", file=sys.stderr,
                          flush=True)
    print(f"done in {time.time() - began:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
