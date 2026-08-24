"""Reproduce the variance-components calibration of V_SIG, from truth alone.

This is the computation cited in anchor_math.growth_estimate. It reads only
vintage truth over the gate panel -- no model, no fit, no forecast score -- so
it is not tuning: it estimates how much of the observed spread in weekly
log-growth is signal and how much is negative-binomial counting noise.

    var(g_raw)  =  v_sig  +  v_noise        (independent components)
    v_sig       =  var(g_raw) - median(v_noise)

Measured 2026-08-23, before any fit of this candidate, over 6 states x 85
sealed as-of dates x 3 seasons:

    k = 2:  n 476  var(g_raw) 0.2779  median v_noise 0.1327  ->  v_sig 0.145
    k = 4:  n 462  var(g_raw) 0.0879  median v_noise 0.0132  ->  v_sig 0.075

The member holds R* fixed across the horizon, so the persistent component
(k = 4, 0.075) is the primary and the transient-inclusive one (k = 2, 0.145) is
a registered sensitivity arm.

Run:  ./.venv/bin/python research/slope-anchored/calibrate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from app.core.data import LOCATIONS, vintage_path            # noqa: E402
from flubnf.sihrs_fit import resolve_state                   # noqa: E402

import anchor_math as AM                                     # noqa: E402
import gate                                                  # noqa: E402


def main() -> None:
    rows = []
    for season in gate.SEASONS:
        for asof in gate.season_asofs(season):
            for loc in gate.STATES:
                try:
                    s = resolve_state(loc, truth_csv=vintage_path(asof),
                                      locations_csv=LOCATIONS,
                                      season_start=gate.season_start(season),
                                      as_of=asof)
                except Exception as e:                       # noqa: BLE001
                    rows.append(dict(season=season, asof=asof, location=loc,
                                     k=-1, reason=f"resolve_failed:{e}"[:80]))
                    continue
                for k in (gate.K_PRIMARY, gate.K_ROBUST):
                    ge = AM.growth_estimate(s.observed, s.times, k=k)
                    rows.append(dict(season=season, asof=asof, location=loc,
                                     k=k, g=ge["g_raw"], vn=ge["v_noise"],
                                     reason=ge["reason"],
                                     y=float(s.observed[-1])))
    d = pd.DataFrame(rows)
    (HERE / "out").mkdir(parents=True, exist_ok=True)
    d.to_csv(HERE / "out" / "calibration.csv", index=False)
    print(f"pre-registration {gate.preregistration_hash()}")
    for k in (gate.K_PRIMARY, gate.K_ROBUST):
        g = d[(d.k == k) & (d.reason == "ok")]
        vg, vn = float(g.g.var()), float(g.vn.median())
        print(f"k = {k}: n {len(g)}  var(g_raw) {vg:.4f}  "
              f"median v_noise {vn:.4f}  ->  v_sig {max(vg - vn, 0):.4f}  "
              f"(sd {np.sqrt(max(vg - vn, 0)):.3f})")
        w = gate.V_SIG / (gate.V_SIG + g.vn)
        print(f"        implied shrinkage weight at V_SIG={gate.V_SIG}: "
              f"median {w.median():.3f}, IQR "
              f"[{w.quantile(.25):.3f}, {w.quantile(.75):.3f}]")
    print(f"frozen V_SIG = {gate.V_SIG}  (primary), sensitivity "
          f"{gate.V_SIG_SENS}")


if __name__ == "__main__":
    main()
