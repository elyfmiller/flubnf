"""Tests for flubnf.compare."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from flubnf.compare import (FLUSIGHT_TO_BACKTEST_HORIZON,
                            TEAM_REFERENCE_DATE_SHIFT_DAYS,
                            align_backtest_with_team, season_week_to_date)
from flubnf.config import FluBNFConfig


class TestSeasonWeekToDate:
    def test_week_0_is_onset_saturday(self):
        """Week 0 should map to the Saturday of season_year's MMWR week 26."""
        d = season_week_to_date(2025, 26, 0)
        assert d.weekday() == 5  # Saturday

    def test_consecutive_weeks_7_days_apart(self):
        a = season_week_to_date(2025, 26, 5)
        b = season_week_to_date(2025, 26, 6)
        assert (b - a).days == 7


class TestAlignBacktestWithTeam:
    def test_basic_alignment(self, tmp_path):
        """Synthesize tiny backtest + team CSVs and verify the merge."""
        # Backtest: 1 state, 2 weeks, both modes.
        bt = pd.DataFrame([
            {"state": "Alabama", "week": 25, "adaptive": True,
             "fcst_h1": 100, "fcst_h2": 110, "fcst_h3": 120, "fcst_h4": 130,
             "wis_h1": 5.0, "wis_h2": 10.0, "wis_h3": 15.0, "wis_h4": 20.0,
             "n_steps": 1, "best_obj": 1.0, "mae": 0, "rmse": 0,
             "mape": 0, "wis_mean": 12.5, "bounds_changed": "-",
             "bounds_added": "-"},
            {"state": "Alabama", "week": 25, "adaptive": False,
             "fcst_h1": 80, "fcst_h2": 85, "fcst_h3": 90, "fcst_h4": 95,
             "wis_h1": 30.0, "wis_h2": 35.0, "wis_h3": 40.0, "wis_h4": 45.0,
             "n_steps": 1, "best_obj": 1.0, "mae": 0, "rmse": 0,
             "mape": 0, "wis_mean": 37.5, "bounds_changed": "-",
             "bounds_added": "-"},
        ])
        bt_csv = tmp_path / "bt.csv"
        bt.to_csv(bt_csv, index=False)

        # The team submission reference_date comparable to backtest week 25 is
        # week 25's ending Saturday PLUS ONE WEEK (equal-information alignment;
        # see flubnf/compare.py module docstring).
        ref = (season_week_to_date(2025, 26, 25)
               + timedelta(days=TEAM_REFERENCE_DATE_SHIFT_DAYS)).isoformat()

        # Team scored: same 4 horizons.
        team = pd.DataFrame([
            {"reference_date": ref, "location": "01", "horizon": h,
             "actual": 100 + h*10, "median": 95 + h*10,
             "wis": 50.0 + h*5, "over": 0, "under": 0,
             "submission": "test.csv"}
            for h in range(4)
        ])
        team_csv = tmp_path / "team.csv"
        team.to_csv(team_csv, index=False)

        cfg = FluBNFConfig.load()
        df = align_backtest_with_team(bt_csv, team_csv, "Alabama", cfg)
        # 4 rows (one per FluSight horizon).
        assert len(df) == 4
        assert set(df["horizon"]) == {0, 1, 2, 3}
        # FluSight h=0 maps to backtest h=1.
        h0 = df[df["horizon"] == 0].iloc[0]
        assert h0["our_wis_adapt"] == 5.0
        assert h0["our_wis_static"] == 30.0
        assert h0["team_wis"] == 50.0

    def test_skips_dates_with_no_team_data(self, tmp_path):
        bt = pd.DataFrame([
            {"state": "Alabama", "week": 999, "adaptive": True,
             "fcst_h1": 1, "fcst_h2": 1, "fcst_h3": 1, "fcst_h4": 1,
             "wis_h1": 1, "wis_h2": 1, "wis_h3": 1, "wis_h4": 1,
             "n_steps": 1, "best_obj": 1.0, "mae": 0, "rmse": 0,
             "mape": 0, "wis_mean": 1, "bounds_changed": "-",
             "bounds_added": "-"},
        ])
        bt_csv = tmp_path / "bt.csv"
        bt.to_csv(bt_csv, index=False)
        team_csv = tmp_path / "team.csv"
        pd.DataFrame(columns=["reference_date", "location", "horizon",
                              "actual", "median", "wis", "over", "under",
                              "submission"]).to_csv(team_csv, index=False)
        cfg = FluBNFConfig.load()
        df = align_backtest_with_team(bt_csv, team_csv, "Alabama", cfg)
        assert len(df) == 0


class TestJoinAlignment:
    """Regression guard for the backtest<->team join.

    This join was wrong for a while: `reference_date` was set to week W's own
    ending date instead of W+1 week, so every comparison paired our forecast of
    one target week against the team's forecast of a DIFFERENT target week. It
    is invisible in the WIS numbers (both sides look plausible) and it moved
    per-state verdicts substantially, so it needs a test that checks the
    alignment itself rather than the scores.

    The check that catches it: both datasets carry the OBSERVED TRUTH for the
    cell they describe. If the join is aligned, the team's `actual` must equal
    our `actual_h{k}` for every matched cell. If it is off by a week, they never
    agree. See the module docstring in flubnf/compare.py for the derivation.
    """

    def test_shift_is_one_week(self):
        assert TEAM_REFERENCE_DATE_SHIFT_DAYS == 7

    def test_horizon_map_is_offset_by_one(self):
        # Their h=0 (week ending R) is our h=1 (week W+1), given the +7d shift.
        assert FLUSIGHT_TO_BACKTEST_HORIZON == {0: 1, 1: 2, 2: 3, 3: 4}

    def test_matched_cells_agree_on_observed_truth(self, tmp_path):
        """Synthetic end-to-end: build a backtest row and the team row it must
        match, give them the SAME truth for the same target week, and assert the
        aligner pairs them. A one-week slip breaks this."""
        cfg = FluBNFConfig.load()
        W = 20
        wk_end = season_week_to_date(cfg.season.year, cfg.season.onset_week, W)
        ref = (wk_end + timedelta(days=TEAM_REFERENCE_DATE_SHIFT_DAYS)).isoformat()

        # Truth for the 4 target weeks our h=1..4 predict (== their h=0..3).
        truth = {1: 100.0, 2: 200.0, 3: 300.0, 4: 400.0}
        bt = pd.DataFrame([{
            "state": "Alabama", "week": W, "adaptive": True,
            **{f"actual_h{h}": v for h, v in truth.items()},
            **{f"fcst_h{h}": v for h, v in truth.items()},
            **{f"wis_h{h}": 10.0 * h for h in truth},
        }])
        bt_csv = tmp_path / "bt.csv"
        bt.to_csv(bt_csv, index=False)

        team_rows = []
        for fs_h, bt_h in FLUSIGHT_TO_BACKTEST_HORIZON.items():
            team_rows.append({
                "reference_date": ref, "location": "01", "horizon": fs_h,
                "target_end_date": (wk_end + timedelta(days=7 * (fs_h + 1))).isoformat(),
                "wis": 20.0, "actual": truth[bt_h], "median": truth[bt_h],
            })
        team_csv = tmp_path / "team.csv"
        pd.DataFrame(team_rows).to_csv(team_csv, index=False)

        df = align_backtest_with_team(bt_csv, team_csv, "Alabama", cfg)
        assert not df.empty, "aligner matched nothing — the join slipped"
        assert len(df) == 4, f"expected 4 matched horizons, got {len(df)}"
        for _, r in df.iterrows():
            bt_h = FLUSIGHT_TO_BACKTEST_HORIZON[r["horizon"]]
            assert r["actual"] == pytest.approx(truth[bt_h]), (
                f"target-week mismatch at fs_h={r['horizon']}: team actual "
                f"{r['actual']} vs our actual_h{bt_h} {truth[bt_h]}"
            )
