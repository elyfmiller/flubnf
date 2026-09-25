"""The slow-request log: every request the server takes SLOW_MS or longer
to answer, and every page the window took SLOW_PAGE_MS or longer to show
(reported by base.html), one line each, with the machine's load average
(a retrospective holding most cores shows up there).

    <local time>  server  <ms>  <METHOD> <path>  load <1-min load>/<cores>
    <local time>  page    <ms>  <path>  server <ms> scripts <ms>  load ...

The file is app/state/logs/slow_requests.log and rolls over to .1 at
MAX_BYTES, so it never grows past twice that. Writing never fails a
request.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from fastapi import Request

#: a request answered slower than this is logged (milliseconds)
SLOW_MS = 300.0
#: a page shown slower than this (navigation start to load end) is logged
SLOW_PAGE_MS = 800.0
#: roll the log over past this size
MAX_BYTES = 512 * 1024

_LOCK = threading.Lock()


def log_path() -> Path:
    from app.core.runs import APP_STATE
    return Path(APP_STATE) / "logs" / "slow_requests.log"


def _load() -> str:
    try:
        return f"load {os.getloadavg()[0]:.1f}/{os.cpu_count() or 0}"
    except (OSError, AttributeError):
        return "load n/a"


def write(kind: str, ms: float, what: str) -> None:
    """Append one line; roll over at MAX_BYTES. Never raises."""
    line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {kind:<6}  "
            f"{ms:7.0f} ms  {what}  {_load()}\n")
    try:
        p = log_path()
        with _LOCK:
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                if p.stat().st_size > MAX_BYTES:
                    os.replace(p, p.with_suffix(".log.1"))
            except FileNotFoundError:
                pass
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


async def slow_request_log(request: Request, call_next):
    """Middleware: time each request; log it when slower than SLOW_MS. The
    server-side milliseconds also go out as a Server-Timing header, which
    base.html reads back when a page is slow to show."""
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000.0
    try:
        response.headers["Server-Timing"] = f"app;dur={ms:.0f}"
    except Exception:
        pass
    if ms >= SLOW_MS:
        write("server", ms, f"{request.method} {request.url.path}")
    return response
