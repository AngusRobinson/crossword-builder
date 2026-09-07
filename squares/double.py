"""Double word squares: rows and columns all words, and all different.

The one shape here that needs no solver of its own. A double square is a
barred grid with no bars -- every across run the full width, every down run
the full height -- so the crossword filler poses it directly and this is a
thin wrapper over it.

Being expressible is not the same as being easy. Under a crude independence
model the expected number of double squares of order n is W^(2n) / 26^(n^2)
against W^n / 26^(n(n-1)/2) for ordinary ones, so doubles are the commoner
kind only while the dictionary holds more than 26^((n+1)/2) words of that
length. That is about 3,400 at four letters and 457,000 at seven, which is why
4x4 falls out instantly and 7x7 has never come out at all: no cells are tied
together, so a placement here says far less than the same placement in a
symmetric square, where it fills a row and a column at once.
"""

from crossword.fill import Filler
from crossword.grid import Grid
from crossword.rules import RuleSet


def double(size, index, *, seed=0, node_budget=8000, restarts=1,
           commonness=0.0, aim=0.85):
    """One n x n grid whose rows and columns are all words."""
    rules = RuleSet(min_entry_length=size, min_checked_fraction=1.0,
                    max_consecutive_unchecked=0, symmetry="none")
    grid = Grid(size=size)
    filler = Filler(grid, index, rules=rules, seed=seed,
                    node_budget=node_budget, commonness=commonness, aim=aim)
    if filler.fill(restarts=restarts):
        return [grid.pattern(s) for s in grid.runs("across")], filler.stats.nodes
    return None, filler.stats.nodes
