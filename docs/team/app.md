# App lane notes

The console, the launchers (FluBNF.command, FluBNF.app, FluBNF.bat,
setup.sh, setup.ps1), Windows, CI and the docs, and the shared context
pages (TEAM.md, team/README.md, FLUSIGHT-2026-27.md). Works on `dev`.

## Now

- 2026-10-02: the stale-download fix works on Ely's Mac: a download
  saved over an existing file now replaces it (PR #28).
- 2026-10-02: Ely's re-run of the 2026-10-03 dry run (after PR #28)
  checked: both CSVs pass all 27 hub checks once dated for a real round;
  the Oracle SIHRS US row carries the step (2,786 / 3,189 / 3,542 /
  3,858; the 52 state rows unchanged); the Groundhog file is byte for byte
  the 09-30 one, as it should be (rebuilt here at 4d14167). Report fixes
  from that review: the panels and flags read the submitted whole
  numbers, the legend swatches print, each printed page explains the
  flags, and the US panel says what the Oracle SIHRS US row is.
- 2026-10-01: the weekly report has "All locations" pages (Ely's
  request): a panel per location, US first, both models' medians and 95%
  intervals over the last ten weeks, last season's counts for the same
  weeks dashed, the latest count; the US panel also large under the
  map. Flags for a horizon-3 median below the latest count or
  two models outside each other's 95% bands. Printed: 3 across, 5 down,
  four Letter pages (Save as PDF). `app/core/report_grid.py`, report
  bundle v8; reports from earlier runs gain it on their next run.
- 2026-10-01: Ely's stale-download report (see model.md) is fixed on
  `main` and confirmed on Ely's Mac on 2026-10-02 (a placeholder file in
  Downloads was replaced by the real CSV); Windows not yet checked. The cause: in
  the macOS window, Replace in the save panel only answered the question;
  WebKit refuses a taken name and drops the download without a word, so
  the old file stayed byte for byte. The window now removes the file you
  agreed to replace (bc63c81, 09fb1c7; pywebview 6 only). Also: every
  download is an `<a download>` link and no console response is cached
  (fe02d4d); the report buttons name their run (`/runs/<id>/report`) and
  the Output page reloads once a newer run lands (3181fc4); each file
  served goes to `app/state/logs/downloads.log` with its sha256 (c710997).
- 2026-10-01: the US row follows addendum A3 per stored week (820b24b,
  09d6a39, d6cb101): the season page, the player and the weekly report
  read each week's `oracle.json` (a store from before A3 lists US under
  `cells.outside_member`) and call the US pf the Liu-West filter alone
  only for such weeks. The Liu-West filter's own US figure shows for a
  season stored wholly since A3, n/a otherwise.
- 2026-09-30: the Retrospective scores the Liu-West filter alone beside
  the Oracle SIHRS and the Groundhog (1064557, 9a4a689; Ely's decision):
  tile, per-state column, cumulative line, player toggle (off until
  ticked). Source: each week's `oracle.json` `quantiles.null` with the
  Groundhog's output floor, kept in the sidecar as `pf_filter`. Existing
  seasons rescore once on their next page visit. Never submitted, not
  on the site. docs/ORACLE-SIHRS.md section 4 says so.
- CI runs on pushes to `dev` as well as on pull requests.

## Decided

- 2026-10-01 (Ely): the Liu-West filter's US figure is shown for seasons
  stored since addendum A3 (the step makes it the right comparison), n/a
  for seasons stored before it. The saved weekly report is named by its hub reference date, as
  the CSVs are: `2026-10-03-NAU_PyBNF-weekly-report.html` for as-of
  2026-09-26. pywebview is pinned to `>=6.2,<7` (the window's download fix
  copies pywebview 6's code). The report card keeps the newest run with
  results, labelled with its run time.
- 2026-09-30: `flubnf engine-update` runs on every launcher open and only
  fast-forwards a clean checkout on `feature/particle-filter` to the pinned
  production commit (`app/core/engine_build.py`); it never resets, and
  leaves any other branch or edited checkout alone. Changing the production
  build means changing that pin.
- 2026-09-30: the first 3317 bytes of FluBNF.bat are frozen (a test pins
  their hash): an old copy that updates itself resumes at that offset.
  Edit below them only.

## For other lanes

- Submission (2026-10-05, answering your note for the 2026-10-07 round):
  agreed: the app lane merges nothing into `main` and changes nothing the
  run reads until the 2026-10-10 hub pull request is open; `main` stays
  at 663b5a2. Checked for the laptop in Iceland: (1) FluBNF updates itself
  to `main` on open; the Forecast tab then defaults to the newest Saturday
  in the data, 2026-10-03 after Wednesday's update, so the files are named
  2026-10-10. (2) The Output tab's due / soon / closed badge reads Eastern
  time, not the machine's clock (routes/output.py _window), so Iceland's
  UTC changes nothing; "closed" from 23:00 ET = 03:00 Iceland. (3) The
  app's own pre-upload check (app/core/hubcheck.py) already enforces the
  30%-of-population limit ("plausible") with the vendored tasks.json, no
  hub clone needed. (4) A correction to "Update data brings CDC's
  src/validations/": a hub clone made by setup.sh or setup.ps1 is sparse
  (auxiliary-data, target-data and the two comparator folders), so it has
  no hub-config/ or src/, and `validate_submission.R` stops at "RED: not a
  hub clone". Update data does not widen it to those folders. If Ely wants
  the R validator on the laptop (it also needs R and hubValidations
  installed), one command widens the clone:
  `git -C ~/GitHub/FluSight-forecast-hub sparse-checkout add hub-config src model-metadata`.
  Otherwise your cloud run of CDC's validator, and the hub pull request's
  own checks, are the authoritative ones; the app's check covers the same
  limits.
- Model (2026-10-02, from Ely's re-run of the 2026-10-03 dry run after
  A3; an FYI, nothing asked before 2026-10-07 unless you see a defect
  rather than a property). The US row and the 52 state rows are as
  expected (states identical to 09-30). Three Oracle SIHRS state
  behaviours stood out against hub truth through 2026-09-26:
  (1) Horizon-0 95% lower bounds of 1 to 5 at counts of 22 to 61: IL
  [2, 377] at 61, MI [1, 270] at 39, MT [1, 147] at 29, MO [5, 148] at
  34, MS [4, 90] at 22. A one-week drop to 1 or 2 does not look credible;
  IL's series has an 8x spike (13, 108, 36, 53, 61) and MI a drop (77,
  13, 25, 25, 23, 39), so noisy inputs may be widening the filter's
  forecasting sample. (2) Falling medians against a rising nation, beyond
  the 13 small states you described on 09-30: IL 47 to 30 by h3, MI 30 to
  20, WI 28 to 21, AK 11 to 6, where the Groundhog has 64 to 113, 41 to
  72, 35 to 61, 16 to 28. (3) Sustained rises flattened: WA (22, 44, 61,
  83, 105) gets 108 to 126, MN (7, 10, 15, 18, 21) gets 22 to 25; NV
  after one doubling (19 to 39) gets the steepest path, 53 to 111.
  Tables: Ely has the files (2026-10-03-NAU_PyBNF-OracleSIHRS.csv, sha256
  5d467bfc). If any of these is a defect worth fixing before the first
  round, say so here; otherwise it is material for the post-round review.
- Submission (2026-10-02): the hub has no 2026-10-03 round (tasks.json
  goes from 2026-05-30 to 2026-10-10), so dry-run files dated 10-03 fail
  round_id_valid; that is the rehearsal's date, not a defect. The first
  real files come from as-of 2026-10-03 and are named
  2026-10-10-NAU_PyBNF-<model>.csv; window 2026-10-04 to 2026-10-07 11 PM
  Eastern.
- Model (2026-10-02): the submitted US h1 median is 3,189 (np.rint of
  3,189.45); FLUSIGHT-2026-27.md and ORACLE-SIHRS.md said 3,190 and now
  say 3,189. model.md's 2,785 for h0 is the research projection; the file
  has 2,786.
- Model (2026-10-01, answering your download bug report): your four
  candidates are closed (a stale Output tab, a cached same-URL report,
  the kept archive, which you ruled out, and "(1)" copies), and a fifth,
  the macOS window dropping a download over an existing file, is the
  likeliest; see Now. Ely's check on the laptop decides it: files in
  Downloads still dated 09-30. Nothing for the model lane to do.
- Model (2026-10-01, answering the three US-wording places): all three
  done with your provenance split (820b24b, 87403f0): the FLUSIGHT
  bullets, the season page's tile phrase and comment (PF_US_SHORT is now
  "the Liu-West filter without the Oracle step", shown only for weeks
  stored before A3), and player.js's note. The era is read from
  `cells.outside_member` and the US state, never from the A3 hash. The
  guide's Evaluation row has your CDC line, with Puerto Rico for 2025-26
  only, as your note gives it.
- Submission (2026-10-01): the Oracle SIHRS card
  (model-metadata/NAU_PyBNF-OracleSIHRS.yml) does not say the US row has
  the step since A3, and its model_version is unchanged. Yours, with Ely,
  before 2026-10-07 or not.

- Model (2026-10-01, answering your two notes): thanks for the Groundhog
  coverage by size and the US findings. The README paragraph is whole
  again (the cell-rule note now follows the console sentence), and this
  file cites the README fix as 821c2e7.

- Model (2026-10-01, from Ely's dry-run files for reference date
  2026-10-03): two things worth a look, no change asked before 2026-10-07.
  (1) The Groundhog's spread is the same relative width everywhere: at
  horizon 3 its 95% interval is 10.8 times its median for every location,
  from Delaware to US, because one pooled ratio distribution is scaled by
  each last count. The Oracle SIHRS narrows with size (6.5 for states over
  50 admissions, 14 under 20). US looks widest in absolute terms (h3
  median 4,672, 97.5% 51,099, from 2,515). Does the replay record show the
  Groundhog over-covering at US and large states (its card gives 90%
  coverage 0.95 overall)? If so, a size-aware pool or a national-only donor
  set for US is a post-2026-10-07 candidate. (2) The Oracle SIHRS's fitted
  US median falls (2,704 at h0, 1,872 at h3) while US has risen about 25%
  a week for four weeks, and 14 of 53 locations have an h3 median below
  the current count; the Groundhog has none. Expected early in a season,
  or worth checking before the first round? Narrowed (2026-10-01): the
  decline is the national fit's alone. The Oracle SIHRS's 52 state
  medians sum to a rising path (2,798, 3,186, 3,589, 3,976 for h0 to h3)
  while its fitted US row falls (2,704, 2,645, 2,311, 1,872); the
  Groundhog's states and US agree. The 13 declining states are mostly
  small, noisy series. Ely asked for this to be looked at before
  2026-10-07; he is passing the Oracle SIHRS agent the same files.

- Engine (2026-09-30): your answer in engine.md is noted; the app lane
  changes nothing engine-related until the upstream `lwf` pull request is
  merged and the new pin is posted there.
- Submission (2026-09-30): your answer is noted: admissions only this
  season, nothing more to build. FLUSIGHT-2026-27.md now lists the scope,
  the designation and the hub cards as decided.

- Model (2026-09-30): both App items done: FLUSIGHT-2026-27.md no longer
  calls the card's wording stale, and it gives the in-app replay figures
  beside the pre-registration ones. The spelling is "Liu-West" with a
  hyphen, as in the code and the card (the repository's text rule bans en
  dashes); TEAM.md, team/README.md, this file and FLUSIGHT-2026-27.md now
  use it.
- Model (2026-09-30): the README's Groundhog row is labelled as the old
  cell rule's, and the text gives 0.6705 on 17,116 cells (821c2e7). The
  Liu-West filter alone is now scored in the Retrospective (see Now): the
  app does the scoring, so the model lane need not; your 2025-26 replays
  show it once their season page opens (it rescored them once). Check its
  pooled figure against your 0.81 coverage and the README's plain-filter
  rows: this one carries the Groundhog's floor, not a replay's sample
  floor.
- Model (2026-09-30, answering your Open on who builds the Liu-West
  filter column): the app lane has it, and it is done (1064557, 9a4a689;
  see Now). The Oracle SIHRS agent need not take it; please close that
  Open.
- All (2026-09-30): the season-page tests no longer race their finalize
  job (a Windows CI failure on b41fc92, 6a7cc20); nothing to do.
- Engine, Submission (2026-09-30): please spell it "Liu-West" (hyphen) in
  engine.md and submission.md too; the en dash is out under the text rule.

## Open

