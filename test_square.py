"""Ordinary word squares: the symmetric kind."""

import pytest

from crossword.index import Index
from crossword.square import find, is_square, search
from crossword.words import load


@pytest.fixture(scope="module")
def plain():
    """No phrases: a word square is nothing but entries.

    UKACD normalises punctuation away, so "it'll" arrives as ITLL. A crossword
    hides that, because such entries are rare enough to catch by eye; here a
    quarter of the answers are ones nobody chose.
    """
    return Index(load("crossword/UKACD.txt", allow_phrases=False))


def test_is_square_reads_both_ways():
    assert is_square(["heart", "ember", "abuse", "resin", "trend"])
    assert not is_square(["heart", "ember", "abuse", "resin", "trends"])
    assert not is_square(["abcd", "bcde", "cdef", "xxxx"])


@pytest.mark.parametrize("size", [3, 4, 5, 6])
def test_squares_come_out_and_are_squares(plain, size):
    rows, _tries, _nodes = find(size, plain, tries=20, node_budget=20000)
    assert rows is not None, f"no {size}x{size} square"
    assert is_square(rows)
    words = {e for e in plain.lengths[size].words}
    for row in rows:
        assert row in words
    assert len(set(rows)) == size, "rows must be distinct"


def test_seven_is_reachable(plain):
    """Which it is not without forward checking.

    Placing rows strictly top to bottom checks only the row being placed. The
    search here computes candidates for every unplaced row at each node, so a
    row that has been left with nothing kills the branch immediately, and the
    row with least freedom is taken next.
    """
    rows, _tries, _nodes = find(7, plain, tries=40, node_budget=40000)
    assert rows is not None
    assert is_square(rows)


def test_the_budget_is_honoured(plain):
    rows, nodes = search(9, plain, node_budget=500)
    assert rows is None
    assert nodes <= 501


def test_a_size_with_no_words_is_not_a_crash(plain):
    rows, nodes = search(40, plain, node_budget=100)
    assert rows is None and nodes == 0
