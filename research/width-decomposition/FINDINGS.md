# Whose intervals are too wide? The 50/50 ensemble's spread, split by member

Build 3 of the 2026-08-21 handoff (section 5). No refits, no new WIS numbers:
the shipped forecast is an equal-weight quantile average of the per-state
PF-SIHRS filter and the calendar analogue, quantile averaging is linear, and so
every interval width is exactly the arithmetic mean of the two member widths:

```
q_ens(tau) = 0.5 q_pf(tau) + 0.5 q_an(tau)   =>   w_ens = 0.5 w_pf + 0.5 w_an
```

The script asserts that identity on every cell rather than assuming it.

Source: `app/state/retro_seal`, 85 as-of weeks across three seasons, PF samples
re-quantiled with `app.core.ensemble.member_quantiles_from_samples` and the
analogue's stored quantile dicts. **16,775 cells**, the same count as the WIS
decomposition in `research/wis-decomposition/FINDINGS.md`, under the same
filters (truth present and positive, member median positive). Dropped: 330 with
no truth, 372 missing a member or a level, 203 with a non-positive median.

Reproduce:

```
./.venv/bin/python research/width-decomposition/decompose_width.py
```

## 0. The phase rule, stated explicitly

Phase is computed **only** from the truth vintage dated the same as-of as the
forecast (`app.core.data.vintage_path`). Nothing in it uses the eventual peak
date, the eventual season shape, or any later vintage. For state *s* at as-of
*T*, using the current season only (season starts August 1, the `RunSpec`
convention):

- `g` = OLS slope of `log(y+1)` on the week index over the **last 4 observed
  weeks ending at T** -- mean weekly log-growth at the forecast origin.
- `p` = `y_T /` the season's running maximum so far.
- `a` = `y_T /` the state's maximum weekly admissions in **prior** seasons
  (present in the same vintage file, settled long before *T*).

| phase | rule |
| --- | --- |
| **rising** | `g > +0.10` |
| **falling** | `g < -0.10` |
| **near-peak** | `abs(g) <= 0.10` **and** `p >= 0.50` **and** `a >= 0.20` |
| **low-flat** | `abs(g) <= 0.10` otherwise |

The `a` guard is load-bearing. Without it a flat three-admissions-a-week
September is filed as "near-peak" because its own running maximum is also
three; with it, the near-peak bucket lands where it should -- Jan-Mar 2024,
Jan-Feb 2025, Jan-Feb 2026 -- and September 2023 contributes zero near-peak
cells instead of 35.

One honest caveat: `y_T` is the as-of last point, which is under-reported at
first issue in 40-60% of 2024-25 and 2025-26 cells (handoff section 4). The
4-week OLS window damps that relative to an endpoint difference, but the rule
inherits a mild bias toward "falling". That bias is the forecaster's too -- it
is what the models saw -- so the labels describe the real decision problem.

## 1. Headline: by horizon

Relative width is the median of `interval width / observed value`, so states
that differ by orders of magnitude in size count equally. Nominal coverage is
0.50 and 0.90.

| h | cells | W50 PF | W50 analogue | W50 ens | cov50 PF | cov50 analogue | cov50 ens | W90 PF | W90 analogue | W90 ens | cov90 PF | cov90 analogue | cov90 ens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4,257 | 0.612 | 0.490 | 0.555 | **0.597** | 0.468 | 0.572 | 1.691 | 1.595 | 1.656 | 0.933 | 0.872 | 0.928 |
| 2 | 4,230 | 0.835 | 0.722 | 0.804 | 0.554 | 0.431 | 0.545 | 2.586 | 2.331 | 2.562 | 0.917 | 0.836 | 0.923 |
| 3 | 4,188 | 1.075 | 0.964 | 1.069 | 0.552 | 0.403 | 0.535 | 3.706 | 3.062 | 3.558 | 0.918 | 0.819 | 0.923 |
| 4 | 4,100 | 1.310 | 1.218 | 1.317 | 0.550 | 0.381 | 0.540 | 4.816 | 4.040 | 4.714 | 0.930 | 0.790 | 0.928 |
| **pooled** | **16,775** | **0.862** | **0.716** | **0.830** | **0.563** | **0.421** | **0.548** | **2.765** | **2.325** | **2.667** | **0.924** | **0.830** | **0.926** |

Mean absolute widths, in admissions, against a mean observed level of 215:

| h | w50 PF | w50 analogue | w50 ens | w90 PF | w90 analogue | w90 ens |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 128.3 | 97.3 | 112.8 | 355.6 | 310.2 | 332.9 |
| 2 | 182.1 | 138.3 | 160.2 | 546.1 | 444.7 | 495.4 |
| 3 | 229.6 | 177.5 | 203.5 | 733.4 | 562.0 | 647.7 |
| 4 | 260.1 | 210.3 | 235.2 | 865.7 | 720.8 | 793.2 |
| **pooled** | **199.4** | **155.3** | **177.3** | **622.6** | **507.3** | **565.0** |

Volume-weighted (`sum widths / sum observed`, big states dominating): PF
0.925 / 2.890, analogue 0.721 / 2.354, ensemble 0.823 / 2.622 at the 50% / 90%
levels. Same ordering.

**The PF is the wider member at every horizon and at both levels, and it is
the only member that over-covers.** The analogue is the opposite defect: it is
*narrower* than nominal everywhere (cov50 0.421, cov90 0.830) and gets worse
with horizon (cov50 0.468 at h=1 down to 0.381 at h=4), because its width grows
with horizon more slowly than the error does. PF contributes 53.6% of the
pooled ensemble width -- close to half, which is what an equal-weight average
of a wide member and a narrow one produces.

This is the analogue's own docstring claim confirmed on the sealed retro from
the other direction: the analogue is not *worse* on dispersion in the sense of
being too wide, it is worse in the sense of being **under-dispersed**, and the
PF's over-width is what the ensemble is buying to fix that.

## 2. By phase -- this is where the answer lives

| phase | cells | W50 PF | W50 an | W50 ens | cov50 PF | cov50 an | cov50 ens | W90 PF | W90 an | W90 ens | cov90 PF | cov90 an | cov90 ens | PF share of width |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rising | 5,623 | **1.125** | **0.554** | 0.887 | 0.571 | **0.345** | 0.534 | 3.608 | 1.672 | 2.826 | 0.941 | 0.760 | 0.935 | **0.647** |
| near-peak | 1,320 | 0.938 | 0.712 | 0.858 | **0.703** | 0.398 | **0.606** | 2.973 | 2.396 | 2.782 | **0.977** | 0.879 | **0.973** | 0.548 |
| falling | 7,100 | 0.657 | 0.779 | 0.732 | 0.513 | 0.464 | 0.534 | 2.016 | 2.518 | 2.324 | 0.890 | 0.858 | 0.906 | 0.466 |
| low-flat | 2,732 | 1.054 | 0.865 | 0.985 | 0.609 | 0.477 | 0.587 | 3.641 | 2.884 | 3.338 | 0.954 | 0.877 | 0.937 | 0.556 |

Analogue-to-PF width ratio, and the share of cells where the analogue is the
wider member:

| phase | median w50 an / w50 PF | median w90 an / w90 PF | share of cells analogue wider |
| --- | --- | --- | --- |
| rising | **0.546** | 0.510 | 0.139 |
| near-peak | 0.826 | 0.897 | 0.286 |
| falling | **1.144** | 1.234 | 0.647 |
| low-flat | 0.800 | 0.805 | 0.261 |

Three things fall out.

1. **On rising weeks the PF is roughly twice the analogue's width** (ratio
   0.546), and it still only reaches cov50 0.571 -- the errors on a rise are
   genuinely large. The analogue on those same cells covers 0.345, badly
   under-nominal. Neither member is right, and they are wrong in opposite
   directions; the equal-weight average lands at 0.534, close to nominal. The
   50/50 blend is doing real work here that neither member does alone.
2. **On falling weeks the ordering reverses**: the analogue is the wider
   member (ratio 1.144, wider on 65% of cells) and the PF is very nearly
   calibrated on its own (cov50 0.513). Whatever the ensemble's over-width is,
   the falling phase is not where the PF causes it.
3. **The near-peak bucket is the one place where over-width is unambiguous and
   belongs to the PF.** cov50 0.703 against a nominal 0.50 -- twenty points of
   excess, the largest anywhere -- and cov90 0.977. The ensemble inherits it:
   cov50 0.606, cov90 0.973.

Per horizon, at the 50% level, the near-peak excess is not a horizon-1
artefact; it is flat across the whole horizon range:

| phase | cov50 PF h1 | h2 | h3 | h4 | cov50 ens h1 | h2 | h3 | h4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rising | 0.645 | 0.543 | 0.538 | 0.558 | 0.576 | 0.517 | 0.511 | 0.531 |
| near-peak | **0.727** | **0.697** | **0.706** | **0.682** | 0.679 | 0.621 | 0.585 | 0.539 |
| falling | 0.534 | 0.512 | 0.507 | 0.498 | 0.552 | 0.538 | 0.520 | 0.526 |
| low-flat | 0.602 | 0.616 | 0.620 | 0.600 | 0.567 | 0.587 | 0.601 | 0.593 |

Note the analogue's relative width barely grows with horizon on rising weeks
(0.440 -> 0.695, a factor of 1.6 from h=1 to h=4) while the PF's grows by 2.2x
(0.746 -> 1.625). That flatness is the mechanical cause of the analogue's
h=4 cov50 of 0.295 in the rising phase.

## 3. Answering the handoff's question

> is the documented over-width PF, analogue, or both, and does it concentrate
> at turns

**It is the PF, and only the PF.** The analogue is under-dispersed at every
horizon and in three of the four phases; there is no reading of these numbers
in which the analogue is too wide overall. The documented "50% intervals cover
55-60%" defect is the PF's (cov50 0.563 pooled, 0.597 at h=1), and the ensemble
inherits about half of it by construction.

**It concentrates at flat-and-high weeks, which is one kind of turn but not the
other.** PF cov50 by phase runs 0.703 near-peak, 0.609 low-flat, 0.571 rising,
0.513 falling. The near-peak bucket carries the excess. But the two turns the
handoff names behave in **opposite** directions, and that is the more important
finding:

| window | cells | W50 PF | W50 an | W50 ens | cov50 PF | cov50 an | cov50 ens | cov90 ens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Feb-2024 plateau** | 832 | 0.900 | 0.759 | 0.838 | 0.727 | 0.692 | **0.743** | 0.982 |
| **Jan-2025 peak** | 416 | 0.485 | 0.305 | 0.402 | 0.317 | 0.180 | **0.236** | 0.755 |
| near-peak, all seasons | 1,320 | 0.938 | 0.712 | 0.858 | 0.703 | 0.398 | 0.606 | 0.973 |
| everything else | 14,579 | 0.867 | 0.727 | 0.840 | 0.551 | 0.418 | 0.543 | 0.924 |

The Feb-2024 plateau is a **too-wide** event for both members at once
(ensemble cov50 0.743, cov90 0.982). The Jan-2025 peak is a **too-narrow**
event for both members at once (ensemble cov50 0.236, cov90 0.755 -- barely
more than half the nominal 50% rate). Same phase labels, opposite failure.
Broken out:

```
2024-02              cells  cov50  cov90  W50pf  W50an  W50ens
  falling              320  0.741  0.978  0.702  0.777   0.764
  low-flat             164  0.744  0.988  0.921  0.764   0.857
  near-peak            256  0.781  0.988  0.976  0.697   0.830
  rising                92  0.641  0.967  1.835  0.926   1.409

2025-01              cells  cov50  cov90  W50pf  W50an  W50ens
  falling               72  0.083  0.528  0.257  0.306   0.286
  near-peak            116  0.336  0.905  0.534  0.377   0.444
  rising               228  0.232  0.750  0.538  0.274   0.410
```

`near-peak` covers 0.781 in Feb-2024 and 0.336 in Jan-2025. `falling` covers
0.741 and 0.083. The label does not carry the information.

## 4. What does carry the information: the week, not the phase

Coverage moves as a block across the whole 50-state grid within a given as-of
week:

| as-of | cells | cov50 ens | cov90 ens | W50 ens |
| --- | --- | --- | --- | --- |
| 2024-01-06 | 208 | 0.808 | 0.995 | 1.017 |
| 2024-02-17 | 208 | 0.764 | 0.986 | 0.943 |
| 2024-12-14 | 204 | 0.279 | 0.887 | 0.507 |
| 2024-12-21 | 208 | 0.284 | 0.837 | 0.472 |
| 2025-01-11 | 208 | 0.236 | 0.721 | 0.412 |
| 2025-01-25 | 208 | 0.236 | 0.788 | 0.390 |
| 2025-02-15 | 208 | 0.697 | 0.986 | 0.834 |
| 2025-12-13 | 208 | 0.245 | 0.803 | 0.457 |
| 2026-01-03 | 208 | 0.337 | 0.913 | 1.749 |
| 2026-02-07 | 207 | 0.715 | 0.981 | 0.721 |

A one-way variance decomposition of the per-cell coverage indicator makes it
quantitative. The outcome is Bernoulli, so the absolute R-squared ceiling is
low; only the ratios between rows mean anything.

| grouping | groups | R2 on cov50 | R2 on cov90 |
| --- | --- | --- | --- |
| phase | 4 | 0.003 | 0.006 |
| horizon | 4 | 0.001 | 0.000 |
| phase x horizon | 16 | **0.005** | 0.006 |
| season | 3 | 0.006 | 0.003 |
| phase x horizon x season | 48 | 0.016 | 0.014 |
| state | 52 | 0.021 | 0.022 |
| **as-of week** | 85 | **0.081** | 0.058 |
| **as-of week x horizon** | 339 | **0.123** | 0.098 |

The forecast week explains 25 times more of the calibration variation than
phase and horizon together. This is a **common-mode, national error**: in a
given week either the whole country's intervals are too wide or the whole
country's are too narrow, and neither the state, the phase, nor the horizon
tells you which.

That is a direct, independent corroboration of Build 1's premise. The missing
information set -- "nobody currently sees that the Midwest peaked last week" --
is precisely a week-level national signal, and it is the grouping that predicts
the miscalibration. A width multiplier keyed on phase and horizon is keyed on
the wrong variable.

## 5. How much too wide, and would a conditional scalar survive LOSO

Descriptive only, and in-sample. `z = (y - median) / width`; nominal 50%
coverage requires `median abs(z) = 0.5`, nominal 90% requires the 90th
percentile of `abs(z) = 0.5`. The implied multiplier is that quantity divided
by 0.5. This is **not** a fitted object and must not be shipped as one --
handoff section 6 requires leave-one-season-out and section 1.5 is the null it
must beat.

| phase | s50 PF | s50 analogue | s50 ensemble | s90 PF | s90 analogue | s90 ensemble |
| --- | --- | --- | --- | --- | --- | --- |
| rising | 0.761 | **1.441** | 0.828 | 0.746 | **2.300** | 0.994 |
| near-peak | 0.614 | 1.039 | 0.719 | 0.536 | 1.093 | 0.602 |
| falling | 1.020 | 0.979 | 0.873 | **1.512** | 0.926 | 1.077 |
| low-flat | 0.698 | 0.909 | 0.710 | 0.665 | 0.740 | 0.619 |
| **pooled** | **0.809** | **1.079** | **0.814** | 1.048 | 1.497 | 0.928 |

The analogue wanting `s = 1.441` at the 50% level and `2.300` at the 90% level
on rising weeks is the single largest miscalibration in the table, and it is in
the *widening* direction. Any global narrowing applied to the ensemble is being
applied on top of that.

Split by season, the ensemble's wanted 50% multiplier is stable in two phases
and not in the other two:

| phase | 2023-24 | 2024-25 | 2025-26 | range |
| --- | --- | --- | --- | --- |
| **near-peak** | 0.709 | 0.719 | 0.730 | **0.021** |
| **low-flat** | 0.706 | 0.749 | 0.691 | **0.058** |
| falling | 0.760 | 0.824 | 1.025 | 0.265 |
| rising | 0.675 | **1.091** | 0.965 | **0.416** |

So the global-scalar null in handoff section 1.5 was an average of two stable
narrowings and two sign-flipping ones. A per-phase scalar restricted to
near-peak and low-flat cells is the only piece with a plausible LOSO signal --
and those are 4,052 of 16,775 cells, 24% of the grid, wanting about a 28%
narrowing. Dispersion is ~50% of WIS, so before the offsetting penalty increase
the ceiling on that arm is roughly `0.24 x 0.50 x 0.28 = 3.4%` pooled, under
the 5% gate the handoff sets. That is a prediction, not a measurement; but
Build 4 should be sized against it before anyone spends a day on it.

## 6. Two incidental notes for the coding agent

**A live inconsistency, not touched.** `app/state_defaults_ensemble_weights.json`
still carries the 2026-08-17 per-horizon freeze (PF share 0.4 / 0.6 / 0.7 / 0.8
plus 12 per-state overrides), and `app.core.ensemble.frozen_weights()` returns
it, while the handoff and the seal both say the shipping ensemble is 50/50
equal weights. Whichever is right, the two should agree. Width-wise it barely
matters -- the frozen blend is 2% narrower at the 50% level (pooled 0.813 vs
0.830) and 1% narrower at the 90% (2.634 vs 2.667) -- so this changes no
conclusion here, but a reader of the code and a reader of the handoff currently
get different answers about what ships.

**The scoring-agreement assertion.** This script reports widths rather than
WIS, but it still binds its own level pairing to the frozen scorer: for 3,000
cells x 3 quantile dicts it re-derives WIS and the dispersion term, pairing
`tau` with `1-tau` by value, and asserts agreement with `flubnf.wis.wis`
(max relative difference 0.00e+00 on both). A reversed upper-quantile array is
the bug that produced the fake +25% in the first draft of `width_sweep.py`, and
an interval-width study is exactly the place it would hide.

## 7. What this says about the build order

- **Build 1 (national growth, fixed `iota`) is corroborated.** The
  miscalibration is week-level and common-mode across all 50 states -- 0.123
  R-squared on as-of x horizon against 0.005 on phase x horizon. A per-week
  national signal is the right shape of instrument for a per-week national
  error.
- **Build 4 (conditional calibration) should be sized before it is built.**
  Phase carries 0.5% of the variation; the two phases whose wanted multiplier
  is stable across seasons are a quarter of the grid; the arithmetic ceiling is
  ~3.4% against a 5% gate. If it is built anyway, condition on near-peak and
  low-flat only, and expect a null.
- **Do not narrow the analogue.** It is the under-dispersed member everywhere,
  and it wants to be 44% wider on rising weeks at the 50% level and 130% wider
  at the 90%. If any spread work is done on the analogue, it is widening, and
  handoff section 4's "widen analogue quantiles by the residual of `c`" is
  already pointing that way.
- **If the PF's spread is touched, touch it at the flat-and-high weeks.** That
  is the only cell class where the PF alone over-covers by a wide margin
  (cov50 0.703, cov90 0.977) in all three seasons. Everywhere else the PF's
  width is either right (falling, 0.513) or being spent to compensate for the
  analogue (rising).
