"""Shared fixtures.

test_foundations.py was written to be run as a script, with each test handing
its return value to the next (`index = test_index(entries)`).  That works
under `python3 test_foundations.py` and breaks under pytest, which sees the
parameters as fixture requests and errors on all four.  Declaring them here
makes both runners work, and the script's own __main__ block still passes the
values by hand.

The index is session-scoped because building it reads a 2.6 MB word list and
constructs a bitset universe per length -- about a second, which is worth
paying once rather than once per test.
"""

import pytest

UKACD = "crossword/UKACD.txt"


@pytest.fixture(scope="session")
def entries():
    from crossword.words import load

    return load(UKACD, strict=False)


@pytest.fixture(scope="session")
def index(entries):
    from crossword.index import Index

    return Index(entries)
