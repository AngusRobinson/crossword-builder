"""The rule set, checked against crosswords that were actually published.

Every other test in this project asserts that the rules do what we think they
say.  None of them could catch the rules saying the wrong thing.  That is how
`check_checked_fraction` shipped with a ceiling where it needed a floor, and
rejected roughly a third of the Guardian's output for two months while the
generator was tuned to satisfy it.

This file closes that gap.  The corpus is the oracle: a predicate that fires
on a published grid is wrong about crosswords, whatever the unit tests say.

The corpus is ~8,300 Guardian puzzles as JSON, one file per puzzle, and is
deliberately not in the repository.  These tests skip without it.
"""

import collections
import glob
import json
import os

import pytest

from crossword.grid import Grid
from crossword.rules import RuleSet, validate

CORPUS = "guardian-cc-master/crosswords"
TEMPLATES = "guardian-cc-master/grids"

# Enough to be decisive, small enough to keep the suite quick.  The full
# corpus holds only ~130 distinct block patterns, so 400 covers essentially
# all of them.
SAMPLE = 400

# The Guardian does publish the occasional grid that breaks its own
# conventions -- 28762 (Paul) and 29082 (Anto) are both genuinely asymmetric,
# with entries crossed only once.  So the target is not zero; it is a ratchet.
# Measured at 1.3% with the floor bound and 34% with the ceiling, this
# threshold distinguishes the two by a wide margin without being falsified by
# five eccentric puzzles.
MAX_REJECTED = 0.03


def _grid_from_guardian(path):
    """Recover a block pattern from a Guardian JSON.  Geometry only."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    size = data["dimensions"]["cols"]
    if data["dimensions"]["rows"] != size:
        return None
    white = set()
    for entry in data["entries"]:
        x, y = entry["position"]["x"], entry["position"]["y"]
        for i in range(entry["length"]):
            white.add((y, x + i) if entry["direction"] == "across" else (y + i, x))
    grid = Grid(size=size)
    grid.blocks = {
        (r, c) for r in range(size) for c in range(size) if (r, c) not in white
    }
    return grid


@pytest.fixture(scope="module")
def published():
    if not os.path.isdir(CORPUS):
        pytest.skip(f"corpus not present at {CORPUS}")
    paths = sorted(glob.glob(f"{CORPUS}/**/*.JSON", recursive=True))
    if not paths:
        pytest.skip("corpus directory is empty")
    # Deterministic stride rather than a seeded shuffle: the sample must not
    # move when the corpus is updated with new puzzles.
    step = max(1, len(paths) // SAMPLE)
    grids = []
    for path in paths[::step]:
        try:
            grid = _grid_from_guardian(path)
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        if grid is not None and grid.size == 15:
            grids.append((os.path.basename(path), grid))
        if len(grids) >= SAMPLE:
            break
    assert len(grids) > 100, f"only {len(grids)} usable puzzles found"
    return grids


def test_rules_accept_published_grids(published):
    """The headline assertion: our rules must accept real crosswords.

    Reported in full rather than on the first failure, because the useful
    output is which predicate is wrong and how often -- one filename tells
    you nothing about whether you have a bad rule or a bad puzzle.
    """
    counts = collections.Counter()
    examples = {}
    rejected = set()
    for name, grid in published:
        for violation in validate(grid):
            counts[violation.rule] += 1
            rejected.add(name)
            examples.setdefault(violation.rule, f"{name}: {violation.detail}")

    rate = len(rejected) / len(published)
    assert rate <= MAX_REJECTED, (
        f"rules reject {len(rejected)} of {len(published)} published "
        f"puzzles ({rate:.1%}, limit {MAX_REJECTED:.0%}):\n"
        + "\n".join(
            f"  {rule:22} {n:4} entries   e.g. {examples[rule]}"
            for rule, n in counts.most_common()
        )
    )


def test_checking_bound_is_a_floor_not_a_ceiling(published):
    """Compare the two candidate bounds head-to-head on real entries.

    Re-derived from the corpus rather than trusting the constant, so that
    reinstating the ceiling fails here with the actual distribution attached
    -- the argument, not an assertion about it.
    """
    seen = collections.Counter()
    for _name, grid in published:
        checked = grid.checked_cells(3)
        for slot in grid.slots(3):
            n = sum(1 for cell in slot.cells if cell in checked)
            seen[(slot.length, n)] += 1

    total = sum(seen.values())
    below_floor = sum(c for (L, n), c in seen.items() if n < L // 2)
    below_ceil = sum(c for (L, n), c in seen.items() if n < -(-L // 2))

    # The ceiling is refuted, not merely unnecessary: odd lengths really do
    # occur at floor(L/2) checked, in quantity.  These are the shapes -- UCUCU,
    # UCUCUCU, UCUCUCUCU -- that the ceiling threw away.
    refuting = {L: seen[(L, L // 2)] for L in (5, 7, 9) if seen[(L, L // 2)]}
    assert len(refuting) == 3, (
        "expected odd-length entries at exactly floor(L/2) checked; "
        f"found {refuting}"
    )
    assert below_ceil / total > 0.05, (
        "the ceiling should reject a substantial share of real entries; "
        f"it rejects {below_ceil}/{total}"
    )
    assert below_floor < below_ceil / 20, (
        f"floor rejects {below_floor}/{total} entries, ceiling rejects "
        f"{below_ceil}/{total} -- floor should be better by an order of "
        f"magnitude"
    )


def _differing(a, b):
    """Entries of `a` whose value differs from `b`'s."""
    return {k: v for k, v in a.items() if b.get(k) != v}


def test_known_bad_templates_are_exactly_the_ones_we_think(published):
    """The 66 shipped .grid files are transcriptions, and nine are wrong.

    Three of them (M49, M50, M64) are disconnected -- white cells cut off
    from the rest of the grid, which is not a crossword at all -- and the
    others break symmetry or checking.  They are not evidence against the
    rules; they are evidence against the files.

    This matters for the grid library: build it from the puzzle JSON, which
    is an export and validates cleanly, not from these.  The test pins the
    bad set so that a corrected or extended `grids/` directory is noticed
    rather than silently absorbed.
    """
    if not os.path.isdir(TEMPLATES):
        pytest.skip(f"templates not present at {TEMPLATES}")

    KNOWN_BAD = {
        "M09": {"symmetry"},
        "M12": {"symmetry"},
        "M26": {"consecutive_unchecked", "symmetry"},
        "M49": {"disconnected", "isolated_cell"},
        "M50": {"disconnected", "isolated_cell"},
        "M59": {"checked_fraction", "consecutive_unchecked"},
        "M61": {"symmetry"},
        "M64": {"disconnected", "isolated_cell", "symmetry"},
        "M74": {"consecutive_unchecked"},
    }

    found = {}
    total = 0
    for path in sorted(glob.glob(f"{TEMPLATES}/*.grid")):
        rows = [line.strip().split(",") for line in open(path) if line.strip()]
        if len(rows) != 15 or any(len(r) != 15 for r in rows):
            continue
        grid = Grid(size=15)
        grid.blocks = {
            (r, c) for r, row in enumerate(rows) for c, v in enumerate(row) if v == "0"
        }
        total += 1
        fired = {v.rule for v in validate(grid)}
        if fired:
            found[os.path.basename(path)[:-5]] = fired

    assert total > 40, f"only {total} usable templates"
    assert found == KNOWN_BAD, (
        "the set of unusable templates has changed:\n"
        f"  newly bad: {_differing(found, KNOWN_BAD)}\n"
        f"  now fixed: {_differing(KNOWN_BAD, found)}"
    )
