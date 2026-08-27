"""Predictive-output floor: no forecast cell may be a point mass.

The failure this prevents (seen live, Arkansas 2026-07-04): twelve summer
weeks of Rt<1 decay the fitted I compartment to ~nothing, the NB observation
mean goes to ~0, and all 10,000 predictive samples land on exactly 0 at every
horizon. A zero-width cell scores catastrophically the moment truth is 1 --
historically 0.23% of such cells carried 49% of total WIS.

The floor superimposes Poisson(LAM) reporting noise on every sample. With
LAM=0.35 a degenerate cell keeps median 0 (correct in a dead week: P(0)=.70)
but gains q75=1 and q97.5=2 -- minimal width, bought at trivial cost when
truth is 0. In season the shift (+0.35 mean against counts in the hundreds)
is invisible. Draws are seeded per (location, date) so identical specs
reproduce bit-for-bit.
"""
from __future__ import annotations

import math

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

    Adaptive rate: when the model's predictive mass has fully collapsed
    (q90 = 0 at every horizon -- a burned-out epidemic, no importation
    term), a fixed tiny lam still medians at 0, which contradicts the
    observed summer background (sporadic 1-4 admissions most weeks). In
    that case the floor takes its rate from `recent` (last observed
    values): lam = clip(mean(last 4), LAM, 5). Arkansas July: recent
    1,1,4,0 -> Poisson(1.5) -> median 1, q97.5 ~4. A healthy in-season
    fit never triggers the adaptive branch.
    """
    arrs = {h: np.asarray(v, dtype=float) for h, v in samples_by_h.items()}
    # The collapse test looks at FORECAST horizons only. The origin ("0")
    # is multiplicatively anchored to the last observed value, so any
    # nonzero final week kept `collapsed` False even when every forecast
    # horizon was flat zero -- suppressing the adaptive branch in exactly
    # the dead-week case the docstring above promises to fix (audit
    # finding). The origin still receives the floor's noise below; it just
    # no longer vetoes the rate decision.
    fins = [a[np.isfinite(a)]
            for h, a in arrs.items() if str(h) != "0"]
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
