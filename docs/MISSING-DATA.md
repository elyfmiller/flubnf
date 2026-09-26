# Missing data in the NHSN hub series

The question: when a state does not report, should the models fill the gap (a spline between the two
neighbouring weeks) instead of treating it as absent or as a 0? This page answers it from the hub's own
record: the 90 archived vintages (2023-09-23 to 2026-07-04, `auxiliary-data/target-data-archive/`) and the
settled `target-data/target-hospital-admissions.csv`. The survey scripts are not part of the app; every
number below comes from the hub files as published. (The eight scored weeks the archive skipped, shipped
since as `data/vintages/`, are not in these counts; see [data/README.md](../data/README.md).)

## What the models do today

The policy is "dropped, never imputed" (`app/core/data.py`).

- **Groundhog.** NaN rows are dropped. If the newest reported count is 0 the forecast is a ratio times 0,
  so the location abstains (`flubnf/analogue.py`, anchor <= 0 returns None). Zeros are also never donors.
- **Oracle SIHRS (particle filter).** NaN weeks are dropped with their true week offsets kept, so a gap is
  simply an absent `.exp` row: the filter propagates through it with no likelihood term. A 0 is a real
  observation and enters the negative-binomial likelihood as 0.
- **Oracle bank.** `_fill_loglinear` (interior NaN, log-linear on log(y+0.5), at most 2% of cells) is used
  only by convention C, which no arm reads.

## How missing data actually appears

"Large neighbour" means the larger of the two neighbouring weeks is 10 or more.

| Case | Settled target-data | 90 vintages |
|---|---|---|
| Absent rows (week missing from the file) | 0 | 0 |
| NA weeks | 36: MA 17, MN 14, WV 5, all 2024-05-18 to 2024-10-05 | interior only, the same 2024 weeks, in 58 vintages; run lengths 1, 5, 6, 11 |
| NA at the newest week (the real-time case) | 0 | 0 |
| Interior NA gaps of 1 or 2 weeks | 2 (MN 2024-09-21 and 2024-10-05, both between zeros) | the same two |
| Interior zero runs, small neighbours | 447 runs, 964 weeks (VT, DE, RI, NH, MT, ND lead) | |
| Interior zero runs, large neighbours | 14 runs, 23 weeks: 11 in the 2024 voluntary-reporting months (NC 8 weeks before 77; LA, MS, NJ, MN around 2024-10-12) | 1 to 2-week ones inside a fit window: LA, MS (2), NJ, MN, in the 30 vintages of 2024-25 |
| Newest week reads 0 | | 119 location-weeks in 35 vintages; every one after a week of 7 or fewer, none after 10 or more |
| Newest week collapses (under a fifth of a prior week of 20 or more) | | 17 location-weeks; 9 were later revised to at least twice the reported value (PR 3, AL 2, NJ, ID, AZ, HI) |

**Is 0 really missing?** Not at the newest week. Of the 119 newest-week zeros, 93 (78%) are still 0 in
settled data; 26 were revised up, to at most 5 (mean settled value 0.35). Newest-week counts of 1 to 3 are
revised up about as often (90 of 344, 26%, mean +0.72). A newest-week 0 in this archive is a genuine low
count in a small state, not a non-report. The hub signals a non-report with NA (only in the 2024 pause) or,
in real time, with a **collapsed partial count**, not with 0.

## Replay (Groundhog, every archived vintage, settled truth)

Scored with the project's WIS (`flubnf/wis.py`) against the validated FluSight-baseline construction
(`flubnf/baseline.py`); "cells" are location x horizon. The Groundhog runs for real here; the particle
filter does not (the engine is not installable in this environment), so no PF replay was possible.

| Rule (newest week treated as unreported, anchor moved back, horizons as-of-aligned) | Location-weeks | Cells | Current / baseline | Rule / baseline | Rule / current |
|---|---|---|---|---|---|
| Newest week 0, carry back up to 2 weeks | 96 (+18 longer runs kept, +5 without settled truth) | 168 | abstains | 1.022 (0.937 on 136 cells with truth > 0) | not comparable |
| Newest week under 0.2 x a prior week of 20+ | 15 scorable of 17 | 60 | 1.174 | 0.383 | 0.326 (8 of 15 better) |

The partial-week result is thin and concentrated: without Puerto Rico and Alabama the ratio is 0.768.
It is also threshold-sensitive: with 0.35 instead of 0.2 (50 location-weeks) the rule is worse than the
current forecast outside PR and AL (1.661), and at 0.5 it is worse overall (1.195, 169 location-weeks).
Only a severe collapse looks like a non-report; a moderate drop is usually real.

## What is not worth building

- **Interior fill (log-linear or PCHIP on log(y+0.5)).** The hub has two interior 1-week NA gaps and both
  sit between zeros, so either fill returns 0. Longer gaps (5 to 11 weeks) are the 2024 pause, where a
  spline has nothing to interpolate from. The PF already handles a dropped week natively; filling it only
  invents a likelihood term. No knob was added.
- **Longer than 2 weeks.** Two weeks either side is already a guess across a quarter of a wave's rise.
- **Trailing interpolation.** Impossible in real time: there is no right-hand neighbour.

## What ships (both off by default)

Two model settings in the Fit window group (`app/core/knobs.py`, rules in `app/core/missing.py`):

- `data.trailing_zero`: keep (default) or missing. Missing: 1 or 2 newest weeks of 0 after a positive week
  are treated as unreported. The Groundhog then forecasts instead of abstaining, at about baseline skill;
  the PF fits without those weeks. It buys coverage, not accuracy.
- `data.partial_week`: keep (default) or missing. Missing: a newest week under a fifth of a prior week of
  20 or more is treated as unreported. The strongest replay result, but 15 events; it needs a
  pre-registered season replay with the PF before anyone turns it on for a submission.

Both members trim a flagged week exactly as `weeks_to_drop` does (horizon h reads h + k weeks from the
moved anchor, so labels stay as-of-relative), a modified run is marked and exported under the non-hub name
unless overridden, and every flagged week is listed in the run record (`data_flags` in the outcome, one
line under "Missing-data rules" on the run page; the PF also records it per cell in `cells.json`). With both
at keep, the engines take exactly their shipped path.

A replay records the same rows per replayed week (`data_flags` in its `run_meta.json`, keyed by the as-of
date; the FluSight replay and the own-data replay alike) and shows a "flagged weeks" count in its settings.

`data.partial_week` is not offered on a custom dataset: its floor (a prior week of 20 or more) assumes
hospital admission counts. The dataset panels hide it and a dataset run or replay refuses it
(`missing.HUB_ONLY_KEYS`); `data.trailing_zero` stays available everywhere.

## The Groundhog's zero-anchor rule

The Groundhog is anchor x donor ratio, so a newest week reading 0 gives it nothing to scale and it abstained.
In the 85 archived vintages of 2023-24 to 2025-26 that happened in 93 of 4,420 location-weeks; the runs of
trailing zeros were 1 week in 63 of them, 2 in 19, 3 in 4, 4 in 4, 6 in 2 and 7 in 1. Donor depth is not
the constraint. The particle filter is unaffected (a 0 is an observation).

Four rules were scored on those 93 location-weeks (172 cells with a FluSight-baseline; WIS ratio to the
baseline, 95% interval), `app/core/engines/analogue.py zero_anchor`:

| Rule (`groundhog.zero_anchor`) | What it forecasts from | Rule / baseline |
|---|---|---|
| `abstain` | nothing: no forecast (what every run did before) | not scored |
| `level` | the mean of the last 4 reported weeks, zeros included, at the 0 week; all 0: Poisson(clip(mean, 0.35, 5)) | 0.874 [0.72, 1.00] |
| `extend` | the last positive week at its own date, the ratio spanning the 1 or 2 zeros; longer runs: the same Poisson | 1.007 [0.73, 1.33]; wins season onsets (0.61), loses on true low counts (1.62) |
| `blend` | level and extend averaged level by level | 0.875 [0.72, 1.02] with a 3-week level arm (the shipped one uses 4); best at onsets (0.71) and in coverage |

A Poisson floor alone scored 1.124. Widening the donor window (-2..+3 weeks) did not help (1.018) and hurt
the low non-zero anchors (1.021 [1.010, 1.031]), so the window is unchanged. The rule has NO default: a
live run asks per state (below), a replay asks on its form, and a season replayed before the rule existed
is read as `abstain`. The choice is recorded with the run and never marks it modified: the model cards
state that it is the forecaster's.

## Per-state choices (the Data issues box)

The Data tab flags every newest week that reads 0 (of the hub's newest-week zeros since 2023, about three
quarters stayed 0 once settled and none rose above 5), every collapsed week (under a fifth of a week of 20
or more; 9 of the 17 in the archive were later revised to at least twice the reported value) and every
unreported one. Some collapses are partial reports (Alabama 8 after 194 on 2026-01-24, settled at 250) and
some are real drops (2026-03-28: Delaware 4 after 24, Hawaii 1 after 21, Maryland 9 after 52, Utah 8 after
49, all settled where they were), so no global rule fits: the forecaster decides per state, in the Data
issues box under the Forecast tab's anchor line, for the real-time week.

| Newest week | Choices |
|---|---|
| reads 0 | `abstain`, `level`, `extend`, `blend` (the Groundhog's rule for this state; the Oracle SIHRS keeps the 0); `set_aside` (both models from the week before, the 0 counted as unreported; offered for 1 or 2 trailing zeros after a positive week); `omit` (the state is left out of both files) |
| collapsed | `keep` (as reported, the default), `set_aside` (both models from the week before), `omit` |
| no row or blank | `carry` (the engines' own walk, the default), `omit` |

The choices are recorded in the run's spec (`extra["data_choices"]`: the week, the data file's sha256 and
each non-default state's issue, reported weeks and choice; `app/core/missing.py`), so a run with none has an
unchanged spec. A set-aside is matched by date and value against the data the run reads: when the data
changed since (Update data was pressed), nothing is trimmed and the run page says "not applied". A state
left out is listed on the Output page as requested and left out, with the reason. None of this marks a
run modified or changes its file names.

## An unreported newest week (own data)

The hub never has one (the table above: no NA and no absent row at the newest week), but a user's dataset
can leave its newest week out. Both members then read the week like a dropped one, so every horizon still
counts from the as-of date: the Groundhog's anchor moves back (`app/core/engines/analogue.py`, `_walk`), and
the particle filter's fit origin moves back with its forecast extended by the same number of weeks
(`pf_forecast_intervals = 4 + lag`, and `collect()` shifts by `weeks_dropped = lag`). Beyond 2 such weeks
past the requested trims (`MAX_ANCHOR_LAG`) the location abstains with the reason recorded. Each location
whose anchor moved is noted in the run record (`analogue_anchor_notes`, `pf_anchor_notes`) and summed on the
run page in one "Unreported newest weeks" row.
