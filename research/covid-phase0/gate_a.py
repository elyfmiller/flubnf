"""GATE A -- COVID-19 SIHRS smoke fit. PRE-REGISTRATION, written before any fit.

Frozen 2026-08-22, before a single COVID fit was launched. Nothing below was
edited after seeing a result; the run log and the results JSON carry the file's
hash so that claim is checkable.

=============================================================================
1. WHAT IS BEING TESTED
=============================================================================
Whether the population-parameterized SIHRS, with `omega` freed and nothing else
changed, can be fitted to COVID-19 hospital admissions vintage-true without
producing a predictive distribution wider than the influenza reference.

The memo's classification says the mechanistic member "does not transfer as
configured", and names one cause (omega fixed) and one failure mode
(over-width). This gate tests the fix and measures the failure mode.

=============================================================================
2. THE MODEL, FROZEN
=============================================================================
Template   flubnf/templates/SIHRS_pop_covid.bngl
           Byte-identical to the production SIHRS_pop_min.bngl except for two
           code lines: `omega {{OMEGA}}` -> `omega omega__FREE`, and the
           simulate suffix. tests/test_profiles.py asserts exactly that.
Fitted (6) Reff, eps1, phi1, omega, mult, r.
           ONE added dimension over influenza's five. Justification for each:
             Reff  same box (0.60, 2.50) as influenza, unchanged. COVID
                   admissions grow more slowly week over week than influenza's,
                   so the ceiling is if anything more generous. NOT widened:
                   an unjustified widening buys posterior spread, which is the
                   named failure mode. If Reff pins high, that is the one
                   defensible change for a second round.
             eps1  same box (0.0, 1.0). Stiffness-critical; unchanged.
             phi1  uniform(0, 52). NO PEAK-WEEK PRIOR. phi1 is the week of peak
                   transmissibility and the epidemic peak LEADS it by a median
                   11.0 weeks under COVID waning (IQR -14.4 to -7.8). A
                   peak-week prior would be wrong by a season quarter.
             omega loguniform(0.01278, 0.12780) per week = 1.8 to 18 months of
                   mean protected duration. THE ADDED DIMENSION. Sourced from
                   two systematic reviews of protection against reinfection,
                   mapped through the SIHRS structure (fraction still protected
                   at t = exp(-omega t)):
                     Bobrovitz 2023 doi:10.1016/S1473-3099(22)00801-5,
                       24.7% at 12 months -> omega 0.0268/wk (8.6 months)
                     Lancet 2023 doi:10.1016/S0140-6736(22)02465-5,
                       36.1% at 40 weeks -> omega 0.0255/wk (9.0 months)
                   THE PRIOR IS WIDER THAN THE GATE WINDOW ON PURPOSE, so that
                   clause (1) is a test and not a tautology.
             mult  (0.002, 1.0), the physical bound. Unchanged.
             r     (0.1, 40.0). Unchanged.
           eps2/phi2 are NOT restored. The repertoire sweep puts the
           one-harmonic bimodal region at 20.4% of the realistic-amplitude
           space once omega is free; two more dimensions buy reachability that
           is already there and pay in width.
Fixed      gamma  = 7/6.84 per week. Omicron mean INTRINSIC generation time
                    6.84 d (95% CrI 5.72-8.60), Manica 2022
                    doi:10.1016/j.lanepe.2022.100446.
                    NOTE, AND THIS CONTRADICTS THE MEMO: the memo says "Omicron
                    generation time is close to influenza's, roughly 3 days ...
                    Source it." Sourced, 3 days is the REALIZED HOUSEHOLD
                    generation time (3.59 d) or the serial interval (2.38 d),
                    both depressed by within-household susceptible depletion.
                    The influenza value this mirrors (Chan 2024) is explicitly
                    INTRINSIC, so the like-for-like COVID number is 6.84 d. This
                    more than halves the modelled epidemic's intrinsic speed
                    relative to a 3-day assumption, and belongs on a
                    sensitivity arm.
           rho    = 0.005, first pass. Branching only; rho*mult is the
                    identified combination and mult is fitted.
           gammaH = 1.17, carried over. Does not enter the fit target.
           s0     = 0.85, carried over. A sensitivity axis for both diseases,
                    not a measurement, for the same immune-escape reason.
           attack rate 0.35 (midpoint of 0.20-0.50) as the rho*mult denominator.

=============================================================================
3. THE DATA, FROZEN
=============================================================================
Truth      CovidHub target-data/time-series.parquet, sliced by `as_of`.
           VINTAGE-TRUE: each fit sees only the snapshot published on its own
           as-of Wednesday, edge = the preceding Saturday.
Season     June boundary. season_start 2025-06-01, so the window carries BOTH
           the 2025 summer wave and the 2025-26 winter wave. That is the whole
           point: omega is not identifiable from one wave.
Origins    as-of 2026-01-07, 2026-02-04, 2026-03-04 (Wednesdays with archived
           vintages). Held-out horizons 1-4 are scored against settled truth.
           EXACTLY ONE cell per state straddles the March 2026 measurement
           break: horizon 4 from origin 2026-03-04 has anchor 2026-02-28 and
           target 2026-03-28. It is dropped by `DiseaseProfile.excluded_for`
           with its reason recorded, so 33 of 36 cells are scored. That cell is
           left in the design deliberately rather than designed around: it
           exercises the guard on live data, and a guard that is never
           triggered is a guard nobody has tested.
           The break is a level shift shared by COVID, influenza and RSV with
           the hospital-reporting count flat, verdict INSTRUMENT; see
           flubnf/reporting_breaks.py.
States     SELECTION RULE, fixed before fitting: the three largest jurisdictions
           by population whose 2025-06-01 window at as-of 2026-03-18 shows two
           or more distinct waves under the pre-registered wave definition
           (>= 6 weeks apart, each >= 40% of the window maximum, trough <= 75%
           of the smaller peak). Applying it: New York, Pennsylvania, North
           Carolina. Two-wave states are chosen deliberately -- a unimodal
           state cannot identify omega, so fitting one would be a weaker test
           dressed as an easier one.

=============================================================================
4. THE GATE, IN ORDER. WIDTH FIRST.
=============================================================================
(3) WIDTH -- evaluated first, because over-width is the named way this port
    fails. Central-95% interval width relative to the actual value,
    (q97.5 - q2.5) / actual, pooled over the held-out cells.
        PASS   <= 4.06, the influenza SIHRS figure.
        KILL   >  4.872, i.e. 4.06 by more than 20%.
        (4.06 to 4.872 is a FAIL-not-kill band: the port survives to a second
         round with a named change.)
(1) OMEGA. The posterior must concentrate INSIDE 3 to 12 months
    (omega 0.01916 to 0.07665 per week) and be OFF ITS BOUNDS.
        PASS   >= 80% of post-burn draws inside the window, AND < 5% of draws
               within 2% of either prior bound.
        KILL   pinned (>= 25% of draws within 2% of a bound) with no
               closed-form anchor available in one round.
(2) SAMPLER HEALTH. R-hat < 1.05 and ESS > 200 per chain, on every fitted
    parameter, split across chains after a 25% burn-in.

    PREDICTION, RECORDED BEFORE THE RUN SO IT CANNOT BE RETROFITTED: clause (2)
    will FAIL, and its failure will say nothing about COVID. The influenza
    SIHRS on this same sampler, at these same defaults, measures multi-chain
    R-hat 3.25 and ESS ~44 against bars of 1.01 and ~400 (recorded in
    sihrs_fit.write_conf's docstring, 2026-08-02, six states). The posterior has
    a condition number of ~1678 -- a long thin ridge -- which no
    isotropic-proposal adaptive-Metropolis sampler traverses. Adding a sixth
    dimension will not improve that. If clause (2) fails at roughly the
    influenza level it is a SAMPLER verdict, already known and already recorded;
    only a COVID-specific degradation (materially worse than the flu reference)
    would be a COVID finding. This is stated in advance precisely so that a
    failure here is not reported as a COVID result.

=============================================================================
5. WHAT WOULD FALSIFY THE WHOLE EXERCISE
=============================================================================
  * omega pinning at the LOW bound (18 months) would say the data want
    influenza-like waning and the memo's central finding is wrong for the
    fitted model, not only for the sweep.
  * omega pinning at the HIGH bound (1.8 months) would say omega is absorbing
    something else -- most likely the level non-stationarity the memo attributes
    to variant replacement -- and the parameter is not measuring waning.
  * Width above 4.872 kills the mechanistic member for COVID, per the memo.
  * A fit that fails to run at all (CVODE stiffness at the new gamma) is a
    template finding, reported as such and not as a skill result.

=============================================================================
6. WHAT THIS GATE CANNOT SETTLE
=============================================================================
No skill claim. relWIS against CovidHub-baseline is Gate B. Three states, three
origins, one season, 36 held-out cells: this is a smoke test of identifiability
and width, and the width figure carries wide uncertainty at this n. The flu
reference of 4.06 was measured on a far larger cell count, so the comparison is
one-sided evidence at best -- it can kill, it cannot bless.

=============================================================================
USAGE
=============================================================================
    .venv/bin/python research/covid-phase0/gate_a.py --smoke     # 1 state, fast
    .venv/bin/python research/covid-phase0/gate_a.py             # the gate
Results land in research/covid-phase0/out/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flubnf import covid_vintage as cv                              # noqa: E402
from flubnf.covid_fit import (materialize_for_profile, omega_to_months,   # noqa: E402
                              resolve_covid_state, write_exp,
                              write_profile_conf)
from flubnf.profiles import COVID, COVID_OMEGA_GATE                 # noqa: E402
from flubnf.settings import BNG, LOCATIONS                          # noqa: E402
from flubnf.sihrs_fit import run_pybnf                              # noqa: E402
from flubnf.unimodal_guard import all_peaks, count_waves            # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
PYBNF = os.path.expanduser("~/.venvs/flubnf/bin/pybnf")

SEASON_START = "2025-06-01"
SELECTION_ASOF = "2026-03-18"
ORIGINS = ("2026-01-07", "2026-02-04", "2026-03-04")
HORIZONS = (1, 2, 3, 4)

FLU_WIDTH_REFERENCE = 4.06
WIDTH_KILL = FLU_WIDTH_REFERENCE * 1.20
RHAT_BAR = 1.05
ESS_BAR = 200.0
OMEGA_INSIDE_BAR = 0.80
OMEGA_BOUND_TOL = 0.02
OMEGA_BOUND_BAR = 0.05
OMEGA_PIN_BAR = 0.25
#: The influenza reference for clause (2), so a failure can be read correctly.
FLU_SAMPLER_REFERENCE = {"rhat": 3.25, "ess_total": 44.0,
                         "source": "sihrs_fit.write_conf docstring, 2026-08-02"}


def preregistration_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# state selection -- the rule, applied
# ---------------------------------------------------------------------------

def select_states(n: int = 3) -> list:
    truth = cv.vintage_path(SELECTION_ASOF)
    locs = pd.read_csv(LOCATIONS, dtype={"location": str})
    locs = locs[locs.abbreviation != "US"].sort_values("population",
                                                       ascending=False)
    out = []
    for name in locs.location_name:
        try:
            s = resolve_covid_state(name, truth_csv=truth,
                                    locations_csv=LOCATIONS,
                                    season_start=SEASON_START,
                                    as_of=SELECTION_ASOF)
        except Exception:
            continue
        if count_waves(s.observed) >= 2:
            out.append(name)
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------

def _ess(x) -> float:
    """Initial-positive-sequence effective sample size (Geyer). Same estimator
    scripts/profiled_fit_run.py uses, so the numbers are comparable."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
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


def read_chains(runs: Path, burn_frac: float = 0.25) -> dict:
    """{param: [chain arrays]} from PyBNF's per-chain params_*.txt."""
    out: dict = {}
    for p in sorted(runs.glob("params_*.txt")):
        try:
            d = pd.read_csv(p, sep=r"\s+")
        except Exception:
            continue
        if len(d) <= 40:
            continue
        d = d.iloc[int(len(d) * burn_frac):]
        for col in d.columns:
            v = pd.to_numeric(d[col], errors="coerce").dropna().to_numpy()
            if v.size:
                out.setdefault(col, []).append(v)
    return out


def convergence(chains: dict) -> dict:
    out = {}
    for col, arrs in chains.items():
        per = [_ess(a) for a in arrs]
        out[col] = {"n_chains": len(arrs),
                    "rhat": _rhat(arrs),
                    "ess_per_chain_min": float(np.nanmin(per)) if per else float("nan"),
                    "ess_per_chain_median": float(np.nanmedian(per)) if per else float("nan"),
                    "ess_total": float(np.nansum(per)) if per else float("nan")}
    return out


def omega_summary(chains: dict) -> dict:
    arrs = chains.get("omega__FREE") or chains.get("omega")
    if not arrs:
        return {"available": False}
    v = np.concatenate(arrs)
    v = v[np.isfinite(v)]
    lo, hi = COVID.fitted_priors["omega__FREE"]
    glo, ghi = COVID_OMEGA_GATE
    w = hi - lo
    q = np.percentile(v, [2.5, 25, 50, 75, 97.5])
    return {"available": True, "n_draws": int(v.size),
            "median": float(np.median(v)),
            "q": {"2.5": float(q[0]), "25": float(q[1]), "50": float(q[2]),
                  "75": float(q[3]), "97.5": float(q[4])},
            "median_months": omega_to_months(float(np.median(v))),
            "months_q": {"2.5": omega_to_months(float(q[4])),
                         "50": omega_to_months(float(q[2])),
                         "97.5": omega_to_months(float(q[0]))},
            "frac_inside_gate": float(np.mean((v >= glo) & (v <= ghi))),
            "frac_at_low_bound": float(np.mean(v <= lo + OMEGA_BOUND_TOL * w)),
            "frac_at_high_bound": float(np.mean(v >= hi - OMEGA_BOUND_TOL * w))}


# ---------------------------------------------------------------------------
# one fit
# ---------------------------------------------------------------------------

def one_fit(args) -> dict:
    state, asof, iters, timeout, keep = args
    tag = f"{state.replace(' ', '_')}_{asof}"
    part = OUT / "parts" / f"{tag}.json"
    if part.is_file():
        try:
            return json.loads(part.read_text())
        except Exception:
            pass
    W = OUT / "work" / tag
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    rec: dict = {"state": state, "asof": asof, "ok": False, "iters": iters}
    try:
        truth = cv.vintage_path(asof)
        s = resolve_covid_state(state, truth_csv=truth, locations_csv=LOCATIONS,
                                season_start=SEASON_START, as_of=asof)
        # contiguity: traj columns index the SIMULATION grid, so a gap would
        # make column n-1+h the wrong week. COVID hub data has no gaps; assert.
        assert int(s.times[-1]) == s.n_obs - 1, "missing weeks: fix traj indexing"
        rec.update({"n_obs": int(s.n_obs), "waves": int(count_waves(s.observed)),
                    "last_observed": float(s.observed[-1]),
                    "data_edge": cv.data_edge(asof),
                    "peaks": [[int(p.index), float(p.value)]
                              for p in all_peaks(s.observed)]})
        sfx = f"{state.replace(' ', '_')}_covid"
        t_end = int(s.n_obs) + 8
        m = materialize_for_profile(COVID, s, W / "m.bngl", suffix=sfx,
                                    t_end=t_end)
        e = write_exp(s, W / f"{sfx}.exp")
        c = write_profile_conf(COVID, s, model=m, exp=e, out_dir=W / "res",
                               conf_path=W / "c.conf", bng_command=str(BNG),
                               max_iterations=iters,
                               burn_in=max(50, iters // 4),
                               adaptive=max(50, iters // 4),
                               population_size=4)
        r = run_pybnf(c, pybnf_binary=PYBNF, cwd=W / "scratch",
                      timeout_sec=timeout)
        rec["elapsed"] = r.get("elapsed", 0.0)
        if not r["ok"]:
            rec["reason"] = (r.get("reason") or r.get("stderr_tail", ""))[-400:]
        else:
            runs = W / "res" / "Results" / "A_MCMC" / "Runs"
            ch = read_chains(runs)
            rec["convergence"] = convergence(ch)
            rec["omega"] = omega_summary(ch)
            rec["medians"] = {k: float(np.median(np.concatenate(v)))
                              for k, v in ch.items()}
            g = sorted(runs.glob("*traj_noise*"))
            if g:
                tr = np.genfromtxt(g[0])
                if tr.ndim == 1:
                    tr = tr.reshape(1, -1)
                n = int(s.n_obs)
                if n - 1 + max(HORIZONS) < tr.shape[1]:
                    rec["samples"] = {str(h): tr[:, n - 1 + h].tolist()
                                      for h in (0,) + HORIZONS}
                    rec["ok"] = True
                else:
                    rec["reason"] = (f"traj has {tr.shape[1]} columns, need "
                                     f"{n + max(HORIZONS)}")
            else:
                rec["reason"] = "no traj_noise output"
    except Exception as exc:
        rec["reason"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        if not keep:
            shutil.rmtree(W, ignore_errors=True)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_text(json.dumps(rec))
    return rec


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def settled_truth() -> pd.DataFrame:
    return cv.vintage_frame(cv.vintages()[-1])


def width_cells(records: list) -> pd.DataFrame:
    """(q97.5 - q2.5) / actual for every held-out cell, with the exclusion
    guard applied. A cell that straddles the March 2026 break is dropped with
    its reason recorded, never silently."""
    truth = settled_truth()
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    rows = []
    for rec in records:
        if not rec.get("ok"):
            continue
        anchor = rec["data_edge"]
        for h in HORIZONS:
            target = str((pd.Timestamp(anchor) + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(anchor, target)
            actual = tmap.get((rec["state"], target))
            v = np.asarray(rec["samples"][str(h)], float)
            v = v[np.isfinite(v)]
            if actual is None or actual <= 0 or v.size < 20:
                rows.append({"state": rec["state"], "asof": rec["asof"],
                             "horizon": h, "target": target, "actual": actual,
                             "excluded": bool(excl), "usable": False})
                continue
            lo, hi = np.percentile(v, [2.5, 97.5])
            rows.append({"state": rec["state"], "asof": rec["asof"],
                         "horizon": h, "target": target, "actual": actual,
                         "median": float(np.median(v)),
                         "q025": float(lo), "q975": float(hi),
                         "width_rel": float((hi - lo) / actual),
                         "excluded": bool(excl),
                         "exclusion_reason": (excl.reason if excl else None),
                         "usable": not excl})
    return pd.DataFrame(rows)


def gate_table(records: list, cells: pd.DataFrame) -> dict:
    ok = [r for r in records if r.get("ok")]
    use = cells[cells["usable"] & cells["width_rel"].notna()] \
        if len(cells) else cells

    # (3) WIDTH -- first
    width = float(use["width_rel"].median()) if len(use) else float("nan")
    width_mean = float(use["width_rel"].mean()) if len(use) else float("nan")
    if not np.isfinite(width):
        w_verdict = "NO DATA"
    elif width <= FLU_WIDTH_REFERENCE:
        w_verdict = "PASS"
    elif width > WIDTH_KILL:
        w_verdict = "KILL"
    else:
        w_verdict = "FAIL (not kill)"

    # (1) OMEGA
    om = [r["omega"] for r in ok if r.get("omega", {}).get("available")]
    if om:
        inside = float(np.mean([o["frac_inside_gate"] for o in om]))
        at_lo = float(np.max([o["frac_at_low_bound"] for o in om]))
        at_hi = float(np.max([o["frac_at_high_bound"] for o in om]))
        med = float(np.median([o["median"] for o in om]))
        pinned = max(at_lo, at_hi) >= OMEGA_PIN_BAR
        o_verdict = ("KILL (pinned)" if pinned else
                     "PASS" if (inside >= OMEGA_INSIDE_BAR
                                and max(at_lo, at_hi) < OMEGA_BOUND_BAR)
                     else "FAIL")
    else:
        inside = at_lo = at_hi = med = float("nan")
        o_verdict = "NO DATA"

    # (2) SAMPLER
    rhats, ess = [], []
    for r in ok:
        for col, d in (r.get("convergence") or {}).items():
            if np.isfinite(d.get("rhat", np.nan)):
                rhats.append(d["rhat"])
            if np.isfinite(d.get("ess_per_chain_min", np.nan)):
                ess.append(d["ess_per_chain_min"])
    rhat_max = float(np.nanmax(rhats)) if rhats else float("nan")
    rhat_med = float(np.nanmedian(rhats)) if rhats else float("nan")
    ess_min = float(np.nanmin(ess)) if ess else float("nan")
    ess_med = float(np.nanmedian(ess)) if ess else float("nan")
    s_verdict = ("NO DATA" if not rhats else
                 "PASS" if (rhat_max < RHAT_BAR and ess_min > ESS_BAR)
                 else "FAIL")

    return {
        "preregistration_sha256_16": preregistration_hash(),
        "fits_attempted": len(records), "fits_ok": len(ok),
        "cells_total": int(len(cells)),
        "cells_excluded_by_break": int(cells["excluded"].sum()) if len(cells) else 0,
        "cells_scored": int(len(use)),
        "gate": {
            "3_width_first": {
                "metric": "median central-95% width / actual, held-out",
                "value": width, "mean": width_mean,
                "bar_pass": FLU_WIDTH_REFERENCE, "bar_kill": WIDTH_KILL,
                "verdict": w_verdict,
                "by_horizon": (use.groupby("horizon")["width_rel"].median()
                               .round(3).to_dict() if len(use) else {})},
            "1_omega": {
                "median_per_week": med,
                "median_months": omega_to_months(med) if np.isfinite(med) else float("nan"),
                "frac_inside_3_to_12_months": inside,
                "bar_inside": OMEGA_INSIDE_BAR,
                "max_frac_at_low_bound": at_lo, "max_frac_at_high_bound": at_hi,
                "bar_at_bound": OMEGA_BOUND_BAR, "bar_pinned": OMEGA_PIN_BAR,
                "verdict": o_verdict},
            "2_sampler": {
                "rhat_max": rhat_max, "rhat_median": rhat_med, "bar": RHAT_BAR,
                "ess_per_chain_min": ess_min, "ess_per_chain_median": ess_med,
                "bar_ess": ESS_BAR, "verdict": s_verdict,
                "influenza_reference": FLU_SAMPLER_REFERENCE,
                "note": ("clause (2) was PRE-REGISTERED as expected to fail; a "
                         "failure at roughly the influenza reference is a "
                         "sampler verdict, not a COVID one")},
        },
    }


def bimodality_check(records: list) -> dict:
    """Does the FITTED model put two epidemics in a year, as the data do?

    The gate is about identifiability and width, but the whole reason omega was
    freed is bimodality, so it is measured rather than assumed. Each fit's
    posterior-median parameter set is integrated for three years past the fit
    window and the waves in the final year are counted.

    Integrated in the POPULATION form (N passed, s0 = 0.85, R0 = Reff/s0) so the
    dynamics match the fitted BNGL rather than the S(0)=1 normalization, and
    with impr = 0 because the min template carries no importation reaction.
    Reading the FINAL year of four means the initial condition has washed out,
    so this reports the model's asymptotic annual pattern, which is the quantity
    the repertoire sweep classified.
    """
    from flubnf.simulate_sihrs import simulate_sihrs
    out = []
    s0 = COVID.fixed.s0_default
    for r in records:
        if not r.get("ok"):
            continue
        m = r.get("medians") or {}

        def g(k, d=None):
            return float(m.get(k + "__FREE", m.get(k, d)))
        try:
            p = dict(N=1.0e7, s0=s0, i0=1.0e-4,
                     R0=g("Reff") / s0, eps1=g("eps1"), phi1=g("phi1"),
                     eps2=0.0, phi2=0.0, gamma=COVID.fixed.gamma_per_week,
                     rho=COVID.fixed.rho, gammaH=COVID.fixed.gammaH_per_week,
                     omega=g("omega"), mult=g("mult"), impr=0.0)
            res = simulate_sihrs(p, n_weeks=52 * 4)
            hw = np.asarray(res.H_weekly, float)[-52:]
            waves = count_waves(hw)
            peaks = all_peaks(hw)
        except Exception as exc:
            out.append({"state": r["state"], "asof": r["asof"],
                        "error": f"{type(exc).__name__}: {exc}"[:160]})
            continue
        out.append({"state": r["state"], "asof": r["asof"],
                    "omega_median": g("omega"),
                    "omega_months": omega_to_months(g("omega")),
                    "eps1": g("eps1"), "phi1": g("phi1"),
                    "observed_waves_in_window": r.get("waves"),
                    "simulated_waves_final_year": int(waves),
                    "simulated_peak_weeks": [int(p_.index) for p_ in peaks]})
    n = [o for o in out if "simulated_waves_final_year" in o]
    return {"per_fit": out,
            "fraction_bimodal": (float(np.mean([o["simulated_waves_final_year"] >= 2
                                                for o in n])) if n else float("nan"))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="one state, one origin, few iterations")
    ap.add_argument("--iters", type=int, default=20000)
    ap.add_argument("--timeout", type=float, default=10800.0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    states = select_states(1 if a.smoke else 3)
    origins = ORIGINS[-1:] if a.smoke else ORIGINS
    iters = 400 if a.smoke else a.iters
    print(f"pre-registration {preregistration_hash()}")
    print(f"states {states}  origins {list(origins)}  iters {iters}")

    jobs = [(s, o, iters, a.timeout, a.keep) for s in states for o in origins]
    t0 = time.time()
    if a.workers <= 1 or len(jobs) == 1:
        records = [one_fit(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            records = list(ex.map(one_fit, jobs))
    print(f"{len(jobs)} fits in {time.time() - t0:.0f}s; "
          f"ok {sum(r.get('ok', False) for r in records)}")

    cells = width_cells(records)
    table = gate_table(records, cells)
    bim = bimodality_check(records)
    (OUT / "gate_a_records.json").write_text(json.dumps(records))
    cells.to_csv(OUT / "gate_a_cells.csv", index=False)
    (OUT / "gate_a_result.json").write_text(
        json.dumps({"table": table, "bimodality": bim,
                    "states": states, "origins": list(origins),
                    "season_start": SEASON_START, "iters": iters}, indent=2))
    print(json.dumps(table, indent=2))
    print(json.dumps(bim.get("per_fit", []), indent=2))


if __name__ == "__main__":
    main()
