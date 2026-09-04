"""Grid representation and slot derivation.

The grid holds two things: which cells are blocked, and which letters are
committed.  Everything the search reasons about — entries, crossings,
checkedness — is derived from the block set, never stored alongside it.

Bar sets are carried but unused for blocked grids.  They are here so that the
barred variant later changes the run-splitting predicate only, not the shape of
this class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

ACROSS = "across"
DOWN = "down"

BLOCK = "#"
EMPTY = "."

# typing.Tuple, not tuple[...]: this alias is evaluated at import time, so
# `from __future__ import annotations` does not defer it.  It is the only
# runtime generic subscript in the package.
Cell = Tuple[int, int]


@dataclass(frozen=True)
class Slot:
    """A maximal run of unblocked cells.

    A run is an *entry* when it is long enough to hold a word.  Runs of length
    one are legal and carry no entry; the cell in them is unchecked in the
    perpendicular direction.  Runs of length two are illegal, but this class
    represents them anyway so the validator has something to report.
    """

    row: int
    col: int
    direction: str
    length: int

    def __post_init__(self):
        # Built once, here, rather than on every access.  A profile of one
        # ordinary run showed 1.4 million calls to `cells`, because
        # `Grid.pattern` walks them for every candidate word at every node.
        # The class is frozen, hence the __setattr__.
        if self.direction == ACROSS:
            cells = tuple((self.row, self.col + i) for i in range(self.length))
        else:
            cells = tuple((self.row + i, self.col) for i in range(self.length))
        object.__setattr__(self, "cells", cells)


@dataclass
class Grid:
    size: int
    blocks: set[Cell] = field(default_factory=set)
    letters: dict[Cell, str] = field(default_factory=dict)
    right_bars: set[Cell] = field(default_factory=set)
    bottom_bars: set[Cell] = field(default_factory=set)

    def __post_init__(self):
        # Derivations that depend only on the blocks are cached against a
        # stamp bumped whenever a block moves.  Every mutation in the project
        # goes through add_block or remove_block, or happens during
        # construction while the cache is still empty, so nothing can read a
        # stale entry.  Anything that reaches into `blocks` directly after
        # construction must bump `_stamp` itself.
        object.__setattr__(self, "_stamp", 0)
        object.__setattr__(self, "_derived", {})

    # -- block placement ---------------------------------------------------

    def partner(self, cell: Cell) -> Cell:
        """The 180-degree rotational image of a cell."""
        row, col = cell
        return (self.size - 1 - row, self.size - 1 - col)

    def add_block(self, cell: Cell) -> tuple[Cell, Cell]:
        """Block a cell and its rotational partner.

        Blocks are only ever added in pairs.  Symmetry is then an invariant of
        construction rather than something the search has to rediscover, and
        the validator's symmetry check becomes a test of this method rather
        than of the generator.
        """
        mate = self.partner(cell)
        self._stamp += 1
        self._derived.clear()
        self.blocks.add(cell)
        self.blocks.add(mate)
        self.letters.pop(cell, None)
        self.letters.pop(mate, None)
        return cell, mate

    def remove_block(self, cell: Cell) -> None:
        self._stamp += 1
        self._derived.clear()
        self.blocks.discard(cell)
        self.blocks.discard(self.partner(cell))

    # -- derivation --------------------------------------------------------

    def runs(self, direction: str) -> list[Slot]:
        """Every maximal unblocked run in one direction, including length-1 runs."""
        key = ("runs", direction)
        hit = self._derived.get(key)
        if hit is not None:
            return hit
        found: list[Slot] = []
        for line in range(self.size):
            start = None
            for offset in range(self.size + 1):
                cell = (line, offset) if direction == ACROSS else (offset, line)
                closed = offset == self.size or cell in self.blocks
                if closed:
                    if start is not None:
                        head = (line, start) if direction == ACROSS else (start, line)
                        found.append(Slot(head[0], head[1], direction, offset - start))
                        start = None
                elif start is None:
                    start = offset
        self._derived[key] = found
        return found

    def slots(self, min_length: int = 3) -> list[Slot]:
        """Runs long enough to be entries."""
        key = ("slots", min_length)
        hit = self._derived.get(key)
        if hit is not None:
            return hit
        found = [
            run
            for direction in (ACROSS, DOWN)
            for run in self.runs(direction)
            if run.length >= min_length
        ]
        self._derived[key] = found
        return found

    def checked_cells(self, min_length: int = 3) -> set[Cell]:
        """Cells belonging to an entry in both directions."""
        key = ("checked", min_length)
        hit = self._derived.get(key)
        if hit is not None:
            return hit
        across: set[Cell] = set()
        down: set[Cell] = set()
        for slot in self.slots(min_length):
            target = across if slot.direction == ACROSS else down
            target.update(slot.cells)
        result = across & down
        self._derived[key] = result
        return result

    def crossings(self, min_length: int = 3) -> dict[Cell, list[tuple[Slot, int]]]:
        """For each cell, the entries through it and the index within each."""
        table: dict[Cell, list[tuple[Slot, int]]] = {}
        for slot in self.slots(min_length):
            for index, cell in enumerate(slot.cells):
                table.setdefault(cell, []).append((slot, index))
        return table

    def pattern(self, slot: Slot) -> str:
        """The committed letters of a slot, with EMPTY for unknowns."""
        return "".join(self.letters.get(cell, EMPTY) for cell in slot.cells)

    def numbering(self, min_length: int = 3):
        """Clue numbers in reading order, with the entries they start.

        A white cell earns a number when an entry begins there, in either
        direction, and a cell beginning both across and down entries carries
        one number shared by the two.  That sharing is the whole subtlety: it
        is why the across list and the down list have gaps in them rather than
        each running 1, 2, 3.

        Returns (numbers, across, down): a cell -> number map, and the two
        lists of (number, slot) ordered as they would be printed.
        """
        heads = {ACROSS: {}, DOWN: {}}
        for slot in self.slots(min_length):
            heads[slot.direction][(slot.row, slot.col)] = slot

        numbers: dict = {}
        across: list = []
        down: list = []
        count = 0
        for row in range(self.size):
            for col in range(self.size):
                cell = (row, col)
                starts_across = heads[ACROSS].get(cell)
                starts_down = heads[DOWN].get(cell)
                if not starts_across and not starts_down:
                    continue
                count += 1
                numbers[cell] = count
                if starts_across:
                    across.append((count, starts_across))
                if starts_down:
                    down.append((count, starts_down))
        return numbers, across, down

    # -- serialisation -----------------------------------------------------

    def render(self) -> str:
        rows = []
        for row in range(self.size):
            rows.append(
                "".join(
                    BLOCK
                    if (row, col) in self.blocks
                    else self.letters.get((row, col), EMPTY)
                    for col in range(self.size)
                )
            )
        return "\n".join(rows)

    def pretty(
        self,
        block: str = "\u00b7",
        empty: str = " ",
        upper: bool = True,
        gap: str = " ",
    ) -> str:
        """A readable rendering, for eyeballing rather than round-tripping.

        `render` stays the canonical form because `parse` has to reverse it.
        This one is free to use whatever reads best: the default is a middle
        dot for blocks, which recedes instead of competing with the letters,
        and column gaps so rows and columns line up as a square rather than a
        squashed rectangle.
        """
        rows = []
        for row in range(self.size):
            cells = []
            for col in range(self.size):
                if (row, col) in self.blocks:
                    cells.append(block)
                else:
                    char = self.letters.get((row, col))
                    if char is None:
                        cells.append(empty)
                    else:
                        cells.append(char.upper() if upper else char)
            rows.append(gap.join(cells))
        return "\n".join(rows)

    @classmethod
    def parse(cls, text: str) -> "Grid":
        rows = [line.strip() for line in text.strip().splitlines() if line.strip()]
        grid = cls(size=len(rows))
        for row, line in enumerate(rows):
            for col, char in enumerate(line):
                if char == BLOCK:
                    grid.blocks.add((row, col))
                elif char != EMPTY:
                    grid.letters[(row, col)] = char.lower()
        return grid

    def annotate(self, min_length: int = 3, gap: str = "", block: str = BLOCK) -> str:
        """Render with C/U marks in place of letters.

        Rule 4 violations are invisible in a plain letter grid, so this is the
        view to read when eyeballing output.  Defaults stay compact because
        tests assert on exact rows; pass gap=" " to read it alongside pretty().
        """
        checked = self.checked_cells(min_length)
        rows = []
        for row in range(self.size):
            rows.append(
                gap.join(
                    block
                    if (row, col) in self.blocks
                    else ("C" if (row, col) in checked else "U")
                    for col in range(self.size)
                )
            )
        return "\n".join(rows)
