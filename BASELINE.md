# Baseline

The measured state of the tool, so that a regression shows up as a diff rather
than as a half-remembered number from a commit message. Update this file in
the same commit as any change that moves it, and say why.

Reproduce with `python3 tools/run_baseline.py` (about 6 minutes). It needs only what
is in the repository: `crossword/grids.txt`, `crossword/scores.txt` and
`benchmark/lists.json`. The Guardian corpus is *not* needed — it is required
only to rebuild those files, via `tools/build_library.py` and `tools/build_frequency.py`.

## Configuration these numbers describe

    min_score      0.0     no hard floor on fill-word familiarity
    max_uses       None    no ceiling
    commonness     3.0     soft preference for familiar words
    top            14      library patterns scanned per list
    quality_scan   4       extra patterns tried once coverage tops out
    budget         6000    seating-search nodes
    attempts       3       seating restarts per pattern
    time_limit     45s     per list

## Coverage, over the 44 frozen benchmark lists

    stratum      lists  mean cov   filled  mean ceiling
    feasible        16       97%    16/16          100%
    realistic       16       86%    16/16           99%
    arbitrary        8       81%      8/8           90%
    theme            4      100%      4/4          100%

    size   mean cov   filled
       6       100%    10/10
      10        91%    10/10
      14        88%    10/10
      18        78%    10/10

    controls at known optimum: 14/16
    total runtime: 368s

Coverage is scored against the length-profile ceiling, never against list
size: an arbitrary 20-word list has a mean ceiling of 80% before a letter is
considered, so coverage/N confounds a weak search with an impossible list.

The `feasible` controls are the pass mark. Their words co-occurred in one
published Guardian puzzle whose grid is in the library, so the optimum is
known to exist. The two that fall short are `feas-14-20` (12/14) and
`feas-18-30` (12/18). `feas-14-20` is a search failure, not a library one: its
ideal grid ranks first and the seater still cannot fill it.

## Fill quality

    unknown to both sources    7.8%   (worst grid 21%)
    mean familiarity          2.557   (worst grid 1.97)

"Unknown to both" means no Guardian answer record *and* no general-English
frequency. It is only meaningful with `min_score` at 0; set a floor and it is
0 by construction, and mean familiarity is the measure that still moves.

## Things measured and deliberately not adopted

    top=50            +2pp on size-18 only, 368s -> 606s. Use --patterns 50
                      on a hard list; not worth the default.
    min_score=1.0     fill quality perfect, but controls 14/16 -> 11/16.
                      A hard floor costs real coverage.
    from-scratch grid generation
                      ~1 legal 15x15 pattern per 10-20 draws at ~20s each,
                      in the alternating family. No configuration improved it.
                      Mutating library grids reaches legal neighbours at 0.4s
                      per seed instead.

    tailoring by length profile (mutate.tailor)
                      Raises the ceiling as designed -- arbitrary 90% -> 96% --
                      and places FEWER words: 70 against 79 across the eight
                      lists the library cannot fully seat. Goodhart:
                      best_over_library ranks by (ceiling, spare) and mutants
                      are bred to maximise exactly that, so they outrank the
                      grids that were filling. A better length profile is not
                      a better grid. Superseded by the below; kept because the
                      failure is instructive.

## Tailoring by fill (mutate.best_with_tailoring)

Breeding on the length profile fails. Breeding on words actually seated works.
The profile survives only as a cheap filter that picks which few of a grid's
33 neighbours are worth filling; the fill itself decides what to keep, scoring
(filled, targets seated, fill quality) -- the same order the pattern scan uses.

Time-matched, both arms given 120s per list:

    stratum        library   tailored        size   library   tailored
    feasible           97%        99%           6      100%       100%
    realistic          86%        89%          10       91%        95%
    arbitrary          81%        83%          14       88%        89%
    theme             100%       100%          18       78%        83%

    fill unknown to both      7.8%       5.2%
    mean familiarity         2.557      2.899
    controls                 14/16      14/16
    runtime                   451s      1224s

Coverage and fill quality both improve, because the breeding objective
includes quality. The cost is 2.7x runtime. The library arm at 120s is
identical to the library arm at 45s, so the gain is mutation and not budget.

It runs as a fallback, not a merge: the library's own answer is computed
first and kept unless mutation beats it outright. Breeding can still surface a
grid that outranks a better one -- that is exactly how the profile version
lost ground -- and a fallback makes that impossible.

    capping the size of a move (mutate.neighbours max_change)
                      A flip is coarse: removing one block can merge two
                      seven-letter entries into a fifteen. Measured over 674
                      legal flips, 38% disturb the length histogram by 4 or
                      less and 89% by 6 or less, but 8.3% lengthen the longest
                      entry by four or more. Restricting to gentle moves is
                      worse, monotonically: over ten hard lists, 112 words
                      uncapped, 110 at a cap of 6, 108 at 4, and never better
                      on any single list. The coarse moves are how the search
                      leaves the library's own neighbourhood; gentle ones
                      shuffle within it. The knob is kept and off.

                      Sliding a block one cell along is not the gentler move
                      it looks: it is a removal and an addition at once, so it
                      disturbs more (median 10 against 6) and only 8.4 are
                      legal per grid against 65.5 flips.

## Entry lengths

Two separate pressures push bred grids towards short entries, and both were
found by using the tool rather than by the benchmark, which never looked at
entry lengths at all.

First, `fill_quality` averaged raw familiarity, and familiarity falls steeply
with length -- 2.60 at three letters against 0.40 at fifteen -- so the metric
rewarded grids made of short words while claiming to measure quality. It now
scores each word against the average for its own length.

Second, and larger: a grid with more, shorter entries is genuinely easier to
fill, and `filled` rightly outranks everything else, so breeding walks towards
chopped-up grids. No scoring tweak reaches that, because the preference is
correct -- those grids really do fill. `mutate.within_envelope` is the honest
instrument: bred grids must stay inside the range published ones occupy, at
most 7 entries of three or four letters and at most 32 entries in total, both
the 90th percentile of the library.

    entries of 3-4 letters, per grid          published library   3.3
                                              library pick only   4.2
                                              breeding, before    9.9
                                              after length fix    8.4
                                              after envelope      5.0

    cost of the envelope: 110 words against 112 over the ten hardest lists

## Aiming, rather than maximising

Familiarity was a ramp: more common was always better, so the search climbed
to the most ordinary word available. Checked on the Zipf scale, which is
independent of the Guardian counts and so not circular, that put 43% of the
fill above Zipf 4 where published answers put 17%. Not obscure -- obvious, and
full of the crosswordese --max-uses was invented to suppress.

Real answers sit at the 86th percentile of familiarity *for their own length*,
steady from 0.77 at four letters to 0.93 at fifteen. So `--aim` (default 0.85)
targets that rank instead of the maximum. A rank within the length, not an
absolute band, or long words would be excluded and --long undone.

    distance from the published Zipf distribution
        monotonic   63        aim 0.85   19
        aim 0.75    46        aim 0.90   17
        aim 0.80    32        aim 0.95   22

Free in coverage: against the monotonic version, feasible 99% either way,
realistic 87% to 88%, arbitrary 81% to 82%, controls 14/16 both, unknown fill
5.4% to 5.5%. It also doubles as a difficulty dial -- aim 0.5 gives a fill at
rank 0.52 -- which largely subsumes --max-uses.

## Pangrams

An ordinary fill is never one: 25 fills missed 4.2 letters on average, almost
always j, q, x and z, and turning the familiarity preference off entirely only
reached 3.5. Freedom was never the constraint -- nothing was asking for a z.

### Which missing letter to chase first

The bonus for supplying a missing letter was flat: every letter the grid still
lacked pulled equally hard. That places whichever is convenient, and what is
convenient is the common ones, so the k and the v go in early and the q and the
j are left to a grid that has no room left for them.

Weighting the bonus by how hard a letter is to place -- log of how few words in
the vocabulary carry it, scaled to mean 1, which puts q and j at 2.4 and e at
0.22 -- changes what is achievable rather than merely what it costs. Twelve
seeds on one grid:

    pangram   all equal          rarest first
       x1     12/12   0.78       12/12   0.76
       x2      7/12   0.72       12/12   0.67
       x3      0/12    --        10/12   0.63

A triple goes from impossible to routine. The familiarity it costs is the price
of completing at all: the awkward letters have to go somewhere, and a grid that
fails has no familiarity to report. At a single pangram the two schemes are
level on completions and the weighting costs 0.02, which is the whole of its
downside.

`--pangram N` adds a bonus in Filler._order for each still-missing letter a
word supplies, scaled by `hunger`, and discards a completed fill that falls
short so the next restart tries again.

    requirement   hunger   achieved   fill rank
    none               -      0/16         0.81
    pangram            2     16/16         0.79
    double            10     16/16         0.70
    triple            24      1/8          --

A pangram is close to free, a double costs real fill quality, a triple works
about one attempt in eight at ~14s each. hunger defaults to 3 x the
requirement.

## Speed

Profiled on one ordinary themed run, three changes took it from 6.5s to 1.9s,
about 3.4x, with no change to any result:

  * `Slot.cells` rebuilt its list on every access -- 1.4 million times in a
    single run, because `Grid.pattern` walks it for every candidate word at
    every node. Built once at construction instead.
  * `runs`, `slots` and `checked_cells` depend only on the blocks and were
    recomputed thousands of times; `validate` alone asks ten predicates, most
    of which call `slots()`. Cached against a stamp bumped by add_block and
    remove_block, which are the only mutations outside construction.
  * The seating search asked `_fits(grid.pattern(slot), word)` half a million
    times, joining a fifteen-character string only to compare and discard it.
    Reading the cells directly short-circuits and allocates nothing.

## American grids

`--style us` selects a second library: 2,500 patterns sampled from 48,481
distinct ones across 33 publications, geometry only. The rule set already expressed the
convention -- every letter checked is
`RuleSet(max_consecutive_unchecked=0, min_checked_fraction=1.0)` -- and real
American grids validate against it, 3,091 of 4,451 puzzles passing with only
about 35 rejected in total.

They are shaped quite differently from British grids: 34 blocks against 69,
and 74 entries against 28.

Building grids from scratch does not work and is not needed. A row-by-row
search produced 0 of 3 at every density and row cap tried; local search --
add a symmetric block pair, undo it if it breaks a rule -- produced legal ones
instantly, but they would not fill: 3/5 at 11x11, 1/5 at 13x13, 0/5 at 15x15.
Real grids fill with the same dictionary, so the grids were the problem and
not the word list. Allowing proper nouns made no measurable difference.

How the library is sampled turned out to matter more than anything else about
it. Spreading evenly across block counts over-represented the extremes, and a
16-block grid is not something anyone publishes; that library filled 2/10 at
its sparse end. Real grids cluster hard -- 36 and 38 blocks are 20% and 22% of
the corpus, and 30 to 44 covers 93% -- so a random sample, which is
proportional by construction, looks like American crosswords and an even one
does not. The proportional library fills 20/20 at about 3s each.

That also fixed themed American grids, which had failed to complete in four
minutes: a four-word theme now places 4/4 in about 135s.

What remains is vocabulary rather than search. Fill familiarity runs about
0.63 against the published 0.86, because UKACD is a British list and an
American grid drawn from it reads oddly -- gyve, sasarara, yealm. `--min-score
1.0` removes the unrecognised words at some cost in variety, but an American
word list would serve the style far better.

## Searching harder does not work; searching again does

`--effort` scales the shortlist, the seating budget, the restarts and the
breeding together. Measured on the two lists that have never reached their
known optimum, it is flat at best and monotonically worse at worst:

    list          normal        deep    exhaustive
    feas-14-20    13/14 27s   13/14 72s   13/14 176s
    feas-18-30    16/18 43s   15/18 244s  14/18 469s

Eight ordinary runs at different seeds do better than one long one, in less
time: feas-18-30 gave [16, 15, 14, 13, 16, 16, 16, 16] in 273s against 14/18
in 469s for a single exhaustive run.

Two things follow. The search is randomised and peaks early, so the way to
spend a time budget is more starts rather than longer ones. And both lists
plateau below an optimum that provably exists -- 13/14 and 16/18 -- which no
parameter reaches, so the remaining gap is in the seating search itself and
not in how long it is given.

## How many runs to keep

**At a fixed total budget, this depends entirely on the style**, and the table
below does not control for that: it gave N runs N times the clock, so it
measures a bigger budget as much as a better strategy.

Controlling for it -- one minute spent as a single search or as the best of
several shorter ones, 24 lists, 8 seeds, read off the improvement curves so
every split comes from the same runs:

    one 60s search   x2      x3      x5      x8     seed spread
      British         0.686   0.686   0.686   0.697       0.024
      barred          0.374   0.379   0.383   0.391       0.179
      jumbo           0.674   0.660   0.832   0.836       0.322
      American        0.333   0.333   0.333   0.333       0.359

    (x1: British 0.686, barred 0.349, jumbo 0.632, American 0.333)

The gain from splitting tracks the seed-to-seed spread almost exactly. A
British search is reliable, so there is no tail to catch and one long search is
as good as any split -- which means the original measurement below, taken on
British lists, was reading the extra clock rather than the extra tries. A jumbo
varies hugely and splitting is worth a third more coverage, lifting completion
from 83% to 100%.

American is the exception that proves the rule: its spread is the largest of
all and splitting buys nothing, because its failures are structural rather than
unlucky. No seed completes a twenty-word theme, so there is no lucky one to
find.

The original measurement, over 12 dense British lists, 8 seeds each, keeping
the best -- at N times the budget:

    runs kept   mean coverage   at optimum   unknown fill
            1           88.4%         2/12           4.2%
            2           94.0%         3/12           1.3%
            3           96.5%         4/12           0.8%
            4           96.5%         4/12           0.0%
          5-8           96.5%         4/12           0.0%

Coverage saturates at three runs and fill quality at four; the fifth through
eighth add nothing at all. One run leaves eight points of coverage on the
table, which is far more than any parameter in the project is worth.

The variance is per-list rather than uniform. Some lists give the same answer
every time (`dense-20-01`: 19 eight times over) and some swing wildly
(`dense-20-03`: 14, 12, 20, 20, 20, 20, 20, 15). There is no way to tell which
kind you have without running it more than once, which is the practical
argument for three.

## A harder benchmark tier

`benchmark/lists-hard.json` holds 24 dense lists -- 20, 24 and 28 targets --
all `feasible`, all with a library ceiling equal to their size, so nothing is
capped on lengths and every shortfall is the crossings. The original 44 had
stopped discriminating: most reach their ceiling at any setting, so a change
showed up on two or three lists at most.

What made them easy was size. A 14-word theme sits in a 28-entry grid with
fourteen ordinary entries to absorb the crossings; a 26-word theme leaves
almost none.

## Barred grids

`runs()` splits on bars as well as blocks, which is all the representation
needs: everything downstream reads runs, so checkedness, the rules and the
search are unchanged. Verified against a published Mephisto -- a cell is
unchecked exactly when one of its two runs has length 1, which is the same
rule a blocked grid uses, and bars produce it where neighbouring blocks would.

Generating patterns looked easy at first, and that was wrong twice over.

The first error was arithmetic dressed up as observation. The shape was read
off a picture of a Mephisto -- 36 entries averaging seven or eight letters --
except that the number of unchecked cells was not read off it at all, it was
guessed, at 14. A real Mephisto leaves 48 of its 144 cells uncrossed: a third
of the grid, not a tenth. Every barred pattern the project built was three
times more interlocked than any published one, which is why none of them
filled.

The second error was thinking the two directions were independent. Nothing is
removed from a barred grid, so there is no connectivity to keep, and it is
tempting to conclude that a pattern is just a partition of each row and each
column chosen separately. It is not. A cell whose across run and down run are
both single is in no entry at all, and two unchecked letters may not sit side
by side, so where a row puts its single cells decides where every column may
put its own. Drawing the two separately gives 2% legal patterns, and pushing
for more unchecked cells drives that to zero:

    openness   legal per 400 draws
    1.0        9
    1.5        0
    2.0        0

Sampling the rows and then *searching* for columns that fit them gives 17%,
and reaches the shape of a real grid.

### What settled it

Published grids, which is what the American style needed too. The same filler,
the same UKACD word list, the same rules:

    Mephisto, 12x12, 36 entries, 48 unchecked
    5 of 5 seeds filled, 196 to 1,352 nodes, 0.04 to 0.33 seconds
    Azed,     12x12, 36 entries, 54 unchecked
    5 of 5 seeds filled, 133 to 1,023 nodes, 0.03 to 0.25 seconds

Every entry is a dictionary word and every one of the 144 cells is lettered.
So the search was never the problem, and neither was the vocabulary. Both had
been blamed in turn, and the earlier diagnosis in this file -- that the search
thrashes on tight interlock -- was measuring a grid no setter would print.

### A corpus of one teaches false rules

The Mephisto arrived first and was treated as the form. It has no entry
shorter than five letters, so the minimum was set to five. The Azed has six
four-letter entries, and under that rule they stop being lights: the checking
predicates then report the cells around them as belonging to no entry at all.
Six isolated cells, ten consecutive unches and two entries under the checked
fraction, in a puzzle printed in a national newspaper. A published grid
failing a rule condemns the rule. The minimum is four.

It was also, quietly, half of why nothing filled. At a matched shape, with the
same generator and the same filler, the constant alone is worth a sevenfold
difference in effort:

    minimum entry   44-56 unchecked   filled     median nodes
    5                                 10 of 12          2,049
    4                                 11 of 12            290

### What actually predicts a fill

Six patterns in each band, 20,000-node budget, minimum entry of four:

    unchecked   filled     median nodes   median seconds
    20-27       5 of 6            4,574             2.5
    28-35       5 of 6            3,139             1.1
    36-43       6 of 6            1,179             0.2
    44-51       5 of 6            2,782             0.1
    52-60       6 of 6              216             0.1

Success rate is flat; cost is not, and falls by a factor of twenty across the
range. This corrects the claim made here earlier from a single sweep -- that
legal patterns fill about a quarter of the time whatever their shape. They do
not. That sweep was run at a minimum entry of five and drew almost all of its
patterns from the tight end, so it measured the two errors above rather than
anything about barred grids.

What survives from it is the shape of a failure. Every success came in fast
and every failure spent the entire budget, so a bigger budget rescues almost
nothing, and one fill attempt is a cheap and decisive test of a pattern.

### What the library is for

So barred patterns are earned rather than assumed: `tools/build_barred_library.py`
generates one, checks it against the rules, and admits it only if a real fill
comes out. That cost is paid once, here, so that nothing pays it at build time.

Matching the published shape needed one more dial. Four-letter entries are
legal but they are a garnish: 8% of published entries, against 36% of what an
unweighted sampler produces. Penalising them is what brings the whole profile
onto the published figures together rather than one measure at a time, and
biasing the *number* of runs per line -- the obvious knob -- does not do it,
moving the share only from 36% to 31% while collapsing the yield.

    per 3,000 draws       entries   mean length   unchecked   4-letter share
    short_bias 1.0           42.3          5.71        47.8            36.1%
    short_bias 0.4           39.0          6.18        48.8            19.9%
    short_bias 0.15          37.5          6.44        47.4             8.0%
    Mephisto and Azed        36.0          6.60       48, 54             8.3%

That is fitted to the published shape, not to fill success, so the fill test
remains an independent check on it -- and it costs something, because the
entries are genuinely longer.

### The constraint that actually binds

Neither published grid lets any entry go more than a third uncrossed. Both top
out at exactly 0.33, on a nine and on a six. The rule as written allowed 0.5,
because `min_checked_fraction` rounds down and floor(4 x 2/3) is 2 -- so a
four-letter light passed with two of its letters unchecked, which is barely an
answer. It was not a theoretical hole: 123 of the 200 patterns in the previous
library contained such an entry, and 199 of them had one below two thirds.

The bound has to round *up* here, which is the exact opposite of the finding
for British grids recorded above, and both are right. They are conclusions
about two different corpora: a Guardian 15x15 really does print UCUCUCUCU, and
rounding up rejected 34% of them; a Mephisto really does not print a
four-letter light with two unches. So the rounding travels with the rule set
rather than with the arithmetic. Rounded up at two thirds, the requirement
reproduces every entry in both published grids exactly.

Enforcing it is not a matter of filtering afterwards. Applied as a filter to
the generator as it stood, four thousand draws produced nothing at all: a
pattern that scatters its single cells satisfies "every entry within a third"
essentially never, and both published grids sit exactly on the line, which
means almost every one of their entries is at its allowance. The constraint
has to be carried through the column search instead -- a down entry's unches
are settled by the rows the moment its column is chosen, and an across entry's
are counted as the columns arrive, with the branch cut as soon as one entry is
over. Yield is then about 24 patterns per 15,000 draws, which costs six
seconds of generation and is irrelevant beside the fill attempts.

The library is 200 patterns.

Which way the two directions are biased also matters, and not in the obvious
direction. Rows are drawn towards few runs, because a Mephisto row usually
holds two entries. Columns are drawn uniformly, and biasing them the same way
is measurably worse -- 28% of those patterns filled against 53%, at the
settings in use when it was measured. The rows are drawn freely and the
columns have to fit around them, and a uniform draw supplies single cells
generously, because most ways of cutting a line have many parts.

This is the American answer arrived at from the other end. There, published
grids filled 72 of 72 and random ones 0 of 5, so the library was extracted
from a corpus. Here there are two published grids, so the library is generated
and then filtered by the same test the corpus was implicitly passing.

### Still missing

Neither exporter can write a bar. `to_ipuz` and `to_exolve` refuse a barred
grid rather than emit a full square of white cells with every entry running
the whole width -- a well-formed file describing the wrong puzzle. `--out`
says so and writes nothing; `--solution` prints the grid with its bars drawn.

Themed barred grids are weak, as themed American ones are. A fifteen-word
vegetable list seated 5, against 13 that could fit the library's entry lengths
at all, with the fill at 0.63 familiarity against a published 0.86.

## What the parameter study found

Ten constants, 1,680 screening runs over 70 configurations and four styles,
then a paired comparison on lists screening never saw, then the held-out half.
The design and its priors are in `experiment/DESIGN.md`, written first.

**One constant of the ten was badly set.** `relax` decides how many seated
targets may be lifted, one at a time, when the fill fails. It was 3. Held out:

    relax 3 -> 10        coverage        completed
      British         0.673 -> 0.682    97% -> 100%
      barred          0.276 -> 0.367    50% ->  94%
      jumbo           0.759 -> 0.777    94% -> 100%
      American        0.142 -> 0.222    17% ->  36%

It costs nothing anywhere and rescues two styles, so the default is now 10.

**The pre-registered metric was wrong, and `relax` is what exposed it.** The
ordering put coverage first and completion second. But lifting fewer targets
seats more of them while completing far less often -- at `relax 0`, barred
grids seated 0.661 of the ceiling and produced a finished grid one time in ten.
Scored by the ordering as written, that wins. Counting targets seated in a run
that never filled is counting nothing, so coverage is now zero unless the grid
completed.

**Nothing else moved much, and that is mostly the clock.** At a fixed time
budget most of these constants are zero-sum: `attempts`, `top`, `budget` and
`node_scale` all spend the same seconds differently. The ones that showed an
effect are the ones that *waste* time rather than trade it -- `attempts` is
better at 1 than at any larger value, at every budget from 2 to 20 seconds, and
the gap narrows rather than crossing.

**A prior of mine was refuted outright.** `budget` and `node_scale` were
expected to be mis-scaled for American grids, which carry 74 entries against a
British 28. They are not, and neither is anything else: American completion
sits at 29-33% for every value of all ten parameters, because the failure is a
cliff rather than a gradient.

    American, completed    8 words: 97%    20 words: 0%    60 words: 0%

Twenty fixed words among 74 fully checked entries appears to be structurally
unfillable, which no constant is going to fix.

## Vocabulary has not saturated

Whether a larger dictionary would help was settled by taking words away from
the end a larger one would add them at: fill using only the most familiar X% of
each length, and see whether the curve is still climbing at 100%.

    most familiar        20%     40%     60%     80%    100%
    words available   45,514  91,033 136,555 182,074 227,601
      British          0.605   0.642   0.651   0.669   0.686
      barred           0.033   0.148   0.237   0.300   0.293
      jumbo            0.619   0.668   0.731   0.805   0.714
      American         0.052   0.094   0.188   0.156   0.271

Every style gains enormously over the range as a whole. Whether the gain is
still coming at the top differs, and the last step is the one that says what
another dictionary would buy:

    80% -> 100%    British +0.017   barred -0.006   jumbo -0.091   American +0.115

British is still climbing slowly and American steeply. Barred and jumbo are
flat or down, though at two seeds a fall of that size is not distinguishable
from noise, and the jumbo figure moves about more than the others because a
21x21 has few enough patterns that one awkward grid shifts the mean.

So a larger dictionary is worth having, and worth most where the grid is
hardest -- which is the opposite of an earlier claim in this file, that
vocabulary was not the constraint. That claim rested on counting candidates per
slot at the *root* of the search, before any letters are committed, when
failures happen deep in it where a slot has five or six letters already fixed
by crossings. Root counts say nothing about that.

## Word squares

A double word square -- rows and columns all words, all different -- is a
barred grid with no bars, so the filler needs nothing added. Four by four and
five by five come out in well under a second, six by six in about forty.

Phrases have to be excluded. UKACD normalises punctuation away, so "it'll"
arrives as ITLL and "ro-ros" as ROROS, and the first 4x4 produced had ITLL down
its third column. A crossword hides that problem, because such entries are rare
enough to catch by eye; a word square does not, because a third of the answers
are columns nobody chose.

Restarts work here, which is worth recording because they did nothing at all
for barred grids. The search is heavily tailed: the try that succeeds does so
in a few thousand nodes and the ones that do not never will.

    6x6      tries   budget each   time to a square
             6             200,000            209 s
            60               8,000             39 s

Seven by seven was not found, and not for want of restarting. The same three
million nodes, split four ways:

    budget per try   tries   result   seconds
           600,000       5   nothing      306
           120,000      25   nothing      312
            30,000     100   nothing      330
             5,000     600   nothing      342

Flat across a 120-fold change in granularity, and flat in time as well, so
there is no tail to catch and no lucky start to find. Vocabulary is not the
constraint either: there are more seven-letter words than six-letter ones,
23,778 against 16,726.

That leaves the search itself, and the suspect is the one identified for barred
grids and never acted on -- backtracking is chronological, so a conflict
teaches it nothing and it rediscovers the same dead end indefinitely. Fourteen
mutually crossing entries is where that costs most. Conflict-directed
backjumping is the obvious next thing to try, and it would be the first change
to the search rather than to what is handed to it.

### The ordinary symmetric square

A different problem, and it needs a solver of its own: grid[r][c] ==
grid[c][r] is a relation between two cells, where every constraint the filler
knows is between a cell and a word.

The symmetry that makes it inexpressible makes it small. Only the upper
triangle is free, so a square of order n is n words rather than 2n, and placing
a row also places the matching column, which hands one letter to every row
still open.

That last part is what decides whether it works. Filling strictly top to
bottom -- which the structure invites, since row i arrives with its first i
letters already fixed -- checks only the row being placed:

    order of placement     5x5      6x6      7x7
    top to bottom          531    2,403    1.6M, none found
    fewest candidates       20      109      38,524

Doing what the filler does instead -- one pass per node over the rows not yet
placed, pruning when any has nothing left and taking the one with least freedom
next -- is worth two orders of magnitude at 6x6 and the difference between
finding a 7x7 and not.

### What a larger dictionary is worth here

Wiktionary against UKACD, ten disjoint seeds at each size, all twenty found:

    size   words UKACD -> Wiktionary   nodes            seconds
      3     1,096 ->  1,957                3 ->     3   0.00 -> 0.00
      4     4,501 ->  8,310                6 ->     4   0.00 -> 0.01
      5     9,837 -> 21,009               17 ->    10   0.01 -> 0.03
      6    16,726 -> 40,055              176 ->   128   0.03 -> 0.10
      7    23,778 -> 64,308           45,276 -> 2,344   1.15 -> 0.35

More vocabulary always cuts the nodes, because a node dies when a row has no
candidate and more words mean fewer such rows. But it costs time per node: the
bitsets are three times longer, so every intersection is dearer, and building
the index takes five seconds against one.

Below 7x7 the search is too easy for that to pay, and the bigger dictionary is
three times *slower* despite doing less work. At 7x7 the node count collapses
by a factor of nineteen and the cost per node stops mattering: 3.3 times
faster. The crossover is where the search becomes hard enough that avoiding
dead ends is worth more than cheap arithmetic.

### Eight by eight, and what the dictionary does to it

    C I T E S S E S      UKACD, 229,685,776 nodes, 11,459 seconds
    I S O T H E R E
    T O X A E M I A      M E R A S P I S    Wiktionary, 1,297,229
    E T A E R I O S      E Y E S A L V E    nodes, 114 seconds
    S H E R W A N I      R E A T T A I N
    S E M I A R I D      A S T R I N G E    177x fewer nodes
    E R I O N I T E      S A T I N E T S    100x faster
    S E A S I D E S      P L A N E T I C
                         I V I G T I T E
                         S E N E S C E D

Four of the eight Wiktionary words -- MERASPIS, EYESALVE, IVIGTITE, SENESCED --
are not in UKACD at all, which is the whole mechanism: a row dies when it has
no candidate, and those four are candidates UKACD could not offer.

It is also the cost. A trilobite larval stage and a Greenlandic mineral are not
words a solver would thank anyone for. The larger dictionary buys feasibility
and spends familiarity, and at this size there is no choice about it -- but in
a crossword, where the fill is meant to be readable, that trade is exactly what
`--aim` exists to manage, and `--aim` is calibrated against UKACD.

Sizes 3 to 7 come out in seconds. Eight takes about 230 million nodes with
UKACD, which is three and a half hours:

    C I T E S S E S      1,149 tries of 200,000 nodes
    I S O T H E R E      229,685,776 nodes, 11,459 seconds
    T O X A E M I A
    E T A E R I O S      no proper nouns, no phrases: all eight
    S H E R W A N I      are ordinary UKACD entries
    S E M I A R I D
    E R I O N I T E
    S E A S I D E S

Earlier runs at 36 million nodes found nothing, which was not evidence of
much: the answer sits six times further out than that.

Three runs launched at seeds 1, 2 and 3 to search in parallel all returned this
same square, within a couple of minutes of each other, at tries 1149, 1148 and
1147. That is not luck, it is a bug: the seed for an attempt was `seed +
attempt`, so consecutive base seeds overlap in all but a try or two and all
three reached absolute seed 1149. Parallel runs did the same work three times.
The stride is now a large prime, so different base seeds explore disjoint
streams.

Widening the search at each node does not help either. At a fixed budget of
25 tries of 200,000 nodes, raising the cap on candidates per node from 200 to
5,000 spends the same nodes and finds the same nothing:

    candidates per node    200    1,000    5,000
    result                none     none     none

So the shape of the search is not what is missing, at these budgets. None of
this proves no 8x8 square exists in this dictionary -- a run that finds nothing
has not shown there was nothing to find -- only that it is not within easy
reach of this method.

## How much the size of the theme list matters

A great deal, and with sharply diminishing returns. Lists were drawn at random
from the 50,339 reasonably familiar words of 4 to 11 letters, three lists at
each size, 30 seconds per run:

    British, about 29 entries per grid
      list size   seated   as % of the grid   completed
            8        7.7         26%             3/3
           32       12.7         44%             3/3
          128       15.7         54%             3/3
          512       18.0         62%             3/3

Sixty-four times the list buys 2.3 times the themed entries. The growth is
roughly logarithmic, which is what a bound of this shape should look like: the
list stops being the constraint quite early, and what limits the grid after
that is how its entries cross each other. Eighteen of 29 is close to the
practical ceiling for a British grid, because the remaining entries are the
ones pinned by several crossings at once.

So a list of 500 is worth having over a list of 30 -- 18 entries against about
12 -- but it will not fill a grid with the theme, and the second five hundred
would add very little.

Style changes the answer more than size does:

    barred, about 37 entries per grid
            8        5.5         15%             2/3
           32        6.0         16%             1/3
          128       10.0         27%             1/3
          512       10.0         27%             1/3

    American, about 77 entries per grid
          every size                              0/3

Barred grids take a theme but less of one, and complete unreliably: their
entries are long and cross each other along their whole length, so a fixed word
constrains far more than it does in a British grid. American grids seated
nothing at all at this budget, at any list size, which is the same wall themed
American grids have hit throughout -- 74 fully checked entries, and every
search parameter here tuned on 28-entry British ones. The 30-second limit is
part of that: it is not evidence that a longer run would fail, only that this
one does.

## Crosswords that read the same upside down

Not the pattern, which is symmetric by convention already, but the letters:
`grid[r][c] == grid[n-1-r][n-1-c]`. Entries pair off under the turn and each
pair holds a word and its reverse, so every free entry needs its reverse to be
a word as well.

That is the whole difficulty, and it is a vocabulary difficulty before it is a
search one. Wiktionary holds 1,137,086 entries and 3,469 reversible ones, and
they thin out fast with length:

    letters      3    4    5    6   7   8  9  10
    usable pairs 395  547  409  172  36  7  1   0

British entries run longer, so fewer British grids survive that table -- 13 of
the 120 -- against 396 of the 2,500 American ones, whose threes to sixes sit
where the stock is deepest. Fewer is not none, and the reason is worth having:
a long entry needs no reversible partner when it is its own reverse. The
British grid below carries DELEVELED, nine letters, drawn from a stock holding
one reversible nine-letter pair.

The first complete one, from `python3 palindrome.py --repeats`:

    S N A M █ S S E S █ █ E S S E      DESSERTS / STRESSED
    A I T U █ P A C S █ S N O A K      LIVE / EVIL
    A D A T █ O D A S █ I R O R I      GUNS / SNUG
    S A M A R O I D █ T R O P E D      DEPORT / TROPED
    █ █ █ G U N S █ L A A B █ █ █
    S A L E T S █ D E S S E R T S      78 entries, all in the dictionary
    T R A N S █ L I V E █ R E E T      60 of them scored, median 1.80
    O R C █ █ R E X E R █ █ C R O
    T E E R █ E V I L █ S N A R T
    S T R E S S E D █ S T E L A S
    █ █ █ B A A L █ S N U G █ █ █
    D E P O R T █ D I O R A M A S
    I R O R I █ S A D O █ T A D A
    K A O N S █ S C A P █ U T I A
    E S S E █ █ S E S S █ M A N S

And a British one, from `python3 palindrome.py --style british --repeats`,
found in 103 nodes -- 28 entries, all of them words:

    █ D █ S █ █ █ D █ R █ D █ D █      DESSERT / TRESSED
    D E T H S █ D E L E V E L E D      REWARDER / REDRAWER
    █ L █ A █ T █ S █ W █ N █ K █      SHABIHAS / SAHIBAHS
    R E D D E R █ S H A B I H A S
    █ V █ D █ O █ E █ R █ E █ N █      DELEVELED, REDDER and
    R E W A R D E R █ D A R G █ █      SHADDAHS are their own
    █ L █ H █ █ █ T █ E █ █ █ D █      reverses, which is how a
    D E S S E R T █ T R E S S E D      nine-letter entry survives
    █ D █ █ █ E █ T █ █ █ H █ L █      a stock with one reversible
    █ █ G R A D █ R E D R A W E R      nine-letter pair in it
    █ N █ E █ R █ E █ O █ D █ V █
    S A H I B A H S █ R E D D E R      only 19 of the 28 are
    █ K █ N █ W █ S █ T █ A █ L █      distinct, which is the cost
    D E L E V E L E D █ S H T E D      of allowing the repeat
    █ D █ D █ R █ D █ █ █ S █ D █

Distinctness is the sharp lever. A palindrome placed in a *paired* entry
writes itself into both halves, so one answer appears twice -- ESSE and IRORI
each do, above. Forbidding it is right for a puzzle and expensive for the
search:

    common words, repeats allowed     found on attempt 25
    common words, all entries distinct   nothing in 1,584 attempts
    proper nouns, all entries distinct   found on attempt 2

and the middle row is not a matter of effort. Over the top thirty grids at
400,000 nodes each, the median attempt died after **110** nodes and only one
of a hundred and twenty reached its budget: the grids are being proved
unfillable, not abandoned. Doubling the stock with proper nouns finds one in
five seconds, and it is markedly worse to read -- NAGRAD, SAREPOL, KAMANIS.

### Barred grids take it much further

The same solver, unchanged: a barred grid pairs its entries under the turn
exactly as a blocked one does. What differs is that a bar may fall anywhere,
so the pattern can be shaped to the vocabulary instead of the other way about
-- and the vocabulary is the whole difficulty here.

That turns out to matter more than any amount of search. With **every answer
distinct**, which the blocked grids could not manage at all:

    3x3 .. 10x10   instantly, first feasible pattern
    11x11          3 seconds, 524 patterns drawn
    12x12          176 seconds, 1,802 patterns drawn

12x12 is Mephisto size. 46 entries, all in the dictionary, all 46 distinct:

    S T R A T S | S L E E T S      STRATS / STARTS
    U|E|E R E S | R E C C E|P      SLEETS / STEELS
    S E M E M E | E V I L E R      SEMEME / EMEMES
    S T A P E S | S A L A M I      EVILER / RELIVE
    E|S N O R E S | N O N E T      STAPES / SEPATS
    D E E D E R|O|S|P|T|R|S        SALAMI / IMALAS
    S|R|T|P|S|O|R E D E E D        SNORES / SERONS
    T E N O N|S E R O N S|E        NONET / TENON
    I M A L A S | S E P A T S      DEEDER / REDEED
    R E L I V E | E M E M E S
    P|E C C E R | S E R E|E|U
    S T E E L S | S T A R T S

So the ordering is the opposite of the intuition. A barred grid looks harder
-- two thirds of its cells are checked against one half of a blocked grid's --
and it is far easier, because the constraint that binds is which words have
reverses, and a barred pattern can be drawn to suit them.
