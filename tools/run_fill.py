# Run as `python3 tools/run_fill.py` from the repository root: Python puts this
# directory on sys.path, not its parent, so the root goes on explicitly.
import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


from tools.build_test_grid import times_like
from crossword.words import load
from crossword.index import Index
from crossword.fill import Filler
from crossword.rules import validate

index = Index(load("crossword/UKACD.txt"))

for seed in range(5):
    grid = times_like()
    filler = Filler(grid, index, seed=seed)
    if filler.fill():
        print(f"seed {seed}: {filler.stats}")
        print(grid.pretty())
        print(validate(grid) or "clean")
        print()
