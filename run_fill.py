from build_test_grid import times_like
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
