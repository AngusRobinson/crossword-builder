"""Rows as phrases, and the constraints that are supposed to hold of them."""

import os
import subprocess
import sys

import pytest

from crossword import frequency
from crossword.index import Index
from crossword.words import load
from squares.segmented import ONE, TWO, split, strings, vocabulary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "search_palindromic_text.py")
DICTIONARY = os.path.join(ROOT, "english-names.txt")
SCORES = os.path.join(ROOT, "english-names-scores.txt")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(DICTIONARY) and os.path.exists(SCORES)),
    reason="needs english-names.txt; tools/build_names.py makes it")


@pytest.fixture(scope="module")
def words():
    scores = frequency.load_scores(SCORES)
    entries = load(DICTIONARY, min_length=3, max_length=7,
                   allow_phrases=False, allow_proper=True, strict=False)
    by_length = vocabulary(entries, scores, floor=4.0)
    by_length[1] = {"a", "i"}
    return by_length, {w for ws in by_length.values() for w in ws}


def test_two_letter_list_is_common_english_only():
    """Admitting the Scrabble list lets every row segment into something."""
    assert "ae" not in TWO and "ut" not in TWO and "gi" not in TWO
    assert {"an", "is", "of", "to"} <= TWO
    assert ONE == frozenset("aio")


def test_a_string_splits_into_its_words(words):
    by_length, _ = words
    readings = {" ".join(p) for p in split("atone", by_length, 6)}
    assert "at one" in readings or "a tone" in readings


def test_generated_strings_really_segment(words):
    by_length, vocab = words
    for text in list(strings(by_length, 4))[:200]:
        assert split(text, by_length, 1), f"{text} does not split"


def test_rows_mode_keeps_every_row_whole(words):
    """The constraint that --rows exists to impose.

    It was written as a check that a word *could* end at the boundary while
    the unfinished states were kept, so a word straddled the row anyway and
    EWERE, which is no word, was reported as a row.
    """
    _, vocab = words
    result = subprocess.run(
        [sys.executable, TOOL, "4", "4.0", "60", "--rows", "--content=1"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr

    def segments(text):
        ok = [True] + [False] * len(text)
        for end in range(1, len(text) + 1):
            for take in range(1, end + 1):
                if ok[end - take] and text[end - take:end] in vocab:
                    ok[end] = True
        return ok[len(text)]

    rows = []
    for line in result.stdout.splitlines():
        if "[" not in line or "]" not in line:
            continue
        inside = line[line.index("[") + 1:line.index("]")]
        # the summary line carries brackets too, but no slashes
        if "/" not in inside:
            continue
        rows += inside.lower().split("/")
    assert rows, "the run reported no squares"
    bad = [r for r in rows if not segments(r)]
    assert not bad, f"rows that do not segment on their own: {bad[:5]}"


def test_the_search_says_whether_it_finished():
    """A budget that stops a search must not read as an exhaustive negative."""
    result = subprocess.run(
        [sys.executable, TOOL, "4", "4.0", "60", "--rows"],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert "exhaustive" in result.stdout or "TIMED OUT" in result.stdout
