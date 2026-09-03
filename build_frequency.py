"""Build the answer-frequency table from the corpus.  Run once; commit it.

    python3 build_frequency.py [corpus_dir]

Needs guardian-cc-master/crosswords, which is not in the repository.  The
output, crossword/frequency.txt, is.
"""

import sys
import warnings

warnings.filterwarnings("ignore")

from crossword import frequency
from crossword.words import load

corpus = sys.argv[1] if len(sys.argv) > 1 else "guardian-cc-master/crosswords"
entries = load("crossword/UKACD.txt", strict=False)
vocabulary = {entry.text for entry in entries}

counts = frequency.extract(corpus, vocabulary)
frequency.save(counts, frequency.DEFAULT_PATH)

print(f"{len(counts)} of {len(vocabulary)} UKACD entries have been used as answers")
print(f"{sum(counts.values())} answer instances counted")
print(f"written to {frequency.DEFAULT_PATH}")
