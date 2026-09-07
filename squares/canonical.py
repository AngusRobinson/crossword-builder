"""Removing the copies a symmetry group hands back.

A SATOR square with its rows in the opposite order is the same square
mirrored, so an exhaustive search returns every solution twice. Which of the
pair is kept does not matter; that exactly one is kept does, because otherwise
"how many are there" is wrong by a factor of two and a top-five list shows
three squares.
"""


def deduplicate(grids):
    """One representative per mirror pair, in the order first seen."""
    seen, unique = set(), []
    for grid in grids:
        key = min(tuple(grid), tuple(reversed(grid)))
        if key not in seen:
            seen.add(key)
            unique.append(grid)
    return unique
