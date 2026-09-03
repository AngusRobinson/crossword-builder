"""Extract the grid library from the corpus.  Run once; commit the result.

    python3 build_library.py [corpus_dir]

Needs guardian-cc-master/crosswords, which is not in the repository.  The
output, crossword/grids.txt, is -- that is the trade this script exists to
make.
"""

import sys

from crossword import library

corpus = sys.argv[1] if len(sys.argv) > 1 else "guardian-cc-master/crosswords"
patterns = library.extract(corpus)
library.save(patterns, library.DEFAULT_PATH)

valid = [p for p in patterns if p.valid]
print(f"{len(patterns)} distinct patterns from {sum(p.uses for p in patterns)} puzzles")
print(f"{len(valid)} pass the rule set, {len(patterns) - len(valid)} do not")
print(f"most used: {patterns[0].source} in {patterns[0].uses} puzzles")
print(f"written to {library.DEFAULT_PATH}")
