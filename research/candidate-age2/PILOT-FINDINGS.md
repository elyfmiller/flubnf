# Age-2 candidate: pilot result — NO-GO

**The paediatric channel identifies `theta` sharply and should still not be
seated. The signal it identifies it with is a concurrent echo of adult
admissions plus a school-calendar artefact, and the model mis-specifies both.**

Run 2026-08-21. Model `SIHRS_pop_age2_min.bngl`, driven directly through the
PF fork; no changes to `flubnf/` or `app/`. Reproduce with the three commands
in `pilot.py`'s docstring.

## 1. The parameter is identified — that part worked

California, 2024-25, 44 weeks, 4000 particles, identical seed. Two arms differ
only in whether the paediatric exp columns carry data or `-1/-1`.

| | theta mean | theta sd | sd / prior sd |
| --- | --- | --- | --- |
| channel ON | 0.583 | 0.055 | 0.27 |
| channel OFF | 0.352 | 0.117 | 0.58 |

Prior is U(0, 0.7): mean 0.350, sd 0.202. With the channel off, theta lands on
its prior mean to three decimals — it is unidentified, as expected. With the
channel on it moves +0.23 and concentrates to a quarter of the prior width.

The mechanism is not decoration. Everything below is about *what* it is
identifying.

## 2. The signal is real, but the model consumes the wrong part of it

Cross-correlation of weekly log-growth in paediatric vs adult admissions, 64
jurisdiction-seasons with adequate volume, epidemic window only:

| lag (wk) | −1 | **0** | **+1** | +2 | +3 |
| --- | --- | --- | --- | --- | --- |
| mean r | 0.261 | **0.647** | **0.613** | 0.358 | 0.004 |

Positive lag means paediatric growth leads. The correlation peaks at lag 0 and
lag +1 is lower, which looks like the echo signature — but that reading is
wrong, and it is worth being explicit about why, because the same mistake is
easy to repeat. Adult growth is itself autocorrelated (week-to-week r = 0.438),
so a high contemporaneous correlation does not preclude incremental
information. The echo test has to be run on the residual, not the raw series.

Run properly, pooled over 932 state-week observations in the epidemic window:

| statistic | value |
| --- | --- |
| raw corr(paed growth_t, adult growth_t+1) | +0.482 |
| raw corr(adult growth_t, adult growth_t+1) | +0.438 |
| **partial corr(paed_t, adult_t+1 given adult_t)** | **+0.310** |

That reproduces the memo's motivating +0.315 essentially exactly, and it holds
*after* controlling for the autoregressive term. **The paediatric signal is not
an echo.** Predicting adult growth one week ahead, R² goes from 0.192 on the
autoregressive term alone to 0.270 when paediatric growth is added —
incremental R² **+0.078**.

The problem is which part of the signal the model eats. Against the actual
forecast target, next week's growth in *total* admissions:

| predictors | R² |
| --- | --- |
| total growth_t alone | 0.2138 |
| + paediatric **growth**_t | 0.2437 (+0.030) |
| + paediatric **share**_t | 0.2234 (+0.010) |
| + both | 0.2477 |

The information lives in paediatric **growth**. The binomial channel on
`Ped_share` — what this model actually implements — consumes the share, which
carries a third as much. The mechanism was built around the weaker observable.

## 3. What the channel actually identifies is the calendar

The paediatric *share* has one large, repeatable feature: a trough. Across 95
jurisdiction-seasons it is not locked to the epidemic.

- Regressing trough week on peak week gives **slope +0.215** (r = 0.200).
  Epidemic-locked would be ≈ +1.0.
- Between 2024-25 and 2025-26 the mean admissions peak moved **−3.29 weeks**;
  the mean share trough moved **−1.27 weeks**.
- 76 of 95 troughs fall in the ten days 3–11 January.
- Trough-week spread collapses while peak-week spread does not: in 2025-26,
  peak sd 2.13 weeks vs trough sd **1.09** weeks.

And the trough is not paediatric at all. Comparing the trough week with three
weeks earlier, median across units: **paediatric admissions ×0.96, adult
admissions ×2.22.** The share falls because the adult denominator more than
doubles while paediatric admissions sit flat.

So the largest feature in the "paediatric" channel is the early-January adult
surge, timed by the calendar. The ensemble already has a member whose entire
basis is calendar-locked structure. This is not orthogonal information.

## 4. The model puts that feature on the wrong side of the peak

Fitted at its posterior mean, California 2024-25:

| | share trough | relative to admissions peak (t=26) |
| --- | --- | --- |
| observed | t = 23 | **−3 weeks (before)** |
| model, theta = 0.583 | t ≈ 30 | **+4 weeks (after)** |

In-season correlation between the modelled and observed share trajectories is
−0.05. The model reproduces the qualitative high-low-high shape and gets its
phase wrong by about seven weeks.

Worse, the level is doing the fitting. The model's median share rises
monotonically in theta (0.070 at 0.30, 0.098 at 0.58, 0.127 at 0.70) and the
observed median is 0.122, so the level-matching value is ≈ 0.68. The filter
moved theta from 0.35 toward that level, not toward a better trajectory
shape — the failure the template header warned about, now measured. The
`rhoK`/`rhoA` calibration was supposed to neutralise the level at the anchor;
it does not, because the eigenvector split does not reproduce the ODE's
realised share.

A confidently-estimated parameter (sd 27% of prior) absorbing a mis-specified,
calendar-driven signal is worse than an unidentified one. It will move the
forecast with conviction on the wrong evidence.

## 5. Independently, the data will not support an evaluation

Age-stratified NHSN state-weeks, by season:

| season | with age split | with n ≥ 50 |
| --- | --- | --- |
| 2022-23 | 0 | 0 |
| 2023-24 | 1,710 | **81** |
| 2024-25 | 3,210 | 1,438 |
| 2025-26 | 3,447 | 1,390 |

Age strata are usable only from 2024-25. That leaves two seasons, one of which
is the development season, so one honest out-of-sample season. And **2023-24 —
the February plateau, one of the two turn events the whole member search is
aimed at — cannot be evaluated at all.** On top of the already-documented
absence of an as-of archive for age strata, there is no way to build a
vintage-true retrospective here.

## 6. Verdict

**No-go for this member as built — but the underlying signal is worth keeping,
and that is a different conclusion from the one I first wrote.**

Against the mechanism, three grounds:

1. It consumes the paediatric **share** through a binomial channel, and the
   share is the weak part of the signal (incremental R² +0.010 vs +0.030 for
   paediatric growth, §2).
2. The share's one large feature is calendar-locked, driven by the adult
   denominator, and duplicated by the analogue member (§3) — which is also why
   the share underperforms growth as a predictor.
3. The model puts that feature on the wrong side of the peak by about seven
   weeks while confidently fitting `theta` to its level (§4). A parameter
   estimated to a quarter of its prior width, on a mis-specified feature, will
   move forecasts with conviction on the wrong evidence.

And independent of the mechanism, §5: age strata begin in 2024-25, so there is
one honest out-of-sample season and the 2023-24 plateau cannot be evaluated at
all. That blocks a vintage-true evaluation regardless of how the member is
built.

For the signal: paediatric growth carries genuine incremental information
about next week's admissions growth (partial r +0.31 after controlling for the
autoregressive term; +0.030 incremental R² on the target). That is modest, and
§5 still limits how well it can be validated, but it is not nothing and it is
not an echo. It does not want to be a compartmental mixing parameter — it wants
to be a predictor entering a model that can use a lagged covariate directly.
That is a live thread for the multi-input work, not for the ODE ensemble.

Cost to reach this: about an hour, versus a full retro build. The two-arm
ON/OFF design is worth reusing — silencing a channel's exp columns while
holding seed and every other input fixed isolates its contribution exactly,
and it is what turned "theta is identified" from a comfort into a question.

A caution recorded against my own reasoning: the raw cross-correlation peaking
at lag 0 (§2) looked like a clean echo verdict and was not one. Whenever the
target is autocorrelated, the echo test must control for the target's own lag
before concluding that a channel adds nothing.

## 7. How much is the signal actually worth? (out-of-sample)

§2's incremental R² was in-sample and pooled. Held out properly — fit on one
season, predict the other, both directions — predicting cumulative log growth
`log(N_{t+h}/N_t)`:

| h | ΔR² (train 24-25 → test 25-26) | ΔR² (train 25-26 → test 24-25) | mean RMSE reduction |
| --- | --- | --- | --- |
| 1 | +0.042 | +0.039 | 2.3% |
| 2 | +0.069 | +0.070 | 3.9% |
| 3 | +0.030 | +0.032 | 1.6% |
| 4 | — (n too small) | — | — |

Both directions agree closely, so the effect is stable. Block-bootstrapping
over jurisdictions (400 draws, in-sample) gives ΔR² CIs that exclude zero at
h=1 (+0.033, [+0.013, +0.076]), h=2 (+0.068, [+0.038, +0.133]) and h=3
(+0.024, [+0.004, +0.090]), but at h=4 the effect is gone: +0.005,
[+0.0001, +0.031], on 11 jurisdictions.

**The gain concentrates on turns**, which is the one thing that could matter
here. Splitting the held-out weeks by whether the forecast window straddles the
season peak, mean RMSE reduction:

| h | turn weeks | all other weeks |
| --- | --- | --- |
| 1 | +4.0% | +2.1% |
| 2 | **+8.8%** | +2.1% |
| 3 | +3.7% | +0.5% |

At h=2 the turn-week gain is +12.2% and +5.5% in the two directions, both
positive. That is above the system's ~5% relWIS noise floor.

Four reasons this is still not a green light:

- The turn cells hold 38–65 observations per test season, and h=1 flips sign
  between directions (−0.2% and +8.3%). h=2 is the only horizon where both
  directions agree and clear the floor.
- These are RMSE reductions on a **point** forecast of log growth. The
  system's defect is that its predictive distribution is too *wide*; a better
  conditional mean does not address spread, and the mapping from ΔRMSE to
  ΔWIS is not established.
- Everything is measured on **final** data. As-of paediatric counts are
  noisier, so these numbers are an upper bound.
- The absolute predictive power is low regardless: the autoregressive baseline
  scores R² 0.026–0.173 at h=1 and is *negative* at h=3. Adding paediatric
  growth moves 0.026 → 0.068.

## What is worth keeping

- `pilot.py`'s two-arm harness, as a template for any future channel.
- The trick in `child_fraction()`: NHSN's `...per100k` columns divided into
  their counts recover CDC's own age-band denominators, so a child population
  fraction needs no census join. It returned 0.2142 for California against a
  census value of about 0.217.
- The eigenvalue normalisation of `beta0` in the BNGL template, which keeps
  `Reff` orthogonal to mixing parameters. That is reusable in any
  multi-class extension.

## What this does not say

It does not say age structure is irrelevant to influenza — it plainly is not.
It says that *this* observable (the paediatric admission share), on *this*
data (NHSN age strata from 2024-25), through *this* mechanism (two-class
assortative mixing with one free mixing parameter) does not carry exploitable
information at a 1–4 week horizon. A different observable, such as paediatric
ICU or age-resolved test positivity with its own as-of archive, is not
addressed by this result.
