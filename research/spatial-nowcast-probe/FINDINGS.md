# Spatial coupling and nowcasting — 2026-08-21 probe

Two ideas, two different verdicts. Neither should be built as first imagined.

## 1. A 52-region BNGL metapopulation — no. The spatial *signal* — yes.

The instinct is right and the container is wrong.

Leave-one-state-out national log-growth at week *t* predicts a state's own growth at *t+1* after controlling for the state's AR(1) **and** a Fourier seasonal (the thing `eps1`/`phi1` already give the PF):

| held-out | R² (AR+seasonal) | + national | ΔR² | RMSE reduction |
| --- | --- | --- | --- | --- |
| 2023-24 | 0.192 | 0.273 | **+0.081** | +5.1% |
| 2024-25 | 0.237 | 0.268 | +0.032 | +2.1% |
| 2025-26 | 0.225 | 0.343 | **+0.118** | +7.9% |

Partial correlation of national growth with next week's own growth, given own lag: **+0.469**. That is larger than paediatric growth's +0.31, and it replicates in all three seasons. It concentrates on turns (|t − state peak| ≤ 3 weeks): RMSE reductions +8.9%, +2.4%, **+14.7%**.

This is this year's realised wave, not the average calendar. The Fourier seasonal — "it's January" — takes AR(1) R² from 0.081 to 0.241 and still leaves most of the national term standing. Memo candidate 4.5 predicted the neighbour term would be collinear with `eps1`/`phi1`. Half right: they are correlated (own vs national growth r = 0.674), and the incremental information is still large.

**Why that does not mean a 52-region BNGL.** The signal is *other states' realised growth last week*, not people moving. A metapopulation with movement reactions:

- Multiplies the ODE from 5 species to ~260, and the PF from 52 independent 10k-particle filters into one 260-dimensional cloud. Particle filters die in that dimension. You also lose per-state parallelism (the thing that makes a Wednesday deadline possible).
- Adds movement rates that admissions at a 1–4 week horizon do not identify. Interstate travel is a rounding error on within-state mixing; the 1-week lead is epidemiological *asynchrony* (some states peaked last week), which is not a commuting flow.
- Charges the width problem. Extra fitted dimensions were how the current PF got too wide. Even with movement *fixed*, you are integrating a stiff 52-compartment system 10,000 × ~26 times per as-of.

The analogue already pools across states (donors are national, calendar-matched, prior seasons). The PF is the isolated member. Spatial information belongs there.

**What to build instead, if this is pursued.** Memo 4.5's shape, specified on *growth* not level:

```
beta_s(t)  +=  iota * (g_nat^{-s}(t) - g_s(t))
```

with `iota` **fixed a priori**, `g_nat^{-s}` the vintage-true leave-one-out national log-growth of admissions, per-state filters unchanged. Zero new fitted parameters, zero new species, embarrassingly parallel still. A level-form importation (`sum w_ss' A_s'/N`) is the occupancy-ratio trap: it restates prevalence, which the filter already has.

Pre-register `iota` from the LOSO coefficients above before any PF run. Gate on turn cells. Vintage story is clean — it uses only the target stream.

## 2. Nowcasting the last week, then feeding it to both members — right architecture, unstable correction

The framework already exists (`weeks_to_drop` / `weeks_to_nowcast` on `RunSpec`; the nowcaster is a documented no-op). The revision facts are not in dispute: 68% of revision mass is the newest observation, 80% the newest two; three weeks back the median revision is exactly zero. Lag-0 first-issue vs settled, 4,560 state-weeks:

| season | median first/final | share < 0.95 | mean \|log-bias\| |
| --- | --- | --- | --- |
| 2023-24 | **1.000** | 17% | 0.060 |
| 2024-25 | 0.918 | 63% | 0.179 |
| 2025-26 | 0.929 | 56% | 0.158 |

The bias is real in the last two seasons (~7–8% typical undercount on the last point) and essentially absent in 2023-24. Reporting completeness **changed between seasons**. That is the failure mode memo 4.3 flagged, and it already happened.

Leave-one-season-out, applying a state's historical median completeness to the last point:

| held-out | naive MdAPE | nowcast MdAPE | \|log\| reduction |
| --- | --- | --- | --- |
| 2023-24 | 0.017 | 0.087 | **−99%** (hurts) |
| 2024-25 | 0.088 | 0.068 | +7.2% |
| 2025-26 | 0.075 | 0.060 | +9.3% |

A single national scalar does the same thing, smaller: −76%, +2.1%, +4.4%. You cannot fit `c` on 2024-25/2025-26 and evaluate it on 2023-24, and you cannot do the reverse. For 2026-27 a correction fitted on the last two seasons is plausible; a three-season retrospective that includes 2023-24 will mix a regime where the correction is poison with two where it is mild help.

**Analogue vs PF, because they are not the same input.**

The analogue *is* `last_point × historical_ratio`. A 7% bias on the last point is a 7% bias on **all four horizons**. That is the member that wants a nowcasted *anchor*. (Do not confuse this with the documented 0.177 relWIS from using the *next* week's true value as the anchor — that is look-ahead, not a nowcast of the current week's revision.)

The PF is one likelihood term in ~26. Replacing the last point with a nowcast and treating it as observed injects **false precision**: the filter becomes more sure of a number you made up. The honest version is memo 4.3 — keep the observed `y`, change the observation model to `y ~ NegBin(c_{s,L} μ, r_L)` so the last point is down-weighted as well as de-biased. `weeks_to_drop = 1` (ignore the last point entirely) is safer than a bad `c` and dumber than a good one: you keep the *direction* of the last point when you completeness-correct, and throw it away when you drop.

So the combined recipe, if this is built:

- Analogue: nowcast the anchor, optionally widen its quantiles by the historical residual of `c`.
- PF: completeness-correct the likelihood; do **not** overwrite the `.exp` file with a point nowcast.
- Fit `c` only on seasons after the 2023-24 break, and do not claim a 2023-24 retrospective for this candidate. Pre-register that.

Expected effect is small. Even a perfect nowcast of a 7% last-point bias is a 7% analogue-median shift, and the PF's median is only 6.4% of its WIS. Memo 4.3's "null is the most probable outcome" still stands. The reason to build it anyway is architectural: it is the only candidate that attacks a *known, vintage-true, one-week* defect in the input both members share, adds no fitted parameters to the PF, and is already stubbed.

## 3. Ranking against today's other results

| idea | incremental signal | right container | build? |
| --- | --- | --- | --- |
| National/regional growth as exogenous term | ΔR² +0.03 to +0.12 after seasonal; +8–15% RMSE at turns in two of three seasons | Per-state PF, `iota` fixed, growth not level | **Yes, next** — cheapest thing that actually addresses turns |
| Last-week nowcast / completeness | Real 7% bias in 2024-26; LOSO correction helps those seasons, wrecks 2023-24 | Analogue anchor + PF likelihood; not a point overwrite | Yes, second, with the regime break pre-registered |
| 52-region BNGL with movement | Same signal as row 1, trapped in the wrong model | — | No |
| Age-structured SIHRS | Real but smaller; consumed the wrong observable | — | No (done) |
| Two-strain gate | Signal inverted vs the gate | — | No (done) |
| Neural member / EINN | No FluSight win; 94% of WIS is calibration | — | No (closed) |

Reproduce: `./.venv/bin/python research/spatial-nowcast-probe/probe.py`

## 4. Settling time (weeks from first issue to within 5% of final)

Measured on all 90 vintages, 7,219 state-weeks, three seasons. "Staying there" means every later vintage also stays within 5%.

| season | median weeks | % already at first issue | % by 1 week | % by 2 weeks |
| --- | --- | --- | --- | --- |
| 2023-24 | 0 | 75% | 85% | 86% |
| 2024-25 | 1 | 50% | 66% | 73% |
| 2025-26 | 0 | 57% | 72% | 82% |
| ALL | 0 | 60% | 74% | 81% |

Median vintage/final by lag (the typical path):

| lag | 2023-24 | 2024-25 | 2025-26 |
| --- | --- | --- | --- |
| 0 (first issue) | 1.000 (p10 0.93) | 0.966 (p10 0.71) | 0.982 (p10 0.75) |
| 1 | 1.000 (p10 0.97) | 0.982 (p10 0.82) | 1.000 (p10 0.88) |
| 2 | 1.000 (p10 0.99) | 1.000 (p10 0.90) | 1.000 (p10 0.92) |

Among the cells that *start* incomplete (first issue < 95% of final — 41–46% of cells in 2024-26): median time to 95% is **2 weeks**, but the tail is fat (2024-25 p75 = 16 weeks; 2025-26 p75 = 5 weeks). Late batch revisions, not slow drip, drive that tail.

Typical FluSight week therefore: the last observation is the moving piece; T−1 is mostly done; T−2 is settled at the median. Do not nowcast the whole series.

