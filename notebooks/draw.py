"""Draw a grid as HTML, for notebooks.

Handles all three styles from the same data, because a grid only ever has
three kinds of thing in it: cells that are blocked, cells that carry a letter,
and separators.  A blocked grid uses the first, a barred grid the third, and an
American grid neither.

Nothing here is used by the builder itself.  It exists so the notebook cells
can be about crosswords rather than about HTML.
"""

from html import escape

from crossword.grid import ACROSS

CSS = """
<style>
.xw { border-collapse: collapse; margin: 8px 0; font-family: Menlo, monospace; }
.xw td { width: 30px; height: 30px; border: 1px solid #b0b0b0; text-align: center;
         vertical-align: middle; position: relative; padding: 0;
         font-size: 15px; font-weight: 600; color: #111; background: #fff; }
.xw td.block { background: #222; border-color: #222; }
.xw td.bar-r { border-right: 3px solid #111; }
.xw td.bar-b { border-bottom: 3px solid #111; }
.xw td.edge  { border-color: #777; }
.xw .num { position: absolute; top: 1px; left: 2px;
           font-size: 8px; font-weight: 400; color: #555; }
.xw td.mark { background: #fff4cc; }
.xw-caption { font-family: Menlo, monospace; font-size: 12px; color: #444; }
</style>
"""


def draw(grid, *, numbers=True, min_length=None, highlight=(), caption=None):
    """One grid as an HTML table.

    `highlight` is any iterable of cells to tint, which is how the notebook
    shows where a themed word was seated.
    """
    if min_length is None:
        min_length = 3
    numbering = {}
    if numbers:
        try:
            numbering = grid.numbering(min_length)[0]
        except Exception:
            numbering = {}
    marked = set(highlight)

    rows = []
    for row in range(grid.size):
        cells = []
        for col in range(grid.size):
            at = (row, col)
            classes = []
            if at in grid.blocks:
                cells.append('<td class="block"></td>')
                continue
            if at in grid.right_bars:
                classes.append("bar-r")
            if at in grid.bottom_bars:
                classes.append("bar-b")
            if at in marked:
                classes.append("mark")
            letter = grid.letters.get(at, "")
            tag = f'<span class="num">{numbering[at]}</span>' if at in numbering else ""
            cells.append(
                f'<td class="{" ".join(classes)}">{tag}{escape(letter.upper())}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    table = f'<table class="xw">{"".join(rows)}</table>'
    if caption:
        table += f'<div class="xw-caption">{escape(caption)}</div>'
    return CSS + table


def show(grid, **kwargs):
    """`draw`, wrapped for display in a notebook cell."""
    from IPython.display import HTML

    return HTML(draw(grid, **kwargs))


def cells_of(grid, word, min_length=3):
    """Every cell of the first entry spelling `word`, for highlighting."""
    for slot in grid.slots(min_length):
        if grid.pattern(slot) == word:
            return list(slot.cells)
    return []


def clue_lists(grid, min_length=3):
    """(number, answer) for each direction, in the order a paper prints them."""
    _numbers, across, down = grid.numbering(min_length)
    return (
        [(n, grid.pattern(s)) for n, s in across],
        [(n, grid.pattern(s)) for n, s in down],
    )
