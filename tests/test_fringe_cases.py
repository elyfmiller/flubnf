"""Tests for the fringe-case ledger.

Each registered case has a fixture observed series that's guaranteed to
trigger it. If the detection logic changes and a case stops firing on
its fixture, this test FAILS — flagging that the coverage regressed.
"""

from __future__ import annotations

import numpy as np
import pytest

from flubnf.conf_files import FreeParam
from flubnf.fringe_cases import (REGISTERED_CASES, CaseMatch, evaluate_all,
                                 get_case, triggered_cases)
from flubnf.session import StateSession


def test_all_cases_registered():
    """Sanity: every case in REGISTERED_CASES has a unique name."""
    names = [c.name for c in REGISTERED_CASES]
    assert len(names) == len(set(names)), "duplicate case name in registry"
    # We expect at least 5 cases as of the initial commit.
    assert len(REGISTERED_CASES) >= 5


def test_small_state_regression_fires():
    obs = np.array([5, 10, 30, 25, 12, 8], dtype=float)
    matches = triggered_cases(obs, None)
    assert any(m.case_name == "small_state_regression" for m in matches)


def test_small_state_regression_not_fired_above_threshold():
    obs = np.array([20, 100, 300, 250, 120], dtype=float)
    matches = triggered_cases(obs, None)
    assert not any(m.case_name == "small_state_regression" for m in matches)


def test_mult_ceiling_crowding():
    sess = StateSession(
        state="California",
        bounds=[FreeParam("mult__FREE", 100, 8000)],
    )
    # Peak of 7000 -> ratio 0.875 of upper bound 8000.
    obs = np.array([100, 500, 2000, 7000, 4000], dtype=float)
    matches = triggered_cases(obs, sess)
    assert any(m.case_name == "mult_ceiling_crowding" for m in matches)


def test_mult_ceiling_no_crowding():
    sess = StateSession(
        state="Alabama",
        bounds=[FreeParam("mult__FREE", 100, 50000)],
    )
    obs = np.array([100, 500, 2000, 7000, 4000], dtype=float)
    matches = triggered_cases(obs, sess)
    assert not any(m.case_name == "mult_ceiling_crowding" for m in matches)


def test_late_season_rebound_fires():
    # First peak, decline, then last 3 weeks rising again.
    obs = np.array([10, 100, 800, 1000, 500, 200, 100, 90, 150, 250, 400],
                   dtype=float)
    matches = triggered_cases(obs, None)
    assert any(m.case_name == "late_season_rebound" for m in matches)


def test_late_season_rebound_no_rebound():
    # Decline continues — no rebound.
    obs = np.array([10, 100, 800, 1000, 500, 200, 100, 50, 30, 20],
                   dtype=float)
    matches = triggered_cases(obs, None)
    assert not any(m.case_name == "late_season_rebound" for m in matches)


def test_data_gap_detects_nan():
    obs = np.array([10, 20, 30, np.nan, 50], dtype=float)
    matches = triggered_cases(obs, None)
    assert any(m.case_name == "data_gap" for m in matches)


def test_data_gap_empty():
    matches = triggered_cases(np.array([], dtype=float), None)
    assert any(m.case_name == "data_gap" for m in matches)


def test_data_gap_no_gap():
    obs = np.array([10, 20, 30, 40, 50], dtype=float)
    matches = triggered_cases(obs, None)
    assert not any(m.case_name == "data_gap" for m in matches)


def test_runaway_K_fires():
    sess = StateSession(
        state="Texas",
        history=[
            {"reference_date": "2026-01-03", "bounds_added": []},
            {"reference_date": "2026-01-10", "bounds_added": ["b1__FREE", "t1__FREE"]},
            {"reference_date": "2026-01-17", "bounds_added": ["b2__FREE", "t2__FREE"]},
            {"reference_date": "2026-01-24", "bounds_added": ["b3__FREE", "t3__FREE"]},
            {"reference_date": "2026-01-31", "bounds_added": ["b4__FREE", "t4__FREE"]},
        ],
    )
    obs = np.array([100, 200, 400], dtype=float)
    matches = triggered_cases(obs, sess)
    assert any(m.case_name == "runaway_K" for m in matches)


def test_runaway_K_calm_session():
    sess = StateSession(
        state="Vermont",
        history=[
            {"reference_date": d, "bounds_added": []}
            for d in ["2026-01-03", "2026-01-10", "2026-01-17", "2026-01-24"]
        ],
    )
    matches = triggered_cases(np.array([10, 20, 30, 40]), sess)
    assert not any(m.case_name == "runaway_K" for m in matches)


def test_outlier_week_fires():
    # Prior weeks: 100±5. Last week: 1000 (huge anomaly).
    obs = np.array([95, 100, 105, 98, 102, 1000], dtype=float)
    matches = triggered_cases(obs, None)
    assert any(m.case_name == "outlier_week" for m in matches)


def test_outlier_week_no_anomaly():
    obs = np.array([95, 100, 105, 98, 102, 110], dtype=float)
    matches = triggered_cases(obs, None)
    assert not any(m.case_name == "outlier_week" for m in matches)


def test_holiday_dip_fires():
    # Christmas week (Dec 27, 2025 = epi week 52 of 2025).
    from flubnf.session import StateSession
    sess = StateSession(state="X", last_reference_date="2025-12-27")
    obs = np.array([300, 280, 320, 280, 130], dtype=float)
    matches = triggered_cases(obs, sess)
    assert any(m.case_name == "holiday_reporting_dip" for m in matches)


def test_holiday_dip_off_season_skipped():
    from flubnf.session import StateSession
    sess = StateSession(state="X", last_reference_date="2025-10-04")
    obs = np.array([300, 280, 320, 280, 130], dtype=float)
    matches = triggered_cases(obs, sess)
    assert not any(m.case_name == "holiday_reporting_dip" for m in matches)


def test_get_case_returns_or_none():
    assert get_case("small_state_regression") is not None
    assert get_case("nonexistent_case") is None


def test_evaluate_all_returns_match_for_every_case():
    obs = np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], dtype=float)
    sess = StateSession(state="Test")
    matches = evaluate_all(obs, sess)
    assert len(matches) == len(REGISTERED_CASES)
    assert all(isinstance(m, CaseMatch) for m in matches)


def test_triggered_cases_have_recommended_actions():
    """Whenever a case fires, it should provide recommendations."""
    obs = np.array([5, 10, 15, 20, 25, 30, 25, 20], dtype=float)
    fired = triggered_cases(obs, None)
    for m in fired:
        assert m.recommended_actions, \
            f"case {m.case_name} fired but had no recommendations"
