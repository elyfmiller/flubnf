# The tail cap on both halves: the Groundhog half (2026-11-11)

Model lane, Ely's Windows PC. Warm start task 3, asked by Ely on
2026-11-04 (submission.md Open) with the Submission lane's handoff of the
same day. The pre-registration was frozen before any score and pushed in
d3996ecd before the first score file was written ([RUNLOG.md](RUNLOG.md)).

| File | What it is |
|---|---|
| [prereg.txt](prereg.txt) | the pre-registration, frozen 2026-11-11 01:31 UTC; `sha256sum -c prereg.txt.sha256` checks it (67262c94...a0d) |
| [both.py](both.py) | the arms in the pipeline's order (hub rows, then the cap), the code check, the scoring, the report |
| [report.txt](report.txt) | the report as `both.py --report` printed it: the reproduction gate, every arm on every subset, the bootstrap, the touched blocks, the exponents, the predictions and the decision rule |
| [RUNLOG.md](RUNLOG.md) | what ran, in order, and what was read after the scores |

The stored forecasts, the per-cell tables and the logs stay outside the
repository, at `%USERPROFILE%\flubnf-model-research\cap-both-halves-2026-11`
on Ely's PC (replay/ in, results/ out).

## Result

Three seasons, 17,116 state cells; the gate reproduces the record exactly
(0.6802, 0.6272, 0.6448, pooled 0.6423). Selected arms (all 25 are in the
report): relWIS natural / log, 95% coverage, EARLY (first 8 weeks of each
season), the corrected-seed windows (CSW):

| arm | relWIS | log | cov95 | EARLY | CSW |
|---|---|---|---|---|---|
| N, no cap | 0.6423 | 0.6249 | 0.946 | 0.6393 | 0.5492 |
| S10-R3, production | 0.6642 | 0.6433 | 0.904 | 0.6848 | 0.6177 |
| S10-RX | 0.6507 | 0.6333 | 0.923 | 0.6569 | 0.5755 |
| M10-R3 | 0.6613 | 0.6460 | 0.884 | 0.6790 | 0.6096 |
| B10-R3 | 0.6592 | 0.6455 | 0.876 | 0.6756 | 0.6056 |
| LN10-R3 | 0.6639 | 0.6418 | 0.867 | 0.6804 | 0.6091 |
| S15-R3 | 0.6491 | 0.6311 | 0.928 | 0.6536 | 0.5711 |
| S15-RX | 0.6437 | 0.6266 | 0.941 | 0.6422 | 0.5541 |
| M15-RX | 0.6435 | 0.6280 | 0.937 | 0.6418 | 0.5534 |
| B15-RX | 0.6426 | 0.6281 | 0.931 | 0.6399 | 0.5502 |

- The level matters most. Taking the larger of the last week and the
  three-week mean (RX) beats the three-week mean at both caps: at 10x by
  -0.0135 [-0.0220, -0.0053] pooled, -0.028 on EARLY and -0.042 on the
  corrected-seed windows; at 15x by -0.0055 [-0.0099, -0.0014]. 95%
  coverage rises (10x 0.904 to 0.923). RX loosens the cap where the level
  lags a jump, the Delaware case: it shrinks 24.0% of state blocks at 10x
  against 27.1%. It costs in October 2023, the one October in the data,
  where the tight cap helped (Sep-Oct 0.8865 against 0.8555).
- The lower half gains little and costs coverage. Against S at the same
  cap and level, M gains -0.0030 at 10x and -0.0011 at 15x (R3), and B
  -0.0050 and -0.0028. Both lose on the log scale at R3 and lower the 95%
  coverage (10x: 0.904 to 0.884 under M, 0.876 under B). Both lose in
  October 2023, where the truth already fell below the band. B narrows
  more than M, not less (its exponent's median 0.43 against the cap's
  0.61). LN changes the score by -0.0003 [-0.0065, +0.0070] at every cap
  and level, with 95% coverage 0.867 at 10x.
- Predictions: G1, G5 and G7 hold. G2, G3, G4 and G6 fail: the mirror's
  EARLY gain at 15x is smaller than predicted, its coverage cost at 15x
  just under the predicted 0.01, B narrows more than M, and the level's
  gain is larger than predicted.

## The decision rule

- At 15x, S15-RX passes every test and is RECOMMENDED; S15-R1 also passes
  and comes second in the tie order. No lower-half rule passes. On the
  newer levels M and B fail (b), one season worse than S15-R3 by 0.0054 to
  0.0074. On the three-week mean they fail the log scale (d) or the EARLY
  coverage (e). LN fails (a).
- At 10x, no arm passes, so S10-R3 stays. Every 10x arm fails (e), the
  EARLY 95% coverage floor of 0.85; production is at 0.778 there. Outside
  the rule: S10-RX fails only that floor (0.843), and it beats production
  pooled, in 2024-25 and 2025-26, on EARLY, on the corrected-seed windows,
  on the log scale and in coverage. 2023-24 is the exception, +0.0027,
  from October.
## Amendment 1: the lower half balanced in admissions (BN)

Ely, on reading the above: after a jump like Delaware's the bottom half can
be wider than the capped top, which looks wrong and may cost WIS. Part 1's
lower-half rules all narrowed too far. [AMENDMENT1.txt](AMENDMENT1.txt),
frozen before its first score, adds the gentlest version: below the median,
pull in only where the 95% band is wider below than above in admissions,
just far enough to even it. Results in [report_amend1.txt](report_amend1.txt):

| arm | relWIS | log | cov95 | against S, same cap and level |
|---|---|---|---|---|
| BN10-R3 | 0.6640 | 0.6493 | 0.888 | -0.0002 [-0.0014, +0.0011] |
| BN10-RX | 0.6510 | 0.6373 | 0.917 | +0.0003 [+0.0000, +0.0007] |
| BN15-R3 | 0.6495 | 0.6357 | 0.921 | +0.0003 [+0.0000, +0.0007] |
| BN15-RX | 0.6438 | 0.6280 | 0.939 | +0.0001 [+0.0000, +0.0002] |

- On WIS it is neutral, and it costs a little coverage and some log
  score. It does far less harm than the log-scale balance B (Sep-Oct
  2023: +0.082 against S10-R3, B +0.164). It helps in November (10x R3
  0.5991 to 0.5951) and costs in October 2023.
- Once the level is fixed there is little left for it to do. It acts in
  10.7% of location-weeks at 10x R3, 4.3% at 10x RX and 0.7% at 15x RX.
  The level alone already evens the band in the rise: the h0 width below
  the median over the width above, November, 10x, goes from 1.12 to 0.82,
  and at 15x RX it is 0.50.
- Predictions H1, H2, H4 and H5 hold. H3 fails: at 10x R3 its 95%
  coverage is 0.015 below S's.
- The rule: no BN arm is recommended over the shrink alone at the same
  cap and level.

## What follows

- This is the Groundhog half. The level and the cap are one setting per
  location for both members, so the prereg leaves the Oracle as it is
  until Part 2 (C0's 84 stored weeks, once the lab Mac's research tree is
  on the PC), unless Ely decides otherwise.
