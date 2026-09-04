"""Write a finished grid out in the formats a setter actually uses.

Everything before this file produces a grid that lives in a terminal.  Exet
and Exolve are where clues get written and puzzles get published, so a grid
that cannot reach them is not finished, however good its fill.

Two formats, because they do different jobs.  ipuz is the interchange format
Exet imports, so that is the one to carry into clue-writing.  Exolve is a
self-contained HTML page that opens in a browser, so that is the one to look
at, or send to a test solver.

Neither carries clues, because this project does not write them.  Both leave
the clue slots empty with the answers attached, which is exactly the state a
setter wants to start from.
"""

from __future__ import annotations

import hashlib
import json

from .grid import ACROSS, BLOCK, DOWN, Grid

IPUZ_VERSION = "http://ipuz.org/v2"
IPUZ_KIND = "http://ipuz.org/crossword/crypticcrossword#1"


def enumeration(surface: str, length: int) -> str:
    """The bracketed length, split as the original spelling was.

    "maple leaf" gives (5,4) and "mother-in-law" gives (6-2-3), which is what
    a solver needs and what the fold to a bare fill string destroyed.  An
    apostrophe does not split a word: "friar's balsam" is two words, not
    three, so only spaces and hyphens count as breaks.
    """
    groups: list = []
    separators: list = []
    run = 0
    for char in surface:
        if char.isalpha():
            run += 1
        elif char in " \t-–—":
            if run:
                groups.append(run)
                separators.append("-" if char == "-" else ",")
                run = 0
    if run:
        groups.append(run)

    if not groups or sum(groups) != length:
        # The surface disagrees with the fill string -- a stray digit, or no
        # surface at all.  The bare length is always right.
        return f"({length})"

    out = str(groups[0])
    for separator, size in zip(separators, groups[1:]):
        out += separator + str(size)
    return f"({out})"


def spelled(surface: str, answer: str) -> str:
    """The answer as it should be written out, separators restored.

    Both formats write a multi-word answer with its spaces -- MAPLE LEAF, not
    MAPLELEAF -- and Exet's own files do the same for hyphens
    (STURGES-BOURNE).  The fill string has neither, so the separators are put
    back from the surface, and only if the letters still agree.
    """
    letters = [c for c in surface if c.isalpha()]
    if "".join(letters).lower() != answer.lower():
        return answer.upper()
    out = []
    for char in surface:
        if char.isalpha():
            out.append(char.upper())
        elif char in " \t-–—":
            out.append("-" if char == "-" else " ")
    return "".join(out).strip()


def _entries(grid: Grid, surfaces: dict, min_length: int):
    """(direction, number, slot, written answer, enumeration) for every entry."""
    _numbers, across, down = grid.numbering(min_length)
    out = []
    for direction, listing in ((ACROSS, across), (DOWN, down)):
        for number, slot in listing:
            answer = grid.pattern(slot)
            surface = (surfaces or {}).get(answer, answer)
            out.append((direction, number, slot,
                        spelled(surface, answer),
                        enumeration(surface, slot.length)))
    return out


# -- ipuz ------------------------------------------------------------------


def to_ipuz(grid: Grid, *, title: str = "Untitled", author: str = "",
            surfaces: dict = None, clues: dict = None,
            min_length: int = 3) -> dict:
    """The puzzle as an ipuz document, ready for Exet to import."""
    numbers, _across, _down = grid.numbering(min_length)
    clues = clues or {}

    puzzle = []
    solution = []
    for row in range(grid.size):
        cells = []
        values = []
        for col in range(grid.size):
            cell = (row, col)
            if cell in grid.blocks:
                cells.append({"cell": "#"})
                values.append({"value": "#"})
                continue
            # "0" is ipuz for "a white cell with no number on it".
            label = str(numbers.get(cell, 0))
            cells.append({"cell": label, "style": {}})
            values.append({"value": grid.letters.get(cell, "").upper()})
        puzzle.append(cells)
        solution.append(values)

    listing: dict = {"Across": [], "Down": []}
    for direction, number, _slot, answer, count in _entries(
        grid, surfaces, min_length
    ):
        key = "Across" if direction == ACROSS else "Down"
        text = clues.get((direction, number), "")
        listing[key].append({
            "number": str(number),
            "label": str(number),
            "clue": f"{text} {count}".strip(),
            "answer": answer,
        })

    return {
        "version": IPUZ_VERSION,
        "kind": [IPUZ_KIND],
        "dimensions": {"width": grid.size, "height": grid.size},
        "title": title,
        "author": author,
        "showenumerations": True,
        "puzzle": puzzle,
        "clues": listing,
        "solution": solution,
    }


def write_ipuz(grid: Grid, path: str, **kwargs) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(to_ipuz(grid, **kwargs), handle, indent=1)


# -- Exolve ----------------------------------------------------------------


EXOLVE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="stylesheet" type="text/css" href="https://\
viresh-ratnakar.github.io/exolve-m.css"/>
<script src="https://viresh-ratnakar.github.io/exolve-m.js"></script>
</head>
<body>
<script>
createExolve(`
{puzzle}
`);
</script>
</body>
</html>
"""


def to_exolve(grid: Grid, *, title: str = "Untitled", setter: str = "",
              surfaces: dict = None, clues: dict = None,
              min_length: int = 3, puzzle_id: str = None) -> str:
    """The puzzle as a standalone Exolve page.

    Note the inversion: Exolve writes blocks as "." and letters as themselves,
    where this project's own `render` uses "#" for a block and "." for an
    empty cell.  The two conventions collide on the same character, which is
    worth saying out loud rather than discovering in a browser.
    """
    clues = clues or {}
    if puzzle_id is None:
        digest = hashlib.sha1(grid.render().encode()).hexdigest()[:8]
        puzzle_id = f"cb-{digest}"

    rows = []
    for row in range(grid.size):
        cells = []
        for col in range(grid.size):
            cell = (row, col)
            if cell in grid.blocks:
                cells.append(".")
            else:
                cells.append(grid.letters.get(cell, "?").upper())
        rows.append("    " + "   ".join(cells))

    lines = [
        "exolve-begin",
        f"  exolve-id: {puzzle_id}",
        f"  exolve-width: {grid.size}",
        f"  exolve-height: {grid.size}",
        f"  exolve-title: {title}",
        f"  exolve-setter: {setter}",
        "  exolve-maker:",
        "    Grid: Crossword Builder",
        "  exolve-language: en Latin 1",
        "  exolve-grid:",
    ]
    lines.extend(rows)

    for direction, label in ((ACROSS, "exolve-across"), (DOWN, "exolve-down")):
        lines.append(f"  {label}:")
        for entry in _entries(grid, surfaces, min_length):
            if entry[0] != direction:
                continue
            _d, number, _slot, answer, count = entry
            text = clues.get((direction, number), "")
            lines.append(
                f"  {number} {text} {count} [{answer}]"
                if text else f"  {number} {count} [{answer}]"
            )
    lines.append("exolve-end")
    return EXOLVE_PAGE.format(puzzle="\n".join(lines))


def write_exolve(grid: Grid, path: str, **kwargs) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(to_exolve(grid, **kwargs))
