"""Data (GET /data): the vintage browser and the freshness panel, the hub
pull (POST /data/pull) and the freshness check (POST /freshness).

The vintage readers are TTL-cached per path. _data_context also builds
datasets_ui's dataset view, and the Forecast tab and the startup warm pass
read _vintage_frame here. An APIRouter server.py includes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core import ttlcache
from app.ui import state
from app.ui.shared import _flash, _invalidate_scans
from app.ui.state import _engine_lock, _status
from app.ui.templating import _script_json, _season_colors, templates

router = APIRouter()


# === Data (/data): read-only vintage views -> data.html ===
# Archived vintage CSVs (~600 KB) are immutable: long TTL, keyed by path +
# date; the hub pull calls _invalidate_scans().

VINTAGE_TTL_S = 300.0


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_frame(path: str):
    """A vintage CSV parsed once and shared, keyed by path. Callers must
    not mutate the frame."""
    import pandas as pd
    tdf = pd.read_csv(path, dtype={"location": str})
    tdf["location"] = tdf["location"].str.zfill(2)
    return tdf


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_summary(path: str, date: str) -> dict:
    return state.data_mod.vintage_summary(date)


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_locations(path: str, date: str) -> tuple:
    return tuple(state.data_mod.vintage_location_names(date))


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_series(path: str, date: str, loc: str) -> dict:
    return state.data_mod.vintage_series(date, loc)


def _newest_report():
    """Did every jurisdiction report the newest week (app/core/reported.py),
    judged with the "Newest weeks reading 0" setting the Forecast form last
    held; None without hub data."""
    from app.core import reported
    from app.ui.state import _last_form
    knobs = _last_form.get("knobs") or {}
    rule = str(knobs.get("data.trailing_zero") or "") if isinstance(
        knobs, dict) else ""
    return reported.check(rule or reported.MS.TRAILING_ZERO)


def _data_context(loc: str = "", vintage: str = "", freshness=None) -> dict:
    """Data page context: the latest vintage's freshness panel and the
    vintage browser's selection. Read-only; bad selections fall back to the
    defaults with a note, never an error page."""
    import re as _re
    vs = state.data_mod.vintages()
    # the weeks served from the shipped snapshots (data/vintages/), not the
    # hub archive: the page marks them so a reader can tell the two apart
    try:
        shipped = [w for w in state.data_mod.shipped_weeks()
                   if state.data_mod.vintage_source(w)["kind"] == "shipped"]
    except Exception:
        shipped = []
    ctx = {"active": "Data", "latest_vintage": vs[-1] if vs else "none",
           "n_vintages": len(vs), "freshness": freshness,
           "shipped": shipped, "n_shipped": len(shipped),
           "shipped_labels": {w: state.data_mod.vintage_source(w)["label"]
                              for w in shipped},
           "latest": None, "vintages": list(reversed(vs)),
           "sel_vintage": "", "sel_loc": "", "loc_names": [],
           "sel_summary": None, "series_table": [], "series_n": 0,
           "series_json": "null", "peak": None, "view_note": "",
           # season-over-season chart palette (fallback for --season-N)
           "season_colors_json": _script_json(_season_colors())}
    ctx["vintage_rows"] = _vintage_rows(vs)
    # the live target file: its newest week is what a real-time run reads
    # when the hand-kept archive has not caught up yet
    try:
        ctx["live_week"] = state.data_mod.live_newest_week()
    except Exception:
        ctx["live_week"] = None
    # the newest week's reporting, from the file a real-time run reads
    ctx["newest_report"] = _newest_report()
    # the "Your datasets" card (built here so /freshness keeps it)
    from app.ui import datasets_ui as _dsu
    ctx.update({"datasets": _dsu.dataset_rows(), "upload": None, "ds": None})
    if not vs:
        return ctx
    latest = vs[-1]
    try:
        ctx["latest"] = _vintage_summary(
            str(state.data_mod.vintage_path(latest)), latest)
    except Exception as e:
        ctx["view_note"] = ("Could not read the latest vintage "
                            f"({type(e).__name__}). The archive may still "
                            "be updating; try again shortly.")
        return ctx
    sel_v = (vintage if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", vintage or "")
             and vintage in vs else latest)
    if vintage and sel_v != vintage:
        ctx["view_note"] = (f"No archived vintage for {vintage}; showing "
                            f"the latest, {latest}.")
    try:
        pv = str(state.data_mod.vintage_path(sel_v))
        names = list(_vintage_locations(pv, sel_v))
        sel_loc = loc if loc in names else (names[0] if names else "")
        if loc and sel_loc != loc:
            note = (f"{ctx['view_note']} " if ctx["view_note"] else "")
            ctx["view_note"] = (note + "That location is not in the "
                                f"{sel_v} vintage; showing {sel_loc}.")
        ctx["sel_vintage"], ctx["sel_loc"] = sel_v, sel_loc
        ctx["loc_names"] = names
        ctx["sel_summary"] = _vintage_summary(pv, sel_v)
        series = _vintage_series(pv, sel_v, sel_loc) if sel_loc else {}
        dates = list(series.get("dates") or [])
        values = list(series.get("values") or [])
        ctx["series_n"] = len(dates)
        # recent weeks, newest first
        ctx["series_table"] = list(zip(dates, values))[-12:][::-1]
        if values:
            pk = max(range(len(values)), key=lambda i: values[i])
            ctx["peak"] = (dates[pk], values[pk])
        # the full series for the Plotly chart
        if values:
            ctx["series_json"] = _script_json(
                {"dates": [str(d)[:10] for d in dates],
                 "values": [float(v) for v in values]})
    except Exception as e:
        ctx["view_note"] = (f"Could not read the {sel_v} vintage "
                            f"({type(e).__name__}).")
    return ctx


def _vintage_rows(vs) -> list:
    """The archive as rows: one per season (August to July), each vintage
    a (week offset from August 1, date) point, newest season first."""
    from datetime import date as _d
    rows = {}
    for v in vs:
        try:
            d = _d.fromisoformat(str(v)[:10])
        except ValueError:
            continue
        y = d.year if d.month >= 8 else d.year - 1
        off = (d - _d(y, 8, 1)).days // 7
        rows.setdefault(y, []).append((off, str(v)[:10]))
    pal = _season_colors() or []          # the player's palette: a list
    out = []
    for i, y in enumerate(sorted(rows, reverse=True)):
        label = f"{y}-{str(y + 1)[2:]}"
        if isinstance(pal, dict):
            color = pal.get(label, "currentColor")
        elif pal and isinstance(pal[0], (list, tuple)):
            color = dict(pal).get(label, "currentColor")
        else:
            color = pal[i % len(pal)] if pal else "currentColor"
        out.append({"season": label, "points": sorted(rows[y]), "color": color})
    return out


@router.get("/data", response_class=HTMLResponse)
def data_page(request: Request, loc: str = "", vintage: str = "",
              source: str = ""):
    if source:
        # browse one custom dataset in the vintage browser's place
        # (a foreign Host never gets here: shared._same_host_guard)
        from app.ui import datasets_ui as _dsu
        ds = _dsu.get_dataset(source)
        if ds is not None:
            ctx = _data_context()
            ctx.update(_dsu.data_context(ds, loc, vintage))
            return templates.TemplateResponse(request, "data.html", ctx)
        _flash("That dataset is not stored; showing the FluSight hub.")
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(loc, vintage))


# === Console controls on the Data tab: /data/pull, /freshness ===
@router.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    # server-side mirror of /api/busy under _engine_lock: refuse only while a
    # run starts or reads hub files (materializing/preparing)
    with _engine_lock:
        running = _status.get("running")
        phase = (_status.get("phase") or "").lower()
        if running and (running == "starting"
                        or "materializing" in phase
                        or "preparing" in phase):
            _flash("A run is reading the hub files right now ("
                   + (_status.get("run_label") or str(running))
                   + "). Updating data would change those files mid read; "
                   "nothing was pulled. Try again once fitting starts or "
                   "the run finishes.")
            return RedirectResponse("/data", status_code=303)
    try:
        before = state.data_mod.newest_week()
    except Exception:
        before = None
    ok, msg = state.data_mod.pull_hub()
    _invalidate_scans()
    if not ok:
        _flash("Updating the hub clone FAILED: "
               + (msg[:200] or "git exited nonzero with no message")
               + ". The local archive is unchanged; check the network and "
               "the hub clone, then try again.")
        return RedirectResponse("/data", status_code=303)
    vs = state.data_mod.vintages()
    try:
        after = state.data_mod.newest_week()
    except Exception:
        after = None
    if after and after != before:
        # new data: the Forecast tab's date follows it (a stale remembered
        # date would otherwise hold the form on last week)
        from app.ui.state import _last_form
        if _last_form:
            _last_form["forecast_date"] = after
    from flubnf.settings import HUB as _H
    comp = (" · comparators: baseline "
            + ("ok" if (_H / "model-output/FluSight-baseline").is_dir() else "missing")
            + ", official ensemble "
            + ("ok" if (_H / "model-output/FluSight-ensemble").is_dir() else "missing"))
    rep = _newest_report()
    # a plain lead, never git's own transcript (fast-forward listings, file
    # counts): whether the data moved is what the user needs
    if after and before and after != before:
        lead = f"New data: through {after} (was {before})"
    elif after:
        lead = f"Already up to date: data through {after}"
    else:
        lead = "Updated"
    _flash(lead
           + (f" · {rep.line()}" if rep else "")
           + (f" · latest vintage {vs[-1]}" if vs else "") + comp)
    return RedirectResponse("/data", status_code=303)


@router.post("/freshness", response_class=HTMLResponse)
def freshness(request: Request):
    f = state.data_mod.check_freshness()
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(freshness=f))
