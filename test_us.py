"""American grids: every letter checked."""

import pytest

from crossword import coverage, library
from crossword.fill import Filler
from crossword.grid import Grid
from crossword.rules import validate


@pytest.fixture(scope="module")
def us():
    return library.load(style="us")


def test_the_two_styles_differ_in_the_way_that_matters(us):
    """British grids leave about half the letters unchecked; American ones
    check every one. Everything else follows from that."""
    british = library.load(style="british")
    assert library.rules_for("us").max_consecutive_unchecked == 0
    assert library.rules_for("british").max_consecutive_unchecked == 1

    def unchecked(pattern):
        grid = pattern.grid()
        white = sum(1 for r in range(15) for c in range(15)
                    if (r, c) not in grid.blocks)
        return white - len(grid.checked_cells(3))

    assert unchecked(us[0]) == 0
    assert unchecked(british[0]) > 40


def test_the_us_library_loads_and_is_legal(us):
    assert len(us) == 1200
    rules = library.rules_for("us")
    for pattern in us[:60]:
        assert validate(pattern.grid(), rules) == []
        assert pattern.size == 15


def test_us_grids_have_american_proportions(us):
    """A modern American 15x15 carries about 36 blocks and 74 entries, against
    69 and 28 for a British one."""
    blocks = sorted(len(p.blocks) for p in us)
    entries = sorted(len(p.grid().slots(3)) for p in us)
    assert 30 <= blocks[len(blocks) // 2] <= 40
    assert 66 <= entries[len(entries) // 2] <= 80

    british = library.load(style="british")
    b_entries = sorted(len(p.grid().slots(3)) for p in british)
    assert entries[len(entries) // 2] > 2 * b_entries[len(b_entries) // 2]


def test_us_patterns_are_not_reused_the_way_british_ones_are(us):
    """British setters share 130 patterns between 8,348 puzzles, so the
    library records how often each was used. American grids are effectively
    never reused, so it is a sample and `uses` is zero throughout."""
    assert all(p.uses == 0 for p in us)
    assert any(p.uses > 100 for p in library.load(style="british"))


def test_a_real_us_grid_fills(index, us):
    """The finding that made the style workable at all.

    Randomly built US grids would not fill -- 0 of 5 at 15x15 -- while real
    ones do, with the same British dictionary. The grids were the problem, not
    the word list.

    How reliably depends steeply on density, because a sparser grid means
    longer entries and every letter is checked twice. Measured over the
    library: 9/10 at 43-49 blocks, 7/10 at 34, and 2/10 at 23-27. The densest
    are used here to keep the suite quick; the sparse end is genuinely hard
    and is recorded in BASELINE.md rather than asserted.
    """
    rules = library.rules_for("us")
    dense = sorted(us, key=lambda p: -len(p.blocks))[:6]
    filled = 0
    for i, pattern in enumerate(dense):
        grid = pattern.grid()
        if Filler(grid, index, rules, node_budget=40000, seed=i).fill(restarts=3):
            filled += 1
            assert validate(grid, rules) == []
    assert filled >= 4, f"only {filled}/6 dense US grids filled"


def test_the_fill_budget_scales_with_the_grid(index, us):
    """8000 nodes was tuned on 28-entry British grids.

    An American grid has about 74 entries, all fully checked, and ran out of
    nodes before finishing -- cover() reported grids unfillable that a bare
    Filler completes in seconds.
    """
    pattern = us[0]
    assert len(pattern.grid().slots(3)) > 60
    got = coverage.cover(pattern, index, [], library.rules_for("us"),
                         attempts=1, seed=0)
    assert got.ok, "a real US grid with no targets must fill"
