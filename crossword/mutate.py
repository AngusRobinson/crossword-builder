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


def neighbours(pattern: Pattern, rules: RuleSet = None, *, min_length: int = 3):
    """Every legal grid one symmetric block-pair flip away.

    Flipping a cell flips its rotational partner too, so symmetry is never
    broken and never has to be repaired.  The centre cell is its own partner,
    which `Grid.add_block` already handles.

    Legality is the full rule set, not a subset: a neighbour that breaks
    connectivity or over-checks an entry is no use however well its lengths
    line up.
    """
    rules = rules or RuleSet()
    size = pattern.size
    seen = {pattern.blocks}
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
            if not validate(grid, rules):
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
           steps: int = 3, min_length: int = 3, limit: int = 40):
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
            for _cell, grid in neighbours(parent, rules, min_length=min_length):
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
                   commonness: float = 3.0, deadline=None, seed: int = 0):
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
                    budget=budget, commonness=commonness, deadline=deadline,
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
            for _cell, grid in neighbours(parent, rules, min_length=min_length):
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


def best_with_tailoring(patterns, index, targets, rules: RuleSet = None, *,
                        fill_rules: RuleSet = None, seeds: int = 4,
                        beam: int = 3, steps: int = 3, width: int = 6,
                        keep: int = 20, share: float = 0.6,
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

    plain = best_over_library(patterns, index, targets, fill_rules,
                              time_limit=time_limit * (1 - share),
                              seed=seed, **kwargs)

    left = time_limit - (time.time() - started)
    if left <= 1.0:
        return plain

    chosen = sorted(patterns, key=lambda p: fitness(p, targets), reverse=True)[:seeds]
    grown = tailor_by_fill(chosen, targets, index, rules, beam=beam, steps=steps,
                           width=width, deadline=time.time() + left * 0.75,
                           seed=seed, **{k: v for k, v in kwargs.items()
                                         if k in ("commonness",)})
    if not grown:
        return plain

    left = time_limit - (time.time() - started)
    bred = best_over_library(list(patterns) + grown[:keep], index, targets,
                             fill_rules, time_limit=max(5.0, left), seed=seed,
                             **kwargs)
    return bred if (bred.ok, bred.n, bred.quality) > (plain.ok, plain.n,
                                                      plain.quality) else plain
