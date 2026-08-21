"""Run ledger, workroot leasing, and seed derivation.

This module IS the constitutional rules as code (docs/APP_DESIGN.md):

  rule 1  every run gets a fresh, exclusive workroot        -> lease_workroot()
  rule 2  every conf carries an explicit derived seed        -> derive_seed()
  rule 3  per-state numbers ship as >=3 seeded replicates    -> RunSpec.replicates
  ledger  every run reproducible from its row                -> Ledger

Each lesson has a date and a cost; see the design doc. None of these are
advisory -- the engines refuse to run outside a leased workroot.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

APP_STATE = Path(__file__).resolve().parents[1] / "state"


def fmt_hms(seconds) -> str:
    """Wall time as h:mm:ss -- the one formatter the console, the retro
    pages, and both report exports share, so a duration reads identically
    wherever it appears. None or a negative value renders as an em space
    dash rather than a fake zero."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "--"
    if s < 0 or s != s:                     # negative or NaN: no fake zero
        return "--"
    s = int(round(s))
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def derive_seed(location: str, forecast_date: str, replicate: int) -> int:
    """Deterministic per-(location, date, replicate) seed.

    Unseeded prior draws produced relWIS 0.894 vs 0.946 from the SAME script
    (2026-08-17); per-state spread is ~±0.05 and fat-tailed. Identical specs
    must reproduce bit-for-bit -- verified across a bngsim minor-version
    upgrade (max quantile diff 0.00e+00).
    """
    h = hashlib.sha256(f"{location}|{forecast_date}|{replicate}".encode()).digest()
    return int.from_bytes(h[:4], "little") % (2**31 - 1)


@dataclass
class RunSpec:
    """Everything that defines one model run. The ledger stores this verbatim."""
    engine: str                      # 'pf' | 'analogue' | 'amcmc' | 'einn'
    forecast_date: str               # YYYY-MM-DD, a Saturday
    locations: list = field(default_factory=list)
    season_start: str = ""
    weeks_to_drop: int = 0           # trim newest N weeks before fitting
    weeks_to_nowcast: int = 0        # framework now, method later (no-op nowcaster)
    replicates: int = 3
    particles: int = 10_000          # sit-down verdict 2026-08-17
    jitter: float = 0.30
    observable_mode: str = "integrated"
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        # Aug-Jul season: a blank season_start derives from the forecast
        # date so specs built anywhere (routes, scripts, tests) agree and
        # nothing hardcodes a season year.
        if not self.season_start and self.forecast_date:
            y, m = int(self.forecast_date[:4]), int(self.forecast_date[5:7])
            self.season_start = f"{y if m >= 8 else y - 1}-08-01"

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def _git_sha(repo: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo,
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


class Ledger:
    """Append-only sqlite record: spec, seeds, engine versions, git SHAs,
    workroot, outcome. Reproducing any submission = re-executing its row."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else APP_STATE / "ledger.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("""CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, created_utc REAL, spec_json TEXT,
            flubnf_sha TEXT, pybnf_sha TEXT, engine_versions TEXT,
            workroot TEXT, status TEXT, outcome_json TEXT)""")
        # wall time per run: created_utc alone cannot say how long a run took.
        # Added by migration so an existing ledger keeps every historical row
        # (they simply report no elapsed time, which is the truth about them).
        have = {r[1] for r in self._db.execute("PRAGMA table_info(runs)")}
        for col in ("finished_utc", "elapsed_s"):
            if col not in have:
                self._db.execute(f"ALTER TABLE runs ADD COLUMN {col} REAL")
        self._db.commit()

    def open_run(self, spec: RunSpec, workroot: Path,
                 engine_versions: dict) -> str:
        run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        root = Path(__file__).resolve().parents[2]
        # named columns, never positional: the table grows by migration
        self._db.execute(
            "INSERT INTO runs (run_id, created_utc, spec_json, flubnf_sha, "
            "pybnf_sha, engine_versions, workroot, status, outcome_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, time.time(), spec.to_json(), _git_sha(root),
             _git_sha(__import__("flubnf.settings", fromlist=["PYBNF"]).PYBNF),
             json.dumps(engine_versions), str(workroot), "running", "{}"))
        self._db.commit()
        return run_id

    def close_run(self, run_id: str, status: str, outcome: dict) -> None:
        """Record the outcome and the run's wall time. elapsed_s is derived
        in SQL from the row's own created_utc, so the number can never drift
        from the timestamp the ledger already holds."""
        now = time.time()
        self._db.execute(
            "UPDATE runs SET status=?, outcome_json=?, finished_utc=?, "
            "elapsed_s=MAX(0, ? - created_utc) WHERE run_id=?",
            (status, json.dumps(outcome), now, now, run_id))
        self._db.commit()

    def rows(self, limit: int = 50) -> list:
        cur = self._db.execute(
            "SELECT run_id, created_utc, spec_json, status, outcome_json, "
            "finished_utc, elapsed_s "
            "FROM runs ORDER BY created_utc DESC LIMIT ?", (limit,))
        return [dict(zip(("run_id", "created_utc", "spec", "status", "outcome",
                          "finished_utc", "elapsed_s"), r))
                for r in cur.fetchall()]


def lease_workroot(run_id: str, base: Optional[Path] = None) -> Path:
    """Fresh, exclusive directory for ONE run. Never reused, never shared.

    Three concurrent experiments sharing one /tmp tree cost a morning and
    tainted two results (2026-08-17). mkdir(exist_ok=False) makes a collision
    an ERROR, not a silent overlap.
    """
    root = (base or APP_STATE / "workroots") / run_id
    root.mkdir(parents=True, exist_ok=False)
    return root


def gc_workroots(keep_last: int = 10, base: Optional[Path] = None) -> int:
    """Reclaim dead workroots, newest `keep_last` kept. Returns count removed."""
    import shutil
    root = base or APP_STATE / "workroots"
    if not root.is_dir():
        return 0
    dirs = sorted((d for d in root.iterdir() if d.is_dir()),
                  key=lambda d: d.name, reverse=True)
    n = 0
    for d in dirs[keep_last:]:
        shutil.rmtree(d, ignore_errors=True)
        n += 1
    return n
