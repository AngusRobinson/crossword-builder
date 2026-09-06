"""Double word squares, using the filler unchanged.

A double word square is an n x n block of letters whose rows are all words and
whose columns are all words, the two sets being different.  There is nothing to
add for it: it is a barred grid with no bars.  Every across run is the whole
width, every down run the whole height, and every letter is checked twice,
which is the most constrained thing this project can be asked for and needs no
new code at all.

    python3 word_square.py 6
    python3 word_square.py 7 --tries 500

The *ordinary* word square, the symmetric kind where the rows and the columns
read the same, is a different problem and this will not produce one.  That
needs grid[r][c] == grid[c][r], a constraint the filler has no way to express,
because it is a relation between two cells rather than between a cell and a
word.

Phrases are excluded by default.  UKACD normalises punctuation away, so "it'll"
and "ro-ros" arrive as ITLL and ROROS and will otherwise cheerfully turn up in
a square, which is not what anyone means by a word.
"""

import argparse
import sys
import time

from crossword.grid import Grid
from crossword.index import Index
from crossword.rules import RuleSet
from crossword.fill import Filler
from crossword.words import load


def square(size, index, *, seed=0, node_budget=200000, restarts=3,
           commonness=0.0, aim=0.85):
    """One filled n x n grid, or None."""
    rules = RuleSet(min_entry_length=size, min_checked_fraction=1.0,
                    max_consecutive_unchecked=0, symmetry="none")
    grid = Grid(size=size)
    filler = Filler(grid, index, rules=rules, seed=seed,
                    node_budget=node_budget, commonness=commonness, aim=aim)
    if filler.fill(restarts=restarts):
        return grid, filler.stats
    return None, filler.stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("size", type=int)
    parser.add_argument("--words", default="crossword/UKACD.txt")
    # Many short tries, not one long one.  The search is heavily tailed here:
    # the try that succeeds does so in a few thousand nodes, and the ones that
    # do not are not going to.  At 6x6, sixty tries of 8,000 nodes found a
    # square in 39 seconds where six tries of 200,000 took 209.
    parser.add_argument("--effort", type=int, default=8000,
                        help="node budget per try (default 8,000)")
    parser.add_argument("--tries", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--commonness", type=float, default=0.0,
                        help="0 takes any word; raise it to prefer familiar "
                             "ones, which at these sizes usually means no "
                             "square at all")
    parser.add_argument("--allow-phrases", action="store_true",
                        help="admit ITLL and ROROS and their friends")
    args = parser.parse_args()

    entries = load(args.words, min_length=args.size, max_length=args.size,
                   allow_phrases=args.allow_phrases)
    print(f"{len(entries)} words of exactly {args.size} letters")
    index = Index(entries)

    began = time.time()
    for step in range(args.tries):
        grid, stats = square(args.size, index, seed=args.seed + step,
                             node_budget=args.effort,
                             commonness=args.commonness)
        if grid is not None:
            print(f"\nfound in {time.time() - began:.1f}s "
                  f"({stats.nodes} nodes, try {step + 1})\n")
            for row in range(args.size):
                print("  " + " ".join(grid.letters[(row, col)].upper()
                                      for col in range(args.size)))
            return 0
    print(f"\nno square in {args.tries} tries and {time.time() - began:.0f}s. "
          f"raise --effort or --tries.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
