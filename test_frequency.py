"""The answer-frequency table and its effect on the fill.

Runs without the corpus: crossword/frequency.txt is committed.
"""

import pytest

from crossword import frequency, library
from crossword.fill import Filler
from crossword.index import Index
from crossword.rules import validate
from crossword.words import load

UKACD = "crossword/UKACD.txt"


@pytest.fixture(scope="module")
def counts():
    return frequency.load()


@pytest.fixture(scope="module")
def entries():
    return load(UKACD, strict=False)


def test_table_loads(counts):
    assert len(counts) == 54660
    assert all(n >= 1 for n in counts.values())
    # The corpus is dominated by short vowel-rich words; this is a domain
    # frequency, not a general English one, and the test says so out loud.
    assert counts["isle"] > counts["hesitate"]


def test_offenders_are_unpublished(counts):
    """The words that made the fill look amateurish must score zero.

    These all appeared in grids this project actually produced.
    """
    for word in ("librairie", "goldless", "ramuli", "yeps", "koniscope",
                 "histie", "corndodger", "diptychs"):
        assert counts.get(word, 0) == 0, word
    # ...and ordinary words must not.
    for word in ("agenda", "cinnabar", "bluebird", "smog", "neaten"):
        assert counts.get(word, 0) > 0, word


def test_filtering_thins_the_dictionary_as_documented(entries, counts):
    assert len(frequency.filter_entries(entries, counts, 0)) == len(entries)
    kept = frequency.filter_entries(entries, counts, 1)
    assert len(kept) == 54660
    # The docstring's warning about high thresholds must stay true, since it
    # is the reason min_uses is meant to be left low.
    harsh = frequency.filter_entries(entries, counts, 5)
    long_words = [e for e in harsh if len(e.text) == 14]
    assert len(long_words) < 20, "min_uses=5 should be documented as too thin"


def test_index_without_counts_has_no_preference(entries):
    index = Index(entries[:500])
    assert index[len(entries[0].text)].uses is None


def test_commonness_improves_the_fill(entries, counts):
    """The measurable point of the whole exercise.

    Same grid, same seed, same dictionary -- only the weighting changes.
    """
    kept = frequency.filter_entries(entries, counts, 1)
    index = Index(kept, counts)
    pattern = library.load()[0]

    def unpublished_fraction(commonness):
        grid = pattern.grid()
        filler = Filler(grid, index, commonness=commonness, seed=7)
        assert filler.fill(), f"fill failed at commonness={commonness}"
        assert validate(grid) == []
        words = [grid.pattern(s) for s in grid.slots(3)]
        return sum(1 for w in words if not counts.get(w)) / len(words)

    # min_uses=1 already guarantees every word has been published at least
    # once, so the weighting is measured by median use instead.
    def median_uses(commonness):
        grid = pattern.grid()
        filler = Filler(grid, index, commonness=commonness, seed=7)
        assert filler.fill()
        words = sorted(counts.get(grid.pattern(s), 0) for s in grid.slots(3))
        return words[len(words) // 2]

    assert unpublished_fraction(0.0) == 0.0      # the floor does that much
    assert median_uses(2.0) > median_uses(0.0), "weighting must raise the median"


def test_commonness_is_a_preference_not_a_filter(entries, counts):
    """An unusual word must stay reachable when the crossings demand it.

    A hard filter here would turn awkward corners into failed fills, which is
    why the cut lives in the index and the weighting does not.  Below the
    branch cap the ordering must be a permutation: every candidate still
    reachable, however heavily it is discounted.
    """
    kept = frequency.filter_entries(entries, counts, 1)
    index = Index(kept, counts)
    grid = library.load()[0].grid()
    filler = Filler(grid, index, commonness=5.0, seed=0)

    ids = sorted(range(len(index[7].words)), key=lambda i: index[7].uses[i])[:50]
    rarest = ids[0]
    assert counts.get(index[7].words[rarest], 0) == 1, "expected a once-used word"

    ordered = filler._order(index[7], list(ids))
    assert set(ordered) == set(ids), "ordering dropped candidates"
    assert ordered != list(ids), "ordering had no effect at all"

    # Above the cap it must truncate, or the branching factor is unbounded.
    everything = list(range(len(index[7].words)))
    assert len(filler._order(index[7], everything)) == filler.branch_cap
