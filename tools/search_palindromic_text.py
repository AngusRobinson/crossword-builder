"""Search for a square whose whole text reads as a palindromic sentence.

A square that is symmetric and unchanged by a half-turn has, read row by row,
a text that is itself a letter-palindrome -- row n-1-r being the reverse of
row r. So looking for a SATOR square that says something is looking for a
palindromic sentence of exactly n^2 letters whose columns happen to be its
rows.

Here a word may cross a row boundary, which the row-by-row search cannot
allow: HETI and ITEH are not words, so that search discards

    H E T I      "HE TIED IT -- TIDE IT, EH?"
    E D I T
    T I D E
    I T E H

which is the best thing either search has found.

Cells are filled in reading order and the partial text is carried as a set of
pending word-prefixes, so a branch dies the moment its letters cannot continue
any word. That is what makes the space tractable: 5x5 has nine free cells,
5.4e12 grids, and the pruning finds five million segmenting ones in half an
hour -- though not all of them, and the search is ordered alphabetically, so a
run that stops early has seen only grids beginning with the first few letters.

    python3 tools/search_palindromic_text.py 4 3.0
    python3 tools/search_palindromic_text.py 5 3.0 1500
    python3 tools/search_palindromic_text.py 5 3.0 1500 --rows

**The grading is the weak part, and it is the limit now rather than the
search.** It scores part-of-speech bigrams, which a string of two-letter words
maximises while saying nothing: BE WE RE HE RE WE RE WE RE HERE WEB outscores
the square above. Penalising short words instead buries the square above,
English sentences being largely short words. Read the shortlist; do not trust
the order.
"""
import sys, json, time, heapq
sys.path.insert(0, "/Users/angus/Documents/Crosswords/Crossword Builder")
from crossword.words import load
from crossword import frequency
from squares.segmented import vocabulary

size, floor = int(sys.argv[1]), float(sys.argv[2])
budget = float(sys.argv[3]) if len(sys.argv) > 3 else 1800
# --rows requires a word to end where a row does, which is exactly the
# row-by-row search: no word may straddle a row boundary.
rows_only = "--rows" in sys.argv
# Keeping the best 300 by the bigram score keeps 300 strings of two-letter
# words, which is what that score likes. Demanding real words instead is a
# filter the score cannot subvert.
CONTENT = 2
SAVE = None
TEXT = None
for a in sys.argv:
    if a.startswith("--content="):
        CONTENT = int(a.split("=", 1)[1])
    if a.startswith("--save="):
        SAVE = a.split("=", 1)[1]
    if a.startswith("--text="):
        TEXT = a.split("=", 1)[1]
ALL = []
scores = frequency.load_scores("english-names-scores.txt")
raw = json.load(open("out/posall.json"))
entries = load("english-names.txt", min_length=3, max_length=size + 2,
               allow_phrases=False, allow_proper=True, strict=False)
by_len = vocabulary(entries, scores, floor=floor); by_len[1] = {"a", "i"}
vocab = {w for ws in by_len.values() for w in ws}
prefixes = {w[:k] for w in vocab for k in range(len(w) + 1)}

DET = set("the a an this that these those my his her its our your no every each some all".split())
PRON = set("i you he she it we they me him us them who what".split())
PREP = set("of in on at to by for with from up out off over into onto near".split())
CONJ = set("and or but so if as than then when".split())
BE = set("is was are were am be been being".split())
def cls(w):
    if w in DET: return "det"
    if w in PRON: return "pron"
    if w in PREP: return "prep"
    if w in CONJ: return "conj"
    if w in BE: return "verb"
    t = set(raw.get(w, ()))
    for a, b in (("verb","verb"),("noun","noun"),("name","noun"),("adj","adj"),
                 ("adv","adv"),("pron","pron"),("prep","prep"),("conj","conj")):
        if a in t: return b
    return "noun"
PAIR = {("det","noun"):3,("det","adj"):3,("adj","noun"):3,("noun","verb"):3,
        ("pron","verb"):4,("verb","det"):3,("verb","noun"):2,("verb","pron"):2,
        ("verb","adv"):2,("verb","prep"):2,("prep","det"):3,("prep","noun"):2,
        ("prep","pron"):2,("adv","verb"):2,("conj","pron"):2,("conj","det"):2,
        ("noun","prep"):2,("pron","prep"):1,("noun","conj"):1,("noun","noun"):1}
def grade(seq):
    if sum(1 for w in seq if len(w) >= 4) < CONTENT:
        return None
    tags = [cls(w) for w in seq]
    s = sum(PAIR.get(p, -1) for p in zip(tags, tags[1:]))
    if "verb" in tags: s += 4
    s -= 2 * sum(1 for w in seq if len(w) == 1)
    s += min(3, sum(1 for w in seq if len(w) >= 4))
    return s

n = size
def orbit(cell):
    seen, todo = set(), [cell]
    while todo:
        r, c = todo.pop()
        if (r, c) in seen: continue
        seen.add((r, c)); todo += [(c, r), (n-1-r, n-1-c), (n-1-c, n-1-r)]
    return frozenset(seen)
orbits = {(r, c): orbit((r, c)) for r in range(n) for c in range(n)}

A = "abcdefghijklmnopqrstuvwxyz"
grid = [[None]*n for _ in range(n)]
best, seen, count = [], 0, 0
began = time.time()

TRUNCATED = [0]

def readings(text, limit=20_000):
    """Every way the text splits, unless there are absurdly many.

    The first version stopped at the first sixty found depth-first, which is
    not a sample of the readings but the sixty that happen to come first when
    long words are tried before short ones -- so a text whose grammatical
    reading used short words early was graded on readings that did not include
    it. Counting first is cheap and says whether the limit binds at all.
    """
    n = len(text)
    ways = [1] + [0] * n
    for end in range(1, n + 1):
        for take in range(1, min(7, end) + 1):
            if text[end-take:end] in vocab:
                ways[end] += ways[end-take]
    if ways[n] > limit:
        TRUNCATED[0] += 1
    out = []
    def walk(at, parts):
        if len(out) >= limit: return
        if at == n: out.append(list(parts)); return
        for k in range(1, min(7, n-at)+1):
            if text[at:at+k] in vocab:
                parts.append(text[at:at+k]); walk(at+k, parts); parts.pop()
    walk(0, [])
    return out

def step(pos, states):
    global seen
    if time.time() - began > budget: return
    if pos == n*n:
        if "" in states:
            seen += 1
            rows = ["".join(r) for r in grid]
            graded = [(grade(s), s) for s in readings("".join(rows))]
            graded = [g for g in graded if g[0] is not None]
            if not graded:
                return
            if SAVE is not None:
                ALL.append(list(rows))
            top = max(graded)
            if len(best) < 300: heapq.heappush(best, (top[0], top[1], rows))
            elif top[0] > best[0][0]: heapq.heapreplace(best, (top[0], top[1], rows))
        return
    r, c = divmod(pos, n)
    fixed = grid[r][c]
    for ch in (A if fixed is None else fixed):
        nxt = set()
        for s in states:
            t = s + ch
            if t in prefixes:
                nxt.add(t)
                if t in vocab: nxt.add("")
        if not nxt: continue
        if rows_only and c == n - 1:
            # A row must END on a word boundary, which means discarding the
            # states that carry an unfinished prefix -- not merely checking
            # that a finished one is among them. Testing `"" in nxt` and
            # keeping the rest let a word straddle the boundary anyway, so
            # EWERE, which is no word, passed as a row.
            if "" not in nxt:
                continue
            nxt = {""}
        cells = () if fixed is not None else orbits[(r, c)]
        for (i, j) in cells: grid[i][j] = ch
        step(pos + 1, nxt)
        for (i, j) in cells: grid[i][j] = None

step(0, {""})
elapsed = time.time() - began
if SAVE is not None:
    json.dump(ALL, open(SAVE, "w"))
    print(f"wrote {len(ALL):,} candidates to {SAVE}", flush=True)
if TRUNCATED[0]:
    print(f"WARNING: {TRUNCATED[0]:,} texts had more readings than the limit "
          f"and were graded on a subset", flush=True)
print(f"{'rows kept whole' if rows_only else 'words may cross rows'}: "
      f"{seen:,} grids segmented, kept best {len(best)} "
      f"[{elapsed:.0f}s{' -- TIMED OUT' if elapsed > budget else ', exhaustive'}]",
      flush=True)
ranked = sorted(best, reverse=True)
if TEXT:
    with open(TEXT, "w") as handle:
        handle.write(f"# {size}x{size}, floor {floor}, "
                     f"{'rows kept whole' if rows_only else 'words may cross rows'}"
                     f", content {CONTENT}\n")
        handle.write(f"# {seen:,} grids segmented, "
                     f"{'exhaustive' if time.time() - began <= budget else 'TIMED OUT'}\n#\n")
        for v, seq, rows in ranked:
            handle.write(f"{v:>4}  {' '.join(seq).upper():<46} "
                         f"{'/'.join(r.upper() for r in rows)}\n")
    print(f"wrote {TEXT}", flush=True)
for v, seq, rows in ranked[:24]:
    print(f"  {v:>3}  {' '.join(seq).upper():<44} [{'/'.join(r.upper() for r in rows)}]")
