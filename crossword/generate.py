"""Stage 5, second attempt: build the pattern and the fill together.

The first version decided one cell at a time in reading order and assigned a
word the moment a run closed.  Measured at 7x7 it succeeded about half the
time and did not reach 11x11 at all.  The prune counts said why: almost every
failure was a *pattern* failure — run lengths, checking — discovered only
after words had already been placed.  Word decisions and pattern decisions
have very different branching factors, and interleaving them at cell
granularity gave the worst of both.

So the two are now nested rather than interleaved: the pattern search is the
outer loop, the stage 4 filler the inner one, and a fill failure backtracks
into a different pattern.  This is not two independent phases — no pattern is
accepted until something can actually be written into it — and it keeps the
property we want for seeded words, since the pattern search can be constrained
to offer a slot of the right length before any fill is attempted.

Moves are whole rows.  Deciding row r also decides row size-1-r by symmetry,
so a 15x15 pattern is eight decisions rather than 113, and every one of them
closes runs and therefore triggers real pruning.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from functools import lru_cache

from .fill import Filler
from .grid import ACROSS, DOWN, Grid
from .index import Index
from .rules import RuleSet, validate

UNKNOWN = 0
BLOCK = 1
OPEN = 2


class _BudgetExceeded(Exception):
    pass


@lru_cache(maxsize=None)
def row_patterns(size: int, min_length: int) -> tuple:
    """Every legal arrangement of blocks within a single line.

    Legal here means only the run-length rule: white runs are of length 1 or
    at least min_length.  Everything else depends on the other rows and cannot
    be judged one line at a time.

    There are 21 of these at size 5, 254 at size 9 and 10,747 at size 15 —
    small enough to enumerate once and cache, large enough that the search
    samples from them rather than trying all.
    """
    out = set()

    def rec(pos: int, blocks: tuple):
        if pos == size:
            out.add(frozenset(blocks))
            return
        for white in [1] + list(range(min_length, size - pos + 1)):
            if pos + white > size:
                continue
            if pos + white == size:
                rec(size, blocks)
            else:
                for run in range(1, size - (pos + white) + 1):
                    rec(
                        pos + white + run,
                        blocks + tuple(range(pos + white, pos + white + run)),
                    )
        for run in range(1, size - pos + 1):
            rec(pos + run, blocks + tuple(range(pos, pos + run)))

    rec(0, ())
    return tuple(sorted(out, key=lambda s: (len(s), sorted(s))))


def _row_is_legal(blocks, size: int, min_length: int) -> bool:
    run = 0
    for col in range(size):
        if col in blocks:
            if 1 < run < min_length:
                return False
            run = 0
        else:
            run += 1
    return not 1 < run < min_length


@lru_cache(maxsize=None)
def alternating_row_patterns(size: int, min_length: int, parity: int) -> tuple:
    """Row patterns restricted to the lattice family British grids use.

    Two row types.  Odd rows are *link* rows: every odd column blocked, so
    their white cells sit in runs of length 1 and carry no across entry, which
    is what makes the cells above and below them unchecked.  Even rows are
    *entry* rows and may only be blocked at even columns.

    Sampling uniformly from all 10,747 legal rows put essentially zero mass on
    this structure — 0 of 330 drawn patterns satisfied the checking ceiling.
    Restricting the move set puts the search inside the family instead of
    hoping to land in it.  Branching drops to a few hundred per row.
    """
    evens = [c for c in range(size) if c % 2 == 0]
    odds = frozenset(c for c in range(size) if c % 2 == 1)
    out = set()
    for mask in range(1 << len(evens)):
        extra = frozenset(evens[i] for i in range(len(evens)) if mask >> i & 1)
        blocks = extra if parity == 0 else odds | extra
        if _row_is_legal(blocks, size, min_length):
            out.add(blocks)
    return tuple(sorted(out, key=lambda s: (len(s), sorted(s))))


@dataclass
class GenStats:
    nodes: int = 0
    patterns: int = 0
    fills: int = 0
    restarts: int = 0
    elapsed: float = 0.0
    prunes: dict = field(default_factory=dict)

    def note(self, reason: str) -> None:
        self.prunes[reason] = self.prunes.get(reason, 0) + 1

    def __str__(self) -> str:
        top = sorted(self.prunes.items(), key=lambda kv: -kv[1])[:4]
        detail = "  ".join(f"{k}={v}" for k, v in top)
        return (
            f"nodes {self.nodes}  patterns {self.patterns}  fills {self.fills}  "
            f"{self.elapsed:.2f}s  {detail}"
        )


class Generator:
    def __init__(
        self,
        size: int,
        index: Index,
        rules: RuleSet | None = None,
        *,
        density: tuple = (0.16, 0.34),
        row_cap: int = 40,
        branch_cap: int = 200,
        node_budget: int = 20000,
        fill_budget: int = 4000,
        length_bias: float = 0.0,
        variety_bias: float = 0.0,
        temperature: float = 1.0,
        pool: int = 24,
        family: str | None = None,
        max_row_blocks: int | None = None,
        max_short: int | None = None,
        short_penalty: float = 1.0,
        variety_reward: float = 1.0,
        seed: int | None = None,
    ):
        self.size = size
        self.index = index
        self.rules = rules or RuleSet()
        self.density = density
        self.row_cap = row_cap
        self.branch_cap = branch_cap
        self.node_budget = node_budget
        self.fill_budget = fill_budget
        self.length_bias = length_bias
        self.variety_bias = variety_bias
        self.temperature = temperature
        self.pool = pool
        self.family = family
        # Cap the blocks a single row may carry.  Without it the move set is
        # sampled uniformly from every legal row, and at size 15 only 8.3% of
        # those carry four blocks or fewer -- so an American grid, which needs
        # about 2.4 per row, is never drawn.  The alternating family solves
        # the same problem for British grids by restricting the move set; this
        # is the blunter version for styles that have no lattice.
        self.max_row_blocks_allowed = max_row_blocks
        self.max_short = max_short
        self.short_penalty = short_penalty
        self.variety_reward = variety_reward
        self.rng = random.Random(seed)

        self.state = [[UNKNOWN] * size for _ in range(size)]
        self.stats = GenStats()
        self.length_counts: dict = {}

        self.patterns = row_patterns(size, self.rules.min_entry_length)
        if max_row_blocks is not None:
            self.patterns = tuple(p for p in self.patterns
                                  if len(p) <= max_row_blocks)
            if not self.patterns:
                raise ValueError(
                    f"no legal row of width {size} has {max_row_blocks} "
                    f"blocks or fewer")
        if family == "alternating":
            self.by_parity = {
                parity: alternating_row_patterns(
                    size, self.rules.min_entry_length, parity
                )
                for parity in (0, 1)
            }
            self.patterns = tuple(
                sorted(set(self.by_parity[0]) | set(self.by_parity[1]),
                       key=lambda s: (len(s), sorted(s)))
            )
        else:
            self.by_parity = None
        if self.rules.max_entry_length is not None:
            cap = self.rules.max_entry_length
            fits = lambda row: all(L <= cap for L in self._entries_in(row))
            self.patterns = tuple(row for row in self.patterns if fits(row))
            if self.by_parity is not None:
                self.by_parity = {parity: tuple(r for r in rows if fits(r))
                                  for parity, rows in self.by_parity.items()}
            if not self.patterns:
                raise ValueError(
                    f"no legal row of width {size} keeps every entry to "
                    f"{cap} letters or fewer")
        self.max_row_blocks = max(len(p) for p in self.patterns)
        self.min_blocks = math.ceil(density[0] * size * size)
        self.max_blocks = math.floor(density[1] * size * size)
        self._entry_lengths = {
            pattern: self._entries_in(pattern) for pattern in self.patterns
        }

    def _entries_in(self, blocks) -> tuple:
        """Across-entry lengths a row pattern produces, ignoring length-1 runs."""
        lengths = []
        run = 0
        for col in range(self.size):
            if col in blocks:
                if run >= self.rules.min_entry_length:
                    lengths.append(run)
                run = 0
            else:
                run += 1
        if run >= self.rules.min_entry_length:
            lengths.append(run)
        return tuple(lengths)

    # -- geometry ----------------------------------------------------------

    def _at(self, row, col):
        if 0 <= row < self.size and 0 <= col < self.size:
            return self.state[row][col]
        return BLOCK

    def _runs(self, direction: str, line: int):
        runs = []
        start = None
        for offset in range(self.size + 1):
            state = (
                self._at(line, offset)
                if direction == ACROSS
                else self._at(offset, line)
            )
            if state == OPEN:
                if start is None:
                    start = offset
                continue
            if start is not None:
                before = (
                    self._at(line, start - 1)
                    if direction == ACROSS
                    else self._at(start - 1, line)
                )
                closed = before != UNKNOWN and state != UNKNOWN
                runs.append((start, offset - start, closed))
                start = None
        return runs

    def _cells_of(self, direction, line, start, length):
        if direction == ACROSS:
            return [(line, start + i) for i in range(length)]
        return [(start + i, line) for i in range(length)]

    def _perp_run(self, cell, direction):
        row, col = cell
        line = row if direction == ACROSS else col
        offset = col if direction == ACROSS else row
        for start, length, closed in self._runs(direction, line):
            if start <= offset < start + length:
                return (length, closed)
        return None

    # -- rules -------------------------------------------------------------

    def _line_ok(self, direction: str, line: int) -> bool:
        other = DOWN if direction == ACROSS else ACROSS
        for start, length, closed in self._runs(direction, line):
            if not closed:
                continue
            if 1 < length < self.rules.min_entry_length:
                self.stats.note("run_length")
                return False
            if (self.rules.max_entry_length is not None
                    and length > self.rules.max_entry_length):
                self.stats.note("too_long")
                return False
            if length < self.rules.min_entry_length:
                continue

            marks = []
            for cell in self._cells_of(direction, line, start, length):
                perp = self._perp_run(cell, other)
                if perp is None or not perp[1]:
                    marks.append(None)
                else:
                    marks.append(perp[0] >= self.rules.min_entry_length)

            # Honours rules.max_consecutive_unchecked rather than assuming
            # it is 1.  Assuming it cost nothing while only British grids were
            # being built, and made American ones impossible: their limit is
            # 0, every cell being checked, so the search happily produced
            # patterns with single unchecked cells and only found out at
            # validation, after paying for the whole subtree.
            streak = 0
            for mark in marks:
                streak = 0 if mark is not False else streak + 1
                if streak > self.rules.max_consecutive_unchecked:
                    self.stats.note("consecutive_unchecked")
                    return False
            # Unknown cells are optimistically counted as checked, so this
            # only fires once the entry is already beyond saving.
            #
            # floor, matching check_checked_fraction.  While this was a
            # ceiling the search pruned away the entry shapes British grids
            # are actually built from -- an odd-length UCUC...U entry was
            # judged one checked cell short and its whole subtree discarded.
            possible = sum(1 for m in marks if m is not False)
            if possible < math.floor(length * self.rules.min_checked_fraction):
                self.stats.note("checked_fraction")
                return False
            # Upper bound. A cell known checked stays checked, so the count of
            # confirmed checks only grows and this prune is sound.
            if self.rules.max_checked_fraction is not None:
                cap = (
                    int(length * self.rules.max_checked_fraction)
                    + self.rules.max_checked_slack
                )
                if sum(1 for m in marks if m is True) > cap:
                    self.stats.note("over_checked")
                    return False
        return True

    def _isolated_ok(self, rows_changed) -> bool:
        for row in rows_changed:
            for col in range(self.size):
                if self.state[row][col] != OPEN:
                    continue
                across = self._perp_run((row, col), ACROSS)
                down = self._perp_run((row, col), DOWN)
                if not across or not down or not across[1] or not down[1]:
                    continue
                if (
                    across[0] < self.rules.min_entry_length
                    and down[0] < self.rules.min_entry_length
                ):
                    self.stats.note("isolated_cell")
                    return False
        return True

    def _connected_ok(self) -> bool:
        """Connectivity under the relaxation that UNKNOWN cells are passable.

        Sound as a prune: an UNKNOWN cell can only ever become BLOCK or OPEN,
        so treating it as passable can only over-estimate connectivity.  If
        the grid is already severed under that assumption, no later decision
        can repair it.
        """
        target = {
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self.state[r][c] != BLOCK
        }
        if not target:
            return False
        start = next(iter(target))
        seen = {start}
        stack = [start]
        while stack:
            row, col = stack.pop()
            for step in (
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ):
                if step in target and step not in seen:
                    seen.add(step)
                    stack.append(step)
        if len(seen) != len(target):
            self.stats.note("disconnected")
            return False
        return True

    # -- pattern search ----------------------------------------------------

    def _apply(self, row: int, blocks) -> list:
        mirror = self.size - 1 - row
        changed = [row]
        for length in self._entry_lengths[blocks]:
            self.length_counts[length] = self.length_counts.get(length, 0) + 1
            if mirror != row:
                self.length_counts[length] = self.length_counts[length] + 1
        for col in range(self.size):
            self.state[row][col] = BLOCK if col in blocks else OPEN
        if mirror != row:
            changed.append(mirror)
            for col in range(self.size):
                self.state[mirror][col] = (
                    BLOCK if (self.size - 1 - col) in blocks else OPEN
                )
        return changed

    def _revert(self, changed, blocks=None) -> None:
        if blocks is not None:
            step = 2 if len(changed) > 1 else 1
            for length in self._entry_lengths[blocks]:
                self.length_counts[length] -= step
        for row in changed:
            for col in range(self.size):
                self.state[row][col] = UNKNOWN

    def _blocks_placed(self) -> int:
        return sum(row.count(BLOCK) for row in self.state)

    def _rows_undecided(self) -> int:
        return sum(1 for row in self.state if UNKNOWN in row)

    def _short_count(self) -> int:
        """Closed entries at exactly the minimum length."""
        total = 0
        for direction in (ACROSS, DOWN):
            for line in range(self.size):
                for _start, length, closed in self._runs(direction, line):
                    if closed and length == self.rules.min_entry_length:
                        total += 1
        return total

    def _short_ok(self) -> bool:
        """Cap the number of minimum-length entries.

        Ranking could only ever pick the best of whatever was drawn, and when
        most of the pattern space is full of three-letter entries the best of
        forty is still poor. A cap is a constraint instead: it prunes during
        the search, so the patterns that reach the ranker are already the
        right shape. Closed runs never reopen, so the count only grows and the
        prune is sound.
        """
        if self.max_short is None:
            return True
        if self._short_count() > self.max_short:
            self.stats.note("too_many_short")
            return False
        return True

    def _density_ok(self) -> bool:
        placed = self._blocks_placed()
        if placed > self.max_blocks:
            self.stats.note("too_dense")
            return False
        ceiling = placed + self._rows_undecided() * self.max_row_blocks
        if ceiling < self.min_blocks:
            self.stats.note("too_sparse")
            return False
        return True

    def _score(self, blocks) -> float:
        """How much this row pattern is preferred. Never a veto.

        Two terms, both optional and both tunable to zero:

        `length_bias` rewards longer across entries, normalised by grid size
        so it is comparable across sizes.  `variety_bias` rewards lengths that
        are under-represented in what has been committed so far, so a grid of
        eight seven-letter entries scores worse than a mixed one.

        Only across entries are counted.  Down lengths depend on rows not yet
        decided and cannot be scored at this point; by symmetry they end up
        correlated with the across distribution anyway.
        """
        lengths = self._entry_lengths[blocks]
        if not lengths:
            return 0.0
        # The shortest entry, not the mean: a row of [3, 9] has a decent mean
        # but still puts a three-letter word in the grid, which is the thing
        # being discouraged.
        longer = min(lengths) / self.size
        rarer = sum(
            1.0 / (1 + self.length_counts.get(length, 0)) for length in lengths
        ) / len(lengths)
        return self.length_bias * longer + self.variety_bias * rarer

    def _candidates(self, row: int):
        mirror = self.size - 1 - row
        if self.by_parity is not None:
            options = list(self.by_parity[row % 2])
        else:
            options = list(self.patterns)
        if mirror == row:
            # A self-mirroring row has to be its own reflection.
            options = [
                p for p in options if p == frozenset(self.size - 1 - c for c in p)
            ]
        if self.temperature <= 0 or (not self.length_bias and not self.variety_bias):
            self.rng.shuffle(options)
            return options[: self.row_cap]

        # Gumbel-top-k: adding Gumbel noise to log-weights and taking the top
        # k is exactly weighted sampling without replacement.  Every pattern
        # keeps a positive chance however low it scores, which is what makes
        # this a preference rather than a filter.
        scored = []
        for pattern in options:
            gumbel = -math.log(-math.log(self.rng.random()))
            scored.append(
                (self._score(pattern) / self.temperature + gumbel, pattern)
            )
        scored.sort(key=lambda pair: -pair[0])
        return [pattern for _, pattern in scored[: self.row_cap]]

    def _search(self, row: int):
        """Yield complete, legal block patterns."""
        self.stats.nodes += 1
        if self.stats.nodes > self.node_budget:
            raise _BudgetExceeded()

        if row > self.size - 1 - row:
            if self.min_blocks <= self._blocks_placed() <= self.max_blocks:
                self.stats.patterns += 1
                yield self._to_grid()
            return

        for blocks in self._candidates(row):
            changed = self._apply(row, blocks)
            lines = [(ACROSS, r) for r in changed] + [
                (DOWN, c) for c in range(self.size)
            ]
            if (
                self._density_ok()
                and self._short_ok()
                and all(self._line_ok(d, ln) for d, ln in lines)
                and self._isolated_ok(changed)
                and self._connected_ok()
            ):
                yield from self._search(row + 1)
            self._revert(changed, blocks)

    def _to_grid(self) -> Grid:
        grid = Grid(size=self.size)
        for row in range(self.size):
            for col in range(self.size):
                if self.state[row][col] == BLOCK:
                    grid.blocks.add((row, col))
        return grid

    # -- entry point -------------------------------------------------------

    def rank(self, pattern: Grid) -> float:
        """Score a *finished* pattern by its entry-length distribution.

        Scoring whole grids works where biasing row choices did not.  A row's
        across entries say little about the grid: a row full of long entries
        carries few blocks, which forces blocks and therefore short entries
        into other rows, and the effect washes out.  Once the pattern is
        complete the distribution is the real one, and ranking costs the
        search nothing because the search itself stays uniform.
        """
        lengths = [slot.length for slot in pattern.slots(self.rules.min_entry_length)]
        if not lengths:
            return float("-inf")
        shortest = sum(1 for n in lengths if n == self.rules.min_entry_length)
        return (
            -self.short_penalty * shortest / len(lengths)
            + self.variety_reward * len(set(lengths)) / len(lengths)
            + sum(lengths) / len(lengths) / self.size
        )

    def _draw_pattern(self):
        """One complete valid pattern from a fresh search, or None."""
        self.state = [[UNKNOWN] * self.size for _ in range(self.size)]
        self.length_counts = {}
        self.stats.nodes = 0
        try:
            for pattern in self._search(0):
                if validate(pattern, self.rules):
                    self.stats.note("pattern_failed_validation")
                    continue
                return pattern
        except _BudgetExceeded:
            self.stats.note("pattern_budget")
        return None

    def generate(self, restarts: int = 6):
        """Draw an independent pool of patterns, rank them, fill best-first.

        One pattern per search, then start over.  Taking the first `pool`
        patterns from a single search instead gives near-duplicates: the walk
        backtracks only into its deepest rows, so sixty patterns shared one
        row 0 and one row 1, and ranking near-identical candidates bought
        almost nothing above 9x9.  Independent draws make `pool` mean sample
        size, which is what it looked like it meant all along.
        """
        start = time.time()
        for attempt in range(restarts):
            self.stats.restarts = attempt
            pool = []
            for _ in range(self.pool):
                pattern = self._draw_pattern()
                if pattern is not None:
                    pool.append(pattern)
            if not pool:
                continue

            pool.sort(key=self.rank, reverse=True)
            for pattern in pool:
                self.stats.fills += 1
                filler = Filler(
                    pattern,
                    self.index,
                    self.rules,
                    branch_cap=self.branch_cap,
                    node_budget=self.fill_budget,
                    seed=self.rng.randrange(1 << 30),
                )
                if filler.fill(restarts=2):
                    self.stats.elapsed = time.time() - start
                    return pattern
                self.stats.note("fill_failed")
        self.stats.elapsed = time.time() - start
        return None
