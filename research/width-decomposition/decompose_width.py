"""Build 3 (handoff 2026-08-21 section 5): whose intervals are too wide?

The shipped forecast is an equal-weight quantile average (vincentization) of
the per-state PF-SIHRS filter and the calendar analogue. Quantile averaging is
linear in the quantiles, so at every level

    q_ens(tau) = 0.5 * q_pf(tau) + 0.5 * q_an(tau)

and therefore every INTERVAL WIDTH is exactly the arithmetic mean of the two
member widths:

    w_ens = 0.5 * w_pf + 0.5 * w_an

No refit and no WIS are needed to attribute the ensemble's spread. This script
reads the sealed retrospective (app/state/retro_seal, three seasons) and splits
the ensemble's 50% and 90% interval widths into the two members, by horizon and
by phase, alongside empirical coverage at both levels. Over-width shows up as
coverage ABOVE nominal.

PHASE IS VINTAGE-LEGAL. It is computed only from the truth vintage dated the
same as-of as the forecast (app.core.data.vintage_path), never from the eventual
peak date. The rule is stated in `phase_label` and printed by the script.

Scoring-agreement guard (handoff section 1.5 / methodological rule 4): this
script reports widths, not WIS, but it still binds its own level pairing to the
frozen scorer. For a subsample of cells it re-derives WIS and the dispersion
term from the same quantile dicts and asserts agreement with `flubnf.wis.wis`.
A reversed upper-quantile array is exactly the bug that produced a confident
fake +25% in the first draft of `width_sweep.py`; pairing tau with 1-tau BY
VALUE and checking against the frozen formula is the control for it.

Run from the repo root with the app venv (pandas), not the engine venv:

    ./.venv/bin/python research/width-decomposition/decompose_width.py

Caches parsed cells in width_cells.pkl and phases in phases.pkl; delete them to
re-read the ~12 GB of stored samples (~4 minutes).
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import ensemble as ens                      # noqa: E402
from app.core.data import vintage_path                    # noqa: E402
from app.core.scoring import load_truth                   # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL     # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI        # noqa: E402
from flubnf.wis import wis as wis_fn                      # noqa: E402

HERE = Path(__file__).resolve().parent
RETRO = REPO / "app" / "state" / "retro_seal"
CELLS = HERE / "width_cells.pkl"
PHASES = HERE / "phases.pkl"

# --- the phase rule (vintage-legal; see module docstring) -------------------
WINDOW = 4          # trailing observed weeks used for the slope, ending at T
DEADBAND = 0.10     # |mean weekly log-growth| below this counts as flat
PEAK_FRAC = 0.50    # flat AND at >= this share of the season's running max
ACTIVITY = 0.20     # ... AND at >= this share of the state's PRIOR-season peak

PHASE_ORDER = ["rising", "near-peak", "falling", "low-flat"]
MEMBERS = ["pf", "analogue", "ensemble"]


def season_start(asof: str) -> pd.Timestamp:
    """RunSpec.__post_init__ convention: the season starts on August 1."""
    ts = pd.Timestamp(asof)
    y = ts.year if ts.month >= 8 else ts.year - 1
    return pd.Timestamp(f"{y}-08-01")


def phase_label(g: float, p: float, a: float) -> str:
    """rising / near-peak / falling / low-flat from as-of quantities alone.

    g -- OLS slope of log(y+1) on week index over the last WINDOW observed
         weeks ending at the as-of week (mean weekly log-growth).
    p -- y_T divided by the season's running maximum so far.
    a -- y_T divided by the state's maximum weekly admissions in seasons
         BEFORE this one (settled at the as-of, so still vintage-legal).

    The `a` guard is what stops a flat 3-admissions-a-week September from being
    filed as "near-peak" purely because its own running maximum is also 3.
    """
    if not np.isfinite(g):
        return "unknown"
    if g > DEADBAND:
        return "rising"
    if g < -DEADBAND:
        return "falling"
    if p >= PEAK_FRAC and np.isfinite(a) and a >= ACTIVITY:
        return "near-peak"
    return "low-flat"


def build_phases(asofs: list[str]) -> pd.DataFrame:
    """(asof, fips) -> phase, from the vintage dated that same as-of."""
    if PHASES.is_file():
        print(f"reusing {PHASES.name}")
        return pd.read_pickle(PHASES)
    rows = []
    print(f"labelling phase from {len(asofs)} vintages...", flush=True)
    for a in asofs:
        t = pd.read_csv(vintage_path(a), dtype={"location": str})
        t["location"] = t["location"].str.zfill(2)
        t["date"] = pd.to_datetime(t["date"])
        T, s0 = pd.Timestamp(a), season_start(a)
        prior = t[t.date < s0].groupby("location").value.max()
        cur = t[(t.date >= s0) & (t.date <= T)]
        for fips, grp in cur.groupby("location"):
            y = grp.sort_values("date").value.to_numpy(float)
            y = y[np.isfinite(y)]          # rule 10: missing weeks are missing
            if len(y) < WINDOW:
                rows.append((a, fips, np.nan, np.nan, np.nan, "unknown"))
                continue
            w = np.log(np.maximum(y[-WINDOW:], 0.0) + 1.0)
            g = float(np.polyfit(np.arange(float(WINDOW)), w, 1)[0])
            p = float(y[-1] / max(y.max(), 1e-9))
            H = float(prior.get(fips, np.nan))
            act = float(y[-1] / H) if np.isfinite(H) and H > 0 else np.nan
            rows.append((a, fips, g, p, act, phase_label(g, p, act)))
    df = pd.DataFrame(rows, columns=["asof", "fips", "g", "p", "a", "phase"])
    df.to_pickle(PHASES)
    return df


def widths(q: dict) -> tuple[float, float]:
    """(50% width, 90% width) from a level -> value dict."""
    return q[0.75] - q[0.25], q[0.95] - q[0.05]


def covers(q: dict, y: float) -> tuple[bool, bool]:
    return (q[0.25] <= y <= q[0.75], q[0.05] <= y <= q[0.95])


def wis_parts(q: dict, y: float) -> tuple[float, float]:
    """Independent re-derivation of (WIS, dispersion) from a quantile dict.

    Levels are paired tau <-> 1-tau BY VALUE, not by array position. This exists
    only to be checked against flubnf.wis.wis.
    """
    m = q[0.5]
    total = disp = 0.0
    for tau in PI:
        lo, hi = q[round(tau, 4)], q[round(1.0 - tau, 4)]
        alpha = 2.0 * tau
        w = max(hi - lo, 0.0)
        pen = (2.0 / alpha) * (max(lo - y, 0.0) + max(y - hi, 0.0))
        total += (alpha / 2.0) * (w + pen)
        disp += w
    K = len(PI)
    return (0.5 * abs(y - m) + total) / (K + 0.5), disp / K


def load_cells() -> pd.DataFrame:
    if CELLS.is_file():
        print(f"reusing {CELLS.name}")
        return pd.read_pickle(CELLS)

    truth, n2f = load_truth()
    files = sorted(RETRO.glob("*/weeks/*/samples.json"))
    asofs = sorted({f.parent.name for f in files})
    ph = build_phases(asofs)
    pmap = {(r.asof, r.fips): r.phase for r in ph.itertuples()}

    rows, checked, worst_w, worst_d = [], 0, 0.0, 0.0
    dropped = {"no_fips": 0, "no_truth": 0, "degenerate": 0, "no_member": 0}
    print(f"reading {len(files)} weeks (one pass, then cached)...", flush=True)
    for i, fp in enumerate(files, 1):
        season = fp.parents[2].name
        d = json.loads(fp.read_text())
        asof = d["asof"]
        T = pd.Timestamp(asof)
        pf_all, an_all = d.get("pf", {}), d.get("analogue", {})
        for loc in sorted(set(pf_all) | set(an_all)):
            fips = n2f.get(loc)
            if not fips:
                dropped["no_fips"] += 1
                continue
            try:
                qpf = ens.member_quantiles_from_samples(pf_all.get(loc, {}))
            except Exception:
                qpf = {}
            qan_raw = an_all.get(loc, {})
            for h in ("1", "2", "3", "4"):
                a = qpf.get(h)
                b = qan_raw.get(h)
                if not a or not b:
                    dropped["no_member"] += 1
                    continue
                b = {float(k): float(v) for k, v in b.items()}
                y = truth.get((fips, T + timedelta(days=7 * int(h))))
                if y is None or y <= 0:
                    dropped["no_truth"] += 1
                    continue
                levels = sorted(set(a) & set(b))
                if len(levels) != len(QL):
                    dropped["no_member"] += 1
                    continue
                e = {L: 0.5 * a[L] + 0.5 * b[L] for L in levels}
                if a[0.5] <= 0 or b[0.5] <= 0:
                    dropped["degenerate"] += 1
                    continue
                wa50, wa90 = widths(a)
                wb50, wb90 = widths(b)
                we50, we90 = widths(e)
                ca50, ca90 = covers(a, y)
                cb50, cb90 = covers(b, y)
                ce50, ce90 = covers(e, y)

                # additivity is the whole premise -- assert it, do not assume it
                assert abs(we50 - 0.5 * (wa50 + wb50)) <= 1e-9 * max(we50, 1.0)
                assert abs(we90 - 0.5 * (wa90 + wb90)) <= 1e-9 * max(we90, 1.0)

                if checked < 3000:
                    for q in (a, b, e):
                        mine_w, mine_d = wis_parts(q, y)
                        ref = wis_fn(q, y)
                        worst_w = max(worst_w, abs(mine_w - ref.wis)
                                      / max(ref.wis, 1e-9))
                        worst_d = max(worst_d, abs(mine_d - ref.dispersion)
                                      / max(ref.dispersion, 1e-9))
                    checked += 1

                rows.append((season, asof, fips, int(h),
                             pmap.get((asof, fips), "unknown"), float(y),
                             a[0.5], b[0.5], e[0.5],
                             wa50, wb50, we50, wa90, wb90, we90,
                             ca50, cb50, ce50, ca90, cb90, ce90))
        del d
        if i % 10 == 0:
            print(f"  {i}/{len(files)} weeks, {len(rows)} cells", flush=True)

    print(f"\nagreement with flubnf.wis on {checked} cells x 3 members: "
          f"max rel. diff WIS {worst_w:.2e}, dispersion {worst_d:.2e}")
    assert worst_w < 1e-9, "wis_parts does not reproduce the frozen formula"
    assert worst_d < 1e-9, "dispersion term does not reproduce flubnf.wis"
    print(f"dropped: {dropped}")

    df = pd.DataFrame(rows, columns=[
        "season", "asof", "fips", "h", "phase", "y",
        "m_pf", "m_analogue", "m_ensemble",
        "w50_pf", "w50_analogue", "w50_ensemble",
        "w90_pf", "w90_analogue", "w90_ensemble",
        "c50_pf", "c50_analogue", "c50_ensemble",
        "c90_pf", "c90_analogue", "c90_ensemble"])
    for m in MEMBERS:
        df[f"r50_{m}"] = df[f"w50_{m}"] / df.y
        df[f"r90_{m}"] = df[f"w90_{m}"] / df.y
    df["pf_share50"] = df.w50_pf / (df.w50_pf + df.w50_analogue).replace(0, np.nan)
    df["pf_share90"] = df.w90_pf / (df.w90_pf + df.w90_analogue).replace(0, np.nan)
    df.to_pickle(CELLS)
    print(f"cached {len(df)} cells -> {CELLS.name}")
    return df


# --- reporting -------------------------------------------------------------

def _fmt(df: pd.DataFrame) -> str:
    return df.to_string(float_format=lambda v: f"{v:.3f}")


def block(df: pd.DataFrame, by: list[str], order=None) -> pd.DataFrame:
    """Relative widths (median of width/y) and coverage, per group."""
    g = df.groupby(by, observed=True)
    out = pd.DataFrame({"cells": g.size()})
    for m in MEMBERS:
        out[f"W50 {m}"] = g[f"r50_{m}"].median()
    for m in MEMBERS:
        out[f"cov50 {m}"] = g[f"c50_{m}"].mean()
    for m in MEMBERS:
        out[f"W90 {m}"] = g[f"r90_{m}"].median()
    for m in MEMBERS:
        out[f"cov90 {m}"] = g[f"c90_{m}"].mean()
    out["pf share"] = g.pf_share50.median()
    if order is not None:
        out = out.reindex([o for o in order if o in out.index])
    return out


def pooled_row(df: pd.DataFrame) -> pd.Series:
    d = {"cells": len(df)}
    for m in MEMBERS:
        d[f"W50 {m}"] = df[f"r50_{m}"].median()
    for m in MEMBERS:
        d[f"cov50 {m}"] = df[f"c50_{m}"].mean()
    for m in MEMBERS:
        d[f"W90 {m}"] = df[f"r90_{m}"].median()
    for m in MEMBERS:
        d[f"cov90 {m}"] = df[f"c90_{m}"].mean()
    d["pf share"] = df.pf_share50.median()
    return pd.Series(d, name="POOLED")


def main() -> int:
    df = load_cells()
    known = df[df.phase != "unknown"]

    print("\n" + "=" * 78)
    print("PHASE RULE (vintage-legal, from vintage_path(as-of) only)")
    print("=" * 78)
    print(f"  g = OLS slope of log(y+1) over the last {WINDOW} observed weeks "
          f"ending at the as-of week")
    print(f"  p = y_T / (season's running max so far)")
    print(f"  a = y_T / (state's max weekly admissions in PRIOR seasons)")
    print(f"  rising    : g >  +{DEADBAND}")
    print(f"  falling   : g <  -{DEADBAND}")
    print(f"  near-peak : |g| <= {DEADBAND} and p >= {PEAK_FRAC} "
          f"and a >= {ACTIVITY}")
    print(f"  low-flat  : |g| <= {DEADBAND} otherwise")
    print("  Nothing here uses the eventual peak date.")

    print("\n" + "=" * 78)
    print("A. RELATIVE INTERVAL WIDTH (median of width / observed) AND COVERAGE"
          ", BY HORIZON")
    print("=" * 78)
    t = block(df, ["h"])
    t.loc["POOLED"] = pooled_row(df)
    print(_fmt(t))

    print("\n" + "=" * 78)
    print("B. SAME, BY PHASE (pooled over horizons)")
    print("=" * 78)
    print(_fmt(block(known, ["phase"], PHASE_ORDER)))

    print("\n" + "=" * 78)
    print("C. 50% INTERVAL: PHASE x HORIZON")
    print("=" * 78)
    for what, cols in (("relative width (median width/observed)",
                        [f"r50_{m}" for m in MEMBERS]),
                       ("coverage (nominal 0.50)",
                        [f"c50_{m}" for m in MEMBERS])):
        print(f"\n  {what}")
        agg = "median" if what.startswith("relative") else "mean"
        p = (known.groupby(["phase", "h"], observed=True)[cols]
             .agg(agg).unstack("h")
             .reindex(PHASE_ORDER))
        p.columns = [f"h{h} {c.split('_', 1)[1]}" for c, h in p.columns]
        print(_fmt(p[sorted(p.columns, key=lambda c: (c.split()[1], c))]))

    print("\n" + "=" * 78)
    print("D. ABSOLUTE INTERVAL WIDTH IN ADMISSIONS (mean), BY HORIZON")
    print("=" * 78)
    a = df.groupby("h")[[f"w50_{m}" for m in MEMBERS]
                        + [f"w90_{m}" for m in MEMBERS]].mean()
    a["mean y"] = df.groupby("h").y.mean()
    a.loc["POOLED"] = list(df[[f"w50_{m}" for m in MEMBERS]
                              + [f"w90_{m}" for m in MEMBERS]].mean()) \
        + [df.y.mean()]
    print(_fmt(a))
    print("\n  pooled relative width, sum(width)/sum(observed) "
          "(volume-weighted, so the big states dominate):")
    for m in MEMBERS:
        print(f"    {m:9s} 50%: {df[f'w50_{m}'].sum()/df.y.sum():.3f}"
              f"   90%: {df[f'w90_{m}'].sum()/df.y.sum():.3f}")

    print("\n" + "=" * 78)
    print("E. BY SEASON")
    print("=" * 78)
    print(_fmt(block(df, ["season"])))

    print("\n" + "=" * 78)
    print("F. WHO OWNS THE WIDTH: analogue / PF width ratio")
    print("=" * 78)
    r = pd.DataFrame({
        "cells": known.groupby("phase", observed=True).size(),
        "median w50 an / w50 pf": known.groupby("phase", observed=True)
        .apply(lambda g: (g.w50_analogue / g.w50_pf.replace(0, np.nan))
               .median(), include_groups=False),
        "median w90 an / w90 pf": known.groupby("phase", observed=True)
        .apply(lambda g: (g.w90_analogue / g.w90_pf.replace(0, np.nan))
               .median(), include_groups=False),
        "share of cells analogue wider":
        known.groupby("phase", observed=True)
        .apply(lambda g: float((g.w50_analogue > g.w50_pf).mean()),
               include_groups=False),
    }).reindex(PHASE_ORDER)
    print(_fmt(r))

    print("\n" + "=" * 78)
    print("G. NAMED TURN WINDOWS (the two the handoff cares about)")
    print("=" * 78)
    rows = []
    for label, mask in (
            ("Feb-2024 plateau", df["asof"].str.startswith("2024-02")),
            ("Jan-2025 peak", df["asof"].str.startswith("2025-01")),
            ("near-peak, all seasons", df.phase == "near-peak"),
            ("everything else", ~((df["asof"].str.startswith("2024-02"))
                                  | (df["asof"].str.startswith("2025-01"))
                                  | (df.phase == "near-peak")))):
        sub = df[mask]
        if not len(sub):
            continue
        row = pooled_row(sub)
        row.name = label
        rows.append(row)
    print(_fmt(pd.DataFrame(rows)))
    print("\n  the two windows broken out BY PHASE -- same label, opposite "
          "failure:")
    for win in ("2024-02", "2025-01"):
        sub = df[df["asof"].str.startswith(win)]
        t = sub.groupby("phase", observed=True).agg(
            cells=("y", "size"),
            cov50=("c50_ensemble", "mean"), cov90=("c90_ensemble", "mean"),
            W50_pf=("r50_pf", "median"), W50_an=("r50_analogue", "median"),
            W50_ens=("r50_ensemble", "median"))
        print(f"\n    {win}")
        print("    " + _fmt(t).replace("\n", "\n    "))
    print("\n  ensemble coverage per as-of week, the turn months:")
    per = df.groupby("asof").agg(cells=("y", "size"),
                                 cov50=("c50_ensemble", "mean"),
                                 cov90=("c90_ensemble", "mean"),
                                 W50=("r50_ensemble", "median"))
    keep = per.index.str.startswith(("2024-01", "2024-02", "2024-12",
                                     "2025-01", "2025-02", "2025-12",
                                     "2026-01", "2026-02"))
    print("  " + _fmt(per[keep]).replace("\n", "\n  "))

    print("\n" + "=" * 78)
    print("H. HOW MUCH TOO WIDE: the width multiplier that would hit nominal")
    print("=" * 78)
    print("  DESCRIPTIVE, IN-SAMPLE. Not a fitted object and not shippable --")
    print("  handoff section 6 requires leave-one-season-out for any such")
    print("  scalar, and section 1.5 is the null it must beat. This only")
    print("  restates the coverage excess on a scale you can read.")
    print("  z = (y - median) / width; nominal 50% needs median|z| = 0.5,")
    print("  nominal 90% needs the 90th percentile of |z| = 0.5.")
    mult = []
    for ph in PHASE_ORDER:
        sub = known[known.phase == ph]
        d = {"phase": ph, "cells": len(sub)}
        for m in MEMBERS:
            z = ((sub.y - _median_of(sub, m)) / sub[f"w50_{m}"]).abs()
            d[f"s50 {m}"] = 2.0 * float(np.median(z[np.isfinite(z)]))
        for m in MEMBERS:
            z = ((sub.y - _median_of(sub, m)) / sub[f"w90_{m}"]).abs()
            d[f"s90 {m}"] = 2.0 * float(np.quantile(z[np.isfinite(z)], 0.90))
        mult.append(d)
    d = {"phase": "POOLED", "cells": len(df)}
    for m in MEMBERS:
        z = ((df.y - _median_of(df, m)) / df[f"w50_{m}"]).abs()
        d[f"s50 {m}"] = 2.0 * float(np.median(z[np.isfinite(z)]))
    for m in MEMBERS:
        z = ((df.y - _median_of(df, m)) / df[f"w90_{m}"]).abs()
        d[f"s90 {m}"] = 2.0 * float(np.quantile(z[np.isfinite(z)], 0.90))
    mult.append(d)
    print(_fmt(pd.DataFrame(mult).set_index("phase")))

    print("\n" + "=" * 78)
    print("I. SENSITIVITY: the superseded per-horizon weight freeze")
    print("=" * 78)
    print("  app/state_defaults_ensemble_weights.json still carries the")
    print("  2026-08-17 freeze (PF share 0.4/0.6/0.7/0.8 plus 12 per-state")
    print("  overrides). The seal shipped 50/50. Width is linear in the")
    print("  weights, so the alternative blend costs nothing to evaluate.")
    w = ens.frozen_weights()
    share = np.array([ens.pf_share(w, h - 1, f)
                      for h, f in zip(df.h, df.fips)], float)
    alt50 = share * df.w50_pf + (1 - share) * df.w50_analogue
    alt90 = share * df.w90_pf + (1 - share) * df.w90_analogue
    alt = pd.DataFrame({
        "h": df.h,
        "W50 50/50": df.r50_ensemble,
        "W50 frozen": alt50 / df.y,
        "W90 50/50": df.r90_ensemble,
        "W90 frozen": alt90 / df.y,
    })
    tab = alt.groupby("h").median(numeric_only=True)
    tab.loc["POOLED"] = alt.drop(columns="h").median(numeric_only=True)
    print(_fmt(tab))

    print("\n" + "=" * 78)
    print("J. IS PHASE A STABLE CONDITIONER? (pre-warning for build 4)")
    print("=" * 78)
    print("  Ensemble only. If a phase wants narrower intervals in one season")
    print("  and wider in another, a per-(phase x horizon) scalar fitted")
    print("  leave-one-season-out will cancel, exactly as the global scalar")
    print("  did in handoff section 1.5.")
    rows = []
    for ph in PHASE_ORDER:
        for season in sorted(known.season.unique()):
            sub = known[(known.phase == ph) & (known.season == season)]
            if len(sub) < 50:
                continue
            z50 = ((sub.y - sub.m_ensemble) / sub.w50_ensemble).abs()
            z90 = ((sub.y - sub.m_ensemble) / sub.w90_ensemble).abs()
            rows.append({
                "phase": ph, "season": season, "cells": len(sub),
                "cov50": sub.c50_ensemble.mean(),
                "cov90": sub.c90_ensemble.mean(),
                "s50 wanted": 2.0 * float(np.median(z50[np.isfinite(z50)])),
                "s90 wanted": 2.0 * float(np.quantile(z90[np.isfinite(z90)],
                                                      0.90)),
            })
    j = pd.DataFrame(rows).set_index(["phase", "season"])
    print(_fmt(j))
    print("\n  spread of the wanted 50% multiplier within each phase:")
    sp = j.groupby("phase")["s50 wanted"].agg(["min", "max"])
    sp["range"] = sp["max"] - sp["min"]
    print(_fmt(sp.reindex(PHASE_ORDER)))

    print("\n" + "=" * 78)
    print("K. WHAT ACTUALLY PREDICTS MISCALIBRATION: phase, or the week?")
    print("=" * 78)
    print("  One-way R^2 of the per-cell ensemble coverage indicator on each")
    print("  grouping. The outcome is Bernoulli so the ceiling is low; only")
    print("  the RATIO between rows is meaningful.")
    rows = []
    for keys in (["phase"], ["h"], ["phase", "h"], ["season"],
                 ["phase", "h", "season"], ["fips"], ["asof"], ["asof", "h"]):
        d = {"grouping": "x".join(keys),
             "groups": df.groupby(keys, observed=True).ngroups}
        for lvl in ("c50_ensemble", "c90_ensemble"):
            v = df[lvl].astype(float)
            tot = float(((v - v.mean()) ** 2).sum())
            m = df.groupby(keys, observed=True)[lvl].transform("mean") \
                  .astype(float)
            d[f"R2 {lvl[:3]}"] = 1.0 - float(((v - m) ** 2).sum()) / tot
        rows.append(d)
    print(_fmt(pd.DataFrame(rows).set_index("grouping")))
    return 0


def _median_of(sub: pd.DataFrame, member: str) -> pd.Series:
    """That member's own median forecast for each cell."""
    return sub[f"m_{member}"]


if __name__ == "__main__":
    sys.exit(main())
