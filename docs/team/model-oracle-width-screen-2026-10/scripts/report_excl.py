"""The trajectory-exclusion arm's readings (AMENDMENT2_EXCL.md section 4)
from exclude_arm.py's output.

    report_excl.py <X.pkl> [--boot 2000]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

import report as R

ORDER = ["none", "clip 15x", "shrink 15x", "shrink 10x",
         "X40", "X30", "X20", "X15", "X40+shrink 15x"]


def arm(c: pd.DataFrame, rule: str, variant: str) -> pd.DataFrame:
    v = "stored" if rule in ("none", "clip 15x", "shrink 15x", "shrink 10x") else variant
    return c[(c.rule == rule) & (c.variant == v)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("x")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    X = pd.read_pickle(a.x)
    c, dr, rt = X["cells"], X["drops"], X["round_trip"]
    c["early"] = pd.to_datetime(c["asof"]).dt.month.isin([9, 10, 11])
    print(f"{a.x}: {c['asof'].nunique()} weeks, {len(arm(c, 'none', ''))} cells per rule")
    print(f"check B' (XP round trip, no limit): {int(rt.cells_differ.sum())} of {int(rt.cells.sum())} "
          f"cells differ, |dWIS| {rt.wis_abs_change.sum():.2f} of {rt.wis_total.sum():.0f}")
    seasons = sorted(c.season.unique())
    for variant in ("XP", "XS"):
        print(f"\n=== {variant} ({'primary: before the narrowing' if variant == 'XP' else 'secondary: on the stored samples'}) ===")
        print(f"{'rule':16s} relWIS    log   c50   c80   c95 |  >30x h3/rec h3/med | "
              + " ".join(f"{s:>7s}" for s in seasons) + " Sep-Nov    rest |   h0    h1    h2    h3")
        for rule in ORDER:
            x = arm(c, rule, variant)
            p, g = R.pooled(x), R.gate(x)
            bys = " ".join(f"{R.pooled(x[x.season == s])['rel']:7.3f}" for s in seasons)
            bh = " ".join(f"{R.pooled(x[x.horizon == h])['rel']:.3f}" for h in range(4))
            print(f"{rule:16s} {p['rel']:.3f}  {p['log']:.3f}  {p['c50']:.2f}  {p['c80']:.2f}  {p['c95']:.2f} | "
                  f"{100 * g['over30']:4.1f}% {g['tail_med']:5.1f} {g['band_med']:6.2f} | {bys} "
                  f"{R.pooled(x[x.early])['rel']:7.3f} {R.pooled(x[~x.early])['rel']:7.3f} | {bh}")
        print(f"\nweek-cluster bootstrap ({a.boot}), natural | log, all 84 weeks and September to November:")
        for rule in ORDER[4:]:
            x = arm(c, rule, variant)
            for ref in ("none", "clip 15x", "shrink 15x"):
                y = arm(c, ref, variant)
                d = R.boot_diff(x, y, a.boot)
                e = R.boot_diff(x[x.early], y[y.early], a.boot)
                print(f"  {rule:15s} minus {ref:10s} {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] | {d[3]:+.4f} "
                      f"[{d[4]:+.4f}, {d[5]:+.4f}]   Sep-Nov {e[0]:+.4f} [{e[1]:+.4f}, {e[2]:+.4f}] | "
                      f"{e[3]:+.4f} [{e[4]:+.4f}, {e[5]:+.4f}]")
        print("\npaths dropped per location-week:")
        none = arm(c, "none", variant)
        h3 = none[none.horizon == 3][["asof", "location", "tail_over_recent"]]
        for n in (40, 30, 20, 15):
            d = dr[(dr.n == n) & (dr.variant == variant)].copy()
            d["share"] = d.dropped / d.n_paths
            m = d.merge(h3, on=["asof", "location"], how="left")
            hot = m[m.tail_over_recent > 30]
            deg = d[d.degenerate]
            print(f"  X{n}: median {100 * d.share.median():.3f}%, 90th {100 * d.share.quantile(.9):.2f}%, "
                  f"max {100 * d.share.max():.1f}% ({d.loc[d.share.idxmax(), 'location']} "
                  f"{d.loc[d.share.idxmax(), 'asof']}); over 1% {int((d.share > .01).sum())}, "
                  f"over 10% {int((d.share > .10).sum())}, over 50% {int((d.share > .50).sum())} "
                  f"of {len(d)}; under 0.1% {100 * (d.share < .001).mean():.1f}%; "
                  f"in the h3 >30x location-weeks ({len(hot)}) median {100 * hot.share.median():.1f}%; "
                  f"degenerate (kept all) {len(deg)}"
                  + (f": {', '.join(f'{r.location} {r.asof}' for r in deg.head(8).itertuples())}" if len(deg) else ""))
        print("\nthe median's move (X median over the none median per cell; cells with a positive none median):")
        base = none.set_index(["asof", "location", "horizon"])["median"]
        for rule in ("X40", "X30", "X20", "X15", "X40+shrink 15x"):
            x = arm(c, rule, variant).set_index(["asof", "location", "horizon"])["median"]
            r = (x / base.reindex(x.index)).where(base.reindex(x.index) > 0).dropna()
            out = []
            for hs, lab in (([3], "h3"), ([0, 1, 2], "h0-h2")):
                rr = r[r.index.get_level_values("horizon").isin(hs)]
                w = rr.idxmin()
                out.append(f"{lab} median {rr.median():.3f}, 10th {rr.quantile(.1):.3f}, 1st {rr.quantile(.01):.3f}, "
                           f"worst {rr.min():.3f} ({w[1]} {w[0]} h{w[2]}); unchanged {100 * (rr == 1).mean():.0f}%, "
                           f"within 1% {100 * ((rr - 1).abs() < .01).mean():.0f}%")
            print(f"  {rule:15s} " + " | ".join(out))


if __name__ == "__main__":
    main()
