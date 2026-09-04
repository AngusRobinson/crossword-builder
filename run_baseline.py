"""Score the grid library against the frozen benchmark.

    python3 run_baseline.py

This is the number every future change to grid generation has to beat.  It
answers the question the project never had an answer to: how much of a target
word list can be absorbed by simply picking the best of 120 grids that the
Guardian already publishes?  A generator that cannot beat this is not earning
its complexity.

Coverage is reported against the length-profile ceiling, not the list size --
see crossword/coverage.py for why.  `feasible` lists carry a known optimum of
N, so their column is the one to read as a pass mark: anything below 100%
there is the search falling short, not the list being impossible.
"""

import collections
import json
import statistics
import time
import warnings

warnings.filterwarnings("ignore")

from crossword import coverage, frequency, library, mutate
from crossword.index import Index
from crossword.words import load

BENCH = "benchmark/lists.json"

# The production configuration, so the benchmark measures what the tool does.
MIN_USES = 0
COMMONNESS = 3.0
# None means "the combined table"; a dict overrides it, for A/B runs.
SCORES = None
QUALITY_SCAN = 4
# Grow tailored mutants from the library for each list.  Off reproduces the
# committed baseline.
TAILOR = False
TAILOR_RULES = None


def main():
    patterns = library.load()
    counts = frequency.load()
    scores = frequency.load_scores()
    entries = frequency.filter_entries(
        load("crossword/UKACD.txt", strict=False), counts, MIN_USES
    )
    index = Index(entries, SCORES if SCORES is not None else scores)
    bench = json.load(open(BENCH, encoding="utf-8"))["lists"]
    print(f"{len(patterns)} patterns, {len(bench)} lists, "
          f"{len(entries)} fill words (min_uses={MIN_USES}, "
          f"commonness={COMMONNESS})\n")

    rows = []
    familiar = []
    start = time.time()
    for item in bench:
        began = time.time()
        pool = patterns
        if TAILOR:
            pool = mutate.candidates(patterns, item["words"], TAILOR_RULES)
        got = coverage.best_over_library(
            pool, index, item["words"], top=14, attempts=3, budget=6000,
            time_limit=45.0, commonness=COMMONNESS,
            quality_scan=QUALITY_SCAN, seed=0
        )
        # Fill quality: the words we chose, not the targets we were given.
        quality = None
        if got.ok:
            placed = set(got.placed)
            fill = [got.grid.pattern(sl) for sl in got.grid.slots(3)
                    if got.grid.pattern(sl) not in placed]
            # Unknown to BOTH sources: never published as an answer and absent
            # from general English.  A word failing only one test is not the
            # kind that embarrasses a setter.
            quality = sum(1 for w in fill
                          if not counts.get(w) and not scores.get(w)) / len(fill)
            familiar.append(got.quality)
        rows.append((item, got, time.time() - began, quality))
        flag = "" if got.ok else "  <- did not fill"
        print(
            f"  {item['id']:16} {got.n:3}/{got.ceiling:<3} of {item['size']:2} "
            f"({got.score:4.0%}) {time.time() - began:5.1f}s{flag}"
        )

    print(f"\ntotal {time.time() - start:.0f}s\n")

    print(f"{'stratum':11} {'lists':>6} {'mean cov':>9} {'filled':>8} {'mean ceiling':>13}")
    by = collections.defaultdict(list)
    for item, got, _t, _q in rows:
        by[item["stratum"]].append((item, got))
    for stratum in ("feasible", "realistic", "arbitrary", "theme"):
        group = by.get(stratum, [])
        if not group:
            continue
        print(
            f"{stratum:11} {len(group):>6} "
            f"{statistics.mean(g.score for _i, g in group):>8.0%} "
            f"{sum(1 for _i, g in group if g.ok):>4}/{len(group):<3} "
            f"{statistics.mean(g.ceiling / i['size'] for i, g in group):>12.0%}"
        )

    print(f"\n{'size':>6} {'mean cov':>9} {'filled':>8}")
    by_size = collections.defaultdict(list)
    for item, got, _t, _q in rows:
        if item["stratum"] != "theme":
            by_size[item["size"]].append(got)
    for size in sorted(by_size):
        group = by_size[size]
        print(
            f"{size:>6} {statistics.mean(g.score for g in group):>8.0%} "
            f"{sum(1 for g in group if g.ok):>4}/{len(group):<3}"
        )

    unpublished = [q for _i, _g, _t, q in rows if q is not None]
    print(f"\nfill quality: {statistics.mean(unpublished):.1%} of chosen fill "
          f"words are unknown to both sources "
          f"(worst grid {max(unpublished):.0%}); "
          f"mean familiarity {statistics.mean(familiar):.3f} "
          f"(worst grid {min(familiar):.2f})")

    controls = by.get("feasible", [])
    perfect = sum(1 for _i, g in controls if g.ok and g.n == g.ceiling)
    print(
        f"\ncontrols: {perfect}/{len(controls)} reached the known optimum. "
        "These are the ones that must be 100%; the rest are diagnostics."
    )


if __name__ == "__main__":
    main()
