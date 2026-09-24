"""PRODUCTION: which run a forecast date's files come from
(app/ui/pipeline._archive_run, the Output page, the Storage panel).

One folder per as-of date, app/state/archive/<date>/, holds the run that
is that date's forecast. Beside its files:

  archive.json    {"run_id", "complete", "archived_utc"}: which run the
                  folder holds, and whether that run finished ok with every
                  requested submission file written and no submission
                  errors (written by _archive_run; absent in folders from
                  before this record existed, which count as complete)

The rule (never a downgrade): a newer run's files replace an earlier
run's for the same date only when the newer run is complete, or when the
earlier one is not. choose() applies it to the runs that wrote a file for
a date (the Output page shows the chosen run's file per model);
keep_reason() applies it to the archive folder.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

RECORD = "archive.json"


def archive_root() -> Path:
    from app.core import runs
    return runs.APP_STATE / "archive"


def _read(p: Path):
    try:
        d = json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def read_record(d: Path) -> dict | None:
    """The folder's archive.json, None when absent or unreadable."""
    return _read(Path(d) / RECORD)


def _write_json(p: Path, data: dict) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def write_record(d: Path, run_id: str, complete: bool) -> None:
    _write_json(Path(d) / RECORD, {"run_id": str(run_id),
                                   "complete": bool(complete),
                                   "archived_utc": time.time()})


def choose(candidates):
    """The candidate a date shows: the newest complete one, else the
    newest. Each candidate is a dict with "run_id" (run ids sort by start
    time) and "complete"; None for none."""
    cands = sorted(candidates or [], key=lambda c: str(c.get("run_id") or ""))
    if not cands:
        return None
    done = [c for c in cands if c.get("complete", True)]
    return (done or cands)[-1]


def keep_reason(d: Path, complete: bool) -> str:
    """Why a new run must NOT replace the archive in `d` ("" when it may):
    the new run is incomplete and the archive holds a complete one (the
    rule of choose())."""
    d = Path(d)
    if not d.is_dir():
        return ""
    rec = read_record(d) or {}
    held = rec.get("run_id") or ""
    if not complete and rec.get("complete", True):
        return ("this run is not complete, so the archive kept the "
                "earlier complete run" + (f" {held}" if held else ""))
    return ""
