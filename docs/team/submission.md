# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-10-07 (evening): THE SEED FIX IS THE TOP PRIORITY OF EVERY LANE
  UNTIL THE 2026-10-14 ROUND (Ely). A collaborator's six-member ensemble
  (NAU plus UGA) flagged the Oracle SIHRS declines (WI, WY); Ely answered
  that a fix is in test and hoped for next week. The cause, checked
  against the code (`flubnf/sihrs_priors.py pin_rho_mult`,
  `flubnf/sihrs_fit.py resolve_state`, the template): rho*mult is pinned
  as (season-to-date admissions per capita) / 0.18, so the admissions
  since Aug 1 always stand for a FULL season's 18% attack rate. At every
  forecast date the model has 18% of the population already infected,
  S/N = 0.67 at the origin and R_eff = 0.79 x Reff; the fitted Reff must
  exceed 1.27 before the model grows at all. The seed i0 is wrong by the
  factor (expected season total) / (to date): US x20, IL x24, WI x26,
  MT x15, MI x36, AK x4.6, PR x7.8, WA x9, HI x5.7, CA x11 (median of the
  four past seasons' per-capita totals, 86.8/100k for the US, against
  4.3/100k so far). It eases through the season because the data force
  Reff up and i0 shrinks as 1/cumulative, not because the brake is right.
  The Oracle step halves the decline in growth terms; the 11 locations
  where the filter's own lam_T is most negative still decline. `fit_i0`
  (a free i0) is not the same fix: it removes the brake altogether and
  scored worse on whole seasons (0.889 against 0.749); the fix below
  keeps a brake that grows with the season.
- 2026-10-07: the plan, with the lanes it needs (details under For other
  lanes; the design is the Submission lane's draft for the Model lane to
  check, not a decision on the method):
  - Plan A (the fix): research knob `pf.seed_denominator` with values
    `to_date` (shipped default, production bit-identical) and
    `season_total`: rho*mult pinned on the median per-capita total of the
    completed past seasons in the same as-of vintage (>= 35 finite weeks;
    the dated archive files carry the whole history from 2022-02, so it
    is as-of safe), floored at the to-date value so the factor is never
    below 1 and the shipped rule returns once a season passes its
    expectation; i0 from the same pin; a location with no completed
    season falls back to the shipped rule, recorded. Attack rate 0.18 and
    s0 0.85 unchanged. One `pin_from()` used by resolve_state, the trim
    re-derivation and the reporting model in `pf.prepare`; cells.json
    gains a `seed` dict only when the knob is on.
  - The decisive replay (Model, lab Mac): the first 8 vintages of
    2023-24 (2023-09-23 to 11-11), 2024-25 (2024-11-16 to 2025-01-04)
    and 2025-26 (2025-08-30, 09-20, 11-15 to 12-20) with the knob,
    53 x 3, against the stored shipped replays, scored with the app's
    scorer (relWIS on common cells, 50/80/95 coverage, share of cells
    with the h3 median below the origin): 24 week-runs at about 5
    minutes = about 2 hours. Whole seasons (74 more weeks, about 6
    hours) only if the early weeks win in 2 of 3 seasons. A 5-minute
    direction check on this week's live data can run first.
  - Stop rules: the knob arm is not better on pooled early-week relWIS;
    or it loses more than 0.05 of 95% coverage; or it wins early but
    loses whole seasons by more than 0.02 (the brake near the peak).
  - Plan B: the same replays on Ely's laptop (2-3x slower) if the lab
    Mac cannot be reached.
  - Plan C (Ely, decided): if no fix is in by 2026-10-14, untick the
    declining Oracle SIHRS locations for that round (this week's 11 would
    leave 42 of 53 = 79%, above CDC's 75% rule); the Groundhog keeps
    every location.
  - Timeline: knob on `dev` by Fri 10-09 (Model, App); early-week replay
    scored by Sun 10-11; Ely decides Mon 10-12; whole seasons Mon-Tue if
    needed; `main` by Tue 10-13 night; card update and hub metadata pull
    request Tue if the method ships (methods_long's i0 sentence and the
    "frozen-specification" phrase, version 1.3); Wed 10-14 run with the
    knob, else Plan C.
- 2026-10-07: cdcepi/FluSight-forecast-hub#3730 merged at 18:54 UTC
  (1e47fc5); both files on the hub's `main` are byte-identical to the
  checked ones. Next round (2026-10-17, due 2026-10-14) reuses
  `FluBNF_submission`: fast-forward it to cdcepi `main` first.
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

- 2026-10-07 (Ely): the Oracle SIHRS is not run as a frozen test this
  season: a clear fix gets made. The seed fix above takes priority over
  every lane's other work until the 2026-10-14 round. Plan C for that
  round is unticking the declining locations.
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

- Model (2026-10-07, top priority): please implement the seed knob on
  `dev` (flubnf/sihrs_priors.py: `SEED_DENOMINATORS`, `SEED_DENOMINATOR`,
  `MIN_COMPLETE_WEEKS = 35`, `expected_total_per_capita(truth, fips,
  population, season_start, as_of)` returning the median and a record
  with the seasons, median, mean; flubnf/sihrs_fit.py: `pin_from(obs,
  population, attack_rate, expected_pc, gamma)` -> (rhomult, i0, factor),
  `resolve_state(..., seed_denominator=SEED_DENOMINATOR)`, StateSetup
  fields `seed_denominator`, `expected_total_pc`, `seed_factor`,
  `seed_record` with shipped defaults so the fake states in app/tests
  keep working; app/core/engines/pf.py prepare(): read
  `extra["seed_denominator"]`, refuse it together with `fit_i0`, pass it
  to both resolve_state calls, use `pin_from` in the trim re-derivation
  and the reporting model, record `seed` in the cell only when the knob
  is on so the shipped cells.json and test_pf_anchor_lag's SHIPPED_KEYS
  hold). Tests: median/floor/fallback/default-identical in
  tests/test_sihrs_fit.py; prepare records `seed` only with the knob;
  fit_i0 + season_total refused. Then the 5-minute live-data direction
  check and the early-week replay above; post the scores in model.md.
  Please also check the mechanism statement above against your own
  reading and say if the median (not mean) and the floor are right.
  If the method ships: addendum A4 and the card's i0 sentence are yours;
  Submission copies the card to the hub.
- App (2026-10-07, top priority): the knob registry entry
  `pf.seed_denominator` (choice, stage fit, PF only, default
  `flubnf.sihrs_priors:SEED_DENOMINATOR`, no card phrase) in
  app/core/knobs.py with `_read` / `write_extra`, the retro form and the
  Model settings panel, and the `SOURCES` entry in app/tests/test_knobs.py,
  so `flubnf retro run <season> --knob pf.seed_denominator=season_total`
  works, the run record marks it modified, and a tree built with the
  other value is refused rather than resumed. Nothing else in the console
  changes; production stays bit-identical.
- Engine (2026-10-07): please keep the lab Mac's CPU free for the Model
  lane's replays until 2026-10-14 (no engine arms); say in engine.md if
  anything in pf.conf or the private engine needs to change for the knob
  (the design expects none: the seed only changes `{{I0FRAC}}`).
- All lanes (2026-10-07): the Oracle SIHRS is not a frozen test this
  season (Decided). The hub card still says "frozen-specification
  replication"; it changes only if the method ships, with the version.
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
