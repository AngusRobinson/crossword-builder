"""Extract an American grid library from a corpus of .xd puzzles.

    python3 build_us_library.py xd-puzzles.zip

Only pre-1965 New York Times puzzles are read, and only their geometry: which
squares are blocked. No clue, answer or title is taken, and nothing from any
other publication or later year is touched.

American grids, unlike British ones, are barely reused -- 4,451 puzzles yield
3,091 distinct patterns, where 8,348 Guardian puzzles yield 130. So there is
no usage count worth recording and the library is a sample rather than a
census.
"""

import collections
import re
import sys
import zipfile

from crossword import library
from crossword.grid import Grid
from crossword.rules import RuleSet, validate

US = RuleSet(max_consecutive_unchecked=0, min_checked_fraction=1.0)
OUT = "crossword/grids-us.txt"
LIMIT = 1200


def grid_of(text):
    """The block pattern of an .xd puzzle: '#' is a block, anything else white."""
    rows, started = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if started:
                break
            continue
        if re.fullmatch(r"[A-Z#_.]+", stripped):
            started = True
            rows.append(stripped.replace("_", "#").replace(".", "#"))
        elif started:
            break
    if len(rows) < 5 or len({len(r) for r in rows}) != 1:
        return None
    if len(rows) != len(rows[0]):
        return None
    return Grid.parse("\n".join(rows).lower())


def main(archive):
    with zipfile.ZipFile(archive) as bundle:
        wanted = [
            name for name in bundle.namelist()
            if name.endswith(".xd") and "/nytimes/" in name
            and (m := re.search(r"/((?:19)\d\d)/", name))
            and int(m.group(1)) < 1965
        ]
        print(f"{len(wanted)} pre-1965 New York Times puzzles")

        seen, rejected, read = {}, collections.Counter(), 0
        for name in sorted(wanted):
            try:
                grid = grid_of(bundle.read(name).decode("utf-8", "replace"))
            except (KeyError, ValueError, OSError):
                continue
            if grid is None or grid.size != 15:
                continue
            read += 1
            problems = {v.rule for v in validate(grid, US)}
            if problems:
                rejected.update(problems)
                continue
            seen.setdefault(frozenset(grid.blocks), (grid, name))

    print(f"{read} were 15x15; {len(seen)} distinct patterns pass the rule set")
    print(f"rejected: {dict(rejected.most_common(5))}")

    # Spread the sample across block counts rather than taking the first N,
    # which would all come from the same few years and look alike.
    by_blocks = collections.defaultdict(list)
    for blocks, (grid, name) in seen.items():
        by_blocks[len(blocks)].append((blocks, grid, name))
    chosen = []
    while len(chosen) < LIMIT and any(by_blocks.values()):
        for count in sorted(by_blocks):
            if by_blocks[count] and len(chosen) < LIMIT:
                chosen.append(by_blocks[count].pop())

    patterns = [
        library.Pattern(size=15, blocks=blocks, uses=0,
                        source=name.rsplit("/", 1)[-1][:-3], valid=True)
        for blocks, _grid, name in chosen
    ]
    library.save(patterns, OUT)
    counts = sorted(len(p.blocks) for p in patterns)
    print(f"\nwrote {len(patterns)} patterns to {OUT}")
    print(f"blocks {counts[0]}-{counts[-1]}, median {counts[len(counts)//2]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "xd-puzzles.zip")
