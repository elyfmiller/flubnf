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
                  lam: float = LAM) -> dict:
    """Add seeded Poisson(lam) noise to every predictive sample.

    `samples_by_h` maps horizon -> list/array of admission samples; the
    same structure comes back with noise added. Non-finite samples pass
    through untouched.
    """
    rng = np.random.default_rng(derive_seed(location, date, _FLOOR_REP))
    out = {}
    for h in sorted(samples_by_h):
        a = np.asarray(samples_by_h[h], dtype=float)
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
