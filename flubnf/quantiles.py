"""SHIPPED: the 23 FluSight quantile levels, and QuantileForecast, which
`baseline_forecast.persistence_quantile_forecast` returns.

FluSight takes 23 quantiles; the hub's horizons are -1..3 and this project
submits 0..3 (app/core/submit.py carries the same levels as QUANTILES,
pinned equal by tests/test_quantiles.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Standard 23 FluSight quantile levels.
FLUSIGHT_QUANTILES: tuple[float, ...] = (
    0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50,
    0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.975, 0.99,
)


@dataclass(frozen=True)
class QuantileForecast:
    """Per-horizon quantile arrays. `quantiles` has shape (n_quantiles, n_horizons)."""
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    quantiles: np.ndarray
    point: np.ndarray   # median forecast (one per horizon), for convenience

    def to_dict(self) -> dict:
        out: dict = {}
        for j, h in enumerate(self.horizons):
            out[h] = {
                float(q): float(self.quantiles[i, j])
                for i, q in enumerate(self.quantile_levels)
            }
        return out
