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

Still open: the controls stay at 14/16. feas-14-20 improves 12 -> 13 of 14 and
feas-18-30 improves 12 -> 15 of 18, both short of a known-achievable optimum.
