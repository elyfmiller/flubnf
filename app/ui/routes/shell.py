"""The endpoints base.html's shell uses that no tab owns.

The versions poller (GET /api/versions, home and Methods poll it while a
version is pending), the favicon, and the busy guard (GET /api/busy: what a
click would interrupt now, for the guard modal), and the slow-page report
(POST /api/perf, into app/ui/perflog.py's log). An APIRouter server.py
includes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.ui import retro_seasons, state
from app.ui.retro_seasons import _RETRO_ACTIVE, _season_status
from app.ui.shared import _sandbox_live
from app.ui.state import _status
from app.ui.versions import VERSIONS, versions_resolved

router = APIRouter()


# === Shell: the versions poller and the favicon (base.html) ===
@router.get("/api/versions")
def api_versions():
    """Versions as known now, and whether the probe landed (home and Methods
    poll this while a value is pending)."""
    return {"versions": dict(VERSIONS), "resolved": versions_resolved()}


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """PyBNF brand kit favicon (small-size mark)."""
    from fastapi.responses import FileResponse
    ico = state.UI_DIR / "static" / "brand" / "favicon.ico"
    return FileResponse(ico, media_type="image/x-icon")


# === Busy guard: what a click would interrupt (base.html) ===
@router.get("/api/busy")
def api_busy():
    """What would a click interrupt now? console_run: the running run's
    label (null when idle); retro: {season: status} for running, stopping
    or paused seasons (paused still holds the engine); phase: the console
    phase (the Update-data guard fires only on 'materializing'/'preparing',
    which read hub files). Seasons come from claims AND on-disk records, so
    a live replay never reads idle."""
    running = _status.get("running")
    live = {}
    for s in retro_seasons._known_seasons():
        st = _season_status(s)
        if st in _RETRO_ACTIVE:
            live[s] = st
    return {
        "console_run": ((_status.get("run_label") or str(running))
                        if running else None),
        "retro": live,
        "phase": _status.get("phase", "") or "",
        "sandbox": _sandbox_live() or None,
    }


# === Slow pages: the window's own timing of a slow page (base.html) ===
@router.post("/api/perf", status_code=204)
async def api_perf(request: Request):
    """A page base.html found slow to show: its path and milliseconds
    (navigation start to load end), with the server's share and the time
    spent running scripts. Logged by app/ui/perflog.py; malformed reports
    are dropped."""
    from app.ui import perflog
    try:
        d = await request.json()
        path = str(d.get("path") or "")[:200]
        total = float(d["total"])
        server = float(d.get("server") or 0.0)
        scripts = float(d.get("scripts") or 0.0)
    except Exception:
        return Response(status_code=204)
    if path.startswith("/") and perflog.SLOW_PAGE_MS <= total < 600000:
        perflog.write("page", total, f"{path}  server {server:.0f} ms "
                                     f"scripts {scripts:.0f} ms")
    return Response(status_code=204)
