"""Tests for per-state error decomposition."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flubnf.error_decomp import (RowMetrics, _decompose_single,
                                 aggregate_by_state,
                                 aggregate_by_state_horizon)
from flubnf.quantiles import FLUSIGHT_QUANTILES


def _qdict(median: float, spread: float = 30.0) -> dict[float, float]:
    """Linear quantile dict centered on `median` with the FluSight 23 levels."""
    return {float(q): float(median + (q - 0.5) * spread)
            for q in FLUSIGHT_QUANTILES}


def test_decompose_perfect_calibration():
    """Actual lands exactly on the median, inside all PIs."""
    q = _qdict(100.0, spread=30.0)
    m = _decompose_single(q, actual=100.0)
    assert m.bias == 0.0
    assert m.abs_err == 0.0
    assert m.coverage_50 == 1.0
    assert m.coverage_80 == 1.0
    assert m.coverage_95 == 1.0
    assert m.overpred == 0.0
    assert m.underpred == 0.0


def test_decompose_under_forecast():
    """Actual is FAR above the upper bound — we under-forecast."""
    q = _qdict(100.0, spread=30.0)
    m = _decompose_single(q, actual=500.0)
    assert m.bias < 0    # median - actual = negative
    assert m.underpred > 0
    assert m.overpred == 0
    assert m.coverage_50 == 0.0
    assert m.coverage_95 == 0.0


def test_decompose_over_forecast():
    q = _qdict(100.0, spread=30.0)
    m = _decompose_single(q, actual=10.0)
    assert m.bias > 0
    assert m.overpred > 0
    assert m.underpred == 0


def test_decompose_inside_50_outside_95_impossible():
    """50% PI is narrower than 95%, so coverage_50 == 1 implies coverage_95 == 1."""
    q = _qdict(100.0, spread=30.0)
    m = _decompose_single(q, actual=105.0)
    if m.coverage_50 == 1.0:
        assert m.coverage_95 == 1.0


def test_aggregate_handles_empty():
    assert aggregate_by_state(pd.DataFrame()).empty
    assert aggregate_by_state_horizon(pd.DataFrame()).empty


def test_aggregate_by_state_groups_rows():
    df = pd.DataFrame([
        {"reference_date": "2026-01-03", "state": "Alabama", "horizon": 0,
         "our_wis": 10.0, "sharpness": 5, "bias": -2, "abs_err": 2,
         "overpred": 0, "underpred": 1,
         "coverage_50": 1, "coverage_80": 1, "coverage_95": 1},
        {"reference_date": "2026-01-10", "state": "Alabama", "horizon": 0,
         "our_wis": 12.0, "sharpness": 6, "bias": 3, "abs_err": 3,
         "overpred": 0.5, "underpred": 0,
         "coverage_50": 0, "coverage_80": 1, "coverage_95": 1},
        {"reference_date": "2026-01-03", "state": "Wyoming", "horizon": 0,
         "our_wis": 5.0, "sharpness": 2, "bias": 0, "abs_err": 1,
         "overpred": 0, "underpred": 0,
         "coverage_50": 1, "coverage_80": 1, "coverage_95": 1},
    ])
    agg = aggregate_by_state(df)
    assert set(agg["state"]) == {"Alabama", "Wyoming"}
    al = agg[agg["state"] == "Alabama"].iloc[0]
    assert al["n_cells"] == 2
    assert pytest.approx(al["mean_wis"], abs=1e-9) == 11.0
    assert pytest.approx(al["mean_bias"], abs=1e-9) == 0.5
    assert 0.0 <= al["calibration_score"] <= 1.0


def test_calibration_score_one_when_balanced():
    """over/under split 50/50 -> calibration_score == 1."""
    df = pd.DataFrame([
        {"state": "X", "our_wis": 5.0, "sharpness": 2, "bias": 0,
         "abs_err": 1, "overpred": 1.0, "underpred": 1.0,
         "coverage_50": 1, "coverage_80": 1, "coverage_95": 1,
         "horizon": 0},
    ])
    agg = aggregate_by_state(df)
    assert pytest.approx(agg["calibration_score"].iloc[0], abs=1e-9) == 1.0


def test_calibration_score_zero_when_all_under():
    df = pd.DataFrame([
        {"state": "X", "our_wis": 5.0, "sharpness": 2, "bias": 0,
         "abs_err": 1, "overpred": 0.0, "underpred": 10.0,
         "coverage_50": 0, "coverage_80": 0, "coverage_95": 0,
         "horizon": 0},
    ])
    agg = aggregate_by_state(df)
    assert pytest.approx(agg["calibration_score"].iloc[0], abs=1e-9) == 0.0


def test_aggregate_by_state_horizon():
    df = pd.DataFrame([
        {"state": "Alabama", "horizon": 0, "our_wis": 10.0,
         "sharpness": 5, "bias": -2, "abs_err": 2,
         "overpred": 0, "underpred": 1,
         "coverage_50": 1, "coverage_80": 1, "coverage_95": 1},
        {"state": "Alabama", "horizon": 3, "our_wis": 25.0,
         "sharpness": 12, "bias": -8, "abs_err": 8,
         "overpred": 0, "underpred": 4,
         "coverage_50": 0, "coverage_80": 0, "coverage_95": 1},
    ])
    out = aggregate_by_state_horizon(df)
    assert len(out) == 2
    assert set(out["horizon"]) == {0, 3}
    # h=3 should have wider sharpness on average.
    h3 = out[out["horizon"] == 3].iloc[0]
    h0 = out[out["horizon"] == 0].iloc[0]
    assert h3["mean_sharpness"] > h0["mean_sharpness"]
