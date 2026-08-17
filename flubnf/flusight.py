"""Parse FluSight forecast-hub submissions and compute WIS against ground truth.

The FluSight hub publishes each team's per-week submission as a CSV with
columns: reference_date, target, horizon, target_end_date, location,
output_type, output_type_id, value.

Ground truth lives at target-data/target-hospital-admissions.csv with one
row per (date, location) pair.

This module:
  - parses a submission file into a {(date,location,horizon): {q: value}} map
  - aligns with ground truth at target_end_date
  - computes WIS per (week, state, horizon) using the same `flubnf.wis` code
    we use on our own backtest forecasts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .wis import FLUSIGHT_PI_QUANTILES, wis

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FluSightScore:
    reference_date: str
    location: str           # FIPS code, e.g. "01"
    horizon: int
    actual: float
    median: float
    wis: float
    over: float
    under: float


def parse_submission(path: Path) -> pd.DataFrame:
    """Parse one weekly submission CSV. Returns the quantile rows only."""
    df = pd.read_csv(path, dtype={"location": str})
    df = df[df["output_type"] == "quantile"].copy()
    df["output_type_id"] = df["output_type_id"].astype(float)
    return df


def parse_target(path: Path) -> pd.DataFrame:
    """Parse target-hospital-admissions.csv into a (date, location) -> value lookup."""
    df = pd.read_csv(path, dtype={"location": str})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "location", "value"]]


def score_submission(
    submission: pd.DataFrame, target: pd.DataFrame,
) -> list[FluSightScore]:
    """Compute WIS for every (date, location, horizon) tuple in a submission.

    Returns one FluSightScore per tuple. Quantile dicts are reconstructed by
    pivoting on output_type_id.
    """
    target_map = {
        (row.date, row.location): float(row.value)
        for row in target.itertuples()
    }
    out: list[FluSightScore] = []
    for (ref_date, location, horizon), group in submission.groupby(
        ["reference_date", "location", "horizon"], sort=False,
    ):
        end_date = pd.to_datetime(group["target_end_date"].iloc[0]).date()
        actual = target_map.get((end_date, location))
        if actual is None:
            continue
        q = dict(zip(group["output_type_id"].to_numpy(),
                     group["value"].to_numpy()))
        try:
            w = wis(q, actual)
        except (KeyError, ValueError):
            continue
        out.append(FluSightScore(
            reference_date=str(ref_date),
            location=location,
            horizon=int(horizon),
            actual=actual,
            median=q.get(0.5, float("nan")),
            wis=w.wis,
            over=w.overprediction,
            under=w.underprediction,
        ))
    return out


def score_all_submissions(
    submission_paths: Iterable[Path],
    target_path: Path,
    *,
    locations: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """Score multiple submissions at once and return one big tidy DataFrame."""
    target = parse_target(target_path)
    rows = []
    location_filter = set(locations) if locations else None
    for sp in submission_paths:
        sub = parse_submission(sp)
        if location_filter:
            sub = sub[sub["location"].isin(location_filter)]
        scores = score_submission(sub, target)
        for s in scores:
            rows.append({
                "reference_date": s.reference_date,
                "location": s.location,
                "horizon": s.horizon,
                "actual": s.actual,
                "median": s.median,
                "wis": s.wis,
                "over": s.over,
                "under": s.under,
                "submission": sp.name,
            })
    return pd.DataFrame(rows)
