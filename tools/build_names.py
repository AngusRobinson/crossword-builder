"""Build a list of people's and places' names, with a familiarity proxy.

A name is worth having because of what it unlocks. A word square that reads
the same after a half-turn needs every entry's reverse to be a word too, and
Wiktionary's five-letter stock offers only 922 such pairs. Sixty-six ordinary
English words -- ABOUT, ALONE, ALERT, ASSET, ATLAS, MILES -- become usable
only because their reverse happens to be a name, so the size of the name list
sets how many ordinary words are reachable at all.

Three sources, each of which already counts its entries, which is why these
and not others:

  US Census 2010 surnames   name and the number of people bearing it
  GeoNames cities1000       place name and its population
  SSA-derived given names   name and its share of births in a year

**The score is a proxy and should be read as one.** Each source is put on a
log scale shifted so that its most famous entry lands near 5.8, which is where
crossword/scores.txt tops out, so that a name and a word can be compared at
all. That is the whole of the calibration: SMITH scoring like a common word is
meant, a hamlet of a thousand people scoring 1.0 is meant, and anything
finer-grained than that is not claimed. A string that is both a surname and a
town takes the better of the two.

Names are written capitalised, which is how `crossword.words.load` recognises
a proper noun: `--proper` then admits them and the default excludes them.

    python3 tools/build_names.py --surnames Names_2010Census.csv \\
        --places cities1000.txt --given baby-names.csv
"""

import argparse
import csv
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Shifts that put each source's most famous entry near 5.8. Chosen from the
# maxima -- SMITH at 2,442,977 bearers, Tokyo at 37 million, JOHN at 8.15% of
# boys born in 1880 -- rather than fitted to anything.
SURNAME_SHIFT = 0.60
PLACE_SHIFT = 1.80
GIVEN_SCALE = 100_000


def keep(name):
    """Letters only, and long enough to be an entry."""
    text = "".join(c for c in name if c.isalpha())
    return text if 3 <= len(text) <= 21 and text.isascii() else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--surnames", help="Names_2010Census.csv")
    parser.add_argument("--places", help="GeoNames cities1000.txt")
    parser.add_argument("--given", help="baby-names.csv")
    parser.add_argument("--out", default="names.txt")
    parser.add_argument("--scores-out", default="names-scores.txt")
    parser.add_argument("--min-score", type=float, default=0.0,
                        help="drop names below this, to keep the list to ones "
                             "a solver might recognise")
    args = parser.parse_args()
    if not any((args.surnames, args.places, args.given)):
        parser.error("give at least one of --surnames, --places, --given")

    best, source = {}, {}

    def offer(name, score, where):
        text = keep(name)
        if text is None or score <= 0:
            return
        key = text.lower()
        if key not in best or score > best[key]:
            best[key] = score
            source[key] = (text.capitalize(), where)

    if args.surnames:
        with open(args.surnames, encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                try:
                    count = int(row["count"])
                except (KeyError, ValueError):
                    continue
                # The census file ends with an aggregate row standing for
                # every name too rare to list; it is not a name, and its count
                # is larger than any real one's.
                if row["name"].upper().replace(" ", "") == "ALLOTHERNAMES":
                    continue
                offer(row["name"], math.log10(count) - SURNAME_SHIFT, "surname")
        print(f"surnames: {sum(1 for v in source.values() if v[1]=='surname'):,}",
              file=sys.stderr)

    if args.places:
        with open(args.places, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split("\t")
                if len(parts) < 15:
                    continue
                try:
                    population = int(parts[14])
                except ValueError:
                    continue
                if population <= 0:
                    continue
                # field 2 is the asciiname, already transliterated
                offer(parts[2], math.log10(population) - PLACE_SHIFT, "place")
        print(f"after places: {len(best):,} names", file=sys.stderr)

    if args.given:
        share = {}
        with open(args.given, encoding="utf-8", errors="replace") as handle:
            for row in csv.DictReader(handle):
                try:
                    percent = float(row["percent"])
                except (KeyError, ValueError):
                    continue
                name = row["name"]
                # the best year a name ever had, not its average
                if percent > share.get(name, 0.0):
                    share[name] = percent
        for name, percent in share.items():
            offer(name, math.log10(percent * GIVEN_SCALE), "given")
        print(f"after given names: {len(best):,} names", file=sys.stderr)

    kept = {k: v for k, v in best.items() if v >= args.min_score}
    print(f"{len(kept):,} names kept (floor {args.min_score})", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(
            "Names of people and places, built by tools/build_names.py from\n"
            "the US Census 2010 surname file, GeoNames, and SSA-derived given\n"
            "names. Capitalised, so crossword.words.load reads them as proper\n"
            "nouns and --proper decides whether they are used.\n"
            "-" * 74 + "\n")
        for key in sorted(kept):
            handle.write(source[key][0] + "\n")

    with open(args.scores_out, "w", encoding="utf-8") as handle:
        handle.write(
            "# Familiarity proxy for names, from tools/build_names.py.\n"
            "#   surnames log10(bearers) - 0.6; places log10(population) -\n"
            "#   1.8; given names log10(peak share of births x 100,000).\n"
            "# Each shifted so its most famous entry lands near the 5.8 that\n"
            "# crossword/scores.txt tops out at. A proxy, not a measurement.\n")
        for key in sorted(kept, key=lambda k: (-kept[k], k)):
            handle.write(f"{key} {kept[key]:.3f}\n")

    print(f"wrote {args.out} and {args.scores_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
