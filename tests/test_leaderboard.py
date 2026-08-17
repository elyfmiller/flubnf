"""Tests for flubnf.leaderboard."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.config import FluBNFConfig
from flubnf.leaderboard import join_with_team, leaderboard


def _make_our_scored() -> pd.DataFrame:
    """Synthetic per-(date,loc,horizon) WIS dataframe for ours.

    Alabama: WE WIN (lower WIS than team).
    California: WE LOSE (higher WIS than team).
    """
    rows = []
    for ref in ["2026-01-03", "2026-01-10"]:
        # Alabama — our WIS lower than team's.
        for h in range(4):
            rows.append({
                "reference_date": ref, "location": "01", "state": "Alabama",
                "horizon": h, "actual": 100.0, "our_median": 95.0,
                "our_wis": 50.0 + h * 10,    # 50, 60, 70, 80
                "target_end_date": "2026-01-10",
            })
        # California — our WIS much higher than team's.
        for h in range(4):
            rows.append({
                "reference_date": ref, "location": "06", "state": "California",
                "horizon": h, "actual": 800.0, "our_median": 600.0,
                "our_wis": 400.0 + h * 50,   # 400, 450, 500, 550
                "target_end_date": "2026-01-10",
            })
    return pd.DataFrame(rows)


def _make_team_csv(tmp_path: Path) -> Path:
    rows = []
    for ref in ["2026-01-03", "2026-01-10"]:
        for h in range(4):
            # Alabama team WIS HIGHER than ours.
            rows.append({
                "reference_date": ref, "location": "01", "horizon": h,
                "wis": 80.0 + h * 8, "median": 100.0,
            })
            # California team WIS LOWER than ours.
            rows.append({
                "reference_date": ref, "location": "06", "horizon": h,
                "wis": 200.0 + h * 20, "median": 800.0,
            })
    csv = tmp_path / "team_scored.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return csv


def test_join_combines_us_with_team(tmp_path):
    ours = _make_our_scored()
    team_csv = _make_team_csv(tmp_path)
    merged = join_with_team(ours, team_csv)
    assert not merged.empty
    assert len(merged) == 16  # 2 dates × 2 states × 4 horizons
    assert "team_wis" in merged.columns
    assert "delta_wis" in merged.columns
    assert "we_win" in merged.columns


def test_join_handles_empty(tmp_path):
    assert join_with_team(pd.DataFrame(), tmp_path / "x.csv").empty


def test_leaderboard_aggregates(tmp_path):
    ours = _make_our_scored()
    team_csv = _make_team_csv(tmp_path)
    lb = leaderboard(ours, team_csv)
    assert not lb["by_state"].empty
    # Alabama: our_wis = 50, 60, 70, 80 → mean 65; team_wis = 60, 68, 76, 84 → mean 72.
    # delta = 65 - 72 = -7. Alabama should be in win column.
    al_row = lb["by_state"][lb["by_state"]["state"] == "Alabama"].iloc[0]
    assert al_row["we_win_rate"] == 1.0   # 100% of cells
    # California is worse (we add +50 to our_wis):
    ca_row = lb["by_state"][lb["by_state"]["state"] == "California"].iloc[0]
    assert ca_row["delta_mean"] > 0
    # by_horizon and by_week have rows.
    assert len(lb["by_horizon"]) == 4
    assert len(lb["by_week"]) == 2


def test_leaderboard_when_no_team_csv(tmp_path):
    lb = leaderboard(_make_our_scored(), tmp_path / "nonexistent.csv")
    assert lb["by_state"].empty
