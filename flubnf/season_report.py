"""Aggregate per-workspace season-progress report.

Pulls together signals that already live on disk in a workspace:
  * per-state session.history (bounds_changed, bounds_added, K evolution)
  * per-state calibration.json (rolling-window coverage diagnostics)
  * submissions/*.csv (forecast medians across the season)
  * results/<state>/Results/sorted_params_final.txt or AMCMC chain
    (most recent fit, best_obj)

Provides DataFrames suitable for plotting in the UI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .calibration import CalibrationTracker
from .paths import WorkspacePaths
from .session import load_session

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeasonReport:
    state_records: pd.DataFrame    # one row per (state, reference_date)
    calibration: pd.DataFrame      # one row per (state, horizon)
    submissions: pd.DataFrame      # one row per (state, ref_date, horizon)
    aggregate_k_trend: pd.DataFrame    # one row per ref_date
    aggregate_calibration: pd.DataFrame  # one row per (horizon)


def build_season_report(paths: WorkspacePaths) -> SeasonReport:
    """Assemble the report from all workspace artifacts."""
    state_rows = _collect_session_histories(paths)
    cal_rows = _collect_calibration(paths)
    sub_rows = _collect_submission_medians(paths)
    agg_k = _aggregate_k_trend(state_rows)
    agg_cal = _aggregate_calibration(cal_rows)
    return SeasonReport(
        state_records=state_rows,
        calibration=cal_rows,
        submissions=sub_rows,
        aggregate_k_trend=agg_k,
        aggregate_calibration=agg_cal,
    )


# ---------------------------------------------------------------------------
# Per-state session history
# ---------------------------------------------------------------------------
def _collect_session_histories(paths: WorkspacePaths) -> pd.DataFrame:
    """Each session has a list of history entries (one per weekly job).
    Convert into a long-format DataFrame for plotting."""
    sessions_dir = paths.root / "sessions"
    if not sessions_dir.exists():
        return pd.DataFrame(columns=[
            "state", "reference_date", "n_steps", "best_obj",
            "bounds_changed", "bounds_added",
        ])
    rows = []
    for p in sorted(sessions_dir.glob("*.json")):
        state = p.stem
        sess = load_session(paths.root, state)
        if sess is None:
            continue
        for entry in sess.history:
            rows.append({
                "state": state,
                "reference_date": entry.get("reference_date"),
                "n_steps": entry.get("n_steps", 1),
                "best_obj": entry.get("best_obj"),
                "bounds_changed": entry.get("bounds_changed", []),
                "bounds_added": entry.get("bounds_added", []),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["reference_date"] = pd.to_datetime(df["reference_date"]).dt.date.astype(str)
    return df


def _aggregate_k_trend(records: pd.DataFrame) -> pd.DataFrame:
    """Mean / max K across all states per reference_date."""
    if records.empty:
        return pd.DataFrame(columns=["reference_date", "mean_K", "max_K",
                                      "n_states_with_K_gt_1"])
    g = records.groupby("reference_date").agg(
        mean_K=("n_steps", "mean"),
        max_K=("n_steps", "max"),
        n_states=("state", "count"),
        n_states_with_K_gt_1=("n_steps", lambda s: int((s > 1).sum())),
    ).reset_index()
    return g


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def _collect_calibration(paths: WorkspacePaths) -> pd.DataFrame:
    p = paths.root / "calibration.json"
    if not p.exists():
        return pd.DataFrame(columns=[
            "state", "horizon", "n_records",
            "coverage_50", "coverage_80", "coverage_95", "rescale_factor",
        ])
    tracker = CalibrationTracker.load(p)
    rows = []
    for (state, h), recs in tracker.history.items():
        cov = tracker.empirical_coverage(state, h)
        factor = tracker.rescale_factor(state, h)
        rows.append({
            "state": state, "horizon": h, "n_records": len(recs),
            "coverage_50": cov.get(0.5),
            "coverage_80": cov.get(0.8),
            "coverage_95": cov.get(0.95),
            "rescale_factor": factor,
        })
    return pd.DataFrame(rows)


def _aggregate_calibration(cal: pd.DataFrame) -> pd.DataFrame:
    if cal.empty:
        return pd.DataFrame(columns=[
            "horizon", "n_states", "mean_coverage_50", "mean_coverage_80",
            "mean_coverage_95", "mean_rescale_factor",
        ])
    g = cal.groupby("horizon").agg(
        n_states=("state", "count"),
        mean_coverage_50=("coverage_50", "mean"),
        mean_coverage_80=("coverage_80", "mean"),
        mean_coverage_95=("coverage_95", "mean"),
        mean_rescale_factor=("rescale_factor", "mean"),
    ).reset_index()
    return g


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
def _collect_submission_medians(paths: WorkspacePaths) -> pd.DataFrame:
    sub_dir = paths.root / "submissions"
    if not sub_dir.exists():
        return pd.DataFrame(columns=[
            "reference_date", "state", "horizon", "median",
            "target_end_date", "location",
        ])
    rows = []
    for csv in sorted(sub_dir.glob("*.csv")):
        try:
            df = pd.read_csv(csv, dtype={"location": str})
        except Exception:
            continue
        df["location"] = df["location"].astype(str).str.zfill(2).where(
            df["location"] != "US", df["location"])
        medians = df[
            (df["output_type"] == "quantile") &
            (df["output_type_id"].astype(float) == 0.5)
        ].copy()
        for _, r in medians.iterrows():
            rows.append({
                "reference_date": str(r["reference_date"]),
                "location": r["location"],
                "horizon": int(r["horizon"]),
                "median": float(r["value"]),
                "target_end_date": str(r["target_end_date"]),
            })
    return pd.DataFrame(rows)
