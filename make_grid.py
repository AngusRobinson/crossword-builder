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


# How hard to look.  Every one of these was a constant buried in make_grid or
# defaulted in the search; the levels move them together, because raising one
# alone tends to spend time without buying anything -- more patterns with too
# few attempts each, or more attempts on too narrow a shortlist.
#
#   top          library grids on the shortlist
#   attempts     seating restarts per grid
#   budget       nodes for the seating branch and bound
#   quality_scan grids tried past the coverage optimum, for a better fill
#   seeds/beam/steps/width   how widely breeding explores
EFFORT = {
    "quick": dict(top=6, attempts=1, budget=1500, quality_scan=0,
                  seeds=2, beam=2, steps=2, width=4, time_limit=15.0),
    "normal": dict(top=14, attempts=3, budget=6000, quality_scan=4,
                   seeds=4, beam=3, steps=3, width=6, time_limit=45.0),
    "deep": dict(top=40, attempts=6, budget=20000, quality_scan=8,
                 seeds=8, beam=4, steps=4, width=8, time_limit=300.0),
    "exhaustive": dict(top=120, attempts=10, budget=60000, quality_scan=16,
                       seeds=12, beam=6, steps=5, width=10, time_limit=1200.0),
}


# Informational output goes through this rather than straight to print, so
# --quiet can silence it. Errors keep using print(..., file=sys.stderr): a
# quiet run still has to say why it failed.
_QUIET = False


def say(*args, **kwargs):
    if not _QUIET:
        print(*args, **kwargs)


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


def nina_placer(cells, text, exact: bool = False):
    """Build the per-pattern rule cover() needs.

    The message takes the white cells from the start of the path onward, so a
    short one sits in the first corner and a full-length one reads the whole
    way round.  A grid with too few white cells on the path cannot carry it.

    `exact` demands that the message use every white cell on the path, which
    is what a perimeter nina means: a circuit that stops three quarters of the
    way round is not one.  For an open path like a single row, stopping early
    is fine and exact is off.
    """
    path = list(cells)

    def place(pattern):
        white = [c for c in path if c not in pattern.blocks]
        if len(white) < len(text) or (exact and len(white) != len(text)):
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
        if len(folded) < 3 or len(folded) > args.max_target:
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
    parser.add_argument("--effort", choices=tuple(EFFORT), default="normal",
                        help="how hard to look. quick is for trying an idea "
                             "out. deep and exhaustive widen everything and "
                             "measurably do not help -- on the benchmark's "
                             "hardest lists they were flat or worse (16, 15, "
                             "14 of 18 for normal, deep, exhaustive) while "
                             "taking ten times as long. To search harder, run "
                             "several --seed values at normal instead")
    parser.add_argument("--tries", type=int, default=3, metavar="N",
                        help="run the search N times from consecutive seeds "
                             "and keep the best (default 3). Measured over "
                             "dense lists, one run averages 88%% of the "
                             "achievable coverage, two 94%%, three 96.5%%, and "
                             "beyond four nothing changes. Each try gets its "
                             "own --time-limit, so N tries takes N times as "
                             "long")
    parser.add_argument("--seed", type=int, default=0,
                        help="the first seed; --tries counts up from it. "
                             "Same seed and settings give the same grid")
    parser.add_argument("--time-limit", type=float, default=None,
                        help="seconds to spend searching (default 45)")
    parser.add_argument("--patterns", type=int, default=None,
                        help="how many grids from the library to try; "
                             "overrides whatever --effort would have chosen")
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
    parser.add_argument("--style", choices=("british", "us", "barred"),
                        default="british",
                        help="british (default): about half the letters "
                             "unchecked, 120 grids from published Guardian "
                             "puzzles. us: every letter checked, 1,200 grids "
                             "from pre-1965 New York Times puzzles, roughly "
                             "74 entries against 28. barred: 12x12 Mephisto "
                             "shape, no blocks at all, entries of four letters "
                             "and up separated by bars")
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
    # Not --words: that collides with the positional `words`, which is the
    # list of target answers, and argparse would quietly let the dictionary
    # path overwrite it.
    parser.add_argument("--dictionary", metavar="PATH", default=WORDLIST,
                        help=f"the fill dictionary (default {WORDLIST}). "
                             "build_wiktionary.py makes a larger one; the "
                             "familiarity settings are calibrated for UKACD, "
                             "so --aim may want re-deriving for another")
    parser.add_argument("--library", metavar="PATH",
                        help="read grid patterns from this file instead of "
                             "the one the style ships with. This is how a "
                             "non-standard size is used: build_barred_library.py "
                             "--size N writes one, and any size works")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="print nothing but errors. The grid is still "
                             "written by --out, so this is the mode for "
                             "scripting: run it, then read the file")
    parser.add_argument("--blank", action="store_true",
                        help="write the puzzle without its answers. Applies to "
                             "the HTML page a barred grid is written to; the "
                             "ipuz and Exolve files always carry the solution, "
                             "because that is what the format is for")
    parser.add_argument("--nina-exact", action="store_true",
                        help="make the message fill the whole path, using "
                             "every white cell on it rather than starting at "
                             "one end and stopping where it runs out. Always "
                             "on for a perimeter, since a circuit that stops "
                             "three quarters of the way round is not one; "
                             "worth asking for on a diagonal, where it is the "
                             "difference between a message down the diagonal "
                             "and a message occupying the whole of it")
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
    global _QUIET
    _QUIET = args.quiet

    # Targets may be as long as the biggest grid on offer, which is only 15
    # for the standard libraries but 21 for a 23x23 jumbo.
    args.max_target = 15
    if args.library:
        args.max_target = max(15, library.load(args.library,
                                               style=args.style)[0].size - 2)
    targets, dropped, spelling = read_targets(args)
    for word, why in dropped:
        print(f"skipped {word!r}: {why}", file=sys.stderr)
    if not targets:
        # No theme words is a real request, not a mistake: --pangram, --nina
        # and the fill-quality settings all give the grid something to be
        # without a single target in it.  Everything downstream already copes
        # -- an empty target list simply seats nothing and fills the grid.
        say("no target words: filling a grid on its own merits",
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
        # A perimeter message must close the circuit; an open path need not,
        # unless the setter asks for it.
        exact = (args.nina_exact
                 or args.nina_path.split(",")[0].strip().lower() == "perimeter")
        placer = nina_placer(path_cells, message, exact=exact)

    patterns = library.load(args.library, style=args.style)
    style_rules = library.rules_for(args.style)
    if placer:
        patterns = [p for p in patterns if placer(p) is not None]
        if not patterns:
            # Say which lengths would have worked.  For a perimeter the
            # message has to close the circuit exactly, so the viable lengths
            # are few and specific, and guessing at them is miserable.
            options = {}
            for candidate in library.load():
                white = sum(1 for c in path_cells if c not in candidate.blocks)
                clean = not [s for s in candidate.grid().slots(3)
                             if set(s.cells) <= set(path_cells)]
                options.setdefault(white, [0, 0])
                options[white][0] += 1
                options[white][1] += clean
            # Best first: a length whose grids have no entry lying along the
            # path is worth far more than one with many grids, because those
            # are the grids where the message is hidden by construction and
            # forces no entry to be anything.
            ranked = sorted(options, key=lambda n: (-options[n][1],
                                                    -options[n][0]))[:6]
            lengths = "\n    ".join(
                f"{n:>2} letters -- {options[n][0]:>2} grids, "
                f"{options[n][1]:>2} of them with no entry along the edge"
                for n in ranked)
            parser.error(
                f"no grid takes a {len(message)}-letter message on that path."
                f"\n  a perimeter message must use every white cell, so it "
                f"has to be exactly one of:\n    {lengths}")
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
    # The dictionary has to reach the longest entry any grid in the library
    # offers. A 15x15 never needs more than 15, but a 21x21 jumbo has
    # nineteen-letter entries and a 23x23 has twenty-one.
    longest = max((s.length for p in patterns for s in
                   p.grid().slots(style_rules.min_entry_length)), default=15)
    entries = load(args.dictionary, strict=False, max_length=max(15, longest))
    counts = frequency.load()
    scores = frequency.load_scores()
    kept = frequency.select(entries, scores, counts,
                            min_score=args.min_score, max_uses=args.max_uses)
    if len(kept) < 5000:
        parser.error(f"those limits leave only {len(kept)} fill words")
    say(f"fill dictionary: {len(kept)} words "
        f"(floor {args.min_score}"
        + (f", ceiling {args.max_uses}" if args.max_uses is not None else "")
        + ")", file=sys.stderr)
    index = Index(kept, scores)

    began = time.time()
    effort = dict(EFFORT[args.effort])
    limit = args.time_limit if args.time_limit is not None else effort.pop("time_limit")
    effort.pop("time_limit", None)
    breeding = {k: effort.pop(k) for k in ("seeds", "beam", "steps", "width")}
    if args.patterns is not None:
        effort["top"] = args.patterns
    common = dict(commonness=args.commonness, aim=args.aim,
                  pangram=args.pangram, **effort)

    # The rules breeding must keep, so a bred grid is still one a setter would
    # print.  The British family is tighter than the plain rule set: its grids
    # alternate checked and unchecked cells, which no rule about fractions can
    # express.  American grids have no such lattice, so their own rule set is
    # the whole constraint.
    breed_rules = (RuleSet(alternating=True, max_checked_fraction=0.5)
                   if args.style == "british" else style_rules)

    # Breeding moves blocks, and a barred grid has none: every neighbour it
    # could propose is a different puzzle style rather than a variation on this
    # one.  The library is the whole search space here, which is affordable
    # because each pattern in it was filled once before it was let in.
    if args.style == "barred":
        args.no_tailor = True

    def once(seed):
        # Breeding exists to fit a word list, so with no list there is nothing
        # to breed towards and it is pure cost.
        if args.no_tailor or not targets:
            return coverage.best_over_library(
                patterns, index, targets, style_rules, seed=seed,
                time_limit=limit, preset=placer or nina, **common)
        return mutate.best_with_tailoring(
            patterns, index, targets, breed_rules, fill_rules=style_rules,
            min_long=args.long, preset=placer or nina, seed=seed,
            time_limit=limit, **breeding, **common)

    # The same list run twice gives different answers, and by a lot: across 12
    # dense lists at 8 seeds each, one run averaged 88.4% of the achievable
    # coverage and the best of three 96.5%.  Four runs cleared the last of the
    # unrecognised fill words.  Beyond that nothing changes, so three is the
    # default and the fifth try onwards is wasted time.
    got, spread = None, []
    for step in range(args.tries):
        # Strided, so that two runs launched with different --seed explore
        # different searches rather than overlapping in all but one try.
        attempt = once(args.seed * 1_000_003 + step)
        spread.append(attempt.n if attempt.ok else None)
        if got is None or (attempt.ok, attempt.n, attempt.quality) > (
                got.ok, got.n, got.quality):
            got = attempt
    elapsed = time.time() - began

    if not got.ok:
        print(f"\nno complete grid found for these {len(targets)} words "
              f"in {elapsed:.0f}s.", file=sys.stderr)
        print("try fewer words, a longer --time-limit, or a different --seed.",
              file=sys.stderr)
        return 1

    say()
    say(got.grid.pretty(block="█"))
    say()

    placed = set(got.placed)
    where = {}
    for slot in got.grid.slots(3):
        word = got.grid.pattern(slot)
        if word in placed:
            where[word] = f"{slot.direction} at row {slot.row + 1}, col {slot.col + 1}"

    if args.tries > 1 and targets:
        shown = ", ".join("-" if n is None else str(n) for n in spread)
        say(f"{args.tries} tries placed [{shown}] -- keeping the best")
    if targets:
        say(f"placed {got.n} of {len(targets)} targets "
              f"({got.score:.0%} of the {got.ceiling} that could fit this "
              f"library) in {elapsed:.0f}s")
    else:
        say(f"filled in {elapsed:.0f}s")
    for word in sorted(placed):
        say(f"   {word:18} {where.get(word, '')}")
    missed = [w for w in targets if w not in placed]
    if missed:
        # A long theme list leaves a long remainder, and printing four hundred
        # words buries everything above it. Naming a dozen makes the point.
        shown = sorted(missed)[:12]
        tail = f", and {len(missed) - len(shown)} more" if len(missed) > 12 else ""
        say(f"could not place {len(missed)} of {len(targets)}: "
            f"{', '.join(shown)}{tail}")
    if got.pattern is not None:
        say(f"grid: library pattern {got.pattern.source} "
              f"(used by {got.pattern.uses} published puzzles)")

    # How ordinary the words we chose ourselves are.  Targets are excluded:
    # they were the setter's choice and are not the fill's to answer for.
    fill = [got.grid.pattern(s) for s in got.grid.slots(style_rules.min_entry_length)
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
    say(f"fill: {len(fill)} words, familiarity rank {typical:.2f} "
          f"(published answers average 0.86), "
          f"{len(unknown)} unknown to both sources"
          # Truncated, and it has to say so: "7 unknown" beside a list of six
          # reads as a miscount rather than as an abridgement.
          + (f" ({', '.join(sorted(unknown)[:6])}"
             + (", ..." if len(unknown) > 6 else "") + ")" if unknown else ""))

    if args.pangram:
        import collections as _c
        seen = _c.Counter("".join(got.grid.letters.values()))
        import string as _s
        short = [c for c in _s.ascii_lowercase if seen[c] < args.pangram]
        word = {1: "pangram", 2: "double pangram", 3: "triple pangram"}[args.pangram]
        say(f"{word}: " + ("achieved" if not short
                             else "NOT achieved, short of " + "".join(short)))

    if placer:
        landed = placer(got.pattern) if got.pattern is not None else None
        if landed is None:
            # The winning grid came from the library list, which was filtered,
            # so this should not happen; say so rather than printing nothing.
            say("nina path: could not be placed -- this is a bug")
        else:
            held = all(got.grid.letters.get(c) == ch for c, ch in landed.items())
            reading = "".join(got.grid.letters.get(c, "?") for c in path_cells
                              if c in landed)
            say(f"nina path: {reading.upper()} "
                  + ("(held)" if held else "NOT HELD -- this is a bug"))

    if nina:
        shown = "".join(sorted(f"{got.grid.letters.get(c, '?')}" for c in nina))
        held = all(got.grid.letters.get(c) == ch for c, ch in nina.items())
        say(f"nina: {len(nina)} cells fixed, "
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
            say(f"WARNING: this is not hidden -- the cells are exactly "
                  f"{len(whole)} whole entries "
                  f"({', '.join(got.grid.pattern(s).upper() for s in whole)}), "
                  f"so reading them just reads those answers")
        else:
            say(f"hidden: spans {touched} entries, "
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
            say(f"WARNING: {len(nonsense)} entries are fixed entirely by the "
                  f"nina and are not words: {', '.join(sorted(nonsense))}")
            say("         a message has to break into real words at the "
                  "entry boundaries")

    problems = validate(got.grid, style_rules)
    say("rules:", "clean" if not problems else f"{len(problems)} VIOLATIONS")

    if args.out and args.style == "barred":
        # Neither puzzle format here can place a bar, and a barred grid written
        # into one would describe a different puzzle. A drawn page can carry
        # it, so that is what barred grids get.
        surfaces = {e.text: e.surface for e in kept}
        surfaces.update(spelling)
        export.write_html(got.grid, args.out + ".html", title=args.title,
                          setter=args.setter, surfaces=surfaces,
                          min_length=style_rules.min_entry_length,
                          solution=not args.blank, themed=placed)
        say(f"wrote {args.out}.html "
              f"(no ipuz or Exolve: neither format can place a bar)")
    elif args.out:
        # The setter's own spelling wins over the dictionary's: they typed
        # "Twelfth Night", and the enumeration a solver sees should say (7,5).
        surfaces = {e.text: e.surface for e in kept}
        surfaces.update(spelling)
        export.write_ipuz(got.grid, args.out + ".ipuz", title=args.title,
                          author=args.setter, surfaces=surfaces)
        export.write_exolve(got.grid, args.out + ".html", title=args.title,
                            setter=args.setter, surfaces=surfaces)
        say(f"wrote {args.out}.ipuz and {args.out}.html")
    if args.solution:
        say()
        # `render` is the blocked-grid form and has nowhere to put a bar, so a
        # barred solution printed through it reads as twelve-letter rows that
        # are not words.  The compact `pretty` keeps the separators.
        if args.style == "barred":
            say(got.grid.pretty(gap="", upper=False))
        else:
            say(got.grid.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
