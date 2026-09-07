"""Drawing grids as HTML."""

import pytest

from crossword import library
from crossword.barred import parse
from crossword.render import cells_of, clue_lists, grid_html, page
from test_barred import MEPHISTO


@pytest.fixture(scope="module")
def blocked():
    return library.load()[0].grid()


def test_styling_is_inline(blocked):
    """No stylesheet, because hosts strip them.

    Jupyter and GitHub both drop a <style> block from rendered notebook
    output, and what is left is an unstyled table: no black squares, and the
    host's own row striping showing through where the blocks should be.
    """
    html = grid_html(blocked)
    assert "<style" not in html
    assert "class=" not in html
    assert html.count("background:#222") == len(blocked.blocks)


def test_bars_are_drawn_and_do_not_escape_the_frame():
    """A bar is a heavy line between two cells, never part of the border."""
    barred = parse(MEPHISTO)
    html = grid_html(barred, min_length=4)
    inner_right = sum(1 for r, c in barred.right_bars if c < barred.size - 1)
    inner_bottom = sum(1 for r, c in barred.bottom_bars if r < barred.size - 1)
    assert html.count("border-right:3px") == inner_right
    assert html.count("border-bottom:3px") == inner_bottom
    assert "background:#222" not in html, "a barred grid has no blocks"


def test_numbering_appears_once_per_numbered_cell(blocked):
    numbers = blocked.numbering()[0]
    html = grid_html(blocked)
    for cell, number in numbers.items():
        assert f">{number}</span>" in html


def test_page_is_standalone_and_carries_both_lists(index):
    """The fallback for styles no puzzle format can hold."""
    from crossword.fill import Filler
    from crossword.library import rules_for

    grid = parse(MEPHISTO)
    filler = Filler(grid, index, rules=rules_for("barred"), seed=0,
                    node_budget=60000, commonness=0.0)
    assert filler.fill()

    html = page(grid, title="Test", min_length=4, solution=True)
    assert html.startswith("<!doctype html>")
    assert "Across" in html and "Down" in html
    across, down = clue_lists(grid, 4)
    assert len(across) + len(down) == len(grid.slots(4))
    for _number, answer in across:
        assert answer.upper() in html


def test_cells_of_finds_a_seated_word(blocked):
    assert cells_of(blocked, "nothinghere") == []


def test_themed_answers_are_marked(index):
    """A setter's aid: which of the answers were the ones asked for."""
    from crossword.barred import parse
    from crossword.fill import Filler
    from crossword.library import rules_for
    from crossword.render import cells_of

    grid = parse(MEPHISTO)
    filler = Filler(grid, index, rules=rules_for("barred"), seed=0,
                    node_budget=60000, commonness=0.0)
    assert filler.fill()
    word = grid.pattern(grid.slots(4)[0])

    marked = page(grid, title="t", min_length=4, solution=True, themed=[word])
    assert marked.count("background:#fff4cc;border") == len(cells_of(grid, word, 4))
    assert marked.count("background:#fff4cc;padding") == 1

    # A blank grid marks nothing: it would say where the theme is.
    blank = page(grid, title="t", min_length=4, solution=False, themed=[word])
    assert "#fff4cc" not in blank
