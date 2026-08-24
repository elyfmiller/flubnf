"""Fit SIHRS with a calendar-conditioned Rt prior on Reff.

Design and justification: docs/RT_PRIOR_DESIGN.md
Pre-check: scripts/rt_prior_precheck.py (analogue band covers 93.5% of realised
Rt in 0.81 of width vs the flat box's 1.90 -- 2.3x more informative and better
centred, while SIHRS's own Rt posterior is 1.78, i.e. barely narrower than its
prior, so the likelihood has almost no information to push back with).

CHANGE ONE THING. Identical to the real-time vintage arm (relWIS 0.918) in every
respect -- same states, same dates, same vintage CSVs, same polar template, same
sampler settings -- except that

    uniform_var Reff__FREE 0.6 2.5

becomes a lognormal centred on the analogue's implied Rt for that epiweek,
estimated from STRICTLY PRIOR seasons.

SIGMA IS DELIBERATELY WIDENED. The analogue's own log-sd would be the maximum-
information choice, but the Reff-vs-Rt mapping neglects the seasonal and
depletion factors (see the design doc), so the prior is inflated by
SIGMA_INFLATE to avoid a confidently wrong prior fighting the data. A prior that
excludes the truth is worse than an uninformative one.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flubnf.analogue import build_bank, donor_ratios, epiweek, season_of  # noqa: E402
from flubnf.sihrs_fit import (FITTED_PRIORS, MIN_PRIORS, materialize_model,  # noqa: E402
                              resolve_state, run_pybnf, write_exp)
from scripts.profiled_fit_run import BNG, LOCS, PYBNF, TEMPLATE, TRUTH, convergence  # noqa: E402,E501
MIN_TEMPLATE = ROOT / 'flubnf' / 'templates' / 'SIHRS_pop_min.bngl'
from scripts.vintage_run import ARCHIVE, vintage_for                      # noqa: E402

GAMMA = 2.188
WIDEN = 1.3                    # for the Reff-vs-Rt approximation
HARD_LO, HARD_HI = 0.60, 2.50  # the original stiffness-safe box; never exceed
PHI_HALFWIDTH = 6.0            # +/- weeks around the analogue's seasonal peak
PHI_GATE_WEEKS = 20            # do NOT constrain phi1 before this many weeks into
                               # the season. Measured: the phi1 prior improves
                               # decline (0.661->0.538) and takeoff+peak
                               # (0.785->0.644) but DEGRADES early growth
                               # (1.055->1.143) -- before the peak there is no
                               # seasonal maximum to locate, so the constraint
                               # only imposes a shape the data contradicts.
_BANK = None
# NOT inherited by pool workers -- macOS spawns, so the worker re-imports this
# module and USE_MIN reverts to [False]. --min-model was silently ignored for an
# entire campaign, which ran the 8-parameter model while labelled 5-parameter.
# The flag now travels in the args tuple. This global is a default only.
USE_MIN = [False]


def bank():
    global _BANK
    if _BANK is None:
        t = pd.read_csv(TRUTH, dtype={"location": str})
        t["location"] = t["location"].str.zfill(2)
        t["date"] = pd.to_datetime(t.date)
        _BANK = build_bank(t.itertuples())
    return _BANK


def rt_prior(asof: str):
    """(lo, hi) for a NARROWED but BOUNDED uniform prior on Reff.

    A lognormal was tried first and was a mistake: it has unbounded support, so
    the sampler proposed Reff of 10-100, beta exploded, and CVODE ground to a
    halt -- three fits on a FIVE-point series ran 4.9h without finishing. The
    original `uniform_var 0.6 2.5` box exists partly as a stiffness guard
    (beta_max), and replacing it with an unbounded distribution removed that
    guard.

    A narrowed uniform keeps the hard bound AND delivers the measured benefit:
    the analogue's 95% band is 0.81 wide against the flat box's 1.90, i.e. the
    same 2.3x information gain, with no tail for the sampler to run off into.
    """
    T = pd.Timestamp(asof)
    # exclude_seasons=() on purpose: the 2021-22 donor exclusion adopted
    # 2026-08-24 was pre-registered and measured on the analogue's FORECAST,
    # not on this prior, and the sealed particle filter was fitted against the
    # unrestricted pool. Inheriting the exclusion here would silently change
    # the prior every future fit sees and make the seal's fitting path
    # unreproducible, for an effect nobody has measured. Revisit only with its
    # own pre-registration.
    g = donor_ratios(bank(), epiweek(T.date()), season_of(T.date()), 1,
                     bandwidth=2, exclude_seasons=())
    if g.size < 30:
        return None
    rt = 1.0 + np.log(g) / GAMMA
    rt = rt[np.isfinite(rt) & (rt > 0.05)]
    if rt.size < 30:
        return None
    lo = float(np.quantile(rt, 0.025))
    hi = float(np.quantile(rt, 0.975))
    # Widen slightly for the Reff-vs-Rt approximation (seasonal and depletion
    # factors are treated as ~1), then clamp inside the original stiffness-safe
    # box. Never widen beyond it.
    mid = 0.5 * (lo + hi)
    half = 0.5 * (hi - lo) * WIDEN
    lo, hi = mid - half, mid + half
    lo = max(lo, HARD_LO)
    hi = min(hi, HARD_HI)
    if hi - lo < 0.15:                 # never collapse to a spike
        mid = 0.5 * (lo + hi)
        lo, hi = max(mid - 0.075, HARD_LO), min(mid + 0.075, HARD_HI)
    return lo, hi



def seasonal_prior(season_start: str):
    """(eps1_lo, eps1_hi, phi1_lo, phi1_hi) from the analogue's pooled Rt curve.

    The analogue's implied Rt as a function of CALENDAR week is exactly what
    eps1/phi1 are supposed to encode, and it is estimated from four pooled
    seasons rather than the ~26 noisy points a single fit sees. Measured:
    Rt runs 0.90 in Jan-Feb up to 1.19 at epiweek 50, and a single harmonic fits
    at R^2 = 0.670 with eps1 ~ 0.095, peak at epiweek ~43.

    This matters most for phi1, whose current prior is 52 WEEKS WIDE and whose
    median R-hat is 58.8 -- the fit cannot locate a seasonal peak from one
    season, and has not been.

    PHASE OFFSET, which is the easy thing to get wrong: model time t is weeks
    since `season_start`, and beta peaks at t = phi1. The analogue speaks in
    EPIWEEKS. So phi1_model = (epiweek_peak - epiweek(season_start)) mod 52.
    """
    from scipy.optimize import curve_fit
    b = bank()
    ews, rts = [], []
    for ew in range(1, 53):
        # 9999 => all seasons usable. exclude_seasons=() for the same reason
        # as rt_prior above, and one more: the eps1/phi1 figures recorded in
        # this docstring were measured on the unrestricted pool, so applying
        # the 2021-22 exclusion here would make them unreproducible.
        g = donor_ratios(b, ew, 9999, 1, bandwidth=1, exclude_seasons=())
        if g.size < 40:
            continue
        rt = 1.0 + np.log(g) / GAMMA
        rt = rt[np.isfinite(rt)]
        if rt.size < 40:
            continue
        ews.append(ew); rts.append(float(np.median(rt)))
    if len(ews) < 20:
        return None
    ews = np.asarray(ews, float); rts = np.asarray(rts, float)

    def f(w, A, eps, phi):
        return A * np.exp(eps * np.cos(2 * np.pi * (w - phi) / 52))
    try:
        p, _ = curve_fit(f, ews, rts, p0=[1.0, 0.2, 43.0], maxfev=20000)
    except Exception:
        return None
    eps = abs(float(p[1]))
    phi_ew = float(p[2]) % 52.0
    ss = 1 - np.sum((rts - f(ews, *p)) ** 2) / np.sum((rts - rts.mean()) ** 2)
    if not np.isfinite(ss) or ss < 0.35:
        return None                      # curve too noisy to constrain anything

    ss_start = pd.Timestamp(season_start)
    phi_model = (phi_ew - epiweek(ss_start.date())) % 52.0

    # Bands, deliberately generous: R^2 is 0.670, not 0.95, and the harmonic is
    # an approximation to a curve with real extra structure (e.g. the week-52
    # holiday dip). Wide enough to contain the truth, narrow enough to matter.
    e_lo, e_hi = max(0.0, eps - 0.12), min(1.0, eps + 0.20)
    p_lo, p_hi = phi_model - PHI_HALFWIDTH, phi_model + PHI_HALFWIDTH
    return e_lo, e_hi, p_lo, p_hi


def write_conf_rt(setup, *, model, exp, out_dir, conf_path, iters, plo, phi,
                  seasonal=None, min_model=False):
    """The sweep's conf, with Reff's flat box replaced by a lognormal."""
    lines = [f"bng_command = {BNG}", f"model = {model} : {exp}",
             f"output_dir = {out_dir}", "fit_type = am",
             "objfunc = neg_bin_dynamic", ""]
    priors = MIN_PRIORS if min_model else FITTED_PRIORS
    for name, (lo, hi) in priors.items():
        if name == "Reff__FREE":
            lines.append(f"uniform_var = {name} {plo:.6f} {phi:.6f}")
            continue
        if seasonal is not None and name == "eps1__FREE":
            lines.append(f"uniform_var = {name} {seasonal[0]:.6f} {seasonal[1]:.6f}")
            continue
        if seasonal is not None and name == "phi1__FREE":
            lines.append(f"uniform_var = {name} {seasonal[2]:.6f} {seasonal[3]:.6f}")
            continue
        kw = ("loguniform_var" if name in ("mult__FREE", "impr__FREE", "r__FREE")
              and lo > 0 else "uniform_var")
        lines.append(f"{kw} = {name} {lo} {hi}")
    lines += ["", "population_size = 4", "parallel_count = 4",
              f"max_iterations = {iters}", f"burn_in = {max(50, iters//4)}",
              f"adaptive = {max(50, iters//4)}", "sample_every = 1",
              "backup_every = 100", "output_noise_trajectory = H_weekly",
              "continue_run = 0", "verbosity = 0"]
    p = Path(conf_path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n")
    return p


def one_fit(args) -> dict:
    (state, asof, workroot, season_start, iters, timeout,
     min_model) = args
    tag = f"{asof}_{state.replace(' ', '_')}"
    ck = Path(workroot) / "parts" / f"{tag}.json"
    if ck.is_file():
        try:
            return json.loads(ck.read_text())
        except Exception:
            pass
    W = Path(workroot) / tag
    shutil.rmtree(W, ignore_errors=True)
    rec: dict = {"state": state, "asof": asof, "ok": False, "arm": "rt_prior"}
    try:
        pr = rt_prior(asof)
        if pr is None:
            raise RuntimeError("no analogue donors for this epiweek")
        plo, phi = pr
        rec["prior_lo"], rec["prior_hi"] = plo, phi
        rec["prior_median_Reff"] = float(0.5 * (plo + phi))
        vf = vintage_for(asof)
        if vf is None:
            raise RuntimeError("no vintage for this as-of")
        s = resolve_state(state, truth_csv=vf, locations_csv=LOCS,
                          season_start=season_start, as_of=asof)
        suffix = f"{state.replace(' ', '_')}_flu"
        tmpl = MIN_TEMPLATE if min_model else TEMPLATE
        m = materialize_model(s, tmpl, W / "m.bngl", suffix)
        e = write_exp(s, W / f"{suffix}.exp")
        sp = seasonal_prior(season_start)
        weeks_in = (pd.Timestamp(asof) - pd.Timestamp(season_start)).days / 7.0
        if sp is not None and weeks_in < PHI_GATE_WEEKS:
            # keep the eps1 (amplitude) constraint, drop the phi1 (phase) one
            sp = (sp[0], sp[1], 0.0, 52.0)
            rec["phi_gated"] = True
        if sp is not None:
            rec["seasonal_prior"] = list(sp)
        rec["weeks_in_season"] = round(weeks_in, 1)
        c = write_conf_rt(s, model=m, exp=e, out_dir=W / "res",
                          conf_path=W / "c.conf", iters=iters, plo=plo, phi=phi,
                          seasonal=sp, min_model=min_model)
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
                        for nm in FITTED_PRIORS:
                            col = nm if nm in post.columns else nm.replace("__FREE", "")
                            if col in post.columns:
                                v = pd.to_numeric(post[col], errors="coerce").dropna()
                                if len(v):
                                    rec[f"med_{col}"] = float(np.median(v))
                    rec["ok"] = True
    except Exception as exc:
        rec.setdefault("reason", f"{type(exc).__name__}: {exc}"[:250])
    finally:
        shutil.rmtree(W, ignore_errors=True)
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(json.dumps(rec))
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", required=True)
    ap.add_argument("--asofs", nargs="+", required=True)
    ap.add_argument("--season-start", default="2025-08-01")
    ap.add_argument("--iters", type=int, default=8000)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=21600.0)
    ap.add_argument("--workroot", default="/tmp/rtprior")
    ap.add_argument("--out", default="backtest_results/rt_prior.json")
    ap.add_argument("--min-model", action="store_true",
                    help="use the 5-parameter SIHRS_pop_min.bngl template")
    a = ap.parse_args()
    USE_MIN[0] = bool(a.min_model)

    jobs = [(s, d, a.workroot, a.season_start, a.iters, a.timeout,
             bool(a.min_model))
            for d in a.asofs for s in a.states]
    print(f"[rt-prior] {len(a.states)} states x {len(a.asofs)} dates = {len(jobs)} "
          f"fits ({a.jobs}-wide). Control = the real-time vintage arm (0.918).",
          flush=True)
    for d in a.asofs[:4]:
        pr = rt_prior(d)
        if pr:
            print(f"    {d}: Reff box [{pr[0]:.3f}, {pr[1]:.3f}] "
                  f"(width {pr[1]-pr[0]:.2f} vs flat 1.90)", flush=True)
    Path(a.workroot).mkdir(parents=True, exist_ok=True)
    out, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one_fit, j): j for j in jobs}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                r = fu.result()
            except Exception as exc:
                r = {"ok": False, "reason": str(exc)[:150]}
            out.append(r)
            print(f"[{i}/{len(jobs)}] {r.get('asof')} {r.get('state')}: "
                  f"ok={r.get('ok')} ({(time.time()-t0)/60:.1f} min)", flush=True)
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(out))
    ok = sum(1 for r in out if r.get("ok"))
    print(f"[rt-prior] done: {ok}/{len(out)} ok, {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
