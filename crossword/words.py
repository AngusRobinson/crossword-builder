"""Loading and normalisation of word lists."""

from __future__ import annotations

import re
import unicodedata
import warnings
from dataclasses import dataclass

_ALPHA_ONLY = re.compile(r"[^a-z]")

REPLACEMENT = "\ufffd"

# NFKD decomposes accents (é -> e + combining acute) but leaves these alone,
# so without an explicit table they are stripped to nothing: "encyclopædia"
# would fold to "encyclopdia" and "straße" to "strae".  Ligatures expand to
# two letters, which changes the entry's length — this is why the length
# distribution is sensitive to getting it right.
TRANSLITERATE = {
    "æ": "ae", "œ": "oe", "ß": "ss", "ø": "o", "đ": "d", "ð": "d",
    "þ": "th", "ł": "l", "ħ": "h", "ı": "i", "ŋ": "ng", "ſ": "s",
}
_TRANSLITERATE_TABLE = str.maketrans(
    {
        **TRANSLITERATE,
        # "ß".upper() is "SS" — two characters, which maketrans rejects as a
        # key. Only single-character uppercase forms can be added.
        **{
            k.upper(): v.upper()
            for k, v in TRANSLITERATE.items()
            if len(k.upper()) == 1
        },
    }
)


@dataclass(frozen=True)
class Entry:
    """A dictionary entry after normalisation.

    `text` is the fill string: lowercase a-z only, punctuation and spaces
    stripped.  `surface` keeps one original form for display and for clue
    writing later.  `proper` and `phrase` are the filter flags.
    """

    text: str
    surface: str
    proper: bool
    phrase: bool

    def __len__(self) -> int:
        return len(self.text)


def _fold(raw: str) -> str:
    """Strip accents, casefold, then remove everything outside a-z."""
    expanded = raw.translate(_TRANSLITERATE_TABLE)
    decomposed = unicodedata.normalize("NFKD", expanded)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _ALPHA_ONLY.sub("", stripped.lower())


def load(
    path: str,
    *,
    min_length: int = 3,
    max_length: int = 15,
    allow_proper: bool = False,
    allow_phrases: bool = True,
    encoding: str = "latin-1",
    strict: bool = True,
) -> list[Entry]:
    """Read a word list and return normalised entries, sorted by text.

    Sorting is deliberate: word ids are assigned by position in this list, so
    a stable order makes bitsets — and therefore test failures — reproducible
    across runs.

    Duplicates are merged after folding, since stripping punctuation creates
    collisions ("re-form" and "reform").  A merged entry is proper only if
    *every* surface form was capitalised; one lowercase citation is enough to
    make the word available as ordinary fill.
    """
    merged: dict[str, Entry] = {}
    damaged: list[str] = []

    with open(path, encoding=encoding) as handle:
        lines = [line.strip() for line in handle]

    # UKACD prefixes a BSD licence, terminated by a rule of hyphens.  This
    # cannot be left to the alphabetic filter: folding strips punctuation and
    # spaces, so "are met:" survives as the six-letter string "aremet".
    for position, line in enumerate(lines):
        if len(line) > 3 and set(line) == {"-"}:
            lines = lines[position + 1 :]
            break

    for surface in lines:
        if not surface:
            continue
        if REPLACEMENT in surface or "\u00ef\u00bf\u00bd" in surface:
            damaged.append(surface)
            continue
        text = _fold(surface)
        if not text:
            continue

        proper = surface[:1].isupper()
        phrase = text != surface.lower()

        previous = merged.get(text)
        if previous is None:
            merged[text] = Entry(text, surface, proper, phrase)
        elif previous.proper and not proper:
            # A lowercase citation outranks the capitalised one.
            merged[text] = Entry(text, surface, False, previous.phrase and phrase)
        elif previous.phrase and not phrase:
            merged[text] = Entry(text, previous.surface, previous.proper, False)

    entries = [
        entry
        for entry in merged.values()
        if min_length <= len(entry.text) <= max_length
        and (allow_proper or not entry.proper)
        and (allow_phrases or not entry.phrase)
    ]
    entries.sort(key=lambda entry: entry.text)

    if damaged:
        message = (
            f"{len(damaged)} lines contain U+FFFD replacement characters, "
            f"e.g. {damaged[0]!r}. The file has been through a lossy decode "
            f"and its accented entries are unrecoverable; obtain a clean copy."
        )
        if strict:
            raise ValueError(message)
        warnings.warn(message, stacklevel=2)

    return entries


def by_length(entries: list[Entry]) -> dict[int, list[Entry]]:
    """Partition entries by length, preserving sorted order within each bucket."""
    buckets: dict[int, list[Entry]] = {}
    for entry in entries:
        buckets.setdefault(len(entry.text), []).append(entry)
    return buckets
