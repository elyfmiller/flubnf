"""Per-state, week-over-week session state.

In production, each Tuesday the team runs the weekly job. The bounds the
analyzer expanded last week + the piecewise step count we settled on
should carry into this week — otherwise every fit starts from a cold
template and the cumulative learning is wasted.

This module persists per-state session state as JSON under

    <workspace>/sessions/<state>.json

Each file holds:
  - `bounds`: list of `{name, low, high}` records (the current uniform_var ranges)
  - `n_steps`: piecewise beta segment count
  - `last_reference_date`: ISO-formatted Saturday of the most recent run
  - `history`: brief log of past adaptations

The walk-forward backtest already maintains this state in memory; this
module is the *persistent* mirror for the one-shot weekly-job workflow.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from .conf_files import FreeParam

log = logging.getLogger(__name__)


@dataclass
class StateSession:
    state: str
    bounds: list[FreeParam] = field(default_factory=list)
    n_steps: int = 1
    last_reference_date: Optional[str] = None
    history: list[dict] = field(default_factory=list)
    # Per-state hyperparameter overrides. Anything in here takes
    # precedence over the global defaults. Common keys:
    #   slope_blend   : float in [0, 1] or -1 (auto-tune)
    #   anchor_lookback: int >= 1
    #   phase_aware   : bool
    #   max_K         : int (override max_steps_for_state)
    #   max_iter      : int (per-state AMCMC iters)
    # Calibrated values from Mac Studio sweeps persist here and survive
    # weekly job runs.
    tuning: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "bounds": [{"name": fp.name, "low": fp.low, "high": fp.high}
                       for fp in self.bounds],
            "n_steps": self.n_steps,
            "last_reference_date": self.last_reference_date,
            "history": self.history,
            "tuning": self.tuning,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StateSession":
        bounds = [FreeParam(b["name"], b["low"], b["high"])
                  for b in d.get("bounds", [])]
        return cls(
            state=d["state"],
            bounds=bounds,
            n_steps=int(d.get("n_steps", 1)),
            last_reference_date=d.get("last_reference_date"),
            history=list(d.get("history", [])),
            tuning=dict(d.get("tuning", {})),
        )

    def get_tuning(self, key: str, default):
        """Look up a tuning hyperparameter with a fallback."""
        return self.tuning.get(key, default)


def session_path(workspace_root: Path, state: str) -> Path:
    return workspace_root / "sessions" / f"{state}.json"


def load_session(workspace_root: Path, state: str) -> Optional[StateSession]:
    p = session_path(workspace_root, state)
    if not p.exists():
        return None
    try:
        return StateSession.from_dict(json.loads(p.read_text()))
    except Exception as e:
        log.warning("could not load session %s: %s", p, e)
        return None


def save_session(workspace_root: Path, session: StateSession) -> Path:
    p = session_path(workspace_root, session.state)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(session.to_dict(), indent=2, default=str))
    return p


def record_step(
    session: StateSession,
    *,
    reference_date: date,
    bounds_changed: list[str],
    bounds_added: list[str],
    best_obj: Optional[float],
) -> None:
    session.history.append({
        "reference_date": reference_date.isoformat(),
        "bounds_changed": bounds_changed,
        "bounds_added": bounds_added,
        "best_obj": best_obj,
        "n_steps": session.n_steps,
    })
    session.last_reference_date = reference_date.isoformat()
