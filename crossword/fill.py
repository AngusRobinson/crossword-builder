"""Stage 4: fill a fixed block pattern.

The pattern does not change here.  Only letters are assigned, so any failure
is unambiguously in the search rather than in grid construction.

The node loop computes one candidate mask per unfilled slot.  That single pass
serves as both the forward check (any empty mask kills the node before a word
is enumerated) and the MRV ordering (smallest mask is expanded first), which
is why they are not written as separate steps.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from .grid import EMPTY, Grid, Slot
from .index import Index
from .rules import RuleSet


@dataclass
class Stats:
    nodes: int = 0
    backtracks: int = 0
    restarts: int = 0
    elapsed: float = 0.0
    dead_slot: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"nodes {self.nodes}  backtracks {self.backtracks}  "
            f"restarts {self.restarts}  {self.elapsed:.2f}s"
        )


class Filler:
    """Backtracking search over the entries of a fixed pattern."""

    def __init__(
        self,
        grid: Grid,
        index: Index,
        rules: RuleSet | None = None,
        *,
        branch_cap: int = 200,
        node_budget: int = 20000,
        commonness: float = 3.0,
        seed: int | None = None,
    ):
        self.grid = grid
        self.index = index
        self.rules = rules or RuleSet()
        # Provisional. The right value is unknown until we have measurements
        # from real runs, so it is a parameter rather than a constant.
        self.branch_cap = branch_cap
        self.node_budget = node_budget
        # How hard to lean towards words that have actually been published.
        # 0 is the old uniform behaviour.  3 was measured: it takes the share
        # of never-published fill from 56% to 19% at no cost in coverage at
        # all, and past about 4 the curve is flat, because what remains is
        # slots whose crossings leave no published candidate -- exactly where
        # an unusual word ought to be allowed through.
        #
        # A weighting, not a filter.  Filtering by frequency instead costs
        # real coverage: cutting the dictionary to the 54,660 published words
        # took the benchmark's controls from 14/16 to 11/16.  Quality that is
        # free and quality that is paid for are different things, and this is
        # the free kind.
        self.commonness = commonness
        self.rng = random.Random(seed)

        self.slots = grid.slots(self.rules.min_entry_length)
        self.used: dict[int, int] = {}
        self.stats = Stats()

        # Letters already in the grid when we were handed it.  A restart
        # rewinds to this, not to empty: a themed entry placed by the caller
        # is a premise of the search, not one of its decisions.
        self.preset = dict(grid.letters)

        # Slots the preset already completes are removed from the search
        # rather than re-derived by it.  This is not an optimisation.  A
        # themed entry is very often a proper noun or a phrase, and the fill
        # dictionary deliberately excludes both -- so searching such a slot
        # would find no candidate word, and the caller's own seed word would
        # be reported as an impossible grid.  If the dictionary does happen
        # to hold it, its id is marked used so it cannot appear twice.
        self.fixed = []
        searchable = []
        for slot in self.slots:
            pattern = "".join(self.preset.get(cell, EMPTY) for cell in slot.cells)
            if EMPTY in pattern:
                searchable.append(slot)
                continue
            self.fixed.append((slot, pattern))
            if slot.length in index:
                word_id = index[slot.length].word_id(pattern)
                if word_id is not None:
                    self.used[slot.length] = self.used.get(slot.length, 0) | (
                        1 << word_id
                    )
        self.slots = searchable
        # Restarts rewind to this, not to empty, for the same reason the
        # letters do.
        self.preset_used = dict(self.used)

        missing = {s.length for s in self.slots if s.length not in index}
        if missing:
            raise ValueError(f"dictionary has no words of length(s) {sorted(missing)}")

    # -- search ------------------------------------------------------------

    def _candidates(self, slot: Slot) -> int:
        pattern = self.grid.pattern(slot)
        exclude = self.used.get(slot.length, 0)
        return self.index[slot.length].match(pattern, exclude)

    def _place(self, slot: Slot, word: str, word_id: int) -> list:
        """Write a word, returning the cells this call is responsible for."""
        written = []
        for cell, char in zip(slot.cells, word):
            if cell not in self.grid.letters:
                self.grid.letters[cell] = char
                written.append(cell)
        self.used[slot.length] = self.used.get(slot.length, 0) | (1 << word_id)
        return written

    def _unplace(self, slot: Slot, word_id: int, written: list) -> None:
        for cell in written:
            del self.grid.letters[cell]
        self.used[slot.length] &= ~(1 << word_id)

    # Candidates whose weights are computed in full.  Scoring every one of
    # 33,000 nine-letter words at a node costs more than the node saves, so a
    # larger set is first thinned uniformly.  MRV means this rarely bites:
    # the slot being expanded is the most constrained one there is.
    WEIGHT_POOL = 2000

    def _order(self, length_index, ids: list) -> list:
        """Which candidate words to try, and in what order.

        With no frequency table, or commonness at zero, this is the original
        uniform shuffle.  Otherwise it is Gumbel-top-k on the familiarity
        score, which is exactly weighted sampling without replacement -- the
        same device the pattern search uses.  Weighting rather than filtering
        matters here: an obscure word is still reachable when the crossings
        leave nothing else, which is the difference between a fill that reads
        well and a fill that fails.
        """
        if self.commonness <= 0 or length_index.score is None:
            if len(ids) > self.branch_cap:
                return self.rng.sample(ids, self.branch_cap)
            shuffled = list(ids)
            self.rng.shuffle(shuffled)
            return shuffled

        if len(ids) > self.WEIGHT_POOL:
            ids = self.rng.sample(ids, self.WEIGHT_POOL)
        score = length_index.score
        scored = []
        for word_id in ids:
            gumbel = -math.log(-math.log(self.rng.random()))
            scored.append((self.commonness * score[word_id] + gumbel, word_id))
        scored.sort(key=lambda pair: -pair[0])
        return [word_id for _weight, word_id in scored[: self.branch_cap]]

    def _search(self, remaining: list) -> bool:
        if not remaining:
            return True

        self.stats.nodes += 1
        if self.stats.nodes > self.node_budget:
            raise _BudgetExceeded()

        best = None
        best_mask = 0
        best_count = None
        for slot in remaining:
            mask = self._candidates(slot)
            count = mask.bit_count() if hasattr(int, "bit_count") else bin(mask).count("1")
            if count == 0:
                # Forward check: this slot is already dead, so no assignment
                # made here can succeed.  Fail without enumerating anything.
                key = (slot.direction, slot.row, slot.col)
                self.stats.dead_slot[key] = self.stats.dead_slot.get(key, 0) + 1
                return False
            if best_count is None or count < best_count:
                best, best_mask, best_count = slot, mask, count

        length_index = self.index[best.length]
        ids = self._order(length_index, length_index.ids(best_mask))

        rest = [s for s in remaining if s is not best]
        for word_id in ids:
            word = length_index.words[word_id]
            written = self._place(best, word, word_id)
            if self._search(rest):
                return True
            self._unplace(best, word_id, written)
            self.stats.backtracks += 1

        return False

    # -- entry point -------------------------------------------------------

    def fill(self, restarts: int = 20) -> bool:
        """Fill the grid, restarting on exhaustion of the node budget.

        Restarts rather than exhaustive backtracking: chronological
        backtracking thrashes on crossword instances, and a fresh seed both
        escapes that and varies the output.
        """
        start = time.time()
        for attempt in range(restarts):
            self.grid.letters.clear()
            self.grid.letters.update(self.preset)
            self.used = dict(self.preset_used)
            self.stats.nodes = 0
            self.stats.restarts = attempt
            try:
                if self._search(list(self.slots)):
                    self.stats.elapsed = time.time() - start
                    return True
            except _BudgetExceeded:
                pass
        self.stats.elapsed = time.time() - start
        return False


class _BudgetExceeded(Exception):
    pass
