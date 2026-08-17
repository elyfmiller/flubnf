"""Per-workspace state ledger.

Tracks what the pipeline has done for this workspace, so the UI and CLI can
show status and so stages can detect "nothing to do". Plain JSON; no
migrations until we need them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class StageRecord:
    name: str
    status: str  # "ok", "error", "skipped"
    ts: str  # ISO timestamp
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceState:
    workspace: str
    season_year: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    last_data_as_of: str | None = None     # YYYY-MM-DD of last CDC pull
    n_piecewise_steps: dict[str, int] = field(default_factory=dict)  # per state
    stages: list[StageRecord] = field(default_factory=list)

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------
    @classmethod
    def load_or_create(cls, path: Path, workspace: str, season_year: int) -> "WorkspaceState":
        if path.exists():
            with open(path) as f:
                raw = json.load(f)
            raw["stages"] = [StageRecord(**s) for s in raw.get("stages", [])]
            return cls(**raw)
        return cls(workspace=workspace, season_year=season_year)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Stage logging
    # ------------------------------------------------------------------
    def record(self, name: str, status: str = "ok", **details: Any) -> None:
        self.stages.append(StageRecord(
            name=name, status=status,
            ts=datetime.now().isoformat(timespec="seconds"),
            details=details,
        ))
