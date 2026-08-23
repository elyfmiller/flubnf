"""Gate A, width clause, measured on the SAME ENGINE the 4.06 reference used.

WHY THIS EXISTS
---------------
`gate_a.py` fits with adaptive MCMC, because clause (2) of the pre-registered
gate asks for R-hat and per-chain ESS, and neither is defined for a particle
filter. But the influenza width reference of 4.06 was measured on the PRODUCTION
path, which is the particle filter, with `pf.collect`'s anchor rescale applied.
Comparing an AMCMC width against a PF width is comparing two samplers, and a
stuck adaptive-Metropolis chain understates parameter spread, which would make a
passing width look better than it is.

So the width clause is measured a second time here, on the particle filter, at
the production settings, on the same three states and the same three origins.
This is the number to put next to 4.06.

WHAT IT DOES NOT TOUCH
----------------------
`app/core/engines/pf.py` is frozen. Its conf format is reproduced here from the
profile seam (`app/core/engines/profiles.py`), which is asserted equal to pf.py's
own constants for influenza in tests/test_engine_profiles.py. The only
differences from pf.py's influenza cell are the ones the profile carries: the
COVID template, the six-variable block, the omega default, and the COVID vintage
source.

ONE CAVEAT ON THE COMPARISON, STATED RATHER THAN BURIED
--------------------------------------------------------
pf.py declares `uniform_var = Reff__FREE`; the profile seam declares
`loguniform_var`, following `sihrs_fit.LOG_SCALE_VARS`. That disagreement
predates this work (see the seam's module docstring) and it changes the shape of
the initial particle draw over Reff, which feeds through to interval width. So
this arm is like-for-like with the 4.06 reference on ENGINE, particle count,
jitter, anchor rescale and horizon convention, but not on the Reff proposal
scale. The difference is a prior shape over one parameter, not a structural one;
it should be re-checked if the measured width lands anywhere near the bar.

Run:  .venv/bin/python research/covid-phase0/gate_a_pf_width.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core.engines import profiles as ep                     # noqa: E402
from flubnf import covid_vintage as cv                          # noqa: E402
from flubnf.covid_fit import (materialize_for_profile,          # noqa: E402
                              resolve_covid_state, write_exp)
from flubnf.profiles import COVID                               # noqa: E402
from flubnf.settings import BNG, LOCATIONS, PY_ENGINE, PYBNF    # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
SEASON_START = "2025-06-01"
ORIGINS = ("2026-01-07", "2026-02-04", "2026-03-04")
STATES = ("New York", "Pennsylvania", "North Carolina")
HORIZONS = (1, 2, 3, 4)
FLU_WIDTH_REFERENCE = 4.06
WIDTH_KILL = FLU_WIDTH_REFERENCE * 1.20

_RUNNER = '''"""Auto-generated PF runner (COVID width arm)."""
import json, os, shutil, sys
sys.path.insert(0, {pybnf!r})
from pathlib import Path
cells = json.load(open({cells!r}))
res = {{}}
for c in cells:
    d = Path(c["dir"])
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        res[c["key"]] = "ok"
    except Exception as e:
        res[c["key"]] = f"FAIL: {{e}}"[:300]
    finally:
        os.chdir(cwd)
    json.dump(res, open({out!r}, "w"))
json.dump(res, open({out!r}, "w"))
'''


def prepare(workroot: Path, particles: int, jitter: float, seed0: int,
            states=STATES, origins=ORIGINS, reff_uniform: bool = False) -> list:
    """`reff_uniform` matches pf.py's own `uniform_var = Reff__FREE` instead of
    the seam's loguniform, so the arm can be run both ways and the caveat in
    this module's docstring settled by measurement rather than argument."""
    cells = []
    for state in states:
        for asof in origins:
            truth = cv.vintage_path(asof)
            s = resolve_covid_state(state, truth_csv=truth,
                                    locations_csv=LOCATIONS,
                                    season_start=SEASON_START, as_of=asof)
            tag = f"{state.replace(' ', '_')}_{asof}"
            d = workroot / tag
            d.mkdir(parents=True, exist_ok=True)
            sfx = ep.suffix(COVID, state)
            m = materialize_for_profile(COVID, s, d / "m.bngl", suffix=sfx,
                                        t_end=int(s.n_obs) + 8)
            m.write_text(m.read_text().replace(
                "begin parameters\n", ep.defaults_block(COVID), 1))
            write_exp(s, d / f"{sfx}.exp")
            r = subprocess.run(["perl", str(BNG), "m.bngl"], capture_output=True,
                               text=True, cwd=str(d), timeout=600)
            if not (d / "m.net").is_file():
                raise RuntimeError(f"netgen failed for {state}: {r.stdout[-300:]}")
            vars_block = ep.vars_block(COVID)
            if reff_uniform:
                vars_block = vars_block.replace("loguniform_var = Reff__FREE ",
                                                "uniform_var = Reff__FREE ")
            (d / "pf.conf").write_text(
                f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {particles}
pf_jitter = {jitter}
pf_observable_mode = 1
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed0 + len(cells)}
{vars_block}""")
            cells.append({"key": tag, "dir": str(d), "state": state,
                          "asof": asof, "n_obs": int(s.n_obs),
                          "last_week_offset": int(s.last_week_offset),
                          "last_observed": float(s.observed[-1]),
                          "data_edge": cv.data_edge(asof)})
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


def execute(workroot: Path, timeout: float) -> dict:
    runner = workroot / "runner.py"
    out_json = workroot / "status.json"
    runner.write_text(_RUNNER.format(pybnf=str(PYBNF),
                                     cells=str(workroot / "cells.json"),
                                     out=str(out_json)))
    p = subprocess.Popen([str(PY_ENGINE), str(runner)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         text=True)
    t0 = time.time()
    while p.poll() is None:
        if time.time() - t0 > timeout:
            p.kill()
            raise RuntimeError("PF runner timed out")
        time.sleep(2)
    if not out_json.is_file():
        raise RuntimeError("PF runner produced no status: "
                           + (p.stderr.read() if p.stderr else "")[-500:])
    return json.loads(out_json.read_text())


def collect_and_score(cells: list, status: dict) -> pd.DataFrame:
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    rows = []
    for c in cells:
        if status.get(c["key"]) != "ok":
            rows.append({**{k: c[k] for k in ("state", "asof")},
                         "usable": False, "reason": status.get(c["key"])})
            continue
        runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
        g = sorted(runs.glob("*traj_noise*"))
        if not g:
            rows.append({"state": c["state"], "asof": c["asof"],
                         "usable": False, "reason": "no traj_noise"})
            continue
        tr = np.genfromtxt(g[0])
        if tr.ndim == 1:
            tr = tr.reshape(1, -1)
        n = c["n_obs"]
        origin = tr[:, n - 1]
        origin = origin[np.isfinite(origin)]
        med0 = float(np.median(origin)) if origin.size else float("nan")
        # the production anchor rescale, verbatim from pf.collect
        scale = c["last_observed"] / med0 if med0 > 0 else 1.0
        for h in HORIZONS:
            target = str((pd.Timestamp(c["data_edge"])
                          + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(c["data_edge"], target)
            actual = tmap.get((c["state"], target))
            v = tr[:, n - 1 + h]
            v = v[np.isfinite(v)] * scale
            if excl or actual is None or actual <= 0 or v.size < 20:
                rows.append({"state": c["state"], "asof": c["asof"],
                             "horizon": h, "target": target,
                             "excluded": bool(excl), "usable": False})
                continue
            lo, hi = np.percentile(v, [2.5, 97.5])
            rows.append({"state": c["state"], "asof": c["asof"], "horizon": h,
                         "target": target, "actual": actual, "usable": True,
                         "excluded": False, "anchor_scale": scale,
                         "median": float(np.median(v)),
                         "width_rel": float((hi - lo) / actual),
                         "covered": bool(lo <= actual <= hi)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--particles", type=int, default=10000)
    ap.add_argument("--jitter", type=float, default=0.02)
    ap.add_argument("--timeout", type=float, default=7200.0)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--reff-uniform", action="store_true",
                    help="match pf.py exactly on the Reff proposal scale")
    ap.add_argument("--smoke", action="store_true",
                    help="one cell, few particles: plumbing check only")
    a = ap.parse_args()
    states = STATES[:1] if a.smoke else STATES
    origins = ORIGINS[-1:] if a.smoke else ORIGINS
    particles = 200 if a.smoke else a.particles
    OUT.mkdir(parents=True, exist_ok=True)
    W = OUT / ("pf_smoke" if a.smoke else
               "pf_work_reffuni" if a.reff_uniform else "pf_work")
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cells = prepare(W, particles, a.jitter, seed0=20260822,
                    states=states, origins=origins,
                    reff_uniform=bool(a.reff_uniform))
    status = execute(W, a.timeout)
    df = collect_and_score(cells, status)
    use = df[df.get("usable", False) == True]           # noqa: E712
    w = float(use["width_rel"].median()) if len(use) else float("nan")
    res = {
        "engine": "particle filter, production settings",
        "particles": particles, "jitter": a.jitter, "smoke": bool(a.smoke),
        "reff_proposal": "uniform (matches pf.py)" if a.reff_uniform else "loguniform (seam default)",
        "states": list(states), "origins": list(origins),
        "cells_total": int(len(df)),
        "cells_excluded_by_march_break": int(df.get("excluded", pd.Series(dtype=bool)).sum()),
        "cells_scored": int(len(use)),
        "elapsed_min": round((time.time() - t0) / 60.0, 1),
        "width_rel_median": w,
        "width_rel_mean": float(use["width_rel"].mean()) if len(use) else float("nan"),
        "by_horizon": ({int(k): round(float(v), 3) for k, v in
                        use.groupby("horizon")["width_rel"].median().items()}
                       if len(use) else {}),
        "by_state": ({k: round(float(v), 3) for k, v in
                      use.groupby("state")["width_rel"].median().items()}
                     if len(use) else {}),
        "coverage_95": float(use["covered"].mean()) if len(use) else float("nan"),
        "reference_flu_sihrs_pf": FLU_WIDTH_REFERENCE,
        "kill_bar": WIDTH_KILL,
        "verdict": ("NO DATA" if not np.isfinite(w) else
                    "PASS" if w <= FLU_WIDTH_REFERENCE else
                    "KILL" if w > WIDTH_KILL else "FAIL (not kill)"),
        "failures": {k: v for k, v in status.items() if v != "ok"},
    }
    df.to_csv(OUT / ("gate_a_pf_smoke_cells.csv" if a.smoke else
                     "gate_a_pf_cells_reffuni.csv" if a.reff_uniform else
                     "gate_a_pf_cells.csv"), index=False)
    (OUT / ("gate_a_pf_smoke.json" if a.smoke else
            "gate_a_pf_width_reffuni.json" if a.reff_uniform else
            "gate_a_pf_width.json")).write_text(json.dumps(res, indent=2))
    if not a.keep:
        shutil.rmtree(W, ignore_errors=True)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
