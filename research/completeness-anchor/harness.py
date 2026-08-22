"""Build 2, analogue-anchor arm: last-week completeness correction of the
calendar analogue's anchor. 2026-08-21 handoff, section 4.

=============================================================================
PRE-REGISTRATION (frozen before the first scoring run; nothing below this
block was altered after a score was seen)
=============================================================================

CANDIDATE
  A1  = analogue with anchor' = anchor / c_s, quantiles widened by the
        residual uncertainty of c (primary arm).
  A1s = anchor' = anchor / c_s only, no widening (sensitivity arm).
  A0  = the production analogue exactly as stored in the seal archive
        (app/state/retro_seal/<season>/weeks/*/samples.json, key "analogue").

C ESTIMATION (per state s, per fitting season F; F in {2024-25, 2025-26};
2023-24 is NEVER used in any fit or claim: the reporting-regime break is
measured, research/spatial-nowcast-probe/FINDINGS.md)
  first issue of week w = w's value in the earliest archived vintage
      containing w (flubnf.settings.ARCHIVE via app.core.data), with the
      settle.py filters: location != US, value present and > 0, week <= the
      vintage's as-of date.
  final of week w = w's value in the newest archived vintage.
  r_i = first/final over the state's weeks of season F.
  c_raw(s) = median_i r_i;  n_s = number of such weeks.

SHRINKAGE (precision-style by week count, frozen before scoring)
  log c(s) = (n_s * log c_raw(s) + n0 * log c_nat) / (n_s + n0),  n0 = 10.
  c_nat = median of season F's pooled state-week ratios. A state with no
  weeks gets c_nat. No clipping: a median first/final above 1.0 is a real
  systematic downward revision and is corrected symmetrically.

WIDENING (frozen before scoring)
  sigma_F = 1.4826 * median_i | log r_i - log c(s_i) |   (MAD-based robust
  sd, pooled over season F's state-weeks; chosen over RMS because the
  measured ratio distribution has a fat left tail, p10 0.71-0.75, and a few
  late batch revisions must not set the width for every state).
  Applied as q'(L) = q(L) * exp(z_L * sigma) with z_L the standard normal
  quantile of L: the median is unchanged, tails widen multiplicatively, all
  four horizons equally (an anchor error is multiplicative at every
  horizon).

APPLICATION
  The correction and the widening apply ONLY when the state's anchor week is
  the vintage's newest week (lag 0). An older anchor is near settled
  (measured lag-2 median vintage/final = 1.000 in every season) and gets
  neither.

CROSS-SEASON HONESTY
  Direction A: c and sigma fitted on 2024-25, scored on 2025-26.
  Direction B: c and sigma fitted on 2025-26, scored on 2024-25.
  NO 2023-24 evaluation, claim, or fit of any kind appears in this analysis.

SEAL REPRODUCTION (before any arm is trusted)
  (1) The engine, run with default (no-extra) specs on the seal's vintages,
      must reproduce the stored analogue quantiles (tolerance 1e-6 rel).
  (2) WIS of the stored analogue quantiles against settled truth must
      reproduce the stored scores_members.json analogue rows (tol 1e-6).
  (3) The stored ensemble rows must reproduce from the stored members via
      app.core.ensemble.vincentize with the frozen weights (tol 1e-6).
      Measured before this registration: the stored seal ensemble was built
      with the FROZEN per-horizon weights, not 50/50. The shipping recipe
      is 50/50 (handoff section 0), so the paired ensemble comparison is
      E1 = 50/50(stored pf, A1) vs E0' = 50/50(stored pf, stored A0), with
      the stored frozen-weight E0 reported for reference only.

METRICS (in order)
  1. Turn cells: as-of months 2025-01 when evaluating 2024-25; 2025-12 and
     2026-01 when evaluating 2025-26. Member relWIS A1 vs A0, paired cells,
     relWIS = sum wis / sum stored base_wis.
  2. Full-grid pooled member relWIS per evaluation season (A0, A1, A1s).
  3. Ensemble: E1 vs E0' on identical cells, turn and pooled; stored E0
     for reference.
  4. Width at matched coverage: summed central 50/80/95 interval widths
     (arm / A0) and empirical coverage, full grid and turn cells.

KILL RULE (frozen)
  Kill if turn-cell relWIS movement, 100*(rel_A0 - rel_A1)/rel_A0, is
  below 5% in magnitude in BOTH cross-fit directions, OR the width screen
  fails: A1's summed width exceeds A0's at any of the three intervals while
  A1's empirical coverage at that interval does not move strictly toward
  nominal. A negative movement (A1 worse) of any size also fails the
  candidate.

SCORING DISCIPLINE
  flubnf.wis.wis is the ONLY scoring function called anywhere in this
  harness; the seal-reproduction assertions (2) and (3) are the required
  agreement checks. Baselines are the stored seal base_wis per cell (the
  validated construction); no baseline is recomputed.
=============================================================================

Run from the repo root:  ./.venv/bin/python research/completeness-anchor/harness.py
Outputs (CSV/JSON, no reports) land in /tmp/build2/.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import ensemble as ens                      # noqa: E402
from app.core.data import vintages, vintage_path          # noqa: E402
from app.core.engines import analogue as ENG              # noqa: E402
from app.core.runs import RunSpec                         # noqa: E402
from app.core.scoring import load_truth                   # noqa: E402
from flubnf.wis import wis as wis_fn                      # noqa: E402

OUT = Path("/tmp/build2")
OUT.mkdir(exist_ok=True)
SEAL = REPO / "app" / "state" / "retro_seal"
N0 = 10                       # shrinkage pseudo-weeks (pre-registered)
TOL = 1e-6
SEASONS = ("2024-25", "2025-26")            # the only seasons touched
TURN_MONTHS = {"2024-25": ("2025-01",),
               "2025-26": ("2025-12", "2026-01")}
FIT_OF_EVAL = {"2025-26": "2024-25", "2024-25": "2025-26"}


def season_of(ts: pd.Timestamp) -> str:
    y = ts.year if ts.month >= 8 else ts.year - 1
    return f"{y}-{str(y + 1)[2:]}"


# ---------------------------------------------------------------- first/final
def first_final() -> pd.DataFrame:
    """One row per (location, week): first-issue value, final value, season.

    settle.py conventions exactly: location != US, value > 0, week <= the
    vintage as-of; first issue = earliest containing vintage; final = the
    newest archived vintage.
    """
    cache = OUT / "first_final.pkl"
    if cache.is_file():
        return pickle.loads(cache.read_bytes())
    vs = vintages()
    print(f"scanning {len(vs)} vintages for first issues...", flush=True)
    frames = []
    for v in vs:
        asof = pd.Timestamp(v)
        df = pd.read_csv(vintage_path(v), dtype={"location": str},
                         usecols=["location", "date", "value"])
        df["location"] = df["location"].str.zfill(2)
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df.location != "US") & df.value.notna() & (df.value > 0)
                & (df.date <= asof)]
        df = df.assign(asof=asof)
        frames.append(df)
    big = pd.concat(frames, ignore_index=True)
    big = big.sort_values("asof", kind="stable")
    first = (big.groupby(["location", "date"], as_index=False).first()
             .rename(columns={"value": "first_value"}))
    last_asof = big["asof"].max()          # bracket access: .asof is a method
    fin = (big[big["asof"] == last_asof][["location", "date", "value"]]
           .rename(columns={"value": "final"}))
    m = first.merge(fin, on=["location", "date"], how="inner")
    m = m[m.final > 0].copy()
    m["ratio"] = m.first_value / m.final
    m["season"] = [season_of(d) for d in m.date]
    cache.write_bytes(pickle.dumps(m))
    return m


def c_table(ff: pd.DataFrame, fit_season: str) -> tuple:
    """(per-state table DataFrame, c dict {fips: c_shrunk}, sigma)."""
    assert fit_season in SEASONS and fit_season != "2023-24"
    sub = ff[ff.season == fit_season]
    c_nat = float(sub.ratio.median())
    rows = []
    for fips, g in sub.groupby("location"):
        n = len(g)
        c_raw = float(g.ratio.median())
        c_shr = float(np.exp((n * np.log(c_raw) + N0 * np.log(c_nat))
                             / (n + N0)))
        rows.append({"fips": fips, "n_weeks": n, "c_raw": c_raw,
                     "c_shrunk": c_shr})
    tab = pd.DataFrame(rows).sort_values("c_shrunk")
    cmap = dict(zip(tab.fips, tab.c_shrunk))
    logc = sub.location.map(cmap)
    resid = np.abs(np.log(sub.ratio.values) - np.log(logc.values))
    sigma = float(1.4826 * np.median(resid))
    tab["c_nat"] = c_nat
    return tab, cmap, sigma


# --------------------------------------------------------------------- arms
def compute_arms(eval_season: str, cmap: dict, sigma: float) -> dict:
    """asof -> {arm -> {loc -> {h(str) -> {level(float) -> value}}}} plus the
    stored pf quantiles. Asserts A0 recompute identity per week."""
    cache = OUT / f"arms_{eval_season}.pkl"
    if cache.is_file():
        return pickle.loads(cache.read_bytes())
    weeks = sorted((SEAL / eval_season / "weeks").glob("*/samples.json"))
    out = {}
    worst_a0 = 0.0
    for wk in weeks:
        d = json.loads(wk.read_text())
        asof = d["asof"]
        stored_an = d["analogue"]
        locs = sorted(stored_an)
        spec0 = RunSpec(engine="analogue", forecast_date=asof, locations=locs)
        a0 = ENG.run(spec0)
        # seal-reproduction assertion (1): byte-level identity of the default
        for loc, qs in stored_an.items():
            for h, q in qs.items():
                rq = a0.get(loc, {}).get(h)
                assert rq is not None, f"A0 recompute missing {asof} {loc} h{h}"
                for L, v in q.items():
                    rel = abs(rq[float(L)] - v) / max(abs(v), 1e-9)
                    worst_a0 = max(worst_a0, rel)
        spec1 = RunSpec(engine="analogue", forecast_date=asof, locations=locs,
                        extra={"analogue_completeness": cmap,
                               "analogue_widen_log_sd": sigma})
        spec1s = RunSpec(engine="analogue", forecast_date=asof, locations=locs,
                         extra={"analogue_completeness": cmap})
        a1 = ENG.run(spec1)
        a1s = ENG.run(spec1s)
        pf_q = {loc: ens.member_quantiles_from_samples(s)
                for loc, s in d.get("pf", {}).items()}
        stored = {loc: {h: {float(L): v for L, v in q.items()}
                        for h, q in qs.items()}
                  for loc, qs in stored_an.items()}
        out[asof] = {"A0": stored, "A1": a1, "A1s": a1s, "pf": pf_q}
        print(f"  {eval_season} {asof}: arms computed "
              f"(A0 max rel diff so far {worst_a0:.2e})", flush=True)
    assert worst_a0 < TOL, f"A0 recompute mismatch {worst_a0:.3e}"
    cache.write_bytes(pickle.dumps(out))
    return out


# ------------------------------------------------------------------- scoring
LO = {"50": 0.25, "80": 0.10, "95": 0.025}
HI = {"50": 0.75, "80": 0.90, "95": 0.975}


def score_cells(eval_season: str, arms: dict, truth: dict, n2f: dict) -> pd.DataFrame:
    """One row per (universe row, arm): the stored analogue/ensemble cell
    universes, scored with flubnf.wis.wis, paired with stored base_wis."""
    sm = pd.DataFrame(json.load(open(SEAL / eval_season / "scores_members.json")))
    rows = []
    worst_repro = {"analogue": 0.0, "ensemble": 0.0}
    for asof, g in sm.groupby("asof"):
        wk = arms.get(asof)
        if wk is None:
            continue
        T = pd.Timestamp(asof)
        blends = {}          # loc -> {"E0p":..., "E1":..., "E0frozen":...}
        for r in g.itertuples():
            h = str(r.horizon + 1)
            y = truth.get((r.fips, T + timedelta(days=7 * (r.horizon + 1))))
            if y is None:
                continue
            if r.model == "analogue":
                for arm in ("A0", "A1", "A1s"):
                    q = wk[arm].get(r.location, {}).get(h)
                    assert q is not None, \
                        f"{arm} missing cell {asof} {r.location} h{h}"
                    res = wis_fn(q, y)
                    if arm == "A0":
                        rel = abs(res.wis - r.wis) / max(r.wis, 1e-9)
                        worst_repro["analogue"] = max(worst_repro["analogue"], rel)
                    rows.append({"model": arm, "location": r.location,
                                 "fips": r.fips, "asof": asof,
                                 "horizon": r.horizon, "wis": res.wis,
                                 "base_wis": r.base_wis, "y": y,
                                 "w50": q[HI["50"]] - q[LO["50"]],
                                 "w80": q[HI["80"]] - q[LO["80"]],
                                 "w95": q[HI["95"]] - q[LO["95"]],
                                 "c50": int(q[LO["50"]] <= y <= q[HI["50"]]),
                                 "c80": int(q[LO["80"]] <= y <= q[HI["80"]]),
                                 "c95": int(q[LO["95"]] <= y <= q[HI["95"]])})
            elif r.model == "ensemble":
                if r.location not in blends:
                    members0, members1 = {}, {}
                    pf_q = wk["pf"].get(r.location) or {}
                    if pf_q:
                        members0["pf"] = pf_q
                        members1["pf"] = pf_q
                    a0q = wk["A0"].get(r.location) or {}
                    a1q = wk["A1"].get(r.location) or {}
                    if a0q:
                        members0["analogue"] = a0q
                    if a1q:
                        members1["analogue"] = a1q
                    fifty = {"pf": 0.5, "analogue": 0.5}
                    blends[r.location] = {
                        "E0p": ens.vincentize(members0, weights=fifty,
                                              location_fips=r.fips),
                        "E1": ens.vincentize(members1, weights=fifty,
                                             location_fips=r.fips),
                        "E0frozen": ens.vincentize(members0, weights=None,
                                                   location_fips=r.fips)}
                b = blends[r.location]
                fr = b["E0frozen"].get(h)
                if fr:
                    # seal-reproduction assertion (3)
                    rel = abs(wis_fn(fr, y).wis - r.wis) / max(r.wis, 1e-9)
                    worst_repro["ensemble"] = max(worst_repro["ensemble"], rel)
                for arm in ("E0p", "E1"):
                    q = b[arm].get(h)
                    if not q:
                        continue
                    res = wis_fn(q, y)
                    rows.append({"model": arm, "location": r.location,
                                 "fips": r.fips, "asof": asof,
                                 "horizon": r.horizon, "wis": res.wis,
                                 "base_wis": r.base_wis, "y": y,
                                 "w50": q[HI["50"]] - q[LO["50"]],
                                 "w80": q[HI["80"]] - q[LO["80"]],
                                 "w95": q[HI["95"]] - q[LO["95"]],
                                 "c50": int(q[LO["50"]] <= y <= q[HI["50"]]),
                                 "c80": int(q[LO["80"]] <= y <= q[HI["80"]]),
                                 "c95": int(q[LO["95"]] <= y <= q[HI["95"]])})
    print(f"  seal reproduction, {eval_season}: stored analogue scores max rel "
          f"diff {worst_repro['analogue']:.2e}; stored ensemble (frozen "
          f"weights) {worst_repro['ensemble']:.2e}")
    assert worst_repro["analogue"] < TOL, "stored analogue scores do not reproduce"
    assert worst_repro["ensemble"] < TOL, "stored ensemble does not reproduce"
    return pd.DataFrame(rows)


def relwis(df: pd.DataFrame, model: str) -> float:
    g = df[df.model == model]
    return float(g.wis.sum() / g.base_wis.sum())


def paired(df: pd.DataFrame, models: tuple) -> pd.DataFrame:
    """Restrict to cells present for every model in `models`."""
    key = ["location", "asof", "horizon"]
    sets = [set(map(tuple, df[df.model == m][key].values)) for m in models]
    common = set.intersection(*sets)
    mask = df.model.isin(models) & df[key].apply(tuple, axis=1).isin(common)
    return df[mask]


def report(eval_season: str, df: pd.DataFrame, fit_season: str,
           sigma: float) -> dict:
    turn = df[df["asof"].str[:7].isin(TURN_MONTHS[eval_season])]
    res = {"eval": eval_season, "fit": fit_season, "sigma": sigma}
    mem = paired(df, ("A0", "A1", "A1s"))
    memt = paired(turn, ("A0", "A1", "A1s"))
    enss = paired(df, ("E0p", "E1"))
    ensst = paired(turn, ("E0p", "E1"))
    res["n_member_cells"] = len(mem[mem.model == "A0"])
    res["n_turn_cells"] = len(memt[memt.model == "A0"])
    for m in ("A0", "A1", "A1s"):
        res[f"rel_{m}"] = relwis(mem, m)
        res[f"rel_turn_{m}"] = relwis(memt, m)
    for m in ("E0p", "E1"):
        res[f"rel_{m}"] = relwis(enss, m)
        res[f"rel_turn_{m}"] = relwis(ensst, m)
    res["move_turn_A1"] = 100 * (res["rel_turn_A0"] - res["rel_turn_A1"]) / res["rel_turn_A0"]
    res["move_turn_A1s"] = 100 * (res["rel_turn_A0"] - res["rel_turn_A1s"]) / res["rel_turn_A0"]
    res["move_pooled_A1"] = 100 * (res["rel_A0"] - res["rel_A1"]) / res["rel_A0"]
    res["move_turn_E1"] = 100 * (res["rel_turn_E0p"] - res["rel_turn_E1"]) / res["rel_turn_E0p"]
    res["move_pooled_E1"] = 100 * (res["rel_E0p"] - res["rel_E1"]) / res["rel_E0p"]
    # width and coverage, full grid and turn, per member arm
    for scope, d in (("grid", mem), ("turn", memt)):
        base = d[d.model == "A0"]
        for m in ("A0", "A1", "A1s"):
            g = d[d.model == m]
            for iv in ("50", "80", "95"):
                res[f"{scope}_w{iv}_{m}"] = float(g[f"w{iv}"].sum()
                                                  / base[f"w{iv}"].sum())
                res[f"{scope}_cov{iv}_{m}"] = float(g[f"c{iv}"].mean())
    for scope, d in (("grid", enss), ("turn", ensst)):
        base = d[d.model == "E0p"]
        for m in ("E0p", "E1"):
            g = d[d.model == m]
            for iv in ("50", "80", "95"):
                res[f"{scope}_w{iv}_{m}"] = float(g[f"w{iv}"].sum()
                                                  / base[f"w{iv}"].sum())
                res[f"{scope}_cov{iv}_{m}"] = float(g[f"c{iv}"].mean())
    # width screen (pre-registered): fail if wider at an interval while
    # coverage does not move strictly toward nominal
    fails = []
    for iv, nom in (("50", 0.50), ("80", 0.80), ("95", 0.95)):
        wr = res[f"grid_w{iv}_A1"]
        c0, c1 = res[f"grid_cov{iv}_A0"], res[f"grid_cov{iv}_A1"]
        if wr > 1.0 and not (abs(c1 - nom) < abs(c0 - nom)):
            fails.append(iv)
    res["width_screen_failures"] = fails
    return res


def main() -> int:
    os.nice(10)
    truth, n2f = load_truth()
    ff = first_final()
    print(f"first/final table: {len(ff)} state-weeks, seasons "
          f"{sorted(ff.season.unique())} (2023-24 present in the table, "
          f"never entering a fit)")
    names = {v: k for k, v in n2f.items()}
    tabs, cmaps, sigmas = {}, {}, {}
    for fs in SEASONS:
        tab, cmap, sigma = c_table(ff, fs)
        tab.insert(0, "state", tab.fips.map(names))
        tabs[fs], cmaps[fs], sigmas[fs] = tab, cmap, sigma
        tab.to_csv(OUT / f"c_table_fit_{fs}.csv", index=False)
        print(f"\n=== c fitted on {fs}: c_nat {tab.c_nat.iloc[0]:.3f}, "
              f"sigma {sigma:.4f}, {len(tab)} states ===")
        print(tab.head(8).to_string(index=False,
              formatters={"c_raw": "{:.3f}".format,
                          "c_shrunk": "{:.3f}".format,
                          "c_nat": "{:.3f}".format}))
    results = []
    for eval_season in SEASONS:
        fs = FIT_OF_EVAL[eval_season]
        print(f"\n=== computing arms: eval {eval_season}, c from {fs} ===",
              flush=True)
        arms = compute_arms(eval_season, cmaps[fs], sigmas[fs])
        df = score_cells(eval_season, arms, truth, n2f)
        df.to_csv(OUT / f"cells_{eval_season}.csv", index=False)
        res = report(eval_season, df, fs, sigmas[fs])
        results.append(res)
        print(json.dumps(res, indent=2))
    (OUT / "results.json").write_text(json.dumps(results, indent=2))

    print("\n=== VERDICT against the pre-registered kill rule ===")
    moves = {r["eval"]: r["move_turn_A1"] for r in results}
    small = all(abs(m) < 5.0 for m in moves.values())
    negative = any(m < 0 for m in moves.values())
    width_fail = any(r["width_screen_failures"] for r in results)
    print(f"turn-cell movement by eval season (positive = A1 better): "
          f"{ {k: round(v, 2) for k, v in moves.items()} }")
    print(f"width screen failures: "
          f"{ {r['eval']: r['width_screen_failures'] for r in results} }")
    if small:
        print("KILL: turn-cell movement below 5% in both cross-fit directions.")
    elif width_fail:
        print("KILL: width screen failed.")
    elif negative:
        print("FAIL: A1 worsens turn cells in at least one direction.")
    else:
        print("PASS: movement at or above 5% in at least one direction, "
              "width screen clean.")
    print("\nNo 2023-24 result exists in this analysis; the season is "
          "excluded from every fit and every claim (measured regime break).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
