"""Tailor a grid to a word list by editing a real one, not inventing one.

The obvious way to fit a grid to a target list is to generate a pattern around
it.  Measured, that does not work: in the British alternating family a 15x15
pattern search yields roughly one legal grid per ten to twenty draws at about
twenty seconds each, and no relaxation of the density or short-entry limits
improved it.  Almost every draw dies on run lengths or connectivity, because
whole-row moves commit sixteen cells at once and the conflicts only surface
several rows later.

Editing is far cheaper.  Every published grid has sixty to seventy legal
single-flip neighbours -- flip one cell and its rotational partner, keep it if
the whole rule set still passes -- and finding all of them costs 0.4 seconds.
Twelve seeds yield 194 distinct entry-length profiles, 184 of which no library
grid can produce.  That is the headroom a target list needs, reached five
hundred times faster than building a pattern from nothing.

It also inherits what the library grids already are.  A neighbour of a real
Guardian grid is still recognisably British, which a from-scratch search has
to be argued into by rules that only approximate the convention.  The cost is
the other side of the same coin: a mutant has an ancestor, so this buys fit,
not originality.

The walk is on the length profile alone, which is cheap and admits no letters.
Whether words actually go in is settled afterwards by the filler, exactly as
crossword.generate nests the two.  A profile is a promise the fill still has
to keep.
"""

from __future__ import annotations

import random
import time

from .coverage import ceiling, spare
from .library import Pattern
from .rules import RuleSet, validate


def _as_pattern(grid, source: str, size: int) -> Pattern:
    return Pattern(size=size, blocks=frozenset(grid.blocks), uses=0,
                   source=source, valid=True)


# The envelope the published grids occupy, measured from crossword/grids.txt.
# Short entries (three or four letters): median 4, 90th percentile 7, max 10.
# Entries in total: median 28, 90th percentile 32, max 34.
MAX_SHORT = 7
MAX_ENTRIES = 32

# What counts as a long entry.  Eleven rather than nine because nine is
# ordinary -- the median grid has eight entries of nine or more -- while the
# median has just two of eleven or more, so that is the one worth asking for.
LONG_LENGTH = 11


def long_entries(grid, min_length: int = 3) -> int:
    return sum(1 for s in grid.slots(min_length) if s.length >= LONG_LENGTH)


def within_envelope(grid, min_length: int = 3, min_long: int = 0) -> bool:
    """Does this grid look like one the Guardian would print?

    Breeding needs this and pattern-picking does not, because the two face
    different pressures.  A grid with more, shorter entries is easier to fill:
    short slots have more candidates and fewer crossings to satisfy.  The
    ranking puts `filled` first, quite rightly, so the walk discovers that
    chopping entries up makes grids that fill -- and it is correct, and the
    result is not a crossword.

    Unconstrained, breeding produced 8.4 entries of three or four letters
    against 3.3 in the published library, and 33.5 entries against 29.0, both
    past the 90th percentile of anything ever printed.  Fixing the quality
    metric's length bias moved that only from 9.9 to 8.4; the rest is this,
    and no scoring tweak reaches it, because filling really is easier there.
    A constraint is the honest instrument: some grids are simply not ones a
    setter would use, however well they fill.

    `min_long` is the same argument from the other end.  Long entries are the
    hardest to fill, so the search under-supplies them too -- 1.1 of eleven or
    more letters against 2.2 in the library.  Asking for them costs coverage,
    which is why it is a setting and not a default.  Of the 120 published
    grids, 85 have at least one such entry, 76 have two, 46 have three and
    only 6 have five, so beyond three the library itself runs thin.
    """
    slots = grid.slots(min_length)
    if len(slots) > MAX_ENTRIES:
        return False
    if sum(1 for s in slots if s.length <= 4) > MAX_SHORT:
        return False
    if min_long and sum(1 for s in slots if s.length >= LONG_LENGTH) < min_long:
        return False
    return True


def _profile_of(grid, min_length: int = 3) -> dict:
    counts: dict = {}
    for slot in grid.slots(min_length):
        counts[slot.length] = counts.get(slot.length, 0) + 1
    return counts


def disturbance(before: dict, after: dict) -> int:
    """How far one grid's entry lengths are from another's.

    L1 over the length histogram, so a move that turns two seven-letter
    entries into one fifteen scores 3 (two sevens gone, one fifteen added)
    plus whatever the crossing column did.  The gentlest legal flip scores 2.
    """
    return sum(abs(before.get(k, 0) - after.get(k, 0))
               for k in set(before) | set(after))


def neighbours(pattern: Pattern, rules: RuleSet = None, *, min_length: int = 3,
               max_change: int = None, like_library: bool = True,
               min_long: int = 0, keep_white=()):
    """Every legal grid one symmetric block-pair flip away.

    Flipping a cell flips its rotational partner too, so symmetry is never
    broken and never has to be repaired.  The centre cell is its own partner,
    which `Grid.add_block` already handles.

    Legality is the full rule set, not a subset: a neighbour that breaks
    connectivity or over-checks an entry is no use however well its lengths
    line up.

    `max_change` caps how much a move may disturb the entry-length histogram.
    A flip is a coarse move -- removing one block can merge two seven-letter
    entries into a fifteen -- and 8.3% of legal flips lengthen the longest
    entry by four or more.  Measured over 674 flips, 38% score 4 or less and
    89% score 6 or less, so a cap around 4 keeps the gentle third.

    Sliding a block one cell along, the obvious smoother move, is not: it is a
    removal and an addition at once, so it disturbs more (median 10 against 6)
    and only 8.4 are legal per grid against 65.5 flips.

    `like_library` keeps the result inside the envelope real grids occupy;
    see `within_envelope` for why breeding cannot be trusted without it.
    """
    rules = rules or RuleSet()
    size = pattern.size
    seen = {pattern.blocks}
    before = _profile_of(pattern.grid(), min_length) if max_change else None
    for row in range(size):
        for col in range(size):
            grid = pattern.grid()
            cell = (row, col)
            if cell in grid.blocks:
                grid.remove_block(cell)
            else:
                grid.add_block(cell)
            key = frozenset(grid.blocks)
            if key in seen:
                continue
            seen.add(key)
            if any(c in grid.blocks for c in keep_white):
                # A nina cell cannot be bred into a block.
                continue
            if validate(grid, rules):
                continue
            if like_library and not within_envelope(grid, min_length, min_long):
                continue
            if max_change is not None:
                if disturbance(before, _profile_of(grid, min_length)) > max_change:
                    continue
            yield cell, grid


def fitness(pattern: Pattern, targets, min_length: int = 3):
    """How well a pattern's slot lengths suit a target list.

    Lexicographic, and the order matters.  The ceiling -- how many targets
    could be seated at all -- comes first because a word with nowhere to go is
    not a tuning problem.  Spare capacity breaks the tie, because the ceiling
    saturates: on a 15x15 most patterns can already seat every word of an
    eighteen-word list, and what separates them is how much room is left to
    arrange them in.
    """
    profile = pattern.profile(min_length)
    return ceiling(profile, targets), spare(profile, targets)


def tailor(seeds, targets, rules: RuleSet = None, *, beam: int = 4,
           steps: int = 3, min_length: int = 3, limit: int = 40,
           max_change: int = None):
    """Hill-climb from library grids towards a list's length profile.

    A beam rather than a single chain: the neighbourhood is wide and mostly
    flat, so one greedy path stalls on a plateau almost immediately, while
    keeping a handful of equal-scoring grids lets the walk cross it.

    Returns the seeds and everything reached, best first, deduplicated by
    block set.  Nothing here has been filled -- these are candidates for
    `coverage.best_over_library`, which is where words meet the grid.
    """
    rules = rules or RuleSet()
    if not seeds:
        return []

    size = seeds[0].size
    best_by_blocks = {p.blocks: p for p in seeds}
    frontier = sorted(seeds, key=lambda p: fitness(p, targets, min_length),
                      reverse=True)[:beam]

    for depth in range(1, steps + 1):
        found = []
        for parent in frontier:
            root = parent.source.split("+")[0]
            for _cell, grid in neighbours(parent, rules, min_length=min_length,
                                          max_change=max_change):
                key = frozenset(grid.blocks)
                if key in best_by_blocks:
                    continue
                child = _as_pattern(grid, f"{root}+{depth}", size)
                best_by_blocks[key] = child
                found.append(child)
        if not found:
            break
        frontier = sorted(found, key=lambda p: fitness(p, targets, min_length),
                          reverse=True)[:beam]

    started = {p.blocks for p in seeds}
    grown = [p for key, p in best_by_blocks.items() if key not in started]
    grown.sort(key=lambda p: fitness(p, targets, min_length), reverse=True)
    return grown[:limit]


def candidates(patterns, targets, rules: RuleSet = None, *, seeds: int = 8,
               beam: int = 8, steps: int = 5, limit: int = 40,
               min_length: int = 3):
    """The library, plus mutants grown from its best-fitting grids.

    The whole library is kept, not just the seeds: tailoring is meant to add
    reach, and a mutant that scores well on lengths can still fill worse than
    an untouched grid.  Ranking them together lets the fill decide, which is
    the only judge that counts.
    """
    rules = rules or RuleSet()
    patterns = list(patterns)
    chosen = sorted(patterns, key=lambda p: fitness(p, targets, min_length),
                    reverse=True)[:seeds]
    grown = tailor(chosen, targets, rules, beam=beam, steps=steps,
                   limit=limit, min_length=min_length)
    return patterns + grown


# -- guided by the fill, not by the profile --------------------------------


def tailor_by_fill(seeds, targets, index, rules: RuleSet = None, *,
                   beam: int = 3, steps: int = 3, width: int = 6,
                   min_length: int = 3, attempts: int = 1, budget: int = 1500,
                   commonness: float = 3.0, max_change: int = None,
                   min_long: int = 0, keep_white=(), preset: dict = None,
                   aim: float = 0.85, pangram: int = 0, deadline=None,
                   seed: int = 0):
    """Hill-climb on words actually seated, rather than on slot lengths.

    `tailor` optimises a length histogram, which is a bound and not a result:
    it counts how many targets *could* go in, with no letters consulted.
    Measured, grids bred on it place fewer words than the untouched library,
    because a profile that scores well can still cross badly, and the mutants
    outrank the grids that were filling.

    So score each candidate by filling it.  Two stages, because filling every
    neighbour is far too slow: the profile is kept as a cheap filter to pick
    the `width` most promising of the thirty-odd neighbours, and only those
    are actually filled.  The proxy chooses what to look at; the objective
    decides what to keep.

    Scores are (filled, targets seated, fill quality), the same order
    `coverage.best_over_library` uses, so a grid that holds more words always
    wins and elegance only breaks ties.
    """
    from .coverage import cover

    rules = rules or RuleSet()
    if not seeds:
        return []
    size = seeds[0].size
    rng = random.Random(seed)

    def score(pattern):
        got = cover(pattern, index, targets, rules, attempts=attempts,
                    budget=budget, commonness=commonness, aim=aim,
                    pangram=pangram, preset=preset, deadline=deadline,
                    seed=rng.randrange(1 << 30))
        return (got.ok, got.n, got.quality)

    scored = {p.blocks: (score(p), p) for p in seeds}
    frontier = [p for _s, p in sorted(scored.values(), key=lambda sp: sp[0],
                                      reverse=True)[:beam]]

    for depth in range(1, steps + 1):
        if deadline is not None and time.time() > deadline:
            break
        children = []
        for parent in frontier:
            root = parent.source.split("+")[0]
            fresh = []
            for _cell, grid in neighbours(parent, rules, min_length=min_length,
                                          max_change=max_change,
                                          min_long=min_long,
                                          keep_white=keep_white):
                key = frozenset(grid.blocks)
                if key not in scored:
                    fresh.append(_as_pattern(grid, f"{root}+{depth}", size))
            # The cheap filter: look only at the most promising few.
            fresh.sort(key=lambda p: fitness(p, targets, min_length), reverse=True)
            for child in fresh[:width]:
                if deadline is not None and time.time() > deadline:
                    break
                scored[child.blocks] = (score(child), child)
                children.append(child)
        if not children:
            break
        frontier = sorted(children, key=lambda p: scored[p.blocks][0],
                          reverse=True)[:beam]

    started = {p.blocks for p in seeds}
    grown = [(s, p) for key, (s, p) in scored.items() if key not in started]
    grown.sort(key=lambda sp: sp[0], reverse=True)
    return [p for _s, p in grown]


def breeding_can_help(patterns, targets, min_length: int = 3) -> bool:
    """Could a bred grid seat more of this list than the library already can?

    Breeding exists to raise the *bound* -- to build a grid whose entry lengths
    suit a list better than any published one does.  Sometimes there is no
    bound left to raise, and then breeding can only spend the clock.

    That matters because the two arms share a budget: breeding takes 60% of it,
    so a run that gains nothing is strictly worse than not breeding at all.
    Measured on a 443-word list, 17.0 words seated against 18.3 -- and 18.3 is
    exactly what the library alone manages on 40% of the clock, which is what
    it was being left with.

    No grid can seat more targets than it has entries, and a bred grid is
    capped at MAX_ENTRIES, which is below the largest grid in the library. So
    the most any grid could hold is a number this can compute in advance, and
    when some library grid already reaches it there is nothing to gain.
    """
    from .coverage import ceiling

    if not patterns or not targets:
        return False
    room = max(max((len(p.grid().slots(min_length)) for p in patterns),
                   default=0), MAX_ENTRIES)
    reachable = min(len(targets), room)
    best_bound = max((ceiling(p.profile(min_length), targets)
                      for p in patterns), default=0)
    return best_bound < reachable


def best_with_tailoring(patterns, index, targets, rules: RuleSet = None, *,
                        fill_rules: RuleSet = None, seeds: int = 4,
                        beam: int = 3, steps: int = 3, width: int = 6,
                        keep: int = 20, share: float = 0.6,
                        max_change: int = None, min_long: int = 0,
                        preset: dict = None,
                        time_limit: float = 120.0, seed: int = 0, **kwargs):
    """Best cover from the library, then from grids bred to fit the list.

    Run as a fallback rather than a merge, and deliberately: breeding can
    still surface a grid that outranks a better one, so the library's own
    answer is computed first and kept unless mutation beats it outright.  The
    arms cannot lose to each other, only win.

    `share` is how much of the budget mutation may spend before the final
    search has to run on what it found.
    """
    from .coverage import best_over_library

    rules = rules or RuleSet()
    fill_rules = fill_rules or rules
    started = time.time()

    if targets and not breeding_can_help(patterns, targets,
                                        fill_rules.min_entry_length):
        return best_over_library(patterns, index, targets, fill_rules,
                                 time_limit=time_limit, preset=preset,
                                 seed=seed, **kwargs)

    plain = best_over_library(patterns, index, targets, fill_rules,
                              time_limit=time_limit * (1 - share),
                              preset=preset, seed=seed, **kwargs)

    left = time_limit - (time.time() - started)
    if left <= 1.0:
        return plain

    chosen = sorted(patterns, key=lambda p: fitness(p, targets), reverse=True)[:seeds]
    grown = tailor_by_fill(chosen, targets, index, rules, beam=beam, steps=steps,
                           width=width, max_change=max_change,
                           min_long=min_long,
                           # A callable preset is a path nina, which is
                           # re-resolved per grid: no particular cell has to
                           # stay white, and a mutant whose path no longer
                           # fits simply scores nothing.
                           keep_white=() if callable(preset)
                           else tuple(preset or ()),
                           preset=preset, aim=kwargs.get("aim", 0.85),
                           pangram=kwargs.get("pangram", 0),
                           deadline=time.time() + left * 0.75,
                           seed=seed, **{k: v for k, v in kwargs.items()
                                         if k in ("commonness",)})
    if not grown:
        return plain

    left = time_limit - (time.time() - started)
    bred = best_over_library(list(patterns) + grown[:keep], index, targets,
                             fill_rules, time_limit=max(5.0, left),
                             preset=preset, seed=seed, **kwargs)
    return bred if (bred.ok, bred.n, bred.quality) > (plain.ok, plain.n,
                                                      plain.quality) else plain
