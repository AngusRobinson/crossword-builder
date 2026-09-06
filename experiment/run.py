"""Screening run for the parameter study.

Every constant in this project was tuned on British 15x15 grids, and three
other styles have since inherited them. This asks which of those constants
actually matter, and whether the answer differs by style.

**Design.** Configurations are drawn at random over the whole parameter space
rather than varied one at a time. Random search finds the few parameters that
matter far more cheaply than a grid does, and unlike one-at-a-time it can see
interactions. Every configuration is run on the same lists, so two of them are
always compared on identical work; the first configuration is today's defaults,
and appears in the results as the baseline.

This is screening, and it answers "which parameters move anything, and does the
answer differ by style". It does not settle a value. Anything that looks real
here goes to a focused paired comparison on the remaining tune lists, and only
then to the held-out half.

**Time.** Each run is given a generous budget and its improvements are
recorded as they happen. `time_limit` does nothing in `best_over_library`
except stop the loop, so a long run passes through exactly the states a short
one would: one run yields the result at every smaller budget, exactly. That is
how the study measures what more time buys, rather than fixing a budget and
guessing.

**What is not touched.** Only the tune half of experiment/lists.json. The held
out half, and benchmark/lists.json, are for confirming a finding at the end.

Results are appended a line at a time, so an interrupted run keeps what it had.

    python3 experiment/run.py --configs 60 --seconds 30
"""

import argparse
import json
import os
import random
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

# The parameter space. Each entry is the values a configuration may draw from,
# with the current default first -- so a configuration that draws every first
# value is today's behaviour, and appears in the results as a baseline.
SPACE = {
    "commonness": [3.0, 0.0, 1.0, 6.0, 12.0],
    "aim": [0.85, 0.65, 0.75, 0.92, 0.98],
    "top": [14, 7, 24, 40, 60],
    "quality_scan": [4, 0, 2, 8, 16],
    "attempts": [3, 1, 2, 6, 10],
    "budget": [6000, 1500, 3000, 15000, 40000],
    "relax": [3, 0, 1, 6, 10],
    "branch_cap": [200, 50, 100, 400, 1000],
    "fill_restarts": [3, 1, 2, 6, 12],
    # The node budget a fill gets is max(8000, node_scale x entries). The
    # scaling was put in for American grids and never measured; a jumbo has
    # twice the entries again.
    "node_scale": [400, 150, 800, 2000],
}

# What each is expected to do, written down before the run so that a surprise
# cannot be retold afterwards as a prediction.
PRIOR = {
    "commonness": "saturates past 3; little effect on coverage either way",
    "aim": "no effect on coverage, large effect on familiarity",
    "top": "more patterns helps large grids most, since their scan is slower",
    "quality_scan": "little effect on coverage; some on familiarity",
    "attempts": "more helps dense lists, where one seating attempt is unlucky",
    "budget": "the one most likely mis-scaled for US and jumbo, whose grids "
              "carry two to three times the entries a British one does",
    "relax": "helps dense lists only",
    "branch_cap": "no effect; it made none at 8x8 and none is expected here",
    "fill_restarts": "small effect, and mostly on styles that fail often",
    "node_scale": "the other candidate for being mis-scaled by style",
}


def draw(rng):
    return {name: rng.choice(values) for name, values in SPACE.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", type=int, default=60)
    parser.add_argument("--seconds", type=float, default=30.0,
                        help="budget per run; the curve covers everything below")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--per-cell", type=int, default=2,
                        help="tune lists per (style, size). The same ones for "
                             "every configuration, so configurations are "
                             "compared on identical work")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="experiment/results.jsonl")
    args = parser.parse_args()

    every = [l for l in json.load(open("experiment/lists.json"))["lists"]
             if l["split"] == "tune"]
    # A fixed, balanced subset: screening wants many configurations more than
    # it wants many lists per configuration, since the analysis pools across
    # configurations with the list as a covariate. Phase two, comparing a
    # handful of settings closely, uses the rest.
    lists, taken = [], {}
    for entry in every:
        key = (entry["style"], entry["size"])
        if taken.get(key, 0) < args.per_cell:
            taken[key] = taken.get(key, 0) + 1
            lists.append(entry)
    print(f"{len(lists)} lists of {len(every)} tune lists, "
          f"{args.per_cell} per (style, size)", file=sys.stderr)
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

    rng = random.Random(args.seed)
    done = 0
    if os.path.exists(args.out):
        done = sum(1 for _ in open(args.out))
        print(f"resuming: {done} runs already recorded", file=sys.stderr)

    began = time.time()
    with open(args.out, "a", encoding="utf-8") as handle:
        for config_id in range(args.configs):
            config = draw(rng) if config_id else {k: v[0] for k, v in SPACE.items()}
            for entry in lists:
                patterns, rules = shelves[entry["style"]]
                for seed in range(args.seeds):
                    row = {"config_id": config_id, "config": config,
                           "list": entry["id"], "style": entry["style"],
                           "size": entry["size"], "seed": seed}
                    if done:
                        done -= 1        # already recorded; skip the work
                        continue
                    curve = []
                    started = time.time()
                    got = coverage.best_over_library(
                        patterns, index, entry["words"], rules,
                        time_limit=args.seconds, seed=seed,
                        on_improve=lambda t, c: curve.append(
                            [round(t, 2), c.n, bool(c.ok), round(c.quality, 4)]),
                        top=config["top"], quality_scan=config["quality_scan"],
                        attempts=config["attempts"], budget=config["budget"],
                        relax=config["relax"], branch_cap=config["branch_cap"],
                        fill_restarts=config["fill_restarts"],
                        node_scale=config["node_scale"],
                        commonness=config["commonness"], aim=config["aim"],
                    )
                    row.update(ok=bool(got.ok), seated=got.n,
                               ceiling=got.ceiling, quality=round(got.quality, 4),
                               elapsed=round(time.time() - started, 2),
                               curve=curve)
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
            print(f"config {config_id + 1}/{args.configs}, "
                  f"{(time.time() - began) / 60:.0f} min elapsed",
                  file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
