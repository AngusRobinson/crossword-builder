# Crossword Builder

Builds crossword grids: British cryptic, American, or the barred 12x12 of a
Mephisto or an Azed.

Give it a theme — answers you have already decided on — and it finds a grid
those words fit into, fills the rest from a dictionary, and writes a puzzle
file you can take into [Exet](https://exet.app) to write clues. A theme is
optional: with no words at all it simply fills a grid on its own merits, which
is a perfectly ordinary way to start a puzzle.

It can also hide a message in the grid, insist on a pangram, choose how obscure
the fill is allowed to be, and print nothing at all if you are scripting it.

```
$ python3 make_grid.py --file birds.txt --out out/birds --title "Dawn Chorus"

█ S U B G E N R E S █ K Y L E
█ H █ I █ P █ E █ U █ E █ A █
L A S T W O R D █ B U S I N G
█ K █ T █ C █ W █ S █ T █ G █
J O S E P H █ I N T E R C O M
█ █ █ R █ █ █ N █ R █ E █ U █
G U N N E R █ G O A L L E S S
█ N █ █ █ E █ █ █ T █ █ █ T █
N I G H T J A R █ A V O C E T
█ F █ A █ O █ O █ █ █ C █ █ █
M O D I F I E R █ C U R L E W
█ R █ R █ N █ Q █ U █ E █ D █
S M R I T I █ U M B R A T I C
█ L █ E █ N █ A █ I █ T █ C █
D Y E R █ G O L D C R E S T █

placed 7 of 7 targets (100% of the 7 that could fit this library) in 2s
   avocet             across at row 9, col 10
   bittern            down at row 1, col 4
   ...
grid: library pattern 26192 (used by 237 published puzzles)
fill: 23 words, familiarity rank 0.77 (published answers average 0.86), 1 unknown to both sources (umbratic)
rules: clean
wrote out/birds.ipuz and out/birds.html
```

That last line is the honest kind of output this aims for: it placed every
target, but `umbratic` is a word neither source has a record of, and it says so
rather than letting it pass.

## Contents

- [Notebooks](#notebooks)
- [Getting started](#getting-started)
- [The settings](#the-settings)
- [American grids](#american-grids)
- [Barred grids](#barred-grids)
- [Ninas](#ninas)
- [Pangrams](#pangrams)
- [How it works](#how-it-works)
- [Reading the output](#reading-the-output)
- [Measuring changes](#measuring-changes)
- [Rebuilding the data files](#rebuilding-the-data-files)
- [Design notes](#design-notes)

## Notebooks

`notebooks/` walks through how the builder works, with the outputs stored so
they read without being run.

| | |
|---|---|
| [1. Building a grid](notebooks/01-building-a-grid.ipynb) | one puzzle end to end: dictionary, grid library, rules, seating, fill, export |
| [2. Words and the index](notebooks/02-words-and-the-index.ipynb) | where the dictionary comes from, how familiarity is scored, what each of the three dials does, and how pattern matching becomes integer arithmetic |
| [3. The fill search](notebooks/03-the-fill-search.ipynb) | forward checking, which entry to expand, choosing words without excluding any, and what failure looks like |
| [4. The other styles](notebooks/04-the-other-styles.ipynb) | American and barred grids, what changed for each, and why where the patterns come from matters more than any rule |
| [5. Ninas and pangrams](notebooks/05-ninas-and-pangrams.ipynb) | hiding a message where the solver would not read, asking for the whole alphabet, and what each costs |

## Getting started

You need Python 3.8 or later and a word list. The project is built around
UKACD, the UK Advanced Cryptics Dictionary — 221,835 entries, copyright J Ross
Beresford, 3-clause BSD and so redistributable provided its notice travels with
it. Put it at `crossword/UKACD.txt`. Any similar list will work, though the
familiarity tables are keyed to UKACD's spellings.

Two other dictionaries have builders, and each writes its own familiarity table
beside itself, which `--dictionary` then picks up without being told:
`tools/build_wiktionary.py` for a much larger British-leaning list, and
`tools/build_american.py` for Spread the Wordlist. Use the American one for American
grids — it takes them from half filling to five in six, because a grid that
checks every cell leans on the short entries and UKACD has a third as many
three-letter words. It stops at fifteen letters, so it cannot fill a jumbo.

Build a familiarity table to go with any dictionary you add:

```bash
python3 tools/build_frequency.py --dictionary wiktionary.txt
```

That writes `wiktionary-scores.txt`, which `--dictionary` then finds by name.
It matters more than it looks. `--min-score` is an absolute cut, so reading
UKACD's numbers against another list's words silently discards everything the
table has never met: the committed table covers 105,373 words, which is 35% of
Wiktionary's five-letter entries, so without its own table a familiarity
ranking over Wiktionary mostly measures whether a word is in UKACD.

Nothing else is required. The grid library and the word-familiarity tables are
committed as data files.

The layout, since there are two projects here rather than one:

    crossword/   the crossword runtime: grids, rules, the fill search
    squares/     word squares, which need solvers of their own
    tools/       scripts that build data — word lists, tables, grid libraries
    tests/       the test suite; `python3 -m pytest` from the root
    experiment/  the parameter study, its design and its results

with `make_grid.py`, `word_square.py` and `sator.py` at the root as the three
things you actually run.

```bash
python3 make_grid.py kestrel curlew avocet bittern redwing
```

Four themed lists are included to try it with:

| | |
|---|---|
| [`lists/birds.txt`](lists/birds.txt) | 391 birds |
| [`lists/trees.txt`](lists/trees.txt) | 138 trees |
| [`lists/elements.txt`](lists/elements.txt) | 113 chemical elements |
| [`lists/instruments.txt`](lists/instruments.txt) | 80 musical instruments |

**A target does not have to be in the dictionary.** The builder seats the word
you gave it and fills around it, so specialist vocabulary the dictionary has
never heard of works exactly as well — about a hundred of those bird names are
not in UKACD. Only the *fill* comes from the dictionary.

Words can be arguments, a file (`--file words.txt`, one per line), or piped in.
Quote multi-word answers: `"twelfth night"`. Case, spaces, hyphens and accents
are folded away, and the original spelling is kept for the enumeration, so
`Twelfth Night` is clued as `(7,5)` rather than `(12)`.

No words at all is a valid request — a nina, a pangram or the quality settings
give a grid something to be on their own.

Write the puzzle out with `--out BASE`. For British and American grids that
produces `BASE.ipuz` (Exet imports it) and `BASE.html` (a self-contained
[Exolve](https://exolve.app) page that opens in a browser). Neither carries
clues, because this project does not write them; both leave the clue slots
empty with the answers and enumerations attached, which is the state a setter
wants to start from.

A barred grid gets `BASE.html` alone, a printable page rather than a puzzle
file — neither format can place a bar. Add `--blank` for the grid without its
answers.

**How long should the list be?** Longer helps, with sharply diminishing
returns. On British grids, three lists at each size:

| words offered | themed entries seated | as % of the grid |
|---|---|---|
| 8 | 7.7 | 26% |
| 32 | 12.7 | 44% |
| 128 | 15.7 | 54% |
| 512 | 18.0 | 62% |

Sixty-four times the list buys 2.3 times the themed entries. Past a hundred or
so the list has stopped being the constraint, and what limits the grid is how
its entries cross one another. So a list of 500 birds is worth having over a
list of 30 — but it will not give you a grid of birds.

## The settings

| Setting | Default | What it does |
|---|---|---|
| `--time-limit S` | 45 | Wall-clock budget for the whole search |
| `--tries N` | 3 | Run N times from consecutive seeds and keep the best |
| `--seed N` | 0 | The first seed; `--tries` counts up from it |
| `--aim Q` | 0.85 | How familiar the fill should be, as a rank within each word's own length. Lower is harder |
| `--commonness F` | 3.0 | How hard to steer towards `--aim`; 0 disables |
| `--min-score S` | 0 | Hard floor: refuse fill words below this familiarity |
| `--max-uses N` | off | Hard ceiling: bar words used more than N times as a Guardian answer, to keep out tired crosswordese |
| `--long N` | 0 | Require at least N entries of 11+ letters |
| `--patterns N` | 14 | How many library grids to consider |
| `--style S` | british | `british`, `us` or `barred`; see below |
| `--no-tailor` | off | Skip breeding grids to fit; about a third of the time, slightly worse. Breeding is skipped anyway when it provably cannot help |
| `--nina`, `--nina-path` | — | Hide a message; see below |
| `--pangram N` | 0 | Require every letter of the alphabet N times |
| `--nina-exact` | off | Make the message fill its whole path, not just the start of it. Always on for a perimeter |
| `--blank` | off | Write the HTML page without the answers |
| `--quiet`, `-q` | off | Print nothing but errors, for scripting |
| `--library PATH` | — | Read grid patterns from this file instead of the style's own |

**`--tries` is doing more work than any other setting.** The same list run
twice gives different answers, sometimes by a lot: over 12 dense lists at 8
seeds each, one run averaged 88.4% of the achievable coverage and the best of
three averaged 96.5%. Four runs cleared the last unrecognised fill word.
Nothing changes after that, so three is the default.

The variance is per-list, and you cannot tell which kind you have in advance.
One list gave 19 on all eight seeds; another gave 14, 12, 20, 20, 20, 20, 20,
15. That is the argument for three rather than one — not that three is better
on average, but that a single run might be the 12.

```
$ python3 make_grid.py --file dense.txt
3 tries placed [14, 12, 20] -- keeping the best
placed 20 of 20 targets (100% of the 20 that could fit this library) in 120s
```

Each try gets its own `--time-limit`, so N tries takes N times as long. Set
`--tries 1` when iterating on an idea.

**Whether splitting a fixed budget is worth it depends on the style**, and the
gain tracks how much the search varies from seed to seed. Given one minute,
spent either as a single search or as the best of several shorter ones:

| | one 60s search | best of 8 x 7.5s | seed-to-seed spread |
|---|---|---|---|
| British | 0.686 | 0.697 | 0.024 |
| barred | 0.349 | 0.391 | 0.179 |
| jumbo | 0.632 | **0.836** | 0.322 |
| American | 0.333 | 0.333 | 0.359 |

A British search is reliable — every seed lands in much the same place, so
there is no luck to catch and one long search is as good as any split. A jumbo
varies enormously, and splitting the budget is worth a third more coverage and
lifts completion from 83% to 100%. American gains nothing because its failures
are structural rather than unlucky: no seed completes a 20-word theme.

So: **British, one long search. Jumbo and barred, several short ones.** With a
minute of patience, `--tries 8 --time-limit 8` on a jumbo against `--tries 1
--time-limit 60` on a British 15x15.

`--aim` is the one to reach for next. It targets a familiarity *rank* rather
than a maximum, because more common is not better without limit: maximising put
43% of the fill above Zipf 4 where published answers put 17%. Real answers sit
at the 86th percentile for their length, hence the default. Drop it to 0.5 for a
markedly harder puzzle.

The hard cuts (`--min-score`, `--max-uses`, `--long`) all cost coverage, which
is why they are off. Prefer `--commonness` and `--aim` unless you want purity at
any price — though `--min-score 1.0` is worth it on a very tightly constrained
grid, where it is often the difference between some unknown words and none.

## American grids

`--style us` swaps the rule set and the library. British grids check about half
the letters of each entry; American ones check every one, and everything else
follows from that — 34 blocks against 69, and 74 entries against 28.

```bash
python3 make_grid.py --style us --time-limit 120
```

The library is 2,500 patterns taken from pre-1965 New York Times puzzles,
geometry only. The rule set needed no new predicates: every letter checked is
`RuleSet(max_consecutive_unchecked=0, min_checked_fraction=1.0)`, and real
American grids validate against it — 3,091 of 4,451 puzzles pass, with about
35 rejected in total.

Fill reliability depends steeply on density, because a sparser grid means
longer entries and every letter is checked twice:

| blocks | filled | time |
|---|---|---|
| 43–49 | 9/10 | 5s |
| 34 | 7/10 | 18s |
| 23–27 | 2/10 | 48s |

**Themed American grids do not work yet.** Seating target words into a fully
checked grid is much harder than into a British one, and a four-word theme did
not complete within four minutes. Every search parameter in the project was
tuned on 28-entry British grids and needs revisiting for 74-entry ones.

## Barred grids

`--style barred` builds the 12x12 shape used by the Mephisto and the Azed. No
squares are blocked out at all: every one of the 144 cells holds a letter, and
the entries are separated by bars drawn between neighbours.

```bash
python3 make_grid.py --style barred --solution
```

Two things follow from having no blocks. Entries are long — four letters
minimum, averaging closer to seven — and the unchecked letters come from
*single cells*, runs of length one that carry a letter but begin no entry. A
published Mephisto leaves 48 of its 144 cells uncrossed and an Azed 54, a third
of the grid, which is far looser than it looks.

That number is the whole difficulty. Barred patterns are easy to generate and
mostly impossible to fill, and the reason is almost always that they are more
interlocked than a real one. `tools/build_barred_library.py` therefore does not
trust the rules alone: it generates a pattern, validates it, and then tries to
fill it, keeping only the ones that come out. A pattern that can be filled is
filled in about a second; one that cannot burns the entire node budget first,
so the test is decisive as well as cheap.

The library shipped here is 200 such patterns. They are shaped to match the
two published grids on four measures at once — entry count, mean entry length,
unchecked cells, and the share of entries that are only four letters, which
real setters use sparingly (8%) and an unweighted sampler produces constantly
(36%).

They also obey the rule that matters most to a solver: **no entry is more than
a third unchecked.** Both published grids sit exactly on that line, and it is
why the barred rule set rounds its checked-fraction bound *up* where the
British one rounds down — rounding down lets a four-letter answer through with
two of its four letters uncrossed. The two directions are not inconsistent;
they are what two different corpora actually do.

```bash
python3 tools/build_barred_library.py --want 200
```

**Themed barred grids are weak, as themed American ones are.** A fifteen-word
vegetable list seated 5, against 13 that could fit the library's entry lengths
at all, and the fill's familiarity came out at 0.63 where published
answers average 0.86. Long entries in both directions leave little room to
absorb a fixed word, and every search parameter in the project was tuned on
28-entry British grids.

**Barred grids get an HTML page instead of a puzzle file.** Neither ipuz nor
Exolve is given bars by this project, and writing one into them would produce a
well-formed file describing a completely different puzzle — a full square of
white cells with every entry running the whole width. So `--out` writes
`<name>.html`: the grid drawn with its bars, the two clue lists, and the
enumerations. It is a page to work from rather than a file to import.

## Other grid sizes

Jumbo British grids come with the project, extracted from the corpus the same
way the 15x15 library was:

```bash
python3 make_grid.py --library crossword/grids-21.txt --solution
```

`crossword/grids-21.txt` holds 28 patterns from published 21x21 Guardian
cryptics and `crossword/grids-23.txt` holds 5 at 23x23. They are thin — the
corpus has 8,348 puzzles at 15x15 and 37 above it — but they are real
geometry, and a 21x21 fills in about a second. The dictionary is loaded to
whatever length the library needs, so a jumbo's nineteen-letter entries are
available where a 15x15 run stops at fifteen.

Barred grids are not tied to 12x12 either. Build a library at any size, odd or
even, and point the builder at it:

```bash
python3 tools/build_barred_library.py --size 13 --want 40 --out grids-13.txt
python3 make_grid.py --style barred --library grids-13.txt --solution
```

The density floor scales with the grid, so it means the same thing at every
size: 30% of cells uncrossed, which is where the published 12x12s sit — a
Mephisto leaves 48 of its 144 and an Azed 54.

Blocked grids are a different matter. British and American styles take their
patterns from libraries of published puzzles, and those are 15x15 because the
puzzles are. There is a size-parameterised generator in `crossword/generate.py`
that makes blocked patterns from scratch, but it is not wired to `make_grid.py`
and it slows sharply above 9x9 — a 9x9 comes out in a couple of seconds, an
11x11 not at all within a small budget. So non-standard blocked sizes are
possible in principle and not available in practice.

## A bigger dictionary

UKACD's 221,835 entries are not enough, and that is measured rather than
assumed. Filling with only the most familiar 80% of it does measurably worse
than with all of it, and the curve has not flattened at 100% — so more
vocabulary would keep paying, most of all for American grids where every letter
is checked.

`tools/build_wiktionary.py` builds a larger one from a Wiktionary extract:

```bash
python3 tools/build_wiktionary.py kaikki-english.jsonl --out wiktionary.txt
python3 make_grid.py --dictionary wiktionary.txt --file lists/birds.txt
```

Take the input from [kaikki.org](https://kaikki.org), which publishes
Wiktionary already parsed by `wiktextract` as one JSON object per line —
scraping the site page by page would be slow, rude, and would need a wikitext
parser. The builder streams, because the file runs to several gigabytes.

Inflections are kept by default and are most of the value: a plural or a past
tense fills a slot the headword does not. Misspellings, abbreviations, other
languages and affixes are dropped.

Proper nouns are kept, with their capitals, exactly as UKACD keeps its twenty
thousand. `--proper` at fill time is what decides whether they are used, and
the loader does that better than a build-time cut could: a word occurring both
capitalised and not — Kestrel the surname, kestrel the bird — counts as
ordinary fill.

The list is not shipped here. Wiktionary is CC BY-SA, so a derived list carries
that licence; building it locally keeps the question where it belongs, and it
is the same reason UKACD is not in the repository either.

**`--aim` is calibrated against UKACD.** Familiarity is a rank *within* each
length, so a much larger dictionary shifts every rank and 0.85 stops meaning
what it means here. Re-derive it before trusting the fill quality.

## Word squares

A sideline, but the machinery is mostly already here.

```bash
python3 word_square.py 7               # ordinary: rows and columns read alike
python3 word_square.py 6 --kind double # double: rows and columns differ
```

|  | |
|---|---|
| **ordinary** | `PASTERS / ATTABOY / STIRRUP / TARTISH / EBRIATE / ROUSTER / SYPHERS` |
| **double** | `ROSIER / EMUNGE / LENTEN / INTENT / STANCE / HANDED`, reading down `RELISH OMENTA SUNTAN INTEND EGENCE RENTED` |

A double square is a barred grid with no bars — every across run is the full
width, every down run the full height — so the ordinary filler makes one with
nothing added. Sizes up to 6 come out in under a minute; 7 has not been found.

An ordinary square cannot be posed that way at all. It needs
`grid[r][c] == grid[c][r]`, a constraint between two *cells*, where everything
the filler knows how to say is a constraint between a cell and a word. So it
has its own solver in `squares/ordinary.py` — which is the same search in
miniature, over *n* words instead of thirty, each one placed against the
letters the others have already fixed.

Sizes up to 7 are quick. A larger dictionary is worth having only once the
search is hard: at 5x5 and 6x6, Wiktionary is three times *slower* than UKACD
despite exploring fewer nodes, because its bitsets are longer and every
intersection costs more. At 7x7 the node count falls nineteenfold and it is
3.3 times faster.

An 8x8 is where that pays spectacularly: **three and a half hours with UKACD,
114 seconds with Wiktionary** — 177 times fewer nodes. Four of the eight words
in the Wiktionary square do not exist in UKACD at all, which is both the
mechanism and the cost, since two of them are a trilobite larval stage and a
Greenlandic mineral.

With UKACD it takes about 230 million nodes and comes out of ordinary words:

```
C I T E S S E S      python3 word_square.py 8 --tries 3000 I S O T H E R E          --effort 200000 --report 200
T O X A E M I A
E T A E R I O S
S H E R W A N I
S E M I A R I D
E R I O N I T E
S E A S I D E S
```

Different `--seed` values explore disjoint searches, so running several at once
genuinely parallelises the hunt.

## Ninas

A nina is a message hidden in the grid, read somewhere the solver would not
normally read.

**Fixed cells** — `--nina ROW,COL,DIR,LETTERS`, counting from 1:

```bash
python3 make_grid.py --nina "1,1,diagonal,ICARUS" ariadne theseus minotaur
```

`DIR` is `across`, `down`, `diagonal`, `antidiagonal`, `up` or `back`. Repeat
the option for several.

A diagonal is usually the better shape. It crosses entries at single cells and
can hardly help being hidden, whereas a straight run along an edge tends to lie
*along* entries — and a message that is exactly two whole entries is not hidden
at all, it is just those two answers. The tool says which you have:

```
hidden: spans 6 entries, 6 of 6 letters not readable as a whole entry
```

**Along a path** — `--nina-path PATH,LETTERS`, which skips whatever cells are
blocked. This is what a perimeter nina actually is:

```bash
python3 make_grid.py --nina-path "perimeter,DICTIONARIES ARE LIKE WATCHES" \
    --min-score 1.0 --seed 2
```

`PATH` is `perimeter`, `toprow`, `bottomrow`, `leftcol`, `rightcol`, `diagonal`
or `antidiagonal`. A perimeter message must use every white cell on the circuit,
so its length has to match a grid exactly; if it does not, the error lists the
lengths that would work and how many grids take each.

The lengths worth aiming at are those whose grids have **no entry lying along
the edge** — 21 of the 120 grids are like that, and there the message is hidden
by construction and forces no entry to be anything. On a 15x15 those lengths are
26, 24, 28, 16 and 22.

Otherwise you hit the real difficulty of a perimeter nina: the edge cells are
parts of entries, so a message that does not break into words at the entry
boundaries leaves nonsense round the outside. The tool warns rather than passing
it off as clean.

## Pangrams

`--pangram N` requires every letter of the alphabet N times.

An ordinary fill is never a pangram — 25 fills missed 4.2 letters on average,
almost always j, q, x and z — and it is not for want of freedom: disabling the
familiarity preference entirely only reached 3.5. Nothing in the search was ever
*asking* for a z. So words supplying a missing letter get a bonus, escalating
with the requirement — and weighted by how hard that letter is to place, so a Q
outranks a K. Measured over 12 seeds on one grid:

| N | Result | Fill familiarity |
|---|---|---|
| 1 | 12/12 | 0.76 |
| 2 | 12/12 | 0.67 |
| 3 | 10/12 | 0.63 |
| 4+ | allowed, has never succeeded | the obstruction is English, not the search |

Weighting every missing letter equally instead places the easy ones first and
spends the freedom the hard ones needed: a double then completes 7 times in 12
and a triple never.

## How it works

Four nested searches. Each layer only commits when the layer below can actually
deliver, so no grid is ever accepted before words have gone into it.

**1. Vocabulary.** The word list is folded to bare letters, filtered by any
floor or ceiling, and indexed. The index is one bitset per word length: bit *i*
is set if word *i* has letter *c* at position *p*, so matching a pattern is an
AND chain and counting survivors is a single `int.bit_count()`.

**2. Choose a grid.** 8,348 published Guardian 15x15 cryptics use only **130
distinct block patterns** between them, 120 of which pass the rule set — setters
pick from a library rather than inventing grids. Those are scored against your
words by how many could fit on length alone, then by spare capacity, and the
best are tried in turn.

**3. Seat the targets.** Branch and bound over assignments of your words to
slots. Most-constrained word first, ties to the longest, because a fifteen-letter
word has one or two homes and a four-letter word has a dozen. Every placement is
undoable, and the bound — seated plus still-seatable — cuts branches that cannot
beat the best arrangement so far.

**4. Fill the rest.** At each node one candidate mask is computed per empty slot.
That single pass is both the forward check (an empty mask kills the node) and the
ordering heuristic (smallest mask expanded first). Candidates are ordered by
nearness to `--aim` plus Gumbel noise, which is weighted sampling without
replacement, and the best 200 are tried.

If the fill fails, the last-seated target is lifted and it tries again: a grid
holding nine targets that completes beats one holding ten that does not, because
the second is not a crossword.

**Breeding.** After the library has had its turn, the best-fitting grids are
*edited* — flip a cell and its rotational partner, keep the result if the whole
rule set still passes — and hill-climbed towards grids that hold more of your
words. Candidates are scored by actually filling them, not by their shape.

This runs as a fallback, never a merge: the library's own answer is computed
first and kept unless breeding beats it outright.

**Output.** Cell numbering (a cell starting both an across and a down entry
carries one shared number), then `.ipuz` and Exolve, with separators restored so
multi-word answers are enumerated correctly.

## Reading the output

```
placed 7 of 7 targets (100% of the 7 that could fit this library)
fill: 23 words, familiarity rank 0.77 (published answers average 0.86), 1 unknown to both sources (umbratic)
hidden: spans 6 entries, 6 of 6 letters not readable as a whole entry
rules: clean
```

**Coverage is scored against the length-profile ceiling, not against how many
words you gave it.** An arbitrary 20-word list has a mean ceiling of 80% before a
single letter is considered, so coverage over list size would confuse a weak
search with an impossible request.

That ceiling ignores letters entirely, so it flatters dense lists badly. Twenty-eight
prime ministers have a ceiling of 23 but only about 14 are really achievable —
once targets outnumber the ordinary fill, they start crossing *each other*, and
two arbitrary surnames only agree if they happen to share a letter in the right
place. Nothing searches its way out of that.

**Familiarity rank** is where the chosen words sit within the familiarity range
for their own length, so 0.86 is what published answers average. **Unknown to
both sources** means no record as a Guardian answer *and* no general-English
frequency — the words that would embarrass a setter.

## Measuring changes

`BASELINE.md` records what the tool currently scores, the settings those numbers
describe, and the things that were tried and rejected. Update it in the same
commit as any change that moves it.

```bash
python3 tools/run_baseline.py     # about six minutes
python3 -m pytest -q        # 111 tests
```

The benchmark is 44 frozen word lists in `benchmark/lists.json`, stratified by
difficulty rather than only by size. The important stratum is `feasible`: those
words co-occurred in one published puzzle whose grid is in the library, so the
optimum is *known to exist* and any shortfall is the search's fault rather than
an impossible request. Do not regenerate the lists to chase a result — paired
comparison on fixed lists is the whole point.

## Rebuilding the data files

Three files are committed so that ordinary use needs no corpus:
`crossword/grids.txt` (the grid library), `crossword/frequency.txt` (Guardian
answer counts) and `crossword/scores.txt` (combined familiarity).

Rebuilding them needs a corpus of published Guardian crosswords as JSON — the
"guardian-cc" collection, one file per puzzle, about 130 MB — and `wordfreq`:

```bash
python3 tools/build_library.py    path/to/guardian-cc-master/crosswords
python3 tools/build_frequency.py  path/to/guardian-cc-master/crosswords
python3 tools/make_benchmark.py   path/to/guardian-cc-master/crosswords
```

`wordfreq` is a build-time dependency only. Nothing at run time imports it.

## Design notes

**The rule set is checked against real crosswords.** `test_corpus.py` validates
against published puzzles rather than against anyone's opinion of the rules —
which is how a bug that rejected 34% of the Guardian's output was found. The
rule required `ceil(L/2)` checked letters per entry; the real convention rounds
down, and the difference is exactly the `UCUC...U` shape British grids are built
from.

**Familiarity comes from two sources.** Guardian usage alone is a domain
frequency: it ranks `isle` and `stye` absurdly high and gives zero to ordinary
words that simply have not come up. General English alone has never heard of a
phrase, and 42,125 UKACD entries are phrases. The score is the better of the two,
which routes phrases to the corpus for free, since a general corpus scores a
concatenated phrase at zero.

**Grids are held to what gets published.** Grids with more, shorter entries are
genuinely easier to fill, so an unconstrained search walks straight towards them
— 9.9 entries of three or four letters against 3.3 in the library. No scoring
tweak reaches that, because the preference is *correct*; those grids really do
fill. So breeding is constrained to stay inside the range published grids
occupy.

**Negative results are kept.** `mutate.tailor` breeds on the length profile and
is measurably worse than doing nothing. It is retained, tested and off, with the
reason recorded, because a specific negative result is worth not rediscovering.
