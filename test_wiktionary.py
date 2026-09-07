"""Building a fill dictionary from a Wiktionary extract."""

import json
import subprocess
import sys

import pytest

from crossword.words import load


@pytest.fixture
def extract(tmp_path):
    """A few lines in wiktextract's shape, covering what has to be filtered."""
    rows = [
        {"word": "run", "pos": "verb", "lang_code": "en",
         "senses": [{"glosses": ["to move quickly"]}],
         "forms": [{"form": "runs", "tags": ["present"]},
                   {"form": "ran", "tags": ["past"]},
                   # Wiktextract uses `forms` for table headings too.
                   {"form": "inflection of run", "tags": ["table-tags"]}]},
        {"word": "kestrel", "pos": "noun", "lang_code": "en",
         "senses": [{"glosses": ["a falcon"]}],
         "forms": [{"form": "kestrels", "tags": ["plural"]}]},
        # Two proper nouns, deliberately different. "Kestrel" folds to the
        # same string as the bird, so the loader's rule -- one lowercase
        # citation makes a word ordinary -- should apply. "Ealing" has no
        # lowercase twin and stays a proper noun.
        {"word": "Kestrel", "pos": "name", "lang_code": "en",
         "senses": [{"glosses": ["a surname"]}]},
        {"word": "Ealing", "pos": "name", "lang_code": "en",
         "senses": [{"glosses": ["a London borough"]}]},
        {"word": "teh", "pos": "noun", "lang_code": "en",
         "senses": [{"tags": ["misspelling"], "glosses": ["of the"]}]},
        {"word": "chien", "pos": "noun", "lang_code": "fr",
         "senses": [{"glosses": ["dog"]}]},
        {"word": "-ness", "pos": "suffix", "lang_code": "en",
         "senses": [{"glosses": ["forming nouns"]}]},
        {"word": "twelfth night", "pos": "noun", "lang_code": "en",
         "senses": [{"glosses": ["a feast"]}]},
    ]
    path = tmp_path / "extract.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def build(extract, tmp_path, *extra):
    out = tmp_path / "words.txt"
    subprocess.run([sys.executable, "build_wiktionary.py", str(extract),
                    "--out", str(out), *extra],
                   check=True, capture_output=True)
    return {e.text: e for e in load(str(out), min_length=3)}


def test_inflections_are_kept(extract, tmp_path):
    """Which are most of the value: a plural fills a slot the headword cannot."""
    words = build(extract, tmp_path)
    assert {"run", "runs", "ran"} <= set(words)
    assert "kestrels" in words


def test_what_a_solver_should_not_meet_is_dropped(extract, tmp_path):
    words = build(extract, tmp_path)
    assert "chien" not in words, "another language"
    assert "ness" not in words, "a suffix, not an answer"
    assert "teh" not in words, "tagged as a misspelling"
    assert "kestrel" in words, "the bird survives"
    assert "ealing" not in words, "a place name, filtered by default"
    assert "inflectionofrun" not in words, "a table heading, not a form"


def test_spelling_survives_for_the_enumeration(extract, tmp_path):
    """The fold is what fills the grid; the surface is what the clue says."""
    words = build(extract, tmp_path)
    assert words["twelfthnight"].surface == "twelfth night"
    assert words["twelfthnight"].phrase


def test_proper_nouns_are_kept_for_the_loader_to_filter(extract, tmp_path):
    """The pipeline already knows how to do this, and does it better.

    A build-time cut cannot see that a word occurs both capitalised and not.
    The loader can, and treats such a word as ordinary fill.
    """
    from crossword.words import load

    out = tmp_path / "words.txt"
    import subprocess, sys as _sys
    subprocess.run([_sys.executable, "build_wiktionary.py", str(extract),
                    "--out", str(out)], check=True, capture_output=True)
    plain = {e.text for e in load(str(out), min_length=3)}
    with_proper = {e.text for e in load(str(out), min_length=3,
                                        allow_proper=True)}
    assert with_proper > plain, "proper nouns are in the file, not lost"

    dropped = tmp_path / "cut.txt"
    subprocess.run([_sys.executable, "build_wiktionary.py", str(extract),
                    "--out", str(dropped), "--drop-proper"],
                   check=True, capture_output=True)
    cut = {e.text for e in load(str(dropped), min_length=3, allow_proper=True)}
    assert cut < with_proper


def test_headwords_only(extract, tmp_path):
    words = build(extract, tmp_path, "--no-forms")
    assert "run" in words and "runs" not in words
