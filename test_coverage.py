"""The grid library and the coverage measure.

These run without the corpus: the library is a committed file and the
benchmark lists are committed JSON.
"""

import json
import os

import pytest

from crossword import coverage, library
from crossword.fill import Filler
from crossword.rules import validate


@pytest.fixture(scope="module")
def patterns():
    return library.load()


def test_library_loads_and_validates(patterns):
    assert len(patterns) == 120
    assert all(p.size == 15 for p in patterns)
    # Sorted most-used first, and the top pattern is the Guardian workhorse.
    assert patterns[0].uses == 458
    assert [p.uses for p in patterns] == sorted((p.uses for p in patterns), reverse=True)
    for pattern in patterns:
        assert validate(pattern.grid()) == [], pattern.source


def test_library_includes_invalid_only_when_asked(patterns):
    everything = library.load(valid_only=False)
    assert len(everything) == 130
    assert sum(1 for p in everything if not p.valid) == 10


def test_pattern_grid_is_a_fresh_copy(patterns):
    first = patterns[0].grid()
    first.letters[(0, 0)] = "z"
    first.blocks.add((0, 0))          # white in every library pattern's corner
    second = patterns[0].grid()
    assert second.letters == {}
    assert (0, 0) not in second.blocks


def test_ceiling_counts_multiset_overlap():
    profile = {3: 1, 5: 2, 7: 1}
    # Two 5s available, three wanted: only two can be seated.
    assert coverage.ceiling(profile, ["aaaaa", "bbbbb", "ccccc"]) == 2
    # A length the grid does not offer contributes nothing.
    assert coverage.ceiling(profile, ["aaaa"]) == 0
    assert coverage.ceiling(profile, ["aaa", "bbbbbbb"]) == 2
    assert coverage.ceiling({}, ["aaa"]) == 0


def test_ceiling_is_an_upper_bound(patterns, index):
    """The measure the whole benchmark is scored against must really bound it."""
    targets = ["kestrel", "curlew", "avocet", "bittern", "redwing"]
    got = coverage.best_over_library(patterns, index, targets, top=4, attempts=2, seed=0)
    assert got.n <= got.ceiling
    assert got.ok
    assert validate(got.grid) == []


def test_preset_words_outside_the_dictionary_survive(index):
    """A themed entry is usually a proper noun, which UKACD deliberately omits.

    Before this was handled, seeding one made the slot candidate-free and the
    grid was reported unfillable -- the caller's own seed word refuted itself.
    """
    pattern = library.load()[0]
    grid = pattern.grid()
    slot = next(s for s in grid.slots(3) if s.length == 7)
    # "mercury" would not do: UKACD has the metal.  "neptune" is only ever
    # capitalised, so the loader's allow_proper=False drops it -- which is
    # precisely the case a themed grid runs into.
    for cell, char in zip(slot.cells, "neptune"):
        grid.letters[cell] = char
    assert index[7].word_id("neptune") is None, "fixture assumes it is absent"

    filler = Filler(grid, index, seed=0)
    assert filler.fill(), "a preset word outside the dictionary must not kill the fill"
    assert grid.pattern(slot) == "neptune"
    assert validate(grid) == []


def test_filler_marks_preset_dictionary_words_as_used(index):
    """A preset word the dictionary does have must not be placed again."""
    pattern = library.load()[0]
    grid = pattern.grid()
    slot = next(s for s in grid.slots(3) if s.length == 6)
    word = index[6].words[0]
    for cell, char in zip(slot.cells, word):
        grid.letters[cell] = char

    filler = Filler(grid, index, seed=0)
    assert filler.used.get(6, 0) & index[6].word_bit(word)
    assert filler.fill()
    entries = [grid.pattern(s) for s in grid.slots(3)]
    assert len(set(entries)) == len(entries), "duplicate entry placed"


def test_benchmark_file_is_well_formed():
    path = os.path.join("benchmark", "lists.json")
    data = json.load(open(path, encoding="utf-8"))
    lists = data["lists"]
    assert len(lists) == 44
    assert len({item["id"] for item in lists}) == len(lists)
    for item in lists:
        assert item["words"], item["id"]
        assert all(w.isalpha() and w.islower() for w in item["words"]), item["id"]
        if item["stratum"] != "theme":
            assert len(item["words"]) == item["size"]
        # The controls are the pass mark, so their optimum must be recorded.
        if item["stratum"] == "feasible":
            assert item["known_optimum"] == item["size"]
        else:
            assert item["known_optimum"] is None


def test_seating_accepts_targets_the_dictionary_lacks(index):
    """The words you most want to seat are the ones UKACD does not have.

    The forward check after a placement must not ask whether the word just
    placed has candidates -- it never will, if it is a proper noun.  Including
    the placed slot in that check refused every such target silently, scoring
    3 of 16 on the controls instead of 12, with no error anywhere.
    """
    pattern = library.load()[0]
    targets = ["neptune", "jupiter", "macbeth", "othello"]
    assert all(index[7].word_id(w) is None for w in targets), "fixture assumes absent"

    got = coverage.cover(pattern, index, targets, attempts=3, seed=0)
    assert got.ok
    assert sorted(got.placed) == sorted(targets), got.placed
    entries = {got.grid.pattern(s) for s in got.grid.slots(3)}
    assert set(targets) <= entries
    assert validate(got.grid) == []


def test_seating_leaves_the_grid_consistent_after_an_early_exit(index):
    """A budget or bound exception unwinds past every pending erase.

    Without an explicit rewind the grid keeps letters from abandoned branches,
    and because _write only fills empty cells the winning words are then
    written around that debris -- reported as seated, but not actually spelt
    in the grid.  A tiny budget forces the unwind.
    """
    import random

    pattern = library.load()[0]
    grid = pattern.grid()
    slots = grid.slots(3)
    targets = ["neptune", "jupiter", "macbeth", "othello", "bermuda", "ipswich"]

    seated, _open = coverage._seat_targets(
        grid, index, slots, targets, random.Random(0), budget=3
    )
    assert seated, "expected at least one seating under a tiny budget"

    # Every letter in the grid belongs to a seated word, and every seated word
    # is actually spelt out where it was said to be.
    owned = set()
    for word, slot, _written in seated:
        assert grid.pattern(slot) == word, f"{word} is not in its slot"
        owned.update(slot.cells)
    assert set(grid.letters) == owned, "stale letters left by the unwind"


def test_the_hard_benchmark_tier_is_well_formed():
    """A second tier, because the first stopped discriminating.

    Most of the original 44 lists reach their ceiling at any setting, so a
    change shows up on two or three of them at most. These are dense -- 20 to
    28 targets in a 28-entry grid -- so the targets are most of the grid and
    have to agree with each other letter by letter.
    """
    import json
    import os

    path = os.path.join("benchmark", "lists-hard.json")
    data = json.load(open(path, encoding="utf-8"))
    lists = data["lists"]
    assert len(lists) == 24
    assert len({item["id"] for item in lists}) == len(lists)

    for item in lists:
        assert item["stratum"] == "dense"
        assert item["size"] in (20, 24, 28)
        assert len(item["words"]) == item["size"]
        assert item["known_optimum"] == item["size"]
        # Not capped on lengths: the difficulty is entirely in the crossings.
        assert item["library_ceiling"] == item["size"]
        assert all(w.isalpha() and w.islower() for w in item["words"])


def test_breeding_is_skipped_when_it_cannot_raise_the_bound(index):
    """Breeding exists to raise the ceiling, not to fill better.

    When some library grid already reaches the most any grid could hold, there
    is nothing left to raise, and since the two arms share a clock, breeding
    anyway costs the library search 60% of its time for nothing.
    """
    from crossword import library, mutate

    patterns = library.load()

    # A long list of every length saturates the bound: some published grid
    # already seats as many as any grid could, so there is nothing to raise.
    varied = [w.strip().lower() for w in open("lists/birds.txt")]
    varied = [w.replace(" ", "").replace("-", "") for w in varied if w]
    assert len(varied) > 200
    assert not mutate.breeding_can_help(patterns, varied)

    # Twenty words of one length do not. A grid has only so many five-letter
    # entries, and breeding can make one that has more.
    fives = sorted({w for w in varied if len(w) == 5})[:20]
    assert len(fives) == 20
    assert mutate.breeding_can_help(patterns, fives)

    # And an empty list has nothing to breed towards.
    assert not mutate.breeding_can_help(patterns, [])
