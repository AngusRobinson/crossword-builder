# Parameter study: design

Written before the run, so that a surprise cannot be retold afterwards as a
prediction. Results go in `FINDINGS.md`, which is generated from the data.

## The question

Every constant in this project was tuned on British 15x15 grids. Three other
styles have since inherited them wholesale: barred 12x12, jumbo 21x21, and
American 15x15. Two things are being asked.

1. Which of those constants actually move anything?
2. Does the answer differ by style?

The second is the one worth the compute. A British grid carries about 30
entries, a jumbo about 55 and an American one about 75, so any constant scaled
to a grid's size is a candidate for being wrong everywhere but where it was
set.

## Data, and why the old benchmark cannot be used

`benchmark/lists.json` has been tuned against throughout this project's
history — `--tries 3`, `aim 0.85` and the effort presets were all chosen using
it. A setting that suits it may only suit it, so it cannot serve as a held-out
set. It stays as a legacy regression check, looked at once at the end, to catch
anything that wins on new lists while breaking old ones.

`experiment/lists.json` is fresh: 96 lists, drawn per style so that entry
lengths match what the style can hold, at three sizes (8, 20 and 60 words).
The tune/hold split is fixed in that file and was made before any run. **The
held-out half is not to be looked at until a finding is otherwise settled.**

Screening uses 24 of the 48 tune lists — two per (style, size) — because it
wants many configurations more than it wants many lists each. The remaining 24
are for the focused comparison in phase two, so that stage is not scored on the
lists that suggested it.

## Method

**Random configurations, not one at a time.** Random search finds the few
parameters that matter far more cheaply than a grid, and unlike varying one
factor at a time it can see interactions.

**Identical work.** Every configuration runs the same 24 lists at the same
seed, so any two are compared on the same problems. Configuration 0 is today's
defaults and is the baseline.

**Time is measured, not fixed.** `time_limit` does nothing in
`best_over_library` except stop the loop, so a long run passes through exactly
the states a short one would. Recording each improvement as it happens gives
the result at every smaller budget from one run, exactly rather than by
estimate. That is how "what does more time buy" gets answered without running
each setting at four budgets.

The fill now takes a wall-clock deadline as well as a node budget, because the
two are not the same: cost per node varies by two orders of magnitude with the
grid, and American runs were taking 68 seconds inside a 20-second budget.
Without that, a comparison at equal wall-clock was not one.

## Metrics, in this order

1. **Coverage** — targets seated as a fraction of the achievable ceiling.
2. **Completion** — whether a full grid came out at all.
3. **Familiarity** — how ordinary the fill is.
4. **Time.**

The order is fixed here so that a disappointing result cannot be rescued by
promoting a metric it happened to improve. Completion outranks familiarity: an
elegant grid that is not a crossword is worth nothing.

## Priors

| parameter | expectation |
|---|---|
| `commonness` | saturates past 3; little effect on coverage |
| `aim` | no effect on coverage, large effect on familiarity |
| `top` | more patterns helps the big grids most |
| `quality_scan` | little on coverage, some on familiarity |
| `attempts` | helps dense lists |
| `budget` | mis-scaled for US and jumbo |
| `relax` | helps dense lists only |
| `branch_cap` | no effect; it made none at 8x8 |
| `fill_restarts` | small, mostly where fills fail |
| `node_scale` | the other candidate for being mis-scaled by style |

## Adoption rules

A change is adopted only if it:

- survives the held-out lists at a similar effect size;
- does not worsen any metric above it in the ordering;
- and, if it helps one style only, is adopted **for that style**, not globally.

Screening does not settle a value. It says where to look.

## Known limitations

- One seed per (configuration, list). Seed variance is large, so screening sees
  parameter effects only through that noise; phase two adds seeds.
- The wall-clock deadline is checked between nodes and between seating
  attempts, so a run can still overshoot by a few seconds.
- `share`, the split between the library and breeding arms, is not screened
  here: breeding is now skipped when it cannot help, so the split only applies
  to a subset of lists and needs its own comparison.

---

## Amendment, 2026-09-07: the metric ordering above is wrong

Recorded here rather than edited into the text above, because the whole point
of writing the design first is that it can be shown to have been wrong.

The ordering put coverage first and completion second. `relax` shows why that
cannot stand. It lifts the most recently seated target when a fill fails, so
raising it seats fewer targets and completes far more often. On barred grids:

    relax   targets seated   grids completed
      0          0.661             10%
      3          0.543             37%
     10          0.316            100%

Read by the ordering as written, `relax = 0` is best. But nine in ten of those
runs produced no grid at all, and a grid that does not fill is not a crossword
whatever it notionally holds. Counting seated targets in a run that failed is
counting nothing.

**Coverage is therefore scored zero unless the grid completed**, which folds
completion into the primary metric rather than ranking it second. The remaining
order is: effective coverage, then familiarity, then time.

This changes which parameters look important. Under the old measure `relax` and
`branch_cap` led; under the corrected one `relax` leads by more, and several
apparent effects were runs being scored for work they had thrown away.
