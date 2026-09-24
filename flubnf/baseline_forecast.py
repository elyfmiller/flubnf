"""SHIPPED (console custom-dataset scoring: app/core/custom_run.py): the symmetrised additive random-walk persistence baseline.

The relWIS denominator for "Run on dataset" and for dataset replay, where
the FluSight-baseline has no cells. It is built as the official
`FluSight-baseline` is: a symmetrised ADDITIVE random walk on week-over-week
differences, returned as a `QuantileForecast`.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from .quantiles import FLUSIGHT_QUANTILES, QuantileForecast


def persistence_quantile_forecast(
    observed: np.ndarray,
    horizons: Sequence[int],
    *,
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
    lookback: int = 6,
    n_samples: int = 2000,
    seed: int = 0,
    epsilon: float = 0.5,
) -> QuantileForecast:
    """Symmetrised ADDITIVE random-walk persistence baseline.

    Matches the FluSight-baseline's construction: sample h week-over-week
    DIFFERENCES (not log-ratios), symmetrised (both +d and -d, so no drift),
    add them to the last observation, and truncate at zero. Not a log-ratio
    walk: that extrapolated growth exponentially (relWIS 2.555 vs 1.133 on
    2025-26).

    `lookback` bounds the difference window; `epsilon` is kept only for API
    compatibility.
    """
    obs = np.asarray(observed, dtype=float)
    obs = obs[np.isfinite(obs)]
    if len(obs) < 2:
        raise ValueError("persistence baseline needs at least 2 observed values")

    last = float(obs[-1])
    win = obs[-(lookback + 1):] if len(obs) >= lookback + 1 else obs
    diffs = np.diff(win)
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        # Two-week edge case: a small symmetric step so quantiles do not
        # collapse to a point mass.
        diffs = np.array([-1.0, 0.0, 1.0])
    # Symmetrise: zero drift is the defining property of a naive reference.
    steps_pool = np.concatenate([diffs, -diffs])

    rng = np.random.default_rng(seed)
    q_levels = np.array(quantile_levels, dtype=float)
    quants = np.empty((len(q_levels), len(horizons)), dtype=float)
    point = np.empty(len(horizons), dtype=float)

    for j, h in enumerate(horizons):
        h = int(h)
        if h < 1:
            samples = np.full(n_samples, last, dtype=float)
        else:
            steps = rng.choice(steps_pool, size=(n_samples, h), replace=True)
            samples = np.clip(last + np.sum(steps, axis=1), 0.0, None)
        quants[:, j] = np.quantile(samples, q_levels)
        point[j] = float(np.quantile(samples, 0.5))

    return QuantileForecast(
        horizons=tuple(int(h) for h in horizons),
        quantile_levels=tuple(quantile_levels),
        quantiles=quants,
        point=point,
    )
