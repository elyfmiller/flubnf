"""COVID arm of the adaptive-transmission member: the round-two bars, applied.

The pre-registration is research/adaptive-beta/gate.py section 4, frozen and
hashed before any fit of this candidate ran. This file implements it and adds
nothing: the three clauses, their bars, the states, the origins and the
estimator ruling are all specified there.

  1. BIMODALITY  >= 1.5 peaks/yr median AND >= 5 of 9 fits >= 1.9, decided on
     the GENERATIVE estimator (the arm's own stochastic process), with the
     SKELETON estimator reported beside it for continuity with rounds one and
     two, a pre-registered REDUCTION guard (sbeta = 0 must return the
     skeleton) and a pre-registered OVER-FLEXIBILITY flag (outside [1.5, 3.5]).
  2. WIDTH       central-95 relative to actual <= 4.06, coverage beside it,
     production settings, break-excluded cells, paired against a
     contemporaneous production-COVID control.
  3. IDENTIFIED  sbeta not pinned (< 25% of pooled draws within 2% of a bound)
     and not prior-shaped (Kolmogorov distance from its prior >= 0.10).

Run:  ./.venv/bin/python research/adaptive-beta/covid_gate.py
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from app.core.runs import derive_seed                       # noqa: E402
from flubnf import covid_vintage as cv                      # noqa: E402
from flubnf.covid_fit import (materialize_for_profile,      # noqa: E402
                              resolve_for_profile, write_exp)
from flubnf.profiles import COVID                           # noqa: E402
from flubnf.settings import BNG, LOCATIONS, PY_ENGINE, PYBNF  # noqa: E402
from flubnf.simulate_sihrs import simulate_sihrs            # noqa: E402
from flubnf.unimodal_guard import all_peaks, count_waves    # noqa: E402

import gate                                                 # noqa: E402

OUT = HERE / "out"
WORK = gate.WORK / "covid"

SEASON_START = "2025-06-01"
ORIGINS = ("2026-01-07", "2026-02-04", "2026-03-04")
STATES = ("New York", "Pennsylvania", "North Carolina")
SELECTION_ASOF = "2026-03-18"
HORIZONS = (1, 2, 3, 4)
PARTICLES = 10_000
REPLICATES = 3
JITTER = 0.30
ARPHI = gate.ARMS["A"]          # the primary arm's frozen value

WIDTH_BAR = 4.06
BIMODAL_MEDIAN_BAR = 1.5
BIMODAL_FIT_CRITERION = 1.9
BIMODAL_COUNT_BAR = 5
OVERFLEX_HI = 3.5               # reported flag, not a bar
PIN_BAR, BOUND_TOL, KS_BAR = 0.25, 0.02, 0.10
N_REALIZATIONS = 200            # generative estimator, per fit

TPL_ARB = REPO / "flubnf/templates/SIHRS_pop_covid_arb.bngl"
PRIORS_ARB = dict(COVID.fitted_priors)
PRIORS_ARB["sbeta__FREE"] = (gate.SBETA_LO, gate.SBETA_HI)

_RUNNER = '''"""Auto-generated COVID adaptive-beta runner."""
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
        res[c["key"]] = ("FAIL: %s" % e)[:300]
    finally:
        os.chdir(cwd)
    json.dump(res, open({out!r}, "w"))
json.dump(res, open({out!r}, "w"))
'''


def build_arms() -> dict:
    """A1 IS the shipped COVID profile; ADAPT adds sbeta and the process."""
    adapt = dataclasses.replace(COVID, template=TPL_ARB,
                                fitted_priors=PRIORS_ARB)
    return {"control": COVID, "adaptive": adapt}


def assert_states() -> None:
    truth = cv.vintage_path(SELECTION_ASOF)
    for st in STATES:
        s = resolve_for_profile(COVID, st, truth_csv=truth,
                                locations_csv=LOCATIONS,
                                season_start=SEASON_START,
                                as_of=SELECTION_ASOF)
        assert count_waves(s.observed) >= 2, f"{st} no longer satisfies the rule"


def _vars_block(profile) -> str:
    out = []
    for name, (lo, hi) in profile.fitted_priors.items():
        log = name in profile.log_scale_vars and lo > 0
        if name == "Reff__FREE":
            log = False                 # production PF proposal scale
        if name == "sbeta__FREE":
            log = True
        out.append(f"{'loguniform_var' if log else 'uniform_var'} = "
                   f"{name} {lo} {hi}")
    return "\n".join(out) + "\n"


def _defaults_block(profile) -> str:
    vals = {"Reff__FREE": 1.20, "eps1__FREE": 0.15, "phi1__FREE": 22.0,
            "omega__FREE": 0.0256, "mult__FREE": 0.05, "r__FREE": 8.0,
            "sbeta__FREE": 0.05}
    return "begin parameters\n" + "".join(f"{k} {vals[k]}\n"
                                          for k in profile.fitted_priors)


def prepare(arm: str, workroot: Path) -> list:
    profile = build_arms()[arm]
    adaptive = arm == "adaptive"
    cells = []
    for state in STATES:
        for asof in ORIGINS:
            truth = cv.vintage_path(asof)
            s = resolve_for_profile(profile, state, truth_csv=truth,
                                    locations_csv=LOCATIONS,
                                    season_start=SEASON_START, as_of=asof)
            for rep in range(REPLICATES):
                tag = f"{state.replace(' ', '_')}_{asof}_rep{rep}"
                d = workroot / tag
                d.mkdir(parents=True, exist_ok=True)
                sfx = f"{state.replace(' ', '_')}_covid"
                m = materialize_for_profile(profile, s, d / "m.bngl",
                                            suffix=sfx,
                                            t_end=int(s.n_obs) + 8)
                m.write_text(m.read_text().replace(
                    "begin parameters\n", _defaults_block(profile), 1))
                write_exp(s, d / f"{sfx}.exp")
                for _ in range(2):
                    r = subprocess.run(["perl", str(BNG), "m.bngl"],
                                       capture_output=True, text=True,
                                       cwd=str(d), timeout=600)
                    if (d / "m.net").is_file():
                        break
                    time.sleep(1.0)
                if not (d / "m.net").is_file():
                    raise RuntimeError(f"netgen failed {arm} {state}: "
                                       f"{r.stdout[-300:]}")
                seed = derive_seed(state, asof, rep)
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
{_vars_block(profile)}"""
                if adaptive:
                    conf += (f"pf_ar1_param = Reff__FREE\n"
                             f"pf_ar1_sigma_param = sbeta__FREE\n"
                             f"pf_ar1_phi = {ARPHI}\n")
                (d / "pf.conf").write_text(conf)
                cells.append({"key": tag, "dir": str(d), "state": state,
                              "asof": asof, "rep": rep, "seed": seed,
                              "n_obs": int(s.n_obs),
                              "last_observed": float(s.observed[-1]),
                              "data_edge": cv.data_edge(asof)})
    (workroot / "cells.json").write_text(json.dumps(cells))
    return cells


def execute(workroot: Path, timeout: float = 14400.0, nice_level: int = 12,
            shards: int = 3) -> dict:
    cells = json.loads((workroot / "cells.json").read_text())
    procs, outs = [], []
    for sh in range(shards):
        mine = cells[sh::shards]
        if not mine:
            continue
        cj = workroot / f"shard_{sh}.json"
        cj.write_text(json.dumps(mine))
        oj = workroot / f"status_{sh}.json"
        rp = workroot / f"runner_{sh}.py"
        rp.write_text(_RUNNER.format(pybnf=str(PYBNF), cells=str(cj),
                                     out=str(oj)))
        procs.append(subprocess.Popen(
            ["nice", "-n", str(nice_level), str(PY_ENGINE), str(rp)],
            stdout=subprocess.DEVNULL,
            stderr=open(workroot / f"shard_{sh}.err", "w")))
        outs.append(oj)
    t0 = time.time()
    while any(p.poll() is None for p in procs):
        if time.time() - t0 > timeout:
            for p in procs:
                p.kill()
            raise RuntimeError("COVID runner timed out")
        time.sleep(5)
    status = {}
    for oj in outs:
        if oj.is_file():
            status.update(json.loads(oj.read_text()))
    return status


# ---------------------------------------------------------------------------
# clause 2: width and coverage (gate_a2.pf_score, same conventions)
# ---------------------------------------------------------------------------

def score_width(cells: list, status: dict) -> pd.DataFrame:
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    by_cell: dict = {}
    for c in cells:
        ent = by_cell.setdefault((c["state"], c["asof"]),
                                 {"reps": [], "meta": c})
        if status.get(c["key"]) != "ok":
            ent["reps"].append({"ok": False})
            continue
        runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
        g = sorted(runs.glob("*traj_noise*"))
        if not g:
            ent["reps"].append({"ok": False})
            continue
        tr = np.genfromtxt(g[0])
        if tr.ndim == 1:
            tr = tr.reshape(1, -1)
        n = c["n_obs"]
        origin = tr[:, n - 1]
        origin = origin[np.isfinite(origin)]
        med0 = float(np.median(origin)) if origin.size else float("nan")
        scale = c["last_observed"] / med0 if med0 > 0 else 1.0
        ent["reps"].append({"ok": True, "scale": float(scale),
                            "med0_raw": med0,
                            "traj": {str(h): tr[:, n - 1 + h]
                                     for h in HORIZONS}})
    rows = []
    for (state, asof), ent in by_cell.items():
        meta = ent["meta"]
        good = [r for r in ent["reps"] if r.get("ok")]
        for h in HORIZONS:
            target = str((pd.Timestamp(meta["data_edge"])
                          + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(meta["data_edge"], target)
            actual = tmap.get((state, target))
            if not good or excl or actual is None or actual <= 0:
                rows.append({"state": state, "asof": asof, "horizon": h,
                             "target": target, "excluded": bool(excl),
                             "usable": False})
                continue
            resc = np.concatenate([r["traj"][str(h)] * r["scale"]
                                   for r in good])
            resc = resc[np.isfinite(resc)]
            lo, hi = np.percentile(resc, [2.5, 97.5])
            rows.append({"state": state, "asof": asof, "horizon": h,
                         "target": target, "actual": actual, "usable": True,
                         "excluded": False,
                         "anchor_scale_max": float(max(r["scale"]
                                                       for r in good)),
                         "median_rescaled": float(np.median(resc)),
                         "width_rel": float((hi - lo) / actual),
                         "covered": bool(lo <= actual <= hi)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# clause 1: bimodality, both estimators
# ---------------------------------------------------------------------------

def _sim_params(med: dict, profile) -> dict:
    f = profile.fixed

    def g(k, d=0.0):
        return float(med.get(k + "__FREE", med.get(k, d)))
    return dict(N=1.0e7, s0=f.s0_default, i0=1.0e-4,
                R0=g("Reff") / f.s0_default, eps1=g("eps1"), phi1=g("phi1"),
                eps2=0.0, phi2=0.0, gamma=f.gamma_per_week, rho=f.rho,
                gammaH=f.gammaH_per_week, omega=g("omega"), mult=g("mult"),
                impr=0.0)


def peaks_skeleton(params: dict, years: int = 10, read: int = 3) -> float:
    """gate_a2's validated estimator: the DETERMINISTIC skeleton."""
    res = simulate_sihrs(params, n_weeks=52 * years)
    hw = np.asarray(res.H_weekly, float)[-(52 * read + 1):-1]
    if not np.all(np.isfinite(hw)) or hw.max() <= 0:
        return float("nan")
    pk = [p for p in all_peaks(hw) if 0 < p.index < len(hw) - 1]
    return len(pk) / float(read)


STEPS_PER_WEEK = 7


def _integrate_paths(p: dict, sbeta: float, arphi: float, rng, n_weeks: int,
                     n_real: int) -> np.ndarray:
    """Weekly admission incidence for `n_real` realizations, vectorized.

    The SIHRS population form of flubnf/simulate_sihrs (frequency-dependent
    infection beta*S*I/N) integrated with the fixed-step daily RK4 the
    production filter uses (flubnf/particle_filter.propagate, verified
    against the BNGL/BNG path to 1.5e-9). Realizations are columns, so the
    stochastic beta path costs one vector of normals per week rather than a
    Python loop per realization.

    Returns (n_weeks, n_real) of rho*gamma*I at week ends.
    """
    N, s0, i0 = p["N"], p["s0"], p["i0"]
    gamma, rho, gammaH, omega = p["gamma"], p["rho"], p["gammaH"], p["omega"]
    eps1, phi1 = p["eps1"], p["phi1"]
    S = np.full(n_real, N * s0)
    I = np.full(n_real, N * i0)
    H = np.zeros(n_real)
    R = np.full(n_real, N * max(0.0, 1.0 - s0 - i0))
    R0 = np.full(n_real, p["R0"])
    v = np.zeros(n_real)
    hw = np.empty((n_weeks, n_real))
    dt = 1.0 / STEPS_PER_WEEK

    def deriv(t, S, I, H, R, b0):
        b = b0 * np.exp(eps1 * np.cos(2 * np.pi * (t - phi1) / 52.0))
        inf = b * S * I / N
        return (-inf + omega * R, inf - gamma * I,
                rho * gamma * I - gammaH * H,
                (1 - rho) * gamma * I + gammaH * H - omega * R)

    for k in range(n_weeks):
        if sbeta > 0:
            v = arphi * v + sbeta * rng.standard_normal(n_real)
            R0 = np.clip(R0 * np.exp(v), 0.05, 20.0)
        b0 = R0 * gamma
        t = float(k)
        for _ in range(STEPS_PER_WEEK):
            k1 = deriv(t, S, I, H, R, b0)
            k2 = deriv(t + dt / 2, S + dt / 2 * k1[0], I + dt / 2 * k1[1],
                       H + dt / 2 * k1[2], R + dt / 2 * k1[3], b0)
            k3 = deriv(t + dt / 2, S + dt / 2 * k2[0], I + dt / 2 * k2[1],
                       H + dt / 2 * k2[2], R + dt / 2 * k2[3], b0)
            k4 = deriv(t + dt, S + dt * k3[0], I + dt * k3[1],
                       H + dt * k3[2], R + dt * k3[3], b0)
            S = np.maximum(S + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]), 0.0)
            I = np.maximum(I + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]), 0.0)
            H = np.maximum(H + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]), 0.0)
            R = np.maximum(R + dt / 6 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]), 0.0)
            t += dt
        hw[k] = rho * gamma * I
    return hw


def peaks_generative(params: dict, sbeta: float, arphi: float, rng,
                     years: int = 10, read: int = 3,
                     n_real: int = N_REALIZATIONS) -> dict:
    """The ARM'S OWN generative model: the AR(1)-on-increments process is
    live, so multi-wave behaviour can arise from transmission variation
    rather than from a limit cycle. At sbeta = 0 this must reduce to the
    skeleton, which is the pre-registered guard."""
    n_weeks = 52 * years
    n = max(1, n_real if sbeta > 0 else 1)
    hw = _integrate_paths(params, sbeta, arphi, rng, n_weeks, n)
    vals = []
    for j in range(n):
        seg = hw[-(52 * read + 1):-1, j]
        if not np.all(np.isfinite(seg)) or seg.max() <= 0:
            vals.append(float("nan"))
            continue
        pk = [p for p in all_peaks(seg) if 0 < p.index < len(seg) - 1]
        vals.append(len(pk) / float(read))
    v = np.asarray(vals, float)
    v = v[np.isfinite(v)]
    return {"median": float(np.median(v)) if v.size else float("nan"),
            "mean": float(np.mean(v)) if v.size else float("nan"),
            "frac_bimodal": float(np.mean(v >= BIMODAL_FIT_CRITERION))
            if v.size else float("nan"),
            "n": int(v.size)}


def posterior_medians(cell: dict) -> tuple:
    runs = Path(cell["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
    g = sorted(runs.glob("params_*"))
    if not g:
        return {}, None
    names = open(g[0]).readline().split()
    p = np.genfromtxt(g[0], skip_header=1)
    med = {n: float(np.median(p[:, j])) for j, n in enumerate(names)}
    return med, (names, p)


def ks_vs_loguniform(v, lo, hi) -> float:
    v = np.asarray(v, float)
    v = v[(v > 0) & np.isfinite(v)]
    if v.size == 0:
        return float("nan")
    u = (np.log(np.clip(v, lo, hi)) - np.log(lo)) / (np.log(hi) - np.log(lo))
    u = np.sort(u)
    n = u.size
    i = np.arange(1, n + 1)
    return float(max(np.max(i / n - u), np.max(u - (i - 1) / n)))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"pre-registration {gate.preregistration_hash()}", flush=True)
    assert_states()
    res = {"preregistration_sha256_16": gate.preregistration_hash(),
           "arphi": ARPHI, "states": list(STATES), "origins": list(ORIGINS),
           "particles": PARTICLES, "replicates": REPLICATES}

    arms_out = {}
    for arm in ("control", "adaptive"):
        W = WORK / arm
        cached = OUT / f"covid_{arm}_status.json"
        if cached.is_file() and (W / "cells.json").is_file():
            cells = json.loads((W / "cells.json").read_text())
            status = json.loads(cached.read_text())
        else:
            W.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            cells = prepare(arm, W)
            status = execute(W)
            cached.write_text(json.dumps(status))
            print(f"{arm}: {len(cells)} fits in "
                  f"{(time.time() - t0) / 60:.1f} min", flush=True)
        n_ok = sum(1 for v in status.values() if v == "ok")
        print(f"{arm}: {n_ok}/{len(cells)} fits ok", flush=True)
        arms_out[arm] = {"cells": cells, "status": status, "n_ok": n_ok}

    # ---- clause 2: width ------------------------------------------------
    print("\n=== CLAUSE 2: width (bar <= 4.06) ===")
    width = {}
    for arm in ("control", "adaptive"):
        df = score_width(arms_out[arm]["cells"], arms_out[arm]["status"])
        use = df[df["usable"] == True]                        # noqa: E712
        width[arm] = {
            "cells_total": int(len(df)),
            "cells_excluded": int(df["excluded"].sum()),
            "cells_scored": int(len(use)),
            "width_rel_median": float(use["width_rel"].median()),
            "coverage95": float(use["covered"].mean()),
            "anchor_scale_max": float(use["anchor_scale_max"].max()),
            "by_horizon": {int(k): round(float(v), 3) for k, v in
                           use.groupby("horizon")["width_rel"]
                           .median().items()}}
        df.to_csv(OUT / f"covid_width_{arm}.csv", index=False)
        print(f"  {arm}: width {width[arm]['width_rel_median']:.3f} "
              f"coverage {width[arm]['coverage95']:.3f} "
              f"({width[arm]['cells_scored']} cells, "
              f"max anchor scale {width[arm]['anchor_scale_max']:.2f})")
    width["ratio_adaptive_over_control"] = (
        width["adaptive"]["width_rel_median"]
        / width["control"]["width_rel_median"])
    width["bar"] = WIDTH_BAR
    width["pass"] = bool(width["adaptive"]["width_rel_median"] <= WIDTH_BAR)
    width["headroom_used"] = float(width["adaptive"]["width_rel_median"]
                                   / WIDTH_BAR)
    print(f"  ratio adaptive/control {width['ratio_adaptive_over_control']:.3f}"
          f"; bar {WIDTH_BAR} -> "
          f"{'PASS' if width['pass'] else 'FAIL (KILL)'}")
    res["clause2_width"] = width

    # ---- clause 3: identifiability of sbeta ------------------------------
    print("\n=== CLAUSE 3: is the innovation scale identified? ===")
    pooled = []
    per_fit = []
    for c in arms_out["adaptive"]["cells"]:
        med, raw = posterior_medians(c)
        if raw is None:
            continue
        names, p = raw
        if "sbeta__FREE" not in names:
            continue
        col = p[:, names.index("sbeta__FREE")]
        pooled.append(col)
        per_fit.append({"state": c["state"], "asof": c["asof"], "rep": c["rep"],
                        "sbeta_median": float(np.median(col)),
                        "sbeta_q10": float(np.quantile(col, 0.10)),
                        "sbeta_q90": float(np.quantile(col, 0.90)),
                        "lo_frac": float(np.mean(col <= gate.SBETA_LO * 1.02)),
                        "hi_frac": float(np.mean(col >= gate.SBETA_HI * 0.98)),
                        **{k: round(v, 4) for k, v in med.items()}})
    allv = np.concatenate(pooled) if pooled else np.array([])
    lo_frac = float(np.mean(allv <= gate.SBETA_LO * (1 + BOUND_TOL)))
    hi_frac = float(np.mean(allv >= gate.SBETA_HI * (1 - BOUND_TOL)))
    ks = ks_vs_loguniform(allv, gate.SBETA_LO, gate.SBETA_HI)
    pinned = bool(max(lo_frac, hi_frac) >= PIN_BAR)
    shaped = bool(ks < KS_BAR)
    ident = {"pooled_draws": int(allv.size),
             "median": float(np.median(allv)) if allv.size else None,
             "frac_at_low_bound": lo_frac, "frac_at_high_bound": hi_frac,
             "ks_vs_prior": ks, "pin_bar": PIN_BAR, "ks_bar": KS_BAR,
             "pinned": pinned, "prior_shaped": shaped,
             "pass": bool(not pinned and not shaped), "per_fit": per_fit}
    print(f"  sbeta pooled median {ident['median']:.4f}; "
          f"at low bound {lo_frac*100:.1f}%, high bound {hi_frac*100:.1f}% "
          f"(pin bar {PIN_BAR*100:.0f}%); KS vs prior {ks:.3f} "
          f"(bar {KS_BAR}) -> {'PASS' if ident['pass'] else 'FAIL (KILL)'}")
    res["clause3_identified"] = ident

    # ---- clause 1: bimodality --------------------------------------------
    print("\n=== CLAUSE 1: bimodality (decided on the generative estimator) ===")
    arms = build_arms()
    rng = np.random.default_rng(20260823)
    bim = {"per_fit": []}
    for c in arms_out["adaptive"]["cells"]:
        med, raw = posterior_medians(c)
        if not med:
            continue
        p = _sim_params(med, arms["adaptive"])
        sb = float(med.get("sbeta__FREE", 0.0))
        sk = peaks_skeleton(p)
        sk_mine = peaks_generative(p, 0.0, ARPHI, rng)["median"]
        gen = peaks_generative(p, sb, ARPHI, rng)
        bim["per_fit"].append({
            "state": c["state"], "asof": c["asof"], "rep": c["rep"],
            "sbeta": round(sb, 4),
            "omega_wk": round(float(med.get("omega__FREE", np.nan)), 5),
            "eps1": round(float(med.get("eps1__FREE", np.nan)), 3),
            "Reff": round(float(med.get("Reff__FREE", np.nan)), 3),
            "skeleton": sk, "skeleton_own_integrator": sk_mine,
            "generative_median": gen["median"],
            "generative_frac_bimodal": gen["frac_bimodal"]})
    pf = pd.DataFrame(bim["per_fit"])
    if len(pf):
        # reduction guard: our integrator at sbeta = 0 must equal the
        # validated skeleton estimator
        d = (pf["skeleton_own_integrator"] - pf["skeleton"]).abs().max()
        bim["reduction_max_abs_diff"] = float(d)
        bim["reduction_ok"] = bool(d <= 0.01)
        print(f"  reduction guard (sbeta=0 == validated skeleton): "
              f"max abs diff {d:.4f} -> "
              f"{'OK' if bim['reduction_ok'] else 'BROKEN, clause VOID'}")
        bim["skeleton_median"] = float(pf["skeleton"].median())
        bim["skeleton_n_bimodal"] = int(
            (pf["skeleton"] >= BIMODAL_FIT_CRITERION).sum())
        # per (state, origin) fits, replicate-pooled by median
        byfit = pf.groupby(["state", "asof"])["generative_median"].median()
        bim["generative_median"] = float(byfit.median())
        bim["generative_n_bimodal"] = int(
            (byfit >= BIMODAL_FIT_CRITERION).sum())
        bim["n_fits"] = int(len(byfit))
        ok = (bim["reduction_ok"]
              and bim["generative_median"] >= BIMODAL_MEDIAN_BAR
              and bim["generative_n_bimodal"] >= BIMODAL_COUNT_BAR)
        bim["overflexible"] = bool(bim["generative_median"] > OVERFLEX_HI)
        bim["pass"] = bool(ok)
        print(f"  SKELETON   median {bim['skeleton_median']:.2f} peaks/yr, "
              f"{bim['skeleton_n_bimodal']} of {len(pf)} draws bimodal")
        print(f"  GENERATIVE median {bim['generative_median']:.2f} peaks/yr, "
              f"{bim['generative_n_bimodal']} of {bim['n_fits']} fits bimodal "
              f"-> {'PASS' if ok else 'FAIL (KILL)'}"
              + ("  [passes by OVER-FLEXIBILITY: above 3.5/yr against 2-3 "
                 "observed]" if bim["overflexible"] else ""))
        pf.to_csv(OUT / "covid_bimodality.csv", index=False)
    res["clause1_bimodality"] = bim

    kills = []
    if not bim.get("pass"):
        kills.append("clause 1, bimodality")
    if not width["pass"]:
        kills.append("clause 2, width above 4.06")
    if not ident["pass"]:
        kills.append("clause 3, innovation scale not identified")
    res["verdict"] = {"decision": "KILL" if kills else "PASS",
                      "kill_rules_fired": kills}
    print(f"\nCOVID VERDICT: {res['verdict']['decision']}")
    for k in kills:
        print(f"  KILL RULE FIRED: {k}")
    (OUT / "covid_result.json").write_text(json.dumps(res, indent=1))
    print(f"written: {OUT / 'covid_result.json'}")


if __name__ == "__main__":
    main()
