import collections

from shortest import contains


def bag(letters):
    return collections.Counter(letters)


def test_any_order():
    assert contains("sequoia", bag("aeiou"), False)
    assert not contains("sequin", bag("aeiou"), False)


def test_letters_are_a_multiset():
    assert contains("assess", bag("sss"), False)
    assert not contains("ases", bag("sss"), False)


def test_in_order_is_a_subsequence_not_a_substring():
    assert contains("facetious", "aeiou", True)
    assert not contains("sequoia", "aeiou", True)
    assert contains("abba", "aa", True)
    assert not contains("ab", "ba", True)
