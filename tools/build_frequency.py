"""Build a familiarity table: how ordinary each word in a dictionary is.

    python3 tools/build_frequency.py
    python3 tools/build_frequency.py --dictionary wiktionary.txt

With no arguments this rebuilds the two committed files for UKACD:
crossword/frequency.txt, the Guardian answer counts, and crossword/scores.txt,
the familiarity scores that `--aim` is calibrated against.

With `--dictionary` it writes a table beside that dictionary instead --
wiktionary.txt gets wiktionary-scores.txt -- and leaves the committed files
alone. `make_grid.py` and `sator.py` pick a table up from that name without
being told, and they have to: a floor like `--min-score 1.0` is an absolute
cut, so reading UKACD's numbers against another list's words silently drops
every word the table has never met.

That is not a hypothetical. crossword/scores.txt covers 105,373 words, which
is 35% of Wiktionary's five-letter entries and 27% of its six-letter ones, so
ranking Wiktionary results by it mostly measures whether a word is in UKACD.

The score is max(log1p(Guardian answer uses), 0.75 * wordfreq Zipf): a word is
rescued by either source, because the corpus knows crosswordese that general
English does not, and general English knows ordinary words that no setter has
happened to use. Counts are re-extracted rather than read from the committed
frequency.txt, which was filtered to UKACD -- 5,779 real Guardian answers are
in Wiktionary but not UKACD, and reading the committed file would score them
from general frequency alone.

`wordfreq` is needed here and nowhere else; the runtime only reads the result.
"""

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crossword import frequency
from crossword.words import load


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default="guardian-cc-master/crosswords")
    parser.add_argument("--dictionary", default=None,
                        help="build a table for this word list instead of "
                             "rebuilding the committed UKACD ones")
    parser.add_argument("--scores-out", default=None,
                        help="where to write it (default: beside the "
                             "dictionary, as <name>-scores.txt)")
    args = parser.parse_args()

    committed = args.dictionary is None
    path = args.dictionary or "crossword/UKACD.txt"
    entries = load(path, strict=False)
    vocabulary = {entry.text for entry in entries}
    print(f"{len(vocabulary):,} entries in {path}", file=sys.stderr)

    counts = frequency.extract(args.corpus, vocabulary)
    print(f"{len(counts):,} of them have been a Guardian answer "
          f"({sum(counts.values()):,} instances)", file=sys.stderr)

    if committed:
        frequency.save(counts, frequency.DEFAULT_PATH)
        print(f"wrote {frequency.DEFAULT_PATH}", file=sys.stderr)

    scores = frequency.build_scores(vocabulary, counts)
    destination = args.scores_out or (
        frequency.SCORES_PATH if committed
        else os.path.splitext(path)[0] + "-scores.txt")
    frequency.save_scores(scores, destination)

    phrases = {e.text for e in entries if e.phrase}
    print(f"\n{len(scores):,} of {len(vocabulary):,} entries scored "
          f"({100 * len(scores) / max(1, len(vocabulary)):.0f}%)",
          file=sys.stderr)
    print(f"  {sum(1 for w in scores if w in phrases):,} of {len(phrases):,} "
          f"phrases", file=sys.stderr)
    print(f"  {sum(1 for w in scores if w not in phrases):,} of "
          f"{len(vocabulary) - len(phrases):,} single words", file=sys.stderr)
    print(f"wrote {destination}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
