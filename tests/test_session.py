"""Tests for flubnf.session (per-state state carry-over)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flubnf.conf_files import FreeParam
from flubnf.session import (StateSession, load_session, record_step,
                            save_session, session_path)


def test_round_trip_via_disk(tmp_path: Path):
    sess = StateSession(
        state="Alabama",
        bounds=[
            FreeParam("b0__FREE", 0.1, 1.5),
            FreeParam("t0__FREE", 0, 12),
        ],
        n_steps=2,
        last_reference_date="2026-01-03",
    )
    save_session(tmp_path, sess)
    loaded = load_session(tmp_path, "Alabama")
    assert loaded is not None
    assert loaded.state == "Alabama"
    assert loaded.n_steps == 2
    assert loaded.last_reference_date == "2026-01-03"
    assert {fp.name for fp in loaded.bounds} == {"b0__FREE", "t0__FREE"}


def test_load_missing_returns_none(tmp_path: Path):
    assert load_session(tmp_path, "DoesNotExist") is None


def test_session_path_is_under_sessions_subdir(tmp_path: Path):
    p = session_path(tmp_path, "Texas")
    assert p.parent == tmp_path / "sessions"
    assert p.name == "Texas.json"


def test_record_step_appends_history(tmp_path: Path):
    sess = StateSession(state="Wyoming",
                        bounds=[FreeParam("b0__FREE", 0.1, 0.9)])
    record_step(sess, reference_date=date(2026, 1, 3),
                bounds_changed=["b0__FREE"], bounds_added=[], best_obj=42.0)
    assert len(sess.history) == 1
    assert sess.history[0]["reference_date"] == "2026-01-03"
    assert sess.history[0]["best_obj"] == 42.0
    assert sess.last_reference_date == "2026-01-03"

    record_step(sess, reference_date=date(2026, 1, 10),
                bounds_changed=[], bounds_added=["b1__FREE", "t1__FREE"],
                best_obj=39.5)
    assert len(sess.history) == 2
    assert sess.last_reference_date == "2026-01-10"


def test_save_then_overwrite(tmp_path: Path):
    sess = StateSession(state="Alabama", bounds=[FreeParam("x", 0, 1)])
    save_session(tmp_path, sess)
    sess.n_steps = 5
    save_session(tmp_path, sess)
    loaded = load_session(tmp_path, "Alabama")
    assert loaded.n_steps == 5


def test_tuning_persists(tmp_path: Path):
    sess = StateSession(
        state="California",
        tuning={"slope_blend": 0.3, "anchor_lookback": 4, "phase_aware": True},
    )
    save_session(tmp_path, sess)
    loaded = load_session(tmp_path, "California")
    assert loaded.tuning["slope_blend"] == 0.3
    assert loaded.tuning["anchor_lookback"] == 4
    assert loaded.tuning["phase_aware"] is True


def test_get_tuning_returns_default_when_missing(tmp_path: Path):
    sess = StateSession(state="Wyoming", tuning={"slope_blend": 0.2})
    assert sess.get_tuning("slope_blend", 0.0) == 0.2
    assert sess.get_tuning("max_K", 1) == 1  # default for missing key


def test_tuning_round_trip_through_disk(tmp_path: Path):
    sess = StateSession(
        state="Texas",
        tuning={"slope_blend": 0.4, "max_K": 8, "max_iter": 20000},
    )
    save_session(tmp_path, sess)
    loaded = load_session(tmp_path, "Texas")
    assert loaded.tuning == sess.tuning
