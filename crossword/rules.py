"""The rule set, as independent predicates over a finished grid.

Each predicate takes a grid and yields violations.  None of them share state
and none of them call each other.  That is deliberate: the errors this project
has already hit were all cases of one rule being folded into another and the
combination hiding a wrong premise.  A fused predicate cannot be individually
disabled, and a rule that cannot be disabled cannot be tested.

Nothing here is written for speed.  This is the oracle, not the search.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .grid import ACROSS, Grid, Slot


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str


@dataclass(frozen=True)
class RuleSet:
    """Parameters of a grid style.

    British cryptic is the default.  US and barred styles will vary these
    rather than editing the predicates.
    """

    min_entry_length: int = 3
    max_consecutive_unchecked: int = 1
    min_checked_fraction: float = 0.5
    # British grids check about half of each entry and no more. Rule 4 is only
    # a floor, so without a ceiling the search drifts to fully-checked
    # American-style grids. Cap = floor(length * fraction) + slack.
    max_checked_fraction: float | None = None
    max_checked_slack: int = 1
    # Which way `min_checked_fraction` rounds, and it is genuinely a property
    # of the style rather than of the arithmetic.  British blocked grids round
    # down -- rounding up rejects a third of published Guardian puzzles, as the
    # note on check_checked_fraction records at length.  Barred grids round up:
    # neither of the two published ones has any entry more than a third
    # unchecked, and rounding down would admit a four-letter light with two
    # unches in it, which is barely an answer at all.
    checked_fraction_rounds_up: bool = False
    # Real grids alternate exactly: every entry in the sampled Guardian puzzle
    # is CUCU... or UCUC..., never two checked or two unchecked in a row. The
    # fraction rules cannot express this — floor(L/2) admits UCU at length 3,
    # ceil(L/2) rejects UCUCU at length 5, and both occur or don't occur for
    # reasons of phase rather than proportion.
    alternating: bool = False
    # An entry crossed only once is effectively unverifiable, which is why CUC
    # is common and UCU is not.
    min_checked: int = 2
    forbid_run_length_two: bool = True
    # No published style forbids a long entry -- a British 15x15 is usually
    # the better for one or two -- so this is None by default and is a
    # constraint the caller imposes, not one the tradition does. It exists
    # because a shape can be wanted for reasons outside the style: a grid
    # whose fill must survive a half-turn needs every entry to be a word whose
    # reverse is also a word, and there are no reversible ten-letter words at
    # all, so the length has to be capped before the search starts.
    max_entry_length: int | None = None
    symmetry: str = "rotational180"


def _describe(slot: Slot) -> str:
    return f"{slot.direction} at ({slot.row},{slot.col}) length {slot.length}"


def check_run_lengths(grid: Grid, rules: RuleSet):
    """Rules 1 and 2: runs are of length 1 or at least min_entry_length."""
    if not rules.forbid_run_length_two:
        return
    for direction in (ACROSS, "down"):
        for run in grid.runs(direction):
            if (rules.max_entry_length is not None
                    and run.length > rules.max_entry_length):
                yield Violation(
                    "run_length",
                    f"{_describe(run)} is longer than the "
                    f"{rules.max_entry_length} allowed")
            if 1 < run.length < rules.min_entry_length:
                yield Violation(
                    "run_length",
                    f"{_describe(run)} is shorter than {rules.min_entry_length}",
                )


def check_no_isolated_cells(grid: Grid, rules: RuleSet):
    """A cell in a length-1 run in both directions belongs to no entry at all."""
    covered = set()
    for slot in grid.slots(rules.min_entry_length):
        covered.update(slot.cells)
    for row in range(grid.size):
        for col in range(grid.size):
            cell = (row, col)
            if cell not in grid.blocks and cell not in covered:
                yield Violation("isolated_cell", f"cell {cell} is in no entry")


def check_unchecked_runs(grid: Grid, rules: RuleSet):
    """Rule 3: no run of unchecked cells longer than the permitted maximum."""
    checked = grid.checked_cells(rules.min_entry_length)
    limit = rules.max_consecutive_unchecked
    for slot in grid.slots(rules.min_entry_length):
        streak = 0
        for cell in slot.cells:
            streak = 0 if cell in checked else streak + 1
            if streak > limit:
                yield Violation(
                    "consecutive_unchecked",
                    f"{_describe(slot)} has {streak} unchecked cells in a row",
                )
                break


def check_checked_fraction(grid: Grid, rules: RuleSet):
    """Rule 4: at least half the letters of every entry are checked.

    The bound rounds *down* by default, and getting that wrong was this
    project's most expensive mistake.  It was written as a ceiling on the reading that "half
    the letters checked" must round up, and the docstring cited UCUCUCUCU as
    the pattern the ceiling existed to reject.  But UCUCUCUCU is the commonest
    nine-letter entry in British cryptics.  Measured against 400 published
    Guardian 15x15 puzzles, the ceiling rejected 136 of them — 34%.

    The corpus settles it.  Every odd length occurs with the floor count and
    no length occurs below it:

        length 5: 2 checked, 104 entries      length 9: 4 checked, 164 entries
        length 7: 3 checked, 292 entries     length 11: 5 checked,  24 entries

    With floor, all 400 puzzles pass and none of the other predicates fire.
    Three-letter entries are not left unguarded by the looser bound: floor
    admits one checked cell, and `check_min_checked` requires two.

    See test_corpus.py, which re-derives this against the corpus rather than
    trusting the number written here.

    Barred grids round the other way; `checked_fraction_rounds_up` says why.
    The two conclusions do not conflict, because they are conclusions about
    two different corpora: a Guardian 15x15 really does print UCUCUCUCU, and a
    Mephisto really does not print a four-letter light with two unches.
    """
    checked = grid.checked_cells(rules.min_entry_length)
    round_off = math.ceil if rules.checked_fraction_rounds_up else math.floor
    for slot in grid.slots(rules.min_entry_length):
        count = sum(1 for cell in slot.cells if cell in checked)
        needed = round_off(slot.length * rules.min_checked_fraction)
        if count < needed:
            yield Violation(
                "checked_fraction",
                f"{_describe(slot)} has {count} checked, needs {needed}",
            )


def check_max_checked(grid: Grid, rules: RuleSet):
    """Rule 7: an entry must not be checked much beyond half its letters."""
    if rules.max_checked_fraction is None:
        return
    checked = grid.checked_cells(rules.min_entry_length)
    for slot in grid.slots(rules.min_entry_length):
        count = sum(1 for cell in slot.cells if cell in checked)
        cap = int(slot.length * rules.max_checked_fraction) + rules.max_checked_slack
        if count > cap:
            yield Violation(
                "over_checked",
                f"{_describe(slot)} has {count} checked, cap is {cap}",
            )


def check_alternating(grid: Grid, rules: RuleSet):
    """Rule 8: checked and unchecked cells strictly alternate."""
    if not rules.alternating:
        return
    checked = grid.checked_cells(rules.min_entry_length)
    for slot in grid.slots(rules.min_entry_length):
        marks = [cell in checked for cell in slot.cells]
        for index, (first, second) in enumerate(zip(marks, marks[1:])):
            if first and second:
                yield Violation(
                    "adjacent_checked",
                    f"{_describe(slot)} has checked cells at {index} and {index + 1}",
                )
                break


def check_min_checked(grid: Grid, rules: RuleSet):
    """Rule 9: every entry is crossed at least twice."""
    if rules.min_checked <= 0:
        return
    checked = grid.checked_cells(rules.min_entry_length)
    for slot in grid.slots(rules.min_entry_length):
        count = sum(1 for cell in slot.cells if cell in checked)
        if count < rules.min_checked:
            yield Violation(
                "under_checked",
                f"{_describe(slot)} is checked only {count} time(s)",
            )


def check_symmetry(grid: Grid, rules: RuleSet):
    """Rule 5: the pattern maps onto itself under the required rotation.

    Blocks are cells and rotate onto cells.  Bars are edges and rotate onto
    edges, which is a different arithmetic and was missing here for as long as
    barred grids were only half-supported: a barred pattern has no blocks, so
    this check passed every one of them vacuously.
    """
    if rules.symmetry != "rotational180":
        return
    for cell in grid.blocks:
        mate = grid.partner(cell)
        if mate not in grid.blocks:
            yield Violation("symmetry", f"block {cell} has no partner at {mate}")
    if grid.right_bars or grid.bottom_bars:
        from .barred import mirror_bars

        right, bottom = mirror_bars(grid)
        for bar in sorted(right ^ grid.right_bars):
            yield Violation("symmetry", f"right bar {bar} is unpartnered")
        for bar in sorted(bottom ^ grid.bottom_bars):
            yield Violation("symmetry", f"bottom bar {bar} is unpartnered")


def check_no_repeated_entries(grid: Grid, rules: RuleSet):
    """A word may not appear twice, in either direction."""
    seen: dict[str, Slot] = {}
    for slot in grid.slots(rules.min_entry_length):
        word = grid.pattern(slot)
        if "." in word:
            continue
        if word in seen:
            yield Violation("repeated_entry", f"{word} appears twice")
        seen[word] = slot


def check_connected(grid: Grid, rules: RuleSet):
    """Every white cell must be reachable from every other.

    Not in the original rule list, and its absence was found immediately: the
    generator produced a 9x9 whose middle row was entirely blocked, which is
    two independent crosswords printed as one.  Nothing in the other rules
    forbids that, because every one of them is local to a single entry.
    """
    white = [
        (row, col)
        for row in range(grid.size)
        for col in range(grid.size)
        if (row, col) not in grid.blocks
    ]
    if not white:
        return
    seen = {white[0]}
    stack = [white[0]]
    while stack:
        row, col = stack.pop()
        for step in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if (
                0 <= step[0] < grid.size
                and 0 <= step[1] < grid.size
                and step not in grid.blocks
                and step not in seen
            ):
                seen.add(step)
                stack.append(step)
    if len(seen) != len(white):
        yield Violation(
            "disconnected",
            f"{len(white) - len(seen)} of {len(white)} white cells are cut off",
        )


PREDICATES = (
    check_run_lengths,
    check_no_isolated_cells,
    check_unchecked_runs,
    check_checked_fraction,
    check_max_checked,
    check_alternating,
    check_min_checked,
    check_symmetry,
    check_connected,
    check_no_repeated_entries,
)


def validate(grid: Grid, rules: RuleSet | None = None) -> list[Violation]:
    rules = rules or RuleSet()
    return [v for predicate in PREDICATES for v in predicate(grid, rules)]
