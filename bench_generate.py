"""Measure the stage 5 generator. Not a test: the numbers move with the
dictionary and the seed, so this reports rather than asserts."""

import warnings

from crossword.generate import Generator
from crossword.index import Index
from crossword.rules import validate
from crossword.words import load

UKACD = "crossword/UKACD.txt"   # <-- set this to your own path

warnings.filterwarnings("ignore")
index = Index(load(UKACD, strict=False))

for size in (5, 7, 9, 11, 13, 15):
    ok = 0
    elapsed = 0.0
    for seed in range(4):
        tight = dict(row_cap=25, node_budget=8000, pool=4) if size >= 13 else {}
        gen = Generator(size, index, seed=seed, **tight)
        grid = gen.generate()
        elapsed += gen.stats.elapsed
        if grid is not None:
            assert validate(grid) == []
            ok += 1
    print(f"{size}x{size}: {ok}/4 succeeded in {elapsed:.1f}s")
