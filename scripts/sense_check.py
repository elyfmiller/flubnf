"""OPS: the pre-submission tail gate (Spencer Fox's rule, adopted 2026-10-21).

For every jurisdiction in a FluSight submission file, the 97.5% quantile of
'wk inc flu hosp' at each horizon is measured against the recent level: the
mean of the last three reported weeks in the hub's target data. The file
FAILS when any horizon-3 ratio exceeds the threshold (30x unless given).
The field summary (the typical state's ratio, the 95% band over the median)
is printed beside it, because that summary is what hid the extremes before:
a band over our own median, summarised by the median across states, read
8x on a week whose worst state read 55x against the recent level.

Run it on every file before the submission commit. The hub check
(app.core.hubcheck, scripts/validate_submission.R) says whether the hub
accepts the file; this says whether the file should be sent.

Usage:
    python scripts/sense_check.py <target-hospital-admissions.csv> <file.csv> [<file.csv> ...] [--threshold 30]

Exit status 0 when every file passes, 1 when any fails, 2 on a bad call.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "wk inc flu hosp"
THRESHOLD = 30.0
RECENT_WEEKS = 3
UPPER = 0.975
LOWER = 0.025
HORIZONS = (0, 1, 2, 3)
GATE_HORIZON = 3


def recent_levels(truth: pd.DataFrame, weeks: int = RECENT_WEEKS) -> tuple[pd.Series, pd.Series, list[str]]:
    """(recent level per location, the last reported value per location, the
    dates averaged). The recent level is the mean over the last `weeks`
    reported dates of the whole file, so a location missing a week averages
    what it has."""
    t = truth[["date", "location", "value"]].copy()
    t["value"] = pd.to_numeric(t["value"], errors="coerce")
    dates = sorted(t["date"].dropna().unique())[-weeks:]
    recent = t[t["date"].isin(dates)].groupby("location")["value"].mean()
    last = t[t["date"] == dates[-1]].set_index("location")["value"]
    return recent, last, [str(d) for d in dates]


def ratios(sub: pd.DataFrame, recent: pd.Series) -> dict[int, pd.DataFrame]:
    """Per horizon, a frame indexed by location: upper (the 97.5% quantile),
    median, band (95% band over the median), ratio (upper over the recent
    level; NaN where the recent level is 0 or unknown)."""
    d = sub[(sub["target"] == TARGET) & (sub["output_type"] == "quantile")].copy()
    d["q"] = d["output_type_id"].astype(float)
    d["v"] = pd.to_numeric(d["value"], errors="coerce")
    d["h"] = d["horizon"].astype(int)
    out: dict[int, pd.DataFrame] = {}
    for h in HORIZONS:
        t = d[d["h"] == h].pivot(index="location", columns="q", values="v")
        if t.empty or UPPER not in t.columns:
            continue
        f = pd.DataFrame(index=t.index)
        f["upper"] = t[UPPER]
        f["median"] = t[0.5] if 0.5 in t.columns else np.nan
        lower = t[LOWER] if LOWER in t.columns else np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            f["band"] = ((f["upper"] - lower) / f["median"]).replace([np.inf, -np.inf], np.nan)
            rl = recent.reindex(t.index).astype(float)
            f["ratio"] = (f["upper"] / rl.where(rl > 0)).replace([np.inf, -np.inf], np.nan)
        out[h] = f
    return out


def gate(sub: pd.DataFrame, recent: pd.Series, threshold: float = THRESHOLD) -> tuple[bool, pd.DataFrame, dict[int, pd.DataFrame]]:
    """(passed, the horizon-3 offenders sorted worst first, the per-horizon
    frames). Passed is False when any horizon-3 ratio exceeds `threshold`."""
    by_h = ratios(sub, recent)
    f = by_h.get(GATE_HORIZON)
    if f is None:
        return True, pd.DataFrame(), by_h
    over = f[f["ratio"] > threshold].sort_values("ratio", ascending=False)
    return over.empty, over, by_h


def report(path: Path, truth: pd.DataFrame, threshold: float = THRESHOLD, out=sys.stdout) -> bool:
    recent, last, dates = recent_levels(truth)
    names = truth.drop_duplicates("location").set_index("location")["location_name"] \
        if "location_name" in truth.columns else pd.Series(dtype=str)
    sub = pd.read_csv(path, dtype=str)
    passed, over, by_h = gate(sub, recent, threshold)
    print(f"== {path.name}  (recent level = mean of {dates[0]}..{dates[-1]}; "
          f"threshold {threshold:g}x at horizon {GATE_HORIZON})", file=out)
    for h, f in sorted(by_h.items()):
        states = f.drop(index="US", errors="ignore")
        r, b = states["ratio"], states["band"]
        worst = r.idxmax() if r.notna().any() else "-"
        print(f"   h{h}: 97.5% over recent level, typical state {r.median():.1f}x, "
              f"max {r.max():.0f}x ({names.get(worst, worst)}); "
              f"95% band over median, typical {b.median():.2f}x; "
              f"over {threshold:g}x: {int((f['ratio'] > threshold).sum())}", file=out)
    if passed:
        print("   PASS", file=out)
    else:
        items = [f"{names.get(loc, loc)} {row.ratio:.0f}x (97.5% {row.upper:.0f}, median {row['median']:.0f}, "
                 f"recent {recent.get(loc, float('nan')):.1f}, last {last.get(loc, float('nan')):.0f})"
                 for loc, row in over.iterrows()]
        print(f"   FAIL ({len(items)} at horizon {GATE_HORIZON}): " + "; ".join(items), file=out)
    return passed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], usage=__doc__.split("Usage:\n")[1].split("\n")[0].strip())
    ap.add_argument("truth", type=Path, help="the hub's target-data/target-hospital-admissions.csv")
    ap.add_argument("files", type=Path, nargs="+", help="submission files to gate")
    ap.add_argument("--threshold", type=float, default=THRESHOLD, help=f"horizon-{GATE_HORIZON} ratio that fails the file (default {THRESHOLD:g})")
    a = ap.parse_args(argv)
    if not a.truth.exists():
        print(f"RED: truth file not found: {a.truth}", file=sys.stderr)
        return 2
    truth = pd.read_csv(a.truth, dtype={"location": str})
    status = 0
    for p in a.files:
        if not p.exists():
            print(f"RED: file not found: {p}", file=sys.stderr)
            return 2
        if not report(p, truth, a.threshold):
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
