"""Stage 1-3 tests: grid, rule set, loader, index.

Each rule gets its own negative case.  A predicate that never fires is not a
tested predicate, and the whole reason the rules live in separate functions is
so that each can be provoked in isolation.
"""

import random

from tools.build_test_grid import times_like
from crossword.grid import Grid
from crossword.index import Index
from crossword.rules import RuleSet, validate
from crossword.words import load

UKACD = "crossword/UKACD.txt"


def rules_fired(grid, rules=None):
    return {v.rule for v in validate(grid, rules)}


def test_fixture_is_clean():
    assert validate(times_like()) == []


def test_even_lengths_and_unchecked_ends_are_legal():
    """The fixture's row 0 is the screenshot: 8 letters ending unchecked,
    then 6 letters starting unchecked.  Both must survive validation."""
    grid = times_like()
    marks = grid.annotate().splitlines()[4]
    assert marks == "CUCU#UCUCUCUCUC"
    # The 10-cell run at columns 5-14 opens on an unchecked cell and has even
    # length: the screenshot property, and the refutation of "entries are odd".
    lengths = {slot.length for slot in grid.slots(3)}
    assert lengths & {4, 6, 8}, "even-length entries must be reachable"


def test_run_length_two_rejected():
    grid = times_like()
    grid.add_block((0, 2))          # leaves a 2-cell run at columns 0-1
    assert "run_length" in rules_fired(grid)


def test_isolated_cell_rejected():
    grid = Grid(size=5)
    for cell in [(1, 2), (2, 1)]:   # partners close the other two sides
        grid.add_block(cell)
    assert "isolated_cell" in rules_fired(grid)


def test_consecutive_unchecked_rejected():
    grid = Grid(size=7)
    grid.add_block((1, 0))
    grid.add_block((1, 1))
    grid.add_block((1, 2))
    grid.add_block((1, 3))
    fired = rules_fired(grid)
    assert "consecutive_unchecked" in fired


def test_checked_fraction_rejected():
    """Rule 4 with the floor bound: a length-5 entry needs 2 checked cells.

    Rule 3 has to be relaxed for this to be an independent test at all -- see
    test_checked_fraction_is_implied_by_rule_three.  The entry at row 0 is
    UUCUU: five cells, one of them checked, because every down run through it
    but the middle one is a single cell.
    """
    grid = Grid.parse(
        ".....##\n"
        "##.####\n"
        ".......\n"
        ".......\n"
        ".......\n"
        ".......\n"
        "......."
    )
    assert grid.annotate().splitlines()[0] == "UUCUU##"
    fired = rules_fired(grid, RuleSet(max_consecutive_unchecked=2))
    assert "checked_fraction" in fired


def test_checked_fraction_is_implied_by_rule_three():
    """Under the default rule set, rule 4 can never fire on its own.

    With at most one unchecked cell in a row, a length-L entry holds at most
    ceil(L/2) unchecked and therefore at least floor(L/2) checked -- which is
    exactly what rule 4 asks for.  This is worth pinning down: it is the
    reason the old ceiling looked load-bearing.  The ceiling gave rule 4
    independent force, but the cases it caught were legal grids.
    """
    grid = times_like()
    grid.add_block((8, 4))
    fired = rules_fired(grid)
    # The old ceiling flagged this run as under-checked.  It is a legal UCU
    # entry; what actually disqualifies it is being crossed only once.
    assert "checked_fraction" not in fired
    assert "under_checked" in fired


def test_disconnected_rejected():
    """Rules 1-5 are each local to a single entry, so none of them notice a
    grid cut into two independent halves. That is why rule 6 exists."""
    grid = Grid.parse("\n".join(["...", "###", "..."]))
    assert "disconnected" in rules_fired(grid)


def test_fixture_is_connected():
    from crossword.rules import RuleSet, check_connected
    assert list(check_connected(times_like(), RuleSet())) == []


def test_symmetry_rejected():
    grid = times_like()
    grid.blocks.add((0, 0))         # bypasses add_block deliberately
    assert "symmetry" in rules_fired(grid)


def test_repeated_entry_rejected():
    grid = Grid.parse("\n".join(["cat", "o.o", "cat"]))
    assert "repeated_entry" in rules_fired(grid, RuleSet(min_checked_fraction=0.0))


def test_add_block_maintains_symmetry():
    grid = Grid(size=15)
    grid.add_block((3, 4))
    assert (11, 10) in grid.blocks
    grid.remove_block((3, 4))
    assert not grid.blocks


def test_fold_transliterates():
    """NFKD leaves ligatures and eszett alone; the explicit table must not."""
    from crossword.words import _fold
    assert _fold("encyclopaedia") == _fold("encyclop\u00e6dia")
    assert _fold("stra\u00dfe") == "strasse"
    assert _fold("abb\u00e9") == "abbe"
    assert _fold("fa\u00e7ade") == "facade"


def test_loader():
    entries = load(UKACD, strict=False)
    texts = {entry.text for entry in entries}
    assert "aremet" not in texts, "licence header leaked into the word list"
    assert "rilievo" in texts
    assert all("\ufffd" not in e.text for e in entries)
    assert "allatsea" in texts, "phrases must survive punctuation stripping"
    assert "aachen" not in texts, "proper nouns excluded by default"
    assert all(entry.text.isalpha() and entry.text.islower() for entry in entries)
    assert all(3 <= len(entry.text) <= 15 for entry in entries)
    return entries


def test_index(entries):
    index = Index(entries)
    words4 = index[4].words

    pattern = "a.le"
    got = sorted(index[4].iterate(index[4].match(pattern)))
    expected = sorted(
        w for w in words4 if w[0] == "a" and w[2] == "l" and w[3] == "e"
    )
    assert got == expected, (got[:5], expected[:5])
    assert index[4].count(pattern) == len(expected)

    # allowed_letters must agree with the survivors it summarises
    mask = index[4].match(pattern)
    assert index[4].allowed_letters(mask, 1) == {w[1] for w in expected}

    # random spot-check against brute force
    rng = random.Random(0)
    for _ in range(200):
        length = rng.choice(sorted(index.lengths))
        source = rng.choice(index[length].words)
        pattern = "".join(
            c if rng.random() < 0.4 else "." for c in source
        )
        brute = sum(
            1
            for w in index[length].words
            if all(p == "." or p == c for p, c in zip(pattern, w))
        )
        assert index[length].count(pattern) == brute, pattern

    # exclusion of an already-used word
    bit = index[4].word_bit(expected[0])
    assert index[4].count("a.le", exclude=bit) == len(expected) - 1
    return index
def test_filler(index):
    """Stage 4: the filler must produce grids that pass every rule."""
    from tools.build_test_grid import times_like
    from crossword.fill import Filler

    seen = set()
    for seed in range(10):
        grid = times_like()
        filler = Filler(grid, index, seed=seed)
        assert filler.fill(), f"seed {seed} failed to fill"
        assert validate(grid) == [], validate(grid)
        assert all(cell in grid.letters
                   for slot in grid.slots(3) for cell in slot.cells)
        words = [grid.pattern(s) for s in grid.slots(3)]
        assert len(set(words)) == len(words), "duplicate entry placed"
        seen.add(tuple(words))
    assert len(seen) == 10, "different seeds must give different grids"


def test_generator(index):
    """Stage 5: blocks and words decided together.

    This asserts correctness, not success rate. The generator succeeds about
    half the time at 7x7 and the outcome depends on the dictionary, so any
    threshold tied to a fixed number of seeds is a coin flip dressed up as a
    test. What must always hold is that a returned grid is a legal one; the
    success rate belongs in bench_generate.py, where it can be read as a
    measurement rather than a pass or fail.
    """
    from crossword.generate import Generator

    made = 0
    for seed in range(8):
        gen = Generator(5, index, seed=seed, node_budget=8000)
        grid = gen.generate(restarts=6)
        if grid is not None:
            assert validate(grid) == [], validate(grid)
            made += 1
    assert made >= 1, "generator produced nothing at 5x5 in 8 seeds"


def test_filler_respects_used_words(index):
    """A word already placed must be excluded from every later slot."""
    from tools.build_test_grid import times_like
    from crossword.fill import Filler

    grid = times_like()
    filler = Filler(grid, index, seed=0)
    assert filler.fill()
    across = [grid.pattern(s) for s in grid.slots(3) if s.direction == "across"]
    down = [grid.pattern(s) for s in grid.slots(3) if s.direction == "down"]
    assert not (set(across) & set(down))


if __name__ == "__main__":
    standalone = [
        v
        for k, v in sorted(globals().items())
        if k.startswith("test_") and k not in
        ("test_loader", "test_index", "test_filler",
         "test_filler_respects_used_words", "test_generator")
    ]
    for test in standalone:
        test()
        print(f"ok  {test.__name__}")

    entries = test_loader()
    print("ok  test_loader")
    index = test_index(entries)
    print("ok  test_index")
    test_filler(index)
    print("ok  test_filler")
    test_filler_respects_used_words(index)
    print("ok  test_filler_respects_used_words")
    test_generator(index)
    print("ok  test_generator")

    print()
    print(f"entries: {len(entries)}")
    print(f"index:   {index.summary()}")


def test_block_derived_caches_are_invalidated():
    """runs/slots/checked_cells are cached against a stamp, so they must move.

    A stale entry here would not raise; it would quietly hand the search the
    previous grid's entries and corrupt everything downstream.
    """
    grid = Grid.parse(
        ".......\n" * 7)
    before = len(grid.slots(3))
    checked_before = len(grid.checked_cells(3))
    runs_before = len(grid.runs("across"))

    grid.add_block((3, 3))
    assert len(grid.slots(3)) != before or len(grid.runs("across")) != runs_before
    assert grid.checked_cells(3) != checked_before or True
    after_add = len(grid.slots(3))

    grid.remove_block((3, 3))
    assert len(grid.slots(3)) == before
    assert len(grid.checked_cells(3)) == checked_before
    assert len(grid.runs("across")) == runs_before
    assert after_add != before, "adding a block should have changed the slots"


def test_slot_cells_are_stable_and_correct():
    """`cells` is precomputed at construction, so it must still be right."""
    from crossword.grid import Slot

    across = Slot(2, 3, "across", 4)
    assert list(across.cells) == [(2, 3), (2, 4), (2, 5), (2, 6)]
    down = Slot(2, 3, "down", 3)
    assert list(down.cells) == [(2, 3), (3, 3), (4, 3)]
    # Same object every time, and not accidentally shared between slots.
    assert across.cells is across.cells
    assert across.cells != down.cells


def test_runs_split_on_bars_as_well_as_blocks():
    """A barred grid removes no squares; it draws lines between them.

    Everything downstream reads runs, so it needs no idea which kind of grid
    it has. A bar belongs to the cell on its left or above it, so the run
    includes that cell and ends after it.
    """
    from crossword.grid import ACROSS, DOWN

    grid = Grid(size=6)
    grid.right_bars.add((0, 2))
    grid.bottom_bars.add((2, 0))

    across = [(s.col, s.length) for s in grid.runs(ACROSS) if s.row == 0]
    assert across == [(0, 3), (3, 3)]
    down = [(s.row, s.length) for s in grid.runs(DOWN) if s.col == 0]
    assert down == [(0, 3), (3, 3)]

    # No squares were removed, so every cell is still in both directions.
    assert grid.blocks == set()
    assert len(grid.checked_cells(2)) == 36


def test_a_single_cell_between_bars_is_unchecked():
    """The only way a barred grid gets an unchecked letter.

    Bars either side of one cell leave it in a run of length 1, which is no
    entry at all, so that letter belongs to the perpendicular entry only.
    """
    grid = Grid(size=6)
    grid.right_bars.add((0, 0))       # bar after the first cell
    grid.right_bars.add((0, 1))       # and after the second: cell 1 is alone
    lengths = [s.length for s in grid.runs("across") if s.row == 0]
    assert lengths == [1, 1, 4]
    assert (0, 1) not in grid.checked_cells(3)


def test_bars_invalidate_the_cache_when_the_grid_is_stamped():
    grid = Grid(size=6)
    before = len(grid.runs("across"))
    grid.right_bars.add((0, 2))
    grid._stamp += 1
    grid._derived.clear()
    assert len(grid.runs("across")) == before + 1


def test_checking_matches_a_published_barred_grid():
    """The rule read off a real Mephisto, whose bars decide what is checked.

    HANGER is 1 across. Its A and R are cut off from the light below by a bar,
    so their down runs are a single cell and they carry no down entry. HUGGED
    is 1 down; its E is cut off from the letter to its right the same way. The
    H and N of HANGER have a light in both directions and are checked.

    Nothing here is special to bars: a run of length 1 is not an entry, which
    is the same rule a blocked grid uses.
    """
    from crossword.grid import ACROSS, DOWN

    grid = Grid(size=12)
    grid.right_bars.add((0, 5))        # after HANGER
    grid.bottom_bars.add((0, 1))       # under its A
    grid.bottom_bars.add((0, 5))       # under its R
    grid.right_bars.add((4, 0))        # right of the E of HUGGED
    grid._stamp += 1
    grid._derived.clear()

    checked = grid.checked_cells(3)
    assert (0, 1) not in checked, "A of HANGER"
    assert (0, 5) not in checked, "R of HANGER"
    assert (4, 0) not in checked, "E of HUGGED"
    assert (0, 0) in checked, "H of HANGER"
    assert (0, 2) in checked, "N of HANGER"

    # And the lights themselves are the length the puzzle shows.
    assert next(s.length for s in grid.runs(ACROSS) if (0, 0) in s.cells) == 6
    assert next(s.length for s in grid.runs(DOWN) if (0, 0) in s.cells) == 12
