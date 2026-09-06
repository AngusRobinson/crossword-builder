"""Word squares, of both kinds.

A **double** word square has words across and words down, all different:

    R O S I E R      reading down: RELISH, OMENTA, SUNTAN,
    E M U N G E                   INTEND, EGENCE, RENTED
    L E N T E N
    I N T E N T
    S T A N C E
    H A N D E D

An **ordinary** word square is the symmetric kind, where the rows and the
columns read the same:

    P A S T E R S
    A T T A B O Y
    S T I R R U P
    T A R T I S H
    E B R I A T E
    R O U S T E R
    S Y P H E R S

The two are solved by different code, which is the interesting part. A double
square is a barred grid with no bars -- every across run is the full width,
every down run the full height -- so the ordinary filler makes one with nothing
added. An ordinary square cannot be posed that way at all: it needs
grid[r][c] == grid[c][r], a constraint between two cells, where everything the
filler knows how to say is a constraint between a cell and a word. So it has
its own small solver in crossword/square.py.

    python3 word_square.py 6
    python3 word_square.py 7 --kind double --tries 500

Phrases are excluded by default. UKACD normalises punctuation away, so "it'll"
arrives as ITLL and "ro-ros" as ROROS; in a crossword such an entry is rare
enough to catch by eye, but a word square is nothing but entries.
"""

import argparse
import sys
import time

from crossword.fill import Filler
from crossword.grid import Grid
from crossword.index import Index
from crossword.rules import RuleSet
from crossword.square import find, is_square
from crossword.words import load


def double(size, index, *, seed=0, node_budget=8000, restarts=1,
           commonness=0.0, aim=0.85):
    """One n x n grid whose rows and columns are all words."""
    rules = RuleSet(min_entry_length=size, min_checked_fraction=1.0,
                    max_consecutive_unchecked=0, symmetry="none")
    grid = Grid(size=size)
    filler = Filler(grid, index, rules=rules, seed=seed,
                    node_budget=node_budget, commonness=commonness, aim=aim)
    if filler.fill(restarts=restarts):
        return [grid.pattern(s) for s in grid.runs("across")], filler.stats.nodes
    return None, filler.stats.nodes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("size", type=int)
    parser.add_argument("--kind", choices=("ordinary", "double"),
                        default="ordinary",
                        help="ordinary (default): rows and columns read the "
                             "same. double: rows and columns are different "
                             "words")
    parser.add_argument("--words", default="crossword/UKACD.txt")
    # Many short tries, not one long one. The search is heavily tailed: the
    # try that succeeds does so in a few thousand nodes, and the ones that do
    # not are not going to.
    parser.add_argument("--effort", type=int, default=20000,
                        help="node budget per try (default 20,000)")
    parser.add_argument("--tries", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--commonness", type=float, default=0.0,
                        help="0 takes any word; raise it to prefer familiar "
                             "ones, which at these sizes often means no square "
                             "at all")
    parser.add_argument("--aim", type=float, default=0.85)
    parser.add_argument("--branch-cap", type=int, default=200,
                        help="how many candidate words to consider at each "
                             "step (default 200). Raising it did not help at "
                             "8x8, but it costs little to try")
    parser.add_argument("--report", type=int, default=0, metavar="N",
                        help="print progress to stderr every N tries, so a "
                             "long search shows it is still going")
    parser.add_argument("--proper", action="store_true",
                        help="allow capitalised entries, which is how the "
                             "larger squares in the literature are built")
    parser.add_argument("--allow-phrases", action="store_true",
                        help="admit ITLL and ROROS and their friends")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    entries = load(args.words, min_length=args.size, max_length=args.size,
                   allow_phrases=args.allow_phrases, allow_proper=args.proper)
    if not args.quiet:
        print(f"{len(entries):,} words of exactly {args.size} letters",
              file=sys.stderr)
    index = Index(entries)

    began = time.time()

    def report(attempt, nodes):
        if args.report and attempt % args.report == 0:
            rate = nodes / max(1e-9, time.time() - began)
            print(f"  {attempt:,} tries, {nodes:,} nodes, "
                  f"{time.time() - began:.0f}s ({rate:,.0f} nodes/s)",
                  file=sys.stderr, flush=True)

    if args.kind == "ordinary":
        rows, tries, nodes = find(args.size, index, tries=args.tries,
                                  node_budget=args.effort, seed=args.seed,
                                  commonness=args.commonness, aim=args.aim,
                                  branch_cap=args.branch_cap,
                                  on_try=report if args.report else None)
    else:
        rows, nodes, tries = None, 0, 0
        for step in range(args.tries):
            tries = step + 1
            rows, spent = double(args.size, index, seed=args.seed + step,
                                 node_budget=args.effort,
                                 commonness=args.commonness, aim=args.aim)
            nodes += spent
            if rows:
                break

    if rows is None:
        print(f"no {args.kind} square in {args.tries} tries and "
              f"{time.time() - began:.0f}s. Raise --effort or --tries.",
              file=sys.stderr)
        return 1

    if args.kind == "ordinary":
        assert is_square(rows), "not symmetric"
    if not args.quiet:
        print(f"found in {time.time() - began:.1f}s "
              f"({nodes:,} nodes, try {tries})\n", file=sys.stderr)
    for row in rows:
        print(" ".join(row.upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
