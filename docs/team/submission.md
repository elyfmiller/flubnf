# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-10-08 (06:15 UTC, interim 2; 2024-25 and 2025-26 still running):
  2023-24 complete in both arms, 8 weeks each, 6 scoreable (as-of 2023-10-07
  to 11-11), 1,248 common Oracle cells, 52 jurisdictions x 3 seeds, the
  app's scorer against settled truth and the hub's baseline:
  - Oracle member, pooled: shipped relWIS 0.791, log-scale relWIS 0.753,
    coverage 50/80/95 = 0.62/0.89/0.98, h3 median below the origin in 19% of
    cells; knob relWIS 1.125, log-scale 0.760, coverage 0.71/0.93/0.99,
    below-origin 6%. So on the natural scale the knob is clearly worse (the
    overshoots in large counts); on the log scale, which is CDC's headline
    relWIS, it is a wash (0.760 against 0.753) with better coverage.
  - By week, log scale, shipped against knob: 10-07 0.730 / 0.839, 10-14
    0.684 / 0.749, 10-21 0.730 / 0.741, 10-28 0.859 / 0.824, 11-04 0.786 /
    0.722, 11-11 0.719 / 0.692: the knob loses the first three weeks and
    wins the last three, as the verifier's mini-replay predicted (better by
    late November). On the natural scale the knob loses every week (1.00 to
    1.57 against 0.69 to 0.92).
  - By horizon, log scale: the knob is worse at h0 (0.817 against 0.801) and
    h1, equal at h2, slightly better at h3 (0.731 against 0.735); on the
    natural scale it is worse at every horizon and the gap grows with the
    horizon (h3 1.30 against 0.80). By state size: small states 0.978
    against 0.950 (log), large 0.595 against 0.607.
  - The filter alone: shipped 0.860 (log 0.891), knob 1.798 (log 0.844),
    coverage 95% 0.95 against 0.99. The Groundhog is identical in both arms
    (1.055, log 0.663), as it must be.
  - Reading: in 2023-24 (an early season, a one-season expectation) the knob
    trades the shipped seed's early-season declines for overshoots of about
    the same log-scale cost, with better calibration. The stop rule as
    written ("not better on pooled early-week relWIS") trips on the natural
    scale and is a coin toss on the log scale; Ely decides which scale the
    rule meant (CDC's evaluation is log scale). Two seasons to go; the
    decision waits for them.
- 2026-10-08 (05:00 UTC, interim; the replay continues): the first scoreable
  weeks of 2023-24 (as-of 2023-10-07 and 10-14; the hub's baseline starts
  with the 2023-10-14 reference date, so the two earlier vintages score
  nothing), 416 common Oracle cells, the app's scorer against settled truth:
  the knob arm is WORSE. Oracle member: shipped relWIS 0.849 (log scale
  0.707), knob 1.347 (0.793); 95% coverage 0.99 in both, 50% coverage 0.71
  against 0.76; share of h3 medians below the origin 0.19 against 0.05. The
  filter alone: shipped 0.877 (0.784), knob 2.011 (0.884). The Groundhog is
  identical in both arms (1.373), as it must be. The loss is the overshoot
  the verifier predicted, in the real filter. Two weeks of one season, with
  a one-season expectation (2022-23); 2024-25 and 2025-26 follow. The stop
  rule "not better on pooled early-week relWIS" is on course to trip; if it
  does, the knob does not ship for 2026-10-14 and Plan C applies unless the
  Model lane has a growth-limited variant it can test in time.
- 2026-10-08 (02:10 UTC): the cloud session's container was reclaimed about
  five minutes after the session went idle (23:31 UTC), which killed the
  detached replay after 81 cells of its first week; the scratchpad, the
  engine venv and the clones survived. Resumed at 02:12 UTC as a job the
  session tracks, with a self check-in every 25 minutes to keep the
  container alive; the retro resumes finished cells. Pace measured before
  the kill: 17 cells a minute on 4 runners for the early 2023-24 weeks (8
  observations a cell), so about 9 minutes a week-arm there and longer where
  the series are longer; new estimate 8-9 hours, scored around 11:00 UTC
  Thursday (04:00 Arizona) if nothing else interrupts. Lesson for the lanes:
  a long run in a cloud session must be a tracked job plus check-ins, never
  a detached process.
- 2026-10-07 (23:25 UTC): the direction check ran clean with the real
  engine, both arms (`flubnf retro run 2026-27`, vintages 2026-09-26 and
  2026-10-03, 19 locations x 3 seeds, 2 runners, about 500 s a week-arm, 17
  s a cell-runner). Branch `seed-denominator` (e916dac) is pushed (Ely's
  go-ahead, 2026-10-07). Findings:
  - The cloud engine reproduces production: the shipped arm's Oracle medians
    at the 2026-10-03 vintage equal the submitted file's to the rounding at
    all 19 locations and 4 horizons (CA 466 / 504 / 541 / 575 against 466 /
    504 / 540 / 575; TX 364 / 413 / 468 / 522 against 364 / 413 / 467 /
    522), and its 11 decliners are exactly the submitted ones (IL, MI, WI,
    MT, AK, OR, ME, PR, DC, SD, WY).
  - The mechanism is visible in the filter alone: under the shipped seed the
    Liu-West filter's own medians decline by h3 in 19 of 19 locations this
    week (CA 451 -> 242, TX 326 -> 289, FL 559 -> 450); the Oracle step
    rescues 8 of them.
  - With the knob (season_total), the Oracle member declines in 5 of 19 (MT
    0.59 of last, DC 0.68, WY 0.85, AK 0.87, SD 0.99), the filter alone also
    in 5 (MT, AK, ME, DC, WY: the data turned down there). The turned-around
    locations rise steeply: over four weeks CA x2.1, WA x2.2, TX x2.4, FL
    x3.4, NY x3.4, NC x4.2, HI x5.7 (filter alone FL x7.2, NY x7.4, NC
    x10.9; the Oracle step halves these in growth terms). Against the
    Groundhog's US x2.0 that is the no-brake overshoot the verifier warned
    of, now in the real filter; IL, MI, WI go from declines to
    flat-to-rising (x1.1-1.3). Truth in four weeks tells which arm was right
    this week; the replay tells in general.
  - The early-week replay started at 23:26 UTC in the cloud session,
    unattended: 2023-24, 2024-25, 2025-26, first 8 vintages each, all 52
    jurisdictions x 3 seeds, shipped arm then knob arm per season, 4
    runners; roots replays/early-<season>-<arm> in the Submission
    scratchpad; about 9 hours, so scored around 09:00 UTC Thursday (02:00
    Arizona). Scoring: `app.core.retro.score_season` per root, members `pf`
    (Oracle SIHRS), `pf_filter` (the filter alone) and `analogue`; pooled
    relWIS and coverage on the common cells of the two arms, plus the share
    of cells with the h3 median below the origin; the stop rules above
    decide.
- 2026-10-07 (night): the diagnosis was checked twice by agents reading the
  code and the hub data, and the fix was tested on a deterministic stand-in.
  None of it is a filter run; the replay below decides.
  - Mechanism confirmed, with two corrections of framing. The model is not
    past its peak AT the origin: the filter fits Reff about 1.34, so the h0
    and h1 medians sit above the last count. The turn comes from depletion
    over the horizon (about 4% of N a week for the US under the shipped
    seed, 0.2% under the fix), so the peak lands at h1-h2. The Oracle step
    is a geometric mean in G = gamma + lam and replaces the filter's own
    weeks 2-4; "halves the decline" holds only against a flat donor, and a
    cell still declines iff (gamma + lam_T)(gamma + lam_d) < gamma^2.
  - REFUTED, correcting the evening entry: the turn does not fade "because
    the season fills in". By Nov 28 only 2.5-26% of a season's total has
    accrued (US 0.256, 0.100, 0.025, 0.064 in 2022-23 to 2025-26), and the
    weekly-to-cumulative ratio that sets the depletion speed is higher in
    late November than now. A deterministic mini-replay puts the shipped
    seed's turn at its worst at the Nov 29/30 vintages of 2025-26 and
    2024-25 (US 2025-11-29: 6179 / 7336 / 7661 / 6988 against truth 7450 /
    11137 / 21057 / 37502). Whatever fades in the real replays is the fitted
    harmonic or slowing growth, not the cumulative.
  - The stand-in (one least-squares SIHRS per location on log(1 +
    admissions) over 2026-08-01 to 10-03, the template's constants and
    bounds; no particles, jitter, negative binomial or Oracle step; files in
    the Submission scratchpad, round-2026-10-10/work/patch/demo): shipped
    seed, 30 of 53 locations decline by h3; season-total seed, 13. US 3677 /
    3790 / 3521 / 2978 against 3942 / 4528 / 4891 / 4923 (submitted Oracle
    3648 / 4180 / 4707 / 5304; Groundhog 3426 / 4291 / 5800 / 6480; last
    observed 3246). The fix turns US, OR, CA, NC, NY, TX and HI around; WI,
    MT, AK, ME, PR, DC, WY, WA and MN decline under both seeds (data
    downturns in the last 1-2 weeks, or the annual harmonic fitting the
    recent deceleration). Its cost: with 0.2-2.6% of N infected (46 of 53)
    there is no brake yet, 18 small locations climb faster than 1.5x a week
    (9 at the Reff bound; 11 had 20 or fewer admissions last week), and in
    DC, WY, ME, MT and AK the fit pulls mult 2.4-141x below the seed and
    re-creates the depletion.
  - The verifier's caution: "removes the early-season turn" is overstated.
    At the same stage last season (the 2025-10-04 vintage) both seeds
    declined alike (US shipped 874 / 760 / 629 / 497, fix 875 / 755 / 614 /
    468, truth 1018 to 1358): when the recent weeks decelerate, the annual
    harmonic absorbs it under the fix as depletion does under the shipped
    seed. This year's rise under the fix rests on that harmonic (28 of 53
    fits put peak transmission before mid-October), so only "rises at h0-h1"
    is identified, not the h2-h3 level. Over eight autumn vintages of
    2025-26 and 2024-25 (six locations, deterministic) the fix is a wash on
    point forecasts (mean absolute log error 0.87 against 0.90): clearly
    better at the late-November vintages, clearly worse where it overshoots
    (US 2024-11-02: 2414 / 5347 / 13652 / 38832 against truth 2176 / 2611 /
    3278 / 4436), because the expected-total pin sets the scale but not the
    SIR's final size.
  - So the fix is a candidate, not a ship. The replay decides under the stop
    rules above; expect a mixed result and read it with the Oracle step on
    and off (the scorer scores the filter alone as `pf_filter` beside the
    Oracle member, so one run gives both) and at the peaks, not only the
    early weeks. Pre-specified for the replay: the expectation is the median
    of however many completed seasons the vintage holds (one for 2023-24,
    namely 2022-23; two for 2024-25; three for 2025-26); a location with
    none falls back to the shipped rule, recorded. A growth-limiting variant
    for small states (a tighter Reff or eps1 prior, or a cap) is the Model
    lane's call and is not in the knob.
  - Carried from the skeptic: the closed trials "swarm-carry 1B hindsight
    ORACLE 1.047" and "donor-informed i0 priors: null" may already be
    P1-like; Model, please read those records (FluBNF-local research/)
    before the replay result is interpreted. fit_i0's 0.889 is not evidence
    against the fix: it opened the i0 x mult ridge, the fix keeps one pinned
    product.
- 2026-10-07 (night): the knob is implemented on branch `seed-denominator`
  (e916dac, from `dev` 1176d9e), by the Submission lane with Ely's go-ahead
  since the Model and App lanes could not be reached; please review rather
  than re-implement. As designed, with two differences: the cell record key
  is `seed_pin` (`seed` is the engine's RNG seed) and the knob help is
  shorter; `pf.seed_denominator` sits in `_FIT_ORDER` after
  `pf.initialization`. Full suite: 3104 passed, 82 skipped, 0 failed. A
  real-data check on the 2025-11-22 vintage resolves all 52 jurisdictions
  with three completed seasons each (factor 1.9 to 163, median 19.7). Ely
  (2026-10-07): the branch is pushed once the knob arm runs clean with the
  real engine; `dev` is untouched.
- 2026-10-07 (night): the private engine now runs in the Submission lane's
  cloud session. Ely granted the Claude GitHub App access to
  elyfmiller/PyBNF-Private; `feature/particle-filter` 2fdadee0 is installed
  in an engine venv with BioNetGen 2.9.3 (the bionetgen 0.8.7 wheel), bngsim
  0.15.1 and numpy 1.26.4; `flubnf.settings.check()` passes; the hub clone
  is a mirror of cdcepi `main` with this week's live file added as the
  2026-10-03 vintage. Running: the direction check, `flubnf retro run
  2026-27` on the 2026-09-26 and 2026-10-03 vintages, 19 locations x 3
  seeds, shipped arm and knob arm, about 8 minutes a week-arm on 2 runners
  (about 20 s a cell). Next, unattended: the early-week replay above, all 52
  jurisdictions, both arms, 4 runners, about 10-12 hours, scored Thursday;
  whole seasons after that if the early weeks pass. The shipped arm is rerun
  here because the stored shipped replays are on the lab Mac; Model, if you
  can export them (`flubnf retro export`), say so.
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

- Model (2026-10-07, top priority): please review the knob on branch
  `seed-denominator` (e916dac; see Now) rather than implement it: the median
  (not the mean) and the floor, `MIN_COMPLETE_WEEKS = 35`, the one-season
  expectation for 2023-24, and whether a growth-limiting variant for small
  states should be a second knob. Please also read the two closed trial
  records named under Now. The replays run in the cloud session unless the
  lab Mac is back; post or compare the scores in model.md. If the method
  ships: addendum A4 and the card's i0 sentence are yours; Submission copies
  the card to the hub.
- App (2026-10-07, top priority): the registry entry is on the branch
  (`pf.seed_denominator` with `_read`, `write_extra` and `_FIT_ORDER`, the
  `SOURCES` entry in app/tests/test_knobs.py, and
  app/tests/test_seed_denominator.py); please review it for the console's
  conventions before it merges to `dev`. Nothing else in the console
  changes; production stays bit-identical.
- Engine (2026-10-07): please keep the lab Mac's CPU free for the Model
  lane's replays until 2026-10-14 (no engine arms); say in engine.md if
  anything in pf.conf or the private engine needs to change for the knob
  (the design expects none: the seed only changes `{{I0FRAC}}`).
- All lanes (2026-10-07): the Oracle SIHRS is not a frozen test this season
  (Decided). The hub card on `dev` is mechanism-only since 1.3 (1176d9e) and
  staged on the fork branch `NAU_PyBNF-OracleSIHRS-1.3`; Ely opens that pull
  request with next week's forecast.
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
