"""Scripts that build the data the project runs on, and benchmarks.

Not imported by `crossword/` or `squares/`: everything here produces a file --
a word list, a familiarity table, a grid library -- which the runtime then
reads. Keeping them a package rather than loose scripts is what lets a test
import one without the repository root being on sys.path by accident.
"""
