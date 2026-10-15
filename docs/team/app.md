# App lane notes

The console, the launchers (FluBNF.command, FluBNF.app, FluBNF.bat,
setup.sh, setup.ps1), Windows, CI and the docs, and the shared context
pages (TEAM.md, team/README.md, FLUSIGHT-2026-27.md). Works on `dev`.

## Now

- 2026-10-15: Ely's cleanup request (Model settings shoved the forecasts
  down; "?" marks everywhere). On `dev`: the Model settings panel opens
  only after a refusal, stays in the settings column, shows each group's
  changed rows with their defaults and folds the rest; the Forecast tab
  shows the forecasts first. Every page holds at most one "i" (Forecast's
  Settings card and panel two); badges and labels say the rest, and the
  reference text moved to Methods folds and its new Model settings table.
  Fixed, each reproduced first: "Export under the hub names anyway" and
  its reason carried over to the next run (now cleared once a run is
  queued; a refusal keeps them, and the Run row says "Differs: File
  names" until the box is ticked again); an invalid value in the closed
  panel silently blocked Run; a Groundhog-only run lost the filter's
  settings; a vintage run replaced Home's and Output's current week;
  a Groundhog-only replay showed "Scoring failed ... IndexError"; Stop
  could leave a stale "running" card; a skipped Saturday's anchor line; a
  Weekly report button 404 after its workroot was deleted. The Forecast
  tab now draws a modified run (badged); Home and Models keep the shipped
  rule. For Submission (2026-10-10): oracle.w's help now says it weighs
  the filter's own growth, lower leaning on the donors.
- 2026-10-14: Ely's answers to the Sandbox usability review. Less text on
  the page, not more; no flag that claims what the model does with the
  data, since one rule of thumb is wrong for another disease or model; Home
  may carry a Sandbox line; the Oracle SIHRS start stays as an example with
  its own mechanisms; 40 to 100 s full fits are fine on student laptops;
  students start from the SIR example (no assignments; they build on it or
  start their own); keep run ids, zip file names and ESS as they are (ESS
  is the reassurance that sampling went well). Any parameter name works
  when it ends in `__FREE` (capitals) and has its prior line; `r__FREE` is
  the one reserved name (the likelihood's dispersion). SARI counts are a
  possible outside data set. On `dev`: the verdict grades the sampling only
  ("Sampling looks healthy", "Quick check: the model runs" never green,
  "Sampling thinned out", "Sampling collapsed"), the band-coverage flag is
  gone, What to try holds two lines at most; Check's headline is amber
  whenever it has notes; the SIR example is the default start with a name
  filled in, and a space in a name becomes _; Check names a rename made in
  one file and a `__free` in small letters; the SIR example says scale
  between about 0.2 and 0.3 (full fits give 0.21 to 0.29). A date,count
  CSV (any count header) loads as one series named after the file, in the
  Sandbox, the Data tab and `flubnf dataset`; two numeric columns are still
  refused, naming both. The fit estimate is scaled by this computer's last
  finished fit (a 1 to 4 times span before one); a live fit shows "0:27 so
  far · about 0:51 in all", and Save and run is off while it runs. Not
  done: a quick check is still estimated at a second or so, since the cost
  model has no start-up term to scale. Set aside: B1's fit-to-data line and
  score sentence, the first-fit card (B3), and the on-page help of Q2.
- 2026-10-14: the Windows student install (Ely's request; Perl suspected). A
  review of FluBNF.bat, setup.ps1 and the console's BNG2.pl runs: 45
  findings, each checked by a skeptic; none was run on a Windows PC. One
  stopped every open after the first since 2026-09-24 while the engine file
  was still in Downloads: FluBNF.bat closed before the console (VERSION's LF
  line ends through `set /p`). test-windows showed it at 6a369bc and passed
  at d5d51a3, which is on `main` as PR #34; `dev` has the same fix. On `dev`
  besides: FluBNF.bat checks for a Windows Perl on every open, counts no Git
  or Cygwin perl, puts an installed Strawberry Perl on PATH, offers winget
  once (`.venv\perl-offer.txt`) after saying Windows will ask permission,
  and judges it by `perl.exe` on disk (a declined prompt read "Perl
  installed"). Only `pybnf-pf-*.tar.gz` counts as the engine file, and a
  miss lists the folders searched; a replaced engine is probed again, and
  installed when it does not import; `:sync` installs BioNetGen when BNG2.pl
  is missing; the engine venv takes x64 Python 3.11 or 3.12 only, finds
  Anaconda in more places, asks conda for x64, tries pypi.org for 5 s first,
  and names a cause and a step before every failure. The console finds one
  Windows Perl (PATH, then the registry's Path, then Strawberry's folders;
  no restart) and pins BNGPATH to BNG2.pl's own folder, so a stale BNGPATH
  no longer kills BNG2.pl, in its 8.3 form when Perl cannot read the long
  one (Łukasz 李); a BNG2.pl failure keeps Perl's first line; doctor checks
  Perl. Sandbox: pf.conf names no folder, so José, m.contreras and Jane Doe
  fit (on Linux: both engines' parsers, five real fits), and a folder with a
  space is no longer refused; the notice lists every missing piece in the
  order a student fixes them, with an engine import probe and a `BNG2.pl -v`
  self-test; a BNG2.pl that never starts is the computer's problem, not the
  model's. Runners record an engine exit or PybnfError with its reason and
  go on to the next cell. CI: the real BNG2.pl on ubuntu and, under
  Strawberry Perl, on windows-latest; the engine pins must have win_amd64
  wheels; a record of bngsim under a non-ASCII folder. Submission, Model:
  production's pf.conf and engine pin are unchanged, and a run that succeeds
  on the lab Mac writes what it wrote before; a failed prepare or cell now
  records its reason, and runners start with SyntaxWarnings off. On Windows
  only, production's BNG2.pl runs and runners get BNGPATH pinned. Engine:
  five notes for your public-PyBNF plan under For other lanes, none a
  decision. This answers two Open items of 2026-10-13 (Perl offered on one
  open only; CI never runs the real BNG2.pl). Ely decided: a Perl that
  needs no administrator (conda-forge's Strawberry repack, unpacked under
  %LOCALAPPDATA%) and bngsim's code generation off for Windows fits come
  next, as their own pull request; the relative pf.conf for production
  waits for stage 1; no conda-first engine venv and no deploy key for CI.
  Still wanted: one hand test on a Standard account, which would be the
  first Sandbox-tab fit recorded on Windows.
  Docs: WINDOWS.md, INSTALL-STUDENTS.md (stay at the window for the
  permission prompt; lines to paste when it still does not work),
  SANDBOX.md, ENGINE.md, LAUNCHERS.md.
- 2026-10-13: Sandbox audit (Ely's request: students report hits and
  misses). Seven readers, each finding then checked by two verifiers: 22
  confirmed, 1 refuted, 23 not checked (the run stopped at a usage limit).
  Fixed on `dev`: a run the engine refuses shows the engine's reason (it
  showed only "failed") and no longer offers the full fit; a refusal's
  remedy reaches the notice's "?" (it was cut at 200 characters); a model's
  page says "This computer cannot fit yet" when the engine, its Python or
  Perl is missing, and Check says so apart from the model; a half-installed
  engine, a folder path with a space, a network over 300 s or a model that
  does not generate is refused in words and leaves no run folder. Check: a
  `__FREE` parameter without a prior and a prior on a fixed parameter are
  problems (the engine refuses both), a prior line without `=` is refused,
  a commented-out simulate action no longer names the suffix,
  `generate_network (` passes, a header mismatch names the header. Run
  settings read as typed (`1e4`); Save, Load, Upload and Simulate no longer
  stall on a run setting out of range; Ctrl/Cmd+S works anywhere on the
  page; a new dataset shows its own weeks, so Load is on; Set N on a model
  without N loads nothing. FluBNF.bat gives its window Strawberry Perl's
  folders after installing it. SANDBOX.md and INSTALL-STUDENTS.md say what
  the Sandbox needs.
- 2026-10-07: weekly report trimmed at Ely's request (PR #31, on `main`): both
  95% bands plain fills in each model's colour, no off-scale arrows, and
  about 90% of the explanatory text removed. A stored run rebuilds
  trimmed when served, so the 2026-10-10 report needs no re-run.
- 2026-10-05: design and convenience pass on `dev` (Ely's request), not
  on `main` while `main` is frozen for the 2026-10-10 round. Display and
  wording only; nothing a run or the submission CSVs read changed.
  Weekly report: member colours that pass contrast in every theme, a
  colour-blind switch that works in a saved file, plain public wording
  (reference date in the title, no internal names), a summary line, a
  jump bar, states listed by category, a numbers table per detail,
  print fixes (5 pages, no orphaned headings). Output: the due round
  stands out with time left, copy-path and validator-command buttons,
  "newer run in progress", superseded runs named. Forecast: reference
  date and window under the date, location presets and filter, the
  last form kept across restarts (`app/state/last_form.json`, the date
  always resets to the newest week). Retrospective: opens on US over
  the last 12 weeks, every member on, deep links, keys. Shell: phone
  tabs wrap, "Match system" theme, g-key shortcuts ("?" lists them).
  Public site and README: one name for the mechanistic member, no
  builder-machine details, a status block and quick start.
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

- Engine (2026-10-14, notes for the public-PyBNF plan, not decisions):
  from the review of the Windows student install. Suggested wording; the
  plan's table and steps stay yours to change.
  - Step 8: add FluBNF.bat. It installs the engine on Windows by itself
    (its own venv, pip line and import probe) and never calls setup.ps1
    for that. FluBNF.command needs nothing: it goes through
    setup_engine.sh.
  - The engine venv row: "x64 Python 3.12 or 3.13, `--only-binary
    bngsim`". bngsim 0.15.1 and 0.16.0 have Windows wheels for cp310 to
    cp313 only, Anaconda 2026.07's own Python is 3.14, and on 3.14 pip
    falls back to a C++17, CMake and Ninja source build (#985's own CI
    notes it), so the flag makes a wrong Python fail at once. The row "how
    lab users get it" says a Python 3.12 venv, this one ">= 3.12".
    FluBNF.bat's Python gate (today x64 3.11 or 3.12) and its `conda
    create python=3.12` fallback can carry over with the versions changed.
  - The preflight row: FluBNF's Perl and BNG2.pl checks stay ahead of the
    import probe (pf.prepare, and the Sandbox's preflight, which now also
    runs `perl BNG2.pl -v` once). Public `lwf` still runs `perl BNG2.pl
    -v` when it loads a conf and generates each network with `perl
    BNG2.pl`, and without Perl on Windows a student gets PyBNF's "BNG2.pl
    was not found at the specified location".
  - If decision 6 pins a commit: `pybnf.__version__` is 1.8.1 on lanl
    `main` and on #985 alike, so it cannot tell one commit from another
    (the LiuWestFilter import already tells PyPI's 1.8.1, which has no
    `lwf`, apart). The commit can be checked in the installed
    distribution's direct_url.json (`vcs_info.commit_id`, PEP 610).
  - #985 has no Windows CI: its tests run on Linux only, and Windows is
    not among its classifiers. FluBNF's windows-latest steps (the real
    BNG2.pl under Strawberry Perl, the record of bngsim under a non-ASCII
    folder) and stage 2's install from scratch on a clean Windows account
    are the public engine's only Windows coverage.

- Submission (2026-10-07, at Ely's request): the weekly report changes
  alone go into `main` before tonight's run (pull request #30, branch
  `report-to-main`: five report commits from `dev` plus three report
  fixes), so the report Ely shares with the lab tonight carries them.
  Nothing the run reads changes: the run writes both CSVs before the
  report, the report writer is inside its own try/except, and the only
  `pipeline.py` lines touched are hover and heading strings inside
  `_write_weekly_report`. Checked before the merge: the full suite and CI
  on Linux and Windows; the same inputs rendered through `main`'s and the
  branch's code give identical bundles (only the wording differs); edge
  runs (Groundhog only, Oracle SIHRS only, US only, one state, gaps,
  zeros) behave as on `main`. The rest of the 2026-10-05 pass stays on
  `dev`. Readiness, checked 01:00 UTC: CDC's hub is still at ee477e74
  (nothing new since your check), `tasks.json` lists 2026-10-10 (window
  2026-10-04 to 2026-10-07), both cards on the hub equal ours, and a
  Groundhog file from `main` re-dated 2026-10-10 passes the app's 17
  checks and CDC's 30% rule (largest share 0.117%). CDC's R validator
  could not run here (no hubValidations); the laptop's R check or the
  hub pull request's checks are the authoritative ones tonight.

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
  installed; model.md says the laptop has hubValidations 2.1.1), check
  the clone the app reads, on the laptop
  `~/Documents/GitHub/FluSight-forecast-hub` (model.md): `ls
  <hub>/hub-config <hub>/src/validations`. If either is missing, one
  command widens it: `git -C <hub> sparse-checkout add hub-config src
  model-metadata`.
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

- For Ely (2026-10-13 Sandbox audit), confirmed but not changed: unsaved
  edits in the macOS window (the leave-page prompt may never show there;
  one try on a Mac settles it); a Check note when the first data row is
  after t = 0 (Oracle SIHRS starts do that by design); a grouped CSV with
  one unreported week cannot load (the Data tab's rule too); FluBNF.bat
  offers Perl on one open only; the trajectory layout with a gap week and
  "collapsed" from one low ESS week (a real run folder from a student
  settles both); elapsed time beside the progress bar; network generation
  runs the whole actions block. CI never runs the real Perl and BNG2.pl
  path, and the page scripts are tested on macOS only.
- For Ely (2026-10-05 design pass), not built yet: a live "This week"
  card on Home; a submission checklist and "Mark as submitted" on the
  due round; this week against last week before submitting; score CSV,
  score map and season comparison in the Retrospective; a smaller
  exported season file (23 MB now). Also Ely's: CITATION.cff version,
  date and authors; the TEAM.md row in the docs index.
- Number conflicts the docs pass could not settle from the repo: Oracle
  SIHRS season figures 0.767 / 0.697 / 0.781 (README, home) against
  in-app replays 0.767 / 0.702 / 0.782 (FLUSIGHT-2026-27.md); bare
  analogue 2025-26 0.618 (README, ORACLE-SIHRS.md) against 0.621
  (SITE.md, the sealed tree).
