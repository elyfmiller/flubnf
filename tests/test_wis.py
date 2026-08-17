"""Tests for flubnf.wis."""

from __future__ import annotations

import pytest

from flubnf.wis import FLUSIGHT_PI_QUANTILES, wis


def _symmetric_quantiles(median: float, half_widths: dict[float, float]) -> dict[float, float]:
    """Build a symmetric quantile dict around median, given half-widths per
    inner-quantile level q (so the (q, 1-q) pair is at (median-hw, median+hw))."""
    q = {0.5: median}
    for level, hw in half_widths.items():
        q[level] = median - hw
        q[1.0 - level] = median + hw
    return q


class TestWIS:
    def test_perfect_point_forecast(self):
        """If every quantile == actual, WIS == 0."""
        q = {0.5: 100.0}
        for level in FLUSIGHT_PI_QUANTILES:
            q[level] = 100.0
            q[1.0 - level] = 100.0
        r = wis(q, 100.0)
        assert r.wis == 0.0

    def test_constant_offset_equals_abs_error_when_zero_width(self):
        """With zero-width intervals (degenerate), WIS reduces to |y - median|."""
        q = {0.5: 100.0}
        for level in FLUSIGHT_PI_QUANTILES:
            q[level] = 100.0
            q[1.0 - level] = 100.0
        actual = 130.0
        r = wis(q, actual)
        # Degenerate case: each IS = (2/alpha) * (y - u) with u = median.
        # Sum of (alpha/2) * IS = sum (y - median) = K * 30.
        # Numerator = 0.5*30 + K*30. K = 11; (K + 0.5) = 11.5
        # = 15 + 330 = 345; / 11.5 = 30
        assert abs(r.wis - 30.0) < 1e-9

    def test_finite_intervals_reduce_score_when_calibrated(self):
        """A forecast with non-zero PIs covering the actual scores lower than a
        point forecast with the same median."""
        actual = 130.0
        point_q = {0.5: 100.0}
        for level in FLUSIGHT_PI_QUANTILES:
            point_q[level] = 100.0
            point_q[1.0 - level] = 100.0
        point_score = wis(point_q, actual).wis

        wide_q = _symmetric_quantiles(100.0,
                                      {l: 40.0 for l in FLUSIGHT_PI_QUANTILES})
        wide_score = wis(wide_q, actual).wis
        assert wide_score < point_score

    def test_overprediction_vs_underprediction_signs(self):
        """An over-prediction (actual below all PIs) bumps the overprediction
        component; vice versa for under-prediction."""
        # Predict 200, actual is 50 -> overprediction (actual < lower)
        over_q = _symmetric_quantiles(200.0,
                                      {l: 5.0 for l in FLUSIGHT_PI_QUANTILES})
        r_over = wis(over_q, 50.0)
        assert r_over.overprediction > 0
        assert r_over.underprediction == 0

        # Predict 50, actual is 200 -> underprediction (actual > upper)
        under_q = _symmetric_quantiles(50.0,
                                       {l: 5.0 for l in FLUSIGHT_PI_QUANTILES})
        r_under = wis(under_q, 200.0)
        assert r_under.underprediction > 0
        assert r_under.overprediction == 0

    def test_requires_median(self):
        with pytest.raises(ValueError):
            wis({0.025: 1, 0.975: 2}, 5.0)
