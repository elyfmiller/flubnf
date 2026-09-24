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


def write_record(d: Path, run_id: str, complete: bool,
                 full: bool = True) -> None:
    _write_json(Path(d) / RECORD, {"run_id": str(run_id),
                                   "complete": bool(complete),
                                   "full": bool(full),
                                   "archived_utc": time.time()})


def full_scope(locations) -> bool:
    """Whether a run asked for the whole hub set: the 52 jurisdictions and
    US (national). A run on a few states is never the date's file while a
    whole-set run exists."""
    from app.core import us_national as _usn
    locs = list(locations or [])
    n = len(_usn.state_names(locs))
    return n >= 52 and len(locs) > n


def scope_of(spec) -> bool:
    """full_scope() of a recorded spec (a RunSpec dict or its JSON); True
    when unreadable, as for records from before the rule."""
    try:
        d = json.loads(spec) if isinstance(spec, str) else dict(spec or {})
        locs = d.get("locations")
    except (ValueError, TypeError):
        return True
    return True if not locs else full_scope(locs)


def choose(candidates):
    """The candidate a date shows: the newest complete one from a run on
    the whole hub set, then the newest complete one, then the newest.
    Each candidate is a dict with "run_id" (run ids sort by start time),
    "complete" and "full"; None for none."""
    cands = sorted(candidates or [], key=lambda c: str(c.get("run_id") or ""))
    if not cands:
        return None
    done = [c for c in cands if c.get("complete", True)]
    whole = [c for c in done if c.get("full", True)]
    return (whole or done or cands)[-1]


def keep_reason(d: Path, complete: bool, full: bool = True) -> str:
    """Why a new run must NOT replace the archive in `d` ("" when it may):
    the new run is incomplete and the archive holds a complete one, or the
    new run covers part of the hub set and the archive holds a whole-set
    complete run (the rule of choose())."""
    d = Path(d)
    if not d.is_dir():
        return ""
    rec = read_record(d) or {}
    held = rec.get("run_id") or ""
    held_done = rec.get("complete", True)
    if not complete and held_done:
        return ("this run is not complete, so the archive kept the "
                "earlier complete run" + (f" {held}" if held else ""))
    if not full and held_done and rec.get("full", True):
        return ("this run covers part of the 53 jurisdictions, so the "
                "archive kept the earlier run on all 53"
                + (f" {held}" if held else ""))
    return ""
