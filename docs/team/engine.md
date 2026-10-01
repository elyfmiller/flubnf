# Engine lane notes

The private PyBNF fork, the Liu–West filter, and its port to public PyBNF.
Works on the lab Mac, in repositories outside this one; it pushes only
this file here.

## Now

- 2026-10-01 overnight, Arizona time: CPU use on the lab Mac. The study
  above (at most 8 processes) and one PyBNF test-suite run on 6 cores.
  It slows other work while it runs but does not break it. If you need the
  machine, say so here (`Engine:` in your notes) or message the session
  "PyBNF Particle Filter". The engine run will pause and resume later. This
  file says when it's done.
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
  - In progress (2026-10-01): a pre-registered synthetic study of whether
    the Liu–West filter follows a change in transmission partway through a
    series (record: FluBNF-local `research/lwf-change-tracking/`). Uses at
    most 8 cores.
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
- Model (heads-up, 2026-10-01, synthetic data only, under study): on a toy
  SIR where transmission drops partway through, the Liu–West filter's beta
  stayed near its old value while the dispersion r fell. Forecasts were
  badly off in one case and fine in another. The move scales with the
  swarm's current spread, so drift may slow as data accumulate. Nothing is
  shown yet for the SIHRS or for production; the study above will say
  more. Until then, describe the filter's drift as an assumption of the
  model, not as "following a change".
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

## Open
