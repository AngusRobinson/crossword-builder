"""Barred grids, pinned against a published Mephisto and a published Azed.

The project spent a while unable to fill a barred grid and blamed, in order,
the dictionary and then the search.  Both were wrong.  This file exists because
the only thing that settled it was a real grid: the same filler and the same
word list complete both of these five times out of five in a fraction of a
second.  What had been wrong was the patterns, which were built with a tenth of
the grid unchecked when a real one leaves a third.

There are two grids here rather than one because the first of them, on its
own, taught a false rule.  A Mephisto has no four-letter entry, so a minimum
of five looked like the form; the Azed has six of them, and against that rule
the cells around each were reported as belonging to no entry at all.  Both
grids are 12x12 and both are transcribed as geometry: no answers, no clues.
"""

import random

import pytest

from crossword.barred import (
    BARRED_RULES,
    compositions,
    mirror_bars,
    parse,
    pattern,
    render,
)
from crossword.fill import Filler
from crossword.library import rules_for
from crossword.rules import RuleSet, validate

# A Mephisto, 12x12.  '_' marks a bar beneath a cell and '|' one between two
# neighbours.  Grid geometry only: no answers, no clues.
MEPHISTO = """\
* _ * * * _|* _ * * * *
* _ * * * * * _|*|*|*|*
* _ * * * * *|_ * * * *
* _ * * *|* * _ * * * *
*|*|_|*|_|*|*|_ _ * * *
_ * * * _ * * _ * * *|_
*|* * _ _ * * _ * _ * *
* * * * _|*|*|*|*|*|_|*
* * * * _ * *|* * * _ *
* * * * _|* * * * * _ *
*|*|*|*|_ * _ * * * _ *
* * * * * *|* * * * * *
"""


# An Azed, 12x12, same notation.  Six of its entries are four letters long.
AZED = """\
* * * * _ * _ * _ * _ *
*|*|*|*|_ * * * * * _ *
* * * * _ *|*|* * * _ *
* * _ * _ * *|*|*|_|*|*
* * _ _|*|*|* * * _ * _
*|*|_ * * * *|* * _ * *
_ * _ * *|* * * _ _|*|*
* * _ * * *|*|_|* _ * *
*|_|*|*|*|* * _ * * * *
* _ * * *|*|* _ * * * *
* _ * _ * _ * _|*|*|*|*
* * * * * * * * * * * *
"""


@pytest.fixture(scope="module")
def mephisto():
    return parse(MEPHISTO)


@pytest.fixture(scope="module")
def azed():
    return parse(AZED)


def test_notation_round_trips(mephisto):
    assert render(mephisto) == MEPHISTO.rstrip("\n")


def test_published_grid_is_symmetric(mephisto):
    right, bottom = mirror_bars(mephisto)
    assert right == mephisto.right_bars
    assert bottom == mephisto.bottom_bars


def test_published_grid_shape(mephisto):
    """The measurements the generator is aimed at.

    The last of these is the one that matters.  A third of the grid carries no
    crossing, and every earlier attempt at a barred pattern left a tenth.  The
    minimum here is 5 rather than the rule set's 4 only because this grid has
    nothing shorter; it reads the same either way.
    """
    slots = mephisto.slots(5)
    lengths = sorted(slot.length for slot in slots)
    assert len(slots) == 36
    assert min(lengths) == 5 and max(lengths) == 11
    assert sum(lengths) / len(lengths) == pytest.approx(6.67, abs=0.01)
    assert 144 - len(mephisto.checked_cells(5)) == 48


def test_bars_alone_decide_checking(mephisto):
    """The rule read off the grid: 1 across is HANGER, 1 down HUGGED.

    The A and R of HANGER are cut from the light below by a bar, so their down
    runs are single cells and carry no entry.  The E of HUGGED is cut the same
    way from the letter to its right.  The H is crossed both ways.
    """
    checked = mephisto.checked_cells(5)
    assert (0, 0) in checked          # H, crossed both ways
    assert (0, 1) not in checked      # A, barred below
    assert (0, 5) not in checked      # R, barred below
    assert (4, 0) not in checked      # E, barred to the right


def test_published_grid_passes_the_barred_rules(mephisto):
    assert validate(mephisto, rules_for("barred")) == []


def test_published_grid_fills(mephisto, index):
    """The experiment that corrected the diagnosis."""
    filler = Filler(mephisto, index, rules=rules_for("barred"),
                    seed=0, node_budget=60000, commonness=0.0)
    assert filler.fill()
    assert len(mephisto.letters) == 144
    words = {entry.text for entry in index.entries} if hasattr(index, "entries") else None
    if words:
        for slot in mephisto.slots(5):
            assert mephisto.pattern(slot) in words


def test_symmetry_check_sees_bars(mephisto):
    """Bars are edges, and rotate onto edges.

    A barred grid has no blocks at all, so before this the symmetry rule passed
    every barred pattern however lopsided.
    """
    mephisto.right_bars.add((0, 0))
    mephisto._stamp += 1
    mephisto._derived.clear()
    violations = validate(mephisto, RuleSet(**BARRED_RULES))
    assert any(v.rule == "symmetry" for v in violations)
    mephisto.right_bars.discard((0, 0))
    mephisto._stamp += 1
    mephisto._derived.clear()


def test_azed_round_trips_and_is_symmetric(azed):
    """Symmetry is also the transcription check.

    These grids are read off a picture by hand, and almost any slip -- a bar
    misplaced, a bar missed -- breaks the half-turn.  A transcription that
    rotates onto itself is very unlikely to be wrong.
    """
    assert render(azed) == AZED.rstrip("\n")
    right, bottom = mirror_bars(azed)
    assert right == azed.right_bars and bottom == azed.bottom_bars


def test_azed_shape_and_rules(azed):
    """The grid that corrected the minimum entry length."""
    slots = azed.slots(4)
    lengths = sorted(slot.length for slot in slots)
    assert len(slots) == 36
    assert lengths.count(4) == 6, "the four-letter entries are the whole point"
    assert min(lengths) == 4 and max(lengths) == 12
    assert 144 - len(azed.checked_cells(4)) == 54
    assert validate(azed, rules_for("barred")) == []


def test_a_minimum_of_five_would_condemn_the_azed():
    """Kept as a standing argument against a corpus of one.

    With the minimum at five the Azed's four-letter entries stop being lights,
    and the rules then report the cells around them as isolated -- six of them,
    in a puzzle that was printed in a national newspaper.
    """
    from crossword.barred import BARRED_RULES

    too_strict = RuleSet(**{**BARRED_RULES, "min_entry_length": 5})
    violations = validate(parse(AZED), too_strict)
    assert any(v.rule == "isolated_cell" for v in violations)
    assert any(v.rule == "run_length" for v in violations)


def test_azed_fills(azed, index):
    filler = Filler(azed, index, rules=rules_for("barred"),
                    seed=0, node_budget=60000, commonness=0.0)
    assert filler.fill()
    assert len(azed.letters) == 144


def test_compositions_are_runs_or_single_cells():
    """Nothing between a single cell and a whole entry is representable.

    A run of two, three or four is neither an unchecked letter nor a light,
    which is what makes the line alphabet small enough to search over.
    """
    every = compositions(12, 4)
    assert all(sum(comp) == 12 for comp in every)
    assert all(part == 1 or part >= 4 for comp in every for part in comp)
    assert len(every) == 117


def test_generated_patterns_are_symmetric_and_legal():
    rules = rules_for("barred")
    rng = random.Random(3)
    made = 0
    for _ in range(120):
        grid = pattern(12, rng=rng)
        if grid is None:
            continue
        right, bottom = mirror_bars(grid)
        assert right == grid.right_bars and bottom == grid.bottom_bars
        if not validate(grid, rules):
            made += 1
    assert made > 0, "the generator produced no legal pattern in 120 draws"


def test_generator_reaches_a_published_shape():
    """`openness` has to be able to get to where the real grids are.

    It did not, once: the column search sorted its candidates by weight and
    then shuffled them uniformly, so the dial moved the rows and nothing else.
    A generator that cannot reach 48 unchecked cells cannot make a Mephisto.
    """
    rules = rules_for("barred")
    rng = random.Random(9)
    loose = 0
    for _ in range(600):
        grid = pattern(12, rng=rng)
        if grid is None:
            continue
        if 144 - len(grid.checked_cells(4)) >= 44 and not validate(grid, rules):
            loose += 1
    assert loose > 0, "no pattern came near the real grid's proportion of unches"


def test_exporters_refuse_barred_grids(mephisto):
    """A barred grid has no blocks, so a writer that only knows blocks would
    emit a full square of white cells with every entry running the whole width:
    a well-formed file describing a different puzzle."""
    from crossword import export

    for writer in (export.to_ipuz, export.to_exolve):
        with pytest.raises(NotImplementedError):
            writer(mephisto)


def test_pretty_draws_the_bars(mephisto):
    """Without this a barred grid prints as a featureless square."""
    drawn = mephisto.pretty()
    assert "|" in drawn
    assert "—" in drawn
    # One row per line of the grid, plus an underline wherever a row has any
    # bar beneath it.
    assert len(drawn.splitlines()) > mephisto.size


def test_library_round_trips_bars(tmp_path):
    """The library file format tells the two notations apart by row width."""
    from crossword import library

    rng = random.Random(4)
    made = None
    while made is None or validate(made, rules_for("barred")):
        made = pattern(12, rng=rng)
    stored = library.Pattern(
        size=12, blocks=frozenset(), uses=0, source="test", valid=True,
        right_bars=frozenset(made.right_bars),
        bottom_bars=frozenset(made.bottom_bars),
    )
    path = tmp_path / "grids.txt"
    library.save([stored], str(path))
    back = library.load(str(path))
    assert len(back) == 1 and back[0].barred
    assert back[0].grid().right_bars == made.right_bars
    assert back[0].grid().bottom_bars == made.bottom_bars


def test_shipped_library_is_all_legal_barred_grids():
    """Every pattern in the library was filled once before it was let in.

    That is not re-checked here, which would cost a minute; what is checked is
    that the file holds what it claims to -- barred, symmetric, legal, and of
    the right size -- so a bad write or a format change cannot pass unnoticed.
    """
    from crossword import library

    rules = rules_for("barred")
    patterns = library.load(style="barred")
    assert len(patterns) >= 20
    for stored in patterns:
        assert stored.barred, f"{stored.source} has no bars"
        grid = stored.grid()
        assert grid.size == 12 and not grid.blocks
        right, bottom = mirror_bars(grid)
        assert right == grid.right_bars and bottom == grid.bottom_bars
        assert validate(grid, rules) == []
        assert 144 - len(grid.checked_cells(4)) >= 44
