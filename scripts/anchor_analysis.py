"""Analyse the held-out anchor+damp validation. Written BEFORE the fits landed.

NOTE: always use df["asof"], never df.asof -- DataFrame.asof is a pandas METHOD,
so attribute access silently returns the method instead of the column.

The selection rule is fixed here in code so it cannot be tuned to whichever
answer looks better once the numbers are visible:

  * lam is chosen ONLY on the TRAIN dates, by lowest mean relWIS.
  * the headline is the TEST relWIS at that lam.
  * the train-test gap is reported as the overfitting estimate. The first
    (unvalidated) look scored lam=0.5 at relWIS 1.091 on data that had chosen
    it; if the held-out number is materially worse, that difference IS the
    overfitting, and it gets stated rather than buried.

lam semantics:  x -> base + (x - base)*lam, base = anchored level at the origin.
  lam=0    flat persistence at the anchored level -- model dynamics contribute
           NOTHING. If this wins, the SIHRS dynamics are actively harmful over a
           4-week horizon and that is the finding.
  lam=1    anchoring only, dynamics untouched.
Baselines reported alongside: raw (no post-processing), and FluSight-baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flubnf.quantiles import FLUSIGHT_QUANTILES  # noqa: E402
from flubnf.wis import wis                       # noqa: E402

HUB = Path(os.environ.get("FLUSIGHT_HUB",
                          os.path.expanduser("~/Documents/GitHub/FluSight-forecast-hub")))
TRUTH = HUB / "target-data" / "target-hospital-admissions.csv"
LOCS = HUB / "auxiliary-data" / "locations.csv"
TARGET = "wk inc flu hosp"
TRAIN_DATES = ("2025-12-13", "2026-01-31")
TEST_DATES = ("2025-11-22", "2026-01-10", "2026-02-28")
LAM_GRID = (0.00, 0.25, 0.50, 0.75, 1.00)


def transform(samples: np.ndarray, origin: np.ndarray, last: float,
              lam: float, anchor: bool) -> np.ndarray:
    """Apply anchor and/or damping to one horizon's predictive samples."""
    med_origin = float(np.median(origin))
    if med_origin <= 0:
        return samples
    scale = (last / med_origin) if anchor else 1.0
    x = samples * scale
    if lam is None:
        return x
    base = med_origin * scale
    return np.maximum(base + (x - base) * lam, 0.0)


def build(records: list[dict], truth: dict, n2f: dict, tdf: pd.DataFrame,
          season_start: str) -> pd.DataFrame:
    rows = []
    for r in records:
        if not r.get("ok") or "samples" not in r:
            continue
        f = n2f.get(r["state"])
        if f is None:
            continue
        asof = pd.Timestamp(r["asof"])
        obs = tdf[(tdf.location == f) & (tdf.date >= pd.Timestamp(season_start))
                  & (tdf.date <= asof)]
        if obs.empty:
            continue
        ld = obs.date.max()
        origin = np.asarray(r["samples"]["0"], float)
        origin = origin[np.isfinite(origin)]
        last = float(r["last_observed"])
        for h in (1, 2, 3, 4):
            s = np.asarray(r["samples"][str(h)], float)
            s = s[np.isfinite(s)]
            if not s.size or not origin.size:
                continue
            a = truth.get((f, ld + timedelta(days=7 * h)))
            if a is None:
                continue
            variants = {"raw": transform(s, origin, last, None, False),
                        "anchored": transform(s, origin, last, None, True)}
            for lam in LAM_GRID:
                variants[f"anchor+damp lam={lam:.2f}"] = transform(
                    s, origin, last, lam, True)
            for name, v in variants.items():
                q = {float(ql): float(np.quantile(v, ql)) for ql in FLUSIGHT_QUANTILES}
                try:
                    w = wis(q, a)
                except (KeyError, ValueError):
                    continue
                rows.append({"variant": name, "state": r["state"], "location": f,
                             "asof": r["asof"], "horizon": h - 1, "wis": w.wis,
                             "pinned": bool(r.get("pinned"))})
    return pd.DataFrame(rows)


def baseline_cells(dates, locs_needed, truth) -> pd.DataFrame:
    rows = []
    for asof in dates:
        ref = (pd.Timestamp(asof) + timedelta(days=7)).date().isoformat()
        fp = HUB / "model-output" / "FluSight-baseline" / f"{ref}-FluSight-baseline.csv"
        if not fp.is_file():
            continue
        d = pd.read_csv(fp, dtype={"location": str})
        if "target" not in d.columns:
            continue
        d = d[(d.output_type == "quantile") & (d.target == TARGET)]
        d["location"] = d["location"].str.zfill(2)
        d["output_type_id"] = pd.to_numeric(d.output_type_id, errors="coerce")
        d["target_end_date"] = pd.to_datetime(d.target_end_date)
        for (loc, hz, ted), g in d.groupby(["location", "horizon", "target_end_date"]):
            if hz < 0 or loc not in locs_needed:
                continue
            a = truth.get((loc, ted))
            if a is None:
                continue
            q = {float(x.output_type_id): float(x.value) for x in g.itertuples()
                 if np.isfinite(x.output_type_id)}
            if 0.5 not in q:
                continue
            try:
                rows.append({"variant": "FluSight-baseline", "location": loc,
                             "asof": asof, "horizon": int(hz), "wis": wis(q, a).wis})
            except (KeyError, ValueError):
                pass
    return pd.DataFrame(rows)


def rel(df: pd.DataFrame, base: pd.Series, variant: str) -> tuple:
    g = df[df["variant"] == variant].set_index("k")
    if g.empty:
        return np.nan, np.nan, 0
    b = base.reindex(g.index)
    ok = b.notna()
    return (g.wis[ok].mean() / b[ok].mean(), (g.wis[ok] < b[ok]).mean(), int(ok.sum()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fits", default="backtest_results/anchor_validation.json")
    ap.add_argument("--season-start", default="2025-08-01")
    a = ap.parse_args()

    recs = json.loads(Path(a.fits).read_text())
    tdf = pd.read_csv(TRUTH, dtype={"location": str})
    tdf["location"] = tdf["location"].str.zfill(2)
    tdf["date"] = pd.to_datetime(tdf.date)
    truth = {(r.location, r.date): float(r.value) for r in tdf.itertuples()}
    locs = pd.read_csv(LOCS, dtype={"location": str})
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))

    ours = build(recs, truth, n2f, tdf, a.season_start)
    if ours.empty:
        print("no scorable fits yet"); return
    base_df = baseline_cells(sorted(ours["asof"].unique()), set(ours["location"]), truth)
    allsc = pd.concat([ours, base_df], ignore_index=True)
    allsc["k"] = list(zip(allsc["location"], allsc["asof"], allsc["horizon"]))
    # common cells only
    n_var = allsc["variant"].nunique()
    cnt = allsc.groupby("k")["variant"].nunique()
    common = set(cnt[cnt == n_var].index)
    allsc = allsc[allsc["k"].isin(common)]
    base = allsc[allsc["variant"] == "FluSight-baseline"].set_index("k").wis

    tr = allsc[allsc["asof"].isin(TRAIN_DATES)]
    te = allsc[allsc["asof"].isin(TEST_DATES)]
    btr = base[base.index.map(lambda k: k[1] in TRAIN_DATES)]
    bte = base[base.index.map(lambda k: k[1] in TEST_DATES)]
    print(f"=== HELD-OUT VALIDATION OF anchor+damp ===")
    print(f"  fits used: {ours.drop_duplicates(subset=['state','asof']).shape[0]}"
          f"   common cells: {len(common)}")
    print(f"  TRAIN {TRAIN_DATES}  n={len(btr)}      TEST {TEST_DATES}  n={len(bte)}\n")

    print(f"{'variant':<26}{'TRAIN relWIS':>14}{'TEST relWIS':>13}{'TEST win':>10}")
    print("-" * 63)
    rows = []
    for v in ["raw", "anchored"] + [f"anchor+damp lam={l:.2f}" for l in LAM_GRID]:
        rtr, _, _ = rel(tr, btr, v)
        rte, wte, n = rel(te, bte, v)
        rows.append((v, rtr, rte, wte))
        print(f"{v:<26}{rtr:>14.3f}{rte:>13.3f}{wte:>10.2f}")

    damp = [r for r in rows if r[0].startswith("anchor+damp") and np.isfinite(r[1])]
    if damp:
        best = min(damp, key=lambda r: r[1])          # chosen on TRAIN only
        print(f"\n  lam selected on TRAIN: {best[0]}  (train relWIS {best[1]:.3f})")
        print(f"  >>> HELD-OUT TEST relWIS = {best[2]:.3f}   win rate {best[3]:.2f}")
        print(f"      beats FluSight-baseline: {'YES' if best[2] < 1.0 else 'NO'}")
        print(f"      overfitting estimate (test - train): {best[2]-best[1]:+.3f}")
        raw_te = [r for r in rows if r[0] == "raw"][0][2]
        print(f"      improvement over raw on TEST: {raw_te:.3f} -> {best[2]:.3f} "
              f"({100*(1-best[2]/raw_te):+.0f}%)")
    print("\n  by horizon (TEST, selected lam):")
    if damp:
        for hz in sorted(te["horizon"].unique()):
            s = te[te["horizon"] == hz]
            bb = base[base.index.map(lambda k: k[1] in TEST_DATES and k[2] == hz)]
            g = s[s["variant"] == best[0]].set_index("k")
            b2 = bb.reindex(g.index)
            ok = b2.notna()
            if ok.sum():
                print(f"    h={hz}: relWIS {g.wis[ok].mean()/b2[ok].mean():.3f}  "
                      f"win {(g.wis[ok]<b2[ok]).mean():.2f}")


if __name__ == "__main__":
    main()
