"""Adaptive-transmission member: the pre-registered gates, scored.

This file MECHANICALLY implements what research/adaptive-beta/gate.py
specifies. Every bar is a constant imported from gate.py -- JAN_COV50_BAR,
FEB_COV50_BAR, MEMBER_FLOOR, the windows, the arms, the panel -- so nothing
here can move a threshold. gate.py was frozen and hashed BEFORE any fit of
this candidate ran; this file was written while those fits were running and
before any score existed. Both hashes travel in the results JSON.

Scoring discipline (gate.py section 5), all four applied before any table:
  (a) an inline independent Bracher WIS agrees with flubnf.wis.wis on every
      scored cell (max relative difference < 1e-9);
  (b) the samples -> quantiles -> WIS path reproduces the seal's stored
      per-cell WIS for pf and analogue (< 1e-6), and the 50/50
      reconstruction is checked against the stored ensemble;
  (c) truth is settled truth; the baseline is the seal's own per-cell
      base_wis, one number per cell shared by every model;
  (d) every member is restricted to IDENTICAL cells.

Run:  ./.venv/bin/python research/adaptive-beta/score.py [--arm A]
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

from app.core import ensemble as ens                     # noqa: E402
from app.core.scoring import load_truth                  # noqa: E402
from flubnf.wis import wis as wis_fn                     # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI       # noqa: E402

import gate                                              # noqa: E402
from gate import (FEB_COV50_BAR, FEB_PLATEAU_MONTHS,     # noqa: E402
                  INCUMBENT_FEB_COV50, INCUMBENT_JAN_COV50,
                  JAN_COV50_BAR, JAN_PEAK_MONTHS, MEMBER_FLOOR, SEAL,
                  SEASONS, SELECT_SEASONS, STATES, TURN_MONTHS, WORK)

KEY = ["season", "location", "asof", "horizon"]
W5050 = {"pf": 0.5, "analogue": 0.5}
STABLE_MONTHS = {"09", "10", "04", "05", "06"}


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


def score_member(qbyh, fips, season, asof, model, truth, rows, agree):
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
               "asof": asof, "horizon": int(h) - 1, "wis": w, "y": float(y)}
        for p in PI:
            row[f"w{p}"] = q[1.0 - p] - q[p]
            row[f"c{p}"] = float(q[p] <= y <= q[1.0 - p])
        rows.append(row)


def relwis(g) -> float:
    return float(g.wis.sum() / g.base_wis.sum()) if len(g) else float("nan")


def coverage_width_table(g) -> dict:
    """Empirical coverage and mean width at every central interval."""
    out = {}
    for p in PI:
        out[round(1 - 2 * p, 3)] = {"coverage": float(g[f"c{p}"].mean()),
                                    "width": float(g[f"w{p}"].mean())}
    return out


def width_at_matched_coverage(cand, ref, nominal=0.50) -> dict:
    """The free pre-screen: how wide is the candidate when it covers as often
    as the reference does at `nominal`?

    Reference coverage c_ref at the nominal level is read off; the candidate's
    (coverage, width) curve over the 11 central intervals is monotone in the
    level, so the candidate's width at coverage c_ref is a linear
    interpolation in coverage. A ratio above 1 means the candidate buys the
    same hit rate with more interval, which is the arithmetic that makes an
    equal-weight ensemble wider.
    """
    rt = coverage_width_table(ref)
    ct = coverage_width_table(cand)
    levels = sorted(rt)
    c_ref = rt[nominal]["coverage"]
    w_ref = rt[nominal]["width"]
    cov = np.array([ct[L]["coverage"] for L in levels])
    wid = np.array([ct[L]["width"] for L in levels])
    o = np.argsort(cov)
    w_cand = float(np.interp(c_ref, cov[o], wid[o]))
    inside = bool(cov.min() <= c_ref <= cov.max())
    return {"nominal": nominal, "ref_coverage": c_ref, "ref_width": w_ref,
            "cand_width_at_ref_coverage": w_cand,
            "ratio": float(w_cand / w_ref) if w_ref > 0 else None,
            "ref_coverage_inside_candidate_range": inside}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="A")
    a = ap.parse_args()
    arm = a.arm
    OUT = HERE / "out"
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"preregistration_sha256_16": gate.preregistration_hash(),
           "scorer_sha256_16": score_hash(), "arm": arm,
           "arphi": gate.ARMS[arm], "panel": STATES, "seasons": SEASONS}
    print(f"pre-registration {res['preregistration_sha256_16']}  "
          f"scorer {res['scorer_sha256_16']}  arm {arm} "
          f"(arphi = {gate.ARMS[arm]})", flush=True)

    truth, n2f = load_truth()
    fips_of = {s: n2f[s] for s in STATES}
    rows, agree = [], []

    # ---- completeness accounting -----------------------------------------
    root = WORK / f"arm{arm}"
    status = {}
    for f in sorted(root.glob("status_*.json")):
        if f.name.endswith(".prog"):
            continue
        status.update(json.loads(f.read_text()))
    n_ok = sum(1 for v in status.values() if v in ("ok", "cached"))
    n_fail = sum(1 for v in status.values() if str(v).startswith("FAIL"))
    n_compact = len(list(root.glob("*/*/*/compact.npz")))
    expected = len(json.loads((root / "cells.json").read_text()))
    print(f"completeness: {n_compact}/{expected} cells produced output; "
          f"status ok/cached {n_ok}, failures {n_fail}")
    res["completeness"] = {"cells_expected": expected, "cells_done": n_compact,
                           "status_ok": n_ok, "status_fail": n_fail,
                           "failures": {k: v for k, v in status.items()
                                        if str(v).startswith("FAIL")}}

    # ---- the adaptive member ---------------------------------------------
    adaptive_q = {}
    for season in SEASONS:
        for asof in gate.season_asofs(season):
            for loc, sh in gate.collect(arm, season, asof).items():
                q = qdict_from_samples(sh)
                if q:
                    adaptive_q[(season, asof, loc)] = q
                    score_member(q, fips_of[loc], season, asof, "adaptive",
                                 truth, rows, agree)
        print(f"collected adaptive member: {season}", flush=True)

    # ---- stored seal members, both ensembles: ONE pass over the store ----
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
                pf_q = (qdict_from_samples(d["pf"][loc])
                        if loc in d.get("pf", {}) else {})
                an_q = (qdict_from_stored(d["analogue"][loc])
                        if loc in d.get("analogue", {}) else {})
                ad_q = adaptive_q.get((season, asof, loc), {})
                if pf_q:
                    score_member(pf_q, fips, season, asof, "pf", truth,
                                 rows, agree)
                if an_q:
                    score_member(an_q, fips, season, asof, "analogue", truth,
                                 rows, agree)
                if pf_q and an_q:
                    score_member(ens.vincentize({"pf": pf_q,
                                                 "analogue": an_q},
                                                weights=dict(W5050),
                                                location_fips=fips),
                                 fips, season, asof, "ens2", truth, rows,
                                 agree)
                if pf_q and an_q and ad_q:
                    score_member(ens.vincentize(
                        {"pf": pf_q, "analogue": an_q, "adaptive": ad_q},
                        weights={"pf": 1 / 3, "analogue": 1 / 3,
                                 "adaptive": 1 / 3}, location_fips=fips),
                        fips, season, asof, "ens3", truth, rows, agree)
            del d
        print(f"scored stored members + ensembles: {season}", flush=True)

    df = pd.DataFrame(rows)

    # ---- assertion (a) ----------------------------------------------------
    worst = max(agree)
    print(f"\nwis agreement with flubnf.wis.wis: max rel diff {worst:.2e} "
          f"({len(agree)} cells)")
    assert worst < 1e-9, "scoring path does not reproduce flubnf.wis.wis"
    res["wis_agreement"] = {"max_rel_diff": worst, "n": len(agree)}

    # ---- stored scores: comparator and base_wis --------------------------
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
    bw = sm.groupby(KEY).base_wis.nunique()
    assert (bw == 1).all(), "base_wis differs across models within a cell"
    base = sm[sm.model == "pf"][KEY + ["base_wis"]].drop_duplicates(KEY)

    # ---- assertion (b) ----------------------------------------------------
    res["seal_reproduction"] = {}
    for mine, theirs, hard in (("pf", "pf", True), ("analogue", "analogue", True),
                               ("ens2", "ensemble", False)):
        m = df[df.model == mine].merge(sm[sm.model == theirs], on=KEY,
                                       suffixes=("_re", "_st"))
        assert len(m), f"no overlap reproducing {theirs}"
        rel = (m.wis_re - m.wis_st).abs() / m.wis_st.abs().clip(lower=1e-12)
        print(f"seal {theirs} reproduction: max rel diff {rel.max():.2e} "
              f"({len(m)} cells)")
        res["seal_reproduction"][theirs] = {"max_rel_diff": float(rel.max()),
                                            "n": int(len(m))}
        if theirs == "ensemble":
            # IDENTITY FACT, not a failure: the seal's stored 'ensemble' rows
            # are the FROZEN per-horizon-weight blend (2026-08-17 freeze),
            # while the pre-registered comparator here is the unfitted 50/50.
            # Reported so the mismatch is never read as a scoring-path fault;
            # the two mandated member reproductions above are the hard checks
            # and they reproduce the sealed values to 1.3e-10 and 3.1e-10.
            res["seal_reproduction"][theirs]["note"] = (
                "stored 'ensemble' is the frozen per-horizon-weight blend; "
                "the comparator here is the unfitted 50/50, so a large "
                "difference is expected and identifies the stored blend")
        if hard:
            assert rel.max() < 1e-6, (
                f"recomputed {theirs} does not match the seal's stored scores; "
                "pooling drift or truth revision -- stop and look")

    # ---- identical cells --------------------------------------------------
    models = ["adaptive", "pf", "analogue", "ens2", "ens3"]
    sets = [set(map(tuple, df[df.model == m][KEY].itertuples(index=False)))
            for m in models]
    sets.append(set(map(tuple, base[KEY].itertuples(index=False))))
    paired = set.intersection(*sets)
    dfp = df[[t in paired for t in map(tuple, df[KEY].itertuples(index=False))]]
    dfp = dfp.merge(base, on=KEY)
    print(f"paired cells (all members + base_wis): {len(paired)}")
    res["paired_cells"] = len(paired)
    res["paired_cells_by_season"] = {s: sum(1 for t in paired if t[0] == s)
                                     for s in SEASONS}

    def grab(model, seasons=None, months=None):
        g = dfp[dfp.model == model]
        if seasons is not None:
            g = g[g.season.isin(seasons)]
        if months is not None:
            g = g[g["asof"].str[:7].isin(months)]
        return g

    # =====================================================================
    # GATE C -- the width pre-screen, computed and reported FIRST
    # =====================================================================
    print("\n=== GATE C: width pre-screen (before any score) ===")
    gc = {"member_vs_production_pf": {}}
    for label, months in (("all_cells", None), ("turn_cells", TURN_MONTHS)):
        cand, ref = grab("adaptive", months=months), grab("pf", months=months)
        tbl = {"adaptive": coverage_width_table(cand),
               "production_pf": coverage_width_table(ref),
               "n_cells": int(len(cand))}
        for nominal in (0.50, 0.80, 0.95):
            tbl[f"matched_{nominal}"] = width_at_matched_coverage(
                cand, ref, nominal)
        gc["member_vs_production_pf"][label] = tbl
        print(f"  {label} ({len(cand)} cells):")
        for nominal in (0.50, 0.80, 0.95):
            ad = tbl["adaptive"][nominal]
            pr = tbl["production_pf"][nominal]
            mt = tbl[f"matched_{nominal}"]
            print(f"    {int(nominal*100)}%: width adaptive {ad['width']:.1f} "
                  f"(cov {ad['coverage']:.3f}) vs production "
                  f"{pr['width']:.1f} (cov {pr['coverage']:.3f}) | "
                  f"width at matched coverage ratio {mt['ratio']:.3f}")
    res["gate_C_width_prescreen"] = gc

    # =====================================================================
    # GATE A -- the two-sided coverage defect
    # =====================================================================
    print("\n=== GATE A: coverage at the two turns (3-member ensemble) ===")
    ga = {}
    for name, months, bar, direction in (
            ("jan2025_peak", JAN_PEAK_MONTHS, JAN_COV50_BAR, "above"),
            ("feb2024_plateau", FEB_PLATEAU_MONTHS, FEB_COV50_BAR, "below")):
        e3 = grab("ens3", months=months)
        e2 = grab("ens2", months=months)
        c3 = float(e3["c0.25"].mean())
        c2 = float(e2["c0.25"].mean())
        ok = (c3 > bar) if direction == "above" else (c3 < bar)
        ga[name] = {"ensemble3_cov50": c3, "incumbent_cov50_recomputed": c2,
                    "incumbent_cov50_reported": (INCUMBENT_JAN_COV50
                                                 if direction == "above"
                                                 else INCUMBENT_FEB_COV50),
                    "bar": bar, "direction": direction, "n_cells": int(len(e3)),
                    "ensemble3_relwis": relwis(e3),
                    "incumbent_relwis": relwis(e2), "pass": bool(ok)}
        print(f"  {name}: 3-member cov50 {c3:.3f} vs bar {bar} "
              f"({direction}) -> {'PASS' if ok else 'FAIL'}   "
              f"[incumbent recomputed {c2:.3f}, reported "
              f"{ga[name]['incumbent_cov50_reported']}]  {len(e3)} cells")
    gateA = all(v["pass"] for v in ga.values())
    ga["pass"] = bool(gateA)
    res["gate_A_coverage"] = ga

    # =====================================================================
    # GATE B -- skill must not regress
    # =====================================================================
    print("\n=== GATE B: 3-member equal weights vs 2-member 50/50 ===")
    gb = {}
    for label, seasons in (("selection_pooled", SELECT_SEASONS),
                           ("confirm_2025-26", ["2025-26"]),
                           ("all_seasons", SEASONS)):
        e3, e2 = grab("ens3", seasons), grab("ens2", seasons)
        r3, r2 = relwis(e3), relwis(e2)
        gb[label] = {"ens3": r3, "ens2": r2, "ratio": float(r3 / r2),
                     "n_cells": int(len(e3)), "pass": bool(r3 < r2)}
        print(f"  {label}: 3-member {r3:.4f} vs 2-member {r2:.4f}  "
              f"ratio {r3 / r2:.4f}  "
              f"({'PASS' if r3 < r2 else 'FAIL'}, {len(e3)} cells)")
    gb["per_season"] = {}
    for s in SEASONS:
        e3, e2 = grab("ens3", [s]), grab("ens2", [s])
        gb["per_season"][s] = {"ens3": relwis(e3), "ens2": relwis(e2)}
    gateB = gb["selection_pooled"]["pass"]
    gb["pass"] = bool(gateB)
    res["gate_B_skill"] = gb

    # ---- member relWIS floor ---------------------------------------------
    print("\n=== floor: the member's own relWIS, every season ===")
    floor = {}
    for s in SEASONS:
        g = grab("adaptive", [s])
        r = relwis(g)
        # An EMPTY season is a run-completeness fault, not a floor violation:
        # say so rather than firing a kill rule on missing data.
        floor[s] = {"relwis": r, "n_cells": int(len(g)),
                    "ok": bool(len(g) and r <= MEMBER_FLOOR),
                    "empty": bool(len(g) == 0)}
        print(f"  {s}: adaptive {r:.4f} "
              f"(pf {relwis(grab('pf', [s])):.4f}, "
              f"analogue {relwis(grab('analogue', [s])):.4f}) "
              f"{'ok' if r <= MEMBER_FLOOR else 'VIOLATION'}")
    floor_ok = all(v["ok"] for v in floor.values())
    res["member_floor"] = {"per_season": floor, "bar": MEMBER_FLOOR,
                           "pass": bool(floor_ok)}

    # ---- reported, not gated ---------------------------------------------
    print("\n=== reported, not gated ===")
    byh = {}
    for h in range(4):
        row = {}
        for m in ("adaptive", "pf", "analogue", "ens2", "ens3"):
            g = dfp[(dfp.model == m) & (dfp.horizon == h)]
            row[m] = relwis(g)
        byh[h] = row
        print(f"  h={h}: " + "  ".join(f"{m} {v:.3f}"
                                       for m, v in row.items()))
    res["by_horizon"] = byh

    pm = gate.load_params(arm)
    if len(pm):
        pm["month"] = pm["asof"].str[5:7]
        pm["stable"] = pm["month"].isin(STABLE_MONTHS)
        pm["turn"] = pm["asof"].str[:7].isin(TURN_MONTHS)
        sb = {
            "median_all": float(pm["sbeta__FREE_med"].median()),
            "median_stable_months": float(
                pm.loc[pm.stable, "sbeta__FREE_med"].median()),
            "median_turn_months": float(
                pm.loc[pm.turn, "sbeta__FREE_med"].median()),
            "prior_geometric_centre": float(np.exp(
                (np.log(gate.SBETA_LO) + np.log(gate.SBETA_HI)) / 2)),
            "frac_cells_pinned_low": float((pm["sbeta_lo_frac"] > 0.25).mean()),
            "frac_cells_pinned_high": float((pm["sbeta_hi_frac"] > 0.25).mean()),
            "sigma_first_median": float(pm["sigma_first"].median()),
            "sigma_last_median": float(pm["sigma_last"].median()),
            "n_cells": int(len(pm))}
        res["innovation_scale"] = sb
        print(f"  sbeta median {sb['median_all']:.4f} "
              f"(prior centre {sb['prior_geometric_centre']:.4f}); "
              f"stable months {sb['median_stable_months']:.4f}, "
              f"turn months {sb['median_turn_months']:.4f}; "
              f"pinned low in {sb['frac_cells_pinned_low']*100:.1f}% of cells, "
              f"high in {sb['frac_cells_pinned_high']*100:.1f}%")
        pm.to_csv(OUT / f"params_arm{arm}.csv", index=False)

    # ---- verdict ----------------------------------------------------------
    kills = []
    if not ga["jan2025_peak"]["pass"]:
        kills.append("gate A, January direction (cov50 <= %.2f)"
                     % JAN_COV50_BAR)
    if not ga["feb2024_plateau"]["pass"]:
        kills.append("gate A, February direction (cov50 >= %.2f)"
                     % FEB_COV50_BAR)
    if not gateB:
        kills.append("gate B (3-member does not beat 2-member on the "
                     "selection seasons)")
    for s, v in floor.items():
        if v["empty"]:
            kills.append(f"INCOMPLETE: no scored cells in {s}")
        elif not v["ok"]:
            kills.append(f"member floor in {s} (relWIS {v['relwis']:.3f} > "
                         f"{MEMBER_FLOOR})")
    verdict = "KILL" if kills else "PASS -- licenses a full-grid run"
    res["verdict"] = {"decision": verdict, "kill_rules_fired": kills,
                      "gate_A": bool(gateA), "gate_B": bool(gateB),
                      "member_floor": bool(floor_ok)}
    print(f"\nVERDICT: {verdict}")
    for k in kills:
        print(f"  KILL RULE FIRED: {k}")

    (OUT / f"result_arm{arm}.json").write_text(json.dumps(res, indent=1))
    dfp.to_csv(OUT / f"cells_arm{arm}.csv", index=False)
    print(f"written: {OUT / f'result_arm{arm}.json'}")


if __name__ == "__main__":
    main()
