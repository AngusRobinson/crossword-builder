"""Word squares and their relatives.

Separate from `crossword/` because they are a different problem. A crossword
constrains a cell against a word -- "this entry must be in the dictionary" --
and the filler is built around that. A word square constrains a cell against
another *cell*: grid[r][c] == grid[c][r] for the symmetric kind, and a
half-turn as well for a SATOR square. That is not something the filler can be
asked for, so these have solvers of their own.

The shapes differ only in which cells are forced equal:

    double square, rectangle   no cells tied
    ordinary square            transpose
    SATOR square               transpose and half-turn

and the size of that symmetry group is what decides difficulty, because it
decides how far one placed letter propagates.
"""
