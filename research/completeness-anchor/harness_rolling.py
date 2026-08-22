"""Build 2, within-season ROLLING completeness estimator: the surviving
variant after the cross-season form was killed 2026-08-21 (width screen
failure on 2025-26; /tmp/build2/results.json). 2026-08-21 handoff, section 4.

=============================================================================
PRE-REGISTRATION (frozen before the first scoring run; nothing below this
block was altered after a score was seen)
=============================================================================

THE ESTIMATOR (vintage-legal by construction; no cross-season anything; every
quantity at as-of t uses only vintages dated <= t)
  At each as-of t (a seal week, which is also a vintage date), for state s:
    ratio set: weeks w of the SAME season as t (Aug-Jul), with
        (t - w) >= 14 days           (mature by the measured settling curve;
                                      the newest week in a vintage is the
                                      as-of Saturday itself, so 14 days = lag
                                      >= 2, where lag-2 median vintage/final
                                      is measured 1.000 in every season),
        s's value of w in vintage t present and > 0,
        first-issue value of w present and > 0,
        first-issue vintage <= t     (legality: a week backfilled after t has
                                      no first issue observable at t).
        Settle conventions throughout: location != US, week <= vintage as-of.
        first issue of w = w's value in the earliest archived vintage
        containing it (same convention as the killed cross-season form).
    r_w = first_issue(w) / value_of_w_in_vintage_t(w).
    window: the most recent K such ratio weeks (sorted by w, tail K);
        n = the number of ratios in the window (n <= K).
    c_nat(t) = median of the POOLED state ratios from the same mature set,
        restricted to the K most recent distinct weeks present in the pool
        (the national estimated the same rolling way, pooled across states,
        matching the killed form's pooled c_nat).
    activation: no correction and no widening until the state has at least 3
        mature ratios. Below that the state is absent from the correction
        table and the engine path is byte-identical to A0.
    shrinkage: log c_s(t) = (n * log c_roll + 6 * log c_nat(t)) / (n + 6),
        i.e. the state's own rolling median gets weight n/(n+6). The shrink
        constant 6 is fixed for every K.
    widening: sigma_s(t) = max(0.02, 1.4826 * median_i | log r_i -
        log c_s(t) |) over the state's window ratios. Applied only where the
        correction applies.
  FROZEN A PRIORI, never tuned on scores: K = 6 primary. K = 4 and K = 8 are
  information-only sensitivities, clearly labeled, never selected.

APPLICATION (the shipped hook, unchanged, HEAD a14e566)
  anchor' = anchor / c_s(t); quantiles widened by exp(z_L * sigma_s(t)).
  Both apply ONLY when the state's anchor week is the vintage's newest week
  (lag 0), via app.core.engines.analogue.completeness_args reading
  spec.extra. Per-state sigma is delivered by grouping states with equal
  sigma into one engine call each, so every A1 cell is produced by the
  shipped engine path end to end; no quantile is post-processed here.

ARMS
  A0  = the production analogue exactly as stored in the seal archive.
  A1  = rolling correction + rolling widening (primary).
  A1s = rolling correction only (sensitivity).
  A1k4 / A1k8 = A1 with K = 4 / K = 8 (information-only sensitivities).
  E0' = 50/50 vincentization of (stored seal pf, A0).
  E1  = 50/50 vincentization of (stored seal pf, A1). Identical cells.

SEAL REPRODUCTION (before any arm is trusted; all three seasons)
  (1) The engine, run with default (no-extra) specs on the seal's vintages,
      must reproduce the stored analogue quantiles (tolerance 1e-6 rel).
  (2) WIS of the stored analogue quantiles against settled truth must
      reproduce the stored scores_members.json analogue rows (tol 1e-6).
  (3) The stored ensemble rows must reproduce from the stored members via
      app.core.ensemble.vincentize with the FROZEN weights (tol 1e-6).
      Measured before this registration (machinery identification, not a
      score of any arm): the stored seal ensemble reproduces with the frozen
      per-horizon weights in ALL THREE seasons (2023-24 probed 2026-08-21,
      max rel diff 1.5e-11; 50/50 does not reproduce it). The shipping
      recipe is 50/50, so the paired comparison is E1 vs E0'.

EVALUATION (all three seasons are honest: nothing is fitted across seasons.
2023-24 is the designed falsification: its reporting was near-complete, the
estimator should learn c near 1 and the correction should vanish; if A1
differs from A0 beyond noise there, the machinery itself is broken.)
  Turn cells: as-of months 2024-02 for 2023-24; 2025-01 for 2024-25;
  2025-12 and 2026-01 for 2025-26.
  Metrics per season, in order:
    1. turn cells, A1 vs A0 paired member relWIS
       (relWIS = sum wis / sum stored base_wis; stored seal baselines, the
       validated construction; no baseline recomputed).
    2. pooled member relWIS (A0, A1, A1s; K sensitivities labeled).
    3. ensemble E1 vs E0' on identical cells, turn and pooled; the stored
       frozen-weight ensemble is reference only.
    4. width screen: summed central 50/80/95 widths (arm / A0) with
       empirical coverage; widths may grow at an interval only where
       coverage moves strictly TOWARD nominal, per season, full grid.
       Trigger: width ratio > 1 + 1e-9 (float-dust guard only) while
       |cov_A1 - nominal| is not strictly < |cov_A0 - nominal|.

MECHANISM PREDICTION (frozen; the key check, where the cross-season form
died): the rolling form should adapt per season. 2024-25 should widen,
2025-26 barely, 2025-26 coverage must not be pushed past nominal the way
the cross-season sigma = 0.0726 did, and 2023-24 should not widen at all
beyond the floor's residue. Reported as held / not held.

KILL RULE (frozen)
  Kill if ANY of:
    (i)   turn-cell movement 100*(rel_turn_A0 - rel_turn_A1)/rel_turn_A0 is
          below 5 in BOTH post-break seasons (2024-25 and 2025-26);
    (ii)  that movement is negative (A1 worse) in ANY post-break season;
    (iii) the width screen fails in ANY season (2023-24 included);
    (iv)  do-no-harm fails on 2023-24: |pooled member movement| >= 2%.

DIAGNOSTICS (information only, reported regardless of verdict)
  c_s(t) trajectories for the 8 most-corrected states (ranked by mean
  |log c_s(t)| over active weeks in the two post-break seasons): activation
  week, stabilization (sd of log c over first 5 vs last 5 active weeks),
  end-of-season c. Activation timing per season: weeks from the first seal
  week to first activation, and the fraction of turn cells whose (as-of,
  state) sits inside the corrected regime (active, and applied at a lag-0
  anchor). A correction that activates after the turn is decorative; this is
  stated plainly.

SCORING DISCIPLINE
  flubnf.wis.wis is the ONLY scoring function called anywhere here; the
  seal-reproduction assertions (2) and (3) are the required agreement
  checks. Baselines are the stored seal base_wis per cell. os.nice(10): the
  regime harness shares this machine.
=============================================================================

Run from the repo root:
    nice -n 10 ./.venv/bin/python research/completeness-anchor/harness_rolling.py
Outputs (CSV/JSON, no reports) land in /tmp/build2roll/.
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

OUT = Path("/tmp/build2roll")
OUT.mkdir(exist_ok=True)
SEAL = REPO / "app" / "state" / "retro_seal"
TOL = 1e-6
MATURE_DAYS = 14
MIN_RATIOS = 3                 # activation gate (pre-registered)
SHRINK = 6                     # shrink constant (pre-registered, all K)
SIGMA_FLOOR = 0.02             # widening floor (pre-registered)
K_PRIMARY = 6
K_SENS = (4, 8)
SEASONS = ("2023-24", "2024-25", "2025-26")
POST_BREAK = ("2024-25", "2025-26")
TURN_MONTHS = {"2023-24": ("2024-02",),
               "2024-25": ("2025-01",),
               "2025-26": ("2025-12", "2026-01")}
MEMBER_ARMS = ("A0", "A1", "A1s", "A1k4", "A1k8")


def season_of(ts: pd.Timestamp) -> str:
    y = ts.year if ts.month >= 8 else ts.year - 1
    return f"{y}-{str(y + 1)[2:]}"


# ------------------------------------------------------------------- panel
def build_panel() -> tuple:
    """(panel, first): panel is one row per (vintage asof, location, week)
    with the state's value in that vintage; first is one row per (location,
    week) with the first-issue value and the vintage it appeared in.

    Settle conventions: location != US, value present and > 0, week <= the
    vintage as-of. Same first-issue convention as the killed form: earliest
    ARCHIVED vintage containing the week."""
    cache = OUT / "panel.pkl"
    if cache.is_file():
        return pickle.loads(cache.read_bytes())
    vs = vintages()
    print(f"scanning {len(vs)} vintages for the revision panel...", flush=True)
    frames = []
    for v in vs:
        asof = pd.Timestamp(v)
        df = pd.read_csv(vintage_path(v), dtype={"location": str},
                         usecols=["location", "date", "value"])
        df["location"] = df["location"].str.zfill(2)
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df.location != "US") & df.value.notna() & (df.value > 0)
                & (df.date <= asof)]
        frames.append(df.assign(asof=asof))
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values("asof", kind="stable")
    first = (panel.groupby(["location", "date"], as_index=False).first()
             .rename(columns={"value": "first_value", "asof": "first_asof"}))
    pickle_bytes = pickle.dumps((panel, first))
    cache.write_bytes(pickle_bytes)
    return panel, first


def roll_tables(panel_t: pd.DataFrame, first: pd.DataFrame,
                t: pd.Timestamp, K: int) -> tuple:
    """(cmap {fips: c}, sigmap {fips: sigma}, diag rows) at as-of t.

    panel_t: the panel restricted to vintage t. Implements the frozen
    estimator exactly as pre-registered above."""
    season = season_of(t)
    m = panel_t[panel_t.date <= t - pd.Timedelta(days=MATURE_DAYS)]
    m = m[[season_of(d) == season for d in m.date]]
    mm = m.merge(first, on=["location", "date"], how="inner")
    mm = mm[(mm.first_value > 0) & (mm.first_asof <= t)].copy()
    mm["ratio"] = mm.first_value / mm.value
    cmap, sigmap, diag = {}, {}, []
    if mm.empty:
        return cmap, sigmap, diag
    pool_weeks = sorted(mm.date.unique())[-K:]
    c_nat = float(mm[mm.date.isin(pool_weeks)].ratio.median())
    for fips, g in mm.groupby("location"):
        g = g.sort_values("date")
        avail = len(g)
        win = g.ratio.values[-K:]
        n = len(win)
        active = avail >= MIN_RATIOS
        c_roll = float(np.median(win))
        c_shr = float(np.exp((n * np.log(c_roll) + SHRINK * np.log(c_nat))
                             / (n + SHRINK)))
        sigma = float(max(SIGMA_FLOOR,
                          1.4826 * np.median(np.abs(np.log(win)
                                                    - np.log(c_shr)))))
        if active:
            cmap[fips] = c_shr
            sigmap[fips] = sigma
        diag.append({"asof": str(t.date()), "fips": fips, "n_avail": avail,
                     "n_win": n, "c_roll": c_roll, "c_nat": c_nat,
                     "c_shrunk": c_shr if active else np.nan,
                     "sigma": sigma if active else np.nan,
                     "active": int(active)})
    return cmap, sigmap, diag


def anchor_lag0(asof: str) -> dict:
    """{fips: True if the state's anchor week is the vintage's newest week},
    replicating the engine's own anchor logic line for line."""
    t = pd.read_csv(vintage_path(asof), dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    t = t[t.date <= pd.Timestamp(asof)]
    newest = t.date.max()
    out = {}
    for fips, g in t.groupby("location"):
        g = g.sort_values("date")
        vals = pd.to_numeric(g.value, errors="coerce").dropna()
        if not len(vals):
            continue
        out[fips] = bool(g.date.loc[vals.index[-1]] == newest)
    return out


# --------------------------------------------------------------------- arms
def widened_group_runs(asof: str, locs_by_sigma: dict, cmap: dict,
                       name_of: dict) -> dict:
    """One shipped-path engine run per distinct sigma value; returns
    {location_name: quantiles} covering every corrected state."""
    out = {}
    for sig, fips_list in locs_by_sigma.items():
        names = sorted(name_of[f] for f in fips_list if f in name_of)
        if not names:
            continue
        spec = RunSpec(engine="analogue", forecast_date=asof, locations=names,
                       extra={"analogue_completeness": cmap,
                              "analogue_widen_log_sd": sig})
        out.update(ENG.run(spec))
    return out


def compute_arms(eval_season: str, panel: pd.DataFrame, first: pd.DataFrame,
                 name_of: dict) -> tuple:
    """asof -> {arm -> {loc -> {h(str) -> {level(float) -> value}}}} plus pf,
    and the diagnostic table. Asserts A0 recompute identity per week."""
    cache = OUT / f"arms_{eval_season}.pkl"
    if cache.is_file():
        return pickle.loads(cache.read_bytes())
    weeks = sorted((SEAL / eval_season / "weeks").glob("*/samples.json"))
    by_asof = dict(tuple(panel.groupby("asof")))
    out, diag_rows = {}, []
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
        stored = {loc: {h: {float(L): v for L, v in q.items()}
                        for h, q in qs.items()}
                  for loc, qs in stored_an.items()}
        panel_t = by_asof.get(pd.Timestamp(asof))
        if panel_t is None:
            panel_t = panel.iloc[0:0]
        lag0 = anchor_lag0(asof)
        week_arms = {"A0": stored}
        for K, tag in ((K_PRIMARY, "A1"), (K_SENS[0], "A1k4"),
                       (K_SENS[1], "A1k8")):
            cmap, sigmap, diag = roll_tables(panel_t, first,
                                             pd.Timestamp(asof), K)
            if K == K_PRIMARY:
                for row in diag:
                    row["lag0"] = int(lag0.get(row["fips"], False))
                    row["applied"] = int(bool(row["active"])
                                         and lag0.get(row["fips"], False))
                diag_rows.extend(diag)
                # A1s: correction only, one shipped-path run, all locations
                spec_s = RunSpec(engine="analogue", forecast_date=asof,
                                 locations=locs,
                                 extra={"analogue_completeness": cmap})
                week_arms["A1s"] = ENG.run(spec_s)
            groups = defaultdict(list)
            for f, sig in sigmap.items():
                groups[sig].append(f)
            corrected = widened_group_runs(asof, groups, cmap, name_of)
            arm = {}
            for loc in locs:
                if loc in corrected:
                    arm[loc] = corrected[loc]
                elif K == K_PRIMARY:
                    arm[loc] = week_arms["A1s"].get(loc, stored[loc])
                else:
                    arm[loc] = stored[loc]     # inactive: engine default = A0
            week_arms[tag] = arm
        week_arms["pf"] = {loc: ens.member_quantiles_from_samples(s)
                           for loc, s in d.get("pf", {}).items()}
        out[asof] = week_arms
        n_act = sum(r["active"] for r in diag_rows if r["asof"] == asof)
        print(f"  {eval_season} {asof}: arms computed, {n_act} states active "
              f"(A0 max rel diff so far {worst_a0:.2e})", flush=True)
    assert worst_a0 < TOL, f"A0 recompute mismatch {worst_a0:.3e}"
    diag = pd.DataFrame(diag_rows)
    cache.write_bytes(pickle.dumps((out, diag)))
    return out, diag


# ------------------------------------------------------------------- scoring
LO = {"50": 0.25, "80": 0.10, "95": 0.025}
HI = {"50": 0.75, "80": 0.90, "95": 0.975}


def _cell_row(model, r, q, y):
    return {"model": model, "location": r.location, "fips": r.fips,
            "asof": r.asof, "horizon": r.horizon, "wis": wis_fn(q, y).wis,
            "base_wis": r.base_wis, "y": y,
            "w50": q[HI["50"]] - q[LO["50"]],
            "w80": q[HI["80"]] - q[LO["80"]],
            "w95": q[HI["95"]] - q[LO["95"]],
            "c50": int(q[LO["50"]] <= y <= q[HI["50"]]),
            "c80": int(q[LO["80"]] <= y <= q[HI["80"]]),
            "c95": int(q[LO["95"]] <= y <= q[HI["95"]])}


def score_cells(eval_season: str, arms: dict, truth: dict) -> pd.DataFrame:
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
        blends = {}
        for r in g.itertuples():
            h = str(r.horizon + 1)
            y = truth.get((r.fips, T + timedelta(days=7 * (r.horizon + 1))))
            if y is None:
                continue
            if r.model == "analogue":
                for arm in MEMBER_ARMS:
                    q = wk[arm].get(r.location, {}).get(h)
                    assert q is not None, \
                        f"{arm} missing cell {asof} {r.location} h{h}"
                    if arm == "A0":
                        rel = abs(wis_fn(q, y).wis - r.wis) / max(r.wis, 1e-9)
                        worst_repro["analogue"] = max(worst_repro["analogue"],
                                                      rel)
                    rows.append(_cell_row(arm, r, q, y))
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
                    rows.append(_cell_row(arm, r, q, y))
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
    key = ["location", "asof", "horizon"]
    sets = [set(map(tuple, df[df.model == m][key].values)) for m in models]
    common = set.intersection(*sets)
    mask = df.model.isin(models) & df[key].apply(tuple, axis=1).isin(common)
    return df[mask]


def report(eval_season: str, df: pd.DataFrame, diag: pd.DataFrame) -> dict:
    turn = df[df["asof"].str[:7].isin(TURN_MONTHS[eval_season])]
    res = {"eval": eval_season}
    mem = paired(df, MEMBER_ARMS)
    memt = paired(turn, MEMBER_ARMS)
    enss = paired(df, ("E0p", "E1"))
    ensst = paired(turn, ("E0p", "E1"))
    res["n_member_cells"] = len(mem[mem.model == "A0"])
    res["n_turn_cells"] = len(memt[memt.model == "A0"])
    for m in MEMBER_ARMS:
        res[f"rel_{m}"] = relwis(mem, m)
        res[f"rel_turn_{m}"] = relwis(memt, m)
    for m in ("E0p", "E1"):
        res[f"rel_{m}"] = relwis(enss, m)
        res[f"rel_turn_{m}"] = relwis(ensst, m)
    for tag in ("A1", "A1s", "A1k4", "A1k8"):
        res[f"move_turn_{tag}"] = 100 * (res["rel_turn_A0"]
                                         - res[f"rel_turn_{tag}"]) / res["rel_turn_A0"]
        res[f"move_pooled_{tag}"] = 100 * (res["rel_A0"]
                                           - res[f"rel_{tag}"]) / res["rel_A0"]
    res["move_turn_E1"] = 100 * (res["rel_turn_E0p"]
                                 - res["rel_turn_E1"]) / res["rel_turn_E0p"]
    res["move_pooled_E1"] = 100 * (res["rel_E0p"]
                                   - res["rel_E1"]) / res["rel_E0p"]
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
    # coverage does not move strictly toward nominal; 1e-9 float-dust guard
    fails = []
    for iv, nom in (("50", 0.50), ("80", 0.80), ("95", 0.95)):
        wr = res[f"grid_w{iv}_A1"]
        c0, c1 = res[f"grid_cov{iv}_A0"], res[f"grid_cov{iv}_A1"]
        if wr > 1.0 + 1e-9 and not (abs(c1 - nom) < abs(c0 - nom)):
            fails.append(iv)
    res["width_screen_failures"] = fails
    # activation and application diagnostics
    d = diag.copy()
    res["mean_active_states"] = float(d.groupby("asof")["active"].sum().mean())
    res["mean_sigma_active"] = float(d[d.active == 1].sigma.mean()) if (d.active == 1).any() else float("nan")
    res["share_sigma_at_floor"] = (float((d[d.active == 1].sigma
                                          <= SIGMA_FLOOR + 1e-12).mean())
                                   if (d.active == 1).any() else float("nan"))
    turn_a0 = memt[memt.model == "A0"]
    dk = d.set_index(["asof", "fips"])
    applied, active = [], []
    for r in turn_a0.itertuples():
        row = dk["applied"].get((r.asof, r.fips))
        applied.append(bool(row) if row is not None else False)
        row = dk["active"].get((r.asof, r.fips))
        active.append(bool(row) if row is not None else False)
    res["turn_cells_applied_frac"] = float(np.mean(applied)) if applied else float("nan")
    res["turn_cells_active_frac"] = float(np.mean(active)) if active else float("nan")
    return res


def activation_summary(eval_season: str, diag: pd.DataFrame,
                       names: dict) -> dict:
    """Per season: weeks until activation and the uncorrected window."""
    asofs = sorted(diag["asof"].unique())     # bracket access: .asof is a method
    first_asof = asofs[0] if asofs else None
    rows = []
    for fips, g in diag.groupby("fips"):
        g = g.sort_values("asof")
        act = g[g.active == 1]
        rows.append({"fips": fips, "state": names.get(fips, fips),
                     "first_active": act["asof"].iloc[0] if len(act) else None,
                     "weeks_to_activate": (asofs.index(act["asof"].iloc[0])
                                           if len(act) else None)})
    t = pd.DataFrame(rows)
    never = t[t.first_active.isna()]
    wk = t.weeks_to_activate.dropna()
    return {"season": eval_season, "first_seal_week": first_asof,
            "n_states": len(t), "n_never_active": len(never),
            "median_weeks_to_activate": float(wk.median()) if len(wk) else None,
            "max_weeks_to_activate": float(wk.max()) if len(wk) else None,
            "median_first_active_date": (sorted(t.first_active.dropna())
                                         [len(t.first_active.dropna()) // 2]
                                         if t.first_active.notna().any()
                                         else None)}


def trajectories(diags: dict, names: dict) -> pd.DataFrame:
    """The 8 most-corrected states, ranked by mean |log c| over active weeks
    in the post-break seasons; per state-season stabilization stats."""
    pooled = pd.concat([diags[s].assign(season=s) for s in POST_BREAK])
    act = pooled[pooled.active == 1].copy()
    act["abslogc"] = np.abs(np.log(act.c_shrunk))
    rank = (act.groupby("fips")["abslogc"].mean()
            .sort_values(ascending=False).head(8))
    rows = []
    for fips in rank.index:
        for s in SEASONS:
            g = diags[s]
            g = g[(g.fips == fips)].sort_values("asof")
            a = g[g.active == 1]
            if not len(a):
                rows.append({"state": names.get(fips, fips), "fips": fips,
                             "season": s, "n_active_weeks": 0})
                continue
            logc = np.log(a.c_shrunk.values)
            rows.append({
                "state": names.get(fips, fips), "fips": fips, "season": s,
                "n_active_weeks": len(a),
                "first_active": a["asof"].iloc[0],
                "c_at_activation": round(float(a.c_shrunk.iloc[0]), 3),
                "c_mid": round(float(a.c_shrunk.iloc[len(a) // 2]), 3),
                "c_end": round(float(a.c_shrunk.iloc[-1]), 3),
                "sd_logc_first5": round(float(np.std(logc[:5])), 4),
                "sd_logc_last5": round(float(np.std(logc[-5:])), 4),
                "mean_sigma": round(float(a.sigma.mean()), 4)})
    return pd.DataFrame(rows)


def main() -> int:
    os.nice(10)
    truth, n2f = load_truth()
    names = {v: k for k, v in n2f.items()}
    panel, first = build_panel()
    print(f"revision panel: {len(panel)} vintage-state-weeks, "
          f"{len(first)} first-issue rows")
    results, diags = [], {}
    for eval_season in SEASONS:
        print(f"\n=== computing arms: {eval_season} (rolling, K={K_PRIMARY}; "
              f"sensitivities K={K_SENS}) ===", flush=True)
        arms, diag = compute_arms(eval_season, panel, first, names)
        diags[eval_season] = diag
        diag.to_csv(OUT / f"c_traj_{eval_season}.csv", index=False)
        df = score_cells(eval_season, arms, truth)
        df.to_csv(OUT / f"cells_{eval_season}.csv", index=False)
        res = report(eval_season, df, diag)
        results.append(res)
        print(json.dumps(res, indent=2))
    (OUT / "results.json").write_text(json.dumps(results, indent=2))

    print("\n=== activation timing ===")
    act = [activation_summary(s, diags[s], names) for s in SEASONS]
    for a in act:
        print(json.dumps(a))
    (OUT / "activation.json").write_text(json.dumps(act, indent=2))

    print("\n=== c trajectories, 8 most-corrected states (post-break rank) ===")
    traj = trajectories(diags, names)
    print(traj.to_string(index=False))
    traj.to_csv(OUT / "trajectories_top8.csv", index=False)

    print("\n=== VERDICT against the pre-registered kill rule ===")
    by = {r["eval"]: r for r in results}
    moves = {s: by[s]["move_turn_A1"] for s in POST_BREAK}
    k1 = all(m < 5.0 for m in moves.values())
    k2 = any(m < 0.0 for m in moves.values())
    k3 = {r["eval"]: r["width_screen_failures"] for r in results}
    k3_fail = any(v for v in k3.values())
    dnh = by["2023-24"]["move_pooled_A1"]
    k4 = abs(dnh) >= 2.0
    print(f"turn-cell movement, post-break (positive = A1 better): "
          f"{ {k: round(v, 2) for k, v in moves.items()} }")
    print(f"width screen failures by season: {k3}")
    print(f"do-no-harm 2023-24 pooled movement: {dnh:+.3f}% (gate |x| < 2)")
    if k1:
        print("KILL (i): turn movement below 5% in both post-break seasons.")
    if k2:
        print("KILL (ii): A1 worsens turn cells in a post-break season.")
    if k3_fail:
        print("KILL (iii): width screen failed.")
    if k4:
        print("KILL (iv): do-no-harm failed on 2023-24.")
    if not (k1 or k2 or k3_fail or k4):
        print("PASS: movement at or above 5% in at least one post-break "
              "season, none negative, width screen clean in all three "
              "seasons, 2023-24 unharmed.")
    print("\nMechanism check (pre-registered prediction: 2024-25 widens, "
          "2025-26 barely, 2023-24 not at all):")
    for s in SEASONS:
        r = by[s]
        print(f"  {s}: grid w95 A1/A0 = {r['grid_w95_A1']:.4f}, "
              f"cov95 {r['grid_cov95_A0']:.3f} -> {r['grid_cov95_A1']:.3f}; "
              f"mean active sigma {r['mean_sigma_active']:.4f}, "
              f"share at floor {r['share_sigma_at_floor']:.2f}, "
              f"turn cells applied {r['turn_cells_applied_frac']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
