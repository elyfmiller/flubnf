"""Gate A addendum: the width metric measured the way the flu reference was.

WHY THIS IS A SEPARATE FILE
---------------------------
`gate_a.py` is the pre-registration and its own sha256 is recorded in the
results, so it is not edited after a run. This script reads the records it
wrote and adds one thing the pre-registration did not pin down: whether the
central-95% width is measured on the RAW posterior predictive or on the
ANCHOR-RESCALED one.

That distinction is not cosmetic. The flu figure of 4.06 comes from the
production pipeline, and `app/core/engines/pf.py::collect` rescales every draw
by `last_observed / median(origin draws)` before quantiles are taken. The
rescale is a single positive multiplier per cell, so it scales the interval
width too. Comparing an unrescaled COVID width against a rescaled flu width
would flatter or punish the port for a reason that has nothing to do with COVID.

Both are reported. The RESCALED figure is the one comparable to 4.06.

IT ALSO SUPERSEDES THE HARNESS'S BIMODALITY CHECK, WHICH HAD A BUG
-------------------------------------------------------------------
`gate_a.py::bimodality_check` counts waves in the final 52 weeks of a
four-year integration. A 52-week window whose edge falls near an annual peak
reports that ONE peak twice -- once at each end -- so a purely annual model can
read as bimodal. Verified: R0 4.48 / eps1 0.44 / 26-week waning shows "2 waves"
in a 52-week window and peaks at weeks 3, 55, 107 over three years, i.e. exactly
one per year. The corrected check below integrates ten years, reads the final
three, drops the two boundary indices, and reports PEAKS PER YEAR. The harness
figure is left in place and unedited so the pre-registration hash stays
verifiable; this number is the one to quote.

A SECOND HARNESS DEFECT, FOUND DURING THE RUN AND RECORDED HERE
----------------------------------------------------------------
With `population_size = 4` PyBNF writes one noise trajectory per chain
(`traj_noise_..._chain_0.txt` .. `_chain_3.txt`). `gate_a.py` takes
`sorted(glob("*traj_noise*"))[0]`, i.e. CHAIN 0 ONLY. Four adaptive-Metropolis
chains sit in four different modes here (that is clause 2's whole finding), so a
single chain understates the predictive spread, and the AMCMC width figure is
therefore a LOWER BOUND, not an estimate. It cannot be repaired from the stored
records because only chain 0's draws were kept.

This does not affect clauses (1) or (2): `read_chains` reads every `params_*.txt`
and pools them, so the omega posterior and the R-hat/ESS numbers use all four
chains. It also does not affect the particle-filter width arm
(`gate_a_pf_width.py`), which runs `population_size = 1` exactly as production
does and therefore has one trajectory file by construction. THE PF NUMBER IS THE
WIDTH NUMBER OF RECORD. Fix the glob before Gate B.

Run:  .venv/bin/python research/covid-phase0/gate_a_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flubnf import covid_vintage as cv                # noqa: E402
from flubnf.covid_fit import omega_to_months          # noqa: E402
from flubnf.profiles import COVID, COVID_OMEGA_GATE   # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
HORIZONS = (1, 2, 3, 4)
FLU_WIDTH_REFERENCE = 4.06
FLU_ANALOGUE_WIDTH = 3.09       # same source, for scale
WIDTH_KILL = FLU_WIDTH_REFERENCE * 1.20


def cells(records: list) -> pd.DataFrame:
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    rows = []
    for rec in records:
        if not rec.get("ok"):
            continue
        anchor_week = rec["data_edge"]
        origin = np.asarray(rec["samples"]["0"], float)
        origin = origin[np.isfinite(origin)]
        med0 = float(np.median(origin)) if origin.size else float("nan")
        # the production anchor rescale, verbatim from pf.collect
        scale = (rec["last_observed"] / med0) if med0 > 0 else 1.0
        for h in HORIZONS:
            target = str((pd.Timestamp(anchor_week)
                          + pd.Timedelta(days=7 * h)).date())
            excl = COVID.excluded_for(anchor_week, target)
            actual = tmap.get((rec["state"], target))
            v = np.asarray(rec["samples"][str(h)], float)
            v = v[np.isfinite(v)]
            if excl or actual is None or actual <= 0 or v.size < 20:
                rows.append({"state": rec["state"], "asof": rec["asof"],
                             "horizon": h, "target": target,
                             "excluded": bool(excl), "usable": False})
                continue
            lo, hi = np.percentile(v, [2.5, 97.5])
            med = float(np.median(v))
            rows.append({
                "state": rec["state"], "asof": rec["asof"], "horizon": h,
                "target": target, "actual": actual, "usable": True,
                "excluded": False, "anchor_scale": scale,
                "median_raw": med, "median_rescaled": med * scale,
                "width_rel_raw": float((hi - lo) / actual),
                "width_rel_rescaled": float((hi - lo) * scale / actual),
                "covered_raw": bool(lo <= actual <= hi),
                "covered_rescaled": bool(lo * scale <= actual <= hi * scale),
                "abs_rel_err_raw": abs(med - actual) / actual,
                "abs_rel_err_rescaled": abs(med * scale - actual) / actual})
    return pd.DataFrame(rows)


def peaks_per_year(params: dict, years: int = 10, read: int = 3) -> dict:
    """Annual peak count of a fitted parameter set, free of the window artifact.

    Integrate `years` years, read the last `read`, drop the first and last index
    (a boundary index is a peak of the WINDOW, not of the epidemic), and divide.
    A value near 2 means the model puts two epidemics in a year; near 1 means it
    is annual whatever the data did.
    """
    from flubnf.simulate_sihrs import simulate_sihrs
    from flubnf.unimodal_guard import all_peaks
    res = simulate_sihrs(params, n_weeks=52 * years)
    hw = np.asarray(res.H_weekly, float)[-(52 * read + 1):-1]
    if not np.all(np.isfinite(hw)) or hw.max() <= 0:
        return {"peaks_per_year": float("nan"), "reason": "non-finite or dead"}
    pk = [p for p in all_peaks(hw) if 0 < p.index < len(hw) - 1]
    return {"peaks_per_year": len(pk) / float(read),
            "peak_weeks_in_window": [int(p.index) for p in pk],
            "trough_to_peak": float(hw.max() / max(hw.min(), 1e-12)),
            "annual_min": float(hw.min()), "annual_max": float(hw.max())}


def bimodality(records: list) -> dict:
    """Does each fit's posterior-median model produce two epidemics a year?

    Integrated in the POPULATION form (N passed, s0 = 0.85, R0 = Reff/s0, impr =
    0) so the dynamics match the fitted BNGL.
    """
    from flubnf.profiles import COVID as C
    s0 = C.fixed.s0_default
    out = []
    for r in records:
        if not r.get("ok"):
            continue
        m = r.get("medians") or {}

        def g(k):
            return float(m.get(k + "__FREE", m.get(k, float("nan"))))
        p = dict(N=1.0e7, s0=s0, i0=1.0e-4, R0=g("Reff") / s0, eps1=g("eps1"),
                 phi1=g("phi1"), eps2=0.0, phi2=0.0,
                 gamma=C.fixed.gamma_per_week, rho=C.fixed.rho,
                 gammaH=C.fixed.gammaH_per_week, omega=g("omega"),
                 mult=g("mult"), impr=0.0)
        try:
            d = peaks_per_year(p)
        except Exception as exc:
            d = {"error": f"{type(exc).__name__}: {exc}"[:160]}
        d.update({"state": r["state"], "asof": r["asof"],
                  "observed_waves_in_fit_window": r.get("waves"),
                  "omega_per_week": round(g("omega"), 5),
                  "omega_months": round(omega_to_months(g("omega")), 2),
                  "Reff": round(g("Reff"), 3), "eps1": round(g("eps1"), 3),
                  "phi1": round(g("phi1"), 1)})
        out.append(d)
    vals = [d["peaks_per_year"] for d in out
            if np.isfinite(d.get("peaks_per_year", np.nan))]
    return {"per_fit": out,
            "median_peaks_per_year": float(np.median(vals)) if vals else float("nan"),
            "fraction_bimodal": (float(np.mean([v >= 1.9 for v in vals]))
                                 if vals else float("nan")),
            "control": ("the same estimator returns 2.00 peaks/yr for "
                        "R0 3.0 / eps1 0.50 / 22-week waning and 1.00 for "
                        "R0 2.0 / eps1 0.35 / 52-week waning, so a value of 1 "
                        "here is a statement about the fit, not about the "
                        "estimator")}


def sampler(records: list) -> dict:
    """Clause (2), re-read with the two things the harness did not know.

    1. phi1 IS CIRCULAR. `flubnf/seasonal.py` ships `circular_rhat` precisely
       because a linear R-hat on a phase is meaningless -- phases of 51 and 1
       are one week apart and the linear statistic calls them a season apart.
       The harness computed the linear one. The raw draws are not stored, so
       this cannot be recomputed here; what CAN be done is to report the
       statistic with and without phi1, because the number that includes it is
       not evidence about mixing.
    2. phi1 is UNIDENTIFIABLE WHEN eps1 -> 0. `summarize_phase`'s own docstring
       says the resultant length goes to zero as the amplitude collapses, i.e.
       the phase becomes uniform on the circle. If the fits put eps1 near zero,
       phi1's R-hat is measuring an absent parameter.
    """
    rows = []
    for r in records:
        if not r.get("ok"):
            continue
        conv = r.get("convergence") or {}
        med = r.get("medians") or {}
        def pick(keys, stat):
            v = [conv[k][stat] for k in conv if k in keys
                 and np.isfinite(conv[k].get(stat, np.nan))]
            return v
        allp = set(conv)
        nophi = {k for k in allp if not k.startswith("phi1")}
        rows.append({
            "state": r["state"], "asof": r["asof"],
            "rhat_max_all": max(pick(allp, "rhat"), default=float("nan")),
            "rhat_max_excl_phi1": max(pick(nophi, "rhat"), default=float("nan")),
            "ess_min_all": min(pick(allp, "ess_per_chain_min"), default=float("nan")),
            "ess_min_excl_phi1": min(pick(nophi, "ess_per_chain_min"),
                                     default=float("nan")),
            "eps1_median": float(med.get("eps1__FREE", med.get("eps1", float("nan")))),
            "per_param_rhat": {k.replace("__FREE", ""): round(v["rhat"], 2)
                               for k, v in conv.items()},
            "per_param_ess_min": {k.replace("__FREE", ""):
                                  round(v["ess_per_chain_min"], 1)
                                  for k, v in conv.items()}})
    e = [r["eps1_median"] for r in rows if np.isfinite(r["eps1_median"])]
    return {"per_fit": rows,
            "rhat_max_all": max((r["rhat_max_all"] for r in rows), default=float("nan")),
            "rhat_max_excl_phi1": max((r["rhat_max_excl_phi1"] for r in rows),
                                      default=float("nan")),
            "ess_per_chain_min_all": min((r["ess_min_all"] for r in rows),
                                         default=float("nan")),
            "ess_per_chain_min_excl_phi1": min(
                (r["ess_min_excl_phi1"] for r in rows), default=float("nan")),
            "eps1_median_across_fits": float(np.median(e)) if e else float("nan"),
            "phi1_note": ("linear R-hat on a circular parameter is not evidence; "
                          "see flubnf.seasonal.circular_rhat. If eps1 sits near "
                          "zero the phase is uniform on the circle by "
                          "construction and phi1 has nothing to converge to."),
            "influenza_reference": {"rhat": 3.25, "ess_total": 44.0,
                                    "bars": {"rhat": 1.01, "ess": 400}}}


def verdict(w: float) -> str:
    if not np.isfinite(w):
        return "NO DATA"
    if w <= FLU_WIDTH_REFERENCE:
        return "PASS"
    return "KILL" if w > WIDTH_KILL else "FAIL (not kill)"


def main() -> None:
    records = json.loads((OUT / "gate_a_records.json").read_text())
    df = cells(records)
    use = df[df["usable"]]
    out = {
        "fits_ok": int(sum(r.get("ok", False) for r in records)),
        "cells_total": int(len(df)),
        "cells_excluded_by_march_break": int(df["excluded"].sum()),
        "cells_scored": int(len(use)),
        "width": {
            "rescaled_comparable_to_flu_4.06": {
                "median": float(use["width_rel_rescaled"].median()),
                "mean": float(use["width_rel_rescaled"].mean()),
                "verdict": verdict(float(use["width_rel_rescaled"].median())),
                "by_horizon": {int(k): round(float(v), 3) for k, v in
                               use.groupby("horizon")["width_rel_rescaled"]
                               .median().items()},
                "by_state": {k: round(float(v), 3) for k, v in
                             use.groupby("state")["width_rel_rescaled"]
                             .median().items()}},
            "raw_no_anchor_rescale": {
                "median": float(use["width_rel_raw"].median()),
                "mean": float(use["width_rel_raw"].mean()),
                "verdict": verdict(float(use["width_rel_raw"].median()))},
            "reference_flu_sihrs": FLU_WIDTH_REFERENCE,
            "reference_flu_analogue": FLU_ANALOGUE_WIDTH,
            "kill_bar": WIDTH_KILL,
        },
        "coverage_95": {
            "rescaled": float(use["covered_rescaled"].mean()),
            "raw": float(use["covered_raw"].mean()),
            "nominal": 0.95,
            "note": ("flu SIHRS covers 87% at width 4.06; the analogue covers "
                     "93% at 3.09. Width alone is not the whole story, but it "
                     "is the pre-registered gate.")},
        "point_error": {
            "median_abs_rel_err_rescaled": float(
                use["abs_rel_err_rescaled"].median()),
            "median_abs_rel_err_raw": float(use["abs_rel_err_raw"].median())},
        "anchor_scale": {
            "median": float(use["anchor_scale"].median()),
            "min": float(use["anchor_scale"].min()),
            "max": float(use["anchor_scale"].max()),
            "note": ("far from 1 means the fitted trajectory does not pass "
                     "through the last observation, which the production "
                     "pipeline corrects for and which is itself a diagnostic")},
    }
    # omega, pooled across fits
    draws = []
    for r in records:
        o = r.get("omega") or {}
        if o.get("available"):
            draws.append(o)
    if draws:
        lo, hi = COVID.fitted_priors["omega__FREE"]
        glo, ghi = COVID_OMEGA_GATE
        out["omega"] = {
            "per_fit": [{"state": r["state"], "asof": r["asof"],
                         "median_per_week": round(r["omega"]["median"], 5),
                         "median_months": round(r["omega"]["median_months"], 2),
                         "months_95": [round(r["omega"]["months_q"]["2.5"], 2),
                                       round(r["omega"]["months_q"]["97.5"], 2)],
                         "frac_inside_gate": round(
                             r["omega"]["frac_inside_gate"], 3),
                         "frac_at_low_bound": round(
                             r["omega"]["frac_at_low_bound"], 3),
                         "frac_at_high_bound": round(
                             r["omega"]["frac_at_high_bound"], 3)}
                        for r in records if (r.get("omega") or {}).get("available")],
            "prior_box_per_week": [lo, hi],
            "gate_window_per_week": [glo, ghi],
            "gate_window_months": [omega_to_months(ghi), omega_to_months(glo)]}
    out["sampler"] = sampler(records)
    out["bimodality"] = bimodality(records)
    df.to_csv(OUT / "gate_a_cells_both_metrics.csv", index=False)
    (OUT / "gate_a_report.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
