"""Tests for flubnf.baseline_forecast."""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.baseline_forecast import (blend_quantile_forecasts,
                                       persistence_quantile_forecast,
                                       recommend_baseline_blend,
                                       rolling_mean_quantile_forecast)
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
# rolling_mean_quantile_forecast
# ---------------------------------------------------------------------------
class TestRollingMean:
    def test_point_matches_window_mean(self):
        observed = np.array([10, 20, 30, 40, 50], dtype=float)
        qf = rolling_mean_quantile_forecast(observed, [1], window=3, seed=0)
        # Window mean = (30 + 40 + 50) / 3 = 40. The h=1 median is sampled
        # around mean, so close to 40.
        median_idx = list(qf.quantile_levels).index(0.5)
        assert qf.quantiles[median_idx, 0] == pytest.approx(40.0, rel=0.15)

    def test_quantiles_monotonic_and_widen_with_horizon(self):
        observed = np.array([10, 20, 30, 40, 50, 60], dtype=float)
        qf = rolling_mean_quantile_forecast(observed, [1, 4], window=4, seed=0)
        assert np.all(np.diff(qf.quantiles, axis=0) >= -1e-9)
        q05 = list(qf.quantile_levels).index(0.05)
        q95 = list(qf.quantile_levels).index(0.95)
        assert (qf.quantiles[q95, 1] - qf.quantiles[q05, 1]) > \
               (qf.quantiles[q95, 0] - qf.quantiles[q05, 0])

    def test_flat_window_still_has_nonzero_spread(self):
        """If the last `window` weeks are identical, the empirical std is
        0 but we must still produce a usable spread."""
        observed = np.array([100.0] * 6)
        qf = rolling_mean_quantile_forecast(observed, [1, 4], window=4, seed=0)
        q05 = list(qf.quantile_levels).index(0.05)
        q95 = list(qf.quantile_levels).index(0.95)
        assert qf.quantiles[q95, 0] > qf.quantiles[q05, 0]

    def test_raises_without_enough_observations(self):
        with pytest.raises(ValueError):
            rolling_mean_quantile_forecast(np.array([10.0]), [1, 2])


# ---------------------------------------------------------------------------
# blend_quantile_forecasts
# ---------------------------------------------------------------------------
def _qf(values: np.ndarray, horizons: tuple[int, ...]) -> QuantileForecast:
    """Build a QuantileForecast with a fixed quantile grid."""
    levels = FLUSIGHT_QUANTILES
    quants = np.tile(values[:, None], (1, len(horizons)))
    return QuantileForecast(
        horizons=horizons, quantile_levels=levels,
        quantiles=quants, point=np.full(len(horizons), values[len(levels)//2]),
    )


class TestBlend:
    def test_weight_zero_returns_primary(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        b = _qf(np.linspace(50, 200, len(FLUSIGHT_QUANTILES)), (1, 2))
        out = blend_quantile_forecasts(a, b, weight=0.0)
        np.testing.assert_array_equal(out.quantiles, a.quantiles)

    def test_weight_one_returns_secondary(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        b = _qf(np.linspace(50, 200, len(FLUSIGHT_QUANTILES)), (1, 2))
        out = blend_quantile_forecasts(a, b, weight=1.0)
        np.testing.assert_array_equal(out.quantiles, b.quantiles)

    def test_half_weight_is_average(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        b = _qf(np.linspace(50, 200, len(FLUSIGHT_QUANTILES)), (1, 2))
        out = blend_quantile_forecasts(a, b, weight=0.5)
        np.testing.assert_allclose(out.quantiles,
                                    0.5 * (a.quantiles + b.quantiles))

    def test_blend_preserves_monotonicity(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        b = _qf(np.linspace(20, 80, len(FLUSIGHT_QUANTILES)), (1, 2))
        out = blend_quantile_forecasts(a, b, weight=0.3)
        assert np.all(np.diff(out.quantiles, axis=0) >= -1e-9)

    def test_mismatched_horizons_raises(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        b = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2, 3))
        with pytest.raises(ValueError, match="horizons"):
            blend_quantile_forecasts(a, b, weight=0.5)

    def test_weight_out_of_range_raises(self):
        a = _qf(np.linspace(0, 100, len(FLUSIGHT_QUANTILES)), (1, 2))
        with pytest.raises(ValueError):
            blend_quantile_forecasts(a, a, weight=1.5)
        with pytest.raises(ValueError):
            blend_quantile_forecasts(a, a, weight=-0.1)


# ---------------------------------------------------------------------------
# recommend_baseline_blend
# ---------------------------------------------------------------------------
class TestRecommendBlend:
    def test_no_recommendation_when_model_is_winning(self):
        assert recommend_baseline_blend([5, 5, 5], [20, 20, 20]) is None

    def test_no_recommendation_when_short_history(self):
        assert recommend_baseline_blend([100], [10]) is None
        assert recommend_baseline_blend([100, 100], [10, 10]) is None

    def test_no_recommendation_when_one_week_is_fine(self):
        """Threshold requires *every* recent week to be bad."""
        # Last 3 weeks: ratios 2.0, 0.9, 2.0 — the 0.9 means hold.
        m = [20.0, 9.0, 20.0]
        b = [10.0, 10.0, 10.0]
        assert recommend_baseline_blend(m, b, ratio_threshold=1.25) is None

    def test_recommends_blend_when_consistently_losing(self):
        # Every week, model WIS = 2× baseline; that triggers.
        m = [20.0, 20.0, 20.0]
        b = [10.0, 10.0, 10.0]
        w = recommend_baseline_blend(m, b, ratio_threshold=1.25)
        assert w is not None
        assert 0.2 <= w <= 0.5

    def test_recommendation_caps_at_max_blend(self):
        m = [100.0, 100.0, 100.0]
        b = [10.0, 10.0, 10.0]
        w = recommend_baseline_blend(m, b, max_blend=0.5)
        assert w == 0.5

    def test_non_finite_inputs_hold(self):
        assert recommend_baseline_blend(
            [20, float("nan"), 20], [10, 10, 10],
        ) is None

    def test_zero_baseline_holds(self):
        # Division-safe: if baseline is 0, we can't compute ratios.
        assert recommend_baseline_blend(
            [20, 20, 20], [10, 0, 10],
        ) is None


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


# ---------------------------------------------------------------------------
# score_submissions_vs_baselines
# ---------------------------------------------------------------------------
class TestScoreSubmissionsVsBaselines:
    def _make_target(self, tmp_path, dates_values: list[tuple[str, str, float]]):
        import pandas as pd
        df = pd.DataFrame(
            [{"date": d, "location": fips, "location_name": "x",
              "value": v, "weekly_rate": 0.0}
             for d, fips, v in dates_values]
        )
        p = tmp_path / "target.csv"
        df.to_csv(p, index=False)
        return p

    def _make_submission(self, tmp_path, ref_date: str, fips: str,
                         horizon: int, target_end: str, median: float):
        """Write a minimal FluSight submission CSV with all 23 quantiles
        clustered around `median`."""
        import pandas as pd
        rows = []
        for q in FLUSIGHT_QUANTILES:
            # narrow band around median for easy scoring
            offset = (q - 0.5) * 10.0
            rows.append({
                "reference_date": ref_date,
                "location": fips,
                "horizon": horizon,
                "target": "wk inc flu hosp",
                "target_end_date": target_end,
                "output_type": "quantile",
                "output_type_id": q,
                "value": median + offset,
            })
        df = pd.DataFrame(rows)
        path = tmp_path / f"{ref_date}-test.csv"
        df.to_csv(path, index=False)
        return path

    def test_scores_three_models_per_cell(self, tmp_path):
        from flubnf.baseline_forecast import (
            aggregate_baseline_comparison, score_submissions_vs_baselines)
        from flubnf.constants import StateInfo
        # Build observed series with a clear trend so persistence has signal.
        target = self._make_target(tmp_path, [
            ("2025-10-04", "01", 10.0),
            ("2025-10-11", "01", 20.0),
            ("2025-10-18", "01", 30.0),
            ("2025-10-25", "01", 40.0),   # actual we score against
        ])
        sub_dir = tmp_path / "submissions"
        sub_dir.mkdir()
        # Submission was for h=0 (next-week horizon), predicting median=50,
        # target_end = 2025-10-25.
        self._make_submission(
            sub_dir, ref_date="2025-10-18", fips="01",
            horizon=0, target_end="2025-10-25", median=50.0,
        )
        locs = {"Alabama": StateInfo("Alabama", "AL", "01", 5_000_000)}
        long_df = score_submissions_vs_baselines(sub_dir, target, locs)
        assert len(long_df) == 1
        row = long_df.iloc[0]
        assert row["state"] == "Alabama"
        # All three WIS values must be finite and non-negative.
        for col in ("model_wis", "persistence_wis", "rolling_wis"):
            assert np.isfinite(row[col])
            assert row[col] >= 0

        agg = aggregate_baseline_comparison(long_df)
        assert "model_vs_persistence" in agg.columns
        assert len(agg) == 1

    def test_missing_target_csv_raises(self, tmp_path):
        from flubnf.baseline_forecast import score_submissions_vs_baselines
        with pytest.raises(FileNotFoundError):
            score_submissions_vs_baselines(
                tmp_path / "submissions", tmp_path / "nope.csv", {}
            )

    def test_skips_rows_with_no_matching_actual(self, tmp_path):
        from flubnf.baseline_forecast import score_submissions_vs_baselines
        from flubnf.constants import StateInfo
        # Observed only up to ref_date, no actual at target_end yet.
        target = self._make_target(tmp_path, [
            ("2025-10-04", "01", 10.0),
            ("2025-10-11", "01", 20.0),
            ("2025-10-18", "01", 30.0),
            # no 2025-10-25 row
        ])
        sub_dir = tmp_path / "submissions"; sub_dir.mkdir()
        self._make_submission(
            sub_dir, ref_date="2025-10-18", fips="01",
            horizon=0, target_end="2025-10-25", median=50.0,
        )
        locs = {"Alabama": StateInfo("Alabama", "AL", "01", 5_000_000)}
        df = score_submissions_vs_baselines(sub_dir, target, locs)
        assert df.empty


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------
import re as _re

_ANSI_RE = _re.compile(r"\x1b\[[0-9;]*m")


def _plain(s: str) -> str:
    """Strip ANSI escapes — Rich emits per-char styles in CI."""
    return _ANSI_RE.sub("", s or "")


class TestBaselineCLI:
    def test_help_lists_options(self):
        from typer.testing import CliRunner
        from flubnf.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["baseline-score", "--help"],
                                env={"NO_COLOR": "1"})
        assert result.exit_code == 0
        plain = _plain(result.stdout)
        assert "--target" in plain
        assert "--rolling-window" in plain
