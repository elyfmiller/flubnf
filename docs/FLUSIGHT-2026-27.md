# FluSight 2026-27: the season at a glance

What the team needs for the weekly CDC FluSight rounds with FluBNF: the
hub's rules, the NAU_PyBNF models, the weekly routine, the pitfalls and the
open decisions. Checked against this repository and cdcepi/FluSight-forecast-hub
(README.md, hub-config/tasks.json, admin.json, model-output, model-metadata and
target-data READMEs) on 2026-09-30. Update it when CDC or the team changes
something; say what changed and when.

## The season (from the hub's README, admin.json and tasks.json)

| Item | Value |
|---|---|
| First due date | Wed 2026-10-07, 11 PM US/Eastern (reference_date 2026-10-10) |
| Last round | reference_date 2027-05-29 (34 rounds); dates may shift with activity |
| Due window | Sunday to Wednesday before the reference date; no late files |
| reference_date | the Saturday after the due Wednesday (end of that MMWR week) |
| target_end_date | reference_date + 7 x horizon |
| Horizons | -1 (unscored hindcast), 0, 1, 2, 3 |
| Locations | "US", 50 states, "11" (DC), "72" (PR): 53 FIPS strings |
| Quantiles | 0.01, 0.025, 0.05 to 0.95 by 0.05, 0.975, 0.99 (23 levels) |
| Ensemble | built Thursday mornings from valid files received by the deadline |
| Evaluation | at least 75% of hospital-admission quantile targets (h0-h3); WIS, relative WIS (log scale), 50/95% coverage; scored on end-of-season data. CDC's season evaluation leaves out national forecasts (2024-25 and 2025-26) and, in 2025-26, Puerto Rico, and the 75% rule counts over the weeks and jurisdictions that remain; the US row still counts in real time (the FluSight ensemble is the per-location median, and its national forecast is the one CDC publishes) |

### Targets (all optional; the first is the primary one)

1. `wk inc flu hosp`: weekly NHSN flu admissions. Quantiles, integers from
   this season. Optional `sample` output: 100 trajectories per task.
2. `wk inc flu prop ed visits`: NSSP proportion of ED visits due to flu,
   0 to 1. Quantiles (plus optional samples). CDC's first priority among the
   optional targets; kept ready in case CDC switches its headline target.
3. `wk flu hosp rate change`: pmf over large_decrease, decrease, stable,
   increase, large_increase against the week before reference_date.
   Stable / large cut-offs per 100k: h0 0.3/1.7, h1 0.5/3, h2 0.7/4, h3 1/5.
   A change of fewer than 10 admissions is stable.
4. `peak week inc flu hosp`: pmf over the 34 Saturdays of the season;
   horizon and target_end_date blank.
5. `peak inc flu hosp`: quantiles of the season's peak weekly admissions.
   Keep submitting both peak targets after the peak.

New this season (per the 2026-27 docs): integer values for the two admission
targets; plausibility checks (admissions quantiles at most 30% of population,
ED at most 25%); optional metadata fields `baseline_model` and
`designated_targets`.

### File rules

- `model-output/<team>-<model>/<reference_date>-<team>-<model>.csv`; one file
  per week holds every target.
- Exactly these columns: reference_date, target, horizon, target_end_date,
  location, output_type, output_type_id, value.
- Submit by pull request to cdcepi/FluSight-forecast-hub; GitHub Actions runs
  hubValidations and comments on the PR.

### Ensemble designation (CDC email, 2026-09-30)

- Up to two designated models per target per team; e.g. two for the
  hospital-admission quantiles and two for the ED target.
- More than two methodologically distinct models for one target: email
  flusight@cdc.gov with out-of-sample evidence and/or a description of the
  methodological differences.
- Extra non-designated models are welcome; baseline models must not be
  designated. `designated_targets` in the metadata limits which targets a
  designated model counts for.

### Target data

- Admissions: NHSN Weekly Hospital Respiratory Data, `totalconfflunewadm`.
  Preliminary release Wednesday (data.cdc.gov mpgq-jmmr), official Friday
  (ua7e-t2fy). Recent weeks are revised; treat the newest week with care.
- ED visits: NSSP (data.cdc.gov rdmq-nq56), `percent_visits_influenza` / 100,
  state rows; hub file updated Wednesday by midday.
- Hub files: `target-data/target-hospital-admissions.csv`,
  `target-data/target-ed-visits-prop.csv`, plus hubverse `time-series.csv`
  and `oracle-output.csv`. Past vintages: `auxiliary-data/target-data-archive/`
  and Delphi Epidata.
- CDC said on 2026-09-30 that it has started updating the target data.

## The team and its models

Team `NAU_PyBNF` (registered 2026-09-22; the old `LosAlamos_NAU` team is
retired). Both models are `designated_model: true`, which is within the
two-per-target limit for the admissions target.

| Model id | Key | Method |
|---|---|---|
| `NAU_PyBNF-OracleSIHRS` | `pf` | SIHRS compartment model (BNGL) fitted weekly by the Liu-West filter (10,000 particles per jurisdiction from Aug 1) in a private PyBNF fork, whose output is a forecasting sample (not an exact posterior), then the "Oracle step": each path's growth blended 50/50 (geometric mean) with a donor growth path from an earlier season at the same calendar week (within 2 epiweeks); donors half NHSN, half FluSurv-NET |
| `NAU_PyBNF-GroundHogCGR` | `analogue` | last observed count x empirical quantiles of growth ratios at the same epiweek in earlier seasons, pooled across jurisdictions, with a FluSurv-NET donor bank; no fitting, no engine needed |

Recorded pooled relative WIS (ratio of sums vs FluSight-baseline, replays of
2023-24 to 2025-26, not real-time): Oracle SIHRS 0.738, Groundhog 0.666.
These are the pre-registration screens' figures; in-app replays on build
2132f15 gave the Oracle SIHRS 0.767 / 0.702 / 0.782 by season (see
[team/model.md](team/model.md)).
The 2026-27 season is the Oracle SIHRS model's first prospective test.

### What FluBNF produces

- By default: `wk inc flu hosp` quantiles, horizons 0-3, all 53 locations
  (US fitted directly; can be unticked), whole numbers kept monotone.
- Optional knobs: `output.horizon_minus1` (adds h -1) and
  `output.rate_change_pmf` (adds the rate-change pmf).
- Not produced: the ED-visit target, both peak targets, sample output.
  For 2026-27 the team submits the weekly admissions target only (below).

## Weekly routine (Sunday to Wednesday)

1. Open FluBNF (FluBNF.command / FluBNF.app on Mac, FluBNF.bat or the Start
   menu entry on Windows). It updates itself and the engine on open; the
   console is at http://127.0.0.1:8710.
2. Data tab: "check for new data", then "Update data" (fast-forwards the hub
   clone). Hub clone: `~/GitHub/FluSight-forecast-hub` (Mac/Linux) or
   `%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub` (Windows); override with
   `FLUBNF_HUB`. Wednesday's preliminary NHSN release is the one that counts.
3. Forecast tab: the date defaults to the newest Saturday in the data (the
   as-of week); reference_date = as-of + 7 days. Review the Data issues box
   (per-state choices for gaps, zeros, partial weeks) before running.
4. Run both models. Real-time runs read the live file only when its newest
   week equals the as-of; otherwise they use a dated vintage.
5. Output tab: check the hub-check badge and the due / soon / closed badge.
   Files land in `app/state/archive/<forecast_date>/`. For the authoritative
   check: `Rscript scripts/validate_submission.R <file.csv> <hub_clone> --window`
   (or `python scripts/validate_submission.py ...`).
6. Upload: FluBNF only writes files. Copy each into
   `model-output/NAU_PyBNF-<model>/` in a fork of the hub and open a PR before
   11 PM Eastern Wednesday; fix anything the validation comment flags.

### Useful commands

- `flubnf doctor`: environment and engine check.
- `flubnf engine-update`: move a clean engine checkout to the production build.
- `flubnf knobs ...`: settings; changed settings without an override write
  `<model_id>-modified` files, which are not hub names.
- `flubnf retro <season>` / `flubnf groundhog retro all --aux flusurv`: replays.
- There is no CLI for the weekly run or the submission; use the console.

### Engine

- Production build: `feature/particle-filter` at `2fdadee0` (bngsim 0.15.1),
  pinned in `app/core/engine_build.py`. A different build only warns.
- The fork is private: a machine needs GitHub access to it, or the lab's
  `pybnf-pf-2fdadee0.tar.gz` archive. Without the engine only Groundhog runs.
- A retrospective resumes only on the engine build it was fitted with.

### Naming and the public PyBNF port (agreed 2026-09-30)

- The PyBNF maintainer (Bill Hlavacek) agreed that the Liu-West filter goes
  into public lanl/PyBNF as `job_type = lwf` ("Liu-West Particle Filter", its
  own `filter` family, settings prefixed `lwf_`), beside an exact sampler,
  IBIS (lanl/PyBNF#973), to be built later. The Liu-West filter is the fast
  real-time option; IBIS will give the exact fixed-parameter posterior.
- Wording: "The Oracle SIHRS is fitted weekly by the Liu-West filter." Its
  output is a forecasting sample of drifting parameters, never a posterior.
  Once IBIS exists, do not say "particle filter" unqualified.
- Production SIHRS fits five parameters (Reff, eps1, phi1, mult, r); notes
  listing seven (with eps2, phi2) are stale.
- The port is on a local, unpushed branch `feat/particle-filter` of the team
  lead's PyBNF fork.

What does not change now: production keeps its own engine (the pin above,
installed non-editable, Python 3.10 on the lab Mac) and the console keeps
writing `pf_*` keys. Rename nothing in FluBNF (model ids, the `pf` key, the
conf writer, the engine pin) until the team lead starts the migration.

What the migration will need later:
- Python 3.12 or newer and bngsim 0.15 or newer (rebuild the engine venv).
- Conf writer: `pf_*` keys become `lwf_*`; edition-2 confs (`experiment:` and
  `noise_model <obs> = neg_bin, dispersion = fit r, location = mean,
  cumulative` in place of `objfunc = neg_bin_dynamic` and
  `pf_cumulative_observable`); `pf_seed` becomes `random_seed`;
  `pf_start_time` and `pf_sampling_interval` are retired (gaps need explicit
  NaN rows); `wall_time_fit` exists, off by default.
- Output readers: check `params_*.txt`, `traj_noise_*`, `ess_*.txt`; names
  and layout may change.
- Results will not be byte-identical (new random-number source and
  likelihood path): show statistical equivalence against the production
  record on matched cells before switching.

Engine findings to respect:
- Choosing the jitter automatically by one-week-ahead predictive score was
  tested and rejected (six-state panel: PF relWIS 0.814 vs 0.773 for a fixed
  0.15, worse at the hard phases, narrower bands). Do not propose it again.
- A private branch (`pf/forecast-fixes-noauto`) adds per-parameter jitter,
  never moves parameters that only set the initial state, and says in the
  run log that the output is a forecasting sample. Not in production.
  Planned: per-parameter jitters for SIHRS against a single 0.15.
- The private engine's `pf_continue` silently ignores revised earlier rows.
  Production refits from scratch each week so it is unaffected, but no
  carried-swarm feature may rely on `pf_continue` with revised data
  (upstream `lwf` refuses a revised row instead).

## Pitfalls to check first

- Writer gates: all 23 quantiles, monotone, no negatives, no zero-width
  distribution. A defect in one location drops that location (listed in
  `submission_dropped`); a file-level defect refuses the whole file.
- Missing data is dropped, never imputed. A newest week of 0 makes Groundhog
  abstain unless a per-state zero-anchor choice is made.
- Holiday weeks: the hub often skips archiving a vintage; backdated runs then
  need the nearest earlier vintage. There is no holiday calendar in FluBNF.
- Revisions: the newest NHSN weeks move; compare Wednesday preliminary with
  Friday official when a state jumps.
- The hub clone must be its own git repository or updates are refused.
- Plausibility flags (30% of population) are new; the FluSight team can
  override a flagged value if it is real.
- Timezone: the deadline is 11 PM Eastern and Arizona keeps no daylight
  saving time: that is 8 PM in Flagstaff while the East is on daylight time
  (through 2026-10-28 and from 2027-03-17), 9 PM from 2026-11-04 to
  2027-03-10.

## Decided for 2026-27, and what is still open

Decided by Ely on 2026-09-30 and 2026-10-01 (see
[team/submission.md](team/submission.md) and [team/model.md](team/model.md)):

- Scope: `wk inc flu hosp` only: quantiles, horizons 0 to 3, all 53
  locations. No ED-visit, peak, rate-change or horizon -1 rows; the knobs
  `output.horizon_minus1` and `output.rate_change_pmf` stay off.
- Both models are designated for that target alone
  (`designated_targets: ["wk inc flu hosp"]` in both cards).
- Both NAU_PyBNF cards are on the hub (cdcepi/FluSight-forecast-hub#3705,
  merged 2026-09-24), one version behind FluBNF's; bringing them up to date
  is not needed for 2026-10-07.
- Both models' weekly files pass CDC's validator (28 of 28 checks): the
  Groundhog on a real-time and a replay run, the Oracle SIHRS on a vintage
  run of 2026-01-10. `scripts/validate_submission.R` runs on the Mac Studio
  (hubValidations 2.1.1) on every Oracle SIHRS file before it goes to the
  hub (see [team/model.md](team/model.md)).
- The Retrospective scores the Liu-West filter alone beside the Oracle
  SIHRS, from each replay week's `oracle.json` (its US figure only for
  weeks stored since addendum A3); it is never submitted.
- From the 2026-10-07 round the Oracle SIHRS US row carries the Oracle
  step like the states (addendum A3, Ely 2026-10-01, PR #27). On the dry
  run (as of 2026-09-26) the US medians were 2,704 / 2,645 / 2,311 /
  1,872 before and are 2,786 / 3,190 / 3,542 / 3,858 with the step
  (`results.json`: 2,785.7 / 3,189.5 / 3,542.3 / 3,858.1). Detail in
  [ORACLE-SIHRS.md](ORACLE-SIHRS.md) section 5c and
  [team/model.md](team/model.md).

Still open:

- Keep the Liu-West naming consistent in anything written for the team;
  leave the code's `pf` names alone until the port lands. The Oracle SIHRS
  card on `dev` names the Liu-West filter (b41fc92); the hub's copy changes
  with the submission lane's cards pull request.
- Windows laptops: the launcher fixes (engine updates on open, the Start
  menu entry) are on `main` since 2026-09-30 (elyfmiller/flubnf PR #25);
  students should open FluBNF.bat once to pick them up.

## Contacts and sources

- flusight@cdc.gov (Rebecca Borchering, Sarabeth Mathis, Annabella Hines).
- CDC's 2025-26 evaluation (published 2026-09-30):
  https://www.cdc.gov/flu-forecasting/evaluation/2025-2026-report.html.
  Its scoring leaves out national forecasts (their scale) and Puerto Rico
  (data availability); the headline is the season's average relative WIS
  over the jurisdictions, national excluded, as in 2024-25, and the 75%
  rule counts over the weeks and jurisdictions that remain. The US row
  still counts in real time: the FluSight ensemble is the per-location
  median of the designated models, and its national forecast is the one
  CDC publishes.
- https://github.com/cdcepi/FluSight-forecast-hub (README.md,
  hub-config/tasks.json, model-output/README.md, model-metadata/README.md,
  target-data/README.md).
- FluBNF: [README](../README.md), [docs index](README.md),
  [ORACLE-SIHRS.md](ORACLE-SIHRS.md), [MISSING-DATA.md](MISSING-DATA.md),
  [ENGINE.md](ENGINE.md), [WINDOWS.md](WINDOWS.md),
  [model-metadata/README.md](../model-metadata/README.md),
  [scripts/README.md](../scripts/README.md), and [TEAM.md](TEAM.md) for who
  works on what.
