# G17 hub-setup: proposal (A)
Base: origin/dev 55fd84e

How: a dev server and a prototype server with FLUBNF_HUB=/nonexistent and
FLUBNF_BNG=/nonexistent/BNG2.pl (this machine has no engine either), text
read from Home, Data and Forecast, POST /run and POST /freshness. DA-22:
each server pulled into its own private copy of the hub clone (cp -a; the
shared clone is never pulled). HM-13: the bug's own setup, an 8 s sleep
added to `_warm_versions` in each served copy only, with check() passing
(FLUBNF_PY_ENGINE and FLUBNF_PYBNF at existing stand-in paths).
Screenshots at 390 px light and 1280 px dark: no sideways scroll.

## WI-08 (also: DA-06)
- Reproduced:
  - /data: "Data through none", "Hub clone not checked"; nothing says the
    folder is missing.
  - Check for new data: "offline", with "fetch failed: [Errno 2] No such
    file or directory: PosixPath('/nonexistent')" (DA-06).
  - POST /run for 2026-04-25 (Groundhog, Arizona) is accepted, recorded
    as a run, and ends "error" with "[Errno 2] No such file or directory:
    '/nonexistent/auxiliary-data/locations.csv'".
  - For 2026-10-17: "Not run: the hub archived no snapshot dated
    2026-10-17. Nearest earlier: 2026-04-25."
  - Not reproduced on 55fd84e: the shipped 2026-04-25 badged "not
    archived · target-data". `vintages()` now includes the shipped
    snapshots, so `live_only` is "" and the badge stays hidden (checked in
    Chromium).
- Root cause: nothing asks whether the clone is there. check_freshness
  runs git in a missing folder, and /run reads locations.csv after the
  claim.
- Fix:
  - core/data.py `hub_missing()`: the hub's locations.csv is not a file.
  - `check_freshness` returns at once with "no hub clone at <path>"; the
    pill reads "missing".
  - Data: an alert in place of the empty state, "The FluSight hub clone is
    not at <path>. To fetch it, run ./setup.sh and relaunch the console."
    The Windows step is setup.ps1's command and FluBNF.bat, as FluBNF.bat
    prints it (templating `setup_hint`). The Hub clone badge reads
    "missing".
  - Forecast: the same alert above the form (hub runs only).
  - /run: refused before the claim, "Not run: the FluSight hub clone is
    not at <path>." with the step in its "?". Dataset runs have their own
    route and are untouched.
- Live after: the alerts, "missing" (the check's JSON: pill bad, words
  "missing", detail "no hub clone at /nonexistent"), and the refusal with
  no run recorded.
- Tests: `test_hub_setup.py::test_with_no_hub_data_and_forecast_say_so_and_a_run_is_refused`.

## HM-08 (medium; also: none)
- Reproduced: yes. With the hub and BioNetGen missing, the only action
  line is "To add the particle-filter engine, run ./setup_engine.sh ...".
  With only the hub missing there is none.
- Fix: Home's action line takes the most basic missing piece first. The
  hub and BioNetGen come from setup.sh / setup.ps1: "To fetch the
  FluSight hub data and BioNetGen, run ./setup.sh and relaunch the
  console." (or either one alone). Then the engine, then Perl, as before.
  Still one line.
- Tests: `test_the_setup_card_counts_the_engine_once_and_leads_with_setup`,
  `test_with_only_the_hub_missing_the_card_says_how_to_fetch_it`.

## HM-11 (also: none)
- Reproduced: yes. The badge "5 not installed ?" names "FluSight hub,
  BioNetGen, Engine venv, PyBNF, bngsim". The rows include "engine venv
  python (pybnf + bngsim)" and "PyBNF fork with fit_type=pf".
- Fix: routes/home.py, one component: `ENGINE = "Particle-filter
  engine"` for the venv, the fork, PyBNF and bngsim in both name maps
  (the badge counts it once). `_missing_rows` folds the venv's and the
  fork's rows into one "Particle-filter engine" row whose "?" names both
  paths. The page script's names follow.
- Live after: "3 not installed: FluSight hub, BioNetGen, Particle-filter
  engine"; three rows; no "fit_type" or "venv" on the card. The
  Component versions row still lists PyBNF and bngsim, each with its
  version (they are versions, not a count).
- Tests: as HM-08's first; test_setup_badge's union pin now reads the
  engine's one name.

## HM-12 (also: none)
- Reproduced: yes. bngsim "not installed" has the pin "?".
- Fix: the pin note's condition leaves out "not installed" (home.html).
- Tests: in the Setup card test.

## HM-13 (also: none)
- Reproduced: yes, with the bug's setup. Dev paints "All components
  installed" while every value reads "resolving…", then flips to "2 not
  installed" with no names.
- Fix:
  - home.html: while any version reads "resolving…" and check() reports
    nothing, the badge is a neutral "checking…".
  - The script waits until no value is resolving. If what is missing then
    differs from what was painted (or the badge says "checking…"), it
    reloads once. The fresh render's badge, its "?" and its rows all name
    it, as the expected asks. No loop: after the probe the server paints
    the same answer.
- Live after: "checking…" at first paint, then "1 not installed" with "?"
  "Particle-filter engine" once the probe lands (8 s).
- Tests: `test_the_badge_says_checking_until_the_versions_land`.

## HM-14 (also: ME-19)
- Reproduced: yes. "Perl /usr/bin/perl" in Component versions (Home);
  Methods' Under the hood reads the same value.
- Fix: versions.py probes `perl -e "print $^V"` (an argument list, no
  shell, so Windows reads it too): "5.38.2"; "installed" if it will not
  say; "not installed" as before.
- Live after: "Perl 5.38.2" on Home and Methods.
- Tests: `test_perl_reads_as_a_version_not_a_path`.

## DA-22 (also: none)
- Reproduced: yes, in a private copy of the hub. Update data: "New data:
  through 2026-10-24 (was 10-17) · +1 week · 69 revised values"; the page
  reloads with "Hub clone not checked".
- Fix: routes/data.py: a successful pull leaves its state
  (`data.fresh_after_pull`: level with origin) for the page it reloads,
  one-shot. A later visit reads "not checked" until a check; nothing
  claims "up to date" days later.
- Live after: "Hub clone up to date" right after the pull.
- Tests: `test_right_after_update_data_the_clone_reads_up_to_date`.

## Checks
- New `app/tests/test_hub_setup.py` (6): all fail on 55fd84e and pass here.
  test_setup_badge's pin of "PyBNF" as its own component updated
  (HM-11's symptom).
- Test setup: the suite's hub never exists (conftest's NO_HUB), and about
  60 tests post /run with the hub's data faked. So conftest gains an
  autouse `_hub_present` (data.hub_missing reads False) and an opt-in
  `hub_absent` with the real check, as `_shipped_vintages_in_tmp` and
  `pf_engine_ready` already do for the snapshots and the engine. My
  missing-hub test opts in. The layout golden (golden/ui_routes.json)
  lists the new Jinja global `setup_hint`.
- ruff clean. Full suite (FLUBNF_HUB=/nonexistent): 3575 passed, 155
  skipped, 0 failed.
- Invariance: not needed (no run path changed; /run only refuses earlier
  when the hub is missing).
- Windows: the setup step names setup.ps1 and FluBNF.bat; the Perl probe
  has no shell quoting.

## Patch
G17/proposal.patch (git diff origin/dev...proto/G17-A)
