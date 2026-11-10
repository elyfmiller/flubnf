# Engine lane notes

The private PyBNF fork, the Liu-West filter, and its port to public PyBNF.
Works on Ely's Windows PC since 2026-11-09 (the lab Mac before), in
repositories outside this one; it pushes only this file here.

## Now

- 2026-11-10 (evening): Ely's old private checkout is renamed, on Ely's
  yes: `Documents\GitHub\PyBNF-pf` is now `Documents\GitHub\PyBNF-pf-old`.
  It is still at eab31c71 with a clean tree; nothing had it open, and
  nothing was deleted. To undo, rename it back.
  - `flubnf.settings.PYBNF` now gives `%LOCALAPPDATA%\FluBNF\PyBNF-pf`
    (2fdadee0) in all three cases checked: a shell opened before
    2026-11-09's install, whose `FLUBNF_PYBNF` still names the old path
    (the pin is passed over, since no engine is there); no variable; and
    the account's value. FluBNF.bat's probe follows the same order.
  - So the trap in the gate entry below is closed for the engine: such a
    shell now finds the production build, not eab31c71.
  - It is not closed for the hub. `Documents\GitHub\FluSight-forecast-hub`
    (e311e57, target data of 2026-08-25) stays. A shell carrying the old
    `FLUBNF_HUB` still reads it, and so would a shell with no `FLUBNF_HUB`,
    since on Windows an existing Documents checkout is the default.

- 2026-11-10 (afternoon): **THE 11-07 GATE (version 2, approved): PASS.**
  All seven criteria hold on the first runs, so retry rule (b) was not
  needed. The verdict decides only whether the 11-11 round runs on the
  public engine; stage 2 still runs.
  - **The runs.** Each ran on a console at 127.0.0.1:8790, from the
    fresh clone at 26acbadf, through the Forecast page's POST `/run`
    with the round's settings. All 159 cells were "ok" in each run, with
    no preparation failure.
    - P1, private: 13:30:55 to 13:37:34 (399 s).
    - P2, private, seed date `2026-10-31#gate-2026-11-10-p2`: 369 s.
    - L1, public: 820 s, the same `pf_seed`s as P1. That is 2.14 times
      the private runs' mean, against `PUBLIC_COST_RATIO` 2.4.
    - Builds, from each run's `component_versions.json`: P1 and P2 ran
      the private engine at 2fdadee0. L1 ran the public engine at
      8410f794, wheel sha256 18a59bc2..., as the lock says.
    - The timings carry some load. Model ran single-core jobs at
      below-normal priority meanwhile: its test suite for 13 minutes,
      then the Groundhog for 17 (model.md, 0e3c2eb4).
    - A trap Model found, which this lane's shell has too: a shell
      opened before 2026-11-09's install still carries the old
      `Documents\GitHub` values of `FLUBNF_HUB` and `FLUBNF_PYBNF`. Under
      private, those name the eab31c71 fork, and doctor fails on it. The
      gate's driver set both to the `%LOCALAPPDATA%` paths itself. A new
      window reads the account's values.
  - **Reproduction.** P1 reproduces the submitted file exactly: 0 of its
    4,692 values differ over its 51 locations. So R is P0, and this PC's
    private engine gives the laptop's numbers to the count.
  - **The measures, L1 against R, with P2 against R (the noise floor)
    after each:**
    - D_mean: 0.0222 against 0.0194 (1.15x).
    - D_90: 0.0397 against 0.0368 (1.08x).
    - C50: 1.00 against 1.00.
    - W95: 1.000 against 1.000.
    - B: +0.0025 against +0.0001.
    - S: +0.0005 against +0.0025.
    - No zero-width blocks in R or in either run.
  - **The criteria:**
    1. L1 has no failed cell. A degenerate update fails a public cell,
       so it had none.
    2. Passed on the ratios, not the floors, so no note.
    3. C50: passed.
    4. W95: passed.
    5. The largest d(L1) in each third against its cap (3 times the
       third's largest d(P2)): 0.248 against 0.449 (Alaska h3, the
       low-count third), 0.066 against 0.158, and 0.051 against 0.111.
    6. B passed on its 0.01 floor, not on 3 x |B(P2)| (0.0004). The
       public medians sit 0.25% higher on average, while the reseeded
       private ones sit 0.01% higher. This is reported, though the gate
       defines no note for B.
    7. S: passed.
  - **Read with them:**
    - C50 and W95 cannot separate the runs this week. Every median sits
      inside R's 50% interval in both runs. The 10x tail cap pins the
      97.5% quantile in about a third of the blocks, so 37 (P2) and 43
      (L1) of the 204 blocks have exactly R's 95% width, and the median
      ratio lands on 1. B, S and D carry the comparison.
    - The 95% width ratios range from 0.938 to 1.151 for P2 and from
      0.902 to 1.210 for L1. The per-block median shifts have a
      standard deviation of 0.027 (P2) and 0.035 (L1).
    - Alaska is the largest d in both runs: 0.150 at h2 for P2, and
      0.248 at h3 for L1.
  - **Not gated, against P1:**
    - Delaware: L1's medians are 77/108/156/222 against 77/109/156/225,
      with d 0.004 to 0.019.
    - Hawaii: L1's are 44/46/50/53 against 44/47/51/57, with d up to
      0.088 at h3, and P2's is 0.087 there.
  - **Kept:** the runs' state folders, P0's copy (sha256 9402fb92...) and
    `gate-measures.json` are in `%USERPROFILE%\flubnf-gate-2026-11-10`,
    with the three scripts that ran and measured the gate in `scripts\`
    there.

- 2026-11-10 (afternoon): the public engine from a fresh clone of `dev`,
  as a stranger would, on Ely's Windows PC. Task 2 is done:
  - `git clone -b dev` (26acbadf) to `%USERPROFILE%\GitHub\flubnf-stranger`,
    then its `FluBNF.bat` with `FLUBNF_SHORTCUTS=off`. It took under four
    minutes, from the clone at 13:03:08 to the console's start. The
    console's `.venv` came first. Then the public engine went into
    `%LOCALAPPDATA%\FluBNF\venv-public` on `py -3.12` (3.12.10), and the
    window ended "public engine ready: pybnf 1.8.1 from
    pybnf-1.8.1-py3-none-any.whl, bngsim 0.15.1", word for word as in
    WINDOWS.md. The launcher set `FLUBNF_PY_ENGINE_PUBLIC` as a User
    variable. The console it started was stopped.
  - Reused, so a real stranger waits longer:
    - Python 3.12.10, Git, and Strawberry Perl;
    - the hub clone (`FLUBNF_HUB`);
    - the private checkout at its pin (`FLUBNF_PYBNF`);
    - pip's cache, for 25 of the 39 packages (14 were downloaded, among
      them the PyBNF wheel, scipy, libroadrunner and cryptography).
    The clone went outside `%LOCALAPPDATA%\FluBNF\flubnf`, where
    WINDOWS.md puts it, because Ely's old install is there.
  - `scripts/engine_lock.py check` under the venv: "public engine
    ready", exit 0.
  - `flubnf doctor` in the fresh clone: 15 ok, 0 warn, 0 fail; "PyBNF
    engine build 8410f794 (lanl/PyBNF, bngsim 0.15.1), the pinned public
    build". Ely's laptop showed the same count.
  - `test_engine_lwf.py::test_real_public_run_reproduces_the_fixture`,
    with Strawberry Perl on PATH and `FLUBNF_TEST_PUBLIC_PYTHON` set:
    passed in 69 s.
  - No docs defect found. The only noise is setuptools' license
    warnings (For other lanes, 2026-11-09). Still to do: tasks 3 and 4,
    meaning one cell through the console's public path, the Sandbox
    examples, and switching this lane's clone between the engines.

- 2026-11-10: THE GATE FOR THE 2026-11-07 ROUND ON THE PUBLIC ENGINE,
  written before any of its runs. Version 1 is fe5861c8. **Version 2,
  below (16571001, the reviewer's changes), is APPROVED.** Ely's answer,
  relayed by App: "Yes, with changes", taking retry rule (b). Nothing
  below changes from here on. The runs start after this entry is pushed,
  in order P1, P2, L1:
  - each one at a time, on a console of its own at 127.0.0.1:8790
    (uvicorn serving `app.ui.server:app`, as `flubnf app` does, with no
    browser);
  - from the fresh clone `flubnf-stranger`, with state folders under
    `%USERPROFILE%\flubnf-gate-2026-11-10`;
  - each started by the Forecast page's own POST `/run`: 2026-10-31, all
    53 locations, both models, 3 replicates of 10,000 particles, the five
    values, and the override with its reason;
  - P2's salt, `gate-2026-11-10-p2`, is added to `spec.extra` by a
    wrapper around `pipeline._run_all` and nothing else.
  - **Scope.** The gate decides only whether the 11-11 round runs on the
    public engine. The 11-18 side-by-side and the remade replays remain
    the engine comparison of record.
  - **What is compared.** The submitted
    `2026-11-07-NAU_PyBNF-OracleSIHRS.csv` (P0): Ely's run on the laptop,
    app build 9d4520d, the private engine, data through 2026-10-31, and
    the round's five override values:
    - `pf.seed_denominator` season_total_early;
    - `oracle.w` 0.25;
    - `oracle.narrow` 0.7;
    - `output.tail_cap` 10;
    - `output.tail_mode` shrink.
    Its 51 locations (Delaware and Hawaii were dropped by Ely) times
    horizons 0 to 3 make 204 blocks of 23 quantiles.
  - **Three runs on this PC**, each with the same five values, through the
    console's run path. Each runs on a console of its own at port 8790,
    with a temporary state folder:
    - **P1, the private engine, the round's own seeds.** This is the
      reproduction check. The hub's data is still through 2026-10-31,
      and the console's reference date is the as-of date plus 7, so a
      run today is the 11-07 round. If the hub moves first, the runs use
      a copy pinned at that week.
    - **P2, the private engine, a salted seed** (the seed-spread hook
      `seed_salt` in `pf.py`'s `seed_date_for`, set from a script,
      since the page has no seed setting). This is the noise floor: the
      same run with independent draws.
    - **L1, the public engine.** The same `pf_seed`s, but a different
      engine's stream, so its draws are independent too.
    Each run is 159 cells (53 locations, 3 replicates of 10,000
    particles). By the lab Mac's costs and the 2.1x public ratio, the
    three should take under an hour and a half together. Model is told
    before they start.
  - **The reference R.** R is P0 if P1 reproduces it, which means every
    value within one count of the file's whole numbers. Otherwise R is
    P1, and P1 against P0 is reported as this PC's difference from the
    laptop.
  - **The measures** are computed for a run A against R over the 204
    blocks, on log(1 + value):
    - d, per block: the mean over the 23 levels of
      |log(1 + qA) - log(1 + qR)|;
    - D_mean and D_90: the mean and the 90th percentile of d over the
      blocks;
    - C50: the share of blocks with A's median inside R's 50% interval;
    - W95: the median over blocks of A's 95% width over R's, on counts.
    - Two signed measures, new in version 2 (over the 51 locations, with
      the horizons averaged within a location first):
      - B: the mean of log(1 + median A) - log(1 + median R);
      - S: the mean log of the 95% width ratio A over R.
    - A block whose 95% width in R is zero is dropped from W95 and S,
      and the count is reported. d, C50 and B keep it.
    The noise floor is P2's values of the same measures.
  - **PASS when all seven hold:**
    1. L1 has no failed cell and no degenerate update that P1 or P2 does
       not also have.
    2. D_mean(L1) is at most 1.25 x D_mean(P2), or at most 0.02 (2%).
       D_90(L1) is at most 1.5 x D_90(P2), or at most 0.05. Where a floor
       is what passed and the ratio is over 1.25 (D_mean) or 1.5 (D_90),
       the verdict is PASS WITH A NOTE: a measured engine difference,
       too small to matter this round.
    3. C50(L1) is at least C50(P2) - 0.05.
    4. W95(L1) is between 0.95 and 1.05 times W95(P2) (version 1 had
       0.90 to 1.11).
    5. Within each third of the 51 locations ranked by R's median (the
       mean over the four horizons; 17 locations each), no block has
       d(L1) above 3 times the largest d(P2) in that third. States with
       counts near 0 to 5 have by far the largest d from draws alone.
    6. |B(L1)| is at most max(0.01, 3 x |B(P2)|).
    7. |S(L1)| is at most max(0.03, 3 x |S(P2)|).
  - **A miss from bad luck.** By the reviewer's estimate, with one
    salted run noise alone misses one of version 1's five tests about 1
    time in 8, and seven tests miss more often. Ely chooses between:
    - **(b), recommended.** A first miss on criteria 2 to 7 brings one
      more salted private run (P3) and one public run with a new salt
      (L2), about 45 minutes. L2 is judged against R, with the floor
      pooled from P2 and P3: the mean of each measure, and per block the
      larger of the two for criterion 5. Only a miss by L2 is FAIL. This
      costs nothing unless there is a miss. A miss on criterion 1 is
      FAIL at once.
    - **(a).** Two more salted private runs from the start (about half
      an hour each), with the floor as the mean of the three, and per
      block the largest of the three.
  - **FAIL when a criterion is missed**, after the retry if Ely chose
    (b). Every measure is reported either way, with the blocks behind
    each miss, and Delaware and Hawaii are reported without being gated.
    A fail means falling back to `FLUBNF_ENGINE=private` for 11-11, which
    is Ely's call with Submission. A pass leaves the 11-11 round on the
    public engine, as decided. Either way stage 2 still runs.
  - Not before Ely's yes. The runs must end before 11-11's target-data
    update, or use the pinned copy.

- 2026-11-09 (later): the private engine, the fallback, is installed on
  Ely's Windows PC, from `dev` (before App's merge), by this lane's
  clone's FluBNF.bat (first open, `FLUBNF_SHORTCUTS=off`) in about five
  minutes:
  - Engine checkout `%LOCALAPPDATA%\FluBNF\PyBNF-pf`, a clone of
    PyBNF-Private `feature/particle-filter` with Ely's login; its HEAD is
    2fdadee0 and nothing newer is on the branch.
  - Engine venv `%USERPROFILE%\.venvs\flubnf-engine`, Python 3.12.10:
    bngsim 0.15.1, numpy 1.26.4, dask and distributed 2022.12.1,
    libroadrunner 2.7.0. The console's `.venv` is 3.12.10 too.
  - The hub, sparse-cloned by `setup.ps1` to
    `%LOCALAPPDATA%\FluBNF\FluSight-forecast-hub`; Perl is the machine's
    Strawberry 5.42.2. User variables now name these (`FLUBNF_HUB`,
    `FLUBNF_PYBNF`, `FLUBNF_PY_ENGINE`; no `FLUBNF_ENGINE`).
  - `flubnf doctor`: 14 ok, 0 warn, 0 fail; "PyBNF engine build 2fdadee0
    (feature/particle-filter), the production build".
  - Ely's old install, which Ely let this lane replace: its engine venv
    is renamed `flubnf-engine.before-2026-11-09`; its
    `Documents\GitHub\PyBNF-pf` (eab31c71) and hub clone stay where they
    are. That checkout is second in the engine search order, so it wins
    again if `FLUBNF_PYBNF` is ever cleared; renaming it takes it out.
  - Not done yet: switching to public and back, and the same cell on both
    engines. Both wait for App's merge, which puts the public route on
    `dev`.

- 2026-11-09 (night): the lane moved to Ely's Windows PC, since the lab
  needs the lab Mac back (submission.md Open, 2026-11-04). It starts
  fresh: no earlier session's memory or scratchpads, none of the lab
  Mac's local folders. The Model lane starts here too and shares the CPU.
  - The machine: Windows 11 Pro (build 26200), Intel i7-12700KF (12
    cores, 20 threads), 32 GB, an RTX 4070 Ti that nothing here uses,
    282 GB free on C: and 747 GB on D:. Controlled Folder Access is on;
    long paths are off. Numbers this lane posts from here name this
    machine and say that bngsim's code generation is off
    (`BNGSIM_NO_CODEGEN=1`, as the console sets it on Windows).
  - Set up tonight: this lane's clone, `%USERPROFILE%\GitHub\flubnf` on
    `dev` (identity Ely's); python.org Python 3.12.10 x64 for this
    account only, not on PATH (`py -3.12`); GitHub CLI 2.103.3, logged in
    as elyfmiller by Ely through the browser. That is an OAuth token with
    `repo`, `workflow`, `read:org` and `gist`, not the lab Mac's
    fine-grained one: it reaches cdcepi and lanl, so the outward-facing
    rule is the only guard. Already
    here: Git 2.45.2, Python 3.11.9, Strawberry Perl 5.42.2 machine-wide
    (`C:\Strawberry`, so FluBNF.bat will not install its own), and an old
    FluBNF install of Ely's (`%LOCALAPPDATA%\FluBNF\flubnf`, `main`
    2eaada8 of 2026-09-01; its private engine `Documents\GitHub\PyBNF-pf`
    is at eab31c71 of 2026-08-20, not the pin 2fdadee0), which Ely says
    this lane may replace.
  - The wheel is published (release
    `pybnf-8410f794e3fa4817572fd07fceb043ddec39d77b`, asset
    `pybnf-1.8.1-py3-none-any.whl`); GitHub's digest for the asset equals
    the sha256 recorded on 2026-10-29 below, so the lock's wheel line
    installs.
  - pybnf 1.8.2 is on PyPI (2026-11-04; lanl tag v1.8.2, 3c3185c5, 46
    commits past 8410f794: noise-model, gradient, bngsim output-grid and
    petab fixes). It needs bngsim 0.17.0 or newer. Ely keeps 8410f794
    with bngsim 0.15.1 for now (Decided); this lane measures 1.8.2 with
    bngsim 0.17 against it here first.
  - Next, in order: the public venv from the lock as a stranger would,
    from a fresh clone once App's merge is on `dev`; one forecast cell
    through the console's public path; the private engine as the
    fallback, both engines on the same cell; then stage 2 and the cost
    model here, after Ely's answers under Open.

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
  - Still open (the wheel release is published, 2026-11-09): a public
    venv built from the lock as a stranger would, and a forecast run
    through the console end to end; both now on Ely's Windows PC.

- 2026-10-29 (Ely's go on plan v3 and the wheel release): stage 1's
  engine side, on `engine-public`. (That day's in-flight list is closed:
  this lane has nothing in flight in those files; see For other lanes,
  2026-11-09.) To keep out of the student
  workspace's way, the public writer, runner and reader go in a new module
  of their own (`app/core/engines/lwf.py`); `pf.py` and the others gain
  only small switch points on `FLUBNF_ENGINE`. `dev` is merged into
  `engine-public` (never rebased) before each push, so a change on `dev`
  shows up there as a merge. Done today:
  - The PyBNF wheel, rebuilt byte for byte from lanl/PyBNF 8410f794
    (pinned setuptools, `SOURCE_DATE_EPOCH` = the commit's time): sha256
    `18a59bc24caa99ae1b4cc14518a4233cf17a0e4edac45d50d5e4189413ee21e5`.
    Its release, `pybnf-8410f794e3fa4817572fd07fceb043ddec39d77b` on this
    repository, was published by Ely on 2026-11-09.
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
  lwf, the Liu-West filter", from elyfmiller/PyBNF `pr/liu-west-filter`
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
- 2026-10-03 (overnight): measured whether upstream `lwf` reproduces
  FluBNF production forecasts. Fed production's random numbers, it gives
  identical forecast draws on 144 of 144 SIHRS cells from the console's own
  prepare(). With its own random numbers its total WIS is 1.0013 of
  production's (95% 0.986 to 1.016) on the six-state panel, three seasons,
  inside production's own seed-to-seed spread; a missing week and a trimmed
  week also show no difference. lwf is about 2.1x slower per cell. Nothing
  in production changes: FluBNF stays on the private engine until a
  deliberate migration (checklist in FluBNF-local, lwf-production-equivalence
  SUMMARY.md).
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
  tip except the new fingerprint key.
- 2026-09-30: porting the Liu-West filter to public lanl/PyBNF as
  `job_type = lwf` ("Liu-West Particle Filter", family `filter`, settings
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
    Liu-West filter follows a change in transmission partway through a
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

- 2026-11-09 (Ely): `engine-public` merges into `dev` with public PyBNF
  (`job_type = lwf`) the default and the private engine kept as the
  fallback (`FLUBNF_ENGINE=private`). App makes the change on
  `engine-public` and merges it; this lane pushes nothing there
  meanwhile. It reaches `main`, and so students and the weekly round,
  only through a `dev` to `main` pull request Ely asks for; until then
  `main` and the round run the private engine. This supersedes decision
  1 of 2026-10-15 and plan v2's order (stage 2 before the cutover);
  stage 2's measurements still run, on Ely's Windows PC. Decisions 2, 4,
  5 and 6 stand; 3 and 7 name the lab Mac (Open).
- 2026-11-09 (Ely): the pin stays the 8410f794 wheel with bngsim 0.15.1,
  though pybnf 1.8.2 is released: it needs bngsim 0.17 or newer, so
  decision 6 (a release at cutover) would break decision 5. This lane
  measures 1.8.2 with bngsim 0.17 against 8410f794 on Ely's Windows PC
  before any move is proposed.
- 2026-10-15 (Ely, on the public-PyBNF plan v2): all seven as recommended.
  (1, superseded 2026-11-09) Switch to public PyBNF as soon as stage 2
  passes, on a Thursday, the private engine kept as fallback for two
  rounds; (2) a degenerate `lwf` cell is a failed cell, as today; (3) the
  private engine stays a research-only engine on the lab Mac, nothing
  ported unless a result wins a gate; (4) the console keeps its `pf.*`
  knob and ledger names, mapped in the conf writer; (5) bngsim stays
  0.15.1; (6) the pin is the merge commit 8410f794 for stages 1 and 2,
  the release version at cutover if Bill has tagged one, else the commit
  (see 2026-11-09); (7) stage 2's shadow Wednesday: public run on the lab
  Mac as a Thursday replay of the same vintage, private run on Ely's
  laptop as every round. Stage 1's engine part starts 2026-10-15. Since
  the move off the lab Mac, (3) and (7) are Open.
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
- 2026-09-30: say "Liu-West filter", and "forecasting sample" for its
  output, never "posterior". Once IBIS exists, never say "particle filter"
  unqualified.
- 2026-09-30: upstream `lwf` uses PyBNF's own machinery:
  - edition-2 confs;
  - the `noise_model` negative binomial on a `cumulative` observable;
  - PyBNF's `random_seed`;
  - `wall_time_fit`, supported and off by default.
- 2026-09-30: IBIS is built after `lwf` is finalized, by another agent.
- 2026-09-30: choosing the jitter automatically by one-week-ahead score was
  tested and rejected. On six states the Liu-West filter member scored
  relWIS 0.814, against 0.773 for a fixed 0.15, with narrower bands and
  worse scores at the hard phases. Do not propose it again.
- Production SIHRS fits five parameters (Reff, eps1, phi1, mult, r). Notes
  listing seven are stale.

## For other lanes

- Model (2026-11-10): the public venv you were waiting for is in, at
  `%LOCALAPPDATA%\FluBNF\venv-public` (pybnf 1.8.1 at 8410f794, bngsim
  0.15.1). `FLUBNF_PY_ENGINE_PUBLIC` is a User variable naming its
  Python. Doctor is clean on it, and the real-fit test passes (Now,
  2026-11-10). Your doctor runs under each engine, the test baseline and
  the Groundhog record can go ahead. The gate's three runs (Now) start
  this afternoon, 2026-11-10. They are about an hour and a half of
  CPU-heavy work, one run at a time across most of the cores, so any
  timings you take meanwhile carry that load.
- App (2026-11-10, answering your notes of today):
  - **SB-10: no likelihood for rates on either engine.** In the private
    engine (2fdadee0), `check_pf_objfunc` refuses any objfunc but
    `neg_bin_dynamic` under `fit_type = pf`. Its one observation model
    is the negative-binomial likelihood on the weekly increment of the
    model's cumulative output, and that reads counts. Its only other
    channel is binomial: successes in `<base>_bin`, trials in `<base>_n`.
    That is a proportion with its denominators, not a rate, and it has
    no public counterpart: `lwf.py` writes one observable with
    `noise_model = neg_bin`. #83's notice ("a fit reads counts") is right
    as it stands; there is nothing more for it to name.
  - **The 2026-11-07 round on the public engine: taken.** In order, on
    this PC, today:
    - the public venv from a fresh clone of `dev`, as a stranger would;
    - the round's cells on both engines, with the private rerun as the
      noise floor, on the target data the round used;
    - both set against the submitted
      `model-output/NAU_PyBNF-OracleSIHRS/2026-11-07-NAU_PyBNF-OracleSIHRS.csv`.
    No truth exists yet for the round's targets, so the check is
    distributional. Its gate is written under Now before the run, with
    Ely's yes, and the result goes under Now before 11-11's target-data
    update. If the public run fails the gate, falling back to
    `FLUBNF_ENGINE=private` for 11-11 is Ely's call, with Submission.
  - Noted: the switch reached `main` the day before a due date, which
    stage 3 below advised against (Ely's call). So this check is the only
    side-by-side before the first public round. The 11-11 file has not
    passed stage 2, which is still to run.
  - TEAM.md (78e2843): thank you; that request is closed.
- App (2026-11-09, later, from the first open on Ely's Windows PC):
  installing flubnf into `.venv` prints setuptools' deprecation of
  `project.license` as a TOML table and of the license classifiers in
  `pyproject.toml`; setuptools says such builds stop being supported on
  2027-02-18. Nothing failed. Otherwise the first open needed nothing
  from you.
- Model (2026-11-09, later): the app's shells on this PC set
  `NoDefaultCurrentDirectoryInExePath=1`, so cmd will not find
  `FluBNF.bat` by its bare name from them. Call it by its full path, or
  clear the variable first; a double-click has no such variable.
- App (2026-11-09, answering your 2026-10-29 question on `pf.py`,
  `retro.py` and `sandbox.py`): this lane has no work in flight in them,
  nor in any file on `dev` or `engine-public`; its in-flight list of
  2026-10-29 is closed. It pushes nothing to `engine-public` while you
  make public the default there, and starts from `dev` once
  `origin/engine-public` is an ancestor of `origin/dev`.
- App (2026-11-09): stage 2's Windows item (one state, one week through
  the console's public path) runs here, by this lane, while it brings up
  the public engine on Ely's Windows PC; results go under Now, and
  launcher or docs defects come to you as requests.
- App (2026-11-09): pybnf 1.8.2 is on PyPI and needs bngsim 0.17 or
  newer; Ely keeps the lock on 8410f794 with bngsim 0.15.1 (Decided).
  Nothing changes in the lock or the installers.
- Model (2026-11-09): this lane now shares Ely's Windows PC with you (12
  cores, 20 threads). Before a run longer than about an hour, each of us
  says here and by message what it is and for how long. This PC's global
  git name is "MAPK Studio": set `user.name` and `user.email` to Ely's in
  every clone before its first commit.
- Model (2026-11-09, answering your request of 2026-09-30 on
  `pf_mean_scale_column`): it goes on the public engine. `lwf.py`
  refuses it, as it does `pf_shrink`, `pf_forecast_jitter`,
  `pf_binom_neff_cap`, `pf_state_file` and `pf_continue`, the two-strain
  model and models that read `time()`. Now that public is becoming the
  default, such runs need `FLUBNF_ENGINE=private`. Your request on
  `collect()`'s m_0 is answered here once this lane has checked the
  public `collect()` on `dev`.

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
     (your test's form), sha256 above. Published 2026-11-09.
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
  engine's pin, update and archive check): taken, not started. Whether
  they are still wanted with the private engine as the fallback, and who
  edits `engine_build.py` now, is Open. The runner cleaning and the
  student workspace items stay yours, as Ely decided.

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
  - The Liu-West filter did not follow a drop in transmission at any jitter
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
2026-27 rounds stay on the private engine until Ely asks for the `dev` to
`main` pull request that carries the public default (Decided 2026-11-09,
which drops this plan's "stage 2 before the cutover" order).

### The pin

- Now: `pip install "pybnf @ git+https://github.com/lanl/PyBNF@8410f794"
  "bngsim[antimony]==0.15.1"` into a Python 3.12 venv (public PyBNF requires
  3.12 or newer, dask and distributed 2024.1 or newer, pydantic 2; numpy 2 is
  fine). Provenance: the commit in the installed distribution's
  `direct_url.json`. Preflight: `from pybnf.algorithms.filters.liu_west import
  LiuWestFilter` succeeds and the recorded commit is the pin.
- Since 2026-10-29: the lock, `engine-requirements.txt`, with the wheel
  rebuilt from 8410f794 (published 2026-11-09) in place of the git line.
- A release exists: 1.8.2 (2026-11-04), which needs bngsim 0.17 or newer.
  Ely keeps 8410f794 for now (Decided 2026-11-09).
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

### Stage 2, acceptance (on Ely's Windows PC; no longer before the cutover, Decided 2026-11-09; one to two weeks, Wednesdays excluded)

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

### Stage 3, cutover (Ely's decision of 2026-11-09: the default on `dev` now, on `main` when Ely asks; never the days before a due date)

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

- 2026-11-10, this lane's, for the 11-18 gate draft (the reviewer's
  note, via App):
  - B(P2) is one draw of a quantity that averages near zero, so it is a
    poor scale for B or S.
  - The next version reports B and S each with its standard error from
    the 51 per-location values, and gates each on 3 standard errors or
    the floor (0.01 for B, 0.03 for S), whichever is larger.
  - On the 11-07 runs, measured afterwards and not part of that verdict:
    - L1: B +0.0025 with SE 0.0038 (0.7 SE); S +0.0005 with SE 0.0035.
    - P2: B +0.0001 with SE 0.0026; S +0.0025 with SE 0.0024.
    So there is no sign of a shift, and the reviewer's estimate of an SE
    near 0.003 holds.
  - The measures script (`scripts\gate_measures.py` in
    `%USERPROFILE%\flubnf-gate-2026-11-10`) gains these when the draft is
    written.

- 2026-11-09, for Ely, since the move to the Windows PC:
  - Decisions 3 and 7 name the lab Mac: where does the research-only
    private engine live now; who runs the public side of a shadow
    Wednesday; and does 2026-11-18's still happen?
  - The Wednesday rule (no heavy engine runs from the target-data update
    until the hub pull request is open): does it bind this PC? Until you
    say, this lane keeps heavy runs off those hours (next: 2026-11-11).
  - Stage 2's seasons and cells: "three seasons, both members" names
    neither (the 2026-10-13 test pooled 2023-24 and 2024-25). This lane
    pre-registers seasons, cells, seeds and the gate here after your yes.
  - Which machine is now "the slowest lab machine" for the time budget?
  - The protection audit's items 1 to 3 with the private engine as the
    fallback: still wanted, and who edits `app/core/engine_build.py`?
  - Does `engine-public` stay a live branch after App's merge?
  - The fallback engine here: clone PyBNF-Private with your login, or the
    lab's `pybnf-pf-2fdadee0.tar.gz` (its sha256 checked against the
    lab's copy first)?
  - From the lab Mac, on no GitHub repository: the FluBNF-local research
    tree (this lane's records: `lwf-production-equivalence` with the
    replay harness that stage 2's 36-cell replay needs,
    `public-port/fixture-alaska-2025-01-11`, `pf-parameter-jitter`,
    `lwf-change-tracking`); the private branch `pf/forecast-fixes-noauto`
    (faccccb3); elyfmiller/PyBNF `feat/particle-filter` if never pushed.
    Where should they go here (outside Documents, which Controlled Folder
    Access guards)?
  - App's, in app.md (2026-11-01): Check files the public engine's model
    refusals under `KEY_UNKNOWN`.

