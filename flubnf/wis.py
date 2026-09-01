"""Weighted Interval Score (WIS).

WIS is the standard FluSight evaluation metric. It approximates the
continuous ranked probability score (CRPS) for a quantile forecast.

Definition (Bracher et al. 2021):

    WIS_{alpha_0:alpha_K}(F, y) = (1 / (K + 0.5)) *
        ( 0.5 * |y - m|
          + sum_{k=1..K} (alpha_k / 2) * IS_{alpha_k}(F, y) )

where m is the median forecast, K is the number of prediction intervals,
each alpha_k corresponds to a central (1 - alpha_k) PI with lower bound l_k
and upper bound u_k, and the interval score is

    IS_{alpha}(F, y) =
        (u - l)
        + (2/alpha) * (l - y) * 1{y < l}
        + (2/alpha) * (y - u) * 1{y > u}

For FluSight's 23 quantiles centered on the median, K=11 prediction
intervals are formed by pairing (q, 1-q) for q in {0.01, 0.025, 0.05, ...,
0.45}; alpha_k = 2 * q_k.

Returns non-negative values (0.0 exactly when every quantile equals the observation); lower is better. WIS == |y - point| when there is
no interval uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np


# Default FluSight prediction-interval levels (alpha_k = 2 * q_k).
FLUSIGHT_PI_QUANTILES: tuple[float, ...] = (
    0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
)


@dataclass(frozen=True)
class WISResult:
    wis: float
    dispersion: float    # average (u_k - l_k) term, before weighting
    overprediction: float
    underprediction: float
    n_intervals: int

    @property
    def calibrated(self) -> bool:
        """A purely informational signal — over- and under-prediction terms
        should be roughly equal for a well-calibrated forecast."""
        if self.overprediction + self.underprediction == 0:
            return True
        ratio = min(self.overprediction, self.underprediction) / max(
            self.overprediction, self.underprediction
        )
        return ratio > 0.5


def wis(
    quantiles: Mapping[float, float],
    actual: float,
    *,
    pi_quantiles: Sequence[float] = FLUSIGHT_PI_QUANTILES,
) -> WISResult:
    """Compute WIS for a single (forecast, observation) pair.

    Args:
        quantiles:    dict mapping quantile level (e.g. 0.025) to forecast value.
                      Must include the median (0.5) and matching low/high pairs
                      (q and 1-q) for each PI level in `pi_quantiles`.
        actual:       observed value.
        pi_quantiles: levels q in (0, 0.5) defining each PI (q, 1-q).
    """
    if 0.5 not in quantiles:
        raise ValueError("quantiles must include the median (q=0.5)")
    median = quantiles[0.5]
    K = len(pi_quantiles)

    sum_weighted_is = 0.0
    sum_disp = 0.0
    sum_over = 0.0
    sum_under = 0.0
    for q in pi_quantiles:
        upper_q = 1.0 - q
        l = _lookup(quantiles, q)
        u = _lookup(quantiles, upper_q)
        alpha = 2 * q
        width = max(u - l, 0.0)
        over = (2.0 / alpha) * max(l - actual, 0.0)
        under = (2.0 / alpha) * max(actual - u, 0.0)
        is_alpha = width + over + under
        sum_weighted_is += (alpha / 2.0) * is_alpha
        sum_disp += width
        sum_over += over
        sum_under += under

    abs_err = abs(actual - median)
    numer = 0.5 * abs_err + sum_weighted_is
    score = numer / (K + 0.5)
    return WISResult(
        wis=score,
        dispersion=sum_disp / K,
        overprediction=sum_over / K,
        underprediction=sum_under / K,
        n_intervals=K,
    )


def wis_many(
    forecasts: Iterable[Mapping[float, float]],
    actuals: Iterable[float],
    **kwargs,
) -> list[WISResult]:
    return [wis(f, a, **kwargs) for f, a in zip(forecasts, actuals)]


def _lookup(quantiles: Mapping[float, float], q: float) -> float:
    """Tolerant key lookup — quantile dicts may have float64 keys built from
    np.quantile, which don't always equality-match Python floats."""
    if q in quantiles:
        return quantiles[q]
    # Fallback: nearest within 1e-6.
    for k, v in quantiles.items():
        if abs(float(k) - q) < 1e-6:
            return v
    raise KeyError(f"quantile level {q} not in forecast dict; "
                   f"have {sorted(quantiles.keys())[:5]}...")
