"""Hand-built 15x15 pattern in the Times family, for testing the filler.

Constraints this pattern has to satisfy, all of them discovered the hard way:

  * Odd rows carry blocks at every odd column, so they hold no across entries
    and their white cells are unchecked.
  * Even-row blocks sit only at even columns 4, 6, 8 or 10.  Column 2 or 12
    would leave an across run of length 2; odd columns would add blocks to
    columns that are already all length-1 runs.
  * No column may take more than one block.  A column split by two blocks has
    a middle run starting on an odd row, and such a run is always one checked
    cell short of the rule 4 ceiling.
  * The two symmetric pairs therefore use columns 4/10 and 6/8, one block
    each, which is the maximum this family allows.
"""
# Run as `python3 tools/build_test_grid.py` from the repository root: Python puts this
# directory on sys.path, not its parent, so the root goes on explicitly.
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


from crossword.grid import Grid

ODD_ROW = {1, 3, 5, 7, 9, 11, 13}
PAIRS = [((4, 4), (10, 10)), ((8, 6), (6, 8))]


def times_like() -> Grid:
    grid = Grid(size=15)
    for row in range(1, 15, 2):
        for col in ODD_ROW:
            grid.add_block((row, col))
    for cell, _mate in PAIRS:
        grid.add_block(cell)      # add_block places the partner itself
    return grid


if __name__ == "__main__":
    g = times_like()
    # On an unfilled grid the emphasis inverts: the block pattern is the
    # content, so blocks go solid and empty cells recede.
    print(g.pretty(block="\u2588", empty="\u00b7"))
    print()
    print(g.annotate(gap=" "))
