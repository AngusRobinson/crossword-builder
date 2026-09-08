"""Crosswords whose letters survive a half-turn."""

import pytest

from crossword.grid import Grid
from crossword.index import Index
from crossword.words import load
from squares.rotational import (is_rotational, pair_slots, reversible, solve)

WIKTIONARY = "wiktionary.txt"


def test_entries_pair_off_under_the_turn():
    """Every entry has a partner, and lengths match across the pair."""
    grid = Grid(size=5)
    pairs, singles, orphans = pair_slots(grid, min_length=5)
    assert not orphans
    assert len(pairs) * 2 + len(singles) == len(grid.slots(5))
    for one, other in pairs:
        assert one.length == other.length
        assert one.direction == other.direction


def test_the_middle_entry_of_an_odd_grid_is_its_own_partner():
    """It maps onto itself, so it has to be a palindrome."""
    _, singles, _ = pair_slots(Grid(size=5), min_length=5)
    assert singles, "a 5x5 has a middle row and a middle column"


def test_an_even_grid_has_no_self_paired_entry():
    _, singles, _ = pair_slots(Grid(size=4), min_length=4)
    assert not singles


def test_reversible_keeps_only_words_whose_reverse_is_one():
    entries = load(WIKTIONARY, strict=False, min_length=4, max_length=4)
    kept = reversible(entries)
    text = {entry.text for entry in entries}
    assert kept
    assert all(entry.text[::-1] in text for entry in kept)
    assert len(kept) < len(entries)


@pytest.mark.parametrize("size", [3, 4, 5])
def test_a_small_grid_fills_and_reads_the_same_upside_down(size):
    entries = load(WIKTIONARY, strict=False, min_length=size, max_length=size)
    index = Index(reversible(entries))
    # Several seeds, as `palindrome.py --tries` does. One seed makes the test
    # a statement about that seed: a change to the dictionary that moved a
    # single word failed this at size 5 while 5x5 squares were still plentiful.
    for seed in range(8):
        grid = Grid(size=size)
        placed, _ = solve(grid, index, seed=seed, node_budget=200_000,
                          min_length=size)
        if placed:
            break
    assert placed, f"no {size}x{size} found in eight seeds"
    assert is_rotational(grid)
    words = {entry.text for entry in entries}
    for row in range(size):
        across = "".join(grid.letters[(row, c)] for c in range(size))
        down = "".join(grid.letters[(r, row)] for r in range(size))
        assert across in words and down in words


def test_a_palindrome_may_not_fill_both_halves_of_a_pair():
    """It would put the same answer in the grid twice."""
    entries = load(WIKTIONARY, strict=False, min_length=4, max_length=4)
    index = Index(reversible(entries))
    grid = Grid(size=4)
    placed, _ = solve(grid, index, seed=0, node_budget=200_000, min_length=4)
    assert placed
    rows = ["".join(grid.letters[(r, c)] for c in range(4)) for r in range(4)]
    columns = ["".join(grid.letters[(r, c)] for r in range(4)) for c in range(4)]
    assert len(set(rows + columns)) == 8, "an entry appears twice"
