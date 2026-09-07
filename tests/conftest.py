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


# Tests live in tests/ and the code they exercise lives at the repository
# root. pytest puts this directory on sys.path, not its parent, so the root
# goes on explicitly rather than relying on the working directory happening to
# be right.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
