"""Build an American fill dictionary from Spread the Wordlist.

The parameter study found the US style stuck at about a third of grids filling,
and stuck there whatever the search was told to do: `aim`, `attempts`,
`branch_cap`, `budget`, `commonness`, `fill_restarts` and `node_scale` all left
it between 0.29 and 0.33, and eight times the time budget moved it from 0.308
to 0.319. A completion rate that ignores every search parameter and the clock
is not a search that needs tuning. It is a vocabulary that does not contain the
fills.

UKACD is a British list, and an American grid asks a different question of it.
Every cell is checked, so the short entries carry the whole grid, and that is
exactly where UKACD is thin:

    length   UKACD    Spread the Wordlist
         3   1,245    4,308
         4   5,181   11,527
        15   5,054   29,435

Three letters is where a 15x15 is most constrained and where the American list
is three and a half times larger. The reason is not spelling -- COLOR against
COLOUR is a rounding error -- but convention: an American entry is often a
phrase, an abbreviation or a name, and a British word list holds none of them.
AAABATTERY and INAROW are entries in one tradition and not words in the other.

**Input.** Spread the Wordlist, from spreadthewordlist.com: one `word;score`
per line, the score an editorial judgement in six steps from 0 to 50, where 50
is clean fill a solver will not resent. Take the lowercase build in either
format; this reads both.

**Output.** Two files. `american.txt` has the shape UKACD has -- a header, a
rule of hyphens, then one surface form per line -- so `crossword.words.load`
reads it unchanged. `american-scores.txt` has the shape `crossword/scores.txt`
has, so `frequency.load_scores(path)` reads it unchanged.

The score conversion divides by ten, which lands the six steps on 0.0 to 5.0
against the 0.69 to 5.80 our own table spans, so `--min-score` keeps meaning
what it meant. Within a step the ties are broken by our existing familiarity
table where it has an opinion, so the most ordinary members of a step sort
above the rest rather than in file order.

**Two flags stop working, and it is the source that stops them.**
`--proper` filters on a leading capital, and Spread the Wordlist is entirely
lowercase, so it cannot tell OMAHA from OMAHA the common noun; every entry
reads as ordinary. `--allow-phrases` filters on punctuation surviving
normalisation, and the phrases here arrive already collapsed, so they read as
ordinary too. Both are correct for the tradition -- American grids want names
and phrases -- but neither switch will do anything, and that is a property of
the list rather than a bug in the loader.

**Licence.** CC BY-NC-SA 4.0. That is why this builds a list rather than
shipping one, as with UKACD and Wiktionary. Selling puzzles made with it is
explicitly allowed by its authors; redistributing the list is what carries the
condition, and the header this writes carries the attribution.

    python3 build_american.py spreadthewordlist.txt
"""

import argparse
import os
import sys

HEADER = """\
American fill dictionary, built by build_american.py from Spread the Wordlist
(spreadthewordlist.com), by Brooke Husic and Erik Agard.

Spread the Wordlist is licensed CC BY-NC-SA 4.0.
https://creativecommons.org/licenses/by-nc-sa/4.0/

Entries are lowercase in the source, so the proper-noun flag cannot be set and
--proper will not filter. Phrases arrive collapsed, so --allow-phrases will not
filter either. Both are the source's doing, not the loader's.
------------------------------------------------------------------------------
"""


def read(path):
    """word -> editorial score, keeping the best score for a repeated word."""
    best = {}
    dropped = 0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or ";" not in line:
                dropped += 1
                continue
            word, _, number = line.rpartition(";")
            word = word.strip().lower()
            if not word.isalpha():
                dropped += 1
                continue
            try:
                score = int(number)
            except ValueError:
                dropped += 1
                continue
            if word not in best or score > best[word]:
                best[word] = score
    return best, dropped


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="the Spread the Wordlist download")
    parser.add_argument("--out", default="american.txt")
    parser.add_argument("--scores-out", default="american-scores.txt")
    parser.add_argument("--min-score", type=int, default=20,
                        help="drop entries scoring below this (default 20). "
                             "The bottom two steps are mostly junk: strings of "
                             "one repeated letter, and fragments no editor "
                             "would set")
    parser.add_argument("--min-length", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=23,
                        help="a 23x23 jumbo has twenty-one-letter entries")
    args = parser.parse_args()

    scored, dropped = read(args.source)
    print(f"{len(scored):,} entries read, {dropped:,} lines skipped",
          file=sys.stderr)

    # Break ties within an editorial step by general familiarity, where we
    # have it. Without this the whole top step sorts in alphabetical order and
    # `aim` has nothing to prefer within it.
    tiebreak = {}
    here = os.path.dirname(os.path.abspath(__file__))
    existing = os.path.join(here, "crossword", "scores.txt")
    if os.path.exists(existing):
        sys.path.insert(0, here)
        from crossword import frequency
        tiebreak = frequency.load_scores(existing)
        print(f"tie-breaking with {len(tiebreak):,} familiarity scores",
              file=sys.stderr)

    kept = {
        word: score for word, score in scored.items()
        if score >= args.min_score
        and args.min_length <= len(word) <= args.max_length
    }
    print(f"{len(kept):,} entries kept "
          f"(score >= {args.min_score}, "
          f"{args.min_length}-{args.max_length} letters)", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
        for word in sorted(kept):
            handle.write(word + "\n")

    # The editorial step dominates; familiarity only orders within it. Scaling
    # the tiebreak to under a tenth of a step keeps it from crossing one.
    with open(args.scores_out, "w", encoding="utf-8") as handle:
        handle.write(
            "# Familiarity per word, for the American dictionary.\n"
            "#   Spread the Wordlist's editorial score / 10, which puts its\n"
            "#   six steps on 0.0 to 5.0, against the 0.69 to 5.80 that\n"
            "#   crossword/scores.txt spans.\n"
            "#   Ties within a step are broken by that table, scaled small\n"
            "#   enough that it cannot lift a word out of its step.\n"
            "# Generated by build_american.py.\n")
        for word in sorted(kept, key=lambda w: (-kept[w], w)):
            value = kept[word] / 10.0 + min(tiebreak.get(word, 0.0), 6.0) / 100.0
            handle.write(f"{word} {value:.3f}\n")

    print(f"wrote {args.out} and {args.scores_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
