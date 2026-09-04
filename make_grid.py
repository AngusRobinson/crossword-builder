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


# How each direction walks the grid, as (row step, column step).  Diagonals
# are the interesting ones for a nina: a straight run of six sits inside one
# or two entries and constrains them hard, while a diagonal of nine touches
# nine different entries by one letter each.  It is a tighter fit on the grid
# and a looser one on the fill.
STEPS = {
    "across": (0, 1),
    "down": (1, 0),
    "diagonal": (1, 1),          # top-left to bottom-right
    "antidiagonal": (1, -1),     # top-right to bottom-left
    "up": (-1, 0),
    "back": (0, -1),             # right to left, for a nina read backwards
}


def _perimeter(size):
    return ([(0, c) for c in range(size)]
            + [(r, size - 1) for r in range(1, size)]
            + [(size - 1, c) for c in range(size - 2, -1, -1)]
            + [(r, 0) for r in range(size - 2, 0, -1)])


# Paths a message can be laid along, skipping whatever cells are blocked.
PATHS = {
    "perimeter": _perimeter,
    "toprow": lambda n: [(0, c) for c in range(n)],
    "bottomrow": lambda n: [(n - 1, c) for c in range(n)],
    "leftcol": lambda n: [(r, 0) for r in range(n)],
    "rightcol": lambda n: [(r, n - 1) for r in range(n)],
    "diagonal": lambda n: [(i, i) for i in range(n)],
    "antidiagonal": lambda n: [(i, n - 1 - i) for i in range(n)],
}


def read_nina_path(spec, size: int = 15):
    """A message laid along a path, skipping the blocked cells.

    This is what a perimeter nina actually is.  Fixing absolute cells cannot
    express one: a 15x15 perimeter is 56 cells and only 3 of the 120 published
    grids leave all of them open, while 34 leave 52 open.  Setters read the
    message off the white squares and let the blocks interrupt it, so the
    letters have to be placed relative to the grid rather than to the frame.

    Returns (path cells, folded message).
    """
    name, _, letters = spec.partition(",")
    name = name.strip().lower()
    if name not in PATHS:
        raise ValueError(f"path must be one of {', '.join(sorted(PATHS))}, "
                         f"not {name!r}")
    text = _fold(letters)
    if not text:
        raise ValueError(f"no letters in {spec!r}")
    cells = PATHS[name](size)
    if len(text) > len(cells):
        raise ValueError(f"{name} has {len(cells)} cells, message has "
                         f"{len(text)} letters")
    return cells, text


def nina_placer(cells, text):
    """Build the per-pattern rule cover() needs.

    The message takes the white cells from the start of the path onward, so a
    short one sits in the first corner and a full-length one reads the whole
    way round.  A grid with too few white cells on the path simply cannot
    carry it.
    """
    path = list(cells)

    def place(pattern):
        white = [c for c in path if c not in pattern.blocks]
        if len(white) < len(text):
            return None
        return dict(zip(white, text))

    return place


def read_nina(specs, size: int = 15) -> dict:
    """Parse --nina arguments into a cell -> letter map.

    Rows and columns are given from 1, matching how placements are reported
    back, because a setter reading "across at row 9, col 10" and then writing
    a nina should not have to change counting systems halfway.
    """
    preset: dict = {}
    for spec in specs:
        parts = [p.strip() for p in spec.split(",")]
        if len(parts) != 4:
            raise ValueError(f"expected ROW,COL,DIR,LETTERS but got {spec!r}")
        row_s, col_s, direction, letters = parts
        direction = direction.lower()
        if direction not in STEPS:
            raise ValueError(f"direction must be one of "
                             f"{', '.join(sorted(STEPS))}, not {direction!r}")
        try:
            row, col = int(row_s) - 1, int(col_s) - 1
        except ValueError:
            raise ValueError(f"row and column must be numbers in {spec!r}")

        text = _fold(letters)
        if not text:
            raise ValueError(f"no letters in {spec!r}")
        down_step, across_step = STEPS[direction]
        for step, char in enumerate(text):
            cell = (row + down_step * step, col + across_step * step)
            if not (0 <= cell[0] < size and 0 <= cell[1] < size):
                raise ValueError(f"{spec!r} runs off the grid at row "
                                 f"{cell[0] + 1}, col {cell[1] + 1}")
            if preset.get(cell, char) != char:
                raise ValueError(f"two ninas disagree at row {cell[0] + 1}, "
                                 f"col {cell[1] + 1}: "
                                 f"{preset[cell]!r} and {char!r}")
            preset[cell] = char
    return preset


def read_targets(args) -> list:
    raw = list(args.words)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            raw.extend(re.split(r"[,\n]", handle.read()))
    if not raw and not sys.stdin.isatty():
        # Read a pipe, but do not sit waiting on one that will never arrive.
        # `not isatty()` is true for any non-interactive context, including a
        # cron job or a background shell with no input at all, where a bare
        # read() blocks for ever.  Ask first.
        import select
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        except (OSError, ValueError):
            ready = []
        if ready:
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
                        help="how hard to steer towards --aim, 0 for no "
                             "preference at all (default 3.0)")
    parser.add_argument("--aim", type=float, default=0.85, metavar="Q",
                        help="what familiarity to aim at, as a rank within "
                             "each word's own length. 1.0 always takes the "
                             "most ordinary word available and fills the grid "
                             "with ISLE and OVER; published answers sit at "
                             "0.86 (default 0.85). Lower for a harder puzzle")
    parser.add_argument("--pangram", type=int, default=0, metavar="N",
                        help="require every letter of the alphabet N times. "
                             "1 is close to free, 2 costs some fill quality, "
                             "3 succeeds about one attempt in eight -- raise "
                             "--time-limit and try several seeds. Higher is "
                             "allowed and will simply be attempted, though 4 "
                             "and up have never succeeded here. A 15x15 holds "
                             "137-168 white cells, so 5x needs 130 and fits "
                             "any grid, 6x needs 156 and fits only the "
                             "roomiest, and 7x fits none")
    parser.add_argument("--nina", action="append", default=[],
                        metavar="ROW,COL,DIR,LETTERS",
                        help="fix letters before any word is chosen, e.g. "
                             "--nina 1,1,diagonal,LABYRINTH. Rows and columns "
                             "count from 1; DIR is across, down, diagonal, "
                             "antidiagonal, up or back. Repeat for several -- "
                             "two make a perimeter. A nina rules out every "
                             "grid that blocks one of its cells: a six-letter "
                             "column leaves 42 grids of 120, a nine-letter "
                             "diagonal 11")
    parser.add_argument("--nina-path", metavar="PATH,LETTERS",
                        help="lay a message along a path, skipping whatever "
                             "cells are blocked -- which is what a perimeter "
                             "nina actually is. PATH is one of "
                             + ", ".join(sorted(PATHS)) +
                             ". A 15x15 perimeter is 56 cells but only 3 of "
                             "the 120 grids leave all of them white, so fixed "
                             "cells cannot express one; 34 grids leave 52")
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
        # No theme words is a real request, not a mistake: --pangram, --nina
        # and the fill-quality settings all give the grid something to be
        # without a single target in it.  Everything downstream already copes
        # -- an empty target list simply seats nothing and fills the grid.
        print("no target words: filling a grid on its own merits",
              file=sys.stderr)

    if args.pangram < 0:
        parser.error("--pangram cannot be negative")
    if args.pangram:
        # 26 * N letters have to physically fit. The grid is not chosen yet,
        # so this uses the roomiest the library offers; a tighter grid will
        # simply fail to fill and say so.
        roomiest = max(225 - len(p.blocks) for p in library.load())
        if 26 * args.pangram > roomiest:
            parser.error(f"--pangram {args.pangram} needs {26 * args.pangram} "
                         f"cells but the roomiest grid has {roomiest}")

    try:
        nina = read_nina(args.nina)
    except ValueError as problem:
        parser.error(str(problem))

    placer = None
    if args.nina_path:
        if nina:
            parser.error("--nina and --nina-path cannot be combined; a path "
                         "message is positioned by the grid's blocks, so the "
                         "two would fight over the same cells")
        try:
            path_cells, message = read_nina_path(args.nina_path)
        except ValueError as problem:
            parser.error(str(problem))
        placer = nina_placer(path_cells, message)

    patterns = library.load()
    if placer:
        patterns = [p for p in patterns if placer(p) is not None]
        if not patterns:
            parser.error("no grid has enough white cells on that path")
        print(f"grids that can carry a {len(message)}-letter message there: "
              f"{len(patterns)} of 120", file=sys.stderr)
    if nina:
        patterns = [p for p in patterns if not (set(nina) & set(p.blocks))]
        if not patterns:
            parser.error("no grid in the library leaves all those cells open; "
                         "try a shorter nina or a different position")
        print(f"grids leaving the nina cells open: {len(patterns)} of 120",
              file=sys.stderr)
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
                  commonness=args.commonness, aim=args.aim,
                  pangram=args.pangram, seed=args.seed)
    # Breeding exists to fit a word list, so with no list there is nothing to
    # breed towards and it is pure cost.
    if args.no_tailor or not targets:
        got = coverage.best_over_library(
            patterns, index, targets, time_limit=args.time_limit,
            preset=placer or nina, **common)
    else:
        # The rules the breeding must keep: the British family the library
        # grids belong to, so a bred grid is still one a setter would print.
        british = RuleSet(alternating=True, max_checked_fraction=0.5)
        got = mutate.best_with_tailoring(
            patterns, index, targets, british, min_long=args.long,
            preset=placer or nina, time_limit=args.time_limit, **common)
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

    if targets:
        print(f"placed {got.n} of {len(targets)} targets "
              f"({got.score:.0%} of the {got.ceiling} that could fit this "
              f"library) in {elapsed:.0f}s")
    else:
        print(f"filled in {elapsed:.0f}s")
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
    ranks = []
    for word in fill:
        bucket = index.lengths.get(len(word))
        word_id = bucket.by_word.get(word) if bucket else None
        if bucket and bucket.quantile and word_id is not None:
            ranks.append(bucket.quantile[word_id])
    typical = sum(ranks) / len(ranks) if ranks else 0.0
    print(f"fill: {len(fill)} words, familiarity rank {typical:.2f} "
          f"(published answers average 0.86), "
          f"{len(unknown)} unknown to both sources"
          + (f" ({', '.join(sorted(unknown)[:6])})" if unknown else ""))

    if args.pangram:
        import collections as _c
        seen = _c.Counter("".join(got.grid.letters.values()))
        import string as _s
        short = [c for c in _s.ascii_lowercase if seen[c] < args.pangram]
        word = {1: "pangram", 2: "double pangram", 3: "triple pangram"}[args.pangram]
        print(f"{word}: " + ("achieved" if not short
                             else "NOT achieved, short of " + "".join(short)))

    if placer:
        landed = placer(got.pattern) if got.pattern is not None else None
        if landed is None:
            # The winning grid came from the library list, which was filtered,
            # so this should not happen; say so rather than printing nothing.
            print("nina path: could not be placed -- this is a bug")
        else:
            held = all(got.grid.letters.get(c) == ch for c, ch in landed.items())
            reading = "".join(got.grid.letters.get(c, "?") for c in path_cells
                              if c in landed)
            print(f"nina path: {reading.upper()} "
                  + ("(held)" if held else "NOT HELD -- this is a bug"))

    if nina:
        shown = "".join(sorted(f"{got.grid.letters.get(c, '?')}" for c in nina))
        held = all(got.grid.letters.get(c) == ch for c, ch in nina.items())
        print(f"nina: {len(nina)} cells fixed, "
              + ("all held" if held else "NOT HELD -- this is a bug"))

    # Entries the nina fixed outright are never checked against the
    # dictionary -- deliberately, since a themed entry is usually a proper
    # noun the fill list excludes.  For a path nina that exemption is a trap:
    # the perimeter cells are parts of real entries, so a message that does
    # not break into words at the entry boundaries leaves nonsense round the
    # edge.  Say which, rather than let it pass as a clean grid.
    fixed = placer(got.pattern) if placer else nina
    if fixed:
        # Is it actually hidden?  A nina is a message read where the solver
        # would not normally read: across entry boundaries, or in a direction
        # entries do not run.  If the cells are exactly a set of whole
        # entries, reading them reads those answers and conceals nothing --
        # MYSTERY and THEATRE along a top row that is two seven-letter entries
        # is not a nina, it is 1 and 5 Across.
        whole = [s for s in got.grid.slots(3) if set(s.cells) <= set(fixed)]
        covered = set()
        for slot in whole:
            covered |= set(slot.cells)
        exposed = set(fixed) - covered
        touched = len({id(s) for s in got.grid.slots(3)
                       for c in fixed if c in s.cells})
        if not exposed:
            print(f"WARNING: this is not hidden -- the cells are exactly "
                  f"{len(whole)} whole entries "
                  f"({', '.join(got.grid.pattern(s).upper() for s in whole)}), "
                  f"so reading them just reads those answers")
        else:
            print(f"hidden: spans {touched} entries, "
                  f"{len(exposed)} of {len(fixed)} letters not readable as a "
                  f"whole entry")

        nonsense = []
        for slot in got.grid.slots(3):
            if not all(c in fixed for c in slot.cells):
                continue
            word = got.grid.pattern(slot)
            bucket = index.lengths.get(len(word))
            if bucket is None or bucket.by_word.get(word) is None:
                nonsense.append(word)
        if nonsense:
            print(f"WARNING: {len(nonsense)} entries are fixed entirely by the "
                  f"nina and are not words: {', '.join(sorted(nonsense))}")
            print("         a message has to break into real words at the "
                  "entry boundaries")

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
