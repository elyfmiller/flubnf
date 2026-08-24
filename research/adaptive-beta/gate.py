"""ADAPTIVE-TRANSMISSION MEMBER. PRE-REGISTRATION, frozen before any fit.

Frozen 2026-08-23, before a single influenza or COVID fit of this candidate
was launched. Nothing below was edited after seeing a result; the run log and
the results JSON carry this file's sha256 so the claim is checkable. Work
legitimately done BEFORE freezing and therefore reflected here: the filter
mechanism was implemented and unit-tested against synthetic clouds
(PyBNF-pf tests/test_pf_adaptive.py, 22 tests), and the research record was
read (docs/RESULTS.md, the RW-beta template, research/covid-phase0/).

=============================================================================
1. WHAT IS BEING TESTED, AND WHY IT IS NOT THE MEMBER ALREADY KILLED
=============================================================================
Candidate: SIHRS whose transmission level is a fitted stochastic process
rather than a constant, filtered sequentially and frozen across the horizon.

    log Reff_t  =  log Reff_{t-1} + v_t
    v_t         =  arphi * v_{t-1} + sbeta_i * eta_t ,   eta_t ~ N(0, 1)
    beta(t)     =  Reff_t * gamma / s0 * exp( eps1*cos(2*pi*(t - phi1)/52) )

Fitted, 6 parameters: Reff (season-start level), eps1, phi1, mult, r, sbeta.
Frozen a priori: arphi = 0.5. Everything else is the production template's
sourced constants, unchanged (flubnf/templates/SIHRS_pop_arb.bngl, whose
mechanism block is byte-for-byte SIHRS_pop_min.bngl).

THE PARAMETERIZATION, STATED. The AR(1) acts on the INCREMENTS of the log of
Reff, i.e. on a velocity v that itself decays geometrically at arphi. The
seasonal harmonic is RETAINED and multiplies the adaptive level, so the
calendar term and the adaptive process coexist and the likelihood may decline
either: eps1 -> 0 leaves a pure adaptive model, sbeta -> 0 leaves the
production model exactly. sbeta is a per-particle parameter carried in the
same theta vector as the rest and weighted by the same likelihood, so it is
learned, not set. Reff is excluded from Liu-West jitter (it would otherwise
receive both treatments and be shrunk toward the ensemble mean); every other
parameter, sbeta included, keeps production Liu-West at jitter 0.30.

Four differences from RW-beta (pre-registered FAIL, 2026-08-19: 3-member
0.664 against 2-member 0.620), each one pointable at in code:

  (1) INCREMENTS, NOT LEVELS. RW-beta moved Reff by Liu-West, which is a
      mean-reverting AR(1) on the LEVEL. This is an AR(1) on the DIFFERENCES
      (pybnf/pf.py::ar1_increment_step). arphi = 0 recovers a level walk and
      is arm B, the mechanism control.
  (2) THE INNOVATION SCALE IS FITTED. RW-beta paid jitter 0.5 x ensemble-sd
      every week regardless of the data; that stable-phase width cost is the
      stated cause of its death. Here the scale is a fitted dimension
      (pf_ar1_sigma_param = sbeta__FREE) so the process can go quiet.
      Weekly weighted mean sigma is written per cell (ar1_diag_*.txt) so
      "it can go quiet" is measured, not assumed.
  (3) FROZEN FORWARD. Transmission stops moving at the forecast origin: no
      innovations and no jitter over h = 1..4 (pf.py::_write_outputs). This
      matches the field (MechBayes freezes log-beta at its last ten days;
      Pyrenew-HE freezes its DifferencedAR1 forward). STATED HONESTLY: the
      production filter already freezes parameters forward, so this property
      is INHERITED rather than new. It is listed because it is a property the
      design requires, and because it is what stops a fitted innovation scale
      from inflating the fan at long horizons; it is not a difference from
      the incumbent.
  (4) THE SEASONAL HARMONIC IS KEPT. RW-beta set eps1 = 0 and was
      deliberately calendar-free. Keeping it means the candidate cannot win
      merely by being the only member that sees the calendar, and cannot lose
      merely by being blind to it.

=============================================================================
2. ARMS
=============================================================================
P0  PRODUCTION PF. Not refitted: the sealed retrospective's stored pf member
    (app/state/retro_seal), which is 10k particles, 3 seeded replicates,
    jitter 0.30, integrated observable, derive_seed(state, asof, rep). Its
    reproduction from stored samples is asserted before use (section 5).
A   THE ARM, arphi = 0.5. Same states, same as-of dates, same replicate
    count, same particle count, SAME SEEDS (derive_seed), same priors for the
    five shared parameters. One added dimension: sbeta, loguniform(0.005,
    0.50) -- a weekly log-transmission innovation sd from 0.5% to 65%,
    loguniform because the interesting question is orders of magnitude and
    the "quiet" end must be reachable. PRIMARY. Fixed a priori; nothing about
    arm A is selected on any season.
B   MECHANISM CONTROL, arphi = 0.0. Identical to A in every other respect, so
    the pair isolates difference (1) from difference (2): a level random walk
    with a FITTED scale. Reported, never used for selection, and it CANNOT
    change the verdict on A. Run only if arm A completes with machine time to
    spare; recorded as "not run" otherwise.

NO HYPERPARAMETER IS SELECTED ON ANY SEASON. The quantity RW-beta had to
select (its jitter) is fitted here, which is the point of the design.
2023-24 and 2024-25 are the selection seasons only in the sense that gate B
is decided there and confirmed on the held-out 2025-26.

Panel: the 6-state shape-diverse panel used by every prior member gate --
Alaska, California, New York, Pennsylvania, Vermont, Wyoming -- x 3 seasons
x all 85 sealed as-of dates x 3 replicates = 1,530 fits per arm, 10k
particles. Panel is TRIAGE, not a seat: the twice-measured lesson (RW-beta
gates, two-strain gate 2) is that 6-state results do not transfer to 52. A
pass here licenses a full-grid run, nothing more.

=============================================================================
3. THE INFLUENZA GATES, IN THIS ORDER
=============================================================================
Everything is computed on cells where EVERY member exists, truth > 0, the
member's median > 0, and the seal's per-cell baseline is defined -- the
frozen score_season rule. Members are quantile-averaged (vincentized) at
EQUAL weights; no weight is fitted anywhere in this analysis, because LOSO
weighting has anti-predicted the held season three times.

A. THE DEFECT THIS TARGETS, MEASURED FIRST AND REPORTED BOTH WAYS.
   The incumbent 2-member ensemble's central-50% interval covers 0.236 at the
   Jan-2025 peak against a nominal 0.500 (too narrow) and 0.743 at the
   Feb-2024 plateau against the same nominal (too wide). The error is
   TWO-SIDED, so a candidate that simply widens everywhere is not a fix.
   Windows: as-of months 2025-01 (peak) and 2024-02 (plateau), the same turn
   cells every prior gate used.
   PASS requires BOTH, on the 3-member equal-weight ensemble:
       January 2025 cov50 > 0.35   AND   February 2024 cov50 < 0.78.
   Both numbers are reported whatever happens, together with the incumbent's
   recomputed values on the identical paired cells (the 0.236/0.743 pair is
   re-measured here rather than quoted; if the recomputation disagrees with
   those figures the discrepancy is reported and the RECOMPUTED incumbent is
   the comparator).

B. SKILL MUST NOT REGRESS.
   The 3-member equal-weight ensemble (production PF, analogue, adaptive
   member) must beat the 2-member 50/50 on identical panel cells, pooled over
   the selection seasons 2023-24 + 2024-25 -- the gate RW-beta failed at
   0.664 against 0.620 -- and the 2025-26 result is reported as the held-out
   confirmation. PASS = pooled selection-season relWIS of the 3-member below
   that of the 2-member on the same cells.

C. WIDTH PRE-SCREEN, TAKEN BEFORE ANY SCORE IS COMPUTED.
   Equal-weight quantile averaging makes the ensemble's interval width the
   arithmetic mean of member widths, so a member wider than the incumbent
   mean arithmetically guarantees a wider ensemble. Reported for the member
   against production PF on identical cells: mean interval width at the 50,
   80 and 95 levels with the empirical coverage beside each, plus width at
   MATCHED coverage (the member's width rescaled to the level at which its
   coverage equals production's). Free, and reported first in the results
   JSON so it cannot be reported selectively afterwards.

KILL RULES (any one kills the member for influenza):
  * A fails in EITHER direction (January cov50 <= 0.35, or February cov50
    >= 0.78);
  * B fails (3-member does not beat 2-member on the selection seasons);
  * the member's OWN relWIS exceeds 1.1 in ANY season.

Also reported, not gated: per-horizon relWIS (a gain confined to h=1 is a
nowcast result, not a seat); the fitted sbeta posterior by phase (the
evidence for "it can go quiet"); the fraction of cells where sbeta sits
within 2% of either bound (pinning); CVODE/filter failure counts.

=============================================================================
4. THE COVID ARM (cheap, and second)
=============================================================================
Same template family on the COVID profile: flubnf/profiles.py COVID with the
adaptive process on Reff and sbeta added, 3 states x 3 origins x 3 seeded
replicates = 27 particle-filter fits at production settings (10k particles,
jitter 0.30, integrated observable), paired against a contemporaneous
production-COVID PF control on the same states, origins and seeds. Round
two's states (New York, Pennsylvania, North Carolina), origins (2026-01-07,
2026-02-04, 2026-03-04), season start 2025-06-01, break-excluded cells.

The round-two bars, applied as written, with ONE estimator generalization
that is declared here rather than discovered later:

  1. BIMODALITY: median >= 1.5 peaks per year AND >= 5 of 9 fits >= 1.9.
     THE ESTIMATOR PROBLEM, AND THE RULING. Round two's estimator integrates
     the deterministic skeleton at posterior-median parameters for ten years
     and reads the last three. For a member whose transmission is a fitted
     stochastic process that is FROZEN at the forecast origin, that skeleton
     has constant beta by construction and must return 1.00 peaks per year --
     the estimator cannot see the arm's actual generative mechanism. Both
     estimators are therefore computed:
       (i)  SKELETON, frozen beta at the posterior median -- directly
            comparable to round one and two's 1.00, and reported first;
       (ii) GENERATIVE, the arm's own process: integrate ten years with the
            AR(1)-on-increments innovations active at the fit's posterior
            sbeta and arphi, 200 realizations per fit, median peaks per year.
     THE GATE IS DECIDED ON (ii), because (ii) is what the fitted model
     actually is. Two anti-triviality guards, both pre-registered, because a
     wandering beta can manufacture peaks:
       * REDUCTION: at sbeta = 0 the generative estimator must return the
         skeleton value to within 0.01 peaks/yr, on the same fits. If it does
         not, the estimator is broken and the clause is reported as VOID
         rather than passed.
       * OVER-FLEXIBILITY: the observed pattern is 2 to 3 waves per year, so
         a generative median outside [1.5, 3.5] is flagged. The registered
         bar is one-sided and a value above 3.5 still passes AS REGISTERED;
         it is reported as "passes the registered bar by over-flexibility",
         and the verdict line says so.
  2. WIDTH: central-95% width relative to actual <= 4.06, coverage reported
     beside it, on break-excluded cells at production settings. The COVID
     hypothesis under test is explicit: the incumbent COVID PF measured 1.689
     against the 4.06 bar, a factor of 2.4 of headroom, so the interval-width
     cost that killed RW-beta on influenza may be affordable here. The arm's
     width is reported both absolutely and as a ratio to the paired control,
     and the verdict states whether the headroom absorbed it.
  3. THE INNOVATION SCALE IS IDENTIFIED: sbeta not pinned (< 25% of pooled
     draws within 2% of either bound, the round-one omega rule) AND not
     prior-shaped (Kolmogorov distance from the loguniform prior >= 0.10).

KILL for COVID: any of the three clauses fails.

=============================================================================
5. SCORING DISCIPLINE (the house rules, applied)
=============================================================================
(a) An inline, independent Bracher et al. 2021 WIS must agree with
    flubnf.wis.wis on EVERY scored cell (max relative difference < 1e-9)
    before any table is produced.
(b) The pooling -> quantiles -> WIS path applied to the seal's STORED pf
    samples must reproduce the seal's stored per-cell WIS (< 1e-6), and
    likewise the stored analogue quantiles. The 2-member 50/50 reconstruction
    is checked against the stored ensemble as an identification of the stored
    blend. If (b) fails, the run stops: it means pooling drift or a truth
    revision, and nothing downstream can be trusted.
(c) Truth is settled truth via load_truth(); the per-cell baseline is the
    seal's own base_wis, one number per cell shared by every model.
(d) Vintage-true fitting throughout: each as-of date reads vintage_path(asof).

=============================================================================
6. WHAT THIS CANNOT SETTLE
=============================================================================
Six states, three seasons, one panel. A pass licenses a full-grid run and
nothing else. The COVID arm is 27 fits at three origins in one season and
carries no skill claim at all (relWIS against CovidHub-baseline is Gate B).

=============================================================================
USAGE
=============================================================================
    .venv/bin/python research/adaptive-beta/gate.py --smoke
    .venv/bin/python research/adaptive-beta/gate.py --run --arm A [--shards 4]
    .venv/bin/python research/adaptive-beta/gate.py --score
    .venv/bin/python research/adaptive-beta/gate.py --covid
Results land in research/adaptive-beta/out/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.data import LOCATIONS, vintage_path          # noqa: E402
from app.core.runs import derive_seed                       # noqa: E402
from flubnf.settings import BNG, PY_ENGINE, PYBNF           # noqa: E402
from flubnf.sihrs_fit import (materialize_model,            # noqa: E402
                              resolve_state, write_exp)

OUT = Path(__file__).resolve().parent / "out"
WORK = Path(os.environ.get(
    "ADAPTBETA_WORK",
    "/private/tmp/claude-1786722491/-Users-l-biosci-posnerlab-Documents-GitHub"
    "-NAU-Projects-NAU-Influenza-M-Model/ab76ceee-c2c4-485d-b683-7b08e1248f4e"
    "/scratchpad/adaptbeta"))
SEAL = REPO / "app/state/retro_seal"
TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_arb.bngl"
PROD_TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_min.bngl"

STATES = ["Alaska", "California", "New York", "Pennsylvania", "Vermont",
          "Wyoming"]
SEASONS = ["2023-24", "2024-25", "2025-26"]
SELECT_SEASONS = ["2023-24", "2024-25"]
PARTICLES = 10_000
REPLICATES = 3
JITTER = 0.30

# --- frozen a priori -------------------------------------------------------
ARMS = {"A": 0.5,      # PRIMARY: AR(1) on increments
        "B": 0.0}      # mechanism control: level random walk, fitted scale
SBETA_LO, SBETA_HI = 0.005, 0.50

# --- gate constants, frozen ------------------------------------------------
JAN_PEAK_MONTHS = ["2025-01"]
FEB_PLATEAU_MONTHS = ["2024-02"]
TURN_MONTHS = ["2024-02", "2025-01"]
JAN_COV50_BAR = 0.35          # PASS strictly above
FEB_COV50_BAR = 0.78          # PASS strictly below
MEMBER_FLOOR = 1.1            # member relWIS must stay below this every season
INCUMBENT_JAN_COV50 = 0.236   # the reported defect, re-measured here
INCUMBENT_FEB_COV50 = 0.743

DEFAULTS_BLOCK = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                  "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n"
                  "sbeta__FREE 0.05\n")
VARS_ARB = f"""uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
loguniform_var = sbeta__FREE {SBETA_LO} {SBETA_HI}
"""


def preregistration_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def season_start(season: str) -> str:
    return f"{season[:4]}-08-01"


def season_asofs(season: str) -> list:
    return sorted(p.name for p in (SEAL / season / "weeks").iterdir()
                  if p.is_dir())


# ---------------------------------------------------------------------------
# cell preparation -- our own, so app/core/engines/pf.py is never touched
# ---------------------------------------------------------------------------

def prepare_cell(d: Path, loc: str, asof: str, season: str, rep: int,
                 arphi: float, template: Path = TEMPLATE,
                 vars_block: str = VARS_ARB,
                 defaults: str = DEFAULTS_BLOCK,
                 ar1: bool = True, text_sub: list | None = None) -> dict:
    """Materialize model + net + exp + conf for one (location, replicate).

    `text_sub` is a list of (old, new) applied to the materialized BNGL
    BEFORE network generation. It exists for exactly one purpose: the
    reduction check, which needs the adaptive template with `sbeta` demoted
    to a fixed constant so the fit carries the production parameter
    dimension and can be compared bit-for-bit.
    """
    d.mkdir(parents=True, exist_ok=True)
    s = resolve_state(loc, truth_csv=vintage_path(asof), locations_csv=LOCATIONS,
                      season_start=season_start(season), as_of=asof)
    sfx = f"{loc.replace(' ', '_')}_flu"
    m = materialize_model(s, template, d / "m.bngl", sfx)
    txt = m.read_text().replace("begin parameters\n", defaults, 1)
    for old, new in (text_sub or []):
        txt = txt.replace(old, new)
    m.write_text(txt)
    write_exp(s, d / f"{sfx}.exp")
    # Network generation, with one retry. Under a parallel prepare the .net
    # is occasionally not visible on the first stat even though BNG reported
    # success (observed 2026-08-23, before any fit of this candidate ran);
    # a retry is a harness fix, not a modelling choice, and a cell that
    # cannot generate its network twice still fails loudly.
    r = None
    for attempt in range(2):
        r = subprocess.run(["perl", str(BNG), "m.bngl"], capture_output=True,
                           text=True, cwd=str(d), timeout=600)
        if (d / "m.net").is_file():
            break
        time.sleep(1.0)
    if not (d / "m.net").is_file():
        raise RuntimeError(f"netgen failed for {loc} {asof}: {r.stdout[-400:]}")
    seed = derive_seed(loc, asof, rep)
    conf = f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {PARTICLES}
pf_jitter = {JITTER}
pf_observable_mode = integrated
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed}
{vars_block}"""
    if ar1:
        conf += (f"pf_ar1_param = Reff__FREE\n"
                 f"pf_ar1_sigma_param = sbeta__FREE\n"
                 f"pf_ar1_phi = {arphi}\n")
    (d / "pf.conf").write_text(conf)
    return {"key": f"{loc.replace(' ', '_')}_r{rep}", "dir": str(d),
            "location": loc, "replicate": rep, "seed": seed, "season": season,
            "asof": asof, "arphi": arphi, "n_obs": int(s.n_obs),
            "last_week_offset": int(s.last_week_offset),
            "last_observed": float(s.observed[-1])}


def _prep_one(job):
    d, loc, asof, season, rep, arphi = job
    d = Path(d)
    if (d / "meta.json").is_file() and (d / "pf.conf").is_file() and \
            (d / "m.net").is_file():
        return json.loads((d / "meta.json").read_text())
    meta = prepare_cell(d, loc, asof, season, rep, arphi)
    (d / "meta.json").write_text(json.dumps(meta))
    return meta


def build_cells(arm: str, workers: int = 4) -> list:
    """Every cell of one arm, in a stable order. Idempotent: an already
    materialized directory is reused, so a resumed run re-prepares nothing.
    Network generation is a perl subprocess per cell, so this parallelizes."""
    from concurrent.futures import ProcessPoolExecutor
    arphi = ARMS[arm]
    root = WORK / f"arm{arm}"
    jobs = []
    for season in SEASONS:
        for asof in season_asofs(season):
            for loc in STATES:
                for rep in range(REPLICATES):
                    d = root / season / asof / f"{loc.replace(' ', '_')}_r{rep}"
                    jobs.append((str(d), loc, asof, season, rep, arphi))
    with ProcessPoolExecutor(max_workers=workers) as ex:
        cells = list(ex.map(_prep_one, jobs, chunksize=8))
    root.mkdir(parents=True, exist_ok=True)
    (root / "cells.json").write_text(json.dumps(cells))
    return cells


# ---------------------------------------------------------------------------
# execution: sharded, nice'd, resumable, compacted per cell
# ---------------------------------------------------------------------------

_RUNNER = '''"""Auto-generated adaptive-beta runner (shard {shard})."""
import json, os, shutil, sys, time
sys.path.insert(0, {pybnf!r})
from pathlib import Path
import numpy as np

cells = json.load(open({cells!r}))
out_json = {out!r}
res = {{}}
t0 = time.time()
for i, c in enumerate(cells, 1):
    d = Path(c["dir"])
    if (d / "compact.npz").is_file():
        res[c["key"] + "|" + c["asof"]] = "cached"
        continue
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        runs = d / "out" / "Results" / "A_MCMC" / "Runs"
        tr = sorted(runs.glob("*traj_noise*"))
        pf_ = sorted(runs.glob("params_*"))
        n = int(c["n_obs"])
        traj = np.genfromtxt(tr[0])
        # keep only the origin column and the four forecast horizons
        keep = traj[:, n - 1:n + 4].astype(np.float32)
        names = open(pf_[0]).readline().split()
        params = np.genfromtxt(pf_[0], skip_header=1)
        diag = d / "out" / "ar1_diag_0.txt"
        dg = np.genfromtxt(diag, comments="#") if diag.is_file() \\
            else np.zeros((0, 3))
        np.savez_compressed(d / "compact.npz", traj=keep,
                            params=params.astype(np.float32),
                            pnames=np.array(names), diag=dg)
        res[c["key"] + "|" + c["asof"]] = "ok"
    except Exception as e:
        res[c["key"] + "|" + c["asof"]] = ("FAIL: %s" % e)[:300]
    finally:
        os.chdir(cwd)
        shutil.rmtree(d / "out", ignore_errors=True)
    if i % 5 == 0 or i == len(cells):
        json.dump({{"done": i, "total": len(cells), "t0": t0,
                   "now": time.time()}}, open(out_json + ".prog", "w"))
        json.dump(res, open(out_json, "w"))
json.dump(res, open(out_json, "w"))
json.dump({{"done": len(cells), "total": len(cells), "t0": t0,
           "now": time.time()}}, open(out_json + ".prog", "w"))
'''


def execute(arm: str, shards: int = 4, nice_level: int = 12) -> list:
    """Launch `shards` nice'd runner processes over the arm's pending cells."""
    root = WORK / f"arm{arm}"
    cells = json.loads((root / "cells.json").read_text())
    pending = [c for c in cells
               if not (Path(c["dir"]) / "compact.npz").is_file()]
    print(f"arm {arm}: {len(cells)} cells, {len(pending)} pending", flush=True)
    if not pending:
        return []
    procs = []
    for sh in range(shards):
        mine = pending[sh::shards]
        if not mine:
            continue
        cj = root / f"shard_{sh}.json"
        cj.write_text(json.dumps(mine))
        rp = root / f"runner_{sh}.py"
        rp.write_text(_RUNNER.format(shard=sh, pybnf=str(PYBNF),
                                     cells=str(cj),
                                     out=str(root / f"status_{sh}.json")))
        p = subprocess.Popen(["nice", "-n", str(nice_level), str(PY_ENGINE),
                              str(rp)],
                             stdout=subprocess.DEVNULL,
                             stderr=open(root / f"shard_{sh}.err", "w"))
        procs.append(p)
        print(f"  shard {sh}: {len(mine)} cells, pid {p.pid}", flush=True)
    return procs


# ---------------------------------------------------------------------------
# collection: the seal's own path (rep-pooled, per-replicate origin anchor)
# ---------------------------------------------------------------------------

def collect(arm: str, season: str, asof: str) -> dict:
    """location -> {h: [samples]}, replicate-pooled after a per-replicate
    origin rescale. Byte-equivalent in method to app/core/engines/pf.collect."""
    root = WORK / f"arm{arm}" / season / asof
    by_loc: dict = {}
    for loc in STATES:
        for rep in range(REPLICATES):
            d = root / f"{loc.replace(' ', '_')}_r{rep}"
            f = d / "compact.npz"
            if not f.is_file():
                continue
            meta = json.loads((d / "meta.json").read_text())
            z = np.load(f, allow_pickle=False)
            tr = z["traj"].astype(float)
            origin = tr[:, 0]
            med = float(np.median(origin[np.isfinite(origin)]))
            scale = meta["last_observed"] / med if med > 0 else 1.0
            dd = by_loc.setdefault(loc, {str(h): [] for h in range(5)})
            dd["0"].extend((origin * scale).tolist())
            for h in (1, 2, 3, 4):
                dd[str(h)].extend((tr[:, h] * scale).tolist())
    return by_loc


def load_params(arm: str) -> pd.DataFrame:
    """Per-cell posterior summary of every fitted parameter."""
    rows = []
    root = WORK / f"arm{arm}"
    for season in SEASONS:
        for asof in season_asofs(season):
            for loc in STATES:
                for rep in range(REPLICATES):
                    d = root / season / asof / f"{loc.replace(' ', '_')}_r{rep}"
                    f = d / "compact.npz"
                    if not f.is_file():
                        continue
                    z = np.load(f, allow_pickle=False)
                    names = [str(x) for x in z["pnames"]]
                    p = z["params"].astype(float)
                    row = {"season": season, "asof": asof, "location": loc,
                           "replicate": rep}
                    for j, nm in enumerate(names):
                        col = p[:, j]
                        row[f"{nm}_med"] = float(np.median(col))
                        row[f"{nm}_q10"] = float(np.quantile(col, 0.10))
                        row[f"{nm}_q90"] = float(np.quantile(col, 0.90))
                    if "sbeta__FREE" in names:
                        col = p[:, names.index("sbeta__FREE")]
                        row["sbeta_lo_frac"] = float(np.mean(
                            col <= SBETA_LO * 1.02))
                        row["sbeta_hi_frac"] = float(np.mean(
                            col >= SBETA_HI * 0.98))
                    dg = z["diag"]
                    if dg.size:
                        dg = np.atleast_2d(dg)
                        row["sigma_first"] = float(dg[0, 0])
                        row["sigma_last"] = float(dg[-1, 0])
                        row["absinc_last"] = float(dg[-1, 1])
                    rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--arm", default="A")
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--nice", type=int, default=12)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"pre-registration {preregistration_hash()}", flush=True)
    if a.smoke:
        print("smoke lives in research/adaptive-beta/smoke.py", flush=True)
        return
    if a.prepare or a.run:
        t0 = time.time()
        cells = build_cells(a.arm, workers=a.shards)
        print(f"prepared {len(cells)} cells in {time.time() - t0:.0f}s",
              flush=True)
    if a.run:
        execute(a.arm, a.shards, a.nice)
        print("shards launched; poll status_*.json.prog", flush=True)


if __name__ == "__main__":
    main()
