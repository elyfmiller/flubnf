"""Fit with `mult` profiled out instead of sampled.

WHAT AND WHY
------------
`mult` is an ascertainment fraction appearing ONLY in the observable
(`H_weekly = rho*mult*gamma*I`), never in a reaction rule. Its optimum is
therefore analytic, and sampling it buys nothing but a badly conditioned
posterior. Measured:

  * pinned `mult` -> forecast 6.74x too low, coverage 0.46
    unpinned       -> 2.15x too low, coverage 0.89;  corr(mult, residual) -0.459
    -- the strongest single association with the dominant error in this project
  * profiling it improves the Hessian condition number 402,219 -> 36,773 (10.9x)
    with fit and forecast statistically unchanged (p = 0.846)

It also matters that this lands BEFORE further sampler work: better-mixed chains
under-forecast MORE (corr(R-hat, residual) = -0.245), because a chain that
actually explores finds the low-`mult` arm of the ridge. Improving the sampler
without removing the ridge makes the symptom worse.

THE TWO-ROUND SHORTCUT
----------------------
True profiling recomputes `mult*` inside the objective at every proposal, which
needs a PyBNF change. This does it once up front on the in-Python mirror --
about 8 s against a ~14 min AMCMC fit, i.e. 0.9% overhead -- then fixes `mult`
in the materialised model so PyBNF samples 7 parameters instead of 8.

FALLBACK IS NOT OPTIONAL
------------------------
Fixing a wrong `mult` is worse than sampling it, because there is no posterior
left to reveal the error. `MultEstimate.needs_fallback()` sends a fit back to
the normal 8-parameter path when the mirror could not fit the state, or when the
analytic optimum exceeds 1.0 (>100% ascertainment, which means the FIXED `rho`
is too small for that state -- a different repair). Measured on 10 states: 8 fix,
2 fall back (Wyoming, fit error 0.98; Alaska, mult* = 1.34).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.profile_mult import estimate, fix_mult_in_model              # noqa: E402
from flubnf.sihrs_fit import (FITTED_PRIORS, materialize_model,          # noqa: E402
                              resolve_state, run_pybnf, write_conf, write_exp)

HUB = Path(os.environ.get("FLUSIGHT_HUB",
                          os.path.expanduser("~/Documents/GitHub/FluSight-forecast-hub")))
TRUTH = HUB / "target-data" / "target-hospital-admissions.csv"
LOCS = HUB / "auxiliary-data" / "locations.csv"
PYBNF = os.path.expanduser("~/.venvs/flubnf/bin/pybnf")
from flubnf.settings import BNG as _BNG
BNG = str(_BNG)
TEMPLATE = Path(__file__).resolve().parent.parent / "flubnf" / "templates" / "SIHRS_pop.bngl"


def _ess(x) -> float:
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 50 or x.std() == 0:
        return float("nan")
    y = x - x.mean()
    f = np.fft.rfft(y, 2 * n)
    ac = np.fft.irfft(f * np.conjugate(f))[:n].real
    ac /= ac[0]
    s = 0.0
    for k in range(1, n - 1, 2):
        p = ac[k] + ac[k + 1]
        if p < 0:
            break
        s += p
    return float(n / (1 + 2 * s))


def _rhat(chains) -> float:
    cs = [np.asarray(c, float) for c in chains]
    cs = [c[np.isfinite(c)] for c in cs]
    cs = [c for c in cs if len(c) > 20]
    if len(cs) < 2:
        return float("nan")
    n = min(len(c) for c in cs)
    cs = [c[-n:] for c in cs]
    W = float(np.mean([c.var(ddof=1) for c in cs]))
    if W <= 0:
        return float("nan")
    B = n * float(np.var([c.mean() for c in cs], ddof=1))
    return float(np.sqrt((((n - 1) / n) * W + B / n) / W))


def convergence(runs: Path) -> dict:
    pfs = sorted(runs.glob("params_*.txt"))
    chains = []
    for p in pfs:
        try:
            d = pd.read_csv(p, sep=r"\s+")
        except Exception:
            continue
        if len(d) > 40:
            chains.append(d.iloc[len(d) // 4:])
    if not chains:
        return {}
    out = {"n_chains": len(chains)}
    for col in chains[0].columns:
        arrs = [pd.to_numeric(ch[col], errors="coerce").dropna().to_numpy()
                for ch in chains]
        arrs = [a for a in arrs if a.size]
        if arrs:
            out[col] = {"ess": float(np.nansum([_ess(a) for a in arrs])),
                        "rhat": _rhat(arrs)}
    return out


def one_fit(args) -> dict:
    state, asof, workroot, season_start, iters, timeout = args
    tag = f"{asof}_{state.replace(' ', '_')}"
    ck = Path(workroot) / "parts" / f"{tag}.json"
    if ck.is_file():
        try:
            return json.loads(ck.read_text())
        except Exception:
            pass
    W = Path(workroot) / tag
    shutil.rmtree(W, ignore_errors=True)
    rec: dict = {"state": state, "asof": asof, "ok": False}
    try:
        s = resolve_state(state, truth_csv=TRUTH, locations_csv=LOCS,
                          season_start=season_start, as_of=asof)
        est = estimate(s)
        rec["mult_est"] = {"mult": est.mult, "raw": est.raw,
                           "clamped": est.clamped, "fit_err": est.fit_err,
                           "ok": est.ok}
        drop = not est.needs_fallback()
        rec["profiled"] = bool(drop)
        suffix = f"{state.replace(' ', '_')}_flu"
        m = materialize_model(s, TEMPLATE, W / "m.bngl", suffix)
        if drop:
            fix_mult_in_model(m, est.mult)
        e = write_exp(s, W / f"{suffix}.exp")
        # Reuse the production writer so this conf is byte-identical to the
        # sweep's except for the dropped `mult` line -- a hand-copied duplicate
        # silently drifted on backup_every and max_iterations when first written,
        # which would have confounded the whole comparison.
        c = write_conf(s, model=m, exp=e, out_dir=W / "res", conf_path=W / "c.conf",
                       bng_command=BNG, max_iterations=iters,
                       burn_in=max(50, iters // 4), adaptive=max(50, iters // 4),
                       drop_vars=("mult__FREE",) if drop else ())
        r = run_pybnf(c, pybnf_binary=PYBNF, cwd=W / "scratch", timeout_sec=timeout)
        rec["elapsed"] = r.get("elapsed", 0)
        if not r["ok"]:
            rec["reason"] = (r.get("reason") or r.get("stderr_tail", ""))[-250:]
        else:
            runs = W / "res" / "Results" / "A_MCMC" / "Runs"
            g = sorted(runs.glob("*traj_noise*"))
            if g:
                tr = np.genfromtxt(g[0])
                if tr.ndim == 1:
                    tr = tr.reshape(1, -1)
                if s.n_obs + 3 < tr.shape[1]:
                    rec["samples"] = {str(h): tr[:, s.n_obs - 1 + h].tolist()
                                      for h in (0, 1, 2, 3, 4)}
                    rec["last_observed"] = float(s.observed[-1])
                    rec["n_obs"] = int(s.n_obs)
                    try:
                        rec["convergence"] = convergence(runs)
                    except Exception:
                        rec["convergence"] = {}
                    pf = runs / "params_0.txt"
                    if pf.is_file():
                        P = pd.read_csv(pf, sep=r"\s+")
                        post = P.iloc[len(P) // 4:]
                        pin = []
                        for nm, (lo, hi) in FITTED_PRIORS.items():
                            if drop and nm == "mult__FREE":
                                continue
                            col = nm if nm in post.columns else nm.replace("__FREE", "")
                            if col not in post.columns:
                                continue
                            v = pd.to_numeric(post[col], errors="coerce").dropna().to_numpy()
                            if not v.size:
                                continue
                            w = hi - lo
                            if (np.mean(v <= lo + 0.02 * w) > 0.25
                                    or np.mean(v >= hi - 0.02 * w) > 0.25):
                                pin.append(nm)
                            rec[f"med_{col}"] = float(np.median(v))
                        rec["pinned"] = pin
                    if drop:
                        rec["med_mult__FREE"] = float(est.mult)
                    rec["ok"] = True
    except Exception as exc:
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:250]
    finally:
        shutil.rmtree(W, ignore_errors=True)
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(json.dumps(rec))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--asofs", nargs="+", required=True)
    ap.add_argument("--season-start", default="2025-08-01",
                    help="kept at Aug 1 to match the sweep this is compared against")
    ap.add_argument("--iters", type=int, default=8000)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=21600.0)
    ap.add_argument("--workroot", default="/tmp/profiled")
    ap.add_argument("--out", default="backtest_results/profiled_fit.json")
    a = ap.parse_args()

    jobs = [(s, d, a.workroot, a.season_start, a.iters, a.timeout)
            for d in a.asofs for s in a.states]
    print(f"[prof] {len(a.states)} states x {len(a.asofs)} dates = {len(jobs)} fits, "
          f"mult profiled, {a.jobs}-wide", flush=True)
    Path(a.workroot).mkdir(parents=True, exist_ok=True)
    out, t0, nprof = [], time.time(), 0
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one_fit, j): j for j in jobs}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                r = fu.result()
            except Exception as exc:
                r = {"ok": False, "reason": str(exc)[:150]}
            out.append(r)
            nprof += bool(r.get("profiled"))
            print(f"[{i}/{len(jobs)}] {r.get('asof')} {r.get('state')}: "
                  f"ok={r.get('ok')} profiled={r.get('profiled')} "
                  f"({(time.time()-t0)/60:.1f} min)", flush=True)
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(out))
    ok = sum(1 for r in out if r.get("ok"))
    print(f"[prof] done: {ok}/{len(out)} ok, {nprof} profiled / "
          f"{len(out)-nprof} fell back, {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
