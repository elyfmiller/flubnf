"""Backfill `data/historical_priors/<state>.json` from legacy PyBNF runs.

Legacy on-disk fits live as

    <results_root>/<State>/Results/sorted_params_final.txt

The format matches what `flubnf.results.read_de_results` already parses
(tab-separated, `Obj` column + `__FREE` parameter columns), so this module
can lean on that.

For each legacy state we also need a peak-admissions value for the season,
which we pull from a FluSight-style target CSV (`date,location,
location_name,value,...`) filtered to the season window.

This module is pure logic — the matching CLI wrapper lives in `flubnf.cli`
under `flubnf backfill-priors`. Idempotent: re-running for the same year
overwrites that year's entry via `record_season`. Pass `force=False` to
skip states that already have an entry for the target year.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .constants import StateInfo
from .historical_priors import load_history, record_season
from .results import read_de_results


@dataclass(frozen=True)
class BackfillOutcome:
    state: str
    status: str           # ok | skipped-exists | no-fit | no-observed | error
    season_year: int
    peak: float = 0.0
    n_params: int = 0
    message: str = ""


def discover_states(results_root: Path) -> list[str]:
    """List every state under `results_root` that has a final sorted_params
    file. Returned in alphabetical order."""
    if not results_root.exists():
        return []
    found: list[str] = []
    for child in sorted(results_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "Results" / "sorted_params_final.txt").exists():
            found.append(child.name)
    return found


def season_window(season_year: int,
                  onset_week: int = 26,
                  end_year_offset: int = 1,
                  end_week: int = 47) -> tuple[date, date]:
    """Return (onset_saturday, end_saturday) for the season starting in
    `season_year` at MMWR `onset_week`.

    Mirrors `flubnf.config.SeasonConfig` defaults (26 / +1 / 47).
    """
    import pymmwr as pm
    onset = pm.epiweek_to_date(pm.Epiweek(season_year, onset_week))
    end = pm.epiweek_to_date(
        pm.Epiweek(season_year + end_year_offset, end_week))
    return onset, end


def observed_for_state(
    target_df: pd.DataFrame,
    info: StateInfo,
    onset: date,
    end: date,
) -> np.ndarray:
    """Slice FluSight target rows for one state within [onset, end).

    The FluSight `target-hospital-admissions.csv` has columns
    `date, location, location_name, value, ...` where `location` is the
    FIPS string. We match on FIPS (zero-padded) for robustness.

    Returned series is indexed by Saturday step from `onset` — entries
    missing in the CSV become NaN, then we truncate at the first NaN
    (matching the convention in `cli._observed_for_state`).
    """
    if "location" not in target_df.columns:
        return np.array([])
    fips = info.fips.zfill(2)
    sub = target_df[target_df["location"].astype(str).str.zfill(2) == fips].copy()
    if sub.empty:
        return np.array([])
    sub["_d"] = pd.to_datetime(sub["date"]).dt.date
    sub = sub.sort_values("_d")
    in_season = sub[(sub["_d"] >= onset) & (sub["_d"] < end)]
    if in_season.empty:
        return np.array([])
    # FluSight target dates are the Saturday week-ending date; `onset` from
    # pymmwr is the Sunday of the same MMWR week, so the per-week date we
    # need is onset + 7*i + 6 days. Truncate at first NaN, mirroring
    # `cli._observed_for_state`.
    by_date = {row["_d"]: float(row["value"]) for _, row in in_season.iterrows()}
    n_weeks = (end - onset).days // 7
    out = np.array(
        [by_date.get(onset + timedelta(days=7 * i + 6), np.nan)
         for i in range(n_weeks)],
        dtype=float,
    )
    if np.any(np.isnan(out)):
        first_nan = int(np.argmax(np.isnan(out)))
        out = out[:first_nan]
    return out


def backfill_state(
    repo_data_dir: Path,
    state: str,
    season_year: int,
    state_results_dir: Path,
    target_df: pd.DataFrame,
    locations: dict[str, StateInfo],
    onset: date,
    end: date,
    *,
    n_steps_final: int = 1,
    force: bool = False,
    dry_run: bool = False,
) -> BackfillOutcome:
    """Pull one state's posterior + observed peak; write a history entry.

    Returns a BackfillOutcome describing what happened. Side effects only
    when `dry_run=False`.
    """
    if not force and not dry_run:
        existing = load_history(repo_data_dir, state)
        if existing and any(s.season_year == season_year for s in existing.seasons):
            return BackfillOutcome(
                state=state, status="skipped-exists", season_year=season_year,
                message=f"history already has {season_year}",
            )

    info = locations.get(state)
    if info is None:
        return BackfillOutcome(
            state=state, status="error", season_year=season_year,
            message="state not in locations table",
        )

    de = read_de_results(state_results_dir, state)
    if de is None or de.population.empty:
        return BackfillOutcome(
            state=state, status="no-fit", season_year=season_year,
            message=f"no sorted_params_final under {state_results_dir}",
        )

    obs = observed_for_state(target_df, info, onset, end)
    if obs.size == 0:
        return BackfillOutcome(
            state=state, status="no-observed", season_year=season_year,
            n_params=len(de.param_names),
            message="no in-season target rows for this state",
        )

    peak = float(np.nanmax(obs)) if obs.size else 0.0
    if dry_run:
        return BackfillOutcome(
            state=state, status="ok", season_year=season_year,
            peak=peak, n_params=len(de.param_names),
            message="dry-run; not written",
        )

    try:
        record_season(
            repo_data_dir, state, season_year, de.population, obs,
            n_steps_final=n_steps_final,
        )
    except Exception as e:
        return BackfillOutcome(
            state=state, status="error", season_year=season_year,
            n_params=len(de.param_names), message=f"record_season failed: {e}",
        )
    return BackfillOutcome(
        state=state, status="ok", season_year=season_year,
        peak=peak, n_params=len(de.param_names),
    )


def backfill_all(
    repo_data_dir: Path,
    *,
    season_year: int,
    results_root: Path,
    target_csv: Path,
    locations: dict[str, StateInfo],
    states: Optional[Iterable[str]] = None,
    onset_week: int = 26,
    end_year_offset: int = 1,
    end_week: int = 47,
    n_steps_final: int = 1,
    force: bool = False,
    dry_run: bool = False,
) -> list[BackfillOutcome]:
    """Walk `results_root`, backfilling every state (or just `states` if given).

    Loads the target CSV once and reuses it across states.
    """
    if not target_csv.exists():
        raise FileNotFoundError(f"target CSV not found: {target_csv}")
    target_df = pd.read_csv(target_csv, dtype={"location": str})

    onset, end = season_window(season_year, onset_week, end_year_offset, end_week)
    discovered = discover_states(results_root)
    if states is not None:
        wanted = set(states)
        discovered = [s for s in discovered if s in wanted]

    out: list[BackfillOutcome] = []
    for state in discovered:
        out.append(backfill_state(
            repo_data_dir, state, season_year,
            results_root / state, target_df, locations, onset, end,
            n_steps_final=n_steps_final, force=force, dry_run=dry_run,
        ))
    return out
