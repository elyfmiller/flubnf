"""The download log: one line for each file the console serves as a
download from a run (a submission CSV or export, a weekly report), so
which file went out, and when, can be read back on the server side:

    <local time>  <route>  run <run id>  <bytes> B  sha256 <first 12>  <path>

A copy in Downloads that does not hash to the line's sha256 was not
written by that download. The file is app/state/logs/downloads.log and
rolls over to .1 like the slow-request log (app/ui/perflog.py). Writing
never fails a request.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.ui import perflog


def log_file() -> Path:
    from app.core.runs import APP_STATE
    return Path(APP_STATE) / "logs" / "downloads.log"


def run_of(path) -> str:
    """The run a file under app state belongs to: its workroot's name, or
    the run an archive folder records (archive.json); "" otherwise."""
    from app.core import archive_record
    from app.core.runs import APP_STATE
    try:
        parts = Path(path).resolve().relative_to(
            Path(APP_STATE).resolve()).parts
    except (OSError, ValueError):
        return ""
    if len(parts) > 2 and parts[0] == "workroots":
        return parts[1]
    if len(parts) > 2 and parts[0] == "archive":
        rec = archive_record.read_record(Path(APP_STATE) / "archive"
                                         / parts[1]) or {}
        return str(rec.get("run_id") or "")
    return ""


def write(route: str, path, run_id: str = "") -> None:
    """Log one download of the file at `path` by `route`; `run_id` is
    looked up from the path when not given. Never raises."""
    try:
        p = Path(path)
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        size = p.stat().st_size
        rid = run_id or run_of(p) or "-"
        perflog.append(log_file(), (
            f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {route}  run {rid}  "
            f"{size} B  sha256 {h.hexdigest()[:12]}  {p}\n"))
    except Exception:
        pass
