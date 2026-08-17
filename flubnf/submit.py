"""Build a FluSight-submittable CSV from a set of per-state forecasts.

The submission schema (per row):

    reference_date, target, horizon, target_end_date,
    location, output_type, output_type_id, value

A complete weekly submission has, for each (state, horizon ∈ {0..3}):
  - 23 quantile rows (output_type=quantile, output_type_id ∈ FLUSIGHT_QUANTILES)
  - Plus a 'point' (median) row is sometimes included as a convenience.

We additionally aggregate per-state quantiles into a US total by summing
the same quantile level across all states. This is what the legacy
PyBNF_to_CDC_121524.py script does — not statistically pure, but it matches
the team's current production behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional

import numpy as np
import pandas as pd

from .constants import STATE_TO_ABBREV, load_locations
from .config import FluBNFConfig
from .quantiles import FLUSIGHT_QUANTILES, QuantileForecast

log = logging.getLogger(__name__)


# Mapping our 1-indexed backtest horizons to FluSight 0-indexed horizons.
BACKTEST_TO_FLUSIGHT_HORIZON = {1: 0, 2: 1, 3: 2, 4: 3}


@dataclass
class StateForecast:
    state: str
    forecast: QuantileForecast    # produced by quantiles.quantile_forecast


def build_submission_dataframe(
    forecasts: Iterable[StateForecast],
    *,
    reference_date: date,
    config: FluBNFConfig,
    target_name: str = "wk inc flu hosp",
    include_us_aggregate: bool = True,
) -> pd.DataFrame:
    """Produce the FluSight-format DataFrame for one submission week.

    `reference_date` is the Saturday of the submission week (the FluSight
    convention). Each forecast horizon h in {0,1,2,3} is mapped to
    target_end_date = reference_date + h * 7 days.
    """
    locs = load_locations(config.locations_csv)
    rows: list[dict] = []
    us_aggregates: dict[tuple[int, float], float] = {}

    for sf in forecasts:
        abbrev = STATE_TO_ABBREV.get(sf.state)
        if abbrev is None or sf.state not in locs:
            log.warning("skipping unknown state %s", sf.state)
            continue
        fips = locs[sf.state].fips
        qd = sf.forecast.to_dict()
        for bt_h, fs_h in BACKTEST_TO_FLUSIGHT_HORIZON.items():
            if bt_h not in qd:
                continue
            target_end_date = reference_date + timedelta(days=7 * fs_h)
            quantile_map = qd[bt_h]
            for q_level in FLUSIGHT_QUANTILES:
                value = quantile_map.get(q_level)
                if value is None:
                    # Tolerant key lookup via the wis module's approach.
                    for k, v in quantile_map.items():
                        if abs(float(k) - q_level) < 1e-6:
                            value = v
                            break
                if value is None:
                    continue
                rows.append({
                    "reference_date": reference_date.isoformat(),
                    "target": target_name,
                    "horizon": fs_h,
                    "target_end_date": target_end_date.isoformat(),
                    "location": fips,
                    "output_type": "quantile",
                    "output_type_id": q_level,
                    "value": max(0.0, float(value)),
                })
                if include_us_aggregate:
                    key = (fs_h, q_level)
                    us_aggregates[key] = us_aggregates.get(key, 0.0) + max(0.0, float(value))

    if include_us_aggregate:
        for (fs_h, q_level), value in us_aggregates.items():
            target_end_date = reference_date + timedelta(days=7 * fs_h)
            rows.append({
                "reference_date": reference_date.isoformat(),
                "target": target_name,
                "horizon": fs_h,
                "target_end_date": target_end_date.isoformat(),
                "location": "US",
                "output_type": "quantile",
                "output_type_id": q_level,
                "value": value,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        # Sort to match FluSight convention.
        df = df.sort_values(
            ["location", "horizon", "output_type_id"]
        ).reset_index(drop=True)
    return df


def write_submission(
    df: pd.DataFrame,
    reference_date: date,
    out_dir: Path,
    *,
    team_model: str = "LosAlamos_NAU-CModel_Flu",
    validate: bool = True,
    strict: bool = False,
) -> Path:
    """Write the submission CSV to out_dir using FluSight's filename convention.

    Args:
        validate: if True, run schema validation. Warnings always logged.
        strict:   if True, raise ValueError on any validation error.
                  if False (default), log errors but write anyway —
                  surfacing the issue without blocking emergency runs.
    """
    if validate:
        from .validate import validate_submission_df
        report = validate_submission_df(df)
        for w in report.warnings:
            log.warning("submission validation: %s", w)
        if not report.ok:
            for e in report.errors:
                log.error("submission validation: %s", e)
            if strict:
                raise ValueError(
                    f"submission failed validation with "
                    f"{len(report.errors)} error(s); first: {report.errors[0]}"
                )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{reference_date.isoformat()}-{team_model}.csv"
    df.to_csv(out, index=False)
    log.info("wrote submission: %s (%d rows)", out, len(df))
    return out
