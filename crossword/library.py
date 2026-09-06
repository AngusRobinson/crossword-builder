"""The grid library: block patterns taken from puzzles that were published.

8,348 Guardian 15x15 cryptics use 130 distinct block patterns between them,
and one of those accounts for 458 puzzles on its own.  Setters do not invent
grids; they pick one.  That makes the library the baseline any generator has
to beat -- not a fallback for when generation fails.

Patterns are stored as rendered text rather than JSON so that a diff of this
file is readable, and so that `Grid.parse` is the only reader needed.  Ten of
the 130 fail `validate`, all of them one-offs used by nine puzzles or fewer;
`load` leaves them out unless asked for.

Extraction needs the corpus (see test_corpus.py); loading does not, which is
the point of checking the extracted file in.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

from .grid import BLOCK, Grid
from .rules import RuleSet, validate

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "grids.txt")
US_PATH = os.path.join(os.path.dirname(__file__), "grids-us.txt")
BARRED_PATH = os.path.join(os.path.dirname(__file__), "grids-barred.txt")

# The rule sets the two libraries are built to.  British grids leave about half
# the letters unchecked; American ones check every one, which is the whole
# difference and everything else follows from it.
BRITISH_RULES = dict(max_consecutive_unchecked=1, min_checked_fraction=0.5)
US_RULES = dict(max_consecutive_unchecked=0, min_checked_fraction=1.0)


def rules_for(style: str) -> RuleSet:
    """The rule set a style is built to."""
    if style == "us":
        return RuleSet(**US_RULES)
    if style == "barred":
        from .barred import BARRED_RULES

        return RuleSet(**BARRED_RULES)
    return RuleSet(**BRITISH_RULES)


def path_for(style: str) -> str:
    if style == "us":
        return US_PATH
    if style == "barred":
        return BARRED_PATH
    return DEFAULT_PATH


@dataclass(frozen=True)
class Pattern:
    """One grid pattern, with what the corpus says about it.

    A pattern is either blocked or barred and never both.  The two are stored
    in one class because everything that consumes a pattern -- the profile, the
    ceiling, the cover search -- reads slots, and slots do not care which kind
    of separator produced them.
    """

    size: int
    blocks: frozenset
    uses: int          # how many published puzzles used it
    source: str        # id of one puzzle that did, for tracing
    valid: bool        # whether it passes our rule set
    right_bars: frozenset = frozenset()
    bottom_bars: frozenset = frozenset()

    @property
    def barred(self) -> bool:
        return bool(self.right_bars or self.bottom_bars)

    def grid(self) -> Grid:
        """A fresh, empty Grid with these separators.  Never share one."""
        made = Grid(size=self.size)
        made.blocks = set(self.blocks)
        made.right_bars = set(self.right_bars)
        made.bottom_bars = set(self.bottom_bars)
        return made

    def profile(self, min_length: int = 3) -> dict:
        """How many entries of each length this pattern offers."""
        counts: dict = {}
        for slot in self.grid().slots(min_length):
            counts[slot.length] = counts.get(slot.length, 0) + 1
        return counts

    def render(self) -> str:
        if self.barred:
            from .barred import render

            return render(self.grid())
        return self.grid().render()


# -- reading and writing ---------------------------------------------------


def load(path: str = None, *, style: str = "british",
         valid_only: bool = True) -> list:
    """Read a grid library, most-used pattern first.

    `style` picks which: "british" is the Guardian library, 120 patterns from
    8,348 published puzzles, about half the letters unchecked.  "us" is 2,500
    patterns from pre-1965 New York Times puzzles, every letter checked.
    "barred" is 200 generated 12x12 patterns, no blocks at all, each one
    filled once before it was admitted; see build_barred_library.py.

    The two are shaped very differently.  British setters reuse grids heavily
    -- 8,348 puzzles share 130 patterns -- so the library is close to a census
    and each pattern carries how often it was used.  American grids are
    effectively never reused: 4,451 puzzles gave 3,091 distinct patterns, so
    that library is a sample and `uses` is zero throughout.
    """
    if path is None:
        path = path_for(style)
    patterns = []
    with open(path, encoding="utf-8") as handle:
        block: list = []
        header = None
        for line in handle:
            line = line.rstrip("\n")
            if line.startswith("#!"):
                if header is not None:
                    patterns.append(_build(header, block))
                header, block = json.loads(line[2:]), []
            elif line.strip() and header is not None:
                block.append(line.strip())
        if header is not None:
            patterns.append(_build(header, block))

    if valid_only:
        patterns = [p for p in patterns if p.valid]
    return sorted(patterns, key=lambda p: (-p.uses, p.source))


def _build(header: dict, rows: list) -> Pattern:
    """One record of a library file.

    The two notations are told apart by width, which is not a trick: a blocked
    row is one character per cell, and a barred one carries the separator
    between each pair as well, so it is always 2n-1 wide.
    """
    size = len(rows)
    common = dict(size=size, uses=header["uses"], source=header["source"],
                  valid=header["valid"])
    if rows and len(rows[0]) == 2 * size - 1:
        from .barred import parse

        grid = parse("\n".join(rows))
        return Pattern(blocks=frozenset(), right_bars=frozenset(grid.right_bars),
                       bottom_bars=frozenset(grid.bottom_bars), **common)
    blocks = frozenset(
        (r, c) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == BLOCK
    )
    return Pattern(blocks=blocks, **common)


DEFAULT_BANNER = (
    "# Block patterns of published Guardian 15x15 cryptics.\n"
    "# Geometry only: no clue, solution or title is reproduced here.\n"
    "# Generated by crossword.library.extract; see build_library.py.\n"
)


def save(patterns: list, path: str = DEFAULT_PATH, banner: str = None) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            (banner or DEFAULT_BANNER)
            + "# Each record is a JSON header on a '#!' line, then the grid.\n"
        )
        for pattern in patterns:
            handle.write(
                "\n#!"
                + json.dumps(
                    {
                        "uses": pattern.uses,
                        "source": pattern.source,
                        "valid": pattern.valid,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
            handle.write(pattern.render() + "\n")


# -- extraction ------------------------------------------------------------


def grid_from_guardian(path: str):
    """Recover a block pattern from a Guardian JSON.  Geometry only.

    Every cell an entry passes through is white; everything else is a block.
    Clues and solutions are not read.
    """
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    size = data["dimensions"]["cols"]
    if data["dimensions"]["rows"] != size:
        return None
    white = set()
    for entry in data["entries"]:
        x, y = entry["position"]["x"], entry["position"]["y"]
        for i in range(entry["length"]):
            white.add((y, x + i) if entry["direction"] == "across" else (y + i, x))
    grid = Grid(size=size)
    grid.blocks = {
        (r, c) for r in range(size) for c in range(size) if (r, c) not in white
    }
    return grid


def extract(corpus: str, size: int = 15, rules: RuleSet | None = None) -> list:
    """Walk a corpus directory and collect its distinct block patterns."""
    rules = rules or RuleSet()
    seen: dict = {}
    for path in sorted(glob.glob(os.path.join(corpus, "**", "*.JSON"), recursive=True)):
        try:
            grid = grid_from_guardian(path)
        except (KeyError, ValueError, json.JSONDecodeError, OSError):
            continue
        if grid is None or grid.size != size:
            continue
        key = frozenset(grid.blocks)
        if key in seen:
            seen[key][0] += 1
        else:
            seen[key] = [1, os.path.basename(path).split(".")[0], grid]

    patterns = [
        Pattern(
            size=size,
            blocks=key,
            uses=uses,
            source=source,
            valid=not validate(grid, rules),
        )
        for key, (uses, source, grid) in seen.items()
    ]
    return sorted(patterns, key=lambda p: (-p.uses, p.source))
