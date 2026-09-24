"""Tests for flubnf.baseline_forecast."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.baseline_forecast import persistence_quantile_forecast
from flubnf.quantiles import FLUSIGHT_QUANTILES, QuantileForecast
from flubnf.wis import wis as wis_score


# ---------------------------------------------------------------------------
# persistence_quantile_forecast
# ---------------------------------------------------------------------------
class TestPersistence:
    def test_returns_quantile_forecast_with_expected_shape(self):
        observed = np.linspace(10, 100, 8)
        qf = persistence_quantile_forecast(observed, [1, 2, 3, 4])
        assert isinstance(qf, QuantileForecast)
        assert qf.horizons == (1, 2, 3, 4)
        assert qf.quantile_levels == FLUSIGHT_QUANTILES
        assert qf.quantiles.shape == (len(FLUSIGHT_QUANTILES), 4)
        assert qf.point.shape == (4,)

    def test_quantiles_are_monotonic_per_horizon(self):
        observed = np.linspace(10, 100, 10)
        qf = persistence_quantile_forecast(observed, [1, 2, 3, 4], seed=0)
        # Each column (per horizon) must be non-decreasing across quantile rows.
        diffs = np.diff(qf.quantiles, axis=0)
        assert np.all(diffs >= -1e-9)

    def test_quantiles_widen_with_horizon(self):
        """Random-walk variance grows with √h, so the 5–95% PI width at
        h=4 should be wider than at h=1."""
        observed = np.array([100, 110, 120, 130, 140, 150, 160], dtype=float)
        qf = persistence_quantile_forecast(observed, [1, 4], seed=0)
        q05_idx = list(qf.quantile_levels).index(0.05)
        q95_idx = list(qf.quantile_levels).index(0.95)
        width_h1 = qf.quantiles[q95_idx, 0] - qf.quantiles[q05_idx, 0]
        width_h4 = qf.quantiles[q95_idx, 1] - qf.quantiles[q05_idx, 1]
        assert width_h4 > width_h1

    def test_median_close_to_last_observed_at_h1(self):
        """With a random walk in log-space, the median at h=1 should be near
        the last observed value (small lookback shouldn't drift it much)."""
        observed = np.array([50.0] * 8)   # flat history
        qf = persistence_quantile_forecast(observed, [1], seed=0)
        median_idx = list(qf.quantile_levels).index(0.5)
        assert qf.quantiles[median_idx, 0] == pytest.approx(50.0, rel=0.2)

    def test_quantiles_nonnegative(self):
        observed = np.array([1, 2, 3, 2, 1, 0.5, 0.5, 0.5], dtype=float)
        qf = persistence_quantile_forecast(observed, [1, 2, 3, 4], seed=0)
        assert np.all(qf.quantiles >= 0)

    def test_raises_without_enough_observations(self):
        with pytest.raises(ValueError):
            persistence_quantile_forecast(np.array([10.0]), [1, 2, 3])

    def test_seed_reproducibility(self):
        observed = np.linspace(10, 100, 8)
        a = persistence_quantile_forecast(observed, [1, 2, 3, 4], seed=42)
        b = persistence_quantile_forecast(observed, [1, 2, 3, 4], seed=42)
        np.testing.assert_array_equal(a.quantiles, b.quantiles)


# ---------------------------------------------------------------------------
# Integration: baseline beats flat-mean forecaster on its own data
# ---------------------------------------------------------------------------
class TestBaselineIntegration:
    def test_persistence_beats_naive_zero_on_flat_data(self):
        """Sanity: a forecast of last_observed should crush a forecast of 0."""
        observed = np.array([100.0] * 10)
        qf = persistence_quantile_forecast(observed, [1], seed=0)
        # WIS of qf vs actual=100
        qd = {float(q): float(v) for q, v in zip(qf.quantile_levels,
                                                  qf.quantiles[:, 0])}
        wis_persist = wis_score(qd, actual=100.0).wis
        # WIS of a forecast that predicts 0 with no spread
        zero_qd = {float(q): 0.0 for q in qf.quantile_levels}
        wis_zero = wis_score(zero_qd, actual=100.0).wis
        assert wis_persist < wis_zero
