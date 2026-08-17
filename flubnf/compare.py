"""Compare our walk-forward backtest WIS scores to the team's actual
LosAlamos_NAU-CModel_Flu submissions on the FluSight hub.

Aligning the two conventions takes BOTH a horizon map and a one-week date shift.
Getting either wrong silently compares forecasts of different target weeks, or
hands one side extra data. This was wrong for a while (see the regression test in
`tests/test_compare.py::TestJoinAlignment`), so the derivation is spelled out.

* The team submits at `reference_date` R with CDC data settled only through
  about R-7. Their horizon h=0 targets the week ending R, h=1 targets R+7, ...

* Our backtest at week W has week W FULLY observed, and its horizon h=1 targets
  week W+1.

Equal information therefore requires the team's last settled week to be our week
W, i.e. R - 7 = date(W), i.e. **R = date(W) + 7 days**
(`TEAM_REFERENCE_DATE_SHIFT_DAYS`). With that shift the target weeks line up as
FluSight h={0,1,2,3} -> backtest h={1,2,3,4}, because their h=0 (week ending R)
is our W+1.

The two errors this rules out, both verified empirically against observed truth:
  * shift=0 with h={0:1,...}: target weeks are off by one week (the team's
    `actual` never equals ours for a matched cell).
  * shift=0 with h={1:1,2:2,3:3}: target weeks DO line up, but our week W is
    already observed while the team had not seen it, so we get a free extra week
    of data and the comparison flatters us.

The CDC weekly-ending-date for season week W (0-indexed from MMWR week 26 of the
season year) is computed via pymmwr.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pymmwr as pm

from .config import FluBNFConfig
from .constants import STATE_TO_ABBREV


FLUSIGHT_TO_BACKTEST_HORIZON = {0: 1, 1: 2, 2: 3, 3: 4}

# Days to add to backtest week W's ending date to get the team submission
# reference_date it is comparable to. +7 equalises the information sets: the team
# submitting at R had settled data through ~R-7, which must equal our week W.
TEAM_REFERENCE_DATE_SHIFT_DAYS = 7


def season_week_to_date(season_year: int, onset_week: int, week_index: int) -> date:
    """Convert (season_year, week_index) -> Saturday calendar date.

    week_index is 0-indexed from `onset_week` (MMWR week of `season_year`).
    The Saturday-of-week is the FluSight reference convention.
    """
    onset_saturday = pm.epiweek_to_date(pm.Epiweek(season_year, onset_week))
    # pymmwr returns the Sunday of the epiweek. Shift to Saturday by +6 days.
    return onset_saturday + timedelta(days=6 + 7 * week_index)


def align_backtest_with_team(
    backtest_csv: Path,
    team_scores_csv: Path,
    state: str,
    config: FluBNFConfig,
    *,
    location_fips: Optional[str] = None,
) -> pd.DataFrame:
    """Build a side-by-side comparison row per (week, horizon) pair.

    Columns: reference_date, horizon, our_wis_static, our_wis_adapt, team_wis,
             our_mae_static, our_mae_adapt, team_abs_err.
    """
    if location_fips is None:
        # Derive from state name.
        abbrev = STATE_TO_ABBREV.get(state)
        if abbrev is None:
            raise KeyError(f"unknown state: {state}")
        from .constants import load_locations
        locs = load_locations(config.locations_csv)
        location_fips = locs[state].fips

    backtest = pd.read_csv(backtest_csv)
    # When the backtest CSV contains multiple states (e.g. `-s A,B,C`),
    # filter down to just the one we are comparing — otherwise the per-week
    # groupby below silently mixes rows across states.
    if "state" in backtest.columns:
        backtest = backtest[backtest["state"] == state].copy()
        if backtest.empty:
            raise ValueError(f"no backtest rows for state {state!r}")
    # location must stay as a 2-digit FIPS string. pandas otherwise reads
    # "01" -> 1 (int) and the filter below silently returns no rows.
    team = pd.read_csv(team_scores_csv, dtype={"location": str})
    if team.empty or "location" not in team.columns:
        return pd.DataFrame()
    team["location"] = team["location"].astype(str).str.zfill(2)

    # Tag each backtest row with the TEAM SUBMISSION reference_date it should be
    # compared against. This is week W's ending date PLUS ONE WEEK -- see
    # `TEAM_REFERENCE_DATE_SHIFT_DAYS` for the derivation. Getting this wrong by
    # one week silently compares forecasts of two different target weeks.
    backtest["reference_date"] = backtest["week"].apply(
        lambda w: (season_week_to_date(
            config.season.year, config.season.onset_week, w,
        ) + timedelta(days=TEAM_REFERENCE_DATE_SHIFT_DAYS)).isoformat()
    )

    # Filter team scores to this state.
    team_state = team[team["location"] == location_fips].copy()
    team_state["reference_date"] = pd.to_datetime(team_state["reference_date"]).dt.date.astype(str)

    rows: list[dict] = []
    for ref_date, group in backtest.groupby("reference_date"):
        team_for_date = team_state[team_state["reference_date"] == ref_date]
        if team_for_date.empty:
            continue
        adapt = group[group["adaptive"] == True].iloc[0] if (group["adaptive"] == True).any() else None
        static = group[group["adaptive"] == False].iloc[0] if (group["adaptive"] == False).any() else None
        for fs_h, bt_h in FLUSIGHT_TO_BACKTEST_HORIZON.items():
            team_h = team_for_date[team_for_date["horizon"] == fs_h]
            if team_h.empty:
                continue
            row = {
                "reference_date": ref_date,
                "horizon": fs_h,
                "team_wis": float(team_h["wis"].iloc[0]),
                "team_abs_err": float(abs(team_h["actual"].iloc[0]
                                          - team_h["median"].iloc[0])),
                "actual": float(team_h["actual"].iloc[0]),
                "team_median": float(team_h["median"].iloc[0]),
            }
            if adapt is not None and f"wis_h{bt_h}" in adapt:
                row["our_wis_adapt"] = float(adapt[f"wis_h{bt_h}"])
            if static is not None and f"wis_h{bt_h}" in static:
                row["our_wis_static"] = float(static[f"wis_h{bt_h}"])
            if adapt is not None and f"fcst_h{bt_h}" in adapt:
                row["our_median_adapt"] = float(adapt[f"fcst_h{bt_h}"])
            if static is not None and f"fcst_h{bt_h}" in static:
                row["our_median_static"] = float(static[f"fcst_h{bt_h}"])
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["reference_date", "horizon"]).reset_index(drop=True)


def summarize_alignment(df: pd.DataFrame) -> pd.DataFrame:
    """Per-horizon summary: mean WIS for team vs adapt vs static."""
    keep = []
    for h in sorted(df["horizon"].unique()):
        slc = df[df["horizon"] == h]
        keep.append({
            "horizon": h,
            "n": len(slc),
            "team_wis_mean": slc["team_wis"].mean(),
            "team_wis_median": slc["team_wis"].median(),
            "adapt_wis_mean": slc.get("our_wis_adapt", pd.Series()).mean(),
            "static_wis_mean": slc.get("our_wis_static", pd.Series()).mean(),
        })
    return pd.DataFrame(keep)
