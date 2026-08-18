"""The PF-SIHRS engine: conf generation + execution of PyBNF `fit_type=pf`.

Two-venv dispatch (constitutional rule 8): materialization and scoring run in
the analysis venv (py3.12, this process); the filter itself runs in the
pybnf/bngsim venv (py3.10) via a runner script written to the workroot --
a FILE, never stdin, because macOS spawn kills stdin-launched pools
(rule 4, measured 2026-08-17).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flubnf.settings import PY_ENGINE as PY310, PYBNF as PYBNF_PF
TEMPLATE = REPO / "flubnf/templates/SIHRS_pop_min.bngl"   # H stays: verdict 2026-08-17
DEFAULTS_BLOCK = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                  "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")

_RUNNER = '''"""Auto-generated PF runner. Executes every prepared cell sequentially."""
import json, os, shutil, sys
sys.path.insert(0, {pybnf_path!r})
from pathlib import Path
cells = json.load(open({cells_json!r}))
results = {{}}
import time as _t
_t0 = _t.time()
for _i, c in enumerate(cells, 1):
    d = Path(c["dir"])
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    cwd = os.getcwd(); os.chdir(d)
    try:
        from pybnf.parse import load_config
        from pybnf.pf import ParticleFilter
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
        results[c["key"]] = "ok"
    except Exception as e:
        results[c["key"]] = f"FAIL: {{e}}"[:200]
    finally:
        os.chdir(cwd)
    json.dump({{"done": _i, "total": len(cells), "t0": _t0,
               "now": _t.time()}}, open({out_json!r} + ".prog", "w"))
json.dump(results, open({out_json!r}, "w"))
'''


def prepare(spec, workroot: Path) -> list:
    """Materialize model+net+exp+conf for every (location, replicate) cell."""
    from flubnf.sihrs_fit import materialize_model, resolve_state, write_exp
    from flubnf.settings import BNG
    from app.core.data import LOCATIONS, vintage_path
    from app.core.runs import derive_seed

    vintage = vintage_path(spec.forecast_date)
    cells = []
    for loc in spec.locations:
        s = resolve_state(loc, truth_csv=vintage, locations_csv=LOCATIONS,
                          season_start=spec.season_start,
                          as_of=spec.forecast_date)
        if spec.weeks_to_drop:
            # drop the newest N rows -- nowcaster reinstates them later
            s.observed = s.observed[:-spec.weeks_to_drop]
            s.times = s.times[:-spec.weeks_to_drop]
            s.n_obs = len(s.observed)
        for rep in range(spec.replicates):
            tag = f"{loc.replace(' ', '_')}_r{rep}"
            d = workroot / tag
            d.mkdir(parents=True)
            sfx = f"{loc.replace(' ', '_')}_flu"
            m = materialize_model(s, TEMPLATE, d / "m.bngl", sfx)
            m.write_text(m.read_text().replace("begin parameters\n",
                                               DEFAULTS_BLOCK, 1))
            write_exp(s, d / f"{sfx}.exp")
            r = subprocess.run(["perl", BNG, "m.bngl"], capture_output=True,
                               text=True, cwd=str(d), timeout=300)
            if not (d / "m.net").is_file():
                raise RuntimeError(f"netgen failed for {loc}: {r.stdout[-300:]}")
            seed = derive_seed(loc, spec.forecast_date, rep)
            (d / "pf.conf").write_text(f"""bng_command = {BNG}
model = {d}/m.bngl : {d}/{sfx}.exp
output_dir = {d}/out
fit_type = pf
objfunc = neg_bin_dynamic
num_particles = {spec.particles}
pf_jitter = {spec.jitter}
pf_observable_mode = {spec.observable_mode}
pf_forecast_weeks = 4
population_size = 1
max_iterations = 1
seed = {seed}
uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
""")
            cells.append({"key": tag, "dir": str(d), "location": loc,
                          "replicate": rep, "seed": seed,
                          "n_obs": int(s.n_obs),
                          "last_week_offset": int(s.last_week_offset),
                          "last_observed": float(s.observed[-1])})
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


def execute(workroot: Path, timeout: float = 3600.0) -> dict:
    """Run every prepared cell in the py3.10 venv. Returns key -> status."""
    runner = workroot / "pf_runner.py"
    out_json = workroot / "pf_status.json"
    runner.write_text(_RUNNER.format(pybnf_path=str(PYBNF_PF),
                                     cells_json=str(workroot / "cells.json"),
                                     out_json=str(out_json)))
    r = subprocess.run([str(PY310), str(runner)], capture_output=True,
                       text=True, timeout=timeout)
    if not out_json.is_file():
        raise RuntimeError(f"PF runner produced no status: {r.stderr[-400:]}")
    return json.loads(out_json.read_text())


def collect(workroot: Path) -> dict:
    """Forecast samples per location: replicate-pooled, anchored at origin."""
    import numpy as np
    cells = json.loads((workroot / "cells.json").read_text())
    by_loc: dict = {}
    for c in cells:
        runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
        tr_files = sorted(runs.glob("*traj_noise*"))
        if not tr_files:
            continue
        tr = np.genfromtxt(tr_files[0])
        n = c["n_obs"]
        origin = tr[:, n - 1]
        med = float(np.median(origin[np.isfinite(origin)]))
        scale = c["last_observed"] / med if med > 0 else 1.0
        d = by_loc.setdefault(c["location"], {str(h): [] for h in range(5)})
        d["0"].extend((origin * scale).tolist())
        for h in (1, 2, 3, 4):
            d[str(h)].extend((tr[:, n - 1 + h] * scale).tolist())
    return by_loc
