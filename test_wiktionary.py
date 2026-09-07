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
        {"word": "Kestrel", "pos": "name", "lang_code": "en",
         "senses": [{"glosses": ["a surname"]}]},
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
    assert "kestrel" in words and "Kestrel" not in words, "proper noun dropped"
    assert "inflectionofrun" not in words, "a table heading, not a form"


def test_spelling_survives_for_the_enumeration(extract, tmp_path):
    """The fold is what fills the grid; the surface is what the clue says."""
    words = build(extract, tmp_path)
    assert words["twelfthnight"].surface == "twelfth night"
    assert words["twelfthnight"].phrase


def test_proper_nouns_can_be_kept(extract, tmp_path):
    words = build(extract, tmp_path, "--keep-proper")
    assert "kestrel" in words


def test_headwords_only(extract, tmp_path):
    words = build(extract, tmp_path, "--no-forms")
    assert "run" in words and "runs" not in words
