"""Slope-anchored member: the pre-registered gates, scored.

This file MECHANICALLY implements what research/slope-anchored/gate.py
specifies. Every bar is a constant imported from gate.py -- R_GROWTH_KILL,
R_WIS_KILL, LATE_TURN_BAR, TURN_ACC_RATIO, JAN_COV50_BAR, FEB_COV50_BAR,
MEMBER_FLOOR, the windows, the variants, the panel -- so nothing here can move
a threshold. gate.py and anchor_math.py were frozen and hashed BEFORE any fit
of this candidate ran; both hashes travel in the results JSON.

Scoring discipline (gate.py section 5), all six applied before any table:
  (a)  an inline independent Bracher WIS agrees with flubnf.wis.wis on every
       scored cell (max relative difference < 1e-9);
  (b)  the samples -> quantiles -> WIS path reproduces the seal's stored
       per-cell WIS for pf and analogue (< 1e-6);
  (b') THIS RUN's own production forward also reproduces the seal's stored pf
       per-cell WIS (< 1e-6) -- the check only this member can make, and the
       one that certifies the zero-added-dimension claim;
  (c)  truth is settled truth; the baseline is the seal's own per-cell
       base_wis, one number per cell shared by every model;
  (d)  vintage-true throughout;
  (e)  the anchor-scale guard is applied at collection and its counts reported.

Run:  ./.venv/bin/python research/slope-anchored/score.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from app.core import ensemble as ens                          # noqa: E402
from app.core.scoring import load_truth                       # noqa: E402
from flubnf.wis import wis as wis_fn                          # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI            # noqa: E402

import anchor_math as AM                                      # noqa: E402
import gate                                                   # noqa: E402
from gate import (CLIP_REPORT_FRAC, FEB_COV50_BAR,            # noqa: E402
                  FEB_PLATEAU_MONTHS, INCUMBENT_FEB_COV50,
                  INCUMBENT_JAN_COV50, JAN_COV50_BAR, JAN_PEAK_MONTHS,
                  LATE_TURN_BAR, MEMBER_FLOOR, PRIMARY, R_GROWTH_KILL,
                  R_WIS_KILL, SEAL, SEASONS, SELECT_SEASONS,
                  SPREAD_RATIO_LABEL, STATES, TURN_ACC_RATIO, TURN_MONTHS,
                  TURN_HORIZON_WEEKS, VARIANTS, WORK)

KEY = ["season", "location", "asof", "horizon"]
W5050 = {"pf": 0.5, "analogue": 0.5}


def score_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def wis_independent(q: dict, y: float) -> float:
    """Inline Bracher et al. 2021 WIS, independent of flubnf.wis."""
    tot = 0.5 * abs(y - q[0.5])
    for p in PI:
        a = 2.0 * p
        lo, hi = q[p], q[1.0 - p]
        tot += (a / 2.0) * ((hi - lo) + (2 / a) * max(lo - y, 0)
                            + (2 / a) * max(y - hi, 0))
    return tot / (len(PI) + 0.5)


def qdict_from_samples(samples_by_h: dict) -> dict:
    return {h: {float(k): v for k, v in qs.items()}
            for h, qs in ens.member_quantiles_from_samples(samples_by_h).items()}


def qdict_from_stored(stored: dict) -> dict:
    return {h: {float(k): float(v) for k, v in qs.items()}
            for h, qs in stored.items()}


def score_member(qbyh, fips, season, asof, model, truth, rows, agree,
                 anchor_value=None):
    T = pd.Timestamp(asof)
    for h in ("1", "2", "3", "4"):
        q = qbyh.get(h)
        if not q:
            continue
        y = truth.get((fips, T + timedelta(days=7 * int(h))))
        if y is None or y <= 0 or q[0.5] <= 0:       # frozen score_season rule
            continue
        w = float(wis_fn(q, y).wis)
        agree.append(abs(w - wis_independent(q, y)) / max(abs(w), 1e-12))
        row = {"model": model, "season": season, "location": fips,
               "asof": asof, "horizon": int(h) - 1, "wis": w, "y": float(y),
               "q50": float(q[0.5]),
               # gate 1a is on the GROWTH FACTOR, never the level: every member
               # is anchored to the same last observation, so a correlation of
               # medians measures the anchor and nothing else.
               "log_growth": (float(np.log(q[0.5] / anchor_value))
                              if anchor_value and anchor_value > 0
                              else np.nan)}
        for p in PI:
            row[f"w{p}"] = q[1.0 - p] - q[p]
            row[f"c{p}"] = float(q[p] <= y <= q[1.0 - p])
        row["over"] = float(y > q[0.975])
        row["under"] = float(y < q[0.025])
        rows.append(row)


class EmptyScoreFrame(RuntimeError):
    """No row survived collection. Carries the per-model breakdown."""


def require_rows(df, models, agree) -> None:
    """Fail loudly, with a breakdown, instead of `max()` on an empty sequence.

    Same defect class as the COVID arm's empty frame: when the truth join or the
    collection loop yields nothing, the first symptom is an opaque error far
    from the cause. Print the per-model counts, then name the problem.
    """
    counts = ({m: int((df.model == m).sum()) for m in models}
              if len(df) else {m: 0 for m in models})
    lines = [f"row ledger: {len(df)} rows, {len(agree)} wis-agreement cells"]
    for m in models:
        lines.append(f"    {m:12s} {counts[m]}")
    print("\n".join(lines), flush=True)
    empty = [m for m in models if counts[m] == 0]
    if len(df) and not empty:
        return
    raise EmptyScoreFrame(
        "\n".join(lines)
        + ("\n  NO ROWS AT ALL: the truth join or the collection loop produced "
           "nothing. Check the (location, target_end_date) key first -- the "
           "as-of must already be the Saturday target-end-date."
           if not len(df) else
           f"\n  these models produced no rows: {empty}. No gate table is "
           "produced, because a missing model silently voids every paired "
           "comparison that uses it."))


def relwis(g) -> float:
    return float(g.wis.sum() / g.base_wis.sum()) if len(g) else float("nan")


def coverage_width_table(g) -> dict:
    out = {}
    for p in PI:
        out[round(1 - 2 * p, 3)] = {"coverage": float(g[f"c{p}"].mean()),
                                    "width": float(g[f"w{p}"].mean())}
    return out


def width_at_matched_coverage(cand, ref, nominal=0.50) -> dict:
    rt, ct = coverage_width_table(ref), coverage_width_table(cand)
    levels = sorted(rt)
    c_ref, w_ref = rt[nominal]["coverage"], rt[nominal]["width"]
    cov = np.array([ct[L]["coverage"] for L in levels])
    wid = np.array([ct[L]["width"] for L in levels])
    o = np.argsort(cov)
    w_cand = float(np.interp(c_ref, cov[o], wid[o]))
    return {"nominal": nominal, "ref_coverage": c_ref, "ref_width": w_ref,
            "cand_width_at_ref_coverage": w_cand,
            "ratio": float(w_cand / w_ref) if w_ref > 0 else None,
            "ref_coverage_inside_candidate_range":
                bool(cov.min() <= c_ref <= cov.max())}


def corr(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return float("nan")
    return float(np.corrcoef(a[m], b[m])[0, 1])


# ---------------------------------------------------------------------------
# gate 2a: the implied turn, from the saved origin clouds
# ---------------------------------------------------------------------------

def truth_peaks() -> pd.DataFrame:
    """Settled-truth peak weeks, the audit's definition (centred 3-week mean)."""
    from app.core.data import ARCHIVE, LOCATIONS as LOC
    settled = sorted(Path(ARCHIVE).glob("target-hospital-admissions_*.csv"))[-1]
    t = pd.read_csv(settled, dtype={"location": str})
    t["date"] = pd.to_datetime(t["date"])
    loc = pd.read_csv(LOC, dtype={"location": str})
    pop = dict(zip(loc.location_name, loc.population))
    rows = []
    for season in SEASONS:
        start = pd.Timestamp(gate.season_start(season))
        hi = pd.Timestamp(f"{int(season[:4]) + 1}-06-15")
        sel = t[(t.date >= start) & (t.date <= hi)]
        for name, g in sel.groupby("location_name"):
            if name not in STATES:
                continue
            g = g.sort_values("date").dropna(subset=["value"])
            if g.empty or g.value.max() <= 0:
                continue
            v = g.value.to_numpy(float)
            sm = pd.Series(v).rolling(3, center=True,
                                      min_periods=1).mean().to_numpy()
            i_sm = int(np.argmax(sm))
            rows.append(dict(season=season, location=name,
                             population=int(pop.get(name, 0)),
                             peak_week_sm=int((pd.Timestamp(
                                 g.date.to_numpy()[i_sm]) - start).days // 7),
                             peak_value_sm=float(sm[i_sm])))
    return pd.DataFrame(rows).set_index(["season", "location"])


def implied_peaks(variant: str, peaks: pd.DataFrame) -> pd.DataFrame:
    """Weighted-median implied peak week per cell, member and production.

    anchor_math.propagate is the audit's own RK4, so the production column here
    is directly comparable to the audit's published figures.
    """
    rows = []
    for season in SEASONS:
        for asof in gate.season_asofs(season):
            for loc in STATES:
                d = WORK / season / asof / f"{loc.replace(' ', '_')}_r0"
                f, af = d / "compact.npz", d / "anchor.json"
                if not (f.is_file() and af.is_file()):
                    continue
                try:
                    row = peaks.loc[(season, loc)]
                except KeyError:
                    continue
                a = json.loads(af.read_text())
                spec = a["variants"][variant]
                z = np.load(f, allow_pickle=False)
                if "cloud_theta" not in z.files:
                    continue
                names = [str(x) for x in z["cloud_pnames"]]
                th = z["cloud_theta"].astype(float)
                S = z["cloud_S"].astype(float)
                I = z["cloud_I"].astype(float)
                t = z["cloud_t"].astype(float)
                w = np.full(th.shape[0], 1.0 / th.shape[0])   # equal-weight draws
                N, s0 = float(a["N"]), float(a["s0"])
                t0m = float(np.median(t))
                origin_week = t0m - 1.0        # the model clock leads by 1 week
                iR, iE = names.index("Reff__FREE"), names.index("eps1__FREE")
                iP, iM = names.index("phi1__FREE"), names.index("mult__FREE")
                s_frac = S / N
                out = {}
                for tag, theta in (
                        ("prod", th),
                        ("member", AM.apply_anchor(
                            th, names, float(spec["r_star"]), s_frac, s0, t0m,
                            bool(spec["harmonic"])))):
                    adm = AM.propagate(theta[:, iR], theta[:, iE],
                                       theta[:, iP], theta[:, iM], S, I, N, s0,
                                       t, TURN_HORIZON_WEEKS,
                                       gamma=float(a["gamma"]),
                                       rho=float(a["rho"]),
                                       gammaH=float(a["gammaH"]),
                                       omega=float(a["omega"]))
                    k = np.argmax(adm, axis=0)
                    pw = origin_week + 1.0 + k
                    lo, med, hi2 = AM.weighted_quantile(pw, w)
                    out[tag] = (med, lo, hi2)
                reff_prod = AM.model_reff(th[:, iR], th[:, iE], th[:, iP],
                                          s_frac, s0, t0m)
                rows.append(dict(
                    season=season, asof=asof, location=loc,
                    origin_week=origin_week,
                    obs_peak_week=float(row.peak_week_sm),
                    peak_after_origin=bool(origin_week < row.peak_week_sm),
                    pw_prod=out["prod"][0], pw_member=out["member"][0],
                    pw_prod_lo=out["prod"][1], pw_prod_hi=out["prod"][2],
                    pw_member_lo=out["member"][1],
                    pw_member_hi=out["member"][2],
                    r_star=float(spec["r_star"]),
                    r_star_raw=float(spec["r_star_raw"]),
                    w_shrink=float(spec["w"]), g_raw=float(spec["g_raw"]),
                    clipped=bool(spec["clipped_low"] or spec["clipped_high"]),
                    reff_prod_med=float(np.median(reff_prod))))
    df = pd.DataFrame(rows)
    if len(df):
        df["err_prod"] = df.pw_prod - df.obs_peak_week
        df["err_member"] = df.pw_member - df.obs_peak_week
    return df


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default=PRIMARY)
    a = ap.parse_args()
    v = a.variant
    OUT = HERE / "out"
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"preregistration_sha256_16": gate.preregistration_hash(),
           "scorer_sha256_16": score_hash(), "variant": v,
           "variant_spec": list(VARIANTS[v]), "panel": STATES,
           "seasons": SEASONS, "v_sig_primary": gate.V_SIG}
    print(f"pre-registration {res['preregistration_sha256_16']}  "
          f"scorer {res['scorer_sha256_16']}  variant {v}", flush=True)

    truth, n2f = load_truth()
    fips_of = {s: n2f[s] for s in STATES}
    rows, agree = [], []
    guard = {"flagged": 0, "dropped": 0}

    # ---- completeness accounting -----------------------------------------
    status = {}
    for f in sorted(WORK.glob("status_*.json")):
        if f.name.endswith(".prog"):
            continue
        status.update(json.loads(f.read_text()))
    n_compact = len(list(WORK.glob("*/*/*/compact.npz")))
    expected = len(json.loads((WORK / "cells.json").read_text()))
    res["completeness"] = {
        "cells_expected": expected, "cells_done": n_compact,
        "status_ok": sum(1 for x in status.values() if x in ("ok", "cached")),
        "status_fail": sum(1 for x in status.values()
                           if str(x).startswith("FAIL")),
        "failures": {k: x for k, x in status.items()
                     if str(x).startswith("FAIL")}}
    print(f"completeness: {n_compact}/{expected} cells produced output")

    # ---- our own members: the anchored variant AND the production forward --
    anchors = {}
    for season in SEASONS:
        for asof in gate.season_asofs(season):
            for tag, variant in (("member", v), ("prod_ours", "prod")):
                byloc, g = gate.collect(season, asof, variant)
                if tag == "member":
                    guard["flagged"] += g["flagged"]
                    guard["dropped"] += g["dropped"]
                for loc, sh in byloc.items():
                    q = qdict_from_samples(sh)
                    if not q:
                        continue
                    anch = float(np.median(sh["0"])) if sh.get("0") else None
                    if tag == "member":
                        anchors[(season, asof, loc)] = q
                    score_member(q, fips_of[loc], season, asof, tag, truth,
                                 rows, agree, anchor_value=anch)
        print(f"collected: {season}", flush=True)
    res["anchor_scale_guard"] = guard

    # ---- stored seal members and both ensembles ---------------------------
    from app.core.retro import samples_file
    for season in SEASONS:
        for wd in sorted((SEAL / season / "weeks").iterdir()):
            f = samples_file(wd)
            if f is None:
                continue
            d = (json.loads(f.read_text()) if f.suffix == ".json"
                 else json.loads(__import__("gzip").decompress(
                     f.read_bytes()).decode()))
            asof = d.get("asof", wd.name)
            for loc in STATES:
                fips = fips_of[loc]
                pf_s = d.get("pf", {}).get(loc)
                pf_q = qdict_from_samples(pf_s) if pf_s else {}
                anch = (float(np.median(pf_s["0"]))
                        if pf_s and pf_s.get("0") else None)
                an_q = (qdict_from_stored(d["analogue"][loc])
                        if loc in d.get("analogue", {}) else {})
                me_q = anchors.get((season, asof, loc), {})
                if pf_q:
                    score_member(pf_q, fips, season, asof, "pf", truth, rows,
                                 agree, anchor_value=anch)
                if an_q:
                    score_member(an_q, fips, season, asof, "analogue", truth,
                                 rows, agree, anchor_value=anch)
                if pf_q and an_q:
                    score_member(ens.vincentize({"pf": pf_q,
                                                 "analogue": an_q},
                                                weights=dict(W5050),
                                                location_fips=fips),
                                 fips, season, asof, "ens2", truth, rows,
                                 agree, anchor_value=anch)
                if pf_q and an_q and me_q:
                    score_member(ens.vincentize(
                        {"pf": pf_q, "analogue": an_q, "member": me_q},
                        weights={"pf": 1 / 3, "analogue": 1 / 3,
                                 "member": 1 / 3}, location_fips=fips),
                        fips, season, asof, "ens3", truth, rows, agree,
                        anchor_value=anch)
            del d
        print(f"scored stored members + ensembles: {season}", flush=True)

    df = pd.DataFrame(rows)
    require_rows(df, ["member", "pf", "analogue", "ens2", "ens3", "prod_ours"],
                 agree)

    # ---- assertion (a) ----------------------------------------------------
    worst = max(agree)
    print(f"\nwis agreement with flubnf.wis.wis: max rel diff {worst:.2e} "
          f"({len(agree)} cells)")
    assert worst < 1e-9, "scoring path does not reproduce flubnf.wis.wis"
    res["wis_agreement"] = {"max_rel_diff": worst, "n": len(agree)}

    # ---- stored scores: comparator and base_wis ---------------------------
    stored = []
    for season in SEASONS:
        sm = pd.read_json(SEAL / season / "scores_members.json")
        sm = sm[sm.location.isin(STATES)].copy()
        sm["asof"] = sm["asof"].astype(str).str[:10]
        sm["horizon"] = sm["horizon"].astype(int)
        sm["season"] = season
        sm["location"] = sm["location"].map(fips_of)
        stored.append(sm[["model", "season", "location", "asof", "horizon",
                          "wis", "base_wis"]])
    sm = pd.concat(stored, ignore_index=True)
    assert (sm.groupby(KEY).base_wis.nunique() == 1).all(), \
        "base_wis differs across models within a cell"
    base = sm[sm.model == "pf"][KEY + ["base_wis"]].drop_duplicates(KEY)

    # ---- assertions (b) and (b') -----------------------------------------
    res["seal_reproduction"] = {}
    for mine, theirs in (("pf", "pf"), ("analogue", "analogue"),
                         ("prod_ours", "pf")):
        m = df[df.model == mine].merge(sm[sm.model == theirs], on=KEY,
                                       suffixes=("_re", "_st"))
        assert len(m), f"no overlap reproducing {theirs} from {mine}"
        rel = (m.wis_re - m.wis_st).abs() / m.wis_st.abs().clip(lower=1e-12)
        label = "b_prime_our_production_forward" if mine == "prod_ours" \
            else theirs
        print(f"seal reproduction [{label}]: max rel diff {rel.max():.2e} "
              f"({len(m)} cells)")
        res["seal_reproduction"][label] = {"max_rel_diff": float(rel.max()),
                                           "n": int(len(m))}
        assert rel.max() < 1e-6, (
            f"{label} does not match the seal's stored scores; the "
            "assimilation phase is not production -- stop and look")

    # ---- identical cells --------------------------------------------------
    models = ["member", "pf", "analogue", "ens2", "ens3", "prod_ours"]
    sets = [set(map(tuple, df[df.model == m][KEY].itertuples(index=False)))
            for m in models]
    sets.append(set(map(tuple, base[KEY].itertuples(index=False))))
    paired = set.intersection(*sets)
    dfp = df[[t in paired for t in map(tuple, df[KEY].itertuples(index=False))]]
    dfp = dfp.merge(base, on=KEY)
    print(f"paired cells (all members + base_wis): {len(paired)}")
    res["paired_cells"] = len(paired)

    def grab(model, seasons=None, months=None):
        g = dfp[dfp.model == model]
        if seasons is not None:
            g = g[g.season.isin(seasons)]
        if months is not None:
            g = g[g["asof"].str[:7].isin(months)]
        return g

    def aligned(m1, m2, col):
        a1 = grab(m1).set_index(KEY)[col]
        a2 = grab(m2).set_index(KEY)[col]
        j = a1.to_frame("x").join(a2.to_frame("y"), how="inner")
        return j.x.to_numpy(), j.y.to_numpy()

    # =====================================================================
    # GATE 1 -- REDUNDANCY, FIRST, before any relWIS exists
    # =====================================================================
    print("\n=== GATE 1: redundancy (computed before any skill number) ===")
    g1 = {"note": "correlations are on log(q50/anchor), never on levels: "
                  "every member shares the same anchor"}
    for clause, col, bar in (("1a_growth", "log_growth", R_GROWTH_KILL),
                             ("1b_error", "logwis", R_WIS_KILL)):
        if col == "logwis":
            dfp["logwis"] = np.log1p(dfp.wis)
        c = {}
        for other in ("analogue", "pf"):
            x, y = aligned("member", other, col)
            c[other] = corr(x, y)
        xr, yr = aligned("pf", "analogue", col)
        c["reference_pf_vs_analogue"] = corr(xr, yr)
        c["max_vs_incumbent"] = float(np.nanmax([c["analogue"], c["pf"]]))
        c["bar"] = bar
        c["pass"] = bool(c["max_vs_incumbent"] < bar)
        if col == "log_growth":
            c["by_horizon"] = {}
            for h in range(4):
                hh = dfp[dfp.horizon == h]
                sub = {}
                for other in ("analogue", "pf"):
                    a1 = hh[hh.model == "member"].set_index(KEY)[col]
                    a2 = hh[hh.model == other].set_index(KEY)[col]
                    j = a1.to_frame("x").join(a2.to_frame("y"), how="inner")
                    sub[other] = corr(j.x, j.y)
                c["by_horizon"][h] = sub
        g1[clause] = c
        print(f"  {clause}: vs analogue {c['analogue']:.3f}, vs pf "
              f"{c['pf']:.3f}  [reference pf~analogue "
              f"{c['reference_pf_vs_analogue']:.3f}]  bar {bar} -> "
              f"{'PASS' if c['pass'] else 'FAIL'}")
    gate1 = g1["1a_growth"]["pass"] and g1["1b_error"]["pass"]
    g1["pass"] = bool(gate1)
    res["gate_1_redundancy"] = g1

    # =====================================================================
    # GATE 3a -- the width pre-screen, free, printed before any relWIS
    # =====================================================================
    print("\n=== GATE 3a: width pre-screen (before any score) ===")
    gw = {}
    for label, months in (("all_cells", None), ("turn_cells", TURN_MONTHS)):
        cand, ref = grab("member", months=months), grab("pf", months=months)
        tbl = {"member": coverage_width_table(cand),
               "production_pf": coverage_width_table(ref),
               "n_cells": int(len(cand))}
        for nominal in (0.50, 0.80, 0.95):
            tbl[f"matched_{nominal}"] = width_at_matched_coverage(cand, ref,
                                                                  nominal)
        gw[label] = tbl
        print(f"  {label} ({len(cand)} cells):")
        for nominal in (0.50, 0.80, 0.95):
            me, pr = tbl["member"][nominal], tbl["production_pf"][nominal]
            mt = tbl[f"matched_{nominal}"]
            print(f"    {int(nominal * 100)}%: member {me['width']:.1f} "
                  f"(cov {me['coverage']:.3f}) vs production "
                  f"{pr['width']:.1f} (cov {pr['coverage']:.3f}) | matched "
                  f"ratio {mt['ratio']:.3f}")
    res["gate_3a_width_prescreen"] = gw

    # =====================================================================
    # GATE 2 -- the turn
    # =====================================================================
    print("\n=== GATE 2: the turn ===")
    peaks = truth_peaks()
    ip = implied_peaks(v, peaks)
    ip.to_csv(OUT / f"implied_peak_{v}.csv", index=False)
    g2 = {}
    fut = ip[ip.peak_after_origin] if len(ip) else ip
    if len(fut):
        dmed = float((fut.err_member - fut.err_prod).median())
        acc_m = float((fut.err_member.abs() <= 2).mean())
        acc_p = float((fut.err_prod.abs() <= 2).mean())
        g2["2a_implied_turn"] = {
            "n_pre_peak_cells": int(len(fut)),
            "member_median_err": float(fut.err_member.median()),
            "production_median_err": float(fut.err_prod.median()),
            "audit_production_median_err": gate.AUDIT_PF_PWERR_MEDIAN,
            "paired_median_delta": dmed, "bar_late_turn": LATE_TURN_BAR,
            "member_abs2": acc_m, "production_abs2": acc_p,
            "audit_production_abs2": gate.AUDIT_PF_PWERR_ABS2,
            "acc_ratio": float(acc_m / acc_p) if acc_p > 0 else float("nan"),
            "bar_acc_ratio": TURN_ACC_RATIO,
            "pass_late": bool(dmed <= LATE_TURN_BAR),
            "pass_acc": bool(acc_p > 0 and acc_m / acc_p >= TURN_ACC_RATIO)}
        k = g2["2a_implied_turn"]
        print(f"  2a-i  paired median (member - production) implied peak week: "
              f"{dmed:+.2f} wk, bar <= {LATE_TURN_BAR} -> "
              f"{'PASS' if k['pass_late'] else 'FAIL'}")
        print(f"        member median err {k['member_median_err']:+.2f}, "
              f"production {k['production_median_err']:+.2f} "
              f"(audit full grid {gate.AUDIT_PF_PWERR_MEDIAN:+.2f})")
        print(f"  2a-ii |err|<=2: member {acc_m:.3f}, production {acc_p:.3f} "
              f"(audit {gate.AUDIT_PF_PWERR_ABS2:.3f}), ratio "
              f"{k['acc_ratio']:.3f} bar {TURN_ACC_RATIO} -> "
              f"{'PASS' if k['pass_acc'] else 'FAIL'}")
    else:
        g2["2a_implied_turn"] = {"pass_late": False, "pass_acc": False,
                                 "note": "no pre-peak cells produced"}
        print("  2a: INCOMPLETE, no pre-peak cells")

    g2["2b_coverage"] = {}
    for name, months, bar, direction, reported in (
            ("jan2025_peak", JAN_PEAK_MONTHS, JAN_COV50_BAR, "above",
             INCUMBENT_JAN_COV50),
            ("feb2024_plateau", FEB_PLATEAU_MONTHS, FEB_COV50_BAR, "below",
             INCUMBENT_FEB_COV50)):
        e3, e2, me = (grab("ens3", months=months), grab("ens2", months=months),
                      grab("member", months=months))
        c3, c2 = float(e3["c0.25"].mean()), float(e2["c0.25"].mean())
        ok = (c3 > bar) if direction == "above" else (c3 < bar)
        g2["2b_coverage"][name] = {
            "ensemble3_cov50": c3, "incumbent_cov50_recomputed": c2,
            "incumbent_cov50_reported": reported, "bar": bar,
            "direction": direction, "n_cells": int(len(e3)),
            "member_cov50": float(me["c0.25"].mean()),
            "member_cov95": float(me["c0.025"].mean()),
            "member_over_frac": float(me["over"].mean()),
            "member_under_frac": float(me["under"].mean()),
            "ensemble3_relwis": relwis(e3), "incumbent_relwis": relwis(e2),
            "pass": bool(ok)}
        q = g2["2b_coverage"][name]
        print(f"  2b {name}: 3-member cov50 {c3:.3f} vs bar {bar} "
              f"({direction}) -> {'PASS' if ok else 'FAIL'}  [incumbent "
              f"recomputed {c2:.3f}, reported {reported}]  member cov50 "
              f"{q['member_cov50']:.3f} over {q['member_over_frac']:.3f} "
              f"under {q['member_under_frac']:.3f}  {len(e3)} cells")
    gate2 = (g2["2a_implied_turn"].get("pass_late", False)
             and g2["2a_implied_turn"].get("pass_acc", False)
             and all(x["pass"] for x in g2["2b_coverage"].values()))
    g2["pass"] = bool(gate2)
    res["gate_2_turn"] = g2

    # =====================================================================
    # GATE 3b/3c -- skill
    # =====================================================================
    print("\n=== GATE 3b: 3-member equal weights vs 2-member 50/50 ===")
    g3 = {}
    for label, seasons in (("selection_pooled", SELECT_SEASONS),
                           ("confirm_2025-26", ["2025-26"]),
                           ("all_seasons", SEASONS)):
        e3, e2 = grab("ens3", seasons), grab("ens2", seasons)
        r3, r2 = relwis(e3), relwis(e2)
        g3[label] = {"ens3": r3, "ens2": r2, "ratio": float(r3 / r2),
                     "n_cells": int(len(e3)), "pass": bool(r3 < r2)}
        print(f"  {label}: 3-member {r3:.4f} vs 2-member {r2:.4f}  ratio "
              f"{r3 / r2:.4f}  ({'PASS' if r3 < r2 else 'FAIL'}, "
              f"{len(e3)} cells)")
    gate3b = g3["selection_pooled"]["pass"]
    g3["pass"] = bool(gate3b)
    res["gate_3b_skill"] = g3

    print("\n=== GATE 3c: the member's own relWIS, every season ===")
    floor = {}
    for s in SEASONS:
        g = grab("member", [s])
        r = relwis(g)
        floor[s] = {"relwis": r, "n_cells": int(len(g)),
                    "ok": bool(len(g) and r <= MEMBER_FLOOR),
                    "empty": bool(len(g) == 0)}
        print(f"  {s}: member {r:.4f} (pf {relwis(grab('pf', [s])):.4f}, "
              f"analogue {relwis(grab('analogue', [s])):.4f}) "
              f"{'ok' if r <= MEMBER_FLOOR else 'VIOLATION'}")
    floor_ok = all(x["ok"] for x in floor.values())
    res["gate_3c_member_floor"] = {"per_season": floor, "bar": MEMBER_FLOOR,
                                   "pass": bool(floor_ok)}

    # ---- reported, not gated ---------------------------------------------
    print("\n=== reported, not gated ===")
    byh = {}
    for h in range(4):
        byh[h] = {m: relwis(dfp[(dfp.model == m) & (dfp.horizon == h)])
                  for m in ("member", "pf", "analogue", "ens2", "ens3")}
        print(f"  h={h}: " + "  ".join(f"{m} {x:.3f}"
                                       for m, x in byh[h].items()))
    res["by_horizon"] = byh

    ad = gate.load_anchor_diagnostics()
    pc = {}
    if len(ad) and len(ip):
        sr = (float(ip.r_star.std() / ip.reff_prod_med.std())
              if ip.reff_prod_med.std() > 0 else float("nan"))
        pc = {"clip_frac": float((ad.clipped_low | ad.clipped_high).mean()),
              "median_w": float(ad.w.median()),
              "median_r_star": float(ad.r_star.median()),
              "sd_r_star": float(ip.r_star.std()),
              "sd_reff_production": float(ip.reff_prod_med.std()),
              "spread_ratio": sr, "bar_clip": CLIP_REPORT_FRAC,
              "label_threshold": SPREAD_RATIO_LABEL,
              "shrunken_persistence": bool(sr < SPREAD_RATIO_LABEL),
              "reason_counts": ad.reason.value_counts().to_dict()}
        print(f"  persistence clause: clipped {pc['clip_frac'] * 100:.1f}%, "
              f"median w {pc['median_w']:.3f}, sd(R*) {pc['sd_r_star']:.3f} vs "
              f"sd(R_eff prod) {pc['sd_reff_production']:.3f}, "
              f"spread ratio {sr:.3f}"
              + ("  -> SHRUNKEN-PERSISTENCE FORECASTER"
                 if pc["shrunken_persistence"] else ""))
        ad.to_csv(OUT / "anchor_diagnostics.csv", index=False)
    res["persistence_clause"] = pc

    # ---- verdict ----------------------------------------------------------
    kills = []
    if not g1["1a_growth"]["pass"]:
        kills.append("gate 1a redundancy: growth correlation %.3f >= %.2f"
                     % (g1["1a_growth"]["max_vs_incumbent"], R_GROWTH_KILL))
    if not g1["1b_error"]["pass"]:
        kills.append("gate 1b redundancy: per-cell WIS correlation %.3f >= %.2f"
                     % (g1["1b_error"]["max_vs_incumbent"], R_WIS_KILL))
    if not g2["2a_implied_turn"].get("pass_late", False):
        kills.append("gate 2a-i: the member turns late")
    if not g2["2a_implied_turn"].get("pass_acc", False):
        kills.append("gate 2a-ii: implied-peak accuracy floor")
    for nm, x in g2["2b_coverage"].items():
        if not x["pass"]:
            kills.append(f"gate 2b {nm} ({x['direction']} {x['bar']})")
    if not gate3b:
        kills.append("gate 3b: 3-member does not beat 2-member on the "
                     "selection seasons")
    for s, x in floor.items():
        if x["empty"]:
            kills.append(f"INCOMPLETE: no scored cells in {s}")
        elif not x["ok"]:
            kills.append(f"gate 3c member floor in {s} "
                         f"(relWIS {x['relwis']:.3f} > {MEMBER_FLOOR})")
    verdict = "KILL" if kills else "PASS -- licenses a full-grid run"
    if pc.get("shrunken_persistence"):
        verdict += " [READ AS: a shrunken-persistence member, not a "\
                   "slope-anchored one]"
    res["verdict"] = {"decision": verdict, "kill_rules_fired": kills,
                      "gate_1": bool(gate1), "gate_2": bool(gate2),
                      "gate_3b": bool(gate3b), "gate_3c": bool(floor_ok)}
    print(f"\nVERDICT: {verdict}")
    for k in kills:
        print(f"  KILL RULE FIRED: {k}")

    (OUT / f"result_{v}.json").write_text(json.dumps(res, indent=1,
                                                     default=float))
    dfp.to_csv(OUT / f"cells_{v}.csv", index=False)
    print(f"written: {OUT / f'result_{v}.json'}")


if __name__ == "__main__":
    main()
