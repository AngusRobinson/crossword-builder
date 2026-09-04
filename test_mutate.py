"""Tailoring a grid to a word list by editing a published one."""

import pytest

from crossword import coverage, library, mutate
from crossword.rules import RuleSet, validate

BRITISH = RuleSet(alternating=True, max_checked_fraction=0.5)


@pytest.fixture(scope="module")
def patterns():
    return library.load()


def test_every_neighbour_is_legal(patterns):
    """A neighbour that breaks a rule is no use however well its lengths fit."""
    found = list(mutate.neighbours(patterns[0], BRITISH))
    assert found, "expected some legal neighbours"
    for _cell, grid in found:
        assert validate(grid, BRITISH) == []


def test_neighbours_keep_symmetry_and_are_distinct(patterns):
    """Flipping a cell flips its partner, so symmetry is never broken.

    It also means flipping a cell and flipping its partner give the *same*
    grid.  Counting both double-counts the neighbourhood, which is why they
    are deduplicated by block set.
    """
    seed = patterns[0]
    found = list(mutate.neighbours(seed, BRITISH))
    seen = set()
    for _cell, grid in found:
        for cell in grid.blocks:
            assert grid.partner(cell) in grid.blocks
        key = frozenset(grid.blocks)
        assert key not in seen, "duplicate neighbour"
        assert key != seed.blocks, "a neighbour must differ from its seed"
        seen.add(key)
    # One flip changes the block count by one pair, or by one at the centre.
    for _cell, grid in found:
        assert abs(len(grid.blocks) - len(seed.blocks)) in (1, 2)


def test_fitness_prefers_a_ceiling_over_spare_room():
    """A word with nowhere to go is not a tuning problem."""
    class Fake:
        def __init__(self, profile):
            self._p = profile
        def profile(self, min_length=3):
            return self._p

    targets = ["aaaaa", "bbbbb", "ccccccc"]
    seats_all = Fake({5: 2, 7: 1})
    roomy_but_short = Fake({5: 9, 7: 0})
    assert mutate.fitness(seats_all, targets) > mutate.fitness(roomy_but_short, targets)


def test_tailoring_reaches_profiles_the_library_cannot(patterns):
    """The point of the exercise: headroom no published grid offers.

    Nine 15-letter words is beyond any library grid -- they carry 0.7 such
    slots on average -- so the ceiling has to be raised by editing, or not
    at all.
    """
    targets = ["a" * 15, "b" * 15, "c" * 15, "d" * 13, "e" * 13]
    before = max(coverage.ceiling(p.profile(), targets) for p in patterns)
    grown = mutate.tailor(
        sorted(patterns, key=lambda p: mutate.fitness(p, targets), reverse=True)[:6],
        targets, BRITISH, beam=6, steps=3,
    )
    assert grown, "tailoring produced nothing"
    after = max(coverage.ceiling(p.profile(), targets) for p in grown)
    assert after >= before
    for pattern in grown:
        assert validate(pattern.grid(), BRITISH) == []
        assert pattern.blocks not in {p.blocks for p in patterns}, "not novel"


def test_tailor_excludes_its_seeds(patterns):
    seeds = patterns[:3]
    grown = mutate.tailor(seeds, ["a" * 7, "b" * 9], BRITISH, beam=3, steps=1)
    started = {p.blocks for p in seeds}
    assert grown
    assert all(p.blocks not in started for p in grown)


def test_candidates_keeps_the_whole_library(patterns):
    """Tailoring adds reach; it must not take any away.

    A mutant can score better on lengths and still fill worse, so the
    untouched grids stay in the running and the fill decides.
    """
    targets = ["a" * 7, "b" * 9, "c" * 5, "d" * 11]
    pool = mutate.candidates(patterns, targets, BRITISH, seeds=3, beam=3,
                             steps=2, limit=10)
    assert len(pool) > len(patterns)
    assert {p.blocks for p in patterns} <= {p.blocks for p in pool}
    # Mutants are traceable to the grid they came from.
    grown = pool[len(patterns):]
    for pattern in grown:
        assert "+" in pattern.source
        assert pattern.source.split("+")[0] in {p.source for p in patterns}
        assert pattern.uses == 0


def test_mutant_patterns_behave_like_library_ones(patterns):
    """They go through the same machinery, so they must have the same shape."""
    grown = mutate.tailor(patterns[:2], ["a" * 7], BRITISH, beam=2, steps=1)
    assert grown
    one = grown[0]
    grid = one.grid()
    grid.letters[(0, 0)] = "z"
    assert one.grid().letters == {}, "grid() must hand out a fresh copy"
    assert isinstance(one.profile(), dict)
    assert one.valid and one.size == 15
