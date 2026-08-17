"""Tests for flubnf.backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd

from flubnf.backtest import (BacktestRecord, append_record_csv, forecast,
                             records_to_dataframe, score, walk_forward)
from flubnf.simulate import predict_weekly


def _rec(state="Alabama", week=18, adaptive=True, wis=None):
    r = BacktestRecord(
        state=state, week=week, adaptive=adaptive, best_obj=0.0, n_steps=2,
        forecast={1: 10.0, 2: 12.0}, actual={1: 11.0, 2: 13.0},
    )
    r.wis = wis or {1: 5.0, 2: 6.0}  # type: ignore[attr-defined]
    return r


class TestResumeCheckpoint:
    def test_append_creates_then_appends_aligned(self, tmp_path):
        p = tmp_path / "Alabama.csv"
        append_record_csv(p, _rec(week=18))
        append_record_csv(p, _rec(week=19))
        df = pd.read_csv(p)
        assert len(df) == 2
        assert set(df["week"]) == {18, 19}
        # header stable across appends (no duplicated header row)
        assert (df["state"] == "Alabama").all()

    def test_append_handles_both_modes_in_one_file(self, tmp_path):
        p = tmp_path / "Alabama.csv"
        append_record_csv(p, _rec(week=18, adaptive=True))
        append_record_csv(p, _rec(week=18, adaptive=False))
        df = pd.read_csv(p)
        assert len(df) == 2
        assert set(df["adaptive"].astype(bool)) == {True, False}

    def test_done_weeks_roundtrip(self, tmp_path):
        # The CLI computes resume-skip from exactly this shape.
        p = tmp_path / "Alabama.csv"
        for w in (18, 19, 20):
            append_record_csv(p, _rec(week=w, adaptive=True))
        df = pd.read_csv(p)
        done = set(int(w) for w in df[df["adaptive"] == True]["week"])
        assert done == {18, 19, 20}

    def test_quantile_bounds_persisted_for_coverage(self):
        # A record carrying a quantile_forecast must expose PI-bound columns
        # so empirical coverage is computable from the CSV without a refit.
        r = _rec(week=18)
        r.quantile_forecast = {  # type: ignore[attr-defined]
            1: {0.025: 5.0, 0.25: 9.0, 0.5: 11.0, 0.75: 13.0, 0.975: 20.0},
            2: {0.025: 6.0, 0.25: 10.0, 0.5: 12.0, 0.75: 15.0, 0.975: 24.0},
        }
        df = records_to_dataframe([r])
        for col in ("q025_h1", "q50_h1", "q975_h1", "q025_h2", "q975_h2"):
            assert col in df.columns
        assert df["q025_h1"].iloc[0] == 5.0
        assert df["q975_h1"].iloc[0] == 20.0
        # Coverage is then: actual_h1 within [q025_h1, q975_h1]?
        assert df["q025_h1"].iloc[0] <= df["actual_h1"].iloc[0] <= df["q975_h1"].iloc[0]

    def test_walk_forward_skips_and_checkpoints(self, tmp_path):
        # Static (stateless) inproc run: skip_weeks must be honored and each
        # run week checkpointed. Uses the fast in-Python engine (no PyBNF).
        rng = np.random.default_rng(0)
        obs = np.concatenate([np.linspace(1, 80, 16), np.linspace(80, 5, 10)])
        cp = tmp_path / "Alabama.csv"
        recs = walk_forward(
            "Alabama", obs, start_week=8, end_week=12, horizons=(1, 2),
            adaptive=False, popsize=6, max_iter=40, engine="inproc",
            checkpoint_path=cp, skip_weeks={8, 9},
        )
        weeks_run = {r.week for r in recs}
        assert 8 not in weeks_run and 9 not in weeks_run
        assert weeks_run <= {10, 11, 12}
        # Every run week was checkpointed to disk.
        df = pd.read_csv(cp)
        assert set(df["week"]) == weeks_run


class TestForecast:
    def test_horizon_alignment(self):
        params = {"I0": 0.005, "b0": 0.5, "gamma": 0.2, "mult": 1000.0, "t0": 1.0}
        # If full trajectory is f, then horizon h at n_observed=N means
        # f[N + h - 1].
        full = predict_weekly(params, 20)
        fcst = forecast(params, n_observed=10, horizons=[1, 2, 3, 4])
        for h in [1, 2, 3, 4]:
            # Two independent ODE solves accumulate solver roundoff to ~1e-6.
            assert abs(fcst[h] - full[10 + h - 1]) < 1e-4


class TestScore:
    def test_perfect_forecast_has_zero_error(self):
        fc = {1: 10.0, 2: 20.0, 3: 30.0}
        act = {1: 10.0, 2: 20.0, 3: 30.0}
        s = score(fc, act)
        assert s.mae == 0.0
        assert s.rmse == 0.0
        assert s.mape == 0.0

    def test_handles_nan_actuals(self):
        fc = {1: 10.0, 2: 20.0, 3: 30.0}
        act = {1: 10.0, 2: float("nan"), 3: 33.0}
        s = score(fc, act)
        # only h=1 and h=3 should contribute (h=2 NaN dropped)
        assert s.mae == ((0 + 3) / 2)

    def test_simple_metrics(self):
        fc = {1: 10.0, 2: 22.0}
        act = {1: 8.0, 2: 20.0}
        s = score(fc, act)
        assert s.mae == 2.0
        assert s.rmse == 2.0


class TestWalkForward:
    def test_basic_static_loop(self):
        # Use a tiny synthetic season.
        params = {"I0": 0.005, "b0": 0.6, "gamma": 0.2, "mult": 1500.0, "t0": 2.0}
        obs = predict_weekly(params, 25) + 1e-3  # avoid exact-zero issues
        records = walk_forward(
            "Test", obs, start_week=8, end_week=12,
            adaptive=False, popsize=8, max_iter=80, seed=0,
        )
        assert len(records) == 5
        # In static mode, no bounds changes / additions ever.
        assert all(r.bounds_changed == [] for r in records)
        assert all(r.bounds_added == [] for r in records)
        # n_steps should stay at 1 throughout.
        assert all(r.n_steps == 1 for r in records)

    def test_adaptive_loop_runs_and_can_evolve(self):
        params = {"I0": 0.005, "b0": 0.6, "gamma": 0.2, "mult": 1500.0, "t0": 2.0}
        obs = predict_weekly(params, 25) + 1e-3
        records = walk_forward(
            "Test", obs, start_week=8, end_week=12,
            adaptive=True, popsize=8, max_iter=80, seed=0,
        )
        assert len(records) == 5
        # In adaptive mode, n_steps is monotonically non-decreasing.
        ns = [r.n_steps for r in records]
        assert all(ns[i] <= ns[i + 1] for i in range(len(ns) - 1))
