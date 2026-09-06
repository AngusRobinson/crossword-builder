"""Ordinary word squares: the symmetric kind, where the rows and columns agree.

    H E A R T
    E M B E R
    A B U S E
    R E S I N
    T R E N D

This is not the puzzle the rest of the project solves, and it cannot be
expressed as one.  Every constraint elsewhere holds between a cell and a word --
"this entry must be a dictionary word" -- while a word square holds between two
*cells*, grid[r][c] == grid[c][r], which the filler has no way to say.

But the symmetry that makes it inexpressible also makes it small.  Only the
upper triangle is free, so a square of order n is n words rather than 2n, and
each word placed constrains every word not yet placed: setting row k also sets
column k, which supplies one letter to every other row.

So this is the same search the filler runs, over n slots instead of 30.  At
every node it computes the candidate set for each unplaced row -- a mask per
known letter, as ever -- and that single pass both prunes the branch, when some
row has nothing left, and says which row to take next, being the one with least
freedom.  Filling strictly top to bottom instead, which the prefix structure
invites, is what leaves a 7x7 out of reach.
"""

from __future__ import annotations

import math
import random


class Budget(Exception):
    """Raised to unwind when a search has spent its nodes."""


def _order(bucket, ids, rng, commonness, aim, cap):
    """Candidate words, best first, with nothing excluded.

    The same Gumbel-top-k device the filler uses: a random order that still
    favours familiar words, so a restart explores somewhere new and an obscure
    word stays reachable when the prefix leaves nothing else.
    """
    quantile = bucket.quantile
    if commonness <= 0 or quantile is None:
        chosen = list(ids)
        rng.shuffle(chosen)
        return chosen[:cap]
    scored = []
    for word_id in ids:
        jolt = -math.log(-math.log(rng.random()))
        scored.append((jolt - commonness * abs(quantile[word_id] - aim) * 4.0,
                       word_id))
    scored.sort(key=lambda pair: -pair[0])
    return [word_id for _weight, word_id in scored[:cap]]


def search(size, index, *, seed=0, node_budget=20000, commonness=0.0,
           aim=0.85, branch_cap=200, distinct=True):
    """One ordinary word square of the given order, or None.

    Returns (rows, nodes).  `distinct` forbids a word appearing twice; in a
    symmetric square the rows and the columns are the same set of words, so a
    repeat shows up twice over.
    """
    bucket = index.lengths.get(size)
    if bucket is None or not bucket.words:
        return None, 0
    rng = random.Random(seed)
    rows: dict = {}
    used: set = set()
    spent = [0]

    def pattern_for(row: int) -> str:
        # Position k of this row is the cell (row, k), which is the same cell
        # as (k, row).  So it is known exactly when row k has been placed.
        return "".join(rows[k][row] if k in rows else "."
                       for k in range(size))

    def place() -> bool:
        if len(rows) == size:
            return True
        spent[0] += 1
        if spent[0] > node_budget:
            raise Budget()

        # One pass over the unplaced rows: it prunes and it orders.
        best, best_mask, fewest = None, 0, None
        for row in range(size):
            if row in rows:
                continue
            mask = bucket.match(pattern_for(row))
            count = bin(mask).count("1")
            if count == 0:
                return False
            if fewest is None or count < fewest:
                best, best_mask, fewest = row, mask, count

        for word_id in _order(bucket, bucket.ids(best_mask), rng, commonness,
                              aim, branch_cap):
            word = bucket.words[word_id]
            if distinct and word in used:
                continue
            rows[best] = word
            used.add(word)
            if place():
                return True
            del rows[best]
            used.discard(word)
        return False

    try:
        if place():
            return [rows[i] for i in range(size)], spent[0]
    except Budget:
        pass
    return None, spent[0]


def find(size, index, *, tries=60, node_budget=8000, seed=0, **kwargs):
    """Restart until a square comes out.  Returns (rows, tries, nodes)."""
    total = 0
    for attempt in range(tries):
        rows, nodes = search(size, index, seed=seed + attempt,
                             node_budget=node_budget, **kwargs)
        total += nodes
        if rows:
            return rows, attempt + 1, total
    return None, tries, total


def is_square(rows) -> bool:
    """Does this actually read the same down as across?"""
    size = len(rows)
    if any(len(row) != size for row in rows):
        return False
    return all(rows[r][c] == rows[c][r]
               for r in range(size) for c in range(size))
