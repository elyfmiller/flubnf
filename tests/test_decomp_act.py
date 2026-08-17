"""Tests for flubnf.decomp_act."""

from __future__ import annotations

import pytest

from flubnf.calibration import CalibrationTracker, CoverageRecord
from flubnf.conf_files import FreeParam
from flubnf.decomp_act import (DecompActions, RecentSignals,
                                apply_to_session, compute_recent_signals,
                                recommend_calibration_widen,
                                recommend_mult_tighten)
from flubnf.session import StateSession


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _record(state="Alabama", horizon=1, reference_date="2025-11-01",
            *, median, actual, half_width=10.0) -> CoverageRecord:
    """Build a CoverageRecord with quantiles centered on `median`."""
    return CoverageRecord(
        state=state, horizon=horizon, reference_date=reference_date,
        q025=median - 2.0 * half_width, q05=median - 1.6 * half_width,
        q25=median - 0.7 * half_width, q50=median,
        q75=median + 0.7 * half_width, q95=median + 1.6 * half_width,
        q975=median + 2.0 * half_width,
        actual=actual,
    )


def _populate(tracker: CalibrationTracker, state: str, rows: list[tuple]):
    """rows: list of (median, actual, half_width) tuples — chronological."""
    for i, (m, a, w) in enumerate(rows):
        tracker.record(_record(
            state=state, reference_date=f"2025-11-{i + 1:02d}",
            median=m, actual=a, half_width=w,
        ))


def _session_with_mult(low=1.0, high=9000.0) -> StateSession:
    return StateSession(
        state="Alabama",
        bounds=[
            FreeParam("b0__FREE", 0.05, 2.0),
            FreeParam("mult__FREE", low, high),
            FreeParam("gamma__FREE", 0.01, 1.2),
        ],
        n_steps=1,
    )


# ---------------------------------------------------------------------------
# compute_recent_signals
# ---------------------------------------------------------------------------
class TestComputeRecentSignals:
    def test_empty_history_returns_benign_signals(self):
        t = CalibrationTracker()
        sig = compute_recent_signals(t, "Alabama", horizon=1)
        assert sig.n_weeks == 0
        # No data → don't trigger anything; cov95 defaults to 1.0.
        assert sig.mean_cov95 == 1.0
        assert sig.mean_bias == 0.0

    def test_lookback_truncates(self):
        t = CalibrationTracker()
        _populate(t, "Alabama", [(100, 80, 10), (100, 80, 10), (100, 80, 10),
                                   (100, 80, 10)])
        sig = compute_recent_signals(t, "Alabama", lookback=3)
        assert sig.n_weeks == 3
        assert len(sig.bias_sequence) == 3

    def test_bias_is_signed_q50_minus_actual(self):
        t = CalibrationTracker()
        _populate(t, "Alabama", [(100, 60, 10), (120, 80, 10)])
        sig = compute_recent_signals(t, "Alabama", lookback=2)
        assert sig.bias_sequence == (40.0, 40.0)
        assert sig.mean_bias == 40.0

    def test_cov95_inside_outside(self):
        t = CalibrationTracker()
        # half_width=10 → q025=80, q975=120 around median=100.
        _populate(t, "Alabama", [
            (100, 100, 10),   # actual=100 inside [80, 120] -> 1
            (100, 150, 10),   # actual=150 outside -> 0
            (100, 100, 10),   # inside -> 1
        ])
        sig = compute_recent_signals(t, "Alabama", lookback=3)
        assert sig.cov95_sequence == (True, False, True)
        assert sig.mean_cov95 == pytest.approx(2/3)


# ---------------------------------------------------------------------------
# recommend_mult_tighten
# ---------------------------------------------------------------------------
class TestMultTighten:
    def test_no_recommendation_below_min_weeks(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=2,
                             bias_sequence=(50.0, 50.0),
                             cov95_sequence=(True, True),
                             median_sequence=(100.0, 100.0),
                             mean_bias=50.0, mean_cov95=1.0)
        assert recommend_mult_tighten(sig, min_weeks=3) is None

    def test_no_recommendation_when_bias_not_consistently_positive(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=3,
                             bias_sequence=(50.0, -10.0, 50.0),
                             cov95_sequence=(True,)*3,
                             median_sequence=(100.0,)*3,
                             mean_bias=30.0, mean_cov95=1.0)
        assert recommend_mult_tighten(sig) is None

    def test_no_recommendation_when_relative_bias_too_small(self):
        # 1% bias on a median of 1000 → ignore (noise).
        sig = RecentSignals(state="X", horizon=1, n_weeks=3,
                             bias_sequence=(10.0, 10.0, 10.0),
                             cov95_sequence=(True,)*3,
                             median_sequence=(1000.0,)*3,
                             mean_bias=10.0, mean_cov95=1.0)
        assert recommend_mult_tighten(sig, min_relative_bias=0.10) is None

    def test_recommends_when_consistent_material_positive_bias(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=3,
                             bias_sequence=(30.0, 25.0, 28.0),
                             cov95_sequence=(True,)*3,
                             median_sequence=(100.0, 100.0, 100.0),
                             mean_bias=27.67, mean_cov95=1.0)
        rec = recommend_mult_tighten(sig, factor=0.8)
        assert rec is not None
        assert rec.new_high_factor == 0.8
        assert "positive bias" in rec.reason

    def test_no_action_with_zero_median(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=3,
                             bias_sequence=(1.0, 1.0, 1.0),
                             cov95_sequence=(True,)*3,
                             median_sequence=(0.0, 0.0, 0.0),
                             mean_bias=1.0, mean_cov95=1.0)
        assert recommend_mult_tighten(sig) is None


# ---------------------------------------------------------------------------
# recommend_calibration_widen
# ---------------------------------------------------------------------------
class TestCalibrationWiden:
    def test_no_action_when_well_calibrated(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=5,
                             bias_sequence=(0.0,)*5,
                             cov95_sequence=(True,)*5,
                             median_sequence=(100.0,)*5,
                             mean_bias=0.0, mean_cov95=1.0)
        assert recommend_calibration_widen(sig, current_max_factor=1.5) is None

    def test_no_action_below_min_weeks(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=2,
                             bias_sequence=(0.0,)*2,
                             cov95_sequence=(False,)*2,
                             median_sequence=(100.0,)*2,
                             mean_bias=0.0, mean_cov95=0.0)
        assert recommend_calibration_widen(sig, current_max_factor=1.5,
                                            min_weeks=3) is None

    def test_widens_when_cov95_below_threshold(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=4,
                             bias_sequence=(0.0,)*4,
                             cov95_sequence=(False, False, True, False),
                             median_sequence=(100.0,)*4,
                             mean_bias=0.0, mean_cov95=0.25)
        rec = recommend_calibration_widen(sig, current_max_factor=1.5,
                                           increment=0.25, cap=2.5)
        assert rec is not None
        assert rec.new_max_factor == pytest.approx(1.75)
        assert "cov_95" in rec.reason

    def test_caps_at_max(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=4,
                             bias_sequence=(0.0,)*4,
                             cov95_sequence=(False,)*4,
                             median_sequence=(100.0,)*4,
                             mean_bias=0.0, mean_cov95=0.0)
        rec = recommend_calibration_widen(sig, current_max_factor=2.4,
                                           increment=0.5, cap=2.5)
        assert rec is not None
        assert rec.new_max_factor == 2.5

    def test_no_action_when_already_at_cap(self):
        sig = RecentSignals(state="X", horizon=1, n_weeks=4,
                             bias_sequence=(0.0,)*4,
                             cov95_sequence=(False,)*4,
                             median_sequence=(100.0,)*4,
                             mean_bias=0.0, mean_cov95=0.0)
        assert recommend_calibration_widen(
            sig, current_max_factor=2.5, increment=0.25, cap=2.5
        ) is None


# ---------------------------------------------------------------------------
# apply_to_session integration
# ---------------------------------------------------------------------------
class TestApplyToSession:
    def test_no_op_when_signals_are_clean(self):
        t = CalibrationTracker()
        # Perfect forecasts: bias=0, full coverage.
        _populate(t, "Alabama", [(100, 100, 10)] * 4)
        sess = _session_with_mult(high=9000.0)
        actions = apply_to_session(t, sess)
        assert not actions
        assert actions.mult_tightened is None
        assert actions.calibration_max_factor is None
        # mult bound unchanged.
        mult = next(fp for fp in sess.bounds if fp.name == "mult__FREE")
        assert mult.high == 9000.0
        assert "calibration_max_factor" not in sess.tuning

    def test_tightens_mult_on_persistent_positive_bias(self):
        t = CalibrationTracker()
        # Median consistently overpredicts; actual ~ 70% of median.
        _populate(t, "Alabama", [
            (200, 140, 10),
            (220, 150, 10),
            (210, 145, 10),
        ])
        sess = _session_with_mult(high=9000.0)
        actions = apply_to_session(t, sess, mult_factor=0.85)
        assert actions.mult_tightened == 0.85
        mult = next(fp for fp in sess.bounds if fp.name == "mult__FREE")
        assert mult.high == pytest.approx(9000.0 * 0.85)
        # Low bound untouched.
        assert mult.low == 1.0

    def test_widens_calibration_on_low_cov95(self):
        t = CalibrationTracker()
        # half_width=2 → 95% PI = median ± 4. Actual constantly outside.
        _populate(t, "Alabama", [
            (100, 200, 2),
            (100, 200, 2),
            (100, 200, 2),
        ])
        sess = _session_with_mult()
        actions = apply_to_session(t, sess)
        assert actions.calibration_max_factor is not None
        # Default starts at 1.5, increment 0.25 → 1.75.
        assert sess.tuning["calibration_max_factor"] == pytest.approx(1.75)

    def test_both_signals_fire_simultaneously(self):
        t = CalibrationTracker()
        # High bias AND low cov95: median way above actual, tight intervals.
        _populate(t, "Alabama", [
            (200, 50, 2),
            (200, 50, 2),
            (200, 50, 2),
        ])
        sess = _session_with_mult(high=9000.0)
        actions = apply_to_session(t, sess)
        assert actions.mult_tightened is not None
        assert actions.calibration_max_factor is not None
        assert len(actions.notes) == 2

    def test_mult_low_floor_prevents_inversion(self):
        """If shrinking the upper would cross the lower bound, we floor it."""
        t = CalibrationTracker()
        _populate(t, "Alabama", [
            (200, 140, 10), (220, 150, 10), (210, 145, 10),
        ])
        sess = _session_with_mult(low=8000.0, high=8500.0)
        apply_to_session(t, sess, mult_factor=0.5)
        mult = next(fp for fp in sess.bounds if fp.name == "mult__FREE")
        # Would have gone to 4250, but flooring keeps it just above low.
        assert mult.high > mult.low
        assert mult.high == pytest.approx(8000.0 * 1.05)

    def test_subsequent_calls_compound_calibration_widening(self):
        """Apply twice → max_factor grows from 1.5 → 1.75 → 2.0."""
        t = CalibrationTracker()
        _populate(t, "Alabama", [
            (100, 200, 2), (100, 200, 2), (100, 200, 2),
        ])
        sess = _session_with_mult()
        apply_to_session(t, sess, max_factor_increment=0.25)
        assert sess.tuning["calibration_max_factor"] == pytest.approx(1.75)
        apply_to_session(t, sess, max_factor_increment=0.25)
        assert sess.tuning["calibration_max_factor"] == pytest.approx(2.00)
