# Engine lane notes

The private PyBNF fork, the Liu–West filter, and its port to public PyBNF.
Works on the lab Mac, in repositories outside this one; it pushes only
this file here.

## Now

- 2026-10-29 (late): the console's public engine is on `engine-public`
  ([2de2ec8](https://github.com/elyfmiller/flubnf/commit/2de2ec8)),
  opt-in behind `FLUBNF_ENGINE=public`; private stays the default and
  nothing changes without the variable. `app/core/engines/lwf.py`
  translates each cell `pf.prepare` wrote into an lwf conf, runs one PyBNF
  process per cell from the public venv, and reads `Results/LWF` back.
  Measured on the lab Mac (in-house, retrospective):
  - The 144-cell replay on the wheel install (the release's wheel bytes
    and the lock's 38 packages) equals the private engine's draws on 144
    of 144 cells, forecasts and predicted counts byte for byte. A cell
    costs 2.07 times the private cost model at the median, 2.21 at most;
    the time budget now scales by 2.4 on public.
  - The console's own run of the Alaska 2025-01-11 cell equals the
    equivalence study's files and own-stream output byte for byte. All
    five Sandbox examples run.
  - Tests: 60 new (`app/tests/test_engine_lwf.py`, a 100 KB fixture with
    no lab paths); the full suite shows this Mac's same 22
    machine-specific failures, none new. An eight-agent review found 15
    real defects (a Windows drive-letter split, the readiness gate,
    weeks resumed across engines, Sandbox edge cases); all fixed, each
    with a test.
  - Still open: the wheel release (Ely publishes it; until then the
    lock's wheel address answers 404 and no real venv can match the
    lock), then `~/.venvs/flubnf-public` built from it as a stranger
    would, and a forecast run through the console end to end.

- 2026-10-29 (Ely's go on plan v3 and the wheel release): stage 1's
  engine side, on `engine-public`. **In flight there: `pf.py`,
  `retro.py`, `sandbox.py`, `engine_build.py`, `flubnf/settings.py`,
  `flubnf/doctor.py`, `reclaim.py`.** To keep out of the student
  workspace's way, the public writer, runner and reader go in a new module
  of their own (`app/core/engines/lwf.py`); `pf.py` and the others gain
  only small switch points on `FLUBNF_ENGINE`. `dev` is merged into
  `engine-public` (never rebased) before each push, so a change on `dev`
  shows up there as a merge. Done today:
  - The PyBNF wheel, rebuilt byte for byte from lanl/PyBNF 8410f794
    (pinned setuptools, `SOURCE_DATE_EPOCH` = the commit's time): sha256
    `18a59bc24caa99ae1b4cc14518a4233cf17a0e4edac45d50d5e4189413ee21e5`.
    Its release, `pybnf-8410f794e3fa4817572fd07fceb043ddec39d77b` on this
    repository, is Ely's to publish (pending).
  - The lock, `engine-requirements.txt`: the 38 packages measured in the
    144-cell replay (antimony, pandas, python-dateutil and six dropped:
    neither FluBNF nor `lwf` imports them) with every CPython 3.12 wheel's
    sha256, plus the wheel line. One platform split: cryptography 50.0.2
    has no Intel macOS wheel, so Intel Macs get 48.0.1 behind a marker.
    Intel Macs need macOS 15 (libroadrunner's Intel wheel). macOS
    arm64, Windows x64 and Linux x64 resolve to the same 38. Installed in
    a scratch venv in 20 s; the filter imports; bngsim 0.15.1, build
    458bf7d72354.

- 2026-10-15 (overnight, Ely lent the lab Mac): stage 1's engine part is
  done. `~/.venvs/flubnf-lwf` holds public PyBNF at the merge commit
  8410f794 with bngsim 0.15.1; fed the production engine's random inputs it
  reproduces production's forecast draws exactly on 144 of 144 cells, and
  its own-stream forecasts equal the October checkout's on 432 of 432, so
  the October equivalence (WIS ratio 1.0013) stands for the merged package.
  A cell costs 1.6 to 2.1 times production's. The merged tree passes every
  test here on Apple silicon (3.12, 3.13, 3.14, ruff, changelog, docs,
  bngsim 0.15.1). The App lane's handoff is under "For other lanes". Nothing
  in FluBNF or the production engine pin changes.
- 2026-10-15 (02:25 UTC): MERGED. lanl/PyBNF#985 is on public PyBNF
  `main` as merge commit 8410f794, all 26 commits kept: Ely's eight and 18
  Bill pushed onto the branch himself over three review rounds (one
  cross-platform defect, two gaps our fixes left, nine refusal and
  bookkeeping fixes, an oracle test file against scipy). The docs site
  already shows the filter (lanl.github.io/PyBNF, algorithm page and key
  reference). No release yet: PyPI is still 1.8.1 (August), so until Bill
  tags one the public install is `pip install "pybnf @
  git+https://github.com/lanl/PyBNF@8410f794"`. Stage 1 of the plan below
  is now triggerable; it starts when Ely says so. Three of Bill's changes
  matter for the plan: the kernel's sums are numpy reductions now, so a
  replay against the private engine matches to rounding, not byte for
  byte; the same BLAS non-determinism lives in the private engine's
  `pf.py` (a repeated run on an Intel Mac can differ in the last digit, so
  the Windows and student docs should not promise otherwise); and `lwf`
  refuses a dispersion outside 1e-6 to 1e6 (the SIHRS prior, 0.1 to 40, is
  well inside). Nothing in FluBNF or the production engine pin changes.
- 2026-10-14: the first review of lanl/PyBNF#985 arrived (Bill's reviewing
  agent, ten inline findings and one outside the diff, every one real:
  two silently accepted keys, a resampling edge, a hung cluster at
  `parallel_count = 0`, log quieting that missed child loggers, header
  collisions, and the adaptive sampler's noise trajectory sharing commit
  2's bug plus a NumPy 2 crash). All fixed in the commits that own them,
  with tests; two efficiency notes answered with measurements. The series
  was rebuilt on the same base and force-pushed as f17cfc07 (eight commits,
  authored as Ely, every gate green). Ely posts the replies. Nothing in
  FluBNF or the production engine pin changes.
- 2026-10-13 (verdict): the per-parameter kernel-jitter test is a
  pre-registered null. No arm beat production's single `pf_jitter = 0.15`
  on the Oracle SIHRS member, so the full-grid stage did not run and
  nothing changes (in-house, retrospective; five arms, three seasons, six
  states, 1,395 weeks, no failed cell). Pooled over 2023-24 and 2024-25,
  arm minus control, Oracle member / filter alone: all 0.05 -0.0002 /
  +0.064; Reff 0.3, rest 0.05 -0.004 / -0.041; Reff 0.15, rest 0.05 -0.013
  / -0.001 but central-50 coverage fell 0.033, past the 0.03 limit; mult
  and r 0.05 -0.004 / -0.014. The Oracle step absorbs most of the kernel's
  effect. Less jitter everywhere is not the lever (the filter alone loses
  0.064 and its coverage). Reff at 0.3 is the best filter alone in every
  season but splits by season on the Oracle member. Record:
  FluBNF-local/research/pf-parameter-jitter (VERDICT.md, RESULTS.md).
- 2026-10-13: the pull request is open: lanl/PyBNF#985, "feat: job_type =
  lwf, the Liu–West filter", from elyfmiller/PyBNF `pr/liu-west-filter`
  a9b1a3ae onto `main` b5fa894a, eight commits. lanl's CI is the branch's
  first Linux run: the build and changelog-fragment checks passed, the
  pytest and ruff legs were still running when this was written. Engine
  follows the review and CI; a failing leg is fixed as a fixup to the
  commit that owns it and re-gated. Nothing in FluBNF or the production
  engine pin changes; the migration starts only after merge and release.
- 2026-10-12 (later): the pull request's nine open questions are decided
  from PyBNF precedent instead of being asked. Three changed code: a run the
  wall-time budget stops now writes its forecast from the last assimilated
  row (ADR-0093), a fixed dispersion (`fix_at`) is accepted beside a fitted
  one, and a global key the filter does not read is warned about and
  ignored (ADR-0014) rather than refused; only `refine`, `bootstrap` and the
  cluster keys stay refused. The segment integrator also quiets bngsim's
  per-run log lines while it integrates. New tip a9b1a3ae on elyfmiller/
  PyBNF, every gate green; Ely opens the pull request. Nothing in FluBNF or
  the production engine pin changes.
- 2026-10-12: the PyBNF pull-request branch is rebased onto current
  lanl/PyBNF `main` (b5fa894a) and reviewed once more as a maintainer
  would: minimal, code plus tests plus user docs, no extra notes files.
  Forty-three findings, a third applied (121 lines fewer, one docs claim
  corrected, shared tails used instead of copies, a test helper module
  renamed, one redundant test cut). Every gate is green on the new tip
  bb29de26, pushed to elyfmiller/PyBNF; Ely opens the pull request. Nothing
  in FluBNF or the production engine pin changes.
- 2026-10-05, answering Submission (the 2026-10-10 round): Engine merges
  nothing into `main` and changes nothing the run reads until the hub pull
  request for 2026-10-10 is open. The pin checks out everywhere the run can
  draw it from:
  - `main` 663b5a2 pins 2fdadee0 on `feature/particle-filter`
    (`app/core/engine_build.py`), and its updater moves by fast-forward to
    exactly that commit.
  - The branch a laptop installs or updates from,
    elyfmiller/PyBNF-Private `feature/particle-filter`, is at 2fdadee0.
  - bngsim stays pinned at 0.15.1.
  - Lab Mac fallback: `~/GitHub/PyBNF-pf` is at 2fdadee0 with a clean tree,
    and its engine venv ran 144 production cells without a failure on
    2026-10-03.
- Lab Mac on Wednesday: no engine job is running or scheduled. Engine will
  start nothing on it all Wednesday, and nothing until the hub pull request
  is open.
- The PyBNF pull-request work (`pr/liu-west-filter` on elyfmiller/PyBNF)
  touches neither FluBNF nor the production pin.
- 2026-10-03 (overnight): measured whether upstream `lwf` reproduces
  FluBNF production forecasts. Fed production's random numbers, it gives
  identical forecast draws on 144 of 144 SIHRS cells from the console's own
  prepare(). With its own random numbers its total WIS is 1.0013 of
  production's (95% 0.986 to 1.016) on the six-state panel, three seasons,
  inside production's own seed-to-seed spread; a missing week and a trimmed
  week also show no difference. lwf is about 2.1x slower per cell. Nothing
  in production changes: FluBNF stays on the private engine until a
  deliberate migration (checklist in FluBNF-local, lwf-production-equivalence
  SUMMARY.md). The lab Mac's CPU is free again.
- 2026-10-01 (night): the PyBNF pull request branch on Ely's fork is now
  `pr/liu-west-filter` at 28c067f7 (force-pushed over ad671377; still 8
  commits on lanl/PyBNF `main` 0cb92a7f, about 6,000 lines). Ely opens the
  pull request against lanl/PyBNF `main`; its text is ready. A pass against
  PyBNF's design records and conventions, after the bug pass, changed two
  things in code: the state file's fingerprint also records bngsim's build
  commit, so a continuation under another build is refused; and the default
  worker count for Independent Runs is the smaller of the run count and the
  CPUs the job holds. The rest is docstrings, docs sentences, four tests
  and two more open questions in the pull request text. Local gates on
  28c067f7: the Python 3.12, 3.13 and bngsim-less 3.14 suites clean with no
  failures, bngsim 0.15.1 on every touched test file, docs build, ruff,
  changelog, every commit's own tests, and byte-identity with the previous
  tip except the new fingerprint key. No engine job is using the lab Mac's
  CPU. If you need the machine, say so here (`Engine:` in your notes).
- 2026-09-30: porting the Liu–West filter to public lanl/PyBNF as
  `job_type = lwf` ("Liu–West Particle Filter", family `filter`, settings
  `lwf_*`). Branch `feat/particle-filter` of Ely's fork elyfmiller/PyBNF,
  from lanl/PyBNF `main` 0cb92a7f; local, not pushed, no pull request yet.
  - Done locally: the segment integrator that the filter and IBIS
    (lanl/PyBNF#973) share, reviewed and fixed (five commits, head
    235fb497). The review found and fixed a silent bug: a particle's
    starting state could keep the first particle's values.
  - Done locally and independently reviewed: the `lwf` job type for one or
    several runs, with a state file and continuation (`lwf_state_file`,
    `lwf_continue`). A continuation gives exactly the same result as one
    uninterrupted run, and a revised earlier row is refused. Head 7eca7270.
  - Equivalence (2026-09-30): `lwf` and the private engine agree within
    Monte Carlo error on a test SIR model. Given the same random numbers
    they give the same output to solver tolerance. `lwf` is about 1.9 times
    slower per particle-row.
  - Done locally and reviewed (2026-10-01): the docs (algorithm section,
    citations) and a tutorial lesson tested in CI. Head 381bba5e, 63
    commits. Next: tidy the series and draft the pull request; Ely opens it.
  - Done (2026-10-01): a pre-registered synthetic study of whether the
    Liu–West filter follows a change in transmission partway through a
    series, with an independent re-analysis and a skeptic. Record:
    FluBNF-local `research/lwf-change-tracking/RESULTS.md`. Summary under
    For other lanes. Branch head a1bc35bb; Ely decides the pull request's
    framing.
- 2026-09-30: private branch `pf/forecast-fixes-noauto` (faccccb3, local,
  not pushed) adds three things:
  - per-parameter jitter (`pf_parameter_jitter = <name> <h>`);
  - parameters that only set the initial state are never moved;
  - a run-log line saying the output is a forecasting sample.

  It was checked on the real SIHRS model and is not in production. All
  three carry into `lwf`.

## Decided

- 2026-10-15 (Ely, on the public-PyBNF plan v2): all seven as recommended.
  (1) Switch to public PyBNF as soon as stage 2 passes, on a Thursday, the
  private engine kept as fallback for two rounds; (2) a degenerate `lwf`
  cell is a failed cell, as today; (3) the private engine stays a
  research-only engine on the lab Mac, nothing ported unless a result wins
  a gate; (4) the console keeps its `pf.*` knob and ledger names, mapped in
  the conf writer; (5) bngsim stays 0.15.1; (6) the pin is the merge commit
  8410f794 for stages 1 and 2, the release version at cutover if Bill has
  tagged one, else the commit; (7) stage 2's shadow Wednesday: public run
  on the lab Mac as a Thursday replay of the same vintage, private run on
  Ely's laptop as every round. Stage 1's engine part starts 2026-10-15.
- 2026-09-30 (answering Submission's note of 2026-09-30): from the first
  round (2026-10-07), engine test runs stay off the lab Mac on submission
  Wednesdays, from the target-data update until the hub pull request is
  open (8 PM Arizona time; 9 PM from 2026-11-04 to 2027-03-10).
- 2026-09-30: production stays on `feature/particle-filter` 2fdadee0 with
  its `pf_*` keys through the first rounds. The engine lane changes nothing
  production uses before 2026-10-07. A move of the pin
  (`app/core/engine_build.py`, the app lane's file) is requested here, never
  made directly.
- 2026-09-30: rename nothing in FluBNF from `pf_*` to `lwf_*` until Ely
  starts the migration.
- 2026-09-30: say "Liu–West filter", and "forecasting sample" for its
  output, never "posterior". Once IBIS exists, never say "particle filter"
  unqualified.
- 2026-09-30: upstream `lwf` uses PyBNF's own machinery:
  - edition-2 confs;
  - the `noise_model` negative binomial on a `cumulative` observable;
  - PyBNF's `random_seed`;
  - `wall_time_fit`, supported and off by default.
- 2026-09-30: IBIS is built after `lwf` is finalized, by another agent.
- 2026-09-30: choosing the jitter automatically by one-week-ahead score was
  tested and rejected. On six states the Liu–West filter member scored
  relWIS 0.814, against 0.773 for a fixed 0.15, with narrower bands and
  worse scores at the hard phases. Do not propose it again.
- Production SIHRS fits five parameters (Reff, eps1, phi1, mult, r). Notes
  listing seven are stale.

## For other lanes

- App (2026-10-29, late, what `engine-public` changed in shared files, so
  the student workspace can merge around it): `pf.py`: the engine checks
  (`engine_available`, `engine_current`, the two messages), `runner_cmd`,
  `execute`, `collect` (now pooling through `_pool`), `cell_seconds`,
  `_signal_tree`. `retro.py`: `_launch_runners`, `_run_round`'s error
  path, a new `_week_engine`. `retro_settings.engine_build_change`.
  `sandbox.py`: `machine_problems`, `_with_load_remedy`. `prepare()`,
  `run_season` and `run_week` are untouched. In your files, small
  public-engine branches: `pipeline._pf_engine_state` and
  `_harvest_params`, `versions._component_versions`,
  `templating._engine_setup_hint`, `routes/home.py`'s two tables and two
  conditions in `home.html`; and `tests/conftest.py` (new) and
  `app/tests/conftest.py` clear `FLUBNF_ENGINE` for every test. The
  `public-engine-install` job could also run
  `app/tests/test_engine_lwf.py::test_real_public_run_reproduces_the_fixture`
  with `FLUBNF_TEST_PUBLIC_PYTHON` set to its venv's Python, if you want a
  real fit in CI.

- App (2026-10-29, answering your 2026-10-26 list for `engine-public`):
  1. The lock: as above, pushed to `engine-public` at the root.
  2. The wheel's URL is
     `https://github.com/elyfmiller/flubnf/releases/download/pybnf-8410f794e3fa4817572fd07fceb043ddec39d77b/pybnf-1.8.1-py3-none-any.whl`
     (your test's form), sha256 above. It answers 404 until Ely publishes
     the release.
  3. `flubnf/settings.py`: `FLUBNF_ENGINE` (private or public, anything
     else warns and means private) and `PY_ENGINE_PUBLIC` from
     `FLUBNF_PY_ENGINE_PUBLIC`, with your two defaults. Coming on
     `engine-public`.
  4. `BNGSIM_NO_CODEGEN=1` stays on Windows runners on both routes.
  5. Doctor and the preflight import `scripts/engine_lock.py`'s `check`
     under the public venv's Python, rather than copy it.
  6. Taken: the public writer, runner and reader, the switch, provenance
     from `direct_url.json`, the doctor, reclaim, the Sandbox, tests on a
     trimmed Alaska fixture (about 130 KB, no lab paths).
  Superseded: the 2026-10-15 handoff's git install line and
  `bngsim[antimony]`; the wheel and the lock replace them.
- App (2026-10-29, your protection-audit items 1 to 3, the private
  engine's pin, update and archive check): taken, after `engine-public`'s
  stage 1 closes (Tuesday 2026-11-03). The runner cleaning and the student
  workspace items stay yours, as Ely decided.

- App (2026-10-15, stage 1 handoff, the engine lane's part is done):
  everything the `engine-public` branch needs, measured on the lab Mac.
  - **Pin.** `pip install "pybnf @ git+https://github.com/lanl/PyBNF@8410f794"
    "bngsim[antimony]==0.15.1"` into a Python 3.12 venv (the lab Mac's is
    `~/.venvs/flubnf-lwf`, Python 3.12.7). What pip installed beside it:
    numpy 2.5.4, scipy 1.18.1, dask and distributed 2026.8.0, pydantic
    2.14.1. The console's check is two lines, since `pybnf.__version__`
    reads "1.8.1" on both the merge commit and the August release:
    `importlib.metadata.distribution("pybnf").read_text("direct_url.json")`
    carries `vcs_info.commit_id` = 8410f794e3fa4817572fd07fceb043ddec39d77b,
    and `from pybnf.algorithms.filters.liu_west import LiuWestFilter` must
    succeed. After Bill tags a release, pin the version instead.
  - **Conf** (edition 2; the fixture's, paths shortened):
    `edition = 2`, `bng_command = <BNG2.pl>`, `model: m.bngl`,
    `bngl_backend = bngsim`, `output_dir = out`, `job_type = lwf`,
    `noise_model = neg_bin, dispersion = fit r__FREE, location = mean`,
    `noise_model Hobs = neg_bin, dispersion = fit r__FREE, location = mean,
    cumulative`, `experiment: <name>, data: <name>.exp`, the five prior lines
    as production writes them, `initialization = rand`, `lwf_particles`,
    `lwf_jitter`, `lwf_bounds = reflect`, `lwf_forecast_intervals`,
    `lwf_resample_threshold = 0.5`, `random_seed = pf_seed mod 2^32`.
  - **Template.** The production SIHRS model with its `begin actions` block
    removed; the fixture ran so. A `generate_network` action alone is also
    accepted (edition-2 rule) if `prepare()` keeps one for its own check.
  - **Data file.** Header `# time<TAB>Hobs`; production row at time t
    becomes lwf time t + 1 (production starts the state at t = -1, lwf at
    0; the counter species keeps the seasonal phase); one row per week from
    1 to the last, a week the console dropped written as `nan`.
  - **Outputs** under `<output_dir>/Results/LWF/`: `forecasts.txt`
    (particles by forecast intervals, header = the forecast times),
    `predicted_counts.txt` (particles by assimilated rows, header = the row
    times; the expected count, 0 where the output fell), `parameters.txt`
    (particles by free parameters, header = names), `parameters_by_row.txt`,
    `weight_ess.txt`, `summary.txt`. Every table opens with `#` note lines,
    then the header row, then whitespace-separated numbers. collect()'s
    anchoring maps directly: origin = the last column of
    `predicted_counts.txt`, horizons = the columns of `forecasts.txt`. A
    10,000-particle cell writes about 5.7 MB (4.6 MB of it predicted
    counts); reclaim should keep what it keeps today.
  - **Fixture.** FluBNF-local, research/public-port/fixture-alaska-2025-01-11:
    `private/` (the production cell's pf.conf, model, .exp, params_0.txt)
    and `public/` (the translated model, .exp, both confs, translate.json,
    and the six Results/LWF files the merge commit wrote). Not in this
    repository; Ely copies it where the App lane can read it.
  - **Equivalence, restated for the merged package** (in-house,
    retrospective): fed the production engine's random inputs, the merge
    commit reproduces production's forecast draws exactly on 144 of 144
    SIHRS cells, as the October checkout did; expected counts agree to
    1.7e-10 relative, parameters to 3.3e-8 (the October checkout gave
    1.3e-9: the kernel's numpy reductions round differently, invisible to
    any draw). With its own random streams, pooled over the six-state
    panel, total WIS lwf over production: 1.0013 (95% interval 0.986 to 1.016, permutation p 0.93), the October number: the
    merged package's own-stream forecast draws are identical to the October
    checkout's on 432 of 432 cells (its parameters differ by at most 3e-8
    relative), so the 2,100-run comparison of 2026-10-03 stands for the merged
    package as it was. No failed cell, no
    degenerate update, 144 + 432 runs.
  - **Cost.** Median 47.9 s per 10,000-particle cell at ten in parallel;
    one cell at a time on the idle machine: 38 to 47 s against production's 18 to 29 s on the same four cells, a ratio of
    1.6 to 2.1; a rerun of each cell reproduced its own-stream run byte for byte. Production's weekly
    grid of 159 cells is 5 to 14 minutes on the lab Mac, so expect roughly
    twice that, inside the one-hour floor.
  - **Tests on Apple silicon** of the merged tree: Python 3.12: 6,755 passed, 12 skipped, 6 xfailed; 3.13: 6,698 passed, 69
    skipped, 6 xfailed; 3.14 without bngsim: 5,930 passed, 841 skipped, 2 xfailed;
    no failure; ruff, the changelog check and `sphinx-build -W` green; bngsim
    0.15.1 on the 14 test files the PR touched: 681 passed. The byte-identical
    repeat, continuation and cluster tests, which failed for Bill on Intel before
    his fix, pass here on Apple silicon..
- App, Submission, Model (2026-10-15): the plan below, "FluBNF on public
  PyBNF" v2, is now live: #985 is merged (8410f794). Stage 1's engine part
  runs on Ely's go and posts the pin and a translated cell here; App's
  `engine-public` branch starts from that. It answers App's request of
  2026-09-30: Python 3.12 or newer, pip-installed engine pinned at the
  merge commit until a release, edition-2 confs, Results/LWF output names.
- App (answering your request of 2026-09-30): noted. The pin's branch and
  commit, the Python version and the output file names will be posted here
  once the upstream `lwf` pull request is merged, not before. What is known
  now:
  - Python 3.12 or newer;
  - `lwf_*` keys;
  - edition-2 confs, with `noise_model` and `random_seed` in place of
    `neg_bin_dynamic` and `pf_seed`;
  - `pf_start_time` and `pf_sampling_interval` retired, with gaps written
    as explicit NaN rows;
  - new output readers;
  - a statistical-equivalence check against the production record before
    switching, because the numbers will not be byte-identical.
- Model (2026-10-01; toy SIR, synthetic data, in-house, not peer-reviewed):
  - The Liu–West filter did not follow a drop in transmission at any jitter
    up to 0.9 (540 pre-registered runs plus 91 checks). It behaved like a
    sequential fit with nearly fixed parameters: its beta matched a plain
    constant-beta fit of the same rows.
  - The private engine, which production uses, behaved the same.
  - A change missing from the model showed up as a falling dispersion r and
    a carried susceptible pool that drifted from the truth. Forecasts stayed
    close only when the drop came at or after the peak; a drop during growth
    gave forecasts far off.
  - Raising h is not a lever: the kernel keeps the swarm's spread, so no h
    widens it.
  - Weekly refits from Aug 1 replay the same rows, so they add no
    adaptivity.
  - Cautions for SIHRS work, untested on it: do not describe the weekly
    filter as adapting to change; a falling r is a cheap alarm that the
    model is missing something.
  - In the toy, beta·S/(N·gamma) came out too low at the forecast origin
    after a slowdown, the same sign as the old "Rt < 1 at the origin"
    finding. That link is untested.
  - Nothing in production changes from this.
- All: the private engine's `pf_continue` silently ignores revised earlier
  rows. Production refits every week, so it is safe. Nothing that carries a
  swarm across weeks may rely on it; upstream `lwf` refuses a revised row.
- Model: planned, not started, after the port groundwork: per-parameter
  jitters for SIHRS against a single 0.15 on forecasts. The design is a few
  pre-registered arms, one season held out, confirmed on the full grid. It
  needs a `pf_parameter_jitter` passthrough in the conf writer, which exists
  only on a local research branch. Say here if the model lane wants to run
  it instead.
- Model: engine tests on the lab Mac are CPU-heavy (the jitter test takes
  about 81 minutes per arm). Say here if a replay needs the machine at a
  given time and the engine runs will wait.

## Plan: FluBNF on public PyBNF (v2, 2026-10-15, after the merge)

lanl/PyBNF#985 is merged: `job_type = lwf` is on public PyBNF `main` as merge
commit 8410f794 (26 commits), the docs site shows it, and there is no release
yet (PyPI 1.8.1, August). `pybnf.__version__` is the static string "1.8.1" on
both, so a version check cannot tell the merge commit from the old release;
until a release exists the console probes the import and reads the commit pip
records (`direct_url.json`). This plan replaces the 2026-10-13 draft.

Goal: FluBNF stops needing the private fork (PyBNF-Private
`feature/particle-filter` 2fdadee0, the PyBNF-pf checkout, the engine
archives and bundles, the collaborator invitations) on every route: the
weekly forecast run, retro replays, the sandbox, custom datasets, the
installers (macOS, Windows, students), the doctor, the docs, the tests. The
2026-27 rounds stay on the private engine until stage 2 passes; nothing in
production changes before Ely's cutover decision.

### The pin

- Now: `pip install "pybnf @ git+https://github.com/lanl/PyBNF@8410f794"
  "bngsim[antimony]==0.15.1"` into a Python 3.12 venv (public PyBNF requires
  3.12 or newer, dask and distributed 2024.1 or newer, pydantic 2; numpy 2 is
  fine). Provenance: the commit in the installed distribution's
  `direct_url.json`. Preflight: `from pybnf.algorithms.filters.liu_west import
  LiuWestFilter` succeeds and the recorded commit is the pin.
- After Bill releases (1.9.0?): `pip install "pybnf==<v>" ...`; preflight:
  `pybnf.__version__` at or above it. Ely asks Bill when.
- bngsim stays 0.15.1 (decision 5).

### What changes

| | today (private fork) | after (public PyBNF) |
|---|---|---|
| engine | PyBNF-Private `feature/particle-filter`, pinned by commit (2fdadee0) in app/core/engine_build.py | `pybnf` installed by pip, pinned by commit (now) or version (after a release) |
| how lab users get it | a 130 KB archive or a 140 MB bundle in Downloads, or a collaborator invitation; setup_engine.sh / setup.ps1 find it, unpack it and `pip install -e` | one pip line into a Python 3.12 venv; no login, no file to hand out, no stale-engine failure mode |
| engine venv | Python 3.11 or 3.12, numpy<2, dask 2022.12.1, bngsim 0.15.1 | Python >= 3.12, numpy >= 1.24, dask and distributed >= 2024.1, pydantic 2, bngsim 0.15.1 |
| conf | edition 1: `fit_type = pf`, `objfunc = neg_bin_dynamic`, `pf_*` keys, `pf_seed`, `pf_start_time = -1`, `pf_cumulative_observable = Hobs` | edition 2: `model:`, `experiment:`, two `noise_model` lines (neg_bin, dispersion = fit r, location = mean, cumulative, on Hobs), `job_type = lwf`, `lwf_*` keys, `random_seed` |
| model template | SIHRS_pop_min.bngl with its `simulate` action | the same model with no action but `generate_network` |
| data file | counts from t = -1 | times one week later (t = 0 is the start; the counter species keeps the phase), column `Hobs`, a `nan` row per missing week |
| runner | `from pybnf.pf import ParticleFilter`, the fork first on sys.path | `from pybnf.algorithms.filters.liu_west import LiuWestFilter; LiuWestFilter(load_config(conf)).run(None)`, nothing on sys.path (a private checkout left there shadows the package) |
| outputs the console reads | out/Results/PF/Runs/*traj_noise*, ess_0.txt, params_0.txt, pf_state.npz | Results/LWF/forecasts.txt, predicted_counts.txt (the clamped mean, 0 where the output fell), parameters.txt, weight_ess.txt; the state file `lwf_state_file` names (format 2) |
| preflight | pybnf/pf.py exists; parse.py grepped for keys | an import probe plus the recorded commit or version; one error wording |
| provenance | fork branch, commit and VERSION stamp | the pip-recorded commit, then the version string; a release is a reproducible build |
| random streams | `pf_seed`, per-week streams | `random_seed`, keyed streams; stored records cannot be regenerated bit for bit across the switch |
| arithmetic | BLAS products (`weights @ x`); a repeated run on an Intel Mac can differ in the last digit | numpy reductions; byte-identical repeats on every BLAS; a replay against the private engine matches to rounding, not byte for byte |
| degenerate update | keeps the prior weights and still forecasts | stops with an error naming the row; outputs through the last assimilated row, no forecast (decision 2) |
| revised earlier rows on a continuation | silently ignored | refused; production refits every week, so nothing depends on it |
| dispersion | any `r` | fixed between 1e-6 and 1e6, a fitted prior within it; the SIHRS prior (0.1 to 40) is well inside |
| cost | about 5 to 14 min per 159-cell weekly grid on the lab Mac | roughly twice that, inside the console's one-hour floor; the cost model needs refitting |
| research paths with no `lwf` equivalent | two-strain binomial channel, reporting-model modes, pf_shrink, pf_forecast_jitter, continuing private clouds | not available; all off in production (decision 3) |
| per-parameter jitter | not in 2fdadee0 | `lwf_parameter_jitter`; the 2026-10-13 test says keep one scale |

### Where the private engine is wired in (flubnf `main`, 38 files)

- Launchers and installers: FluBNF.command, FluBNF.bat, SetupEngine.command,
  install.sh, reinstall.sh, setup.sh, setup.ps1, setup_engine.sh,
  scripts/macos/move_home.sh, scripts/cut_engine_archive.sh (retire),
  scripts/README.md.
- Code: flubnf/settings.py (PYBNF, PY_ENGINE), flubnf/doctor.py,
  app/core/engine_build.py (the pin), app/core/engines/pf.py (writer, runner
  template, collect, preflight), app/core/retro.py.
- Docs: README.md, docs/ENGINE.md, docs/INSTALL-STUDENTS.md,
  docs/LAUNCHERS.md, docs/ORACLE-SIHRS.md ("Engine line-up"), docs/WINDOWS.md.
- Tests: app/tests/conftest.py, test_engine_build.py, test_engine_contract.py,
  test_engine_preflight.py, test_engine_sampling_interval.py,
  test_pf_hardening.py, test_pf_shards.py, test_report_season.py,
  test_retro_fit_level.py, test_sandbox_guard.py; tests/test_doctor_engine_hub.py,
  test_engine_bundle.py, test_mac_app_bundle.py, test_reinstall_script.py,
  test_windows_controlled_folder_access.py.

### Stage 1, now: the contract and the opt-in branch

Engine, lab Mac, on Ely's go (about a day):
1. `~/.venvs/flubnf-lwf`: Python 3.12, the pin above. Record the commit pip
   stores and the dependency versions.
2. Rerun the equivalence replay (144 SIHRS cells, lab tree
   research/lwf-production-equivalence) against the private engine 2fdadee0 on
   that venv. Expected: forecasts equal to rounding (the kernel's sums are
   numpy reductions now), expected counts within about 1e-9 relative. Record
   the largest difference; the "identical draws" claim of 2026-10-03 is
   restated accordingly.
3. Post here, for the App lane: the pin and how to check it, the dependency
   set, the exact conf and data translation, the output names, and one
   production cell translated by hand (Alaska 2025-01-11: conf, .exp,
   template, outputs) as the fixture.

Done 2026-10-15 (engine, steps 1 to 3): the venv on the pin, the replay and
own-streams reruns on the merged package, the fixture cell, the handoff above.

App, branch `engine-public` on `dev`, opt-in until stage 3 (about a week):
4. flubnf/settings.py: `FLUBNF_ENGINE = private | public` (default private);
   `PY_ENGINE` for the public venv; `FLUBNF_PYBNF` private only.
5. app/core/engines/pf.py: a second writer, runner and reader behind the
   switch: the edition-2 conf, the template without actions, write_exp with
   the one-week shift, `Hobs` and `nan` rows, the LiuWestFilter runner,
   collect() from Results/LWF, the import-probe preflight with the commit or
   version check; engine_build.py's pin becomes the public pin; doctor and
   reclaim follow.
6. knobs.py and the ledger keep the console's `pf.*` names and map them in the
   writer (decision 4).
7. Sandbox and custom datasets write the public conf under the switch.
8. Tests on the engine lane's fixture; CI has no engine, as today.
9. setup_engine.sh, setup.ps1, install.sh, reinstall.sh: a public route (venv
   plus pip) beside the private one; docs ENGINE.md, INSTALL-STUDENTS.md,
   WINDOWS.md, LAUNCHERS.md, README. Nothing reaches a student until `main`.

Model and Submission: nothing runs on the public engine yet.

### Stage 2, acceptance (after `engine-public` runs one week end to end on the lab Mac; one to two weeks, Wednesdays excluded)

- Engine and Model: the full grid through the console's public path, three
  seasons, both members, against the private engine's own rerun on identical
  cells (not the stored reseal). Gate, pre-registered before the run; starting
  values: total WIS ratio public over private within 0.98 to 1.02 per season
  and pooled, 50% and 95% coverage within 0.02, no failed cell the private run
  did not have, no degenerate update; plus the replay to rounding on 36 cells.
- App: Windows (one state, one week) and the installer from scratch on a clean
  user, then Ely's laptop.
- Submission: one shadow Wednesday: both engines run, the private file is
  submitted, the public file is diffed and kept (decision 7: on which machine).
- Engine: the cost model refitted; the time budget checked on the slowest lab
  machine.

### Stage 3, cutover (Ely's decision after stage 2; a Thursday, never the days before a due date)

- App: `FLUBNF_ENGINE` defaults to public; the pin is the public one; the setup
  scripts default to the public route; the private route stays one release as
  "legacy"; docs/MODEL-PROVENANCE.md records the last private-engine round and
  the first public one.
- Submission: the next round runs public with the private engine still
  installed as the fallback for two rounds; the method card needs no change
  unless it names the build.
- Model: research replays move or stay private per decision 3.

### Stage 4, retiring the private repository (after two clean public rounds)

- The private route and `scripts/cut_engine_archive.sh` go; no more archives
  or bundles; the collaborator invitations stop.
- PyBNF-Private is archived read-only on GitHub; the lab Mac keeps one checkout
  of 2fdadee0 for reproducing sealed numbers and, under decision 3, for
  research paths; docs/ENGINE.md and the engine-provenance notes say so.
- flubnf's docs name one engine: public PyBNF at a version.

### Decisions for Ely, with a recommendation each

1. Timing. Recommend: switch as soon as stage 2 passes, on a Thursday, with the
   private engine kept as fallback for two rounds; realistic earliest
   mid-November. Waiting for the end of May is the conservative alternative
   and means two engines in parallel all season.
2. Degenerate row. Recommend: treat a degenerate cell as a failed cell, as
   today (the week is stored from the surviving replicates and logged); no
   code. Not seen once in 2,100 runs.
3. Research paths. Recommend: keep the private engine as a research-only
   engine on the lab Mac; port two-strain or the reporting model to `lwf` only
   if a research result wins a gate.
4. Console names. Recommend: keep `pf.*` knob and ledger names, map them in
   the writer; stored records stay readable and the rule "rename nothing to
   lwf_* yet" stays.
5. bngsim. Recommend: 0.15.1 now (bit-identical to every production
   integration); 0.16 or later only after a measured check.
6. Pin. Recommend: pin the merge commit 8410f794 for stages 1 and 2; cut over
   on the release version if Bill has tagged one by then, else on the commit.
7. Machines for stage 2's shadow Wednesday. Recommend: the public run on the
   lab Mac (Thursday replay of the same vintage), the private run on Ely's
   laptop as every round; the files diffed after.

## Open

