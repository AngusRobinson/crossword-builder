"""Numbering, and the two output formats.

Both formats are checked by reading them back and rebuilding the grid, not by
eyeballing a sample.  A format that cannot be parsed back to what went in is
broken whatever it looks like.
"""

import json
import re

import pytest

from crossword import export, library
from crossword.export import enumeration
from crossword.grid import ACROSS, DOWN, Grid
from crossword.index import Index
from crossword.fill import Filler


@pytest.fixture(scope="module")
def filled(index):
    grid = library.load()[0].grid()
    filler = Filler(grid, index, seed=11)
    assert filler.fill(), "fixture grid must fill"
    return grid


# -- numbering -------------------------------------------------------------


def test_numbering_shares_one_number_between_directions():
    """A cell starting both an across and a down entry carries one number.

    This is why the across and down lists have gaps rather than each counting
    1, 2, 3 -- the classic thing to get wrong.
    """
    grid = Grid.parse(
        "...#...\n"
        "...#...\n"
        "...#...\n"
        "#######\n"
        "...#...\n"
        "...#...\n"
        "...#..."
    )
    numbers, across, down = grid.numbering()
    # (0,1) and (0,2) start down entries but no across entry, so they take
    # numbers 2 and 3 and the second across entry is 4, not 2.
    assert numbers[(0, 0)] == 1
    assert numbers[(0, 1)] == 2
    assert numbers[(0, 4)] == 4
    # 1 starts both an across and a down entry, so it appears in both lists.
    assert across[0][0] == 1 and down[0][0] == 1
    assert [n for n, _s in across] == [1, 4, 7, 8, 9, 10, 11, 14, 17, 18, 19, 20]
    assert [n for n, _s in down] == [1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16]
    assert max(numbers.values()) == len(numbers) == 20


def test_numbering_is_in_reading_order():
    grid = library.load()[0].grid()
    numbers, _a, _d = grid.numbering()
    ordered = sorted(numbers, key=lambda cell: numbers[cell])
    assert ordered == sorted(numbers)          # (row, col) order is reading order
    assert list(numbers[c] for c in ordered) == list(range(1, len(numbers) + 1))


# -- enumeration -----------------------------------------------------------


@pytest.mark.parametrize("surface,length,expected", [
    ("maple leaf", 9, "(5,4)"),
    ("mother-in-law", 11, "(6-2-3)"),
    ("twelfth night", 12, "(7,5)"),
    ("friar's balsam", 12, "(6,6)"),      # an apostrophe does not split
    ("agenda", 6, "(6)"),
    ("nonsense", 5, "(5)"),               # surface disagrees: trust the length
    ("", 4, "(4)"),
])
def test_enumeration(surface, length, expected):
    assert enumeration(surface, length) == expected


# -- ipuz ------------------------------------------------------------------


def test_ipuz_round_trips_the_grid(filled, tmp_path):
    path = tmp_path / "p.ipuz"
    export.write_ipuz(filled, str(path), title="T", author="A")
    doc = json.load(open(path, encoding="utf-8"))

    rebuilt = Grid(size=doc["dimensions"]["width"])
    for row, cells in enumerate(doc["solution"]):
        for col, cell in enumerate(cells):
            if cell["value"] == "#":
                rebuilt.blocks.add((row, col))
            else:
                rebuilt.letters[(row, col)] = cell["value"].lower()
    assert rebuilt.render() == filled.render()

    # Blocks and numbers must agree between the two parallel arrays.
    numbers, _a, _d = filled.numbering()
    for row, cells in enumerate(doc["puzzle"]):
        for col, cell in enumerate(cells):
            if (row, col) in filled.blocks:
                assert cell == {"cell": "#"}
            else:
                assert cell["cell"] == str(numbers.get((row, col), 0))


def test_ipuz_clues_cover_every_entry(filled, tmp_path):
    path = tmp_path / "p.ipuz"
    export.write_ipuz(filled, str(path))
    doc = json.load(open(path, encoding="utf-8"))
    _numbers, across, down = filled.numbering()

    for key, listing in (("Across", across), ("Down", down)):
        assert len(doc["clues"][key]) == len(listing)
        for entry, (number, slot) in zip(doc["clues"][key], listing):
            assert entry["number"] == str(number)
            assert entry["answer"] == filled.pattern(slot).upper()
            # No clue written, but the enumeration must still be there.
            assert entry["clue"] == f"({slot.length})"


# -- Exolve ----------------------------------------------------------------


def _exolve_grid(page):
    body = page.split("exolve-grid:")[1].split("exolve-across:")[0]
    return [line.split() for line in body.strip().splitlines()]


def test_exolve_round_trips_the_grid(filled):
    page = export.to_exolve(filled, title="T", setter="S")
    rows = _exolve_grid(page)
    assert len(rows) == filled.size

    rebuilt = Grid(size=filled.size)
    for row, cells in enumerate(rows):
        assert len(cells) == filled.size
        for col, cell in enumerate(cells):
            # Exolve marks a block with ".", where this project's own render
            # uses "#" for a block and "." for an empty cell.  The characters
            # collide, so the inversion is asserted rather than assumed.
            if cell == ".":
                rebuilt.blocks.add((row, col))
            else:
                rebuilt.letters[(row, col)] = cell.lower()
    assert rebuilt.render() == filled.render()


def test_exolve_lists_every_entry_with_its_answer(filled):
    page = export.to_exolve(filled)
    _numbers, across, down = filled.numbering()
    across_block = page.split("exolve-across:")[1].split("exolve-down:")[0]
    down_block = page.split("exolve-down:")[1].split("exolve-end")[0]

    for block, listing in ((across_block, across), (down_block, down)):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        assert len(lines) == len(listing)
        for line, (number, slot) in zip(lines, listing):
            match = re.match(r"^(\d+) \((\d+)\) \[([A-Z]+)\]$", line)  # single-word fill
            assert match, line
            assert int(match.group(1)) == number
            assert int(match.group(2)) == slot.length
            assert match.group(3) == filled.pattern(slot).upper()


def test_exolve_page_is_self_contained(filled):
    page = export.to_exolve(filled, title="Birds", setter="Arct Pr(a)e")
    assert page.startswith("<!DOCTYPE html>")
    assert "createExolve(`" in page
    assert "exolve-begin" in page and "exolve-end" in page
    assert "exolve-title: Birds" in page
    assert "exolve-setter: Arct Pr(a)e" in page
    # exolve-m.js is the only thing it needs, and it comes from the CDN.
    assert "viresh-ratnakar.github.io/exolve-m.js" in page


def test_target_spellings_reach_the_enumeration(filled):
    """A target the setter typed as two words must be enumerated as two.

    The fold to a bare fill string destroys the spacing, so the surface has to
    be carried separately or every themed multi-word answer is given away as
    a single long word.
    """
    slot = next(s for s in filled.slots(3) if s.length == 9)
    answer = filled.pattern(slot)

    plain = export.to_exolve(filled)
    assert f"(9) [{answer.upper()}]" in plain

    # Both formats write the answer with its separators restored, as Exet's
    # own files do: MAPLE LEAF, not MAPLELEAF.
    spelling = answer[:5] + " " + answer[5:]
    spaced = export.to_exolve(filled, surfaces={answer: spelling})
    assert f"(5,4) [{spelling.upper()}]" in spaced
    assert f"(9) [{answer.upper()}]" not in spaced

    doc = export.to_ipuz(filled, surfaces={answer: spelling})
    written = [c["answer"] for c in doc["clues"]["Across"] + doc["clues"]["Down"]]
    assert spelling.upper() in written
    assert answer.upper() not in written
