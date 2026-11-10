# The Groundhog's flat small states, round 2026-11-07

Submission's question of 2026-11-05 (submission.md, For other lanes): why
the Groundhog forecast steep rises in Hawaii, Alaska, Montana and
Washington, where the data were flat or falling, and whether the cause is
the old to_date pin, the donors or the growth prior. A diagnosis, not a
screen: nothing here scores a forecast or a variant.

## How it was run

- `gh_flat.py` re-runs the shipped Groundhog
  (`app.core.engines.analogue.run`, `shipped_aux_pools()` and
  `shipped_local_pools()`: flusurv@06eff6a7 at weight 0.5 with its fitted
  shrink, own share 0.5, size-matched kernel sd 1, effective-donor floor
  30) for as-of 2026-10-31. It then takes each median ratio apart into the
  admissions pool (the state's own cells and the rest, with the weights
  `local_weights` gives them) and the FluSurv-NET pool.
- Data: the hub's live target file as of cdcepi main a73013aa. Its last
  change is fcc3c636 (2026-11-04), the update the round ran on, cut at
  2026-10-31 as the engine cuts it.
- Run on Ely's Windows PC, dev b4b176b, Python 3.11.9 (the clone's
  console venv). No engine, no state folder.
  `FLUBNF_HUB=<hub> python gh_flat.py <clone>` gives `report.txt`.

## What it shows

- The run reproduces the round. Its medians equal the submitted file
  to rounding: Alaska 14, 19, 26, 36; Montana 30, 48, 73, 97;
  Washington 230, 355, 540, 766. They also equal Hawaii's left-out
  58, 80, 104, 141 (submission.md 2026-11-04 21:47 UTC).
- The Groundhog's growth is the calendar's. Its median ratio blends the
  admissions donors (epiweek 44 within 2 weeks, seasons 2022-23 to
  2025-26) and FluSurv-NET's half and half. A state enters only through
  three things: its anchor (the level), the size kernel (the level
  again), and its own past seasons at this calendar week (half of the
  admissions half, so a quarter of the blend). Nothing reads its recent
  trend.
- Four weeks past the anchor (hub h3), FluSurv-NET's median ratio is
  2.98 for every state, and the other states' kernel-weighted ratio is
  2.9 to 3.6. Across all 52 states the implied weekly growth to h3 is
  1.27 to 1.38 for the middle 80% (median 1.34). Observed growth over
  the last three weeks was 1.10 to 1.54 (median 1.26). Rank correlation
  between the two: -0.10.

| state | last weeks (10-10 to 10-31) | observed /wk | own 4-wk | rest 4-wk | FluSurv-NET 4-wk | Groundhog /wk to h3 |
|---|---|---|---|---|---|---|
| Hawaii | 78, 86, 67, 54 | 0.89 | 1.85 | 3.39 | 2.98 | 1.27 |
| Alaska | 13, 22, 8, 12 | 0.97 | 2.80 | 3.62 | 2.98 | 1.32 |
| Montana | 26, 20, 20, 27 | 1.01 | 6.66 | 3.47 | 2.98 | 1.38 |
| Washington | 126, 158, 160, 179 | 1.12 | 8.92 | 2.94 | 2.98 | 1.44 |

In the table, own, rest and FluSurv-NET are each pool's weighted median
4-week ratio. Washington and Montana run fastest because their own past
seasons rose steeply from early November (Washington 2 to 23 times in all
four). Hawaii peaked on 10-17, off the calendar, and the Groundhog has no
way to see that.

- It is not the pin: the to_date pin is the Oracle's seed stage
  (`pf.seed_denominator`), and the Groundhog has none. It is not the
  anchors either: every one is the state's newest week, with no lag and
  no note.
