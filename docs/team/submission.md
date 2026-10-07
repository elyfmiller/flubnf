# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-10-07: round 2026-10-10 (EW40) submitted as is:
  cdcepi/FluSight-forecast-hub#3730 from `FluBNF_submission` (2605672,
  plus Ely's sync merge ab91b74). It adds only the two files, and both
  are byte-identical to the files Ely ran (both 4,877 lines). Both pass
  `validate_submission.R`, 31 checks with `--window`, against the hub
  (target data of 2026-10-07; the hub's later commits are other teams'
  files). The Groundhog file is byte-identical to a cloud regeneration
  from `main`. The Data issues box was empty: all 53 locations reported
  2026-10-03, with no zero or collapsed newest week.
- 2026-10-07, sense check (for the post-round review; no blockers): every
  2026-10-03 count is inside both models' h0 50% and 95% intervals, and
  every trend projection is inside both 95% intervals at h0 and h1. The
  two models' 95% intervals overlap everywhere. Both medians sit 15-25%
  below the US growth path (about 27% a week; the season is 3x the
  same week of 2022-25 and 4-7 weeks ahead of it, so the calendar-matched
  donors grow too slowly). Oracle SIHRS: medians fall in 11 locations
  (IL, MI, WI, MT, AK, OR, ME among them), CA, WA and MN flatten, and NH
  rises 5x by h3; all are documented dry-run behaviour (model.md). The
  Groundhog puts its 2.00x path on every location. Hawaii (28 to 64) is
  above its all-time weekly maximum in both files at h3. Ely chose to
  untick nothing.
- 2026-10-05: the hub changed since 09-30: PR validation now runs CDC's
  custom 30%-of-population check (`max_hosp_popn_frac`, in
  `src/validations/R/`), so `validate_submission.R` reports 30 checks, not
  28. A FluBNF Groundhog file (dated 2026-10-10) passes all 30 against the
  hub at ee477e74. `tasks.json` and the metadata schema are unchanged
  (still byte-identical to FluBNF's copies).
- 2026-10-05: cdcepi/FluSight-forecast-hub#3713 is merged: both cards on
  the hub match FluBNF's `model-metadata/` (Liu-West wording,
  `designated_targets`). The fork branch `NAU_PyBNF-metadata-update` can go.
- 2026-09-30: the weekly file passes CDC's own validator for a Groundhog
  real-time run and a replay; the model lane's Oracle SIHRS replay file
  passes too (model.md: GREEN).

## Decided

- 2026-10-05 (Ely): weekly submissions go through one branch,
  `FluBNF_submission` of elyfmiller/FluSight-forecast-hub. Ely hands the
  submission lane the two CSVs; the lane checks them (CDC's validator plus
  a sense check of the forecasts against the data), brings the branch up
  to cdcepi `main` (fast-forward; a fresh dated branch if last week's pull
  request is still open), commits both files as Ely under
  `model-output/NAU_PyBNF-<model>/`, pushes, and sends Ely a link with the
  pull request prefilled; Ely presses Create (the lane cannot open pull
  requests on cdcepi from its session). Commit and pull request title:
  `NAU_PyBNF forecast YYYY-MM-DD (EWnn)`, the reference date and its MMWR
  week, e.g. `NAU_PyBNF forecast 2026-10-10 (EW40)`.
- 2026-10-05 (Ely): the 2026-10-10 round runs on the private engine, the
  production pin `feature/particle-filter` 2fdadee0 with its `pf_*` keys,
  not the public `lwf` port (Engine's equivalence result changes nothing
  for this round).
- 2026-09-30 (Ely): the 2026-27 scope is `wk inc flu hosp` only:
  quantiles, horizons 0 to 3, all 53 locations. No ED-visit, peak,
  rate-change or horizon -1 rows; the knobs `output.horizon_minus1` and
  `output.rate_change_pmf` stay off.
- 2026-09-30 (Ely): both models are designated for that target alone
  (`designated_targets` in both cards).
- 2026-09-30: the hub's cards are byte copies of FluBNF's
  `model-metadata/`: change a card there first (its tests check it
  against the hub schema), then the submission lane copies it to the fork.

## For other lanes

- All lanes (2026-10-07): the 2026-10-10 hub pull request is open
  (#3730), so the `main` freeze requested on 2026-10-05 is over.
- Engine, Model: no Mac Studio time is needed for this round if Ely's
  laptop runs it; keep the Wednesday rule anyway (free from the
  target-data update until the hub pull request is open) as the fallback.
- App: Ely's laptop needs `main` (FluBNF updates itself on open) and its
  hub clone updated in the Data tab before the run ("Update data"), which
  also brings CDC's new `src/validations/` for `validate_submission.R`.
- App (answering your note of 2026-10-01 on the Oracle SIHRS card and
  A3): the card never says the US row is outside the step, so A3 leaves it
  accurate; no card change or version bump for this round.
- Model (answering your notes of 2026-09-30): noted: 2026-10-07 runs both
  models on `main` with the Data issues box's preselected choices and
  `run.drop_same_day` off; short newest weeks explain the Oracle SIHRS's
  coverage; the wide early-season Groundhog tails are expected. Thanks for
  the card wording: it is on the hub (#3713 merged).
- Model: thanks for the GREEN on the Oracle SIHRS file; request closed.
- App (answering your request of 2026-09-30): done: "Liu-West" with a
  hyphen in this file too.
- App: `app/tests/test_model_metadata.py` now handles `oneOf` (0e6e3cc).
  If CDC changes its metadata schema again, the test fails wherever the
  hub clone is current: re-vendor the schema and update `SCHEMA_SHA256`.

## Open
