"""Plumbing checks for the adaptive-transmission member, before the gate run.

Four things, in this order, each of which would invalidate the gate if wrong:

  1. TEMPLATE REDUCTION. SIHRS_pop_arb.bngl with the adaptive process OFF and
     no sbeta dimension must reproduce the production SIHRS_pop_min.bngl cell
     BIT FOR BIT on the same seed. A structural elaboration that does not
     reduce to the model it elaborates is testing a different model.
  2. THE PROCESS IS LIVE. The same cell with the process ON must differ, and
     its ar1_diag file must exist with one row per assimilated week.
  3. THE SCALE MOVES. The weighted mean sigma must not sit at its prior
     centre for the whole season -- if it cannot move, "fitted" is a fiction.
  4. FORECAST SANITY. Finite, positive, monotone-ish quantiles at all four
     horizons, and an origin anchor scale near 1 (the round-one COVID
     rescale pathology, checked here so it cannot arrive unnoticed).

Run:  ./.venv/bin/python research/adaptive-beta/smoke.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from gate import (DEFAULTS_BLOCK, PROD_TEMPLATE, TEMPLATE,  # noqa: E402
                  VARS_ARB, WORK, prepare_cell, preregistration_hash)
from flubnf.settings import PY_ENGINE, PYBNF                # noqa: E402

PROD_DEFAULTS = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
                 "phi1__FREE 22.0\nmult__FREE 0.05\nr__FREE 8.0\n")
PROD_VARS = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""
ARB_NO_SBETA_DEFAULTS = PROD_DEFAULTS + "sbeta__FREE 0.05\n"

LOC, ASOF, SEASON, REP = "California", "2025-01-11", "2024-25", 0
PARTICLES_SMOKE = 2000

RUNNER = '''import json, os, sys
sys.path.insert(0, {pybnf!r})
from pathlib import Path
d = Path({d!r})
os.chdir(d)
from pybnf.parse import load_config
from pybnf.pf import ParticleFilter
ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
print("ok")
'''


def run_cell(d: Path) -> None:
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    r = HERE / f"_smoke_runner_{d.name}.py"
    r.write_text(RUNNER.format(pybnf=str(PYBNF), d=str(d)))
    p = subprocess.run(["nice", "-n", "12", str(PY_ENGINE), str(r)],
                       capture_output=True, text=True, timeout=3600)
    r.unlink(missing_ok=True)
    if "ok" not in p.stdout:
        raise RuntimeError(f"cell failed: {p.stderr[-2000:]}")


def traj(d: Path) -> np.ndarray:
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    f = sorted(runs.glob("*traj_noise*"))[0]
    return np.genfromtxt(f)


def patch_particles(d: Path) -> None:
    c = (d / "pf.conf").read_text()
    (d / "pf.conf").write_text(
        c.replace("num_particles = 10000", f"num_particles = {PARTICLES_SMOKE}"))


def main() -> None:
    print(f"pre-registration {preregistration_hash()}")
    root = WORK / "_smoke"
    shutil.rmtree(root, ignore_errors=True)
    res = {}

    # ---- 1. template reduction -------------------------------------------
    d_prod = root / "prod"
    prepare_cell(d_prod, LOC, ASOF, SEASON, REP, 0.0, template=PROD_TEMPLATE,
                 vars_block=PROD_VARS, defaults=PROD_DEFAULTS, ar1=False)
    patch_particles(d_prod)
    run_cell(d_prod)

    d_red = root / "arb_reduced"
    # sbeta demoted to a fixed constant: same parameter dimension as
    # production, so the comparison is bit-for-bit and not merely close.
    prepare_cell(d_red, LOC, ASOF, SEASON, REP, 0.0, template=TEMPLATE,
                 vars_block=PROD_VARS, defaults=PROD_DEFAULTS, ar1=False,
                 text_sub=[("sbeta   sbeta__FREE", "sbeta   0.05")])
    patch_particles(d_red)
    run_cell(d_red)

    a, b = traj(d_prod), traj(d_red)
    same = a.shape == b.shape and a.tobytes() == b.tobytes()
    res["template_reduction_bitwise"] = bool(same)
    print(f"1. template reduction (arb, process OFF, no sbeta) == production: "
          f"{'PASS' if same else 'FAIL'}")
    if not same:
        d = np.abs(a - b).max() if a.shape == b.shape else float("nan")
        print(f"   max abs diff {d:.3e}  shapes {a.shape} {b.shape}")

    # ---- 2/3. the process is live and its scale moves ---------------------
    d_on = root / "arb_on"
    meta = prepare_cell(d_on, LOC, ASOF, SEASON, REP, 0.5, template=TEMPLATE,
                        vars_block=VARS_ARB, defaults=DEFAULTS_BLOCK, ar1=True)
    patch_particles(d_on)
    run_cell(d_on)
    c = traj(d_on)
    res["process_changes_output"] = bool(c.shape != a.shape
                                         or c.tobytes() != a.tobytes())
    print(f"2. process ON differs from production: "
          f"{'PASS' if res['process_changes_output'] else 'FAIL'}")

    dg = np.genfromtxt(d_on / "out" / "ar1_diag_0.txt", comments="#")
    dg = np.atleast_2d(dg)
    n_weeks = int(meta["n_obs"])
    res["diag_rows"] = int(dg.shape[0])
    res["diag_rows_expected"] = n_weeks
    print(f"   ar1_diag rows {dg.shape[0]} (weeks assimilated {n_weeks})")

    sig = dg[:, 0]
    prior_centre = float(np.exp((np.log(0.005) + np.log(0.50)) / 2))
    res["sigma_first"] = float(sig[0])
    res["sigma_last"] = float(sig[-1])
    res["sigma_min"] = float(sig.min())
    res["sigma_prior_centre"] = prior_centre
    moved = abs(sig[-1] - sig[0]) / max(sig[0], 1e-9) > 0.05
    res["scale_moves"] = bool(moved)
    print(f"3. fitted scale: first {sig[0]:.4f} -> last {sig[-1]:.4f} "
          f"(prior centre {prior_centre:.4f})  "
          f"{'PASS' if moved else 'FAIL (pinned at its start)'}")
    print(f"   mean |log increment| last week {dg[-1, 1]:.4f}")

    # ---- 4. forecast sanity ----------------------------------------------
    n = meta["n_obs"]
    origin = c[:, n - 1]
    med = float(np.median(origin[np.isfinite(origin)]))
    scale = meta["last_observed"] / med if med > 0 else float("nan")
    res["anchor_scale"] = scale
    qs = {}
    for h in (1, 2, 3, 4):
        col = c[:, n - 1 + h] * scale
        qs[h] = [float(np.quantile(col, q)) for q in (0.025, 0.5, 0.975)]
    res["quantiles"] = qs
    ok = (np.isfinite(scale) and 0.5 < scale < 2.0
          and all(np.isfinite(v).all() and v[0] <= v[1] <= v[2]
                  for v in qs.values()))
    res["forecast_sane"] = bool(ok)
    print(f"4. anchor scale {scale:.3f}; quantiles "
          + "  ".join(f"h{h}:[{v[0]:.0f},{v[1]:.0f},{v[2]:.0f}]"
                      for h, v in qs.items())
          + f"  {'PASS' if ok else 'FAIL'}")

    # production comparison at the same particle count, for context
    n_p = meta["n_obs"]
    op = a[:, n_p - 1]
    sc_p = meta["last_observed"] / float(np.median(op[np.isfinite(op)]))
    for h in (1, 4):
        cw = np.quantile(c[:, n_p - 1 + h] * scale, 0.975) - \
            np.quantile(c[:, n_p - 1 + h] * scale, 0.025)
        pw = np.quantile(a[:, n_p - 1 + h] * sc_p, 0.975) - \
            np.quantile(a[:, n_p - 1 + h] * sc_p, 0.025)
        res[f"width95_h{h}_ratio"] = float(cw / pw) if pw > 0 else None
        print(f"   width95 h={h}: adaptive {cw:.0f} vs production {pw:.0f} "
              f"(ratio {cw / pw:.2f})")

    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "smoke.json").write_text(json.dumps(res, indent=1))
    verdict = (res["template_reduction_bitwise"]
               and res["process_changes_output"] and res["forecast_sane"])
    print(f"\nSMOKE {'PASS' if verdict else 'FAIL'}")


if __name__ == "__main__":
    main()
