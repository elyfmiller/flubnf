# App lane notes

The console, the launchers (FluBNF.command, FluBNF.app, FluBNF.bat,
setup.sh, setup.ps1), Windows, CI and the docs, and the shared context
pages (TEAM.md, team/README.md, FLUSIGHT-2026-27.md). Works on `dev`.

## Now

- 2026-10-30 (later): student workspace step 4, experiments and the
  compare page, on `dev`
  ([a1ea679](https://github.com/elyfmiller/flubnf/commit/a1ea679)). The
  Sandbox gallery gains one Experiments card: the four choices (a
  shipped model or a registered `name@n`; season; smoke, pilot or full;
  the Oracle step, on by default for `sihrs` only), Start, and the list
  of experiments with each one's relWIS beside the shipped replay's. No
  new tab. An experiment runs on this computer under the Sandbox's
  claim, so the weekly run, shipped and dataset replays and Sandbox fits
  refuse while it runs and it refuses while they do; Stop is
  `/sandbox/stop` with `experiment=`, and Resume is Start with the same
  choices. `experiments.score` writes `summary.json` as step 1 laid it
  out (both sides rescored against one truth, the shipped replay read
  through read-only readers only, sums over the cells both scored, US
  like for like), at every segment end and again on a view when the
  truth, the stored weeks or the shipped replay moved. The compare page
  (`/sandbox/experiments/<id>`) reads `summary.json` only: relWIS, log
  relWIS and coverage for the model, the shipped replay and the model
  against it, by location, week and horizon, failed fits, and what ran;
  Start, the page's JSON, Stop and Delete answer JSON when asked. No new
  problem code, CSS rule or Jinja global, and no Engine-lane file
  changed. Tested: the full suite with only the 22 failures this Mac
  already had; the workbench, the Retrospective and the weekly run's
  refusals byte for byte as before; Ely's retro tree unchanged by every
  read. In the browser on a spare console, two real smoke runs of
  2024-25 (about 50 s each): the unedited template, Oracle step off,
  relWIS 1.710 against the shipped Liu-West filter alone's 1.656 on the
  same 16 cells (1 replicate against 3), and `sihrs`, Oracle step on,
  1.272 against 1.219; Stop, Delete, the JSON answers and phone width.
  Defaults taken, for Ely to change: a full experiment is offered on
  this computer before step 5 (it holds the engine for hours, so a
  Monday run must stop it first); the model list offers `sihrs-2strain`
  and `sihrs-natg` too; a summary is rescored on view when stale (about
  weekly in season); with the Oracle step on, US is compared only with a
  shipped US of the same kind, which no stored season has yet, so it
  reads n/a. Step 5 (the runner, queue and estimates on the Mac Studio)
  waits for Ely's go.
- 2026-10-30: student workspace step 3, the Sandbox side, on `dev`
  ([ed75622](https://github.com/elyfmiller/flubnf/commit/ed75622)). New
  model gains one start, "Oracle SIHRS template, for replays", in the
  Oracle SIHRS group and only with a hub; it uses the Location, Forecast
  date and Season start fields that exist. It writes the production
  template with its placeholders kept (`{{POP}}`, `{{I0FRAC}}` ...)
  under a three-line note, the shipped priors, and the Oracle start's
  data. The Sandbox fills the placeholders in memory, never in the files
  (`sandbox_data.filled_bngl`): N is the population of the location
  data.exp was loaded for and i0 is pinned from its counts, as a replay
  pins it; Check, Save and run and Simulate data use it, the diagrams
  sample values, and Set N is not offered where N is a placeholder. For
  such a model Check says Ready for replays or Not ready, each finding
  with its code, and which registered version the files already are;
  Register, a button in that line only, saves the editor text and
  freezes the next version (`beta2@1`), or names the one that holds
  them. One new code, PLACEHOLDERS_UNFILLED. Models without placeholders
  are unchanged: their Check JSON, runs, diagrams and pages compared
  byte for byte with `dev` before. A version file that is not a regular
  file now reads as MODEL_CHANGED (left over from step 2). Added: one
  start option, one route, and the Register button inside Check's Ready
  line; taken away: Set N on the template. Tested: the full suite with
  only the 22 failures this Mac already had, and in the browser on a
  spare console (create, Check, Register @1, Not ready on a `pf_jitter`
  line, an edit, Register @2; phone width). Defaults taken, for Ely to
  change: the template from the hub only (the core takes a dataset group
  too); registered versions listed nowhere until step 4's experiment
  form; Register saves unsaved editor text first, as Save and run does;
  no location means a run or Simulate is refused in words.
- 2026-10-29 (later still): student workspace step 2, the engine side,
  on `dev`
  ([0abd3e8](https://github.com/elyfmiller/flubnf/commit/0abd3e8),
  [2f55419](https://github.com/elyfmiller/flubnf/commit/2f55419)). No
  page, button or setting changes. `pf.prepare` reads
  `spec.extra["model"]`: a shipped name (`sihrs`, `sihrs-2strain`,
  `sihrs-natg`) gives today's cells for its variant; a library version's
  verified text becomes the cell's template, and its cumulative output
  and priors are parsed and written again (`library.replay_conf`), never
  copied. `fit_i0`, `prior_ranges`, `iota` and `neff_cap` are refused
  beside a library model. `retro.run_season(weeks=)` replays an
  experiment's frozen weeks and never resumes a folder holding another
  experiment; that refusal comes before any flag is cleared.
  `experiments.replay` runs a plan with the shipped Groundhog beside the
  model and the Oracle step on or off, and checks the model's
  fingerprint before each week. Two new codes: SUFFIX_IN_MODEL, and
  LINE_BREAK_NOT_ALLOWED (PyBNF splits lines on a form feed and the
  like, BNG2.pl does not, so a comment could hide a statement from the
  structure rules). The shipped cells are pinned byte for byte by
  `test_prepare_golden.py`, committed before `pf.py` changed. On the
  real hub (2024-12-28, California and Vermont), the shipped, 2strain
  and natg cells are the same before and after, by `variant` or by name,
  and a library copy of sihrs differs by one comment line in `m.bngl`.
  Experiments now keep the Groundhog (about 1% of a filter week), which
  reverses step 1's default. Tested: the full suite with only the 22
  failures this Mac already had. Left for later: a library model with
  `reporting` (step 7), and refusing a version file that is not a
  regular file (done in step 3).
- 2026-10-29 (later): student workspace step 1, the file formats, on
  `dev` ([e2dba2e](https://github.com/elyfmiller/flubnf/commit/e2dba2e)).
  No page, button or setting changes. `app/core/library.py`: the Ready
  for replays rules, the replay normal form and fingerprint, Register
  into `sandbox/library/<name>/<n>/`, `name@version`.
  `app/core/experiments.py`: `experiment.json` (model, season, size,
  oracle), the size presets, the shipped replay compared with,
  `summary.json` as sums. `app/core/problem_codes.py`: 52 codes, pinned
  by `app/tests/golden/problem_codes.json`; Check returns a code beside
  each problem and warning (`SandboxError` gained `code=`). The structure
  rules read model.bngl as BNG2.pl does, so a statement outside a block,
  which BNG2.pl runs as Perl, is refused. Defaults taken: smoke and
  pilot run 1 replicate against the shipped 3; with the Oracle step off
  a shipped side exists for 2024-25 only (`quantiles.null`); experiments
  skip the Groundhog (step 2 keeps it). Tested: the new and Sandbox
  tests (379), and the full suite with only the 22 failures this Mac
  already had. Step 2 (engine side) waits for Ely's go.
- 2026-10-29: the student workspace, designed with Ely (decisions under
  Decided). It is built one step at a time, in the order of the steps
  below, starting with the file formats, and under the rule in UI-KIT.md
  "Before adding a control".
  Students try beta variants and other configurations of SIHRS, later
  RSV and COVID-19 models, from the Sandbox through to replays, for
  people and scripts alike:
  - Models: a "SIHRS template" Sandbox start keeps the per-state
    placeholders (`{{POP}}`, `{{S0FRAC}}`, `{{I0FRAC}}` ...); Check gains
    "Ready for replays"; Register freezes a version with a fingerprint of
    its files, and any edit is a new version.
  - Experiments: one folder each, never the shipped season tree; three
    sizes (smoke: 2 locations, 2 weeks; pilot: about 10 locations every
    other week, 1 replicate; full: the shipped settings, 7.0 h for
    2024-25 on Ely's Mac); a compare page against the shipped replay on
    the same cells (log WIS, relative WIS, 50/80/95 coverage); one
    `summary.json` for the page and for scripts. A shipped replay's
    `oracle.json` already keeps the filter's own quantiles
    (`quantiles.null`), so a variant without the Oracle step compares
    without another replay; scoring them is new.
  - On the runner: one queue, a time and disk estimate before a job is
    accepted, lean storage for experiments (forecasting samples dropped
    once a week is scored: about 1.5 GB to under 100 MB a season), the
    Storage tab by experiment.
  - Every page action also a `flubnf` command with `--json` output and
    fixed exit codes; Check's problems get stable codes; one guide for
    anyone working from a terminal. Students' work lives in untracked
    folders only: the launchers set aside edits to tracked files.
  - Pathogen a field on models, datasets and experiments; RSV and
    COVID-19 come in first as snapshot datasets and run the plain filter.
  - From the protection audit (2026-10-29), also to build:
    - A check on pull requests from forks. It refuses co-author or
      generated-by lines, and commits authored or committed under Ely's
      emails. It flags changes to the launchers, the installers,
      `.github/` and the engine updater. `proposals/<name>/` holds only a
      fixed list of file names, with no links, executables or oversized
      files; a name list, so the check names no tool.
    - The runner cleans every model before it runs. A model's actions
      block is code (BNG2.pl runs each action through Perl `eval`), so it
      gets FluBNF's own. `priors.conf` takes keys from a fixed list only
      (`postprocess` would run Python). The `suffix` may not name a path.
      Each job has time, memory and disk limits.
- 2026-10-28 (later, Ely's answer to the Open question below): a
  Submitted / Before cap switch per location
  ([0e16723](https://github.com/elyfmiller/flubnf/commit/0e16723)), to
  review how much the output stage narrows the width. Where the cap moved
  a location's file (43 of 53 on Monday's 15x-shrink run), its panel and
  its detail open on what went to the hub, read from the run's own CSVs
  beside the report (`submission/`, in the workroot and the archive
  alike, so no change to `ui/pipeline.py`); Before cap shows the model's
  own, after the Oracle step and the narrowing (Ely chose that over the
  filter's own). The panel, the US panel and the detail's fan and numbers
  move together. The h3 97.5% figure reads the model's own, then the
  file's (55x -> 15x). Tested: the report tests (140), the full suite
  (the same 21 machine-specific failures), Monday's report in the
  browser, desktop and phone.
- 2026-10-28: Ely's weekly-report notes, on `main` through
  [#62](https://github.com/elyfmiller/flubnf/pull/62)
  ([1ff557a](https://github.com/elyfmiller/flubnf/commit/1ff557a); Ely
  merged it while its checks were still running). The header picks the
  theme: System or the console's eight. Served by the console it shares
  the console's choice; a saved copy keeps its own (`rpTheme`). Hide map
  folds the categorical map and its keys on screen, and paper always
  prints it. The live panels open with the median and the whole 95% band
  in frame (the printed drawing keeps CLIP_X). Beside each name: each
  model's horizon-3 97.5% quantile over the mean of the last three
  reported weeks (`flubnf.tailcap.recent_level`), red above 15x.
  Found: the report's bands and that figure are the model's own, before
  the output stage's upper-tail cap. `ui/pipeline.py` hands the report
  `pf_q`/`an_q` from before the cap, the detail fans too: on Monday's
  15x-shrink run West Virginia's Oracle SIHRS h3 97.5% is 425 in the
  report and 115 in the file, and US Groundhog 78,635 against 61,180.
  Medians agree. Tested: the report tests (137), the full suite (the same
  21 machine-specific failures as clean dev), Monday's report in the
  browser in two themes at desktop and phone width.
- 2026-10-26 (late, Ely's go): the public engine's real install in CI, on
  `engine-public` ([55bce80](https://github.com/elyfmiller/flubnf/commit/55bce80)),
  so Windows no longer waits for the engine lane's lock. The
  `public-engine-wheel` job builds the PyBNF wheel from lanl/PyBNF
  8410f794 on macOS and writes a hashed lock for it
  (`scripts/make_test_lock.py`, never the engine lane's lock).
  `public-engine-install` then runs FluBNF.bat's public block in cmd.exe on
  Windows, and `setup_engine.sh --public` on macOS, against that lock,
  served over https on localhost, into a venv under `Jane O'Brien (Lab)`.
  It runs a fresh install, an open with nothing to do, a new lock (the
  wheel alone goes back), a tampered hash (refused) and PyBNF's lesson 50
  in the venv (`tests/test_public_engine_real.py`). Here on the Mac all
  five pass (108 s cold, 34 s with pip's cache). The Windows leg's first
  run is CI's on [#61](https://github.com/elyfmiller/flubnf/pull/61).
  Found: PyBNF asks for BNG2.pl (`BNGPATH` or `bng_command`) even with
  `bngl_backend = bngsim`, so the public route still needs BioNetGen and
  Perl.
- 2026-10-26 (evening): Wednesday's overrides on `main` (d7d13e5), end
  to end through the Forecast form, in my own console (port 8790, a temp
  state folder, private engine 2fdadee0): both models, all 53
  locations, real-time on the hub clone's newest week (as-of 2026-10-17;
  Wednesday's round needs 2026-10-24's data, due Wed Oct 28), with
  `pf.seed_denominator season_total_early`, `oracle.w 0.25`,
  `oracle.narrow 0.7`, `output.tail_cap 15`, `output.tail_mode shrink`.
  - Finished `ok` in 314 s (preparation about 15 s, then 53 locations x 3
    Independent Runs, 159 of 159 ok, no preparation failures). Two files
    under the `-modified` names (the hub-name box was left unticked),
    4,876 rows each, 53 locations, horizons 0 to 3, quantiles in order,
    no negatives or NaNs. The run page, its report, Output and Home all
    answer 200; no errors in the console log.
  - The Oracle side (`oracle.json`): applied to 53 of 53, no abstentions,
    no guard hits; w 0.25, narrowing k 0.7 applied; admissions bank 396
    paths from 2022-2025, FluSurv-NET bank 381 paths from 14 seasons,
    mixed half and half; submitted seed 2026091801. The tail cap touched
    156 Oracle SIHRS cells and 103 Groundhog cells. US medians h0-h3:
    Oracle SIHRS 5,907 / 7,375 / 9,335 / 11,961, Groundhog 5,236 / 6,769
    / 9,180 / 11,708.
  - For anyone running main from a worktree: BNG2.pl is looked up in the
    checkout's own `.venv`, so a worktree without one fails preparation
    for every location ("Can't open perl script"); set `FLUBNF_BNG` to the
    app venv's BNG2.pl.
- 2026-10-26: the public-PyBNF move, console side, on branch
  `engine-public` (from `dev` 554ac57; nothing from it goes to `dev` or
  `main` until Ely says so). Ely sent the plan with the task, as
  engine.md still shows 2026-10-15's; where engine.md's update differs,
  engine.md wins.
  - One lock, `engine-requirements.txt` (the engine lane's), read only
    through `scripts/engine_lock.py`: the PyBNF wheel's URL and sha256
    come from its `pybnf @` line, so they arrive with the lock and no
    installer changes; `check` holds a venv to the lock (the Liu-West
    filter imports, bngsim as pinned, pip's record of the wheel).
  - macOS and Linux ([a6e3e91](https://github.com/elyfmiller/flubnf/commit/a6e3e91)):
    `setup_engine.sh --public` installs into `~/.venvs/flubnf-public`
    with `--require-hashes --only-binary :all:`, refuses the private
    engine's venvs, and records `FLUBNF_ENGINE=public` in `.flubnf.env`
    (`--private` drops it). FluBNF.command, SetupEngine.command,
    setup.sh, install.sh and reinstall.sh follow the route. bngsim's
    unpinned source-build fallback is gone ([69ac38e](https://github.com/elyfmiller/flubnf/commit/69ac38e)).
  - Windows ([f2c284f](https://github.com/elyfmiller/flubnf/commit/f2c284f)):
    `setup.ps1 -Engine public|private` records the choice in
    `.flubnf.env.cmd` only; FluBNF.bat's `:publicengine` installs into
    `%LOCALAPPDATA%\FluBNF\venv-public` through the private block's venv
    code with an x64 3.12-only gate. Frozen bytes and the 4049 offset as
    they were.
  - CI ([163e90b](https://github.com/elyfmiller/flubnf/commit/163e90b)):
    the Windows-wheel step reads the lock (`engine_lock.py deps`, the
    wheel's line left out) with `--require-hashes`; a notice and a pass
    while there is no lock. Docs ([24bd622](https://github.com/elyfmiller/flubnf/commit/24bd622)):
    ENGINE.md "The public engine (opt-in)", WINDOWS.md, LAUNCHERS.md and
    the rest; students keep the engine file.
  - Tested on Ely's Mac: tests/test_engine_public.py (26; sample locks,
    stand-in venvs), the Windows text tests and the launcher byte test,
    the CI step's script on a real lock of bngsim[antimony]'s six Windows
    wheels (passes; one tampered hash fails; no lock passes), refusals
    and a sample-lock install in a throwaway home (stops at the wheel's
    404, as it should before the release), and both full suites: the
    same 21 failures as clean `dev` on this Mac (it has an engine, which
    test_no_engine does not expect; launcher tests), none new. Not run: a public install end to end (no lock or wheel
    yet); FluBNF.bat under cmd and setup.ps1 under PowerShell (no Windows
    or pwsh here); the Windows-only tests. CI runs through draft pull
    request [#61](https://github.com/elyfmiller/flubnf/pull/61)
    (`engine-public` into `dev`, opened at Ely's word for CI only: never
    merged without it), on each push to the branch.
- 2026-10-26 (later): the public route end to end on Ely's Mac, ahead of
  the engine lane's lock: a wheel built here from lanl/PyBNF 8410f794
  (paths at most 53 characters), a hashed lock of the 40 packages it
  resolves to with `bngsim[antimony]==0.15.1`, served over https on
  localhost, and the real `setup_engine.sh --public` in a throwaway home
  (never `~/.venvs`). It installed in 33 s and checked out; a second run
  took 2 s and no pip; a tampered hash was refused; a home path with a
  space worked; PyBNF's lesson 50 (`job_type = lwf`, 2,000 particles, 42
  rows) ran in that venv in 11 s with all six Results/LWF files. One fix
  from it ([696b3aa](https://github.com/elyfmiller/flubnf/commit/696b3aa)):
  pip keeps an installed pybnf 1.8.1 whatever wheel the lock names, and
  forcing every package took 465 s; a stale venv now gets pybnf alone
  again (4 s), every package only if the check still fails, on both
  platforms. CI on #61 passed before the fix. Not run: a forecast through
  the console on the public engine (`pf.py`'s public writer, runner and
  reader are the engine lane's, not on the branch yet), so no comparison
  with the private engine here; that is stage 2.
- 2026-10-26: the App lane moved from the cloud session "FluBNF 2.0" (now
  a record only) to Ely's Mac, in Ely's clone, and can message other
  agents. PR #60 (G01 to G10: 53 bugs, 20 of the 25 S2s) is on `main`
  (d7d13e5). The fix run is paused for Ely's "go" on G11; the S2s still
  open are HM-01, ME-03, ST-01, SB-01 and SB-02.

- 2026-10-25: Ely's bug hunt, find only, on `dev` at bcaafb7: one pass
  per tab, one for wiring, one for the look of every page, and the full
  suite. 208 bugs after merging duplicates (25 S2, 86 S3, 97 S4, no S1),
  in [bug-hunt-2026-10-25.md](bug-hunt-2026-10-25.md) with each bug's
  steps and evidence in the JSON beside it. Not covered: Oracle SIHRS
  runs (no engine on the test machine). The fix run comes separately.
  For Model: the Groundhog record on Home, Models and Methods is still the
  own-state form's 0.660, not the size-matched form's 0.642 (HM-01).
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

- 2026-10-29 (Ely): minimalism. The console is already close to too much
  to take in, the shipped models' settings most of all, so the student
  workspace adds as few choices as it can. An experiment asks for a
  model, a season, a size (smoke, pilot, full) and the Oracle step on or
  off; the sizes are presets, never separate particle, replicate,
  location or week fields. New work goes into the tabs that exist, and
  nothing is added to the shipped models' forms. Each step's review
  counts what it adds. The rules: UI-KIT.md, "Before adding a control".
- 2026-10-29 (Ely): the student workspace build changes the Engine
  lane's files directly where the design needs it (`pf.py`, `retro.py`,
  `sandbox.py` and their tests), instead of waiting on the Engine lane.
  The work lands on `dev` like any other, and the Engine lane's notes
  are read first for anything in flight.
- 2026-10-29 (Ely, after a protection audit): the wiki is off (never
  used). Actions run only GitHub's own actions, which are all any branch
  uses. `tests.yml` states a read-only token
  ([1b83158](https://github.com/elyfmiller/flubnf/commit/1b83158)).
  TEAM.md now holds the rules for the two machines, Ely's credentials,
  reviewing a fork's pull request and merging it. Found: only Ely's
  account can write here, so the risks left are ways to act as Ely.
  These are Ely's credentials on the students' Mac Studio, the
  students' shared cloud account connected to Ely's GitHub, and student
  code or models run where Ely's login is. A BNGL file runs Perl when
  BNG2.pl reads it.
- 2026-10-29 (Ely): GitHub rules, set that day (rulesets 26160504 and
  26160505). `main` changes only through a merged pull request whose six
  checks are green (`test` and `test-windows` on 3.11 and 3.12,
  `windows-own-perl`, `windows-setup-script`), with no bypass, no force
  push and no deletion. The checks do not ask the branch to be up to
  date, since main's merge commits are never in `dev`. Merge commits only:
  squash and rebase are off for the repository. `dev`: no force push or
  deletion. CI on every pull request from outside waits for Ely's
  approval (before, only a first-time contributor's did). TEAM.md says so.
- 2026-10-29 (Ely): the student workspace (plan under Now).
  - Students, and agents working for them, fork, branch and open pull
    requests against `dev`; Ely and Ely's agents review; only Ely merges.
    Everything in the repository is human-authored: commits under the
    contributor's own name, with no co-author trailers or generated-by
    lines. A CI check on pull requests will refuse them, naming no tool.
    No file in the repository is written for a particular assistant: the
    guide is for anyone working from a terminal.
  - A proposal is a folder, `proposals/<name>/`: the model files, the
    experiment settings, the results summary and the student's own
    write-up. CI checks it, and review reruns it on the lab runner, where
    the fingerprints must match. It becomes a shipped model only through
    Ely's lanes.
  - Long runs go on the lab's 24-core Mac Studio, a different machine
    from the lab Mac the Engine and Model lanes use. All the students
    work in one shared lab account there, which has the whole disk, and
    reach it off-site through remote sessions. One shared runner, a
    FluBNF install on `main`, works one queue. Each student's work sits
    in a folder of their own, and code from a fork never runs on the
    runner. Nothing caps the disk, so the size checks are the guard: a
    job is refused when it would leave too little free space, and the
    storage figures are a command with JSON output as well as a page.
  - The Oracle step is a switch on every experiment: it belongs to the
    shipped SIHRS, and other models may try it or not. It is off by
    default for any other model (App's proposal).
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

- All lanes (2026-10-29): `main` refuses a merge pushed by hand; merge a
  `dev` to `main` pull request with `gh pr merge <n> --merge --repo
  elyfmiller/flubnf` or the website, once all six checks are green.
  `dev` refuses a force push. Submission: the hand-pushed merge in your
  notes no longer works.
- All lanes (2026-10-29): read TEAM.md's new rules on reviewing a fork's
  pull request. Its code and models never run where Ely's GitHub login
  is, and only Ely's merge brings its work into `dev`. Cloud sessions:
  set the git name and email to Ely's before the first commit, merges
  included. 490cf08 (a merge into fix/G16-weekly-report, on `dev`
  through #70) carries the session's default identity, not Ely's. It
  stays in history, since `dev` takes no force push.
- Model (2026-10-29): your notes call the lab Mac "the Mac Studio"
  (model.md:5 and about ten more). The students' machine is a different
  Mac Studio, and the notes record Ely's `gh` login on yours. Please say
  "lab Mac" for yours.
- Engine (2026-10-29, from the protection audit):
  1. The engine pin by its full commit ID, in a constant of its own for
     `engine_update`'s compare and merge. Keep the 8-character name for
     archive names and display (`archive_name`, `cut_engine_archive.sh`
     and their tests). Today a fresh install takes the branch tip, and
     PyBNF-Private has three writers besides Ely and no branch
     protection on the Free plan.
  2. A fresh install (the `setup_engine.sh` clone, the bundle) ends at
     the pin by a fast-forward, not a detached checkout, so that
     `engine_update` still sees the branch.
  3. An engine archive in Downloads is installed with no hash check.
     Check it against the pin's archive.
  4. For the runner: the cleaning described under Now. PyBNF reads the
     model's `generate_network` options and `setOption` again, so
     cleaning only the first BNG2.pl call is not enough.
- Engine (2026-10-29, the student workspace). Ely has decided that the
  build changes your files directly (see Decided), so items 1 to 4 below
  and the audit's runner cleaning will arrive on `dev` from App's build,
  with their tests. Say in your notes if you have work in flight in
  `pf.py`, `retro.py` or `sandbox.py`, so the two don't collide.
  Items 1 and 2 are on `dev` (step 2, 2f55419). In `pf.py`:
  `LIBRARY_REFUSED` and `_named_model` (new), and `prepare` (a branch
  for a library model: its text as the cell's template, the DEFAULTS
  splice skipped, and its cumulative output and priors in `pf.conf`). In
  `retro.py`: `run_season` (`weeks=`, and the experiment check before
  `clear_flags`). `run_week`, `execute` and `collect` are unchanged. A
  library cell keeps the public engine's cell contract (one `model =`
  line, a two-column `.exp`, the four prior kinds, no new `pf_*` key);
  `test_pf_named_model.py` checks it. Item 1 is done in a narrow form:
  the three templates stay in `pf.py`, and the shipped names are
  composed from them (`library.shipped_files`), not stored as versions.
  Item 4 is on `dev` (step 3, ed75622): in `sandbox.py`, the template
  start (`from_shipped(template=True)`), `placeholder_n` and the
  placeholder fill in `prepare` and `simulate_data`; in
  `sandbox_check.py`, `check(name=)` fills them before BNG2.pl and adds
  Ready for replays; `sandbox_data.filled_bngl` is new. Item 3 (step 5)
  is not started. The items as first listed:
  1. `pf.prepare` takes a registered model (template, prior block,
     starting values) in place of TEMPLATE / TEMPLATE_2S / TEMPLATE_NATG,
     which become registered models themselves.
  2. A replay into an experiment's own root, with the model's
     fingerprint in `run_meta.json` and a resume refused when it
     changed, as for knobs.
  3. Lean storage for experiments: forecasting samples dropped once the
     week's national aggregate and scores are written, if nothing reads
     them later.
  4. Sandbox promotion (`sandbox.py`): a Sandbox model registered.
- Model (2026-10-29, the student workspace):
  - What makes a fair comparison: the same cells, a pilot's 1 replicate
    against the shipped 3, and how many seasons.
  - Whether `oracle.json`'s `quantiles.null` can be scored as the
    shipped filter without the step (the floor and the cap).
  - Which beta variants to offer as starts.
  - RSV and COVID-19 priors and season starts.

- Engine (2026-10-26, for `engine-public`): what App needs to finish.
  1. `engine-requirements.txt` at the repository root on `engine-public`:
     every package pinned with its hashes, the win_amd64 cp312 files'
     included, and one line `pybnf @ <release URL>.whl
     --hash=sha256:<64 hex>`, the release's tag naming
     8410f794e3fa4817572fd07fceb043ddec39d77b. pip-compile's layout is
     fine; `scripts/engine_lock.py` reads it. A Windows-only dependency
     missing from the lock fails on Windows under `--require-hashes`, and
     CI's check evaluates markers on Linux. Today's resolution has none
     (App resolved the wheel plus `bngsim[antimony]==0.15.1`: 40 packages,
     no platform marker among them, every one with a win_amd64 or pure
     wheel for 3.12), so this matters only if the set changes.
  2. The wheel's URL and sha256 in engine.md. Nothing to type into the
     installers: they read the lock.
  3. `flubnf/settings.py`: please confirm `PY_ENGINE_PUBLIC` reads
     `FLUBNF_PY_ENGINE_PUBLIC`, with `~/.venvs/flubnf-public/bin/python`
     and `%LOCALAPPDATA%\FluBNF\venv-public\Scripts\python.exe` as its
     defaults, and that `FLUBNF_ENGINE` takes private or public (the
     launchers warn and use private for anything else). The installers
     write and read those names.
  4. Keep `BNGSIM_NO_CODEGEN=1` for Windows runners on the public route
     (`pf.runner_popen_kwargs` sets it today); the docs say so.
  5. Doctor or the provenance check may call `scripts/engine_lock.py
     check` (the lock's wheel against pip's direct_url.json); say if you
     would rather import it.
  6. The console's public-engine code is yours (Ely, 2026-10-26).
     engine.md's stage 1 gives it to App (steps 4 to 8); please move it
     there. On `engine-public`, behind `FLUBNF_ENGINE`:
     - `app/core/engines/pf.py`: the public writer, runner and reader (the
       edition-2 conf with `bng_command`, the template without actions,
       `write_exp`'s one-week shift with `Hobs` and `nan` rows, the
       LiuWestFilter run, `collect()` from `Results/LWF`), and the import
       probe as the preflight. The `pf.*` knob and ledger names stay,
       mapped in the writer (decision 4).
     - `flubnf/settings.py`: the switch and `PY_ENGINE_PUBLIC` (item 3).
     - `app/core/engine_build.py`: the public pin, and its provenance from
       pip's `direct_url.json`. A wheel install has no git checkout; today
       a run records "PyBNF build 2fdadee0 (feature/particle-filter)" from
       git.
     - `flubnf/doctor.py` and `app/core/reclaim.py`; the Sandbox
       (`app/core/sandbox.py`) and custom datasets writing the public conf.
     - Tests on your fixture (Alaska 2025-01-11). CI has no engine, but
       the `public-engine-install` job builds a real public venv on Windows
       and macOS, if a console test should run against one.

     App's part stays the installers, the launchers, CI and the docs.
     Stage 2 waits on this and on items 1 and 2.

- Model and Submission (2026-10-15, answering Model's request of the same
  day): on `dev`, Home, Methods, /models, /model/analogue, the site,
  FLUSIGHT-2026-27.md and CITATION.cff print the shipped Groundhog
  (0.702 / 0.651 / 0.653, 0.660 on 17,116 cells, FluSight's cell rule;
  the pooled form 0.670 beside it) with your wording; each pooled figure
  names its cells, and Methods keeps the pooled form's 0.666 on 15,340
  only for its paired comparison with the bare analogue, labelled. The
  site names a tree replayed before 2026-10-15 "Groundhog (pooled form)"
  from its settings. Two wording points in your files, not edited here:
  (1) README's [^earlier] footnote says Home and Methods still print
  0.722 / 0.653 / 0.651 (0.666) on 15,340 cells; Home prints none now,
  so perhaps "the figures Methods keeps for the paired comparison with
  the bare analogue". (2) Card 1.2's methods_long says "A second donor
  pool built the same way from FluSurv-NET", which reads as weighted too;
  perhaps "matched the same way but pooled across sites". Submission:
  worth settling before card 1.2 goes to the hub fork.
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

- For Ely (2026-10-26, `engine-public`):
  - The ENGINE_WHEEL_URL and ENGINE_WHEEL_SHA256 pair is read from the
    lock's wheel line by one script that bash, cmd and PowerShell all
    call, rather than typed into each installer: the lock is then the
    only place it changes. Say if you wanted the pair in the installers.

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
