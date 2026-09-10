"""Merge every word list into one, with the best score each word has.

Different sources reach different corners: the 7-letter reversible words that
make a 7x7 SATOR square possible are in Spread the Wordlist and not in
Wiktionary, and the names are in neither. Choosing between them loses squares
that exist.

Each file is read the way `crossword.words.load` reads it -- UTF-8 first,
latin-1 if that fails -- because UKACD is latin-1 and everything the build
scripts write is UTF-8. Reading them all one way turns 1,336 UKACD entries
into replacement characters, silently.

    python3 tools/merge_dictionaries.py --out everything.txt
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crossword import frequency

SOURCES = [("wiktionary.txt", "wiktionary-scores.txt"),
           ("crossword/UKACD.txt", "crossword/scores.txt"),
           ("american.txt", "american-scores.txt"),
           ("names.txt", "names-scores.txt")]


def lines_of(path):
    try:
        with open(path, encoding="utf-8") as handle:
            lines = [l.rstrip("\n") for l in handle]
    except UnicodeDecodeError:
        with open(path, encoding="latin-1") as handle:
            lines = [l.rstrip("\n") for l in handle]
    for i, line in enumerate(lines):
        if len(line) > 3 and set(line) == {"-"}:
            return lines[i + 1:]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="everything.txt")
    parser.add_argument("--scores-out", default="everything-scores.txt")
    args = parser.parse_args()

    seen, scores = {}, {}
    for path, table in SOURCES:
        if not os.path.exists(path):
            print(f"  skipping {path}: not here", file=sys.stderr)
            continue
        got = lines_of(path)
        for surface in got:
            key = surface.strip().lower()
            if not key:
                continue
            # a lowercase spelling beats a capitalised one, as the loader has it
            if key not in seen or (seen[key][:1].isupper()
                                   and not surface[:1].isupper()):
                seen[key] = surface.strip()
        print(f"  {path}: {len(got):,} lines, {len(seen):,} distinct so far",
              file=sys.stderr)
        if os.path.exists(table):
            for word, value in frequency.load_scores(table).items():
                scores[word] = max(scores.get(word, 0.0), value)

    with open(args.out, "w", encoding="utf-8") as out:
        out.write("Every word list this project holds, merged by\n"
                  "tools/merge_dictionaries.py. Each source keeps its own\n"
                  "licence; none of them is redistributed here.\n"
                  + "-" * 70 + "\n")
        for key in sorted(seen):
            out.write(seen[key] + "\n")
    frequency.save_scores(scores, args.scores_out)
    print(f"{len(seen):,} entries -> {args.out}", file=sys.stderr)
    print(f"{len(scores):,} scored -> {args.scores_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
