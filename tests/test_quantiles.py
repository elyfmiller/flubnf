"""Tests for flubnf.quantiles."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.conf_files import FreeParam
from flubnf.fitting import fit
from flubnf.quantiles import (FLUSIGHT_QUANTILES, quantile_forecast,
                              sample_trajectories)
from flubnf.simulate import predict_weekly


def _quick_fit():
    true = {"I0": 0.005, "b0": 0.6, "gamma": 0.2, "mult": 1500.0, "r": 20.0, "t0": 2.0}
    obs = predict_weekly(true, 18) + np.random.default_rng(0).normal(0, 0.3, 18)
    bounds = [
        FreeParam("I0__FREE", 0.001, 0.02),
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("gamma__FREE", 0.05, 0.5),
        FreeParam("mult__FREE", 500, 5000),
        FreeParam("r__FREE", 1, 50),
        FreeParam("t0__FREE", 0, 10),
    ]
    return fit("Q", obs, bounds, popsize=10, max_iter=120, seed=0)


class TestSIRSTrajectoryRoutingG1:
    """G1 regression: the DE quantile path must route SIRS params through the
    SIRS mirror + merge the fixed structural params, not the piecewise mirror."""

    def _sirs_fit(self):
        true = {"b0": 0.2, "db1": 0.8, "tc1": 8.0, "sw": 2.5, "gamma": 0.5,
                "mult": 0.01, "r": 20.0, "I0": 50.0, "N": 1_000_000.0, "omega": 0.0}
        obs = predict_weekly(true, 22, model_type="sirs_logistic")
        fixed = {"tc1": 8.0, "sw": 2.5, "N": 1_000_000.0, "omega": 0.0}
        bounds = [FreeParam("b0__FREE", 0.05, 1.5),
                  FreeParam("db1__FREE", -1.2, 1.2),
                  FreeParam("gamma__FREE", 0.05, 0.9),
                  FreeParam("mult__FREE", 1e-4, 5e-2),
                  FreeParam("r__FREE", 1, 50),
                  FreeParam("I0__FREE", 1.0, 1000.0)]
        return fit("SIRSq", obs, bounds, popsize=10, max_iter=80, seed=0,
                   model_type="sirs_logistic", fixed_params=fixed), fixed

    def test_sirs_trajectories_finite_with_fixed_params(self):
        res, fixed = self._sirs_fit()
        traj = sample_trajectories(res, 24, top_n=20, samples_per_member=10,
                                   seed=0, model_type="sirs_logistic",
                                   fixed_params=fixed)
        finite_rows = (~np.any(~np.isfinite(traj), axis=1)).mean()
        assert finite_rows > 0.9

    def test_sirs_without_fixed_params_is_all_nan(self):
        # Proves the routing matters: SIRS params lacking tc/sw via the SIRS
        # mirror raise -> NaN rows (the latent-bug behavior).
        res, _ = self._sirs_fit()
        traj = sample_trajectories(res, 24, top_n=20, samples_per_member=10,
                                   seed=0, model_type="sirs_logistic",
                                   fixed_params=None)
        assert np.all(~np.isfinite(traj))


class TestClipForecast:
    """Forecast-sanity clip: tame physically-impossible blowups."""

    def _qf(self, q975_h1):
        from flubnf.quantiles import QuantileForecast
        levels = (0.025, 0.5, 0.975)
        # 1 horizon, blowup in the upper quantile.
        quants = np.array([[10.0], [50.0], [q975_h1]])
        return QuantileForecast(horizons=(1,), quantile_levels=levels,
                                quantiles=quants, point=np.array([50.0]))

    def test_clips_blowup_to_cap(self):
        from flubnf.quantiles import clip_forecast
        qf = self._qf(3.8e10)
        out = clip_forecast(qf, cap=43020.0)
        assert out.quantiles.max() == pytest.approx(43020.0)
        # The non-blowup quantiles are untouched.
        assert out.quantiles[0, 0] == pytest.approx(10.0)
        assert out.quantiles[1, 0] == pytest.approx(50.0)

    def test_legitimate_forecast_untouched(self):
        from flubnf.quantiles import clip_forecast
        qf = self._qf(5800.0)  # a real CA-surge upper bound
        out = clip_forecast(qf, cap=43020.0)
        assert out.quantiles.max() == pytest.approx(5800.0)

    def test_floor_at_zero(self):
        from flubnf.quantiles import QuantileForecast, clip_forecast
        qf = QuantileForecast(horizons=(1,), quantile_levels=(0.5,),
                              quantiles=np.array([[-3.0]]), point=np.array([-3.0]))
        out = clip_forecast(qf, cap=100.0)
        assert out.quantiles.min() >= 0.0


class TestSampleTrajectories:
    def test_shape(self):
        res = _quick_fit()
        traj = sample_trajectories(res, n_weeks=20, top_n=20, samples_per_member=10, seed=1)
        assert traj.shape == (200, 20)

    def test_uses_top_n_clamp(self):
        res = _quick_fit()
        # top_n bigger than population should be silently clamped.
        traj = sample_trajectories(res, n_weeks=10, top_n=99999, samples_per_member=5, seed=1)
        assert traj.shape[0] == res.population.shape[0] * 5

    def test_negbin_samples_are_nonnegative_integers(self):
        res = _quick_fit()
        traj = sample_trajectories(res, n_weeks=10, top_n=5, samples_per_member=3, seed=1)
        finite = traj[np.isfinite(traj).all(axis=1)]
        if finite.size > 0:
            assert (finite >= 0).all()
            assert np.allclose(finite, np.round(finite))


class TestQuantileForecast:
    def test_quantile_count_matches_flusight(self):
        res = _quick_fit()
        qf = quantile_forecast(res, n_observed=14, horizons=[1, 2, 3, 4],
                               top_n=20, samples_per_member=20, seed=2)
        assert qf.quantiles.shape == (len(FLUSIGHT_QUANTILES), 4)

    def test_quantiles_are_monotonic_in_q(self):
        res = _quick_fit()
        qf = quantile_forecast(res, n_observed=14, horizons=[1, 2, 3, 4],
                               top_n=20, samples_per_member=20, seed=2)
        # Each column (horizon) should be non-decreasing as q increases.
        for j in range(qf.quantiles.shape[1]):
            col = qf.quantiles[:, j]
            assert (col[:-1] <= col[1:]).all()

    def test_to_dict_returns_per_horizon_dicts(self):
        res = _quick_fit()
        qf = quantile_forecast(res, n_observed=14, horizons=[1, 2, 3, 4],
                               top_n=20, samples_per_member=20, seed=2)
        d = qf.to_dict()
        assert set(d.keys()) == {1, 2, 3, 4}
        for h, qd in d.items():
            assert 0.5 in qd
            assert len(qd) == len(FLUSIGHT_QUANTILES)
