"""Tests for flubnf.calibration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from flubnf.calibration import (CalibrationTracker, CoverageRecord,
                                apply_calibration)
from flubnf.quantiles import FLUSIGHT_QUANTILES, QuantileForecast


def _make_qf(med: float = 100.0, half_width: float = 50.0) -> QuantileForecast:
    """Synthetic quantile forecast: linear ramp between med-hw and med+hw."""
    n_q = len(FLUSIGHT_QUANTILES)
    quants = np.zeros((n_q, 4))
    for i, q in enumerate(FLUSIGHT_QUANTILES):
        # Map q in [0,1] to value via linear interpolation across the band.
        quants[i, :] = med + (q - 0.5) * 2 * half_width
    return QuantileForecast(
        horizons=(1, 2, 3, 4),
        quantile_levels=tuple(FLUSIGHT_QUANTILES),
        quantiles=quants,
        point=np.array([med, med, med, med]),
    )


class TestRecordAndPersist:
    def test_record_appends_to_bucket(self):
        t = CalibrationTracker()
        for w, actual in enumerate([90, 110, 95, 105]):
            t.record(CoverageRecord(
                state="Alabama", horizon=1,
                reference_date=f"2026-01-{3 + 7*w:02d}",
                q025=70, q05=75, q25=85, q50=100, q75=115, q95=125, q975=130,
                actual=float(actual),
            ))
        assert len(t.history[("Alabama", 1)]) == 4

    def test_rolling_window_trims(self):
        t = CalibrationTracker(rolling_window=3)
        for w in range(5):
            t.record(CoverageRecord(
                state="Alabama", horizon=1,
                reference_date=f"2026-01-{3 + 7*w:02d}",
                q025=0, q05=0, q25=0, q50=0, q75=0, q95=0, q975=0,
                actual=0,
            ))
        assert len(t.history[("Alabama", 1)]) == 3

    def test_round_trip(self, tmp_path: Path):
        t = CalibrationTracker()
        t.record(CoverageRecord(
            state="Texas", horizon=2, reference_date="2026-01-03",
            q025=50, q05=60, q25=70, q50=80, q75=90, q95=100, q975=110,
            actual=85,
        ))
        p = tmp_path / "cal.json"
        t.save(p)
        loaded = CalibrationTracker.load(p)
        assert ("Texas", 2) in loaded.history
        assert loaded.history[("Texas", 2)][0].actual == 85

    def test_load_missing_returns_empty(self, tmp_path: Path):
        t = CalibrationTracker.load(tmp_path / "does_not_exist.json")
        assert t.history == {}


class TestEmpiricalCoverage:
    def test_well_calibrated_returns_nominal(self):
        t = CalibrationTracker()
        # Construct 100 records where actuals hit roughly the right
        # percentile inside each PI.
        rng = np.random.default_rng(7)
        for w in range(100):
            # Sample an actual uniformly from the full quantile range.
            u = rng.uniform()
            actual = 50 + u * 100   # [50, 150]
            t.record(CoverageRecord(
                state="X", horizon=1, reference_date=f"w{w}",
                q025=52.5, q05=55, q25=75, q50=100, q75=125, q95=145, q975=147.5,
                actual=float(actual),
            ))
        cov = t.empirical_coverage("X", 1)
        # 50% PI (0.25..0.75): expect ~50% coverage.
        assert 0.35 < cov[0.5] < 0.65

    def test_undercovered_intervals(self):
        t = CalibrationTracker()
        # Force the actual to often fall OUTSIDE the 50% PI (too narrow).
        for w in range(20):
            t.record(CoverageRecord(
                state="Y", horizon=1, reference_date=f"w{w}",
                q025=80, q05=85, q25=95, q50=100, q75=105, q95=115, q975=120,
                actual=140.0,   # well above q95
            ))
        cov = t.empirical_coverage("Y", 1)
        assert cov[0.5] == 0.0
        assert cov[0.95] == 0.0


class TestRescaleFactor:
    def test_no_data_returns_one(self):
        t = CalibrationTracker()
        assert t.rescale_factor("Wyoming", 1) == 1.0

    def test_under_min_samples_returns_one(self):
        t = CalibrationTracker()
        for w in range(3):
            t.record(CoverageRecord(
                state="Wy", horizon=1, reference_date=f"w{w}",
                q025=0, q05=0, q25=0, q50=0, q75=0, q95=0, q975=0,
                actual=0,
            ))
        assert t.rescale_factor("Wy", 1) == 1.0

    def test_under_coverage_widens(self):
        t = CalibrationTracker()
        # Many weeks of UNDER-coverage: actual outside the 80% PI.
        for w in range(15):
            t.record(CoverageRecord(
                state="Z", horizon=1, reference_date=f"w{w}",
                q025=90, q05=92, q25=95, q50=100, q75=105, q95=108, q975=110,
                actual=120.0,   # outside the 80% PI (90..108)
            ))
        factor = t.rescale_factor("Z", 1)
        assert factor > 1.0   # widen intervals

    def test_over_coverage_narrows(self):
        t = CalibrationTracker()
        # OVER-coverage: actuals always inside even the 50% PI.
        for w in range(15):
            t.record(CoverageRecord(
                state="Q", horizon=1, reference_date=f"w{w}",
                q025=0, q05=10, q25=50, q50=100, q75=150, q95=190, q975=200,
                actual=100.0,
            ))
        factor = t.rescale_factor("Q", 1)
        assert factor < 1.0


class TestApplyCalibration:
    def test_no_rescale_when_tracker_empty(self):
        qf = _make_qf()
        t = CalibrationTracker()
        out = apply_calibration(qf, t, state="X")
        np.testing.assert_allclose(out.quantiles, qf.quantiles)

    def test_widens_when_undercovered(self):
        qf = _make_qf(med=100, half_width=10)
        t = CalibrationTracker()
        # 15 weeks of significant under-coverage at h=1.
        for w in range(15):
            t.record(CoverageRecord(
                state="A", horizon=1, reference_date=f"w{w}",
                q025=85, q05=88, q25=95, q50=100, q75=105, q95=112, q975=115,
                actual=150,
            ))
        out = apply_calibration(qf, t, state="A")
        # h=1 column should widen relative to original.
        orig_width = qf.quantiles[-2, 0] - qf.quantiles[1, 0]
        new_width = out.quantiles[-2, 0] - out.quantiles[1, 0]
        assert new_width > orig_width
        # Other horizons unchanged (no history for h=2..4).
        np.testing.assert_allclose(out.quantiles[:, 1:], qf.quantiles[:, 1:])

    def test_clipped_at_zero_when_rescale_widens_through_zero(self):
        # Start with a positive forecast that the rescaler widens beyond
        # the zero floor on the low end.
        qf = _make_qf(med=30, half_width=5)
        t = CalibrationTracker()
        # Severe under-cover at h=1.
        for w in range(15):
            t.record(CoverageRecord(
                state="C", horizon=1, reference_date=f"w{w}",
                q025=28, q05=28.5, q25=29, q50=30, q75=31, q95=31.5, q975=32,
                actual=120,
            ))
        out = apply_calibration(qf, t, state="C")
        # h=1 (rescaled column) must not produce negative values.
        assert (out.quantiles[:, 0] >= 0).all()
