"""The endpoints base.html's shell uses that no tab owns.

The versions poller (GET /api/versions, home and Methods poll it while a
version is pending), the favicon, and the busy guard (GET /api/busy: what a
click would interrupt now, for the guard modal). An APIRouter server.py
includes.
"""
from __future__ import annotations

from fastapi import APIRouter

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
