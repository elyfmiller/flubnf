"""Generate per-state .exp files from a CDC weekly hospitalization CSV.

A `.exp` file is the tab-separated time-series PyBNF reads as observed data:

    #time   H_weekly
    0       27.0
    1       15.0
    ...

This is the deterministic, config-driven replacement for
`NAU_Influenza/scripts/110624_exp_generator.py`. Differences from the legacy
script: no hardcoded paths, no global state, handles missing weeks (NaN) by
truncating at the first NaN (consistent with legacy behavior — PyBNF expects
contiguous weekly observations), and is testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pymmwr as pm

from .config import FluBNFConfig
from .constants import JURISDICTIONS, STATE_TO_ABBREV
from .paths import WorkspacePaths

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpWriteResult:
    state: str
    path: Path
    n_weeks: int
    last_date: date | None


def generate_exp_files(
    cdc_csv: Path,
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    states: Iterable[str] | None = None,
) -> list[ExpWriteResult]:
    """Write one .exp per state from a CDC weekly CSV snapshot.

    Args:
        cdc_csv:  Path to the raw CDC CSV (from `fetch_cdc_data`).
        paths:    Workspace paths (the exp directory is created as needed).
        config:   FluBNF config (uses cdc.* column names and season.* window).
        states:   Restrict to these states (canonical underscore-joined names).
                  Defaults to all jurisdictions.
    """
    states = list(states or JURISDICTIONS)
    paths.exp_dir.mkdir(parents=True, exist_ok=True)

    date_col, geo_col, val_col = _resolve_columns(cdc_csv, config)
    df = pd.read_csv(cdc_csv, usecols=[date_col, geo_col, val_col], low_memory=False)
    df = df.sort_values([geo_col, date_col])
    # Stash resolved names on config so _write_one_state can use them.
    resolved = (date_col, geo_col, val_col)

    onset = pm.epiweek_to_date(pm.Epiweek(config.season.year, config.season.onset_week))
    end = pm.epiweek_to_date(
        pm.Epiweek(config.season.year + config.season.end_year_offset,
                   config.season.end_week)
    )

    results: list[ExpWriteResult] = []
    for state in states:
        abbrev = STATE_TO_ABBREV.get(state)
        if abbrev is None:
            log.warning("Unknown state %s, skipping", state)
            continue
        result = _write_one_state(
            df=df, state=state, abbrev=abbrev,
            onset=onset, end=end, paths=paths,
            date_col=resolved[0], geo_col=resolved[1], val_col=resolved[2],
        )
        results.append(result)
    return results


def _resolve_columns(cdc_csv: Path, config: FluBNFConfig) -> tuple[str, str, str]:
    """Pick the first column alias that exists in the CSV header for each
    of date / geo / value."""
    header = pd.read_csv(cdc_csv, nrows=0).columns
    available = set(header)
    def pick(aliases: list[str], kind: str) -> str:
        for a in aliases:
            if a in available:
                return a
        raise ValueError(
            f"None of the {kind} column aliases {aliases} found in {cdc_csv.name}. "
            f"Available columns: {sorted(available)[:10]}..."
        )
    return (
        pick(config.cdc.date_columns, "date"),
        pick(config.cdc.geo_columns, "geo"),
        pick(config.cdc.value_columns, "value"),
    )


def _write_one_state(
    *,
    df: pd.DataFrame,
    state: str,
    abbrev: str,
    onset: date,
    end: date,
    paths: WorkspacePaths,
    date_col: str,
    geo_col: str,
    val_col: str,
) -> ExpWriteResult:
    state_df = df[df[geo_col] == abbrev].copy()
    if state_df.empty:
        out = _write_empty(paths.exp_file(state))
        log.warning("No rows for %s (%s); wrote empty .exp", state, abbrev)
        return ExpWriteResult(state=state, path=out, n_weeks=0, last_date=None)

    # Parse dates and subtract one day to align with the legacy script
    # (CDC "Week Ending Date" is Saturday; the legacy code used previous-day).
    state_df["_date"] = (
        pd.to_datetime(state_df[date_col]) - pd.Timedelta(days=1)
    ).dt.date
    mask = (state_df["_date"] >= onset) & (state_df["_date"] < end)
    in_season = state_df[mask].copy().sort_values("_date")
    values = in_season[val_col].to_numpy(dtype=float)

    # Truncate at the first NaN (PyBNF expects contiguous weekly observations).
    if np.any(np.isnan(values)):
        first_nan = int(np.argmax(np.isnan(values)))
        values = values[:first_nan]
        last_date = in_season["_date"].iloc[first_nan - 1] if first_nan > 0 else None
    else:
        last_date = in_season["_date"].iloc[-1] if len(in_season) else None

    out_df = pd.DataFrame({
        "#time": np.arange(len(values), dtype=int),
        "H_weekly": values,
    })
    out_path = paths.exp_file(state)
    out_df.to_csv(out_path, sep="\t", index=False)
    return ExpWriteResult(
        state=state, path=out_path,
        n_weeks=len(values), last_date=last_date,
    )


def _write_empty(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"#time": [], "H_weekly": []}).to_csv(path, sep="\t", index=False)
    return path
