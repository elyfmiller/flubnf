"""Season-over-season priors from past best-fit parameters.

Each completed flu season produces per-state best-fit parameters
(b0, t0, gamma, mult, ...). Storing those gives us informative priors
for next year — when this state's outbreak typically starts, what
transmission rates are realistic, what the recovery rate looked like.

This module:
  - Records per-state, per-season parameter summaries on disk.
  - Loads historical summaries.
  - Emits adjusted initial bounds for a new season that combine the
    state-adaptive bounds (based on early-season observed) with the
    historical informed prior (when sufficient prior history exists).

The blend is gentle by default — the data drives the fit, history just
gives a head start. Mac Studio sweeps can find better blend weights
per state.

Format on disk: JSON at `<repo>/data/historical_priors/<state>.json`:

    {
        "state": "Alabama",
        "seasons": [
            {
                "season_year": 2024,
                "best_params": {"b0__FREE": 0.45, ...},
                "p25_params":  {"b0__FREE": 0.40, ...},
                "p75_params":  {"b0__FREE": 0.50, ...},
                "peak_admissions": 412,
                "peak_week": 27
            },
            ...
        ]
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .conf_files import FreeParam

log = logging.getLogger(__name__)


@dataclass
class SeasonSummary:
    """Per-state per-season parameter posterior summary."""
    season_year: int
    best_params: dict[str, float] = field(default_factory=dict)
    p25_params: dict[str, float] = field(default_factory=dict)
    p75_params: dict[str, float] = field(default_factory=dict)
    peak_admissions: float = 0.0
    peak_week: int = 0
    n_steps_final: int = 1


@dataclass
class StateHistory:
    state: str
    seasons: list[SeasonSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"state": self.state,
                "seasons": [asdict(s) for s in self.seasons]}

    @classmethod
    def from_dict(cls, d: dict) -> "StateHistory":
        return cls(
            state=d["state"],
            seasons=[SeasonSummary(**s) for s in d.get("seasons", [])],
        )


def history_path(repo_data_dir: Path, state: str) -> Path:
    return repo_data_dir / "historical_priors" / f"{state}.json"


def load_history(repo_data_dir: Path, state: str) -> Optional[StateHistory]:
    p = history_path(repo_data_dir, state)
    if not p.exists():
        return None
    try:
        return StateHistory.from_dict(json.loads(p.read_text()))
    except Exception as e:
        log.warning("could not load %s: %s", p, e)
        return None


def save_history(repo_data_dir: Path, hist: StateHistory) -> Path:
    p = history_path(repo_data_dir, hist.state)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(hist.to_dict(), indent=2))
    return p


def record_season(
    repo_data_dir: Path,
    state: str,
    season_year: int,
    population: pd.DataFrame,
    observed_full_season: np.ndarray,
    n_steps_final: int = 1,
) -> StateHistory:
    """Append a SeasonSummary to this state's history.

    `population` is a DE/AMCMC posterior DataFrame with __FREE columns
    and (optionally) an "Obj" column for the best fit. We summarize the
    top-N (best 50) into median/p25/p75.

    Idempotent: re-recording the same year overwrites.
    """
    hist = load_history(repo_data_dir, state) or StateHistory(state=state)
    # Drop any pre-existing entry for this year.
    hist.seasons = [s for s in hist.seasons if s.season_year != season_year]

    top = population.head(50) if len(population) > 50 else population
    param_cols = [c for c in top.columns if c.endswith("__FREE")]
    best_idx = 0
    if "Obj" in top.columns:
        best_idx = int(top["Obj"].idxmin())
    best_row = top.loc[best_idx] if not top.empty else None

    best_params = {c: float(best_row[c]) for c in param_cols} if best_row is not None else {}
    p25 = {c: float(top[c].quantile(0.25)) for c in param_cols} if not top.empty else {}
    p75 = {c: float(top[c].quantile(0.75)) for c in param_cols} if not top.empty else {}

    obs = np.asarray(observed_full_season, dtype=float)
    obs_finite = obs[np.isfinite(obs)]
    peak = float(obs_finite.max()) if obs_finite.size else 0.0
    peak_week = int(np.argmax(obs)) if len(obs) else 0

    summary = SeasonSummary(
        season_year=season_year,
        best_params=best_params,
        p25_params=p25,
        p75_params=p75,
        peak_admissions=peak,
        peak_week=peak_week,
        n_steps_final=int(n_steps_final),
    )
    hist.seasons.append(summary)
    hist.seasons.sort(key=lambda s: s.season_year)
    save_history(repo_data_dir, hist)
    return hist


def informed_initial_bounds(
    base_bounds: list[FreeParam],
    history: StateHistory,
    *,
    blend_weight: float = 0.5,
    require_min_seasons: int = 1,
    min_history_window_pct: float = 0.50,
) -> list[FreeParam]:
    """Blend `base_bounds` with the state's historical p25/p75 range.

    The new bounds are:
        new_low  = (1 - blend_weight) * base.low  + blend_weight * hist.p25
        new_high = (1 - blend_weight) * base.high + blend_weight * hist.p75

    But we never shrink below `min_history_window_pct` of the original
    base range — this keeps DE from being trapped by a fluky historical
    season.

    With <`require_min_seasons` seasons of history we return base_bounds
    unchanged.
    """
    if history is None or len(history.seasons) < require_min_seasons:
        return list(base_bounds)
    # Combine across all historical seasons: median p25, median p75.
    out: list[FreeParam] = []
    for fp in base_bounds:
        p25_vals = [s.p25_params[fp.name] for s in history.seasons
                    if fp.name in s.p25_params]
        p75_vals = [s.p75_params[fp.name] for s in history.seasons
                    if fp.name in s.p75_params]
        if not p25_vals or not p75_vals:
            out.append(fp)
            continue
        hist_p25 = float(np.median(p25_vals))
        hist_p75 = float(np.median(p75_vals))
        new_low = (1 - blend_weight) * fp.low + blend_weight * hist_p25
        new_high = (1 - blend_weight) * fp.high + blend_weight * hist_p75
        # Never let blended range shrink below min_history_window_pct of base.
        base_range = fp.high - fp.low
        min_range = min_history_window_pct * base_range
        if new_high - new_low < min_range:
            mid = 0.5 * (new_low + new_high)
            new_low, new_high = mid - min_range / 2, mid + min_range / 2
        # Don't let the new range cross zero if the original didn't.
        if fp.low >= 0:
            new_low = max(0.0, new_low)
        out.append(FreeParam(fp.name, float(new_low), float(new_high)))
    return out
