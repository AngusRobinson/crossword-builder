"""Draw a grid as HTML: for notebooks, and for a printable page.

Every style is drawn from the same data, because a grid only ever holds three
kinds of thing -- cells that are blocked, cells that carry a letter, and
separators between them.  A blocked grid uses the first, a barred grid the
third, and an American grid neither.

Styling is inline on each element rather than in a stylesheet.  A <style> block
is stripped by Jupyter and by GitHub when they render notebook output, and what
survives is an unstyled table: no black squares, and the host's own row
striping showing through where the blocks should be.
"""

from html import escape

from .grid import ACROSS

EDGE = "#111"
LINE = "#999"
BLOCK = "#222"
MARK = "#fff4cc"


def _cell_style(grid, at, marked, size):
    row, col = at
    edges = {
        "top": "2px solid " + EDGE if row == 0 else "1px solid " + LINE,
        "left": "2px solid " + EDGE if col == 0 else "1px solid " + LINE,
        "bottom": "2px solid " + EDGE if row == size - 1 else "1px solid " + LINE,
        "right": "2px solid " + EDGE if col == size - 1 else "1px solid " + LINE,
    }
    # A bar is a heavy line *inside* the grid, so it overrides the light rule
    # between two cells but never the frame.
    if at in grid.right_bars and col < size - 1:
        edges["right"] = "3px solid " + EDGE
    if at in grid.bottom_bars and row < size - 1:
        edges["bottom"] = "3px solid " + EDGE
    background = BLOCK if at in grid.blocks else (MARK if at in marked else "#fff")
    return (
        f"width:26px;height:26px;padding:0;position:relative;"
        f"text-align:center;vertical-align:middle;"
        f"font:600 14px/26px ui-monospace,Menlo,monospace;color:#111;"
        f"background:{background};"
        f"border-top:{edges['top']};border-left:{edges['left']};"
        f"border-bottom:{edges['bottom']};border-right:{edges['right']};"
    )


def grid_html(grid, *, numbers=True, min_length=3, highlight=(), solution=True):
    """One grid as a self-contained HTML table."""
    numbering = grid.numbering(min_length)[0] if numbers else {}
    marked = set(highlight)
    rows = []
    for row in range(grid.size):
        cells = []
        for col in range(grid.size):
            at = (row, col)
            style = _cell_style(grid, at, marked, grid.size)
            if at in grid.blocks:
                cells.append(f'<td style="{style}"></td>')
                continue
            letter = grid.letters.get(at, "") if solution else ""
            tag = ""
            if at in numbering:
                tag = (f'<span style="position:absolute;top:0;left:2px;'
                       f'font:400 8px/9px ui-monospace,Menlo,monospace;'
                       f'color:#555;">{numbering[at]}</span>')
            cells.append(f'<td style="{style}">{tag}{escape(letter.upper())}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return ('<table style="border-collapse:collapse;margin:8px 0;">'
            + "".join(rows) + "</table>")


def show(grid, **kwargs):
    """`grid_html`, wrapped for display in a notebook cell."""
    from IPython.display import HTML

    return HTML(grid_html(grid, **kwargs))


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


def page(grid, *, title="Untitled", setter="", min_length=3,
         surfaces=None, solution=False):
    """A standalone printable page: the grid, then the two clue lists.

    This is the fallback for styles the puzzle formats cannot carry.  Neither
    ipuz nor Exolve is given bars by this project, and a barred grid written
    into either would describe a different puzzle; written here it is at least
    correct, and it prints.
    """
    from .export import enumeration, spelled

    surfaces = surfaces or {}

    across, down = clue_lists(grid, min_length)

    def listing(name, items):
        lines = [f'<h2 style="font:600 13px sans-serif;margin:14px 0 6px;'
                 f'letter-spacing:.08em;text-transform:uppercase;">{name}</h2>']
        lines.append('<ol style="list-style:none;padding:0;margin:0;'
                     'font:13px/1.7 Georgia,serif;">')
        for number, answer in items:
            surface = surfaces.get(answer, answer)
            shown = escape(spelled(surface, answer).upper()) if solution else ""
            lines.append(
                f'<li><span style="display:inline-block;width:2.2em;'
                f'color:#666;">{number}</span>{shown} '
                f'<span style="color:#666;">'
                f'{enumeration(surface, len(answer))}</span></li>'
            )
        lines.append("</ol>")
        return "".join(lines)

    heading = escape(title) + (f" &middot; {escape(setter)}" if setter else "")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title></head>"
        '<body style="margin:24px;background:#fff;color:#111;">'
        f'<h1 style="font:600 20px Georgia,serif;margin:0 0 2px;">{heading}</h1>'
        + grid_html(grid, min_length=min_length, solution=solution)
        + '<div style="display:flex;gap:36px;align-items:flex-start;">'
        + f"<div>{listing('Across', across)}</div>"
        + f"<div>{listing('Down', down)}</div>"
        + "</div></body></html>"
    )
