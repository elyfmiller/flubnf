# What FluBNF's WIS is made of, and what a calibration layer is worth

Prompted by a good question: EINN produces no quantiles, but can't you
manufacture them — run it N times, or wrap a fitted variance around the
median that grows with horizon? Yes, you can. This measures what that buys.

Production PF, `app/state/retro_seal`, 16,775 cells, three seasons.

## 1. The score is almost entirely the uncertainty representation

WIS decomposes exactly and additively into a median term, a dispersion term
(interval widths alone) and a penalty term (charged when truth escapes an
interval):

| horizon | cells | median % | dispersion % | penalty % | cov50 | cov95 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 4,257 | 6.3 | 55.2 | 38.4 | 0.597 | 0.965 |
| 2 | 4,230 | 6.5 | 48.2 | 45.2 | 0.554 | 0.956 |
| 3 | 4,188 | 6.4 | 48.3 | 45.4 | 0.552 | 0.960 |
| 4 | 4,100 | 6.3 | 50.4 | 43.4 | 0.550 | 0.970 |
| **pooled** | 16,775 | **6.4** | **49.9** | **43.7** | | |

**93.6% of the score is governed by the uncertainty representation and 6.4% by
the point forecast.** Any architecture of the form "point model + calibration
layer" is therefore being scored roughly 94% on the calibration layer. The
point model competes for the remaining 6.4% (plus indirect influence on the
penalty term).

Coverage confirms the documented defect from the other direction: the 50%
intervals cover 55–60% of the time. They are too wide, most at horizon 1.

## 2. A fitted width multiplier does not generalise

The simplest calibration layer: one scalar per horizon, scaling every quantile
around the unchanged median, `q'(tau) = m + s*(q(tau) - m)`. This is the
best case for the idea — it is applied to a model whose median is already
good, and there is no new model to train.

In-sample it looks like a real gain:

| h | best s | relWIS at s | relWIS as shipped | gain |
| --- | --- | --- | --- | --- |
| 1 | 0.65 | 0.7881 | 0.8269 | +4.7% |
| 2 | 0.85 | 0.8212 | 0.8292 | +1.0% |
| 3 | 0.85 | 0.7719 | 0.7794 | +1.0% |
| 4 | 0.80 | 0.7030 | 0.7159 | +1.8% |

Leave-one-season-out, with `s` fitted only on the other two seasons, it does
not:

| held-out | s fitted elsewhere | relWIS at s | as shipped | gain |
| --- | --- | --- | --- | --- |
| 2023-24 | 0.70 / 0.90 / 0.90 / 0.85 | 0.9891 | 1.0233 | +3.3% |
| 2024-25 | 0.75 / 0.90 / 0.90 / 0.85 | 0.6196 | 0.6361 | +2.6% |
| 2025-26 | 0.60 / 0.70 / 0.70 / 0.70 | 0.8659 | 0.8248 | **−5.0%** |
| **pooled** | | **0.7726** | **0.7746** | **+0.3%** |

**+0.3% pooled, against a ~5% noise floor.** Two seasons want narrower
intervals and one wants wider, the fitted multiplier swings between 0.60 and
0.90 across folds, and the gains cancel. This is the house rule about fitted
quantities failing to generalise, reproduced on a single scalar per horizon —
about the smallest fitted object it is possible to propose.

## 3. What this implies for a point-forecast member

- Running a deterministic model N times gives spread from initialisation and
  SGD noise — *training* variability, not observation noise or structural
  error. Deep ensembles are characteristically underdispersed, and the penalty
  term is already 43.7% of the score here, so an underdispersed member is
  charged heavily on exactly the term it gets wrong.
- A normal wrapped around the median has the right shape in horizon but the
  wrong support: admissions are non-negative counts and many jurisdictions run
  below 50/week, so a normal puts mass below zero. The production PF already
  uses a negative binomial for this reason.
- A horizon-only variance model is homoscedastic across phase, while §1 shows
  the miscalibration varies by horizon and §2 shows it varies by season. The
  spread needed at a turn is not the spread needed on a smooth rise.
- Published precedent: the one purely AI/ML FluSight entrant with published
  numbers scored 30% coverage on its 50% intervals.

So "you can bolt quantiles on" is true, and it does not rescue a point model.
The bolt-on is where ~94% of the score lives, and §2 shows that fitting it is
itself hard on this data.

## 4. What survives

The intervals really are too wide (cov50 = 0.55–0.60 against nominal 0.50),
and dispersion really is half the score. That is a genuine, localised defect
worth attacking — it is just that a **global** multiplier is the wrong
instrument, because the required correction is not global. A conditional
calibration (on phase, on trajectory curvature, on jurisdiction volume) is a
different and better-posed question, and §2 is the null result it should be
measured against.

## 5. A correction against my own first run

The first version of §2 reported a confident **+25% pooled LOSO gain** with
the optimum pinned at the edge of the search grid. It was an indexing bug:
`LEVELS` stores the upper quantiles in the same order as the lower ones, and
I reversed them, pairing the 1% quantile with the 55% quantile. Two things
caught it — the optimum sat at the grid boundary, and `relWIS` at `s=1.0` came
out at 1.63 for a member independently known to score 0.775.

`width_sweep.py` now asserts agreement with `flubnf.wis.wis` at `s=1.0` before
reporting anything (max relative difference 4.5e-16). Any future rescoring
script should carry the same assertion; a scoring bug that makes results look
*better* is the one nobody double-checks.

## Reproducing

```
./.venv/bin/python research/wis-decomposition/decompose_wis.py   # section 1
./.venv/bin/python research/wis-decomposition/width_sweep.py     # section 2
```

`width_sweep.py` caches parsed cells in `cells.pkl`; delete it to re-read the
stored retrospectives (~4 minutes).
