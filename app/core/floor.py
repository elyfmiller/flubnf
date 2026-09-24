"""PRODUCTION: the output floor applied to console-run PF samples
(app/ui/pipeline._run_all).

Predictive-output floor: no forecast cell may be a point mass.

A burned-out fit (weeks of Rt<1) can put every sample on exactly 0; a
zero-width cell scores catastrophically when truth is 1 (such cells once
carried 49% of total WIS). So Poisson(LAM=0.35) noise is added to every
sample: a dead cell keeps median 0 but gains q75=1, q97.5=2; in season the
shift is invisible. Seeded per (location, date), so specs reproduce exactly.
"""
from __future__ import annotations

import math

from app.core import horizons as hz
import numpy as np

from app.core.runs import derive_seed

LAM = 0.35
_FLOOR_REP = 7777  # replicate slot reserved for floor noise, disjoint from fits


def floor_samples(samples_by_h: dict, location: str, date: str,
                  lam: float = LAM, recent=None) -> dict:
    """Add seeded Poisson noise to every predictive sample.

    `samples_by_h` maps horizon -> list/array of admission samples; the
    same structure comes back with noise added. Non-finite samples pass
    through untouched.

    Adaptive rate: when the mass has fully collapsed (q90 = 0 at every
    forecast horizon), a tiny lam would still median at 0 against a summer
    background of 1-4 admissions, so lam = clip(mean(last 4 of `recent`),
    LAM, 5). A healthy in-season fit never triggers this.
    """
    arrs = {h: np.asarray(v, dtype=float) for h, v in samples_by_h.items()}
    # collapse is judged on forecast horizons only: the origin is anchored to
    # the last observation and must not veto the adaptive rate (it still gets noise)
    fins = [a[np.isfinite(a)]
            for h, a in arrs.items() if str(h) != hz.ORIGIN]
    collapsed = all(a.size and np.quantile(a, 0.9) <= 0 for a in fins) \
        and any(a.size for a in fins)
    if collapsed and recent is not None:
        tail = [float(v) for v in list(recent)[-4:] if np.isfinite(v)]
        if tail:
            lam = float(np.clip(np.mean(tail), lam, 5.0))
    rng = np.random.default_rng(derive_seed(location, date, _FLOOR_REP))
    out = {}
    for h in sorted(arrs):
        a = arrs[h]
        noise = rng.poisson(lam, size=a.shape)
        fin = np.isfinite(a)
        b = a.copy()
        b[fin] = a[fin] + noise[fin]
        out[h] = b.tolist()
    return out


def _pois_ppf(level: float, lam: float) -> int:
    cum, k, p = 0.0, 0, math.exp(-lam)
    while True:
        cum += p
        if cum >= level or k > 100:
            return k
        k += 1
        p *= lam / k



def floor_quantiles(q_by_h: dict, lam: float = LAM) -> dict:
    """Deterministic floor for members that arrive as quantiles (analogue):
    each level is lifted to at least the Poisson(lam) quantile, so a flat-zero
    cell gains upper-tail width while legitimate spread passes through."""
    out = {}
    for h, qd in q_by_h.items():
        out[h] = {L: max(float(v), float(_pois_ppf(float(L), lam)))
                  for L, v in qd.items()}
    return out
