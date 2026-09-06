"""Barred grids: notation, symmetry, and pattern generation.

A barred grid removes no squares.  Every cell holds a letter, and the entries
are separated by lines drawn between neighbours, so the two directions are
independent in a way they never are in a blocked grid: `right_bars` decides
every across run and `bottom_bars` every down run, and neither touches the
other.  That is what makes generation here a matter of cutting each line
separately rather than searching a coupled block set.

The shape targeted is read off a published Mephisto, whose measurements are
pinned in the tests.  The one number that matters, and the one this project
first got wrong by guessing it from a picture, is how much of the grid is
unchecked: a third of it, not a tenth.  Barred grids get an unchecked letter
from a run of length one, and they use a great many of them.
"""

from __future__ import annotations

import functools
import math
import random

from .grid import Grid

# Read off two published grids, a Mephisto and an Azed.  Entries are long and
# mostly checked, but a third of the grid is unchecked, because the single
# cells that separate the entries are themselves letters.  Fewer unchecked
# cells than this interlocks the grid far more tightly than any real barred
# puzzle, and it will not fill.
#
# The minimum was 5 while the Mephisto was the only grid to hand, which is the
# hazard of a corpus of one: it has no four-letter entry, but the Azed has six,
# and the rule as written called each of them a run too short to be a light and
# then reported the cells around it as isolated.  A published puzzle failing a
# rule condemns the rule.
BARRED_RULES = dict(
    min_entry_length=4,
    max_consecutive_unchecked=1,
    min_checked_fraction=0.6,
    forbid_run_length_two=True,
)


def parse(text: str) -> Grid:
    """Read the diagram notation: '_' for a bar beneath, '|' for one to the right.

    Cells sit at even offsets of a line and the separator between two of them
    at the odd offset in between, so a row of a 12-grid is 23 characters.
    """
    lines = [line for line in text.rstrip("\n").split("\n") if line.strip()]
    size = len(lines)
    grid = Grid(size=size)
    for row, line in enumerate(lines):
        cells, seps = line[0::2], line[1::2]
        if len(cells) != size:
            raise ValueError(f"row {row} has {len(cells)} cells, expected {size}")
        for col, mark in enumerate(cells):
            if mark == "_":
                grid.bottom_bars.add((row, col))
            elif mark != "*":
                raise ValueError(f"row {row}, col {col}: unexpected {mark!r}")
        for col, mark in enumerate(seps):
            if mark == "|":
                grid.right_bars.add((row, col))
            elif mark != " ":
                raise ValueError(f"row {row}, separator {col}: unexpected {mark!r}")
    return grid


def render(grid: Grid) -> str:
    """The inverse of `parse`, for reading a generated pattern back."""
    rows = []
    for row in range(grid.size):
        line = []
        for col in range(grid.size):
            line.append("_" if (row, col) in grid.bottom_bars else "*")
            if col < grid.size - 1:
                line.append("|" if (row, col) in grid.right_bars else " ")
        rows.append("".join(line))
    return "\n".join(rows)


def mirror_bars(grid: Grid) -> tuple[set, set]:
    """The bar sets under a half turn.

    A bar is an edge, not a cell, so it does not use `Grid.partner`.  The
    right bar after (r, c) lies between (r, c) and (r, c + 1); rotating both
    ends puts it between (n-1-r, n-2-c) and (n-1-r, n-1-c), which is the right
    bar after (n-1-r, n-2-c).  The bottom bar moves the same way downwards.
    """
    n = grid.size
    right = {(n - 1 - r, n - 2 - c) for r, c in grid.right_bars}
    bottom = {(n - 2 - r, n - 1 - c) for r, c in grid.bottom_bars}
    return right, bottom


@functools.lru_cache(maxsize=None)
def compositions(size: int, min_entry: int) -> tuple[tuple[int, ...], ...]:
    """Every way to cut a line into runs that are one cell or a whole entry.

    Nothing between the two is allowed: a run of two, three or four is neither
    an unchecked letter nor a light, and is exactly what the rules forbid.
    """
    if size == 0:
        return ((),)
    out = []
    for part in [1] + list(range(min_entry, size + 1)):
        if part <= size:
            for rest in compositions(size - part, min_entry):
                out.append((part,) + rest)
    return tuple(out)


@functools.lru_cache(maxsize=None)
def run_lengths(comp: tuple[int, ...], size: int) -> tuple[int, ...]:
    """For each offset along a line, the length of the run containing it.

    Cached, and returning a tuple so that caching is safe: the column search
    asks for the same handful of compositions tens of thousands of times.
    """
    out = []
    for part in comp:
        out.extend([part] * part)
    assert len(out) == size
    return tuple(out)


def _line_bars(comp: tuple[int, ...]) -> list[int]:
    """Offsets a run ends at, excluding the edge, which needs no bar."""
    out, at = [], 0
    for part in comp[:-1]:
        at += part
        out.append(at - 1)
    return out


def pattern(
    size: int = 12,
    *,
    min_entry: int = 4,
    decay: float = 0.55,
    column_decay: float = 1.0,
    openness: float = 1.0,
    short_bias: float = 1.0,
    rng: random.Random | None = None,
    attempts: int = 400,
) -> Grid | None:
    """One symmetric bar pattern, or None if this draw of rows admits no columns.

    Rows fix every across run and columns every down run, and each half of the
    grid determines the other by rotation, so only the first half of each is
    drawn.  `decay` biases the rows towards few runs, because a Mephisto row
    usually holds two entries, and `openness` the other way, rewarding the
    single cells that carry the unchecked letters.

    Columns are drawn uniformly by default (`column_decay` of 1.0) and that is
    a measured choice, not an oversight.  The two directions are not
    interchangeable here: the rows are drawn freely and the columns have to fit
    around whatever the rows did, and a uniform draw supplies single cells
    generously because most compositions of a line have many parts.  Biasing
    the columns towards few runs as well looks tidier and fills far worse --
    the patterns it produces were filled 21% of the time against 55%.

    The two directions cannot be drawn independently, which is the thing that
    took a published grid to see.  A cell single in *both* directions belongs to
    no entry at all, and two unchecked letters cannot sit side by side, so where
    a row puts its single cells constrains where every column may put its own.
    Sampling the two separately collides constantly: raising `openness` at all
    took the yield of legal grids from two per cent to zero.  So the rows are
    sampled and the columns are then *searched*, left to right, against them.

    Nothing here checks the fraction of each across entry that ends up checked,
    because that depends on every column at once.  Callers validate.
    """
    rng = rng or random.Random()
    choices = compositions(size, min_entry)

    def bias(rate: float) -> list:
        return [
            rate ** (len(c) - 1)
            * openness ** sum(1 for part in c if part == 1)
            * short_bias ** sum(1 for part in c if part == min_entry)
            for c in choices
        ]

    row_weights, column_weights = bias(decay), bias(column_decay)
    half = size // 2

    # Rows first, and freely: nothing constrains them until columns exist.
    rows = [rng.choices(choices, row_weights)[0] for _ in range(half)]
    rows += [tuple(reversed(rows[size - 1 - r])) for r in range(half, size)]
    across = [run_lengths(comp, size) for comp in rows]

    columns: list[tuple[int, ...] | None] = [None] * size

    def column_ok(col: int, comp: tuple[int, ...]) -> bool:
        down = run_lengths(comp, size)
        previous_unchecked = False
        for row in range(size):
            if across[row][col] == 1 and down[row] == 1:
                return False                      # in no entry at all
            if down[row] > 1:
                # Inside a down entry an unchecked letter is one the row left
                # single; two in a row is the rule that forbids UU.
                unchecked = across[row][col] == 1
                if unchecked and previous_unchecked:
                    return False
                previous_unchecked = unchecked
            else:
                previous_unchecked = False
        return True

    def pair_ok(left: int, right: int) -> bool:
        """No across entry may carry two unchecked letters side by side."""
        a, b = run_lengths(columns[left], size), run_lengths(columns[right], size)
        for row in range(size):
            if across[row][left] > 1 and across[row][right] > 1:
                if a[row] == 1 and b[row] == 1:
                    return False
        return True

    def weighted_order() -> list[int]:
        """The compositions in a random order that respects their weights.

        Gumbel-top-k: adding Gumbel noise to each log weight and sorting gives
        a draw without replacement in weight order, which is what a column
        search wants -- it must be able to reach every composition, but should
        try the plausible ones first.  Shuffling uniformly here was a real bug
        for a while, and a quiet one: `decay` and `openness` then applied to
        the rows only, and the docstring above claimed otherwise.
        """
        keys = [
            math.log(w) - math.log(-math.log(rng.random())) if w > 0 else -math.inf
            for w in column_weights
        ]
        return sorted(range(len(choices)), key=lambda i: -keys[i])

    def place(col: int, budget: list[int]) -> bool:
        if col == half:
            # The middle pair is the one adjacency symmetry does not give free.
            return pair_ok(half - 1, half)
        for index in weighted_order():
            if budget[0] <= 0:
                return False
            budget[0] -= 1
            comp = choices[index]
            if not column_ok(col, comp):
                continue
            columns[col] = comp
            columns[size - 1 - col] = tuple(reversed(comp))
            if col and not pair_ok(col - 1, col):
                columns[col] = columns[size - 1 - col] = None
                continue
            if place(col + 1, budget):
                return True
            columns[col] = columns[size - 1 - col] = None
        return False

    if not place(0, [attempts]):
        return None

    grid = Grid(size=size)
    for row, comp in enumerate(rows):
        for cut in _line_bars(comp):
            grid.right_bars.add((row, cut))
    for col, comp in enumerate(columns):
        for cut in _line_bars(comp):
            grid.bottom_bars.add((cut, col))
    # The bars went straight into the sets rather than through a mutator, so
    # the derivation cache must not have been read yet.  It has not: the grid
    # was made four lines ago.
    return grid
