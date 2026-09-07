"""Crosswords whose letters, not just whose blocks, survive a half-turn.

Ordinary grids are already symmetric under a half-turn in their *pattern*:
that is the convention, and `rules.symmetry` enforces it. This asks for the
same of the fill, so that grid[r][c] == grid[n-1-r][n-1-c] and the whole
diagram reads the same upside down.

What that does to the entries is the whole problem. The across entry at
(r, c) of length L maps to the across entry at (n-1-r, n-1-c-L+1), and the
letters arrive reversed, so entries pair off and each pair holds one word and
its reverse. An entry mapped onto itself must be a palindrome. Half the
entries are therefore free and the other half are dictated, and every free one
has to be a word whose reverse is also a word.

That is a savage cut. Wiktionary has 44,612 six-letter words and 172 usable
reversible pairs among them; at ten letters it has 134,944 words and *no*
reversible pairs at all. Which is why the shape of the grid decides
feasibility before the search starts: a British 15x15 wants two ten-letter
entries and cannot be filled at any effort, while an American one leans on
threes to sixes, where the stock is in the hundreds. 341 of the 2,500 grids in
the American library clear their own vocabulary requirement; 3 of the 120
British ones do.

The search itself is the usual one -- most-constrained entry first, abandon a
branch when some entry has no candidate left -- with one change that keeps it
exact. A word `w` in slot A needs `reverse(w)` to fit slot B, and `reverse(w)`
matches B's pattern exactly when `w` matches B's pattern reversed. So the two
constraints merge into a single pattern before the dictionary is consulted,
and the candidate set is neither over- nor under-counted.
"""

from __future__ import annotations

import math
import random

from crossword.grid import Grid


class Budget(Exception):
    """Raised to unwind when a search has spent its nodes."""


def pair_slots(grid: Grid, min_length: int = 3):
    """Entries grouped by what the half-turn does to them.

    Returns (pairs, singles). A grid whose blocks are not themselves
    half-turn symmetric will have entries whose partner is not an entry; those
    are returned in neither list, and `unpaired` reports them.
    """
    n = grid.size
    slots = grid.slots(min_length)
    index = {(s.row, s.col, s.direction): s for s in slots}
    pairs, singles, orphans = [], [], []
    seen = set()
    for slot in slots:
        key = (slot.row, slot.col, slot.direction)
        if key in seen:
            continue
        if slot.direction == "across":
            mate = (n - 1 - slot.row, n - 1 - slot.col - slot.length + 1,
                    "across")
        else:
            mate = (n - 1 - slot.row - slot.length + 1, n - 1 - slot.col,
                    "down")
        if mate == key:
            singles.append(slot)
            seen.add(key)
        elif mate in index:
            pairs.append((slot, index[mate]))
            seen.add(key)
            seen.add(mate)
        else:
            orphans.append(slot)
            seen.add(key)
    return pairs, singles, orphans


def reversible(entries):
    """The words whose reverse is also a word. Everything else is unusable."""
    text = {entry.text for entry in entries}
    return [entry for entry in entries if entry.text[::-1] in text]


def _merge(one: str, two: str):
    """One pattern satisfying both, or None if they disagree anywhere."""
    out = []
    for a, b in zip(one, two):
        if a == ".":
            out.append(b)
        elif b == "." or a == b:
            out.append(a)
        else:
            return None
    return "".join(out)


def _order(bucket, ids, rng, commonness, aim, cap):
    """Candidates best first: Gumbel-top-k, as the filler uses."""
    quantile = bucket.quantile
    if commonness <= 0 or quantile is None:
        chosen = list(ids)
        rng.shuffle(chosen)
        return chosen[:cap]
    scored = []
    for word_id in ids:
        jolt = -math.log(-math.log(rng.random()))
        scored.append((jolt - commonness * abs(quantile[word_id] - aim) * 4.0,
                       word_id))
    scored.sort(key=lambda pair: -pair[0])
    return [word_id for _weight, word_id in scored[:cap]]


def solve(grid: Grid, index, *, seed: int = 0, node_budget: int = 200_000,
          branch_cap: int = 200, commonness: float = 0.0, aim: float = 0.85,
          min_length: int = 3, distinct: bool = True):
    """Fill `grid` so that a half-turn leaves it unchanged.

    `index` must be built from reversible words only -- see `reversible` --
    because every free entry needs its reverse to be a word too.
    """
    pairs, singles, orphans = pair_slots(grid, min_length)
    if orphans:
        raise ValueError(
            f"{len(orphans)} entries have no partner under a half-turn, so "
            f"this grid's blocks are not half-turn symmetric: "
            f"{orphans[0].row, orphans[0].col, orphans[0].direction}")

    # One decision per pair, plus one per self-paired entry.
    free = [(a, b) for a, b in pairs] + [(s, None) for s in singles]
    rng = random.Random(seed)
    placed: dict = {}
    used: set = set()
    spent = [0]

    def candidates(a, b):
        """The exact mask for this decision, or None if it is already dead."""
        bucket = index.lengths.get(a.length)
        if bucket is None:
            return None, None
        want = grid.pattern(a)
        # reverse(w) fits b  <=>  w fits b's pattern reversed.
        other = grid.pattern(b if b is not None else a)[::-1]
        merged = _merge(want, other)
        if merged is None:
            return None, None
        return bucket, bucket.match(merged)

    def write(slot, word):
        written = []
        for cell, char in zip(slot.cells, word):
            if cell not in grid.letters:
                grid.letters[cell] = char
                written.append(cell)
            elif grid.letters[cell] != char:
                for done in written:
                    del grid.letters[done]
                return None
        return written

    def place():
        if len(placed) == len(free):
            return True
        spent[0] += 1
        if spent[0] > node_budget:
            raise Budget()

        best, best_mask, best_bucket, fewest = None, 0, None, None
        for entry in free:
            if entry[0] in placed:
                continue
            bucket, mask = candidates(*entry)
            if mask is None or mask == 0:
                return False
            count = bin(mask).count("1")
            if fewest is None or count < fewest:
                best, best_mask, best_bucket, fewest = entry, mask, bucket, count
        a, b = best

        for word_id in _order(best_bucket, best_bucket.ids(best_mask), rng,
                              commonness, aim, branch_cap):
            word = best_bucket.words[word_id]
            mirror = word[::-1]
            if b is None:
                if word != mirror:
                    continue                  # a self-paired entry must be one
            elif distinct and word == mirror:
                # A palindrome in a *paired* slot writes itself into both
                # halves, so the grid carries the same entry twice. That is
                # how ESSE and IRORI each appeared at both ends of the first
                # fill this found.
                continue
            if distinct and (word in used or (b is not None and mirror in used)):
                continue
            first = write(a, word)
            if first is None:
                continue
            second = [] if b is None else write(b, mirror)
            if second is None:
                for cell in first:
                    del grid.letters[cell]
                continue
            placed[a] = word
            used.add(word)
            if b is not None:
                used.add(mirror)
            if place():
                return True
            del placed[a]
            used.discard(word)
            if b is not None:
                used.discard(mirror)
            for cell in first + second:
                del grid.letters[cell]
        return False

    try:
        if place():
            return dict(placed), spent[0]
    except Budget:
        pass
    return None, spent[0]


def is_rotational(grid: Grid) -> bool:
    """Does this grid actually read the same after a half-turn?"""
    n = grid.size
    for (row, col), char in grid.letters.items():
        if grid.letters.get((n - 1 - row, n - 1 - col)) != char:
            return False
    return True
