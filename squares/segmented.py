"""Rows that are phrases, not single words.

Every square so far has wanted each row to be one dictionary entry, which is
what makes an English sentence impossible: five words of exactly five letters,
with no room for the short ones a sentence is mostly built from. Allowing a
row to break into several words -- IT IS A, or ON TOP -- puts them back, and
with them the articles and prepositions English cannot do without.

The dictionaries have no one- or two-letter entries at all: build_wiktionary.py
takes --min-length 3, so A and IT were never there to be found. Rather than
rebuild for the sake of about seventy words, they are listed here, which also
keeps out the two-letter noise a full list carries (AA, AB, AD, AE, AG...) and
would let a row segment into anything.
"""

# The one-letter words. O is the vocative, as in "O Death".
ONE = frozenset("aio")

# Common two-letter English, and only that. The Scrabble list has about a
# hundred, most of which (AE, EF, GI, UT, ZA) no reader would accept in a
# sentence -- and with breaks allowed anywhere, admitting them lets every row
# segment into something, which is the same as having no constraint at all.
TWO = frozenset("""
am an as at be by do go he hi if in is it me my no of oh ok on or so to up us
we ax ox id ye ah eh um uh lo pa ma re ex an
""".split())


def vocabulary(entries, scores, floor=0.0, longest=None):
    """Words available to build a row from, bucketed by length."""
    by_length = {}
    for entry in entries:
        text = entry.text
        if longest is not None and len(text) > longest:
            continue
        if len(text) == 1:
            if text not in ONE:
                continue
        elif len(text) == 2:
            if text not in TWO:
                continue
        elif scores.get(text, 0.0) < floor:
            continue
        by_length.setdefault(len(text), set()).add(text)
    for text in ONE:
        by_length.setdefault(1, set()).add(text)
    for text in TWO:
        by_length.setdefault(2, set()).add(text)
    return by_length


def strings(by_length, size, max_words=None):
    """Every string of `size` letters that splits into those words."""
    reach = {0: {""}}
    for total in range(1, size + 1):
        out = set()
        for take in range(1, total + 1):
            for head in reach[total - take]:
                for word in by_length.get(take, ()):
                    out.add(head + word)
        reach[total] = out
    if max_words is None:
        return reach[size]
    return {text for text in reach[size]
            if min_words(text, by_length) <= max_words}


def min_words(text, by_length):
    """Fewest words the string can be read as, or a large number if none."""
    best = [0] + [99] * len(text)
    for end in range(1, len(text) + 1):
        for take in range(1, end + 1):
            if text[end - take:end] in by_length.get(take, ()):
                best[end] = min(best[end], best[end - take] + 1)
    return best[len(text)]


def split(text, by_length, limit=6):
    """Readings of the string, fewest words first."""
    found = []

    def walk(at, parts):
        if len(found) >= limit:
            return
        if at == len(text):
            found.append(list(parts))
            return
        for take in range(1, len(text) - at + 1):
            piece = text[at:at + take]
            if piece in by_length.get(take, ()):
                parts.append(piece)
                walk(at + take, parts)
                parts.pop()

    walk(0, [])
    found.sort(key=len)
    return found
