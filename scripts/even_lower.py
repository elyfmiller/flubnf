"""Even a hub file's 95% bands on the log scale by narrowing the lower half
only.

The upper-tail cap (flubnf/tailcap.py, mode shrink) narrows the quantiles
above the median, so a capped band is wider below the median than above on
the log scale. This step narrows the levels below the median just enough
that the 95% band is no wider below than above: the Model lane's rule B
(docs/team/model-cap-both-halves-2026-11/prereg.txt), computed from the
file itself, wherever the band is wider below.

For a location and horizon with median m, 2.5% quantile lo and 97.5%
quantile hi (lo > 0, m > lo, hi > m), the exponent is

    k = min(1, ln(hi / m) / ln(m / lo))

taken per horizon (default; each horizon's band comes out even) or, with
per_horizon=False, the smallest over the location's horizons (rule B as
registered). Below the median q' = m (q / m) ** k (q = 0 stays 0), in whole
admissions (half to even), each block monotone and never above its median.
The median and every level above it are untouched, so the tail gate, the
hub's population check and the medians read the same as before.

usage: python scripts/even_lower.py <in.csv> <out.csv> [--per-location]
"""
from __future__ import annotations

import math
import sys

import numpy as np
import pandas as pd

TARGET = "wk inc flu hosp"


def exponents(levels: dict, per_horizon: bool = True) -> dict:
    """{horizon: k} for one location. levels: horizon -> {level: value}."""
    ks = {}
    for h, v in levels.items():
        m, lo, hi = v.get(0.5), v.get(0.025), v.get(0.975)
        if m is None or lo is None or hi is None:
            continue
        if lo > 0 and m > lo and hi > m:
            ks[h] = min(1.0, math.log(hi / m) / math.log(m / lo))
    if not per_horizon and ks:
        k = min(ks.values())
        ks = {h: k for h in ks}
    return ks


def even_block(v: dict, k: float) -> dict:
    """One block's levels -> values with the lower half narrowed by k."""
    if k >= 1.0:
        return dict(v)
    m = v[0.5]
    out = {}
    for lev, q in v.items():
        if lev < 0.5 and q > 0:
            out[lev] = float(np.round(m * (q / m) ** k))
        else:
            out[lev] = q
    run = -math.inf
    for lev in sorted(out):
        if lev < 0.5:
            run = max(run, out[lev])
            out[lev] = min(run, m)
    return out


def even_lower(d: pd.DataFrame, per_horizon: bool = True):
    """(the frame with its lower halves evened, [(location, horizon, k)] for
    every block changed). Rows other than the target's quantiles stay as
    they are."""
    d = d.copy()
    d["value"] = d.value.astype(float)
    rows = (d.target == TARGET) & (d.output_type == "quantile")
    lev = pd.to_numeric(d.output_type_id, errors="coerce")
    val = d.value
    changed = []
    for loc, g in d[rows].groupby("location"):
        levels = {h: dict(zip(lev[b.index], val[b.index]))
                  for h, b in g.groupby("horizon")}
        ks = exponents(levels, per_horizon)
        for h, b in g.groupby("horizon"):
            k = ks.get(h, 1.0)
            if k >= 1.0:
                continue
            new = even_block(levels[h], k)
            d.loc[b.index, "value"] = [new[x] for x in lev[b.index]]
            changed.append((loc, h, round(k, 4)))
    return d, changed


def main(argv: list) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, dst = argv[1], argv[2]
    d = pd.read_csv(src, dtype=str)
    out, changed = even_lower(d, per_horizon="--per-location" not in argv)
    v = out.value.astype(float)
    out["value"] = [str(int(x)) if x.is_integer() else repr(x) for x in v]
    out.to_csv(dst, index=False)
    ks = [k for *_, k in changed]
    locs = len({c[0] for c in changed})
    print(f"{src} -> {dst}: lower half narrowed in {len(changed)} blocks, "
          f"{locs} locations"
          + (f"; exponent median {np.median(ks):.2f}, smallest {min(ks):.2f}"
             if ks else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
