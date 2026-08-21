"""Does the production PF's predictive distribution want to be narrower?

The decomposition says dispersion is ~50% of WIS and the median only ~6%.
Empirical coverage of the 50% interval runs 0.55-0.60 against a nominal 0.50,
so the intervals look too wide. This measures what a pure calibration layer --
one scalar per horizon, scaling every interval around the unchanged median --
would be worth.

    q'(tau) = m + s * (q(tau) - m)

Fitted LEAVE-ONE-SEASON-OUT. `s` for a held-out season is fitted only on the
other seasons, so no season is scored with a multiplier that saw it. This is
the same discipline the ensemble weights are held to, and for the same reason:
an in-sample optimum here would be meaningless.

Run from the repo root with the app venv.
"""
from __future__ import annotations

import json
import pickle
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import ensemble as ens                        # noqa: E402
from app.core.scoring import _baseline_cells, load_truth    # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI          # noqa: E402

STATE = REPO / "app" / "state"
CACHE = Path(__file__).resolve().parent / "cells.pkl"
K = len(PI)
LEVELS = [round(q, 4) for q in PI] + [0.5] + [round(1 - q, 4) for q in PI]


def wis_scaled(qv: np.ndarray, med: float, y: float, s: float) -> float:
    """WIS after scaling every quantile toward/away from the median by s.

    LEVELS is [PI..., 0.5, (1-PI)...] with the tail built in the SAME order as
    PI, so qv[i] and qv[K+1+i] are already the matching (q, 1-q) pair. Do not
    reverse the tail -- doing so pairs the 1% quantile with the 55% quantile
    and silently produces nonsense widths.
    """
    q = med + s * (qv - med)
    lo, hi = q[:K], q[K + 1:]
    a = 2 * np.array(PI)
    width = np.maximum(hi - lo, 0.0)
    pen = np.maximum(lo - y, 0.0) + np.maximum(y - hi, 0.0)
    return float((0.5 * abs(y - med) + np.sum((a / 2) * width + pen)) / (K + 0.5))


def load_cells() -> list:
    if CACHE.is_file():
        print(f"reusing {CACHE.name}")
        return pickle.loads(CACHE.read_bytes())
    truth, n2f = load_truth()
    out = []
    weeks = sorted((STATE / "retro_seal").glob("*/weeks/*/samples.json"))
    print(f"reading {len(weeks)} weeks (one pass, then cached)...", flush=True)
    for wk in weeks:
        season = wk.parents[2].name
        d = json.loads(wk.read_text())
        asof = d["asof"]
        T = pd.Timestamp(asof)
        if "pf" not in d:
            continue
        for loc, samples in d["pf"].items():
            fips = n2f.get(loc)
            if not fips:
                continue
            try:
                qs = ens.member_quantiles_from_samples(samples)
            except Exception:
                continue
            for h in ("1", "2", "3", "4"):
                q = qs.get(h)
                if not q:
                    continue
                y = truth.get((fips, T + timedelta(days=7 * int(h))))
                if y is None or y <= 0 or q.get(0.5, 0) <= 0:
                    continue
                try:
                    qv = np.array([q[l] for l in LEVELS], float)
                except KeyError:
                    continue
                out.append((season, fips, asof, int(h) - 1, qv, float(q[0.5]), float(y)))
    CACHE.write_bytes(pickle.dumps(out))
    print(f"cached {len(out)} cells")
    return out


def main() -> int:
    cells = load_cells()
    seasons = sorted({c[0] for c in cells})
    grid = np.round(np.arange(0.30, 1.61, 0.05), 2)

    # Before trusting a single number: at s=1.0 this must reproduce the frozen
    # formula in flubnf.wis exactly. An earlier version did not, and produced a
    # confident 25% "gain" that was pure indexing error.
    from flubnf.wis import wis as wis_fn
    worst = 0.0
    for (_, _, _, _, qv, med, y) in cells[:2000]:
        mine = wis_scaled(qv, med, y, 1.0)
        theirs = float(wis_fn({l: v for l, v in zip(LEVELS, qv)}, y).wis)
        worst = max(worst, abs(mine - theirs) / max(theirs, 1e-9))
    print(f"agreement with flubnf.wis at s=1.0: max rel. diff {worst:.2e}")
    assert worst < 1e-9, "wis_scaled does not reproduce the frozen formula"

    # baseline WIS per cell, for relWIS
    truth, _ = load_truth()
    bases = {}
    for asof in sorted({c[2] for c in cells}):
        fips = {c[1] for c in cells if c[2] == asof}
        try:
            bases.update(_baseline_cells(asof, fips, truth))
        except Exception:
            pass

    def relwis(sub, s_by_h):
        num = den = 0.0
        for (_, fips, asof, h, qv, med, y) in sub:
            b = bases.get((fips, asof, h))
            if b is None or not np.isfinite(b) or b <= 0:
                continue
            num += wis_scaled(qv, med, y, s_by_h[h])
            den += b
        return num / den if den > 0 else np.nan

    print("\nIn-sample optimum per horizon (diagnostic only, NOT the result):")
    print(f"{'h':>2}{'best s':>9}{'relWIS@s':>11}{'relWIS@1.0':>12}{'gain':>9}")
    for h in range(4):
        sub = [c for c in cells if c[3] == h]
        r1 = relwis(sub, {h: 1.0})
        best = min(grid, key=lambda s: relwis(sub, {h: s}))
        rb = relwis(sub, {h: best})
        print(f"{h+1:2d}{best:9.2f}{rb:11.4f}{r1:12.4f}{100*(r1-rb)/r1:+8.1f}%")

    print("\nLEAVE-ONE-SEASON-OUT (the honest number):")
    print(f"{'held-out season':>16}{'s fitted elsewhere':>21}"
          f"{'relWIS@s':>11}{'relWIS@1.0':>12}{'gain':>9}")
    tot_s = tot_b = 0.0
    for ho in seasons:
        tr = [c for c in cells if c[0] != ho]
        te = [c for c in cells if c[0] == ho]
        if not tr or not te:
            continue
        s_by_h = {}
        for h in range(4):
            sub = [c for c in tr if c[3] == h]
            s_by_h[h] = min(grid, key=lambda s: relwis(sub, {h: s})) if sub else 1.0
        r_s = relwis(te, s_by_h)
        r_1 = relwis(te, {h: 1.0 for h in range(4)})
        print(f"{ho:>16}{str([s_by_h[h] for h in range(4)]):>21}"
              f"{r_s:11.4f}{r_1:12.4f}{100*(r_1-r_s)/r_1:+8.1f}%")
        for (_, fips, asof, h, qv, med, y) in te:
            b = bases.get((fips, asof, h))
            if b is None or not np.isfinite(b) or b <= 0:
                continue
            tot_s += wis_scaled(qv, med, y, s_by_h[h])
            tot_b += b
    print(f"\n  pooled LOSO relWIS with calibration: {tot_s/tot_b:.4f}")
    r1all = relwis(cells, {h: 1.0 for h in range(4)})
    print(f"  pooled relWIS as shipped            : {r1all:.4f}")
    print(f"  pooled gain                         : "
          f"{100*(r1all - tot_s/tot_b)/r1all:+.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
