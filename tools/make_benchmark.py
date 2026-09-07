"""Build the frozen benchmark of target word lists.

    python3 make_benchmark.py [corpus_dir]

Forty synthetic lists, ten at each of four sizes, stratified by how hard they
are rather than only by how long.  Size alone is the wrong axis: measured
against the library, a 20-word list drawn arbitrarily has a mean length-profile
ceiling of 80% and is never fully fittable, while 20 words taken from a real
puzzle are fully fittable every time.  Two lists of the same length can differ
from trivial to provably impossible, so the strata carry the difficulty and
the sizes only span the range a setter would actually attempt.

  feasible   words that really did appear together in one published puzzle,
             so a grid achieving all N provably exists and is in the library.
             These are the controls.  Without them a score of 6/10 cannot
             distinguish a weak search from an impossible list.
  realistic  lengths drawn from the corpus slot-length distribution, words
             drawn from the dictionary.  Fits the shape of real grids without
             being a real answer set.
  arbitrary  uniform from the dictionary.  Deliberately awkward: this is the
             adversarial end, where the length profile fights the library.

Written once and committed.  Reuse the same lists across every variant of the
search -- list composition dominates the variance, so a paired comparison on
fixed lists detects an improvement that fresh draws would bury in noise.
"""

import collections
import glob
import json
import os
import random
import sys
import warnings

warnings.filterwarnings("ignore")

# Run as `python3 tools/make_benchmark.py` from the repository root: Python puts this
# directory on sys.path, not its parent, so the root goes on explicitly.
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


from crossword import library
from crossword.words import _fold, load

SIZES = (6, 10, 14, 18)
PER_SIZE = 10
MIX = {"feasible": 4, "realistic": 4, "arbitrary": 2}
OUT = os.path.join("benchmark", "lists.json")

# Real themes, for face validity.  Synthetic lists cannot reproduce the way a
# genuine theme clusters -- all one part of speech, often proper nouns the
# fill dictionary excludes, lengths dictated by the subject rather than
# chosen.  A benchmark with no recognisable cases in it is hard to trust.
THEMES = {
    "birds": ["kestrel", "chaffinch", "nightjar", "wheatear", "redwing",
              "goldcrest", "bittern", "avocet", "curlew", "fieldfare"],
    "shakespeare": ["hamlet", "othello", "macbeth", "tempest", "cymbeline",
                    "coriolanus", "pericles", "twelfthnight"],
    "chemistry": ["titration", "isotope", "catalyst", "valency", "alkane",
                  "enthalpy", "covalent", "reagent", "molarity", "sublimate"],
    "weather": ["cumulus", "isobar", "monsoon", "drizzle", "hailstone",
                "anticyclone", "squall", "overcast"],
}


def solutions(path):
    """The answers of one published puzzle, folded to fill strings."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data["dimensions"]["cols"] != 15 or data["dimensions"]["rows"] != 15:
        return None, None
    words = []
    for entry in data["entries"]:
        text = _fold(entry.get("solution") or "")
        if 3 <= len(text) <= 15 and len(text) == entry["length"]:
            words.append(text)
    return os.path.basename(path).split(".")[0], words


def main(corpus="guardian-cc-master/crosswords"):
    rng = random.Random(20260903)
    patterns = library.load()
    in_library = {p.source for p in patterns}

    entries = load("crossword/UKACD.txt", strict=False)
    pool = [e.text for e in entries if 3 <= len(e.text) <= 15]
    by_length = collections.defaultdict(list)
    for word in pool:
        by_length[len(word)].append(word)

    # The length distribution real grids offer, to draw "realistic" lists from.
    slot_lengths = []
    for pattern in patterns:
        for length, count in pattern.profile().items():
            slot_lengths.extend([length] * count * max(1, pattern.uses // 50))

    # Puzzles whose grid is in the library, so a feasible list is feasible in
    # a pattern we actually hold.
    usable = []
    for path in sorted(glob.glob(os.path.join(corpus, "**", "*.JSON"), recursive=True)):
        try:
            source, words = solutions(path)
        except (KeyError, ValueError, json.JSONDecodeError, OSError):
            continue
        if source and words and len(words) >= max(SIZES) and source in in_library:
            usable.append((source, words))
    rng.shuffle(usable)
    print(f"{len(usable)} published puzzles usable as feasible controls")

    lists = []
    cursor = 0
    for size in SIZES:
        for stratum, count in MIX.items():
            for _ in range(count):
                if stratum == "feasible":
                    source, words = usable[cursor % len(usable)]
                    cursor += 1
                    target = rng.sample(words, size)
                    note = f"answers of Guardian {source}"
                    optimum = size
                elif stratum == "realistic":
                    lengths = [rng.choice(slot_lengths) for _ in range(size)]
                    target = [rng.choice(by_length[n]) for n in lengths]
                    note = "lengths sampled from corpus slot distribution"
                    optimum = None
                else:
                    target = rng.sample(pool, size)
                    note = "uniform draw from the dictionary"
                    optimum = None
                lists.append({
                    "id": f"{stratum[:4]}-{size:02d}-{len(lists):02d}",
                    "size": size,
                    "stratum": stratum,
                    "note": note,
                    "known_optimum": optimum,
                    "words": sorted(target),
                })

    for name, words in THEMES.items():
        lists.append({
            "id": f"theme-{name}",
            "size": len(words),
            "stratum": "theme",
            "note": "hand-written real theme",
            "known_optimum": None,
            "words": sorted(_fold(w) for w in words),
        })

    os.makedirs("benchmark", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({
            "generated_by": "make_benchmark.py",
            "seed": 20260903,
            "note": "Frozen benchmark. Do not regenerate to chase a result; "
                    "paired comparison on fixed lists is the point.",
            "lists": lists,
        }, handle, indent=1)

    counts = collections.Counter(item["stratum"] for item in lists)
    print(f"wrote {len(lists)} lists to {OUT}: {dict(counts)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
