"""Season-long WIS leaderboard: us vs team across all states + horizons.

Reads:
  * `backtest_results/flusight_team_scored.csv` (team submissions scored
    via `flubnf score-team`)
  * a per-state submission set (workspace's `submissions/<date>-*.csv`)
    OR a backtest CSV with `wis_h*` columns
  * the observed actuals from a CDC CSV (for scoring our submissions)

Emits:
  * Per-(state, horizon) WIS for both us and team
  * Aggregate leaderboard ordered by Δ (our_wis - team_wis)
  * Per-week trend showing whether the gap is widening or narrowing
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pymmwr as pm

from .config import FluBNFConfig
from .constants import load_locations
from .paths import WorkspacePaths
from .wis import wis as wis_fn

log = logging.getLogger(__name__)


def score_our_submissions(
    submissions_dir: Path,
    observed_csv: Path,
    config: FluBNFConfig,
) -> pd.DataFrame:
    """Score every submission CSV in `submissions_dir` against observed
    admissions from `observed_csv`. Returns one row per (reference_date,
    location, horizon) with our_wis, our_median, actual."""
    locs = load_locations(config.locations_csv)
    fips_to_state = {info.fips: name for name, info in locs.items()}
    df_obs = pd.read_csv(observed_csv)
    from .backtest import _resolve_columns_quick
    geo_col, date_col, val_col = _resolve_columns_quick(df_obs, config)
    df_obs["_d"] = pd.to_datetime(df_obs[date_col]) - pd.Timedelta(days=1)
    df_obs = df_obs.sort_values([geo_col, "_d"])

    rows = []
    for sub_path in sorted(submissions_dir.glob("*.csv")):
        try:
            sub = pd.read_csv(sub_path, dtype={"location": str})
        except Exception:
            continue
        if sub.empty:
            continue
        sub["location"] = sub["location"].astype(str).str.zfill(2).where(
            sub["location"] != "US", sub["location"])
        ref_date = str(sub["reference_date"].iloc[0])
        for (fips, h), group in sub[sub["output_type"] == "quantile"].groupby(
                ["location", "horizon"]):
            state = fips_to_state.get(fips)
            if state is None or state not in locs:
                continue
            abbrev = locs[state].abbreviation
            tgt = str(group["target_end_date"].iloc[0])
            obs_state = df_obs[df_obs[geo_col] == abbrev]
            obs_row = obs_state[obs_state["_d"].dt.date.astype(str) == tgt]
            if obs_row.empty:
                continue
            actual = float(obs_row[val_col].iloc[0])
            if not np.isfinite(actual):
                continue
            qd = dict(zip(group["output_type_id"].astype(float),
                          group["value"].astype(float)))
            try:
                our_wis = wis_fn(qd, actual).wis
            except Exception:
                continue
            rows.append({
                "reference_date": ref_date,
                "location": fips,
                "state": state,
                "horizon": int(h),
                "actual": actual,
                "our_median": float(qd.get(0.5, np.nan)),
                "our_wis": float(our_wis),
                "target_end_date": tgt,
            })
    return pd.DataFrame(rows)


def join_with_team(
    our_scored: pd.DataFrame,
    team_scored_csv: Path,
) -> pd.DataFrame:
    """Inner-join our scores with team's per-(date, location, horizon) WIS."""
    if our_scored.empty or not team_scored_csv.exists():
        return pd.DataFrame()
    team = pd.read_csv(team_scored_csv, dtype={"location": str})
    team["location"] = team["location"].astype(str).str.zfill(2).where(
        team["location"] != "US", team["location"])
    team["reference_date"] = pd.to_datetime(team["reference_date"]).dt.date.astype(str)
    keep = ["reference_date", "location", "horizon", "wis", "median"]
    keep = [c for c in keep if c in team.columns]
    team = team[keep].rename(columns={"wis": "team_wis",
                                       "median": "team_median"})
    merged = our_scored.merge(
        team, on=["reference_date", "location", "horizon"],
        how="inner",
    )
    if not merged.empty:
        merged["delta_wis"] = merged["our_wis"] - merged["team_wis"]
        merged["we_win"] = merged["delta_wis"] < 0
    return merged


def leaderboard(our_scored: pd.DataFrame, team_scored_csv: Path) -> dict:
    """Return three dataframes:
      - by_state: aggregate WIS per state (ours, team, delta, win rate)
      - by_horizon: aggregate WIS per horizon
      - by_week: per-week mean WIS trend (us vs team).
    """
    merged = join_with_team(our_scored, team_scored_csv)
    if merged.empty:
        return {"by_state": pd.DataFrame(),
                "by_horizon": pd.DataFrame(),
                "by_week": pd.DataFrame(),
                "merged": pd.DataFrame()}

    by_state = merged.groupby("state").agg(
        n_cells=("delta_wis", "count"),
        our_mean_wis=("our_wis", "mean"),
        team_mean_wis=("team_wis", "mean"),
        delta_mean=("delta_wis", "mean"),
        we_win_rate=("we_win", "mean"),
    ).reset_index().sort_values("delta_mean")

    by_horizon = merged.groupby("horizon").agg(
        n_cells=("delta_wis", "count"),
        our_mean_wis=("our_wis", "mean"),
        team_mean_wis=("team_wis", "mean"),
        delta_mean=("delta_wis", "mean"),
        we_win_rate=("we_win", "mean"),
    ).reset_index()

    by_week = merged.groupby("reference_date").agg(
        n_cells=("delta_wis", "count"),
        our_mean_wis=("our_wis", "mean"),
        team_mean_wis=("team_wis", "mean"),
        delta_mean=("delta_wis", "mean"),
        we_win_rate=("we_win", "mean"),
    ).reset_index()

    return {
        "by_state": by_state,
        "by_horizon": by_horizon,
        "by_week": by_week,
        "merged": merged,
    }
