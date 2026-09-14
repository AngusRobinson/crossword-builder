"""The shortest entries that contain a given set of letters.

    python3 shortest.py aeiou                  # SEQUOIA
    python3 shortest.py aeiou --in-order       # the vowels in alphabetical order
    python3 shortest.py jqxz --words everything.txt
    python3 shortest.py abcdefgh --without s

Letters are a multiset: `ss` asks for two S's, not one. `--in-order` asks for
them as a subsequence -- in that order, not necessarily adjacent. Among entries
of the same length the more familiar come first.
"""

import argparse
import collections
import os
import sys

from crossword import frequency
from crossword.words import load

WORDLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "crossword", "UKACD.txt")


def contains(text, wanted, in_order):
    if in_order:
        rest = iter(text)
        return all(letter in rest for letter in wanted)
    have = collections.Counter(text)
    return all(have[letter] >= n for letter, n in wanted.items())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("letters")
    parser.add_argument("--in-order", action="store_true",
                        help="the letters must appear in the order given")
    parser.add_argument("--without", default="", metavar="LETTERS",
                        help="letters the entry must not contain at all")
    parser.add_argument("--words", default=WORDLIST)
    parser.add_argument("--scores", default=None,
                        help="familiarity table; defaults to the one beside "
                             "the dictionary, else UKACD's")
    parser.add_argument("--min-score", type=float, default=0.0, metavar="S")
    parser.add_argument("--proper", action="store_true",
                        help="allow capitalised entries")
    parser.add_argument("--phrases", action="store_true",
                        help="allow multi-word entries")
    parser.add_argument("--top", type=int, default=10,
                        help="how many to show (default 10)")
    parser.add_argument("--lengths", type=int, default=1, metavar="N",
                        help="show the shortest N lengths, not just the "
                             "shortest one (default 1)")
    args = parser.parse_args()

    letters = "".join(c for c in args.letters.lower() if c.isalpha())
    banned = set(args.without.lower())
    if not letters:
        parser.error("no letters given")
    if banned & set(letters):
        parser.error("a letter cannot be both wanted and excluded")
    wanted = letters if args.in_order else collections.Counter(letters)

    entries = load(args.words, min_length=len(letters), max_length=100,
                   allow_proper=args.proper, allow_phrases=args.phrases,
                   strict=False)

    scores_path = args.scores
    if scores_path is None:
        beside = os.path.splitext(args.words)[0] + "-scores.txt"
        if os.path.exists(beside):
            scores_path = beside
        elif os.path.abspath(args.words) == os.path.abspath(WORDLIST):
            scores_path = frequency.SCORES_PATH
    scores = frequency.load_scores(scores_path) if scores_path else {}

    found = [e for e in entries
             if scores.get(e.text, 0.0) >= args.min_score
             and not banned & set(e.text)
             and contains(e.text, wanted, args.in_order)]
    if not found:
        print(f"no entry in {os.path.basename(args.words)} contains "
              f"{letters.upper()}", file=sys.stderr)
        return 1

    lengths = sorted({len(e.text) for e in found})[:args.lengths]
    found = [e for e in found if len(e.text) in lengths]
    found.sort(key=lambda e: (len(e.text), -scores.get(e.text, 0.0), e.text))

    print(f"{len(found):,} entries of {', '.join(map(str, lengths))} letters "
          f"contain {letters.upper()}"
          f"{' in that order' if args.in_order else ''}", file=sys.stderr)
    for e in found[:args.top]:
        print(f"{len(e.text):>3}  {scores.get(e.text, 0.0):5.2f}  {e.surface}")
    if len(found) > args.top:
        print(f"  ... and {len(found) - args.top:,} more (--top)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
