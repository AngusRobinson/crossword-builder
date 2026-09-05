"""How many words from a target list a grid can be made to hold.

This is the project's objective function, and until now nothing computed it.
The generator ranked patterns by entry-length distribution -- a proxy for
"pleasant grid", not for "fits my words" -- so its search had no idea what it
was optimising for.

Two quantities, and the distinction between them is the whole point:

`ceiling` ignores letters entirely and asks how many targets could even fit
the slot lengths.  It is a bound, computed in microseconds, and no search can
beat it.  `cover` actually places words and completes the grid, so it reports
what was really achieved.

Report the ratio.  Coverage against the list size confounds a weak search
with an impossible list: a 20-word list drawn arbitrarily has a mean ceiling
of 80% before a single letter is considered, so 16/20 may be a perfect score.
Coverage against the ceiling is the number that means something.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .fill import Filler
from .grid import Grid
from .index import Index
from .rules import RuleSet


# -- the bound -------------------------------------------------------------


def ceiling(profile: dict, targets) -> int:
    """Multiset intersection of target lengths with available slot lengths.

    Letters are not consulted, so this over-counts: it assumes any word can
    cross any other.  That is what makes it a bound rather than an estimate.
    """
    want: dict = {}
    for word in targets:
        want[len(word)] = want.get(len(word), 0) + 1
    return sum(min(count, profile.get(length, 0)) for length, count in want.items())


def best_ceiling(patterns, targets) -> tuple:
    """The most promising pattern in a library, and its bound."""
    best, best_n = None, -1
    for pattern in patterns:
        n = ceiling(pattern.profile(), targets)
        if n > best_n:
            best, best_n = pattern, n
    return best, best_n


# -- the achieved coverage -------------------------------------------------


@dataclass
class Cover:
    """The outcome of one attempt to build a grid around a target list."""

    placed: tuple = ()
    grid: object = None
    ok: bool = False           # did the rest of the grid fill?
    ceiling: int = 0      # the bound for the whole library, not one pattern
    quality: float = 0.0  # mean familiarity of the words we chose ourselves
    pattern: object = None
    attempts: int = 0
    stats: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.placed)

    @property
    def score(self) -> float:
        """Achieved coverage as a fraction of what was even possible."""
        return self.n / self.ceiling if self.ceiling else 0.0

    def __str__(self) -> str:
        state = "filled" if self.ok else "UNFILLED"
        return (f"{self.n}/{self.ceiling} targets ({self.score:.0%}), {state}"
                f", fill {self.quality:.2f}")


class _Budget(Exception):
    pass


def _fits(pattern: str, word: str) -> bool:
    return len(pattern) == len(word) and all(
        p == "." or p == c for p, c in zip(pattern, word)
    )


def _fits_slot(letters: dict, slot, word: str) -> bool:
    """Whether a word can go in a slot, without building its pattern.

    The obvious spelling is `_fits(grid.pattern(slot), word)`, and it was
    almost a fifth of the run: half a million calls, each joining a fifteen
    character string only to compare it and throw it away.  Reading the cells
    directly short-circuits on the first disagreement and allocates nothing.
    """
    for cell, char in zip(slot.cells, word):
        seen = letters.get(cell)
        if seen is not None and seen != char:
            return False
    return True


def _crossing(slots, placed):
    """The open slots that share a cell with `placed`, and so just changed.

    Only these can have lost candidates.  Re-checking all 28 slots after every
    placement was most of the seating cost, and all but a handful of them are
    provably unaffected.

    `placed` itself is excluded, and that exclusion is load-bearing.  Asking
    whether the slot we just filled still has a candidate asks whether the
    target word is in the fill dictionary -- and target words are precisely
    the ones that are not.  Including it silently refused every proper noun
    and multi-word answer, which is most of a real puzzle's grid.
    """
    touched = set(placed.cells)
    return [
        slot
        for slot in slots
        if slot is not placed and touched.intersection(slot.cells)
    ]


def _alive(grid: Grid, index: Index, slots) -> bool:
    """Forward check: every slot named still has at least one candidate word."""
    for slot in slots:
        if slot.length not in index:
            return False
        if not index[slot.length].match(grid.pattern(slot)):
            return False
    return True


def fill_quality(grid, index, placed, min_length: int = 3,
                 aim: float = 0.85) -> float:
    """How familiar the chosen words are *for their length*.

    Targets are excluded: they were the setter's choice and are not the
    fill's to answer for, or a themed grid full of proper nouns would score
    as badly written when the obscurity was deliberate.

    Each word is scored by how near its familiarity rank *within its own
    length* comes to `aim`.  Two things follow from that, and both were
    mistakes this replaced.

    Ranking is per length because raw familiarity falls steeply with it --
    2.60 at three letters against 0.40 at fifteen -- so averaging the raw
    figure rewards grids built from short words.  It did: the grids this
    picked carried 9.9 entries of three or four letters against 3.3 in the
    library, and never once chose a grid with a fifteen.

    And the target is 0.85 rather than the maximum, because more familiar is
    not better without limit.  Measured on 21,895 published answers, setters
    sit at a median rank of 0.86 for the length.  Maximising instead put 43%
    of the fill above Zipf 4 where real answers put 17%: not obscure, just
    obvious.
    """
    values = []
    for slot in grid.slots(min_length):
        word = grid.pattern(slot)
        if word in placed:
            continue
        bucket = index.lengths.get(slot.length)
        if bucket is None or bucket.score is None:
            continue
        word_id = bucket.by_word.get(word)
        if aim is None:
            # The superseded monotonic measure, kept reachable so the two can
            # be compared. Normalised by length, or it just counts short words.
            raw = bucket.score[word_id] if word_id is not None else 0.0
            values.append(raw - bucket.mean_score)
            continue
        if bucket.quantile is None or word_id is None:
            values.append(-1.0)
            continue
        values.append(-abs(bucket.quantile[word_id] - aim))
    return sum(values) / len(values) if values else 0.0


def _write(grid: Grid, slot, word) -> list:
    written = []
    for cell, char in zip(slot.cells, word):
        if cell not in grid.letters:
            grid.letters[cell] = char
            written.append(cell)
    return written


def _erase(grid: Grid, written) -> None:
    for cell in written:
        del grid.letters[cell]


def _seat_targets(grid, index, slots, targets, rng, *, budget=1500, branch=5,
                  enough=None):
    """Branch and bound over assignments of target words to slots.

    The first version of this was greedy: it seated a word, never moved it,
    and dropped for good any word that would not go in immediately.  That
    scored 9 of 16 on the benchmark's control lists -- lists whose words
    demonstrably all fit one published grid, so every shortfall was the
    search giving up rather than the grid running out of room.

    Three things do the work here.  Search order takes the most constrained
    target first and breaks ties towards the longest, because a fifteen-letter
    word has one or two homes in a grid and a four-letter word has a dozen;
    seating the long ones late means discovering too late that their slots are
    gone.  Every placement can be undone, so a word that blocks two others is
    reconsidered instead of being lived with.  And the bound -- what is seated
    plus what could still be seated -- cuts any branch that cannot beat the
    best arrangement already found, which is what stops the skip option from
    turning this into an exponential enumeration.
    """
    targets = list(dict.fromkeys(targets))       # de-duplicate, keep order
    # Whatever the caller had already committed.  The search writes and erases
    # as it goes, but an exception -- budget exhausted, or the bound reached --
    # unwinds the stack past every pending erase, so the grid cannot be trusted
    # afterwards and is rewound to this explicitly.
    initial = dict(grid.letters)
    if enough is None:
        enough = len(targets)
    best: list = []
    current: list = []
    nodes = [0]

    def options_for(open_slots, remaining):
        found = {}
        for word in remaining:
            fits = [
                slot
                for slot in open_slots
                if slot.length == len(word)
                and _fits_slot(grid.letters, slot, word)
            ]
            if fits:
                found[word] = fits
        return found

    def recurse(open_slots, remaining):
        nodes[0] += 1
        if nodes[0] > budget:
            raise _Budget()

        options = options_for(open_slots, remaining)
        if len(current) + len(options) <= len(best):
            return                                  # cannot beat what we have
        if not options:
            if len(current) > len(best):
                best[:] = list(current)
            return
        if len(best) >= enough:
            raise _Budget()       # nothing left to win; unwind

        word = min(
            options,
            key=lambda w: (len(options[w]), -len(w), rng.random()),
        )
        choices = options[word]
        rng.shuffle(choices)
        # Prefer a slot the word already agrees with: reusing a committed
        # letter interlocks with what is there instead of spending a fresh
        # cell, and leaves more of the grid free for the words still to come.
        choices.sort(key=lambda s: sum(1 for c in s.cells if c in grid.letters),
                     reverse=True)

        rest = [w for w in remaining if w != word]
        for slot in choices[:branch]:
            written = _write(grid, slot, word)
            if _alive(grid, index, _crossing(open_slots, slot)):
                current.append((word, slot, written))
                if len(current) > len(best):
                    best[:] = list(current)
                recurse([s for s in open_slots if s is not slot], rest)
                current.pop()
            _erase(grid, written)
            if len(best) >= enough:
                raise _Budget()

        # Leaving this word out is a real option -- one word can be worth two
        # -- but it is tried last and the bound above usually kills it.
        recurse(open_slots, rest)

    try:
        recurse(list(slots), targets)
    except _Budget:
        if len(current) > len(best):
            best[:] = list(current)

    # Rebuild the winning arrangement on a clean grid.  Skipping the rewind
    # left stale letters behind, and _write only fills cells that are empty,
    # so a target would be written around the debris and silently mangled.
    grid.letters.clear()
    grid.letters.update(initial)
    seated = []
    for word, slot, _written in best:
        seated.append((word, slot, _write(grid, slot, word)))
    open_slots = [s for s in slots if all(s is not t for _w, t, _x in seated)]
    return seated, open_slots


def cover(
    pattern,
    index: Index,
    targets,
    rules: RuleSet | None = None,
    *,
    attempts: int = 2,
    fill_restarts: int = 3,
    relax: int = 3,
    budget: int = 1500,
    deadline: float | None = None,
    commonness: float = 3.0,
    aim: float = 0.85,
    pangram: int = 0,
    hunger: float = None,
    preset: dict = None,
    seed: int | None = None,
) -> Cover:
    """Build a filled grid holding as many targets as possible.

    Randomised restarts around the seating search, best kept.  On a fill
    failure the most recently seated target is lifted and the fill retried --
    a grid that holds nine targets and completes is worth more than one that
    holds ten and does not, because the second is not a crossword.
    """
    rules = rules or RuleSet()
    rng = random.Random(seed)
    targets = [w for w in targets if len(w) in index]
    bound = ceiling(pattern.profile(rules.min_entry_length), targets)
    best = Cover(ceiling=bound, attempts=attempts)

    if callable(preset):
        # A path nina: the letters land on the white cells along a path, so
        # which cell holds which letter depends on where this grid's blocks
        # fall.  It cannot be settled before the pattern is known, and a grid
        # whose path has the wrong number of white cells cannot carry the
        # message at all.
        preset = preset(pattern)
        if preset is None:
            return Cover(ceiling=bound, attempts=attempts)

    for attempt in range(attempts):
        if deadline is not None and time.time() > deadline:
            break
        grid = pattern.grid()
        if preset:
            # A nina: letters the setter fixed before any word was chosen.
            # The grid is rebuilt each attempt, so they go back on each
            # attempt.  Everything downstream honours them already: `_fits`
            # reads the slot's current pattern, so a target disagreeing with
            # a nina letter is never offered that slot, and the filler treats
            # them as preset exactly like a seeded theme word.
            grid.letters.update(preset)
        slots = grid.slots(rules.min_entry_length)
        seated, _open = _seat_targets(
            grid, index, slots, targets, rng, budget=budget, enough=bound
        )

        for lift in range(relax + 1):
            if lift:
                if not seated:
                    break
                _word, _slot, written = seated.pop()
                _erase(grid, [c for c in written if c in grid.letters])

            # Scaled to the grid, not fixed.  8000 was tuned on British
            # grids, which carry about 28 entries; an American one carries
            # about 74, all of them fully checked, and ran out of nodes before
            # it could finish -- reporting a grid as unfillable that a bare
            # Filler completes in seconds.
            filler = Filler(
                grid, index, rules,
                node_budget=max(8000, 400 * len(slots)),
                commonness=commonness, aim=aim,
                pangram=pangram, hunger=hunger,
                seed=rng.randrange(1 << 30),
            )
            # A pangram is reached by biasing and retrying, so it needs far
            # more restarts than an ordinary fill: each near miss is thrown
            # away rather than backtracked.
            ok = filler.fill(restarts=max(fill_restarts, 25) if pangram
                             else fill_restarts)
            placed = tuple(word for word, _s, _w in seated)
            worth = fill_quality(grid, index, set(placed),
                                 rules.min_entry_length, aim) if ok else 0.0

            # Lexicographic, and the order is the policy: a completed grid
            # always beats an incomplete one, more targets always beat fewer,
            # and only then does the fill's quality break the tie.  Quality
            # must never buy its way past coverage -- an elegant grid missing
            # a themed entry is the wrong trade.
            if (ok, len(placed), worth) > (best.ok, best.n, best.quality):
                best = Cover(
                    placed=placed,
                    grid=Grid.parse(grid.render()) if ok else None,
                    ok=ok,
                    ceiling=bound,
                    quality=worth,
                    attempts=attempt + 1,
                    stats={"nodes": filler.stats.nodes},
                )
            if ok:
                break
            grid.letters = dict(filler.preset)

        if best.ok and best.n == bound:
            break

    return best


def spare(profile: dict, targets) -> int:
    """Slots left over at the lengths the targets want.

    The ceiling saturates: on a 15x15 most patterns can seat all eighteen
    words of a long list, so ranking on it alone leaves dozens tied and the
    tie is broken by popularity, which has nothing to do with fit.  Spare
    capacity is what distinguishes them.  A pattern offering five seven-letter
    slots for three seven-letter targets can put them anywhere; one offering
    exactly three has already made the choice, and if those three do not
    cross agreeably there is no second arrangement to try.
    """
    want: dict = {}
    for word in targets:
        want[len(word)] = want.get(len(word), 0) + 1
    return sum(max(0, profile.get(length, 0) - count) for length, count in want.items())


def best_over_library(patterns, index, targets, rules=None, *, top=14,
                      time_limit: float = 45.0, quality_scan: int = 4,
                      **kwargs):
    """Try the most promising patterns in a library, return the best cover.

    Patterns are tried by bound first, then by spare capacity.  Once no
    remaining pattern can beat the coverage already achieved, the scan does
    not stop immediately: it keeps going for `quality_scan` more patterns,
    because two grids holding the same targets are not equally good.  Which
    grid you choose decides what the rest of the fill has to be, and that is
    a decision the filler cannot make for itself -- by the time it runs, the
    pattern is fixed and the awkward corner is already there.

    Set quality_scan to 0 to stop at the first pattern achieving best
    coverage, which is faster and was the behaviour before fill quality was
    measured at all.
    """
    rules = rules or RuleSet()
    scored = sorted(
        ((ceiling(p.profile(rules.min_entry_length), targets),
          spare(p.profile(rules.min_entry_length), targets), i, p)
         for i, p in enumerate(patterns)),
        key=lambda t: (-t[0], -t[1], t[2]),
    )[:top]

    # A wall-clock cap, because the node budget is not one.  Cost per node
    # varies by two orders of magnitude with grid and list, and without this
    # a single awkward list ran for thirty-two minutes while its neighbours
    # took ten seconds.  Whatever has been found when the clock runs out is
    # returned; the search improves monotonically, so an early stop costs
    # quality, never correctness.
    deadline = time.time() + time_limit

    best = Cover(ceiling=scored[0][0] if scored else 0)
    spent = 0
    for bound, _spare, _i, pattern in scored:
        if time.time() > deadline:
            break
        if best.ok and best.n >= bound:
            # No coverage left to win here or below -- the list is sorted by
            # bound.  Keep looking only for a better fill, and not for long.
            spent += 1
            if spent > quality_scan:
                break
        got = cover(pattern, index, targets, rules, deadline=deadline, **kwargs)
        if (got.ok, got.n, got.quality) > (best.ok, best.n, best.quality):
            best = got
            best.pattern = pattern
    # cover() knows only its own pattern's bound.  Score against the best
    # bound the library offers, or a pattern that happened to be easy would
    # flatter the result.
    if scored:
        best.ceiling = scored[0][0]
    return best
