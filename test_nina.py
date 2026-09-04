"""Letters fixed before any word is chosen."""

import pytest

import make_grid
from crossword import coverage, frequency, library, mutate
from crossword.fill import Filler
from crossword.index import Index
from crossword.rules import RuleSet, validate
from crossword.words import load

BRITISH = RuleSet(alternating=True, max_checked_fraction=0.5)


@pytest.fixture(scope="module")
def patterns():
    return library.load()


def test_parsing_counts_from_one():
    """Rows and columns are 1-based, matching how placements are reported.

    A setter reading "across at row 9, col 10" and then writing a nina should
    not have to change counting systems halfway.
    """
    nina = make_grid.read_nina(["1,1,down,HID"])
    assert nina == {(0, 0): "h", (1, 0): "i", (2, 0): "d"}
    across = make_grid.read_nina(["3,2,across,AB"])
    assert across == {(2, 1): "a", (2, 2): "b"}


def test_parsing_folds_and_merges():
    nina = make_grid.read_nina(["1,1,across,Bew are", "1,1,down,BAT"])
    assert nina[(0, 0)] == "b"          # both agree here
    assert len(nina) == 8               # 6 across + 2 more down


@pytest.mark.parametrize("spec,message", [
    ("1,1,sideways,ABC", "direction must be one of"),
    ("1,1,across", "ROW,COL,DIR,LETTERS"),
    ("14,14,across,TOOLONG", "runs off the grid"),
    ("1,1,across,", "no letters"),
    ("x,1,across,AB", "must be numbers"),
])
def test_parsing_rejects_nonsense(spec, message):
    with pytest.raises(ValueError) as caught:
        make_grid.read_nina([spec])
    assert message in str(caught.value)


def test_conflicting_ninas_are_caught():
    with pytest.raises(ValueError) as caught:
        make_grid.read_nina(["1,1,across,AB", "1,1,down,XY"])
    assert "disagree" in str(caught.value)


def test_filler_holds_loose_letters(index, patterns):
    """The mechanism the nina rides on, built for seeded theme words.

    Letters are taken from a real fill so the nina is known satisfiable, then
    a different seed must honour them and still produce a legal grid.
    """
    source = patterns[0].grid()
    assert Filler(source, index, seed=1).fill()
    nina = {c: source.letters[c] for c in list(source.letters)[:6]}

    grid = patterns[0].grid()
    grid.letters.update(nina)
    assert Filler(grid, index, seed=7).fill()
    assert all(grid.letters[c] == ch for c, ch in nina.items())
    assert validate(grid) == []


def test_cover_reapplies_the_nina_on_every_attempt(index, patterns):
    """cover() rebuilds the grid each attempt, so the nina must go back on.

    Without that the letters survive the first attempt and vanish on the
    second, which shows up as a grid that quietly ignores them.
    """
    source = patterns[0].grid()
    assert Filler(source, index, seed=1).fill()
    nina = {c: source.letters[c] for c in list(source.letters)[:5]}

    got = coverage.cover(patterns[0], index, [], attempts=3, preset=nina, seed=3)
    assert got.ok
    for cell, char in nina.items():
        assert got.grid.letters[cell] == char


def test_a_target_may_not_contradict_the_nina(index, patterns):
    """`_fits` reads the slot's live pattern, so this falls out for free."""
    pattern = patterns[0]
    grid = pattern.grid()
    slot = next(s for s in grid.slots(3) if s.length == 6)
    nina = {slot.cells[0]: "q", slot.cells[1]: "z"}

    got = coverage.cover(pattern, index, ["kestrel"], attempts=2,
                         preset=nina, seed=0)
    if got.ok:
        assert got.grid.pattern(slot).startswith("qz")


def test_breeding_never_blocks_a_nina_cell(patterns):
    keep = {(4, 4), (4, 5), (4, 6)}
    for _cell, grid in mutate.neighbours(patterns[0], BRITISH, keep_white=keep):
        assert not (keep & grid.blocks)


def test_no_target_words_is_a_valid_request(tmp_path):
    """A grid with no theme words is something to ask for, not a mistake.

    --pangram, --nina and the fill-quality settings all give a grid something
    to be without a single target in it. This used to be refused outright.
    """
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "make_grid.py", "--time-limit", "40", "--no-tailor"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    assert "filled in" in done.stdout
    assert "rules: clean" in done.stdout


def test_no_arguments_does_not_hang_on_stdin():
    """`not isatty()` is true for any non-interactive context, not just a pipe.

    A bare read() there waits for input that will never come, so a cron job or
    a background shell would hang for ever rather than build a grid.
    """
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "make_grid.py", "--time-limit", "20", "--no-tailor",
         "--patterns", "2"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr


def test_stdin_is_still_read_when_it_carries_words():
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "make_grid.py", "--time-limit", "40", "--no-tailor"],
        input="kestrel, curlew, avocet\n",
        capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    assert "placed 3 of 3 targets" in done.stdout


@pytest.mark.parametrize("spec,expected", [
    ("1,1,diagonal,ABC", [((0, 0), "a"), ((1, 1), "b"), ((2, 2), "c")]),
    ("1,15,antidiagonal,ABC", [((0, 14), "a"), ((1, 13), "b"), ((2, 12), "c")]),
    ("1,15,back,ABC", [((0, 14), "a"), ((0, 13), "b"), ((0, 12), "c")]),
    ("3,1,up,ABC", [((2, 0), "a"), ((1, 0), "b"), ((0, 0), "c")]),
])
def test_adventurous_directions(spec, expected):
    """A diagonal touches nine entries by one letter each rather than sitting
    inside one or two, which is a tighter fit on the grid and a looser one on
    the fill."""
    assert make_grid.read_nina([spec]) == dict(expected)


def test_directions_still_have_to_stay_on_the_grid():
    for spec in ("1,1,antidiagonal,ABCD", "1,1,up,AB", "14,14,diagonal,ABCD"):
        with pytest.raises(ValueError) as caught:
            make_grid.read_nina([spec])
        assert "runs off the grid" in str(caught.value)


def test_two_ninas_can_make_a_perimeter():
    """Composing is how the more elaborate shapes are reached."""
    nina = make_grid.read_nina(["1,1,across,ABCDEFGHIJKLMNO",
                                "15,15,back,PQRSTUVWXYZABCD"])
    assert len(nina) == 30
    assert nina[(0, 0)] == "a" and nina[(0, 14)] == "o"
    assert nina[(14, 14)] == "p" and nina[(14, 0)] == "d"


def test_path_nina_skips_blocked_cells():
    """What a perimeter nina actually is.

    A 15x15 perimeter is 56 cells and only 3 of the 120 published grids leave
    all of them white, so fixed cells cannot express one. Setters read the
    message off the white squares and let the blocks interrupt it.
    """
    cells, text = make_grid.read_nina_path("perimeter,NINA ROUND THE RIM")
    assert len(cells) == 56
    assert text == "ninaroundtherim"

    place = make_grid.nina_placer(cells, text)
    patterns = library.load()
    fitted = [p for p in patterns if place(p) is not None]
    assert len(fitted) > 100, "a short message should fit almost any grid"

    placed = place(fitted[0])
    assert len(placed) == len(text)
    assert not (set(placed) & set(fitted[0].blocks)), "landed on a block"
    # In path order, skipping blocks, it spells the message.
    order = [c for c in cells if c in placed]
    assert "".join(placed[c] for c in order) == text


def test_path_nina_rejects_a_grid_with_too_few_white_cells():
    cells, text = make_grid.read_nina_path("toprow,ABCDEFGHIJKLMNO")
    place = make_grid.nina_placer(cells, text)
    patterns = library.load()
    # 15 letters needs a completely open top row, which is rare.
    fitted = [p for p in patterns if place(p) is not None]
    assert 0 < len(fitted) < 20
    for pattern in patterns:
        if place(pattern) is None:
            assert any((0, c) in pattern.blocks for c in range(15))


@pytest.mark.parametrize("spec,message", [
    ("spiral,ABC", "path must be one of"),
    ("perimeter,", "no letters"),
    ("toprow,ABCDEFGHIJKLMNOP", "15 cells, message has 16"),
])
def test_path_specs_are_checked(spec, message):
    with pytest.raises(ValueError) as caught:
        make_grid.read_nina_path(spec)
    assert message in str(caught.value)


def test_cover_accepts_a_placer_and_rejects_unusable_grids(index):
    """cover() resolves a path nina per grid, because which cell holds which
    letter depends on where that grid's blocks fall."""
    cells, text = make_grid.read_nina_path("toprow,ABCDEFGHIJKLMNO")
    place = make_grid.nina_placer(cells, text)
    patterns = library.load()
    unusable = next(p for p in patterns if place(p) is None)
    got = coverage.cover(unusable, index, [], attempts=1, preset=place, seed=0)
    assert not got.ok, "a grid that cannot carry the message must not succeed"
