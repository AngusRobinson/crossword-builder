"""Crosswords that read the same upside down.

Not the pattern -- that is already symmetric by convention -- but the letters:
grid[r][c] == grid[n-1-r][n-1-c], so turning the diagram through half a turn
gives the diagram back.

    python3 palindrome.py
    python3 palindrome.py --style british --proper
    python3 palindrome.py --tries 8 --effort 400000

Entries pair off under the turn and each pair holds a word and its reverse, so
every free entry needs its reverse to be a word too, and that is what decides
everything. Wiktionary holds 1.1 million entries and 3,469 reversible ones,
and they run out with length: 395 usable pairs at three letters, 172 at six,
36 at seven, 7 at eight, 1 at nine, and none at all at ten.

Which is why the grid matters more than the effort, and why this tries them in
order of how much slack each leaves at its scarcest length. 396 of the 2,500
American grids clear their own vocabulary requirement before the search
begins, and 13 of the 120 British ones do -- fewer, because British entries
run longer, but not none. A long entry does not need a reversible partner when
it is its own reverse, which is how a grid carrying a nine-letter entry fills
from a stock with no reversible nine-letter words in it: DELEVELED.

Distinctness is the other lever, and a sharp one. A palindrome placed in a
paired entry writes itself into both halves, so the same answer appears twice;
forbidding that is right for a puzzle and expensive for the search. Over all
396 grids and four seeds it found nothing, and most grids were *proved*
unfillable in a hundred nodes rather than running out of budget. Allow the
repeat, or allow proper nouns, and it comes out in seconds.
"""

import argparse
import collections
import sys
import time

from crossword import frequency, library
from crossword.index import Index
from crossword.words import load
from squares.rotational import pair_slots, reversible, solve, is_rotational


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--style", choices=("us", "british", "barred"),
                        default="us",
                        help="us by default, having far more grids that "
                             "clear the vocabulary; british works too")
    parser.add_argument("--dictionary", default="wiktionary.txt")
    parser.add_argument("--scores", default=None)
    parser.add_argument("--proper", action="store_true",
                        help="allow capitalised entries, which roughly doubles "
                             "the reversible stock")
    parser.add_argument("--repeats", action="store_true",
                        help="go straight to allowing a palindrome to fill "
                             "both halves of a pair, so one answer appears "
                             "twice. Without it that is tried only as a "
                             "fallback, and the result says which it used")
    parser.add_argument("--distinct", action="store_true",
                        help="refuse the fallback: no repeated answer, or "
                             "nothing")
    parser.add_argument("--size", type=int, default=12,
                        help="barred only; the blocked libraries are 15x15")
    parser.add_argument("--grids", type=int, default=400,
                        help="how many candidate grids to try")
    parser.add_argument("--tries", type=int, default=4, help="seeds per grid")
    parser.add_argument("--effort", type=int, default=60_000,
                        help="node budget per attempt")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    def say(*text):
        if not args.quiet:
            print(*text, file=sys.stderr, flush=True)

    entries = load(args.dictionary, strict=False, max_length=23,
                   allow_proper=args.proper)
    usable = reversible(entries)
    if not usable:
        parser.error("no reversible words in that dictionary")
    import os
    scores_path = args.scores
    if scores_path is None:
        beside = os.path.splitext(args.dictionary)[0] + "-scores.txt"
        scores_path = beside if os.path.exists(beside) else None
    scores = (frequency.load_scores(scores_path) if scores_path
              else frequency.load_scores())
    index = Index(usable, scores)
    stock = collections.Counter(len(entry.text) for entry in usable)
    say(f"{len(entries):,} entries, {len(usable):,} of them reversible")

    # A grid whose scarcest length has no stock cannot be filled, and saying so
    # here costs nothing where finding it out by search costs a budget.
    min_length = 4 if args.style == "barred" else 3
    if args.style == "barred":
        # Barred grids are not a library but a generator, and they are much
        # the easiest of the three here: bars can fall anywhere, so a pattern
        # can be shaped to the vocabulary instead of the other way about.
        import random
        from crossword import barred
        rng = random.Random(0)
        candidates = []
        while len(candidates) < args.grids * 4:
            drawn = barred.pattern(args.size, min_entry=min_length, rng=rng)
            if drawn is not None:
                candidates.append(drawn)
    else:
        candidates = [pattern.grid()
                      for pattern in library.load(None, style=args.style)]

    ranked = []
    for grid in candidates:
        pairs, singles, orphans = pair_slots(grid, min_length)
        if orphans:
            continue
        need = collections.Counter(a.length for a, _ in pairs)
        need += collections.Counter(s.length for s in singles)
        if any(need[L] * 2 > stock.get(L, 0) for L in need):
            continue
        ranked.append((min(stock.get(L, 0) / (2 * need[L]) for L in need),
                       grid))
    ranked.sort(key=lambda row: -row[0])
    say(f"{len(ranked):,} grids clear their own vocabulary requirement")
    if not ranked:
        print(f"No {args.style} grid can be filled from this dictionary: "
              f"every one wants a length the reversible stock does not reach.",
              file=sys.stderr)
        return 1

    # A repeated answer is a flaw, so it is not the first thing tried; but a
    # grid with one beats no grid, so it is tried second unless forbidden.
    passes = [False] if args.distinct else ([True] if args.repeats
                                            else [False, True])
    began = time.time()
    attempts = 0
    for allow_repeats in passes:
        if allow_repeats and len(passes) > 1:
            say(f"no grid with every answer distinct in {attempts} attempts; "
                f"allowing one repeated answer")
        for seed in range(args.tries):
            for slack, blank in ranked[:args.grids]:
                grid = blank.copy()
                grid.letters.clear()
                attempts += 1
                placed, nodes = solve(grid, index, seed=seed,
                                      node_budget=args.effort,
                                      min_length=min_length,
                                      distinct=not allow_repeats)
                if placed:
                    assert is_rotational(grid), "not symmetric under a half-turn"
                    entries = [grid.pattern(slot)
                               for slot in grid.slots(min_length)]
                    say(f"found on attempt {attempts} in "
                        f"{time.time()-began:.0f}s ({nodes:,} nodes, "
                        f"slack x{slack:.1f}); {len(set(entries))} of "
                        f"{len(entries)} answers distinct")
                    print(grid.pretty(gap="", upper=True)
                          if args.style == "barred" else grid.render())
                    return 0
    print(f"nothing in {attempts} attempts and {time.time()-began:.0f}s. "
          f"Try --proper, a smaller --size, or a larger --effort.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
