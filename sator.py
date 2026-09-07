"""SATOR squares: word squares that read the same in all four directions.

    S A T O R
    A R E P O
    T E N E T
    O P E R A
    R O T A S

Two symmetries at once. It is a symmetric word square, grid[r][c] ==
grid[c][r], so the columns are the rows; and it is unchanged by a 180-degree
turn, grid[r][c] == grid[n-1-r][n-1-c]. Together those force row n-1-r to be
the reverse of row r, which collapses the problem: the square is fixed by its
top half, every row of which must be a word whose reverse is also a word, and
for odd n the middle row must additionally be a palindrome.

That is why this is fast where a plain word square is not. An ordinary 5x5
searches for five words; this searches for two, and reads the rest off. The
binding resource is not the dictionary's size but how many *reversible* words
it holds -- 821 five-letter ones in Wiktionary against 288 in UKACD, and only
309 six-letter ones, which is what puts 6x6 out of reach in ordinary words.

Squares are reported best-first by familiarity, on the weakest word rather
than the average: a square is only as recognisable as its most obscure entry,
and averaging lets four ordinary words hide a fifth nobody has met.

    python3 sator.py 5
    python3 sator.py 6 --proper --top 20
"""

import argparse
import os
import sys

from crossword import frequency
from crossword.words import load
from squares.canonical import deduplicate
from squares.sator import solve

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("size", type=int)
    parser.add_argument("--words", default="wiktionary.txt")
    parser.add_argument("--scores", default=None,
                        help="familiarity table; defaults to the one beside "
                             "the dictionary, else UKACD's")
    parser.add_argument("--proper", action="store_true",
                        help="allow capitalised entries")
    parser.add_argument("--repeats", action="store_true",
                        help="keep squares that use a word twice")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args()

    entries = load(args.words, min_length=args.size, max_length=args.size,
                   allow_phrases=False, allow_proper=args.proper, strict=False)
    words = {entry.text for entry in entries}
    reversible = sum(1 for w in words if w[::-1] in words)
    print(f"{len(words):,} words of {args.size} letters, "
          f"{reversible:,} of them reversible", file=sys.stderr)

    scores_path = args.scores
    if scores_path is None:
        beside = os.path.splitext(args.words)[0] + "-scores.txt"
        scores_path = beside if os.path.exists(beside) else None
    scores = (frequency.load_scores(scores_path) if scores_path
              else frequency.load_scores())

    found = deduplicate(solve(words, args.size))
    if not args.repeats:
        found = [grid for grid in found if len(set(grid)) == args.size]
    print(f"{len(found):,} squares (exhaustive)", file=sys.stderr)
    if not found:
        return 1

    # Weakest word first, then the average as a tie-break.
    def rank(grid):
        values = [scores.get(word, 0.0) for word in grid]
        return (min(values), sum(values) / len(values))

    found.sort(key=rank, reverse=True)
    for grid in found[:args.top]:
        weakest, mean = rank(grid)
        print(f"\nweakest {weakest:.2f}, mean {mean:.2f}")
        for word in grid:
            print(f"   {' '.join(word.upper())}   {scores.get(word, 0.0):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
