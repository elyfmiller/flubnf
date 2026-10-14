# Engine lane notes

The private PyBNF fork, the Liu–West filter, and its port to public PyBNF.
Works on the lab Mac, in repositories outside this one; it pushes only
this file here.

## Now

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

- App, Submission, Model (2026-10-13): the plan below, "FluBNF on public
  PyBNF", is a draft for when lanl/PyBNF#985 merges; it names what each
  lane changes and when. Stage 0 asks nothing but reading; no branch
  before Ely posts the merge commit. It also answers App's request of
  2026-09-30 as far as it can before the merge (Python 3.12 or newer,
  pip-installed engine, edition-2 confs, Results/LWF output names).
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

## Plan: FluBNF on public PyBNF (draft 2026-10-13, for Ely and the other lanes)

Why now: lanl/PyBNF#985 (`job_type = lwf`, the Liu-West filter) is open.
When it merges and Bill cuts a release, FluBNF can drop the private fork:
the engine becomes `pip install pybnf`, and the console's conf writer,
runner, readers, preflight and installers change with it. Nothing here
starts before Ely says so; the 2026-27 rounds run on the private engine
(2fdadee0) until the gate in stage 2 passes. Measured basis (lab tree,
research/lwf-production-equivalence, 2026-10-03): fed the same random
inputs, `lwf` reproduces the production engine's forecasts exactly on
144/144 SIHRS cells; with its own streams, total WIS ratio 1.0013 (95%
0.986 to 1.016); about 2.1x slower per cell; the plumbing differs
everywhere.

### What changes

| | today (private fork) | after (public PyBNF) |
|---|---|---|
| engine | PyBNF-Private `feature/particle-filter`, pinned by commit (2fdadee0) in app/core/engine_build.py | `pybnf` from PyPI, pinned by version; until the first release, a lanl commit through pip's git URL (lanl/PyBNF is public, no login) |
| how lab users get it | a 130 KB archive or a 140 MB bundle in Downloads, or a collaborator invitation; setup_engine.sh / setup.ps1 find it, unpack it and `pip install -e` | `pip install "pybnf==<v>" "bngsim[antimony]==0.15.1"` into a Python 3.12 venv; no login, no file to hand out, no archive hunt, no stale-engine failure mode |
| engine venv | Python 3.11 or 3.12, numpy<2, dask 2022.12.1, bngsim 0.15.1 | Python >= 3.12, numpy >= 1.24 (2.x fine), dask and distributed >= 2024.1, pydantic 2, bngsim 0.15.x |
| conf | edition 1: `fit_type = pf`, `objfunc = neg_bin_dynamic`, `pf_*` keys, `pf_seed`, `pf_start_time = -1`, `pf_cumulative_observable = Hobs` | edition 2: `model:`, `experiment:`, two `noise_model` lines (neg_bin, dispersion = fit r, location = mean, cumulative, on Hobs), `job_type = lwf`, `lwf_*` keys, `random_seed` |
| model template | SIHRS_pop_min.bngl with its `simulate` action | the same model with no action but `generate_network` |
| data file | counts from t = -1 (the initial state one week before the first row) | times one week later (t = 0 is the start; the counter species keeps the seasonal phase), column `Hobs`, a `nan` row per missing week |
| runner | `from pybnf.pf import ParticleFilter; ParticleFilter(load_config(conf)).run(None)`, the fork first on sys.path | `from pybnf.algorithms.filters.liu_west import LiuWestFilter; LiuWestFilter(load_config(conf)).run(None)`, nothing on sys.path (an old private checkout left there shadows the package) |
| outputs the console reads | out/Results/PF/Runs/*traj_noise*, ess_0.txt, params_0.txt, pf_state.npz | Results/LWF/forecasts.txt, predicted_counts.txt, parameters.txt (also parameters_by_row.txt, weight_ess.txt, summary.txt); the state file `lwf_state_file` names |
| preflight | pybnf/pf.py exists; parse.py grepped for keys; the "is not an observable" stale-engine error | an import probe of LiuWestFilter plus `pybnf.__version__` against the pin; one error wording |
| provenance | fork branch, commit and VERSION stamp; builds that were not reconstructible (docs/MODEL-PROVENANCE.md) | the pybnf and bngsim version strings; a release is a reproducible build |
| random streams | `pf_seed`, per-week streams | `random_seed`, keyed streams; stored records cannot be regenerated bit for bit across the switch; any record on `lwf` is a new measurement |
| degenerate update | keeps the prior weights and still forecasts | stops with an error naming the row, outputs through the last assimilated row, no forecast (decision 2) |
| revised earlier rows on a continuation | silently ignored | refused; production refits every week, so nothing depends on it |
| cost | about 5 to 14 min per 159-cell weekly grid on the lab Mac | roughly twice that, inside the console's one-hour floor; the per-cell cost model needs refitting |
| research paths with no `lwf` equivalent | two-strain binomial channel, reporting-model likelihood modes, pf_shrink, pf_forecast_jitter, continuing private clouds | not available; all are off in production (decision 3) |
| per-parameter jitter | not in 2fdadee0 | `lwf_parameter_jitter`, in #985; whether to use it waits on the engine lane's test |

### Stage 0, now (nothing in production changes)

- Engine: keep #985 green and answer Bill's review; finish the
  per-parameter jitter test; keep the equivalence harness runnable as the
  acceptance test for the merge commit.
- App: read-only: this table and the equivalence summary; no branch yet.
  Settle the shape of the engine switch with Ely (decision 4) so the
  stage 1 branch starts right.
- Submission: one line in FLUSIGHT-2026-27.md: the engine switch is
  planned, not scheduled, and never lands in the days before a due date.
- Model: list the research replays that would still need the private
  engine after the switch (decision 3).

### Stage 1, the pull request is merged into lanl main (trigger: Ely posts the merge commit)

Engine, lab Mac:
1. Install the merge commit into a fresh venv (`~/.venvs/flubnf-lwf`,
   Python 3.12: `pip install "pybnf @ git+https://github.com/lanl/PyBNF@<sha>"
   "bngsim[antimony]==0.15.1"`); rerun the equivalence replay (144 cells)
   on it; post here the pin (commit or version), the Python floor, the
   dependency set, the bngsim version, the exact conf and data
   translation, the output names.
2. Post one production cell translated by hand (Alaska 2025-01-11: conf,
   .exp, template, outputs) so the App lane builds against real files.

App, branch `engine-public` on `dev`, opt-in until stage 3:
3. flubnf/settings.py: `FLUBNF_ENGINE = private | public` (default
   private); `PY_ENGINE` for the public venv; `FLUBNF_PYBNF` private only.
4. app/core/engines/pf.py: a second writer, runner and reader behind the
   switch: the edition-2 conf, the template without actions, write_exp
   with the one-week shift, `Hobs` and `nan` rows, the LiuWestFilter
   runner, collect() from Results/LWF, the preflight as an import probe
   with a version check; engine_build.py's production pin becomes a pybnf
   version; doctor and reclaim follow.
5. knobs.py and the ledger keep the console's own names (`pf.jitter`,
   `pf.particles` ...) and map them in the writer; renaming the console's
   schema is decision 4.
6. Sandbox: sandbox_bngl.py writes the public conf under the switch; the
   "needs no engine" check is unchanged.
7. Tests: fixtures from the engine lane's translated cell; CI has no
   engine, so the writer and readers are tested on fixtures, as today.
8. setup_engine.sh, setup.ps1, install.sh: a public route (venv plus pip)
   beside the private one; docs ENGINE.md, INSTALL-STUDENTS.md,
   WINDOWS.md, LAUNCHERS.md, README. Nothing reaches a student until
   `main`.

Model and Submission: nothing runs on the public engine yet.

### Stage 2, acceptance (trigger: the `engine-public` branch runs one week end to end on the lab Mac)

- Engine and Model, lab Mac: the full grid through the console's public
  path, three seasons, both members (Oracle SIHRS with the step, the
  filter alone), against the private engine's own rerun on identical
  cells (not the stored reseal, whose streams differ). The gate is
  pre-registered before the run; starting values: total WIS ratio public
  over private within 0.98 to 1.02 per season and pooled, 50% and 95%
  coverage within 0.02, no failed cell the private run did not have, no
  degenerate update; plus the byte-level replay on 36 cells. Expected
  from the 2026-10-03 study: ratio about 1.00.
- App: the same on Windows (one state, one week) and the installer from
  scratch on a clean user account, then Ely's laptop.
- Submission: one shadow Wednesday: both engines run, the private file is
  submitted, the public file is diffed and kept.
- Engine: the per-cell cost model refitted; the time budget checked on
  the slowest lab machine.

### Stage 3, cutover (trigger: Ely's decision after stage 2, ideally on a PyPI release; a Thursday, never the days before a due date)

- App: `FLUBNF_ENGINE` defaults to public; engine_build.py pins the pybnf
  version; the setup scripts default to the public route; the private
  route stays one release as "legacy", then goes; docs/MODEL-PROVENANCE.md
  records the switch and the first public-engine round.
- Submission: the next round runs public with the private engine still
  installed as the fallback; the method card needs no change unless it
  names the build.
- Engine: the private branches are archived read-only; the last
  private-engine round is recorded; the stale-engine error wordings go.
- Model: research replays move or stay private per decision 3.

### Decisions for Ely

1. Timing: build and validate during the season; switch only after stage
   2 passes, at a quiet point. A mid-season switch is defensible when the
   full grid agrees within the gate, because every submission is a
   self-computed replay and the card does not name the build; waiting for
   the end of May is the conservative choice.
2. Degenerate row: accept the failed cell (the week is stored from the
   other replicates) or rewrite the row as `nan` and rerun. Not seen once
   in 2,100 runs.
3. Research paths: keep the private engine as a research-only engine
   (two engines installed on the lab Mac), or port two-strain and the
   reporting model to `lwf` later. Production needs neither.
4. Names: the console keeps its `pf.*` knob and ledger names and maps
   them (least churn, stored records stay readable), or renames to
   `lwf.*` at the cutover. The rule "rename nothing to `lwf_*` yet"
   stands until stage 1.
5. bngsim: 0.15.1 (bit-identical to every production integration) or
   0.16.0 (what #985's CI runs). 0.15.1 until measured.
6. Whether the public route may pin a lanl commit before a PyPI release
   (pip's git URL works, no login), or waits for the release.

## Open

- 2026-10-13: the six decisions at the end of the public-PyBNF plan
  (timing, degenerate rows, research paths, console names, bngsim pin,
  pinning a commit before a release).
