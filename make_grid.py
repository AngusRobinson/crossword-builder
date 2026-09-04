"""Build a grid around a list of words.

    python3 make_grid.py mercury venus earth mars jupiter saturn
    python3 make_grid.py --file mywords.txt
    echo "kestrel curlew avocet" | python3 make_grid.py

Words may be given as arguments, in a file (one per line, or separated by
commas or spaces), or on stdin.  Case, spaces, hyphens and accents are all
folded away, so "Twelfth Night" and "twelfthnight" are the same target.

Prints the filled grid, says where each target went, and names any it could
not place.  Exit status is 1 if no grid could be built at all.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

from crossword import coverage, export, frequency, library, mutate
from crossword.index import Index
from crossword.rules import RuleSet, validate
from crossword.words import _fold, load

WORDLIST = "crossword/UKACD.txt"


def read_targets(args) -> list:
    raw = list(args.words)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            raw.extend(re.split(r"[,\n]", handle.read()))
    if not raw and not sys.stdin.isatty():
        raw.extend(re.split(r"[,\n]", sys.stdin.read()))

    # Split on lines and commas only, never on spaces: a multi-word answer is
    # one target.  "Twelfth Night" is a twelve-letter entry, not a seven and
    # a five, and splitting it produced a spurious three-letter "the" from
    # "The Tempest".
    targets, dropped, spelling = [], [], {}
    for item in raw:
        folded = _fold(item)
        if not folded:
            continue
        if len(folded) < 3 or len(folded) > 15:
            dropped.append((item.strip(), f"{len(folded)} letters after folding"))
        elif folded not in targets:
            targets.append(folded)
            spelling[folded] = item.strip()
    return targets, dropped, spelling


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a crossword grid around a list of target words."
    )
    parser.add_argument("words", nargs="*", help="target words")
    parser.add_argument("--file", help="read targets from a file")
    parser.add_argument("--seed", type=int, default=0, help="0 for repeatable runs")
    parser.add_argument("--time-limit", type=float, default=45.0,
                        help="seconds to spend searching (default 45)")
    parser.add_argument("--patterns", type=int, default=14,
                        help="how many grids from the library to try")
    parser.add_argument("--min-score", type=float, default=0.0, metavar="S",
                        help="floor: refuse fill words with a familiarity "
                             "below S. 0 allows everything, 1.0 leaves 84,268 "
                             "words, 2.0 leaves 33,687 and is too thin to "
                             "fill 15-letter slots reliably. A hard cut costs "
                             "coverage; prefer --commonness first")
    parser.add_argument("--max-uses", type=int, default=None, metavar="N",
                        help="ceiling: refuse fill words used as a Guardian "
                             "answer more than N times, to keep tired "
                             "crosswordese out. 20 removes 684 words (isle, "
                             "extra, star, blue, bridge, echo, stud)")
    parser.add_argument("--commonness", type=float, default=3.0, metavar="F",
                        help="how hard to prefer words that have been "
                             "published as answers, 0 for no preference "
                             "(default 3.0; above 4 makes little difference)")
    parser.add_argument("--long", type=int, default=0, metavar="N",
                        help="require at least N entries of 11+ letters. "
                             "Default 0. Long entries are the hardest to fill, "
                             "so this costs coverage. Of the 120 library "
                             "grids, 85 have one, 76 have two, 46 have three "
                             "and only 6 have five")
    parser.add_argument("--no-tailor", action="store_true",
                        help="skip breeding grids to fit your words. Faster "
                             "(about a third of the time) and a little worse: "
                             "on the benchmark, tailoring gains 5 points of "
                             "coverage on 18-word lists and cuts unfamiliar "
                             "fill from 7.8%% to 5.2%%")
    parser.add_argument("--out", metavar="BASE",
                        help="write BASE.ipuz and BASE.html (Exolve). ipuz is "
                             "what Exet imports; the HTML opens in a browser")
    parser.add_argument("--title", default="Untitled", help="puzzle title")
    parser.add_argument("--setter", default="", help="setter's name")
    parser.add_argument("--solution", action="store_true",
                        help="also print the grid as plain text")
    args = parser.parse_args()

    targets, dropped, spelling = read_targets(args)
    for word, why in dropped:
        print(f"skipped {word!r}: {why}", file=sys.stderr)
    if not targets:
        parser.error("no usable target words given")

    patterns = library.load()
    if args.long:
        patterns = [p for p in patterns
                    if mutate.long_entries(p.grid()) >= args.long]
        if len(patterns) < 5:
            parser.error(f"--long {args.long} leaves only {len(patterns)} grids; "
                         f"try a smaller number")
        print(f"grids with {args.long}+ long entries: {len(patterns)} of 120",
              file=sys.stderr)
    entries = load(WORDLIST, strict=False)
    counts = frequency.load()
    scores = frequency.load_scores()
    kept = frequency.select(entries, scores, counts,
                            min_score=args.min_score, max_uses=args.max_uses)
    if len(kept) < 5000:
        parser.error(f"those limits leave only {len(kept)} fill words")
    print(f"fill dictionary: {len(kept)} words "
          f"(floor {args.min_score}"
          + (f", ceiling {args.max_uses}" if args.max_uses is not None else "")
          + ")", file=sys.stderr)
    index = Index(kept, scores)

    began = time.time()
    common = dict(top=args.patterns, attempts=3, budget=6000,
                  commonness=args.commonness, seed=args.seed)
    if args.no_tailor:
        got = coverage.best_over_library(
            patterns, index, targets, time_limit=args.time_limit, **common)
    else:
        # The rules the breeding must keep: the British family the library
        # grids belong to, so a bred grid is still one a setter would print.
        british = RuleSet(alternating=True, max_checked_fraction=0.5)
        got = mutate.best_with_tailoring(
            patterns, index, targets, british, min_long=args.long,
            time_limit=args.time_limit, **common)
    elapsed = time.time() - began

    if not got.ok:
        print(f"\nno complete grid found for these {len(targets)} words "
              f"in {elapsed:.0f}s.", file=sys.stderr)
        print("try fewer words, a longer --time-limit, or a different --seed.",
              file=sys.stderr)
        return 1

    print()
    print(got.grid.pretty(block="█"))
    print()

    placed = set(got.placed)
    where = {}
    for slot in got.grid.slots(3):
        word = got.grid.pattern(slot)
        if word in placed:
            where[word] = f"{slot.direction} at row {slot.row + 1}, col {slot.col + 1}"

    print(f"placed {got.n} of {len(targets)} targets "
          f"({got.score:.0%} of the {got.ceiling} that could fit this library) "
          f"in {elapsed:.0f}s")
    for word in sorted(placed):
        print(f"   {word:18} {where.get(word, '')}")
    missed = [w for w in targets if w not in placed]
    if missed:
        print(f"could not place: {', '.join(sorted(missed))}")
    if got.pattern is not None:
        print(f"grid: library pattern {got.pattern.source} "
              f"(used by {got.pattern.uses} published puzzles)")

    # How ordinary the words we chose ourselves are.  Targets are excluded:
    # they were the setter's choice and are not the fill's to answer for.
    fill = [got.grid.pattern(s) for s in got.grid.slots(3)
            if got.grid.pattern(s) not in placed]
    unpublished = [w for w in fill if not counts.get(w)]
    unknown = [w for w in fill if not counts.get(w) and not scores.get(w)]
    # got.quality is measured against the average for each word's own length,
    # so 0 is "typical for its length" and the sign is what to read.
    print(f"fill: {len(fill)} words, {got.quality:+.2f} vs typical for their "
          f"length, {len(unknown)} unknown to both sources"
          + (f" ({', '.join(sorted(unknown)[:6])})" if unknown else ""))

    problems = validate(got.grid)
    print("rules:", "clean" if not problems else f"{len(problems)} VIOLATIONS")

    if args.out:
        # The setter's own spelling wins over the dictionary's: they typed
        # "Twelfth Night", and the enumeration a solver sees should say (7,5).
        surfaces = {e.text: e.surface for e in kept}
        surfaces.update(spelling)
        export.write_ipuz(got.grid, args.out + ".ipuz", title=args.title,
                          author=args.setter, surfaces=surfaces)
        export.write_exolve(got.grid, args.out + ".html", title=args.title,
                            setter=args.setter, surfaces=surfaces)
        print(f"wrote {args.out}.ipuz and {args.out}.html")
    if args.solution:
        print()
        print(got.grid.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
