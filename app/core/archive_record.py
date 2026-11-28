"""PRODUCTION: which run a forecast date's files come from
(app/ui/pipeline._archive_run, the Output page, the Storage panel).

One folder per as-of date, app/state/archive/<date>/, holds the run that
is that date's forecast. Beside its files:

  archive.json    {"run_id", "complete", "full", "modified",
                  "hub_names", "archived_utc"}: which run the folder
                  holds, whether that run finished ok with every requested
                  submission file written and no submission errors,
                  whether it covered the whole hub set, whether it was
                  made with modified model settings, and whether its files
                  carry the hub names (written by _archive_run; absent in
                  folders from before this record existed, which count as
                  complete; "modified" and "hub_names" absent in records
                  from before modified runs were archived: modified_of and
                  hub_named_of read the folder)

The rule (never a downgrade): a newer run's files replace an earlier
run's for the same date only when the newer run is complete, or when the
earlier one is not. A run made in the round's own week (real-time) is the
date's forecast: a later backtest of that week (a vintage run) replaces
it only when no real-time run wrote one. choose() applies it to the runs
that wrote a file for a date (the Output page shows the chosen run's file
per model); keep_reason() applies it to the archive folder. A run's model
settings play no part: a run made with modified settings is archived by
the same rule, its files under their own -modified names, and its record
says so (modified_of). Its files' names do: an archive whose files carry
the hub names (the files that went to the hub) is never replaced by a
run whose files carry the -modified names (hub_named_of).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

RECORD = "archive.json"


def _read(p: Path):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def read_record(d: Path) -> dict | None:
    """The folder's archive.json, None when absent or unreadable."""
    return _read(Path(d) / RECORD)


def _write_json(p: Path, data: dict) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def write_record(d: Path, run_id: str, complete: bool,
                 full: bool = True, modified: bool = False,
                 hub_names: bool = True) -> None:
    _write_json(Path(d) / RECORD, {"run_id": str(run_id),
                                   "complete": bool(complete),
                                   "full": bool(full),
                                   "modified": bool(modified),
                                   "hub_names": bool(hub_names),
                                   "archived_utc": time.time()})


def files_hub_named(d: Path):
    """Whether the submission files in a run's or an archive's folder carry
    the hub names: True when any CSV sits under a hub model's name (a
    retired one included), False when every one carries the -modified name
    (knobs.MODIFIED_SUFFIX), None when the folder holds none."""
    from app.core.knobs import MODIFIED_SUFFIX
    dirs = {p.parent.name for p in Path(d).glob("submission/*/*.csv")}
    if not dirs:
        return None
    return any(not n.endswith(MODIFIED_SUFFIX) for n in dirs)


def hub_named_of(d: Path) -> bool:
    """Whether the run an archive folder holds wrote its files under the
    hub names: its record says so, and a record from before it did is read
    from the folder's own files (files_hub_named)."""
    rec = read_record(d) or {}
    if "hub_names" in rec:
        return bool(rec["hub_names"])
    return bool(files_hub_named(d))


def modified_of(d: Path) -> bool:
    """Whether the run an archive folder holds was made with modified
    model settings: its record says so, and a record from before it did
    is read from the folder, where such a run's knobs.json travels with
    its files (every modified run writes one, a shipped run never)."""
    rec = read_record(d) or {}
    if "modified" in rec:
        return bool(rec["modified"])
    return (Path(d) / "knobs.json").is_file()


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


def realtime_of(spec) -> bool:
    """Whether a recorded spec (a RunSpec dict or its JSON) is a real-time
    run, made in its round's own week; True when unreadable or when it
    records no mode, as for records from before the mode existed."""
    try:
        d = json.loads(spec) if isinstance(spec, str) else dict(spec or {})
        return (d.get("extra") or {}).get("mode") != "vintage"
    except (ValueError, TypeError, AttributeError):
        return True


def choose(candidates):
    """The candidate a date shows: among the real-time runs (all of them
    when none is), the newest complete one from a run on the whole hub
    set, then the newest complete one, then the newest. Each candidate is
    a dict with "run_id" (run ids sort by start time, to the second),
    "complete", "full" and "realtime", and may carry "order", the
    ledger's (created_utc, rowid): runs that started in the same second
    are newest by it, as app/ui/shared._scan_results orders them, never by
    the id's random suffix. None for none."""
    def newest_last(c):
        rid = str(c.get("run_id") or "")
        return rid[:15], tuple(c.get("order") or (0.0, 0)), rid
    cands = sorted(candidates or [], key=newest_last)
    if not cands:
        return None
    # a backtest of a past week never replaces the run made in that week
    cands = [c for c in cands if c.get("realtime", True)] or cands
    done = [c for c in cands if c.get("complete", True)]
    whole = [c for c in done if c.get("full", True)]
    return (whole or done or cands)[-1]


def keep_reason(d: Path, complete: bool, full: bool = True,
                realtime: bool = True, hub_names: bool = True) -> str:
    """Why a new run must NOT replace the archive in `d` ("" when it may):
    the new run is a backtest (vintage) and the archive holds a real-time
    run, or the new run is incomplete and the archive holds a complete
    one, or it covers part of the hub set and the archive holds a
    whole-set complete run (the rule of choose()), or its files carry the
    -modified names (`hub_names` False) and the archive's carry the hub
    names (hub_named_of): the files that went to the hub stay."""
    d = Path(d)
    if not d.is_dir():
        return ""
    rec = read_record(d) or {}
    held = rec.get("run_id") or ""
    held_done = rec.get("complete", True)
    if not realtime and realtime_of((_read(d / "results.json") or {})
                                    .get("spec", "")):
        return ("this run is a vintage run of a past week, so the archive "
                "kept the run made in that week"
                + (f" {held}" if held else ""))
    if not complete and held_done:
        return ("this run is not complete, so the archive kept the "
                "earlier complete run" + (f" {held}" if held else ""))
    if not full and held_done and rec.get("full", True):
        return ("this run covers part of the 53 locations, so the "
                "archive kept the earlier run on all 53"
                + (f" {held}" if held else ""))
    if not hub_names and hub_named_of(d):
        return ("this run's files carry the -modified names, so the "
                "archive kept the earlier run whose files carry the hub "
                "names" + (f" {held}" if held else ""))
    return ""
