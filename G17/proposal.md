# G17 hub-setup: proposal (B)
Base: origin/dev 399f694 (the prototype was cut from 55fd84e; the two
differ in docs only)

How: a fresh server from dev with FLUBNF_HUB=/nonexistent and FLUBNF_BNG
pointing at a missing file (a second with the default hub, a third with
a private copy of the hub clone for Update data), the pages read with
curl and in Chromium at 1280 px light and 390 px dark; the cold-launch
case with an 8 s sleep in `_warm_versions` on a tree copy, the version
snapshot deleted, and FLUBNF_PY_ENGINE and FLUBNF_PYBNF pointed at
existing files so check() passes; the same on the prototype.

## WI-08 (also: DA-06)
- Reproduced: yes. Data: "Data through none", "Hub clone not checked", and
  with no data "Update data downloads it"; the Check: "offline ? fetch
  failed: [Errno 2] No such file or directory: PosixPath('/nonexistent')";
  Update data: "Could not update the hub clone: Not pulled: the hub folder
  /nonexistent is not a git clone of the FluSight hub." Forecast: nothing
  says the hub is missing; a Groundhog run for 2026-04-25 is accepted,
  recorded "real-time (newest week)" and ends "[Errno 2] No such file or
  directory: '/nonexistent/auxiliary-data/locations.csv'". The "not
  archived · target-data" badge on the anchor line is hidden on dev (the
  page's text holds it, hidden; `vintages()` counts the shipped weeks):
  that part does not reproduce.
- Root cause: nothing tests the clone's presence once; check_freshness
  reads the fetch's OSError as "offline"; /run reads the hub's files
  after the claim.
- Fix: `data.hub_missing(data=True)`, one test for every page: "there is
  no hub folder at <path>", or "the hub folder <path> holds no data
  directories (a sparse checkout without them)" (data=False: the folder's
  absence alone, for the fetch and the pull). Data: a warn line "No
  FluSight data: there is no hub folder at /nonexistent. To fetch it, run
  ./setup.sh and relaunch the console." in place of the empty state, the
  clone badge "missing" with the reason in its "?", the Check answers
  "missing" with "no hub clone: …" (no Errno, no PosixPath), Update data
  is refused with the same words and the setup step. Forecast: the same
  warn line above the anchor (not on a dataset page); /run refuses before
  the claim: "Not run: no FluSight data (there is no hub folder at
  /nonexistent)." with "To fetch it, run ./setup.sh and relaunch the
  console." as its detail. The step is platform-aware
  (templating `_hub_setup_hint`, `hub_setup_text`: setup.ps1 and
  FluBNF.bat on Windows).
- Live after: as above on both pages; the POST leaves no workroot and no
  ledger row; no sideways scroll at 390 px.
- Tests: test_hub_setup.py `test_the_hubs_absence_is_one_tested_state`,
  `test_data_says_the_clone_is_missing_and_what_fetches_it`,
  `test_forecast_says_the_clone_is_missing_and_refuses_a_run`.
  The suite points FLUBNF_HUB at a missing folder and fakes the hub's
  data layer and the runs, so an autouse fixture in app/tests/conftest.py
  fakes the clone's presence too (`hub_missing` answers "") and the
  `hub_check_real` fixture opts a test into the real check (test_hub_setup
  does); without it the refusal at /run stopped 50 faked runs across
  test_forecast_us_choice, test_knobs_wiring and others.
  test_data_view's archive fixture gets a hub folder beside its archive.
  The UI golden lists the new template global `hub_setup_hint`.
- Risk: /run gains one refusal before the claim; the run path after it
  is unchanged (invariance: see Checks). A clone present but without its
  data directories reads "missing" on the pages too, and the Check and
  the pull still run against it (pull_hub self-heals the sparse
  directories it can).

## HM-08 (medium confidence; also: none)
- Reproduced: yes. Hub and BioNetGen missing: "5 not installed", the one
  action line is the engine's; with the engine's files present and the
  hub missing: no action line at all.
- Fix: a first line, before the engine's: "To add the FluSight data and
  BioNetGen, run ./setup.sh and relaunch the console." (the pieces named
  as missing: "the FluSight data", "BioNetGen", or both; setup.sh fetches
  the sparse hub and installs bionetgen; Windows: "run setup.ps1 and open
  FluBNF.bat again"), then the engine line, then Perl's as before.
- Tests: `test_a_missing_hub_gets_its_action_line_first`.

## HM-11 (also: none)
- Reproduced: yes. "3 not installed ? Engine venv, PyBNF, bngsim", rows
  "engine venv python (pybnf + bngsim) ?" and "PyBNF fork with
  fit_type=pf ?", then "PyBNF not installed", "bngsim ? not installed":
  one install step counted three ways, four "?" marks.
- Fix: the engine is one component, "Particle-filter engine", in the
  badge (`_CHECK_NAMES`, `_VERSION_NAMES` and the recount script map its
  parts to the one name), in the rows (`_setup_rows`: one row per
  component in plain words, its paths together in its "?": "The particle
  filter's own Python, with PyBNF and bngsim. The PyBNF fork that holds
  the particle filter. Looked for at … (FLUBNF_PY_ENGINE) and …
  (FLUBNF_PYBNF)"), and in the versions row (one "Particle-filter engine:
  not installed" stat while the engine is absent by the check or by both
  probes; PyBNF and bngsim read their versions as before once installed).
  Every row's words are plain: "The FluSight hub's data: truth vintages
  and the locations table", "BioNetGen's BNG2.pl, which builds each
  cell's reaction network", "Perl, which runs BNG2.pl"; the check's own
  detail (a clone present but sparse, a checkout without pf.py) follows
  when it has one.
- Live after (the engine the only gap): "1 not installed ? Particle-filter
  engine", the engine's action line, one row, "Particle-filter engine not
  installed · BioNetGen 2.9.3 · Perl 5.38.2 · FastAPI · Plotly": two "?"
  marks where there were four.
- Tests: `test_the_engines_parts_are_one_component_in_the_badge_rows_and_versions`;
  test_setup_badge's pin of the part names updated (the bug's symptom).

## HM-12 (also: none)
- Reproduced: yes: the pin note's "?" beside "bngsim not installed".
- Fix: the note's condition also excludes "not installed" (and the
  folded stat has no note at all).
- Tests: `test_the_bngsim_pin_note_stays_off_beside_not_installed`;
  test_fewer_marks' `test_home_says_the_bngsim_pin_only_when_the_build_differs`
  still passes.

## HM-13 (also: none)
- Reproduced: yes, both halves. check() passing, probe slow: t=0 "All
  components installed" beside six "resolving…"; t=11 s "2 not installed"
  with no "?" (the recount only re-words the badge; with the outlook not
  yet ready the page reloads once and the tip appears, which hid it in
  one of my tries).
- Fix: while any version is still resolving the badge reads "checking…"
  (pending, id hm-checking) inside a `#hm-setup-state` slot; the recount
  waits until no value reads "resolving", then draws the badge again
  with its "?" naming what is missing (`FluBNFUI.badge` + `FluBNFUI.tip`),
  or "All components installed".
- Live after: t=0 "checking…", no tip; t=11 s "3 not installed" with the
  tip "FluSight data, BioNetGen, Particle-filter engine" (and "2 not
  installed · PyBNF, bngsim" → "Particle-filter engine" in the
  check()-passing case).
- Tests: `test_a_cold_launch_says_checking_until_the_probe_lands`.

## HM-14 (also: ME-19)
- Reproduced: yes: "Perl /usr/bin/perl" on Home's versions row and in
  Methods' Under the hood table.
- Fix: versions.py probes `perl -e 'print $^V'` (the perl
  settings.resolve_perl finds, else PATH's) and shows "5.38.2"; "installed"
  when the probe fails, "not installed" when there is none. Both pages
  read the same value.
- Tests: `test_perl_shows_its_version_not_its_path`.
- Windows: the probe runs FluBNF's own or Strawberry Perl as resolve_perl
  finds it; `$^V` prints the same there.

## DA-22 (also: none)
- Reproduced: yes (a private copy of the hub clone): after Update data the
  flash says "Up to date · data through …" and the badge "not checked";
  a Check's "up to date" is gone on the next GET too.
- Fix: routes/data.py keeps the last check's verdict (`_remember_check`,
  keyed by the clone it judged); a successful pull records "up to date
  with origin" (the pull just matched origin), and the page renders the
  kept verdict when it has no fresh one.
- Live after: the reloaded page reads "Hub clone up to date" with "up to
  date with origin" in its "?", after a pull and after a check.
- Tests: `test_the_hub_badge_keeps_what_update_data_established`.
- Risk: the verdict is this launch's memory; a restart starts at "not
  checked" as before.

## Checks
- Targeted: test_hub_setup (9), test_setup_badge, test_fewer_marks,
  test_platform_setup_hint, test_pull_hub, test_retro_no_hub,
  test_data_tab_qol, test_data_view, test_data_source, test_forecast_aids,
  test_no_engine, test_remembered_form, test_perl_bng_env,
  test_perl_preflight, test_site_smoke, test_pages, test_console_qol,
  tests/test_get_perl: all pass. ruff gate clean.
- Full suite (FLUBNF_HUB=/nonexistent), in a worktree pinned at the prototype: 3577 passed, 154 skipped; the two test_doctor failures are this container's Python 3.13, as on dev.
- Invariance: an all-53 Groundhog run on 2026-10-17 from dev (399f694) and from the prototype give the same submission file, md5 56da9201b416eb5c80317c849b55168e.
- Windows: the setup words name setup.ps1 and FluBNF.bat; the Perl probe
  takes the path resolve_perl gives; no file or encoding change.
- For Ely: none.

## Patch
G17/proposal.patch (git diff origin/dev...proto/G17-B)
