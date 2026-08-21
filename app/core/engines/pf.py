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
# Two-strain candidate (spec.extra["variant"] == "2strain"): A/B circuits +
# the NREVSS typed-positives binomial channel. Same trim as min.
TEMPLATE_2S = REPO / "flubnf/templates/SIHRS_pop_2strain_min.bngl"
# National-growth candidate (spec.extra["variant"] == "natg"): production `min`
# plus exp(iota*(g_nat^-s - g_s)) on beta(t), iota FROZEN a priori. Same 5
# fitted parameters, same defaults, same vars -- the arm adds no dimension, so
# DEFAULTS_BLOCK and VARS_1S are reused verbatim. See flubnf/natgrowth.py.
TEMPLATE_NATG = REPO / "flubnf/templates/SIHRS_pop_natg.bngl"
DEFAULTS_2S = ("begin parameters\nReffA__FREE 1.20\nReffB__FREE 0.95\n"
               "eps1__FREE 0.15\nphi1A__FREE 22.0\nphi1B__FREE 30.0\n"
               "mult__FREE 0.05\nr__FREE 8.0\n")
VARS_1S = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""
VARS_2S = """loguniform_var = ReffA__FREE 0.6 2.5
loguniform_var = ReffB__FREE 0.3 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1A__FREE 0.0 52.0
uniform_var = phi1B__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""

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
    variant = (spec.extra or {}).get("variant")
    two_strain = variant == "2strain"
    natg = variant == "natg"
    if natg:
        from flubnf.natgrowth import IOTA_FROZEN, growth_gap_series, natg_tokens
        # The ledger's copy of the spec is the record of record, so the frozen
        # value travels in spec.extra. Absent, it falls back to the constant --
        # it is never derived here and never fitted.
        iota = float((spec.extra or {}).get("iota", IOTA_FROZEN))
    if two_strain:
        from datetime import date as _d, timedelta as _td

        import pandas as _pd

        from flubnf import nrevss
        # NREVSS release cadence: week ending Saturday D publishes the
        # following Friday, i.e. AFTER the FluSight deadline for reference
        # date D. Honest as-of uses typed data through D-7.
        nrevss_asof = (_d.fromisoformat(spec.forecast_date)
                       - _td(days=7)).isoformat()
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
        gg = None
        if natg:
            # Vintage-true on BOTH sides: the same file the state's own
            # likelihood reads. Truncated to the filter's real last week so the
            # "hold the last gap over h=1..4" branch begins exactly where the
            # forecast does, even when weeks_to_drop trimmed the tail.
            gg = growth_gap_series(
                loc, truth_csv=vintage, locations_csv=LOCATIONS,
                season_start=spec.season_start, as_of=spec.forecast_date
            ).truncate(int(s.last_week_offset))
        typed_by_t, a0 = {}, 0.85
        if two_strain:
            try:
                ser = nrevss.a_share_series(loc, spec.season_start, nrevss_asof)
                for row in ser.itertuples():
                    t_off = int((_pd.Timestamp(row.date)
                                 - _pd.Timestamp(spec.season_start)).days // 7)
                    typed_by_t[t_off] = (int(row.total_a),
                                         int(row.total_a) + int(row.total_b))
                a0 = nrevss.a0_share(loc, spec.season_start, nrevss_asof)
            except Exception:
                typed_by_t, a0 = {}, 0.85   # typed feed down: channel 2 just
                                            # has no rows; the fit still runs
        for rep in range(spec.replicates):
            tag = f"{loc.replace(' ', '_')}_r{rep}"
            d = workroot / tag
            d.mkdir(parents=True)
            sfx = f"{loc.replace(' ', '_')}_flu"
            if two_strain:
                tmpl, tok = TEMPLATE_2S, {"{{A0SHARE}}": f"{a0:.4f}"}
            elif natg:
                tmpl, tok = TEMPLATE_NATG, natg_tokens(gg, iota)
            else:
                tmpl, tok = TEMPLATE, None
            m = materialize_model(s, tmpl, d / "m.bngl", sfx, extra_tokens=tok)
            m.write_text(m.read_text().replace("begin parameters\n",
                                               DEFAULTS_2S if two_strain
                                               else DEFAULTS_BLOCK, 1))
            if two_strain:
                lines = ["# time H_weekly A_share_bin A_share_n"]
                for t_off, v in zip(s.times, s.observed):
                    a_k, n_k = typed_by_t.get(int(t_off), (-1, -1))
                    lines.append(f"{int(t_off)} {v:.6f} {a_k} {n_k}")
                (d / f"{sfx}.exp").write_text("\n".join(lines) + "\n")
            else:
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
{VARS_2S if two_strain else VARS_1S}"""
+ (f"pf_binom_neff_cap = {(spec.extra or {}).get('neff_cap', 300)}\n"
   if two_strain else ""))
            cells.append({"key": tag, "dir": str(d), "location": loc,
                          "replicate": rep, "seed": seed,
                          "variant": ("2strain" if two_strain
                                      else "natg" if natg else "1strain"),
                          "a0": a0 if two_strain else None,
                          "typed_weeks": len(typed_by_t) if two_strain else None,
                          "iota": iota if natg else None,
                          "natg_last_gap": gg.last_gap if natg else None,
                          "natg_active_weeks": gg.n_active if natg else None,
                          "natg_clipped_weeks": gg.n_clipped if natg else None,
                          "n_obs": int(s.n_obs),
                          "last_week_offset": int(s.last_week_offset),
                          "last_observed": float(s.observed[-1])})
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


class RunStopped(Exception):
    pass


def execute(workroot: Path, timeout: float = 3600.0) -> dict:
    """Run every prepared cell in the engine venv. Cancelable: touching
    <workroot>/STOP terminates the runner between cells."""
    import time
    runner = workroot / "pf_runner.py"
    out_json = workroot / "pf_status.json"
    runner.write_text(_RUNNER.format(pybnf_path=str(PYBNF_PF),
                                     cells_json=str(workroot / "cells.json"),
                                     out_json=str(out_json)))
    # reduced scheduling priority: the fit yields to the interactive server
    # so the application stays usable during a multi-hour run. `nice` execs
    # the interpreter, so this Popen still refers to the real runner process
    # and the STOP handling below is unchanged. See app/core/proc.py.
    from app.core.proc import low_priority_cmd, low_priority_popen_kwargs
    proc = subprocess.Popen(low_priority_cmd([str(PY310), str(runner)]),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, **low_priority_popen_kwargs())
    t0 = time.time()
    stop = workroot / "STOP"
    while proc.poll() is None:
        if stop.exists():
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise RunStopped("stopped by user")
        if time.time() - t0 > timeout:
            proc.kill()
            raise RuntimeError("PF runner timed out")
        time.sleep(1)
    if not out_json.is_file():
        raise RuntimeError(f"PF runner produced no status: "
                           f"{(proc.stderr.read() if proc.stderr else '')[-400:]}")
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
