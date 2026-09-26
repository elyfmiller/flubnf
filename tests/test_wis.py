"""Tests for flubnf.wis."""

from __future__ import annotations

import math

import pytest

from flubnf.wis import (COVERAGE_BANDS, FLUSIGHT_PI_QUANTILES, coverage,
                        interval_covered, log_shift, log_wis, wis)


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


#: the 23 FluSight levels
_LEVELS = (0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40,
           0.45, 0.5, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95,
           0.975, 0.99)


class TestLogScaleWIS:
    """log_wis is WIS after log(x + 1) is applied to every quantile and to
    the observation (scoringutils transform_forecasts, log_shift, offset 1:
    the CDC dashboard's log scale)."""

    #: five levels whose log(x + 1) values are 0, 1, 2, 3, 4
    Q = {0.05: 0.0, 0.25: math.e - 1, 0.5: math.e ** 2 - 1,
         0.75: math.e ** 3 - 1, 0.95: math.e ** 4 - 1}
    PI = (0.05, 0.25)

    def test_hand_worked_inside_both_intervals(self):
        # log truth 2.5: median 0.5 * 0.5 = 0.25; 50% (1, 3): IS 2, * 0.25
        # = 0.5; 90% (0, 4): IS 4, * 0.05 = 0.2; (0.25 + 0.5 + 0.2) / 2.5
        y = math.e ** 2.5 - 1
        assert log_wis(self.Q, y, pi_quantiles=self.PI) == pytest.approx(0.38)

    def test_hand_worked_above_both_intervals(self):
        # log truth 5: median 1.5; 50%: 2 + 4 * 2 = 10, * 0.25 = 2.5;
        # 90%: 4 + 20 * 1 = 24, * 0.05 = 1.2; 5.2 / 2.5
        y = math.e ** 5 - 1
        assert log_wis(self.Q, y, pi_quantiles=self.PI) == pytest.approx(2.08)

    def test_a_truth_of_zero_is_scored(self):
        # log truth 0 = the 5% quantile: median 1; 50%: 2 + 4 * 1 = 6, * 0.25
        # = 1.5; 90%: IS 4 (0 is on the bound), * 0.05 = 0.2; 2.7 / 2.5
        assert log_wis(self.Q, 0.0, pi_quantiles=self.PI) == pytest.approx(1.08)
        assert log_shift(0.0) == 0.0

    def test_the_23_level_set_matches_an_independent_implementation(self):
        """Values from a separate implementation of scoringutils::wis
        (interval decomposition, count_median_twice = FALSE) on log1p
        values, written without this package."""
        q = dict(zip(_LEVELS, [float(k) for k in range(23)]))
        for y, natural, logged in ((0.0, 6.758260869565217, 1.768051962188696),
                                   (11.0, 1.497391304347826, 0.13807272994801),
                                   (30.0, 14.758260869565218,
                                    0.7145021607812877)):
            assert wis(q, y).wis == pytest.approx(natural, rel=1e-12)
            assert log_wis(q, y) == pytest.approx(logged, rel=1e-12)

    def test_a_negative_value_reads_as_zero(self):
        """A count is never negative; the log is not taken outside its domain."""
        assert log_shift(-3.0) == 0.0
        assert log_shift(math.e - 1) == pytest.approx(1.0)


class TestCoverage:
    """1 when lower <= truth <= upper, both ends inclusive (scoringutils
    interval_coverage), for the 50/80/95 percent central intervals."""

    Q = dict(zip(_LEVELS, [float(k) for k in range(23)]))
    # 95%: [q0.025, q0.975] = [1, 21]; 80%: [q0.1, q0.9] = [3, 19];
    # 50%: [q0.25, q0.75] = [6, 16]

    def test_the_bands_and_their_levels(self):
        assert COVERAGE_BANDS == (("50", 0.25, 0.75), ("80", 0.10, 0.90),
                                  ("95", 0.025, 0.975))

    def test_both_ends_are_inclusive(self):
        assert coverage(self.Q, 1.0) == {"50": 0, "80": 0, "95": 1}
        assert coverage(self.Q, 21.0) == {"50": 0, "80": 0, "95": 1}
        assert coverage(self.Q, 3.0) == {"50": 0, "80": 1, "95": 1}
        assert coverage(self.Q, 16.0) == {"50": 1, "80": 1, "95": 1}
        assert coverage(self.Q, 6.0) == {"50": 1, "80": 1, "95": 1}

    def test_outside_every_interval(self):
        assert coverage(self.Q, 0.5) == {"50": 0, "80": 0, "95": 0}
        assert coverage(self.Q, 21.5) == {"50": 0, "80": 0, "95": 0}
        assert coverage(self.Q, 16.5) == {"50": 0, "80": 1, "95": 1}

    def test_a_point_mass_covers_only_its_own_value(self):
        zero = {L: 0.0 for L in _LEVELS}
        assert coverage(zero, 0.0) == {"50": 1, "80": 1, "95": 1}
        assert coverage(zero, 1.0) == {"50": 0, "80": 0, "95": 0}

    def test_a_missing_level_gives_none(self):
        five = {0.05: 0.0, 0.25: 1.0, 0.5: 2.0, 0.75: 3.0, 0.95: 4.0}
        assert coverage(five, 2.0) == {"50": 1, "80": None, "95": None}
        assert interval_covered(five, 2.0, 0.25, 0.75) == 1
