"""Tests for flubnf.amcmc (AMCMC traj_noise reader + quantile builder)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from flubnf.amcmc import (anchor_trajectories,
                          quantile_forecast_from_amcmc, read_traj_noise)
from flubnf.quantiles import FLUSIGHT_QUANTILES


def test_read_traj_noise_returns_none_when_missing(tmp_path):
    assert read_traj_noise(tmp_path, "Alabama") is None


def test_read_traj_noise_round_trip(tmp_path):
    """Write a fake traj_noise file in the layout PyBNF produces and read it."""
    runs = tmp_path / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    expected = np.arange(30, dtype=float).reshape(3, 10)
    np.savetxt(runs / "traj_noise_Alabama_H_weekly_chain_0.txt", expected)
    out = read_traj_noise(tmp_path, "Alabama")
    assert out is not None
    np.testing.assert_allclose(out, expected)


def test_quantile_forecast_alignment_with_horizon():
    """horizon h reads from column n_observed + h - 1."""
    rng = np.random.default_rng(0)
    traj = rng.normal(loc=100, scale=10, size=(500, 20))
    qf = quantile_forecast_from_amcmc(traj, n_observed=10, horizons=[1, 2, 3, 4])
    # The median for each horizon should be close to 100 (we drew N(100, 10)).
    median_idx = FLUSIGHT_QUANTILES.index(0.5)
    for j in range(4):
        assert abs(qf.quantiles[median_idx, j] - 100) < 3


def test_quantile_forecast_requires_enough_columns():
    traj = np.zeros((100, 5))
    with pytest.raises(ValueError):
        quantile_forecast_from_amcmc(traj, n_observed=4, horizons=[1, 2, 3])


def test_quantile_forecast_skips_nan_rows():
    traj = np.zeros((10, 12), dtype=float)
    traj[0, 5] = np.nan  # one bad row
    qf = quantile_forecast_from_amcmc(traj, n_observed=8, horizons=[1, 2, 3, 4])
    # No exception, valid quantiles produced.
    assert qf.quantiles.shape == (len(FLUSIGHT_QUANTILES), 4)


class TestAnchorTrajectories:
    def test_multiplicative_anchor_lands_on_observation(self):
        """With lookback=1, anchor matches the last observed value exactly."""
        traj = np.full((5, 6), 50.0)
        observed = np.array([10, 20, 30, 40, 50])  # last_obs = 50
        out = anchor_trajectories(traj, observed, mode="multiplicative",
                                  lookback=1)
        assert np.allclose(out[:, 4], 50)

    def test_multiplicative_scales_future_weeks(self):
        """Underprediction at W=2 by 2x should push future weeks up 2x (lookback=1)."""
        traj = np.array([[10, 20, 30, 40, 50]] * 4, dtype=float)
        observed = np.array([10, 20, 60])  # at W=2, obs=60, sample=30 -> 2x
        out = anchor_trajectories(traj, observed, mode="multiplicative",
                                  lookback=1)
        np.testing.assert_allclose(out[:, 2], 60)
        np.testing.assert_allclose(out[:, 3], 80)
        np.testing.assert_allclose(out[:, 4], 100)

    def test_additive_shift(self):
        traj = np.full((3, 6), 50.0)
        observed = np.array([10, 20, 30])  # at W=2: obs-sample = -20
        out = anchor_trajectories(traj, observed, mode="additive", lookback=1)
        np.testing.assert_allclose(out[:, 2], 30)
        np.testing.assert_allclose(out[:, 3], 30)

    def test_multiplicative_lookback_uses_geo_mean(self):
        """With lookback=3 and a perfectly consistent 2x under-prediction,
        the geo-mean ratio is 2x, so the shift is the same as lookback=1."""
        traj = np.array([[10, 20, 30, 40, 50]] * 4, dtype=float)
        observed = np.array([20, 40, 60])  # obs/sample = 2.0 at each week
        out = anchor_trajectories(traj, observed, mode="multiplicative",
                                  lookback=3)
        # geo-mean of [2,2,2] = 2; future weeks scale by 2.
        np.testing.assert_allclose(out[:, 3], 80)
        np.testing.assert_allclose(out[:, 4], 100)

    def test_multiplicative_lookback_dampens_outlier(self):
        """One noisy week shouldn't dominate when lookback averages 3 weeks."""
        traj = np.array([[10, 20, 30, 40, 50]] * 4, dtype=float)
        # Two weeks at ratio 1.0, one outlier at ratio 10.0.
        observed = np.array([10, 20, 300])  # last ratio = 10x
        out_k1 = anchor_trajectories(traj, observed, mode="multiplicative",
                                     lookback=1, clamp=(0.01, 100.0))
        out_k3 = anchor_trajectories(traj, observed, mode="multiplicative",
                                     lookback=3, clamp=(0.01, 100.0))
        # lookback=1: factor=10; lookback=3 geo-mean: (1*1*10)^(1/3) ≈ 2.15
        assert out_k1[0, 3] > out_k3[0, 3] * 3  # k=1 is much more aggressive

    def test_no_negative_after_anchoring(self):
        traj = np.array([[100, 200, 300, 400]] * 3, dtype=float)
        observed = np.array([10, 20, 30])
        # Additive shift: factor = 30 - 300 = -270; all weeks shift down.
        out = anchor_trajectories(traj, observed, mode="additive")
        assert (out >= 0).all()

    def test_clamp_protects_against_blowup(self):
        """If sample[W] is tiny and obs is large, factor is clamped."""
        traj = np.array([[0.1, 0.2, 0.3, 0.4]] * 3, dtype=float)
        observed = np.array([1, 5, 100])
        out = anchor_trajectories(traj, observed, mode="multiplicative",
                                  clamp=(0.5, 5.0))
        # Without clamp, factor would be 100/0.3 ≈ 333; clamped to 5.
        # So traj[:,2] becomes 0.3 * 5 = 1.5, not 100.
        np.testing.assert_allclose(out[:, 2], 1.5)


class TestPhaseGatedSlopeBlend:
    """The slope_blend correction is suppressed in transition phases
    (NEAR_PEAK, TROUGH) where observed momentum is unreliable."""

    def test_phase_aware_suppresses_blend_at_near_peak(self):
        # NEAR_PEAK series (verified via detect_phase).
        obs = np.array([500, 800, 1000, 1100, 1000, 800], dtype=float)
        # Model growth differs from obs growth so a blend would change the
        # forecast — but phase_aware should suppress it.
        traj = np.array([
            [400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300],
        ] * 4, dtype=float)
        no_blend = anchor_trajectories(
            traj.copy(), obs, mode="multiplicative",
            lookback=3, slope_blend=0.0, phase_aware=False,
        )
        with_phase = anchor_trajectories(
            traj.copy(), obs, mode="multiplicative",
            lookback=3, slope_blend=0.5, phase_aware=True,
        )
        without_phase = anchor_trajectories(
            traj.copy(), obs, mode="multiplicative",
            lookback=3, slope_blend=0.5, phase_aware=False,
        )
        # phase_aware should detect NEAR_PEAK / UNKNOWN and suppress blend.
        np.testing.assert_allclose(with_phase[:, -1], no_blend[:, -1], rtol=1e-9)
        # Without phase-awareness, the values diverge from no_blend.
        assert not np.allclose(without_phase[:, -1], no_blend[:, -1])

    def test_phase_aware_keeps_blend_during_clear_rise(self):
        # Clear exponential rise (obs doubling each week).
        # obs window (last 3): 200, 400, 800 -> obs_growth = 2.0
        obs = np.array([50, 100, 200, 400, 800], dtype=float)
        # Model grows ~1.3x per week: under-predicts the obs growth.
        # Disagreement = log(2.0/1.3) ≈ 0.43, NOT in dead zone.
        traj = np.array([
            [22, 28.6, 37.2, 48.3, 62.9, 81.7, 106.2, 138.1],
        ] * 4, dtype=float)
        no_blend = anchor_trajectories(
            traj.copy(), obs, mode="multiplicative",
            lookback=3, slope_blend=0.0, phase_aware=False,
        )
        with_phase = anchor_trajectories(
            traj.copy(), obs, mode="multiplicative",
            lookback=3, slope_blend=0.5, phase_aware=True,
        )
        # phase_aware keeps blend active during RISING → values DIFFER.
        assert not np.allclose(with_phase[:, -1], no_blend[:, -1])


def test_quantile_forecast_anchored_lands_h0_on_observed():
    """End-to-end with lookback=1: anchored quantile forecast at h=1 lands
    close to obs[W] when the model predicts a constant trajectory."""
    rng = np.random.default_rng(0)
    traj = rng.normal(loc=100, scale=10, size=(500, 10))
    observed = np.array([100, 100, 100, 100, 100, 100, 100, 50])  # W=7, obs=50
    qf = quantile_forecast_from_amcmc(
        traj, n_observed=8, horizons=[1, 2],
        observed=observed, anchor=True, anchor_mode="multiplicative",
        anchor_lookback=1,
    )
    median_idx = list(qf.quantile_levels).index(0.5)
    assert abs(qf.quantiles[median_idx, 0] - 50) < 5
