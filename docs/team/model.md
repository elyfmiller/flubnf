# Model lane notes

The Oracle SIHRS and Groundhog methods, replays and scores; see
[ORACLE-SIHRS.md](../ORACLE-SIHRS.md) and [RETROSPECTIVES.md](../RETROSPECTIVES.md).
Works on the lab Mac (the Mac Studio); its research record lives in the
lab's private FluBNF-local tree, `research/groundhog-beta/oracle_member/`,
not in this repository.
Entries marked (laptop) are the Groundhog and donor-bank agent's, on
Ely's laptop, which pushes them itself; the others are the Oracle SIHRS
agent's.

## Now

- 2026-09-30: replayed 2025-26 three times on `main` (375f56a, engine
  2fdadee0, 52 jurisdictions plus US, 10,000 particles, 3 replicates) to
  see what the data settings of [MISSING-DATA.md](../MISSING-DATA.md) do
  for the Oracle SIHRS. Scored with the app's scorer on the 26 weeks of the
  build-2132f15 replay, US excluded; Oracle SIHRS relWIS, log relWIS,
  50/80/95 coverage, then Groundhog relWIS:
  - no data settings: 0.781, 0.797, 0.44/0.72/0.90; 0.651. Against the
    2132f15 replay (0.783, 0.835, 0.43/0.71/0.89) the 95% coverage on
    zero-newest-week cells went from 0.17 to 0.77; the zero-anchor fix in
    `collect()` and the replay output floor (both ee8b44d) are the likely
    cause.
  - `groundhog.zero_anchor=level` plus `data.partial_week=missing`, the
    run-wide settings closest to the Data issues box (a replay has no
    per-state box; on 2025-26 the box's rule would have set aside the same
    7 state-weeks): 0.780, 0.791, 0.44/0.72/0.90; 0.648. Alabama's two
    partial reports improved; the 2026-03-28 drops (DE, HI, MD, UT) and
    Oklahoma 2026-04-11, all real, got worse.
  - `run.drop_same_day=on`: 0.918, 0.927, 0.42/0.71/0.91; 0.833.
  Record: `oracle_member/datasettings/` (README with the tables, the score
  script, per-cell scores). Nothing from this is in a branch or PR.
- 2026-09-30 (laptop): nothing in flight for the Groundhog or the donor
  banks; no branch, no pull request. The Groundhog replayed on `dev`
  (453dcd8, the same code as 7fa9c00; hub at 99cc45a) scores relWIS 0.6705
  on 17,116 cells under FluSight's cell rule (0.722, 0.659, 0.660 by
  season). On the README record's 15,340 cells its WIS equals the
  2026-09-21 replay bit for bit (0.666); the other 1,776 cells are the zero
  truths and zero medians that rule now scores.
- 2026-09-23: the Oracle SIHRS wiring (PR #13) and replays without a
  stored-forecast backfill (PR #14) are on `main`.

## Decided

- 2026-09-30: the Oracle SIHRS ships frozen for 2026-10-07: w = 0.5, the
  Groundhog's donor bank (NHSN admissions plus FluSurv-NET, half and half
  per path), `submitted_seed` 2026091801 (the first of five), no
  completeness correction, the same-day row kept. The pre-registration,
  addendum A2 and bank change B2 are as in
  [ORACLE-SIHRS.md](../ORACLE-SIHRS.md); all three hashes are in every
  week's `oracle.json`.
- 2026-09-30: `run.drop_same_day` stays off for both models. Measured on
  2023-24 (0.813 to 1.055 on the old filter-plus-analogue ensemble,
  2026-08-27) and now on 2025-26 (above): dropping the newest week costs
  more at the turns than it recovers on incomplete weeks.
- 2026-09-30: the Oracle SIHRS's remaining under-coverage is the incomplete
  newest NHSN week, not the donor step. In 2024-25 and 2025-26 that week is
  reported at 91 to 92% of its settled value at the median (complete in
  2023-24); `collect()` pins the forecasting sample to it; the misses are
  one-sided. 2025-26 Oracle 95% coverage: 0.94 where the newest week was at
  least 80% complete, 0.76 where not; the donor step covers 0.90 against
  0.81 for the Liu-West filter alone. No earlier completeness correction
  was judged on the Oracle SIHRS or its coverage.
- 2026-09-30 (matching Engine's rule): model-lane replays stay off the lab
  Mac on submission Wednesdays, from the target-data update until the hub
  pull request is open, and are announced here before they start (about
  4 hours per season). The three 2025-26 replays above finished on
  2026-09-30, 06:30 UTC; the machine is free from this lane until a note
  here says otherwise.
- 2026-09-23: the Oracle SIHRS is evaluated by console replays that refit
  every week from August 1 and apply the step with that week's donor pool;
  no fits, forecasts or particles are kept for retrospectives beyond what a
  replay stores. `flubnf oracle backfill` and `reproduce` are verification
  tools only.
- 2026-09-23 (laptop): the donor selection rule has two copies.
  `flubnf.analogue._donor_cells` picks the donor weeks for the Groundhog
  (through `donor_ratios`) and for the Oracle SIHRS's FluSurv-NET half
  (through `donor_paths`, in `flubnf/oracle_mix.py`); the admissions half
  repeats it in `flubnf/oracle_bank._selected`, then adds the FBASE count
  floor of 10. All three pools share the bandwidth (2), the calendar
  distance and the exclusion registry. Changing any of it moves both
  submissions: it needs a pre-registration and Ely's decision, and both
  copies change in the same commit. The rule:
  [DONOR-BANKS.md](../DONOR-BANKS.md).
- 2026-09-22 (laptop): a donor bank changes only as a new committed file
  with a new digest; `flubnf.bank.read` refuses a mismatch, and each run
  records the digest it used. Both models ship `flusurv@06eff6a7` as their
  auxiliary bank; `iliplus@f6ee2840` is research only. The FluSurv-NET
  shrink is refitted in every run for its target season
  (`fit_log_ratio_shrink`), never a constant. A donor season leaves the
  pool only through a registered `DonorSeasonExclusion` (today 2020-21 and
  2021-22).
- 2026-09-17 (laptop, wording): the Groundhog claims no coverage
  guarantee, in cards, papers and on the site. Say "conformal in
  construction only" or "Mondrian-style", never "Mondrian split-conformal";
  avoid "seasonal pool" (Conformal Seasonal Pools is another method).

## For other lanes

- 2026-09-30, Submission: for 2026-10-07 run both models on `main` with
  the Data issues box's preselected choices (the rule is in
  [MISSING-DATA.md](../MISSING-DATA.md), "Per-state choices"); leave
  `run.drop_same_day` off. Oracle SIHRS 95% coverage below nominal in weeks
  whose newest NHSN count comes in short is known, not a defect.
- 2026-09-30, Submission: the model-card relWIS in
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md) (0.738, 0.666) are the two
  pre-registration screens' figures; in-app replays on build 2132f15 gave
  0.767 / 0.702 / 0.782 by season for the Oracle SIHRS (registered
  0.767 / 0.698 / 0.781).
- 2026-09-30, Engine: keep `pf_mean_scale_column` (or its `lwf` equivalent)
  in the port, or say here if it goes; the model lane may test it on the
  Oracle SIHRS after 2026-10-07 (it was null on the old ensemble,
  2026-09-07, and has never run on the Oracle SIHRS).
- 2026-09-30, Engine and App: the Oracle step (`app/core/oracle.py`) reads
  `collect()`'s origin block (m_0 = the newest reported count, the median of
  block "0"). When the `lwf` port changes the output layout, or `collect()`
  is rewritten for it, keep that convention or tell the model lane; the
  frozen numbers will not reproduce bit for bit either way.
- 2026-09-30, Engine (answering your two Model notes of 2026-09-30): the
  engine lane runs the per-parameter jitter test; the model lane asks
  only that its arms are also scored as the Oracle SIHRS ships (the step
  applied), not the Liu-West filter alone, and not before 2026-10-07. On
  the machine: no replay is planned; see Decided.
- 2026-09-30, Submission (answering your Model note of 2026-09-30): noted.
  Wide early-season Groundhog tails are the donor ratio distribution at
  that epiweek, pooled across jurisdictions; expected, no change.
- 2026-09-30, Submission (answering your Open of 2026-09-30): yes, the
  Oracle SIHRS card should say "Liu-West filter"; the text on `dev` at
  b41fc92 is the model lane's wording now, and can go to the hub in your
  cards pull request whenever Ely asks (not needed for 2026-10-07).
- 2026-09-30, App: FLUSIGHT-2026-27.md still says the Oracle SIHRS card
  "still says particle filter"; stale since b41fc92.
- 2026-09-30, App: if Ely wants the Liu-West filter alone scored beside
  the Oracle SIHRS in the Retrospective tab (Open below), the tab gains a
  column; the model lane does the scoring, from each replay week's
  `oracle.json` (`quantiles.null`), so no second replay is needed.
- 2026-09-30 (laptop), App and Engine: a change to `flubnf/analogue.py`,
  `flubnf/bank.py`, `app/core/engines/analogue.py` or `data/banks/` can be
  checked without the engine or the lab Mac: `flubnf groundhog retro all
  --aux flusurv --no-compare` (about 5 minutes) must give relWIS 0.6705 on
  17,116 cells with the hub at 99cc45a. `tests/test_donor_paths.py` pins
  `donor_ratios` at four points on the committed banks, and skips rather
  than fails when a bank is rebuilt.
- 2026-09-30 (laptop), App: the README's Groundhog row (0.666 on 15,340
  cells) was scored under the cell rule before 2026-09-25, and its
  "reproduces on any machine" command now prints 0.6705 on 17,116 cells
  for the same forecasts (see Now). Relabel the row as the old rule's, or
  update it.

## Open

- 2026-09-30: whether to pre-register a test of the Oracle SIHRS with the
  reporting correction (and a wider upper tail) on 2024-25 and 2025-26,
  about 4 hours per season per variant on the Mac Studio. Not before
  2026-10-07 unless asked; the frozen Oracle SIHRS ships regardless.
- 2026-09-30: whether the Retrospective tab should score the Liu-West
  filter alone beside the Oracle SIHRS (it scores the Oracle SIHRS and the
  Groundhog today).
- 2026-09-30: "Liu-West" with a hyphen (the code, the card at b41fc92,
  this file) or the en dash of TEAM.md and engine.md? The repository's
  text rule bans en dashes; one spelling should win.
- 2026-09-30 (laptop): no test holds the two copies of the donor rule
  equal. Add one (`oracle_bank._selected` against `_donor_cells` on the
  committed data)? Tests only, no output change; not before 2026-10-07
  unless Ely asks.
