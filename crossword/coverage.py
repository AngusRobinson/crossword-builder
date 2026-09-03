"""How many words from a target list a grid can be made to hold.

This is the project's objective function, and until now nothing computed it.
The generator ranked patterns by entry-length distribution -- a proxy for
"pleasant grid", not for "fits my words" -- so its search had no idea what it
was optimising for.

Two quantities, and the distinction between them is the whole point:

`ceiling` ignores letters entirely and asks how many targets could even fit
the slot lengths.  It is a bound, computed in microseconds, and no search can
beat it.  `cover` actually places words and completes the grid, so it reports
what was really achieved.

Report the ratio.  Coverage against the list size confounds a weak search
with an impossible list: a 20-word list drawn arbitrarily has a mean ceiling
of 80% before a single letter is considered, so 16/20 may be a perfect score.
Coverage against the ceiling is the number that means something.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .fill import Filler
from .grid import Grid
from .index import Index
from .rules import RuleSet


# -- the bound -------------------------------------------------------------


def ceiling(profile: dict, targets) -> int:
    """Multiset intersection of target lengths with available slot lengths.

    Letters are not consulted, so this over-counts: it assumes any word can
    cross any other.  That is what makes it a bound rather than an estimate.
    """
    want: dict = {}
    for word in targets:
        want[len(word)] = want.get(len(word), 0) + 1
    return sum(min(count, profile.get(length, 0)) for length, count in want.items())


def best_ceiling(patterns, targets) -> tuple:
    """The most promising pattern in a library, and its bound."""
    best, best_n = None, -1
    for pattern in patterns:
        n = ceiling(pattern.profile(), targets)
        if n > best_n:
            best, best_n = pattern, n
    return best, best_n


# -- the achieved coverage -------------------------------------------------


@dataclass
class Cover:
    """The outcome of one attempt to build a grid around a target list."""

    placed: tuple = ()
    grid: object = None
    ok: bool = False           # did the rest of the grid fill?
    ceiling: int = 0      # the bound for the whole library, not one pattern
    pattern: object = None
    attempts: int = 0
    stats: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.placed)

    @property
    def score(self) -> float:
        """Achieved coverage as a fraction of what was even possible."""
        return self.n / self.ceiling if self.ceiling else 0.0

    def __str__(self) -> str:
        state = "filled" if self.ok else "UNFILLED"
        return f"{self.n}/{self.ceiling} targets ({self.score:.0%}), {state}"


def _fits(pattern: str, word: str) -> bool:
    return len(pattern) == len(word) and all(
        p == "." or p == c for p, c in zip(pattern, word)
    )


def _alive(grid: Grid, index: Index, slots) -> bool:
    """Forward check: every slot still has at least one candidate word."""
    for slot in slots:
        if slot.length not in index:
            return False
        if not index[slot.length].match(grid.pattern(slot)):
            return False
    return True


def _seat_targets(grid, index, slots, targets, rng):
    """Greedily seat as many targets as the crossings allow.

    Most-constrained-target-first.  A target that fits only one slot has to
    take it, and finding that out after the slot is gone costs a restart, so
    it is chosen first.  Placement is undone whenever it kills another slot,
    which keeps every returned arrangement completable in principle.
    """
    remaining = list(targets)
    rng.shuffle(remaining)
    seated = []

    while remaining:
        options = {}
        for word in remaining:
            fitting = [
                slot
                for slot in slots
                if slot.length == len(word) and _fits(grid.pattern(slot), word)
            ]
            if fitting:
                options[word] = fitting
        if not options:
            break

        word = min(options, key=lambda w: (len(options[w]), rng.random()))
        choices = options[word]
        rng.shuffle(choices)

        for slot in choices:
            written = []
            for cell, char in zip(slot.cells, word):
                if cell not in grid.letters:
                    grid.letters[cell] = char
                    written.append(cell)
            rest = [s for s in slots if s is not slot]
            if _alive(grid, index, rest):
                seated.append((word, slot, written))
                slots = rest
                break
            for cell in written:
                del grid.letters[cell]
        remaining.remove(word)

    return seated, slots


def cover(
    pattern,
    index: Index,
    targets,
    rules: RuleSet | None = None,
    *,
    attempts: int = 8,
    fill_restarts: int = 3,
    relax: int = 3,
    seed: int | None = None,
) -> Cover:
    """Build a filled grid holding as many targets as possible.

    Randomised restarts, best kept.  On a fill failure the most recently
    seated target is lifted and the fill retried -- a grid that holds nine
    targets and completes is worth more than one that holds ten and does not,
    because the second is not a crossword.
    """
    rules = rules or RuleSet()
    rng = random.Random(seed)
    targets = [w for w in targets if len(w) in index]
    bound = ceiling(pattern.profile(rules.min_entry_length), targets)
    best = Cover(ceiling=bound, attempts=attempts)

    for attempt in range(attempts):
        grid = pattern.grid()
        slots = grid.slots(rules.min_entry_length)
        seated, _open = _seat_targets(grid, index, slots, targets, rng)

        for lift in range(relax + 1):
            if lift:
                if not seated:
                    break
                _word, _slot, written = seated.pop()
                for cell in written:
                    grid.letters.pop(cell, None)

            filler = Filler(
                grid, index, rules,
                node_budget=8000, seed=rng.randrange(1 << 30),
            )
            ok = filler.fill(restarts=fill_restarts)
            placed = tuple(word for word, _s, _w in seated)

            # A completed grid always beats an incomplete one, however many
            # targets the incomplete one holds.
            if (ok, len(placed)) > (best.ok, best.n):
                best = Cover(
                    placed=placed,
                    grid=Grid.parse(grid.render()) if ok else None,
                    ok=ok,
                    ceiling=bound,
                    attempts=attempt + 1,
                    stats={"nodes": filler.stats.nodes},
                )
            if ok:
                break
            grid.letters = dict(filler.preset)

        if best.ok and best.n == bound:
            break

    return best


def best_over_library(patterns, index, targets, rules=None, *, top=12, **kwargs):
    """Try the most promising patterns in a library, return the best cover.

    Patterns are tried in order of their bound: a pattern that cannot seat as
    many targets as one already achieved cannot improve on it, so the scan
    stops there rather than grinding through all 120.
    """
    rules = rules or RuleSet()
    scored = sorted(
        ((ceiling(p.profile(rules.min_entry_length), targets), -p.uses, i, p)
         for i, p in enumerate(patterns)),
        key=lambda t: (-t[0], t[1], t[2]),
    )[:top]

    best = Cover(ceiling=scored[0][0] if scored else 0)
    for bound, _uses, _i, pattern in scored:
        if best.ok and best.n >= bound:
            break
        got = cover(pattern, index, targets, rules, **kwargs)
        if (got.ok, got.n) > (best.ok, best.n):
            best = got
            best.pattern = pattern
    # cover() knows only its own pattern's bound.  Score against the best
    # bound the library offers, or a pattern that happened to be easy would
    # flatter the result.
    if scored:
        best.ceiling = scored[0][0]
    return best
