"""Build a word list from a Wiktionary extract, for use as a fill dictionary.

UKACD is 221,835 entries and the parameter study found that is not enough: at
a fixed budget, filling with only the most familiar 80% of it does measurably
worse than with all of it, and the curve has not flattened. So more vocabulary
is worth having, particularly for the American style where every letter is
checked.

**Input.** Not Wiktionary itself -- scraping page by page would be slow and
rude, and the wikitext needs a parser. Use `wiktextract` output instead, which
is Wiktionary already parsed into JSON, one entry per line. kaikki.org
publishes it, including English-only extracts. This reads that format,
streaming, because the file runs to several gigabytes.

The exact download URL is not written here because it could not be checked from
where this was built; take it from kaikki.org's English dictionary page.

**Output.** The same shape as UKACD: a header, a rule of hyphens, then one
surface form per line. `crossword.words.load` reads it unchanged.

**Licence.** Wiktionary is CC BY-SA. That is why this script exists rather than
a word list in the repository: the list you build is yours to keep locally, and
the attribution travels in the header it writes.

    python3 build_wiktionary.py kaikki-english.jsonl --out wiktionary.txt
"""

import argparse
import json
import re
import sys
from collections import Counter

# Which parts of speech to take. Wiktextract marks a good deal that is not
# usable as an answer: prefixes and suffixes, single characters, punctuation.
DEFAULT_POS = ("noun", "verb", "adj", "adv", "name", "num", "intj", "conj",
               "prep", "pron", "det", "phrase")

# Senses carrying these are not what a solver should meet in a grid.
SKIP_TAGS = frozenset({
    "misspelling", "obsolete", "archaic-spelling", "alt-of", "abbreviation",
    "initialism", "acronym", "romanization", "misconstruction",
})

FOLD = re.compile(r"[^a-z]")


def usable(surface, min_length, max_length):
    """The fill string, or None if this cannot be an answer."""
    text = FOLD.sub("", surface.lower())
    if not text or not (min_length <= len(text) <= max_length):
        return None
    # A surface that is mostly punctuation folds to something unrelated to what
    # it says, and a solver would not recognise the result as the word.
    if len(text) < len(FOLD.sub("", surface.lower().replace(" ", "").replace("-", ""))):
        return None
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="wiktextract JSONL, as from kaikki.org")
    parser.add_argument("--out", default="wiktionary.txt")
    parser.add_argument("--min-length", type=int, default=3)
    parser.add_argument("--max-length", type=int, default=21)
    parser.add_argument("--lang", default="en", help="language code to keep")
    parser.add_argument("--pos", nargs="+", default=list(DEFAULT_POS))
    parser.add_argument("--no-forms", action="store_true",
                        help="headwords only, without inflections. The "
                             "inflections are most of the value: they are what "
                             "makes a plural or a past tense available to fill "
                             "a slot the headword does not fit")
    parser.add_argument("--keep-proper", action="store_true",
                        help="keep capitalised entries, which are otherwise "
                             "dropped as UKACD drops them")
    args = parser.parse_args()

    wanted = set(args.pos)
    seen, tally = {}, Counter()
    lines = 0

    with open(args.source, encoding="utf-8") as handle:
        for line in handle:
            lines += 1
            if not lines % 200000:
                print(f"  {lines:,} lines, {len(seen):,} words",
                      file=sys.stderr, flush=True)
            line = line.strip()
            if not line or line[0] != "{":
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                tally["unparsed"] += 1
                continue
            if entry.get("lang_code") != args.lang:
                continue
            if entry.get("pos") not in wanted:
                tally["pos"] += 1
                continue

            # Skip an entry whose every sense is one a solver should not meet.
            senses = entry.get("senses") or []
            if senses and all(SKIP_TAGS & set(sense.get("tags") or ())
                              for sense in senses):
                tally["skipped sense"] += 1
                continue

            surfaces = [entry.get("word") or ""]
            if not args.no_forms:
                for form in entry.get("forms") or []:
                    text = form.get("form")
                    # Wiktextract uses the forms list for tables and notes as
                    # well as inflections; the notes are marked.
                    if text and "table-tags" not in (form.get("tags") or ()):
                        surfaces.append(text)

            for surface in surfaces:
                if not surface:
                    continue
                if not args.keep_proper and surface[:1].isupper():
                    tally["proper"] += 1
                    continue
                text = usable(surface, args.min_length, args.max_length)
                if text is None:
                    tally["unusable"] += 1
                    continue
                # Keep the first spelling seen, so the enumeration a setter
                # gets is a real one rather than a fold of several.
                seen.setdefault(text, surface)

    ordered = sorted(seen.values(), key=lambda w: (FOLD.sub("", w.lower()), w))
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(
            "Built from Wiktionary via wiktextract (kaikki.org).\n"
            "Wiktionary content is available under CC BY-SA; see\n"
            "https://en.wiktionary.org/wiki/Wiktionary:Copyrights\n"
            "This list is a derived work and carries the same licence.\n"
            f"Built by build_wiktionary.py from {args.source}.\n"
            "--------------------------------------------------------------------\n"
        )
        handle.write("\n".join(ordered) + "\n")

    lengths = Counter(len(FOLD.sub("", w.lower())) for w in ordered)
    print(f"\n{len(ordered):,} words from {lines:,} lines -> {args.out}",
          file=sys.stderr)
    print("dropped: " + ", ".join(f"{k} {v:,}" for k, v in tally.most_common()),
          file=sys.stderr)
    print("by length: " + ", ".join(f"{n}:{lengths[n]:,}"
                                    for n in sorted(lengths)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
