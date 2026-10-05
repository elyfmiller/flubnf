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

- 2026-10-01 (evening, done 2026-10-02 06:00 UTC): at Ely's request, the
  three season replays on the Mac Studio's console (2023-24, 2024-25,
  2025-26; all 53, made before A3, so their US row is the filter alone)
  were copied and given the A3 US row from their own stored filter
  samples, no refit, and exported as bundles (the research 2025-26 arm
  with 31 weeks too). US cell, FluSight's cell rule, filter alone to with
  the step: 2023-24 0.724 to 0.656 (120 cells; 95% coverage 0.97 to 0.99),
  2024-25 0.690 to 0.552 (96 cells; 0.86 to 0.97), 2025-26 0.895 to 0.783
  (88 cells; 0.72 to 0.91); the research arm 0.871 to 0.763 (108 cells).
  The states' pooled figures are unchanged in every season (0.767, 0.702,
  0.783, 0.778). Bundles: `oracle_member/a3_replays/bundles/`. Method: the registered
  step on the US cell with the week's recorded vintage (every hash
  verified), states as stored, the week's oracle.json and sidecar updated,
  the season re-scored, then exported as replay bundles for the console's
  Retrospective import (read-only archived entries; the live replays are
  never written). The research 2025-26 arm with 31 weeks gets the same.
  Script `oracle_member/us_national/a3_backfill_replays.py`; outputs under
  `oracle_member/a3_replays/`. Mac Studio load: minutes of scoring per
  season, nothing on a Wednesday.
- 2026-10-01: addendum A3 frozen and wired (Ely's decision, Decided).
  Commit d5bd68b on `dev`: `flubnf.oracle.ADDENDUM_A3_SHA256` and
  `US_KEY = "0"`; `app/core/oracle.py` apply_week sends the US cell through
  the step under that key and records `rng_key` and the hash (only a
  location without a FIPS key stays outside); the backfill meta and the
  page copy carry the hash; `us_national.PF_US_NOTE` covers stores from
  before A3; [ORACLE-SIHRS.md](../ORACLE-SIHRS.md) section 5c; tests.
  Pull request from `dev` to `main` opened on 2026-10-01 with `gh` (see
  For other lanes), at Ely's request; Ely merges.
  Checked on the day: the dry run's six fitted states reproduce the
  shipped provenance bit for bit; the US cell equals the research
  computation on the dry run and on all 93 stored weeks of the three
  replayed seasons (record `oracle_member/us_national/step/fidelity_a3_2026-10-01.json`).
  Every test in `tests/` and `app/tests/` passes except the vendored
  hub-schema check, which fails against the lab hub clone because that
  clone is from July (For other lanes, Submission). The pull request from
  `dev` to `main` is open; Ely merges, then pulls `main` and runs the
  newest data to see the US forecast with the step. No Mac Studio time was used beyond seconds; nothing on a
  Wednesday.
- 2026-10-01: the registered Oracle step applied to the US cell, tested
  at Ely's request (Decided below). Mac Studio use for it is over (two
  US-only replays, 11 and 13 minutes, on 2026-10-01 UTC; nothing on a
  Wednesday).
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

- 2026-10-01 (Ely): addendum A3 is frozen and applies from the first
  round, 2026-10-07: the Oracle step covers the US national cell as it
  covers the 52 jurisdictions, RNG key 0, nothing else changed; the hash
  (8a3552bc...) joins the other three in every week's oracle.json. This
  supersedes the decision of 2026-09-30 below (the fitted US row as is).
  Ely's reasons, in chat: the three-season table, the real-time weight of
  the US row (the FluSight ensemble and CDC's published national forecast;
  the season score leaves it out, For other lanes), and the team's own
  standard for its national forecast. `PREREG_oracle_member_ADDENDUM_A3.md`
  in the research tree records the decision with the verbal-authorization
  caveat of the earlier freezes.
- 2026-10-01 (finding, read by Ely before the decision above): the registered step
  applied to the US cell beats the shipped US row in all three replayed
  seasons, US cells only, FluSight's cell rule, relWIS shipped to with the
  step: 2023-24 0.724 to 0.656, 2024-25 0.754 to 0.584, 2025-26 0.871 to
  0.763; 95% coverage 0.97 to 0.99, 0.83 to 0.95, 0.73 to 0.93; five seeds
  within 0.001. The dry-run week would read 2,785 / 3,189 / 3,542 / 3,858.
  The research script reproduces the shipped step bit for bit on states;
  the only new convention is RNG key 0 for US. As on the states, the gain
  sits in the rise and the decline and the step loses across the peak
  turn. Record: `oracle_member/us_national/README.md` section 6; draft
  `PREREG_oracle_member_ADDENDUM_A3_draft.md`; two independent checks.
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

- 2026-10-01, App (a bug report from Ely, via the model lane): after the
  A3 merge Ely reran the 2026-10-03 forecast on the laptop (run 10-01
  10:04; the Forecast chart shows the US row with the step, the Output
  card shows that run, 53 of 53, passes the hub's checks), then downloaded
  the two CSVs and the weekly report again, agreeing to overwrite the
  previous day's copies. The files that arrived were byte for byte the
  previous day's: the US row at 2,704 / 2,645 / 2,311 / 1,872 and the
  report naming app build 4e251d6 and the earlier run's wall time. Ely
  asks for a small investigation. What the code says: the Output card's
  CSV links carry the chosen run's own path (`/output/download?path=`),
  so a freshly loaded page links the new run; the report button is the
  same URL every day (`/output/report/download`) and the dated report
  download serves the archive folder. Candidates, in the order the model
  lane would check: an Output tab loaded before the run and not reloaded
  (old links, same filenames); a cached response on the same-URL report
  download (FileResponse sets no Cache-Control); the archive keeping the
  earlier run (the 10:04 run's results.json `outcome.archived` reads
  "kept: ..."), with downloads taken from a dated view; the browser
  saving "(1)" copies while the old files stayed. Whatever it is,
  `Cache-Control: no-store` on both download routes and a run id in the
  report download URL would remove two of the four. Update, same day:
  Ely sent the 10:04 run's results.json. It is the new run (A3 bank
  label, `research` false, 53 locations, Delaware's zero levelled as
  recommended) and its stored US quantiles are the step's, medians
  2,785.7 / 3,189.5 / 3,542.3 / 3,858.1, so the run's own files are new
  and the server computed the right thing. The question left is which
  file the download served; the archive for the date is keyed by the
  as-of date (`archive/2026-09-26/`), and its archive.json names the run
  it holds. Ely sent that too: run 20261001T100424-677678, complete and
  full, archived 17:09 UTC. So the archive and the run folder both hold
  the new files, and the kept-archive candidate is out. What remains is
  an Output tab loaded before the run (its CSV links name the earlier
  run's folder, which the download route serves as readily as the new
  one) or a cached same-URL report download. Both are closed by the same
  two changes: `Cache-Control: no-store` on the download routes, and
  links that cannot go stale (the run id in the report URL, and a reload
  of the Output page when a run finishes, or a check in the download
  route that the file is the date's chosen one).
- 2026-10-01, Engine and Model (the lab Mac lanes): the GitHub CLI is on
  the Mac Studio since today (`gh` 2.102.0 in `/usr/local/bin`, on every
  shell's PATH), logged in as elyfmiller with a fine-grained token that
  Ely scoped to elyfmiller/flubnf only (pull requests read and write,
  contents read; stored in the login keychain; git stays on SSH). So a lab
  lane can now open a pull request from `dev` to `main` itself, with
  `gh pr create --base main --head dev`, still only when Ely asks, and
  with no attribution lines in the description (TEAM.md). The token cannot
  reach cdcepi/FluSight-forecast-hub, by construction. Ely set it up on
  2026-10-01 at this lane's request; `~/.config` had been root-owned and
  Ely took it back with chown.
- 2026-10-01, Submission: before 2026-10-07, pull the lab hub clone
  (`~/GitHub/FluSight-forecast-hub`, now at 18f68c23 of 2026-07-15). Its
  `tasks.json` lists reference dates only to 2026-05-30, so
  `validate_submission.R` run against it cannot pass a 2026-10-10 file;
  the hub at 09c96ec8 (2026-09-30) lists them to 2027-05-29. The same
  staleness fails the console's vendored-schema test on this machine.
  Also: from this round the Oracle SIHRS file's US row is the step's
  output (A3), 53 locations and the same quantile rows as before; the
  checks in the week's `oracle.json` are `addendum_a3_sha256` and
  `locations.US.state` ("both"), with `cells.outside_member` empty.
- 2026-10-01, App: three places describe the US row as outside the step
  and are yours: the two bullets at the end of
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md) (now: the step covers US
  from round one, A3 frozen 2026-10-01); `retro_season.html`'s tile phrase
  "the particle filter without the Oracle step" with `us_national.PF_US_SHORT`
  and the comment near its US row; player.js's note comment. The long note
  `PF_US_NOTE` now covers both eras in words (commit d5bd68b). A
  provenance-aware split, if you want one: a store from before A3 lists US
  under `cells.outside_member` in its oracle.json; a store since does not.
- 2026-10-01, Submission and whoever keeps
  [FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md): the CDC's season
  evaluation does not score the US row. The 2025-26 report (published
  2026-09-30,
  https://www.cdc.gov/flu-forecasting/evaluation/2025-2026-report.html)
  says its scoring left out national forecasts because of their scale,
  and Puerto Rico because of data availability; its headline metric is
  the season's average relative WIS over the jurisdictions, excluding
  national. The 2024-25 report left out national forecasts too. The 75%
  rule counts forecasts over the weeks and jurisdictions that remain after
  those exclusions. The US row still counts in real time: the FluSight
  ensemble is the per-location median of the designated models, and the
  national ensemble is the forecast CDC publishes. The guide's Evaluation
  row could say so in one line.
- 2026-10-01, Engine (answering your change-tracking note of 2026-10-01):
  read, nothing needed. It agrees with this lane's dry-run finding: the
  weekly filter does not adapt out of a structural miss, so the early
  turn (the i0 seed, Decided) is not something the filter corrects; the
  Oracle step is the brake. The falling-r alarm is noted and untested on
  the SIHRS; this lane will not test it before 2026-10-07.
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
- 2026-10-05 (laptop), Submission (answering your note of 2026-10-05 to
  all lanes): agreed on all three points; the Groundhog and donor-bank
  side has nothing to merge before the 2026-10-10 hub pull request.
  `main` 663b5a2 has the Groundhog and donor-bank files unchanged since
  2026-09-30 (banks `flusurv@06eff6a7`, `iliplus@f6ee2840`). Ely's laptop,
  checked read-only on 2026-10-05:
  - FluBNF on `main` at 663b5a2, no local changes; the engine checkout on
    `feature/particle-filter` 2fdadee0, no local edits, and the app calls
    it the production build; R has hubValidations 2.1.1 for
    `scripts/validate_submission.R`.
  - The hub copy (`~/Documents/GitHub/FluSight-forecast-hub`, the path
    the app reads) is at 652d87c, behind CDC's ee477e7: "Update data"
    before the run, as planned.
  - Three full runs of both models already completed on this laptop
    (as-of 2026-09-26, on 2026-09-30 and twice on 2026-10-01): 53
    locations, all 159 fits ok (53 times 3 replicates), the Oracle step
    applied, about 5 minutes from reading the data to both files. The two
    of 2026-10-01 already carry A3 (`addendum_a3_sha256` in `oracle.json`;
    the US row comes out of the step, where the 2026-09-30 run left it
    outside). The round does not need the lab Mac.

## Open

- 2026-09-30, decided (a) above; kept for the record: the options were
  (a) keep the fitted US (frozen spec; at 25% a week the h3 truth is
  about 6,100, inside the band's 8,381 but far above the 1,872 median),
  (b) a sum of states (not valid as built, see Decided), (c) leave US out
  this round (valid, reversible weekly). The model lane had recommended
  (c). The 13 declining states are the same mechanism halved by the step
  plus noise (Illinois lam_T -0.41, Montana -0.27); nothing beyond it.
- 2026-10-01, for Ely: merge the A3 pull request (`dev` to `main`,
  commit d5bd68b plus notes; `dev` carries docs only beyond that), pull
  `main` on the laptop and run the newest data (the 2026-09-30 release)
  to see the US forecast with the step. Decided on
  2026-10-01 (kept for the record): freeze A3 for the first round, or
  hold it for round two; frozen for the first round.
- 2026-09-30, superseded by the entry above (kept for the record): whether
  to amend the pre-registration so the step is applied to the US cell too
  (addendum A3). A freed or re-seeded i0 is NOT the candidate: it was tried
  three times and closed (swarm-carry stage 1B, 2026-09-04/05: FITI0 0.889
  and hindsight ORACLE 1.047 against 0.749 for production, declined by Ely
  on 2026-09-05; the donor-informed i0 priors of the anchor study,
  2026-09-19: null). Freeing i0 gives the right level and no brake; the
  Oracle step is the brake, and the frozen spec keeps US outside it. The
  amendment can be checked without refits (`flubnf oracle backfill` on the
  three replayed seasons' stored US samples), minutes on the Mac Studio,
  only after Ely says so.
