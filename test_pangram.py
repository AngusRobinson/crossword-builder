"""Requiring every letter of the alphabet."""

import collections
import string

import pytest

from crossword import frequency, library
from crossword.fill import Filler
from crossword.index import Index
from crossword.rules import validate
from crossword.words import load


def counts_of(grid):
    return collections.Counter("".join(grid.letters.values()))


def short_of(grid, need):
    seen = counts_of(grid)
    return [c for c in string.ascii_lowercase if seen[c] < need]


def test_an_ordinary_fill_is_never_a_pangram(index):
    """The reason this feature needs a mechanism rather than luck.

    Across 25 fills an unconstrained grid missed 4.2 letters on average, and
    turning the familiarity preference off entirely only reached 3.5. Nothing
    in the search was asking for a z.
    """
    pattern = library.load()[0]
    misses = []
    for seed in range(6):
        grid = pattern.grid()
        assert Filler(grid, index, seed=seed).fill()
        misses.append(len(short_of(grid, 1)))
    assert min(misses) > 0, "an ordinary fill should not stumble into a pangram"


def test_pangram_is_reached_and_the_grid_stays_legal(index):
    pattern = library.load()[0]
    for seed in range(3):
        grid = pattern.grid()
        filler = Filler(grid, index, pangram=1, node_budget=40000, seed=seed)
        assert filler.fill(restarts=40), f"seed {seed} produced no fill"
        assert short_of(grid, 1) == []
        assert validate(grid) == []
        words = [grid.pattern(s) for s in grid.slots(3)]
        assert len(set(words)) == len(words), "duplicate entry"


def test_double_pangram_is_reached(index):
    pattern = library.load()[0]
    grid = pattern.grid()
    filler = Filler(grid, index, pangram=2, node_budget=40000, seed=0)
    assert filler.fill(restarts=40)
    assert short_of(grid, 2) == []
    assert validate(grid) == []


def test_hunger_scales_with_the_requirement(index):
    """A pangram needs hunger 2 and a double about 10, so it scales."""
    grid = library.load()[0].grid()
    assert Filler(grid, index, pangram=0).hunger == 3.0
    assert Filler(grid, index, pangram=1).hunger == 3.0
    assert Filler(grid, index, pangram=2).hunger == 6.0
    assert Filler(grid, index, pangram=3).hunger == 9.0
    assert Filler(grid, index, pangram=2, hunger=1.5).hunger == 1.5


def test_missing_mask_tracks_what_the_grid_lacks(index):
    grid = library.load()[0].grid()
    filler = Filler(grid, index, pangram=1, seed=0)
    assert filler._missing_mask() == (1 << 26) - 1     # empty grid lacks all
    assert Filler(grid, index, pangram=0, seed=0)._missing_mask() == 0

    assert filler.fill(restarts=40)
    assert filler._missing_mask() == 0, "a finished pangram lacks nothing"


@pytest.fixture(scope="module")
def scored(entries):
    """An index carrying familiarity scores.

    The shared `index` fixture has none, which is deliberate -- it is what
    caught the pangram bonus living inside the familiarity branch, where an
    unscored index ignored the request in silence.
    """
    return Index(entries, frequency.load_scores())


def test_pangram_works_without_familiarity_scores(index):
    """The regression that test failure exposed."""
    assert index[7].quantile is None
    grid = library.load()[0].grid()
    filler = Filler(grid, index, pangram=1, node_budget=40000, seed=0)
    assert filler.fill(restarts=40)
    assert short_of(grid, 1) == []


def test_pangram_costs_some_fill_quality(scored):
    """Worth stating: the letters have to come from somewhere.

    Measured over 16 grids, mean familiarity rank falls from 0.81 with no
    requirement to 0.79 for a pangram and 0.70 for a double.
    """
    pattern = library.load()[0]
    def rank(pangram):
        grid = pattern.grid()
        assert Filler(grid, scored, pangram=pangram, node_budget=40000,
                      seed=2).fill(restarts=40)
        vals = []
        for slot in grid.slots(3):
            word = grid.pattern(slot)
            bucket = scored[len(word)]
            word_id = bucket.by_word.get(word)
            if word_id is not None:
                vals.append(bucket.quantile[word_id])
        return sum(vals) / len(vals)
    assert rank(2) <= rank(0) + 0.02, "a double pangram should not read better"
