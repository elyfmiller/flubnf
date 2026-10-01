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

- 2026-09-30: the dry run's falling US forecast (Ely's question of
  2026-09-30), investigated and answered; the findings and the options are
  under Decided and Open, the full record with the diagnostics is
  `oracle_member/us_national/README.md`. Mac Studio use for it is over
  (five short fits on 2026-09-30). Nothing in the frozen Oracle SIHRS, the
  code or the submission changed.
- 2026-09-30: Submission's validation request done. Vintage run, forecast
  date 2026-01-10, all 53 jurisdictions, Oracle SIHRS only, every setting
  at its default, no Data issues flagged for that vintage; console build
  7fa9c00, engine 2fdadee0, hub clone 18f68c23. The file
  `2026-01-17-NAU_PyBNF-OracleSIHRS.csv` (4,876 rows, 53 locations,
  integers; 52 active cells, US outside the step as designed) is GREEN:
  28 of 28 hubValidations checks. Copy with the validator's output and
  the run's `oracle.json`: `oracle_member/datasettings/validation_2026-01-10/`;
  the file also went to Ely.
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

- 2026-09-30 (Ely): for 2026-10-07 the Oracle SIHRS file keeps its fitted
  US row as the frozen spec produces it (option a below): Ely is
  comfortable with the shape, an early-season turn a mechanistic model of
  this kind can show. US is not left out and not replaced by a sum of
  states.
- 2026-09-30 (finding, for Ely's decision below): the dry run's falling US
  row is not the national fit's alone. The Liu-West filter alone, refitted
  for all 53 locations (bit-identical US: 2,704 / 2,645 / 2,311 / 1,871),
  has its h3 median below the current count in 42 of 52 states and in 24
  of the 28 states that rose 50% or more over four weeks; the states'
  filter-alone medians sum to 2,705 / 2,717 / 2,442 / 1,995, the US path.
  The states rise in the dry run only because the Oracle step blends in
  past-season donor growth (California: filter alone 410 to 230, Oracle
  SIHRS 424 to 574). Not filter health (ESS 754 to 5,500 of 10,000, no
  degenerate step), not the newest week (the h0 median is above it), not
  the harmonic (phi1 19.8, factor 1.04 and rising).
- 2026-09-30 (finding): the cause is the pinned initial infected fraction
  (`flubnf/sihrs_fit.py resolve_state`): i0 = first week x 0.18 /
  (season-to-date admissions x gamma), large while the cumulative is small
  (US 4.9e-3, 1.65 million infectious on August 1). To match 657 weekly
  admissions from that many infections the filter takes mult 0.0077, which
  makes the 11,107 admissions since August 1 mean 72 million infections
  (21% of the US): S/N 0.85 to 0.65 by week 8, R_eff below 1 at week 9, a
  peak at week 10. A deterministic SIHRS at the fitted medians reproduces
  the data and the forecast. The filter moves parameters, never the
  depleted state. Refitting with i0 free (the research option `fit_i0`)
  gives i0 9e-4, mult 0.045 and a rising US forecast (3,070 to 5,454, h3
  band 440 to 108,000). The same early-season turn is in every stored
  replay (2025-26 at 2025-08-30 and 09-20, 2023-24 at epiweeks 38 to 41,
  fitted US flat to falling while the truth rose, inside the 95% band) and
  fades by November as the cumulative grows.
- 2026-09-30 (finding, option b): the console's sum-of-states US
  (`retro.national_aggregate`, draws summed by index, states independent)
  is a scoring device with no writer path, and on the 2025-26 replay it
  scores relWIS 1.038 with 50/80/95 coverage 0.10 / 0.28 / 0.46 against
  0.871 and 0.24 / 0.47 / 0.73 for the fitted US: far too narrow. Not
  valid for a submission as built.
- 2026-09-30 (finding, option c): leaving US out of the Oracle SIHRS file
  is valid: every location is optional in the hub's tasks.json, the
  Forecast form unticks US without a code change, the Groundhog file keeps
  its US row, CDC's inclusion rule is 75% of targets.
- 2026-09-30 (Ely): the pre-registered coverage test (reporting correction,
  wider upper tail) is on hold; Ely and this lane go over the data-settings
  replays together first. Nothing runs for it.
- 2026-09-30 (Ely): the Retrospective tab scores the Liu-West filter
  alone beside the Oracle SIHRS; the App lane built it (1064557, 9a4a689)
  and the model lane checked it (For other lanes).
- 2026-09-30 (Ely): hubValidations 2.1.1 is installed on the Mac Studio
  (R 4.6, system library), so `scripts/validate_submission.R` runs there
  on every Oracle SIHRS file before it goes to the hub.
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
- 2026-10-01 (laptop): the donor-rule plan is agreed (the Oracle SIHRS
  agent's answer above): after 2026-10-07 that agent makes
  `oracle_bank._selected` a thin wrapper over `analogue._donor_cells`
  (made public as `donor_cells`), landing only if the donors, their order
  and the Oracle suites stay bitwise.
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

- 2026-09-30, Submission: the Oracle SIHRS file for 2026-10-07 carries the
  fitted US row as the frozen spec produces it (Ely's decision, Decided).
  Its median falls while the states' rise; that is known and explained
  (the i0 seed, Decided), not a defect to fix on the day.
- 2026-09-30, App (answering your note of 2026-09-30): checked. On the
  2025-26 no-settings replay your `pf_filter` scoring gives, on the 26
  weeks, relWIS 0.846, log relWIS 1.011, coverage 0.369 / 0.621 / 0.807
  (31 weeks: 0.849, 1.009, 0.363 / 0.617 / 0.814); this lane's own
  scoring of the same `quantiles.null` without the floor gave 0.846,
  1.012, 0.369 / 0.621 / 0.806 (31 weeks: 0.849, 1.010, 0.362 / 0.617 /
  0.814). The Groundhog's floor moves nothing past the third decimal. The
  Oracle SIHRS and Groundhog rows match too.
- 2026-09-30, Submission (answering your request of 2026-09-30): GREEN,
  see Now. The card the validator used is FluBNF's
  `model-metadata/NAU_PyBNF-OracleSIHRS.yml` on `dev` (its note said the
  hub did not hold the card yet, as a first-submission pull request).
- 2026-09-30, Model (laptop) (answering your donor-rule plan of
  2026-09-30): agreed. The Oracle SIHRS agent writes it after 2026-10-07
  (`oracle_bank.py` is its file). Gates before it lands: same donors in
  the same bank order (the per-path draws index into it),
  `tests/test_donor_paths.py`, `FLUBNF_ORACLE_FULL=1` on
  `tests/test_oracle.py` and `tests/test_oracle_mix.py` bitwise against the
  registered screens, and `flubnf oracle reproduce`. The `epiweek` cache
  question is checked by timing one weekly pool build before and after.
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
- 2026-10-01 (laptop), App (answering your dry-run question 1): yes. On
  the 2026-09-21 record (52 states, 15,340 cells, US not scored), binned by
  each cell's own h0 median, the Groundhog's 95% coverage is 0.87 under
  20, 0.95 at 20 to 50, 0.975 at 50 to 200 and 0.99 at 200 or more (50%:
  0.36, 0.52, 0.54, 0.59). The pooled 0.95 averages under-coverage on
  small series with over-coverage on large ones; Florida, Texas,
  California and New York cover 0.99 to 1.00. A size-aware spread (or a
  national donor set for US) is a post-2026-10-07 candidate and needs a
  pre-registration; nothing changes for the first round.
- 2026-10-01 (laptop), App: thanks for the README fix (821c2e78), which
  matches the replay. Two small things: the paragraph after it now starts
  "or from the console", a fragment of the sentence the new paragraph
  split; and app.md cites the fix as 02cc23e, which is not a commit.
- 2026-09-30 (laptop), App and Engine: a change to `flubnf/analogue.py`,
  `flubnf/bank.py`, `app/core/engines/analogue.py` or `data/banks/` can be
  checked without the engine or the lab Mac: `flubnf groundhog retro all
  --aux flusurv --no-compare` (about 5 minutes) must give relWIS 0.6705 on
  17,116 cells with the hub at 99cc45a. `tests/test_donor_paths.py` pins
  `donor_ratios` at four points on the committed banks, and skips rather
  than fails when a bank is rebuilt.

## Open

- 2026-09-30, decided (a) above; kept for the record: the options were
  (a) keep the fitted US (frozen spec; at 25% a week the h3 truth is
  about 6,100, inside the band's 8,381 but far above the 1,872 median),
  (b) a sum of states (not valid as built, see Decided), (c) leave US out
  this round (valid, reversible weekly). The model lane had recommended
  (c). The 13 declining states are the same mechanism halved by the step
  plus noise (Illinois lam_T -0.41, Montana -0.27); nothing beyond it.
- 2026-09-30, after 2026-10-07, for Ely: whether to amend the Oracle
  SIHRS pre-registration so the step is applied to the US cell too
  (addendum A3). A freed or re-seeded i0 is NOT the candidate: it was tried
  three times and closed (swarm-carry stage 1B, 2026-09-04/05: FITI0 0.889
  and hindsight ORACLE 1.047 against 0.749 for production, declined by Ely
  on 2026-09-05; the donor-informed i0 priors of the anchor study,
  2026-09-19: null). Freeing i0 gives the right level and no brake; the
  Oracle step is the brake, and the frozen spec keeps US outside it. The
  amendment can be checked without refits (`flubnf oracle backfill` on the
  three replayed seasons' stored US samples), minutes on the Mac Studio,
  only after Ely says so.
