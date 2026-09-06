"""Bitset index for pattern matching.

One universe per word length.  Bit i of a mask is set iff word i of that
length satisfies the constraint the mask represents.  A pattern query is an
AND chain over the known positions; the count of survivors is one call to
int.bit_count().

Python's arbitrary-precision ints are the right container here.  The AND runs
in C over the whole universe at once, and cheap counts are what the search
ordering heuristics consume — a trie would give membership but not counts.
"""

from __future__ import annotations

import string

from .words import Entry

ALPHABET = string.ascii_lowercase
WILDCARD = "."

if hasattr(int, "bit_count"):  # Python 3.10+
    def popcount(value: int) -> int:
        return value.bit_count()
else:  # pragma: no cover - fallback for older interpreters
    def popcount(value: int) -> int:
        return bin(value).count("1")


def _letter_mask(word: str) -> int:
    mask = 0
    for char in word:
        mask |= 1 << (ord(char) - 97)
    return mask


ALL_LETTERS = (1 << 26) - 1


class LengthIndex:
    """Index over all words of a single length."""

    def __init__(self, entries: list[Entry], length: int, scores: dict = None):
        self.length = length
        self.entries = entries
        self.words = [entry.text for entry in entries]
        self.all = (1 << len(entries)) - 1

        # How ordinary each word is, parallel to `words`, in the log units
        # crossword.frequency produces.  None when no table was supplied,
        # which the filler reads as "no preference" rather than "everything is
        # equally obscure".
        self.score = (
            [scores.get(word, 0.0) for word in self.words]
            if scores is not None
            else None
        )
        self._mean = None

        # Which letters each word contains, as a 26-bit mask.  The pangram
        # search asks "does this word supply a letter the grid still lacks"
        # at every node, and an integer AND answers it in one operation where
        # a set intersection would allocate.
        self.letters = [
            _letter_mask(word) for word in self.words
        ]

        # Each word's familiarity as a rank within its own length, in [0, 1].
        # Raw familiarity cannot be compared across lengths -- long words are
        # rarer by nature -- but a rank can, and real answers turn out to sit
        # at a remarkably steady quantile whatever their length: 0.77 at four
        # letters, 0.86 overall, 0.93 at fifteen.  That is what makes a single
        # target work for the whole grid.
        if self.score is None:
            self.quantile = None
        else:
            order = sorted(range(len(self.score)), key=lambda i: self.score[i])
            self.quantile = [0.0] * len(order)
            n = max(1, len(order) - 1)
            for rank, word_id in enumerate(order):
                self.quantile[word_id] = rank / n

        # Word -> id, so a caller holding a word (a themed entry the setter
        # chose, say) can ask whether it is in the dictionary without a linear
        # scan and without catching ValueError from list.index.
        self.by_word = {word: i for i, word in enumerate(self.words)}

        self.masks: list[dict[str, int]] = [
            {char: 0 for char in ALPHABET} for _ in range(length)
        ]
        for word_id, word in enumerate(self.words):
            bit = 1 << word_id
            for position, char in enumerate(word):
                self.masks[position][char] |= bit

    @property
    def mean_score(self) -> float:
        """Average familiarity of the words at this length.

        Familiarity falls steeply with length -- 2.60 at three letters, 0.40
        at fifteen -- because long words are rarer in every corpus.  Anything
        comparing words *across* lengths has to divide that out, or it is
        really just measuring how short they are.
        """
        if self.score is None:
            return 0.0
        if self._mean is None:
            self._mean = sum(self.score) / len(self.score) if self.score else 0.0
        return self._mean

    def match(self, pattern: str, exclude: int = 0) -> int:
        """The mask of words fitting a pattern, minus any excluded ids."""
        mask = self.all & ~exclude
        for position, char in enumerate(pattern):
            if char == WILDCARD:
                continue
            try:
                mask &= self.masks[position][char]
            except KeyError:
                # A caller has passed a pattern that was never folded -- a
                # hyphen or an apostrophe from a surface form, most likely.
                # Say so here rather than surfacing a KeyError from a dict of
                # single letters several frames down.
                raise ValueError(
                    f"pattern {pattern!r} contains {char!r}; patterns hold "
                    f"a-z and '.' only, so fold the word first"
                ) from None
            if not mask:
                return 0
        return mask

    def count(self, pattern: str, exclude: int = 0) -> int:
        return popcount(self.match(pattern, exclude))

    def allowed_letters(self, mask: int, position: int) -> set[str]:
        """Which letters remain possible at a position, given a mask.

        This is the forward-checking primitive.  An empty result means the
        slot is dead, and that is established without enumerating one word.
        """
        table = self.masks[position]
        return {char for char in ALPHABET if mask & table[char]}

    def ids(self, mask: int) -> list:
        """The word ids in a mask, lowest first."""
        found = []
        while mask:
            low = mask & -mask
            found.append(low.bit_length() - 1)
            mask ^= low
        return found

    def iterate(self, mask: int):
        """Yield the words in a mask, lowest id first."""
        while mask:
            low = mask & -mask
            yield self.words[low.bit_length() - 1]
            mask ^= low

    def word_bit(self, word: str) -> int:
        return 1 << self.by_word[word]

    def word_id(self, word: str):
        """The id of a word, or None if the dictionary does not have it."""
        return self.by_word.get(word)


class Index:
    """The whole dictionary, partitioned by length."""

    def __init__(self, entries: list[Entry], scores: dict = None):
        buckets: dict[int, list[Entry]] = {}
        for entry in entries:
            buckets.setdefault(len(entry.text), []).append(entry)
        self.lengths = {
            length: LengthIndex(bucket, length, scores)
            for length, bucket in buckets.items()
        }

    def __getitem__(self, length: int) -> LengthIndex:
        return self.lengths[length]

    def __contains__(self, length: int) -> bool:
        return length in self.lengths

    def summary(self) -> str:
        return ", ".join(
            f"{length}:{len(self.lengths[length].words)}"
            for length in sorted(self.lengths)
        )
