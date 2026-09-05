# Baseline

The measured state of the tool, so that a regression shows up as a diff rather
than as a half-remembered number from a commit message. Update this file in
the same commit as any change that moves it, and say why.

Reproduce with `python3 run_baseline.py` (about 6 minutes). It needs only what
is in the repository: `crossword/grids.txt`, `crossword/scores.txt` and
`benchmark/lists.json`. The Guardian corpus is *not* needed — it is required
only to rebuild those files, via `build_library.py` and `build_frequency.py`.

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

Measured over 12 dense lists, 8 seeds each, keeping the best:

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

Generating patterns is easy, unlike blocked ones. Nothing is removed, so there
is no connectivity to keep and no isolated cells to avoid; a pattern is a
partition of each row and column. Two dials, and they are independent, because
a length-1 run is not an entry -- a single cell adds an unch without adding a
light:

    lights per line   entries   unchecked   mean length
    about 1.5              36          14           7.6
    2                      46          16           6.0
    3                      62          14           4.5

The first row is a Mephisto: about 36 entries averaging seven or eight
letters. Sampling uniformly over partitions is not -- it favours many small
parts and gives 60 entries averaging 4.5.

They do not fill: 0 of 6 at the Mephisto shape, 0 of 12 at a looser one, about
a minute each.

The reason is not vocabulary, which was the first guess and was wrong. UKACD
holds 250,378 entries and every slot in a failing grid has thousands of
candidates -- 1,112 at worst, 17,945 at the median. What fails is the search:
60,001 nodes produce 59,986 backtracks, 45,702 of them hitting a slot with
nothing left, and one slot accounts for 10,278 of those on its own. It
rediscovers the same dead end over and over, because backtracking is
chronological and a conflict teaches it nothing.

Restarts, the standard remedy for a thrashing search, do nothing here. The
same 240,000 nodes spent as 4 searches of 60,000 or as 480 of 500 gives 0 of 8
either way. So the failure is not bad luck that a fresh start could avoid.

That leaves two possibilities and they are not yet separated: the search has a
systematic weakness on tight interlock, or these randomly barred patterns are
simply unsatisfiable. The American style faced exactly this question and
answered it with real grids -- randomly built ones filled 0 of 5 while
published ones filled 72 of 72 instantly. The same test needs a published
barred grid, which the project does not have.

Not done: check_symmetry only inspects blocks, so bar symmetry is unenforced
and the work above set symmetry="none".

Still open: the controls stay at 14/16. feas-14-20 improves 12 -> 13 of 14 and
feas-18-30 improves 12 -> 15 of 18, both short of a known-achievable optimum.
