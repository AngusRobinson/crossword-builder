"""Requiring every letter of the alphabet."""

import collections
import string
import sys

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


def test_impossible_multiples_are_refused_not_attempted():
    """26 x N letters have to physically fit in the white cells.

    A 15x15 library grid holds 137 to 168 of them. 6x needs 156 and fits only
    the roomiest; 7x needs 182 and fits none, so it is refused with the
    arithmetic rather than ground at.
    """
    import subprocess

    roomiest = max(225 - len(p.blocks) for p in library.load())
    assert 26 * 7 > roomiest >= 26 * 6

    done = subprocess.run(
        [sys.executable, "make_grid.py", "--pangram", "7", "kestrel"],
        capture_output=True, text=True, timeout=300)
    assert done.returncode != 0
    assert "needs 182 cells" in done.stderr, done.stderr

    # And a possible one must not be refused on these grounds.
    done = subprocess.run(
        [sys.executable, "make_grid.py", "--pangram", "5", "--help"],
        capture_output=True, text=True, timeout=300)
    assert done.returncode == 0


def test_difficulty_rises_steeply_with_the_multiple(scored):
    """Why there is no cap, and why high multiples still will not work.

    Per single biased search the mean shortfall roughly doubles per step: 1.0
    letters short at N=1, 1.6 at 2, 3.6 at 3, 5.5 at 4. The obstruction is
    English, not the search -- j, q, x and z are the missing ones every time,
    and no amount of restarting conjures words that contain them.
    """
    pattern = library.load()[0]

    def shortfall(n):
        grid = pattern.grid()
        filler = Filler(grid, scored, pangram=n, node_budget=30000, seed=5)
        if not filler._search(list(filler.slots)):
            pytest.skip("no complete fill at this seed")
        return len(short_of(grid, n))

    assert shortfall(1) <= shortfall(4), "higher multiples must be harder"


def test_scarce_letters_pull_harder(index):
    """A missing Q must outrank a missing K.

    Under equal weights every missing letter pulls the same, and the easy ones
    get placed first while the grid still has room -- which is exactly the
    freedom the hard ones needed.
    """
    from crossword.fill import _letter_rarity

    rarity = _letter_rarity(index)
    weight = dict(zip("abcdefghijklmnopqrstuvwxyz", rarity))
    assert weight["q"] > weight["k"] > weight["f"] > weight["e"]
    assert abs(sum(rarity) / 26 - 1.0) < 1e-9, "scaled to mean 1"


def test_a_triple_pangram_comes_out(index):
    """78 of about 160 letters dictated, which even scheme cannot manage."""
    from crossword import library
    from crossword.fill import Filler
    from crossword.rules import RuleSet

    pattern = library.load()[0]
    wins = 0
    for seed in range(4):
        grid = pattern.grid()
        filler = Filler(grid, index, RuleSet(), seed=seed, commonness=3.0,
                        aim=0.85, pangram=3, node_budget=60000)
        if filler.fill():
            counts = collections.Counter("".join(grid.letters.values()))
            assert all(counts[c] >= 3 for c in string.ascii_lowercase)
            wins += 1
    assert wins >= 2, f"only {wins} of 4 triple pangrams completed"
