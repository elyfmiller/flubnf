"""Settling time of FluSight NHSN admissions: weeks from first issue until
the vintage value is within 5% of the final (latest-vintage) value.

Also reports the share of revision mass by lag, which is what "moving
anchors" actually are.

Run from repo root with the app venv.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from app.core.data import vintages, vintage_path  # noqa: E402


def season_of(d) -> str:
    ts = pd.Timestamp(d)
    y = ts.year if ts.month >= 8 else ts.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def main() -> int:
    vs = vintages()
    print(f"loading {len(vs)} vintages...", flush=True)
    # (loc, week) -> list of (asof, value) in issue order
    series = defaultdict(list)
    latest = None
    for v in vs:
        asof = pd.Timestamp(v)
        df = pd.read_csv(vintage_path(v), dtype={"location": str},
                         usecols=["location", "date", "value"])
        df["location"] = df["location"].str.zfill(2)
        df["date"] = pd.to_datetime(df["date"])
        df = df[(df.location != "US") & df.value.notna() & (df.value > 0)
                & (df.date <= asof)]
        for r in df.itertuples():
            series[(r.location, pd.Timestamp(r.date))].append((asof, float(r.value)))
        latest = df
    settled = {(r.location, pd.Timestamp(r.date)): float(r.value)
               for r in latest.itertuples()}

    # For each (loc, week) that has a settled value and at least one issue:
    # lag 0 = first vintage that contains this week.
    # Find first lag (in issues, converted to weeks) at which |y/final - 1| <= 0.05
    # AND stays there (last crossing).
    lags_to_95 = []          # (season, lag_weeks)
    still_open = []          # never reached 95% by latest
    # revision mass: |Δ| at each lag, as share of total |Δ| from first to final
    mass = defaultdict(list)  # lag_weeks -> |delta|
    first_ratio = defaultdict(list)
    path_ratio = defaultdict(list)  # lag -> list of y_lag/final

    for key, issues in series.items():
        loc, week = key
        final = settled.get(key)
        if final is None or final <= 0:
            continue
        seas = season_of(week)
        if seas not in ("2023-24", "2024-25", "2025-26"):
            continue
        # unique as-ofs, sorted; value at each = last write in that vintage
        by_asof = {}
        for asof, val in issues:
            by_asof[asof] = val
        asofs = sorted(by_asof)
        first_asof = asofs[0]
        # lag in weeks from FIRST issue, using vintage dates
        vals = []
        for asof in asofs:
            lag_w = int(round((asof - first_asof).days / 7.0))
            vals.append((lag_w, by_asof[asof]))
        # collapse duplicate lags (keep last)
        d = {}
        for lag, val in vals:
            d[lag] = val
        lags = sorted(d)
        y0 = d[lags[0]]
        first_ratio[seas].append(y0 / final)
        # revision steps: consecutive vintage changes attributed to that lag
        prev = y0
        for lag in lags[1:]:
            mass[lag].append(abs(d[lag] - prev))
            prev = d[lag]
        mass[0].append(abs(y0 - 0))  # not used; skip
        for lag, val in d.items():
            path_ratio[(seas, lag)].append(val / final)

        # first lag at which within 5% AND all later issues stay within 5%
        settled_at = None
        for i, lag in enumerate(lags):
            rest = [d[l] for l in lags[i:]]
            if all(abs(v / final - 1.0) <= 0.05 for v in rest):
                settled_at = lag
                break
        if settled_at is None:
            still_open.append((seas, loc, week, d[lags[-1]] / final, lags[-1]))
        else:
            lags_to_95.append((seas, settled_at, y0 / final))

    print(f"\ncells scored: {len(lags_to_95)} settled to 5%; "
          f"{len(still_open)} still outside 5% at latest vintage")

    print("\n=== Weeks from FIRST ISSUE until within 5% of final AND staying there ===")
    print(f"{'season':>10}{'n':>7}{'median':>8}{'p75':>7}{'p90':>7}"
          f"{'% lag0':>9}{'% by 1w':>9}{'% by 2w':>9}{'% by 4w':>9}")
    by = defaultdict(list)
    for seas, lag, _ in lags_to_95:
        by[seas].append(lag)
    by["ALL"] = [lag for _, lag, _ in lags_to_95]
    for seas in ("2023-24", "2024-25", "2025-26", "ALL"):
        a = np.array(by[seas], float)
        def pct(k):
            return 100 * (a <= k).mean()
        print(f"{seas:>10}{len(a):7d}{np.median(a):8.1f}{np.percentile(a,75):7.1f}"
              f"{np.percentile(a,90):7.1f}{pct(0):9.1f}{pct(1):9.1f}"
              f"{pct(2):9.1f}{pct(4):9.1f}")

    print("\n=== Median (p10, p90) of vintage/final at each lag, by season ===")
    print(f"{'lag':>5}", end="")
    for seas in ("2023-24", "2024-25", "2025-26"):
        print(f"{seas:>22}", end="")
    print()
    for lag in range(0, 9):
        print(f"{lag:5d}", end="")
        for seas in ("2023-24", "2024-25", "2025-26"):
            r = path_ratio.get((seas, lag), [])
            if len(r) < 30:
                print(f"{'n='+str(len(r)):>22}", end="")
                continue
            a = np.array(r)
            print(f"{np.median(a):6.3f} ({np.percentile(a,10):.3f}-{np.percentile(a,90):.3f})"
                  f"{'':>0}", end="")
            print(f" n={len(a):4d}", end="")
        print()

    # Conditional: among cells whose FIRST issue was < 0.95 of final,
    # how long to settle? That's the actual incomplete-report question.
    print("\n=== Same, but ONLY cells whose first issue was < 95% of final ===")
    print(f"{'season':>10}{'n':>7}{'median wks':>12}{'p75':>7}{'p90':>7}{'% by 1w':>9}{'% by 2w':>9}")
    by2 = defaultdict(list)
    for seas, lag, r0 in lags_to_95:
        if r0 < 0.95:
            by2[seas].append(lag)
    for seas in ("2023-24", "2024-25", "2025-26"):
        a = np.array(by2[seas], float)
        if len(a) < 20:
            print(f"{seas:>10}  n={len(a)}")
            continue
        print(f"{seas:>10}{len(a):7d}{np.median(a):12.1f}{np.percentile(a,75):7.1f}"
              f"{np.percentile(a,90):7.1f}{100*(a<=1).mean():9.1f}{100*(a<=2).mean():9.1f}")

    print("\n=== Still unfixed at latest vintage (ratio to final) ===")
    from collections import Counter
    print("  by season:", dict(Counter(s for s, *_ in still_open)))
    if still_open:
        rats = [r for *_, r, _ in still_open]
        print(f"  their current/final: median {np.median(rats):.3f}  "
              f"p10 {np.percentile(rats,10):.3f}")

    print("\nFirst-issue completeness (all cells):")
    for seas, rs in first_ratio.items():
        a = np.array(rs)
        print(f"  {seas}: median {np.median(a):.3f}  p10 {np.percentile(a,10):.3f}  "
              f"share first<0.95 {(a<0.95).mean():.1%}  n={len(a)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
