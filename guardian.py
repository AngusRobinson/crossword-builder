"""Read a Guardian crossword JSON and recover its block pattern.

Only geometry is used: entry positions, directions and lengths. Clues and
solutions are ignored, so nothing of the puzzle itself is reproduced.
"""

import json

from crossword.grid import Grid


def grid_from_guardian(path: str) -> Grid:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    cols = data["dimensions"]["cols"]
    rows = data["dimensions"]["rows"]

    white = set()
    for entry in data["entries"]:
        x, y = entry["position"]["x"], entry["position"]["y"]
        for i in range(entry["length"]):
            white.add((y, x + i) if entry["direction"] == "across" else (y + i, x))

    grid = Grid(size=cols)
    grid.blocks = {
        (r, c) for r in range(rows) for c in range(cols) if (r, c) not in white
    }
    return grid
