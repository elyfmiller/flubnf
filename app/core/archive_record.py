"""PRODUCTION: the forecast archive's own record (app/ui/pipeline._archive_run,
the Output page's "Mark as submitted", the Storage panel).

One folder per as-of date, app/state/archive/<date>/, holds the run that
is that date's forecast. Beside its files:

  archive.json    {"run_id", "complete", "archived_utc"}: which run the
                  folder holds, and whether that run finished ok with every
                  requested submission file written and no submission
                  errors (written by _archive_run; absent in folders from
                  before this record existed, which count as complete)
  submitted.json  {"run_id", "submitted_utc", "submitted_at"}: the operator
                  marked this archive as submitted to the hub (FluBNF only
                  writes the files; submission stays manual). Also recorded
                  on the run's ledger row (outcome "submitted").

The rules: a later run replaces the archive only when it is complete, or
when the archive holds an incomplete run (never a downgrade); a marked
archive is never replaced and cannot be deleted from Storage.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

RECORD = "archive.json"
SUBMITTED = "submitted.json"

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def archive_root() -> Path:
    from app.core import runs
    return runs.APP_STATE / "archive"


def archive_dir(date: str) -> Path | None:
    """The archive folder of an as-of date; None for a malformed date."""
    if not _DATE.match(str(date or "")):
        return None
    return archive_root() / str(date)


def _read(p: Path):
    try:
        d = json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def read_record(d: Path) -> dict | None:
    """The folder's archive.json, None when absent or unreadable."""
    return _read(Path(d) / RECORD)


def read_submitted(d: Path) -> dict | None:
    """The folder's submitted.json, None when not marked. An unreadable
    marker still counts as marked (a guard never fails open)."""
    p = Path(d) / SUBMITTED
    if not p.exists():
        return None
    return _read(p) or {"run_id": "", "submitted_at": "", "submitted_utc": 0}


def _write_json(p: Path, data: dict) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def write_record(d: Path, run_id: str, complete: bool) -> None:
    _write_json(Path(d) / RECORD, {"run_id": str(run_id),
                                   "complete": bool(complete),
                                   "archived_utc": time.time()})


def keep_reason(d: Path, complete: bool) -> str:
    """Why a new run must NOT replace the archive in `d` ("" when it may):
    the archive is marked submitted, or the new run is incomplete and the
    archive holds a complete one."""
    d = Path(d)
    if not d.is_dir():
        return ""
    rec = read_record(d) or {}
    held = rec.get("run_id") or ""
    sub = read_submitted(d)
    if sub is not None:
        return ("the archive is marked submitted"
                + (f" (run {held})" if held else "")
                + ", so no later run replaces it")
    if not complete and rec.get("complete", True):
        return ("this run is not complete, so the archive kept the "
                "earlier complete run" + (f" {held}" if held else ""))
    return ""


def _stamp(now: float) -> str:
    """Local date and time, minute precision, with the zone's name (EDT,
    MST; the long name on Windows), else the UTC offset."""
    t = time.localtime(now)
    zone = getattr(t, "tm_zone", "") or time.strftime("%z", t)
    return f"{time.strftime('%Y-%m-%d %H:%M', t)} {zone}".strip()


def mark(date: str, now: float | None = None) -> dict:
    """Mark the archive of `date` as submitted; returns the record.
    Raises ValueError when there is no archive for the date."""
    d = archive_dir(date)
    if d is None or not d.is_dir():
        raise ValueError(f"no archive for {date}")
    now = time.time() if now is None else float(now)
    rid = (read_record(d) or {}).get("run_id") or ""
    rec = {"run_id": rid, "submitted_utc": now, "submitted_at": _stamp(now)}
    _write_json(d / SUBMITTED, rec)
    if rid:
        _ledger_note(rid, {"submitted": {"date": date, **rec}})
    return rec


def unmark(date: str, now: float | None = None) -> bool:
    """Remove the mark; False when the archive was not marked."""
    d = archive_dir(date)
    if d is None or not (d / SUBMITTED).exists():
        return False
    was = read_submitted(d) or {}
    (d / SUBMITTED).unlink()
    rid = was.get("run_id") or (read_record(d) or {}).get("run_id") or ""
    if rid:
        now = time.time() if now is None else float(now)
        _ledger_note(rid, {"submitted_unmarked": {
            "date": date, "was": was.get("submitted_at", ""),
            "unmarked_at": _stamp(now)}}, drop=("submitted",))
    return True


def _ledger_note(run_id: str, patch: dict, drop=()) -> None:
    """The mark on the run's ledger row too; never fatal (the marker file
    is the guard, the ledger its history)."""
    try:
        from app.core.runs import Ledger
        Ledger().update_outcome(run_id, patch, drop=drop)
    except Exception:
        pass


def status(date: str) -> dict | None:
    """For a page: {"date", "run_id", "complete", "submitted" (record or
    None)} of the archive of `date`; None when there is none."""
    d = archive_dir(date)
    if d is None or not d.is_dir():
        return None
    rec = read_record(d) or {}
    return {"date": date, "run_id": rec.get("run_id") or "",
            "complete": bool(rec.get("complete", True)),
            "submitted": read_submitted(d)}
