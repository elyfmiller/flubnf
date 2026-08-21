"""What is FluBNF's WIS actually made of?

Motivating question: if you take a point-forecast model and bolt a calibration
layer onto it (run it N times, or wrap a fitted variance around the median),
how much of the score is the model and how much is the calibration layer?

WIS decomposes exactly into three additive pieces (Bracher et al. 2021):

    WIS = [ 0.5*|y-m|  +  sum_k (a_k/2)*(u_k-l_k)  +  sum_k (a_k/2)*penalty_k ]
          -------------   -----------------------     -----------------------
            MEDIAN            DISPERSION                    PENALTY
          all of (K+0.5)

  MEDIAN     depends only on the point forecast.
  DISPERSION depends only on the interval widths -- pure calibration layer.
  PENALTY    is charged when truth falls outside an interval; it depends on
             BOTH, and it is what punishes intervals that are too narrow.

A model supplying only a median controls the first term and, through it, part
of the third. The calibration layer controls the second outright.

Run from the repo root with the app venv.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import ensemble as ens                        # noqa: E402
from app.core.scoring import load_truth                     # noqa: E402
from flubnf.wis import FLUSIGHT_PI_QUANTILES as PI          # noqa: E402

STATE = REPO / "app" / "state"
K = len(PI)


def parts(q: dict, y: float) -> tuple:
    """(median_term, dispersion_term, penalty_term); they sum to WIS."""
    med = 0.5 * abs(y - q[0.5])
    disp = pen = 0.0
    for ql in PI:
        lo, hi = q[round(ql, 4)], q[round(1.0 - ql, 4)]
        a = 2 * ql
        disp += (a / 2.0) * max(hi - lo, 0.0)
        pen += (a / 2.0) * ((2.0 / a) * max(lo - y, 0.0)
                            + (2.0 / a) * max(y - hi, 0.0))
    n = K + 0.5
    return med / n, disp / n, pen / n


def coverage(q: dict, y: float) -> dict:
    """Empirical coverage at the 50%, 80% and 95% central intervals."""
    return {int(round(100 * (1 - 2 * ql))):
            float(q[round(ql, 4)] <= y <= q[round(1 - ql, 4)])
            for ql in (0.25, 0.10, 0.025)}


def main() -> int:
    truth, n2f = load_truth()
    weeks = sorted((STATE / "retro_seal").glob("*/weeks/*/samples.json"))
    if not weeks:
        raise SystemExit("no retro_seal weeks found under app/state")
    print(f"reading {len(weeks)} stored weeks from app/state/retro_seal\n")

    acc = defaultdict(list)
    cov = defaultdict(list)
    for wk in weeks:
        d = json.loads(wk.read_text())
        asof = d["asof"]
        T = pd.Timestamp(asof)
        members = [k for k in d if isinstance(d[k], dict) and k != "asof"]
        for mem in members:
            for loc, samples in d[mem].items():
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
                        m, dd, p = parts(q, y)
                    except KeyError:
                        continue
                    acc[(mem, int(h))].append((m, dd, p))
                    for lvl, hit in coverage(q, y).items():
                        cov[(mem, int(h), lvl)].append(hit)

    if not acc:
        raise SystemExit("no cells scored")

    print("WIS decomposition -- share of total score, by member and horizon")
    print("(MEDIAN = point forecast; DISPERSION = interval width alone;")
    print(" PENALTY = charged when truth escapes the interval)\n")
    print(f"{'member':10}{'h':>3}{'cells':>8}{'WIS':>10}"
          f"{'median%':>10}{'disp%':>9}{'penalty%':>10}"
          f"{'cov50':>8}{'cov80':>8}{'cov95':>8}")
    for (mem, h) in sorted(acc):
        a = np.array(acc[(mem, h)])
        tot = a.sum(axis=0)
        s = tot.sum()
        if s <= 0:
            continue
        c = [np.mean(cov.get((mem, h, lvl), [np.nan])) for lvl in (50, 75, 95)]
        print(f"{mem:10}{h:3d}{len(a):8d}{a.sum(axis=1).mean():10.2f}"
              f"{100*tot[0]/s:10.1f}{100*tot[1]/s:9.1f}{100*tot[2]/s:10.1f}"
              f"{c[0]:8.3f}{c[1]:8.3f}{c[2]:8.3f}")

    print("\npooled over horizons:")
    for mem in sorted({m for m, _ in acc}):
        a = np.vstack([np.array(acc[(m, h)]) for m, h in acc if m == mem])
        tot = a.sum(axis=0)
        s = tot.sum()
        print(f"  {mem:10} median {100*tot[0]/s:5.1f}%   "
              f"dispersion {100*tot[1]/s:5.1f}%   penalty {100*tot[2]/s:5.1f}%"
              f"   (n={len(a)})")
    print("\nDISPERSION + PENALTY is the fraction of the score governed by the")
    print("uncertainty representation rather than by the point forecast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
