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
    ("1,1,sideways,ABC", "across or down"),
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
