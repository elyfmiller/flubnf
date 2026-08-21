"""FastAPI operations console -- landing, freshness, settings, run, tabs.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710
"""
from __future__ import annotations

import time
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from fastapi import BackgroundTasks, FastAPI, Form, Request     # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse    # noqa: E402
from fastapi.templating import Jinja2Templates                  # noqa: E402

from app.core import data as data_mod                           # noqa: E402
from app.core import ttlcache                                   # noqa: E402
from app.core.runs import (Ledger, RunSpec, fmt_hms,            # noqa: E402
                           lease_workroot, settings_html,
                           spec_settings, version_pairs)

app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["pop_flash"] = lambda: _status.pop("flash", None)
# one wall-time format everywhere the console shows a duration
templates.env.filters["hms"] = fmt_hms

def _repo_sha(short: bool = True) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--short" if short else "HEAD",
                            "HEAD"], capture_output=True, text=True, timeout=5,
                           cwd=str(Path(__file__).resolve().parents[2]))
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


RUNNING_SHA = _repo_sha()   # the code THIS process actually executes


def _restart_needed() -> bool:
    """True when the repo on disk is ahead of the running process: a pull
    landed but Python in memory is still the old build. The page reload
    shows fresh templates and static files while server logic stays stale,
    which cost days of confused field debugging; the banner ends that."""
    sha = _repo_sha()
    return bool(sha and RUNNING_SHA and sha != RUNNING_SHA)


templates.env.globals["running_sha"] = lambda: RUNNING_SHA
templates.env.globals["restart_needed"] = _restart_needed
# one renderer for the settings blocks, shared by the progress cards, the run
# page, and both report exports: a reader comparing an artifact against the
# console never has to reconcile two wordings (see app/core/runs.py)
templates.env.globals["settings_html"] = settings_html

ENGINES = ("all", "pf", "amcmc")     # "all" = pf + analogue + ensemble
_status: dict = {"running": None, "log": []}
_last_form: dict = {}


def _component_versions() -> dict:
    """Installed versions of the components named in user-facing copy,
    resolved once per process at import. Console packages come from this
    interpreter (importlib.metadata); pybnf and bngsim from the engine venv's
    interpreter; BioNetGen from the VERSION file beside BNG2.pl. Anything
    unresolvable reports 'not installed' instead of raising."""
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("fastapi", "jinja2", "plotly", "pandas", "numpy"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    out["bionetgen"] = "not installed"
    try:
        from flubnf.settings import load_locations, BNG
        vf = Path(BNG).parent / "VERSION"
        if vf.is_file():
            out["bionetgen"] = vf.read_text().strip()
        elif Path(BNG).exists():
            out["bionetgen"] = "installed"
    except Exception:
        pass
    out["pybnf"] = out["bngsim"] = "not installed"
    try:
        import json
        import subprocess
        from flubnf.settings import PY_ENGINE
        if Path(PY_ENGINE).exists():
            code = ("import json\n"
                    "from importlib.metadata import version\n"
                    "d = {}\n"
                    "for p in ('pybnf', 'bngsim'):\n"
                    "    try: d[p] = version(p)\n"
                    "    except Exception: d[p] = 'not installed'\n"
                    "print(json.dumps(d))")
            r = subprocess.run([str(PY_ENGINE), "-c", code],
                               capture_output=True, text=True, timeout=15)
            out.update(json.loads(r.stdout.strip() or "{}"))
    except Exception:
        pass
    return out


VERSIONS = _component_versions()


def _default_forecast_date() -> str:
    """Latest Saturday, clamped to the latest ARCHIVED vintage -- during the
    off-season the hub stops publishing, and a default that points at a
    nonexistent vintage greets the user with an error (laptop field test,
    2026-08-18)."""
    import datetime as dt
    d = dt.date.today()
    sat = str(d - dt.timedelta(days=(d.weekday() - 5) % 7))
    vs = data_mod.vintages()
    return min(sat, vs[-1]) if vs else sat


# --------------------------------------------------------------------------
# cached filesystem scans
#
# The console asks the same directory questions many times per render (how
# many weeks a season has, which workroots hold results, what is archived),
# and every answer stats a file per week. Measured idle, /retro spent 68 ms
# of its 71 ms there, and under the load of a real fitting run that cost
# multiplies. Each scan below is therefore cached for a couple of seconds
# (app/core/ttlcache.py), which is invisible against pollers that run every
# two to three seconds, and every action that changes the underlying state
# calls _invalidate_scans() so the interface is never stale after a click.
# --------------------------------------------------------------------------

@ttlcache.ttl_cache()
def _weeks_done(root: Path) -> int:
    """Completed weeks in a season tree: the count of stored samples.json.

    THE hot scan of the retrospective pages. Every caller goes through here
    so one page render pays for it once."""
    root = Path(root)
    try:
        return len(list((root / "weeks").glob("*/samples.json")))
    except OSError:
        return 0


@ttlcache.ttl_cache()
def _scan_results(workroots: Path) -> list:
    """results.json paths under a workroots directory, newest run first."""
    try:
        return sorted(Path(workroots).glob("*/results.json"), reverse=True)
    except OSError:
        return []


def _workroot_results() -> list:
    """Workroot results.json paths, newest run first. The scan is cached;
    the files themselves are read fresh by the caller, so a run that
    rewrites its results is never served a stale forecast.

    KEYED BY PATH, never by nothing: the state root is switchable (tests
    redirect it, and a cached answer from one root must never be served for
    another). Every cache below follows the same rule."""
    from app.core.runs import APP_STATE
    return _scan_results(APP_STATE / "workroots")


def _invalidate_scans() -> None:
    """Drop every cached scan. Called by the actions that change what the
    scans describe, so a count on the page after a click is always the count
    on disk."""
    ttlcache.clear_all()


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """PyBNF brand kit favicon (the small-size mark, loop omitted per the
    kit's minimum-size rule)."""
    from fastapi.responses import FileResponse
    ico = Path(__file__).parent / "static" / "brand" / "favicon.ico"
    return FileResponse(ico, media_type="image/x-icon")


def _outlook_cards(res: dict | None) -> dict:
    """fips -> hover card for svg_map, colored by the latest run's categorical
    outlook (ensemble if present, else pf). States without results -- and the
    no-results-at-all case -- get empty cards, so the caller always renders the
    full silhouette."""
    import pandas as pd
    from app.core.report import categorical_probs
    from app.core.report_v2 import CATS
    _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
    n2a = dict(zip(_l.location_name, _l.abbreviation))
    n2p = dict(zip(_l.location_name, _l.population.astype(float)))
    models = (res or {}).get("models", {})
    picked = models.get("ensemble") or models.get("pf") or {}
    observed = (res or {}).get("observed", {})
    cards = {}
    for loc, qd in picked.items():
        fips = n2f.get(loc, "")
        q1 = (qd or {}).get("1")
        obs = observed.get(loc) or []
        # tolerate the pre-quantile results schema (medians-only floats)
        if len(fips) != 2 or not isinstance(q1, dict) or not obs:
            continue
        lo = float(obs[-1][1])
        vals = [float(v) for v in q1.values()]
        probs = categorical_probs(vals, lo, int(n2p[loc]), 1)
        med1 = float(q1.get("0.5", vals[len(vals) // 2]))
        hover = (f"<b>{loc}</b><br>current: {lo:.0f}"
                 f"<br>1-wk median: {med1:.0f}<br>" +
                 "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                             for c in CATS))
        cards[fips] = {"probs": probs, "name": loc, "abbr": n2a.get(loc, ""),
                       "fips": fips, "hover_html": hover}
    for name, fips in n2f.items():
        if len(fips) == 2:
            cards.setdefault(fips, {"name": name, "abbr": n2a.get(name, ""),
                                    "fips": fips})
    return cards


def _diagram_data(res: dict | None) -> dict:
    """Annotation feed for the home page's interactive SIHRS diagram: per
    location, the latest run's fitted-parameter posterior medians (harvested
    into results.json at run time), the last observed admissions point, and
    the 1-week median from the same model the outlook cards use. Empty when
    no run exists; the diagram then renders unannotated with a hint."""
    out = {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    if not res:
        return out
    try:
        out["date"] = res.get("forecast_date", "") or ""
        params = res.get("params") or {}
        pf_p = params.get("pf") or {}
        p2_p = params.get("pf2s") or {}
        models = res.get("models") or {}
        out["has_pf2s"] = bool(p2_p) or bool(models.get("pf2s"))
        observed = res.get("observed") or {}
        picked = models.get("ensemble") or models.get("pf") or {}
        for loc in set(pf_p) | set(p2_p) | set(observed) | set(picked):
            e = {}
            if isinstance(pf_p.get(loc), dict) and pf_p[loc]:
                e["pf"] = pf_p[loc]
            if isinstance(p2_p.get(loc), dict) and p2_p[loc]:
                e["pf2s"] = p2_p[loc]
            obs = observed.get(loc) or []
            if obs:
                e["obs"] = obs[-1]
            q1 = (picked.get(loc) or {}).get("1")
            if isinstance(q1, dict) and q1.get("0.5") is not None:
                e["med1"] = float(q1["0.5"])
            if e:
                out["locations"][str(loc)] = e
        out["order"] = sorted(
            out["locations"],
            key=lambda l: (l.upper() not in ("US", "US (NATIONAL)"), l))
    except Exception:
        return {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    return out


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        _, res = _latest_results()
    except Exception:
        res = None
    # a real map as the hero graphic: latest run's outlook if one exists,
    # otherwise the empty-country silhouette
    map_svg, outlook_date, outlook_n = "", "", 0
    try:
        from app.core.usmap import map_legend, svg_map
        cards = {}
        try:
            cards = _outlook_cards(res)
            if any(c.get("probs") for c in cards.values()):
                outlook_date = (res or {}).get("forecast_date", "")
        except Exception:
            pass                      # no LOCATIONS/hub -> bare silhouette
        with_data = {c["abbr"] for c in cards.values() if c.get("probs")}
        # the national fit has no state shape on the map: the caption counts
        # only jurisdictions a reader can actually see colored
        outlook_n = len(with_data - {"US"})
        # legend under the map, from the same module that colors it: the
        # five categories plus the no-data tone are readable without hovering
        map_svg = ("<div style='max-width:880px;margin:0 auto'>"
                   "<script>window.MAP_LINK='/output/report';</script>"
                   + svg_map(cards, clickable=with_data)
                   + map_legend() + "</div>")
    except Exception:
        pass
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home", "map_svg": map_svg, "outlook_date": outlook_date,
        "outlook_n": outlook_n,
        "versions": VERSIONS, "diagram": _diagram_data(res),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


@app.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS model, the fitting machinery, the
    ensemble, and the data and verification policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS})


@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request):
    import pandas as pd
    from flubnf.settings import load_locations
    # an empty state list must be visible, never silent: with no checklist the
    # form's every run quietly launches all 52 jurisdictions
    locations_error = ""
    try:
        _l = load_locations()
        all_locs = list(_l.location_name[(_l.location.str.len() == 2)
                                         & (_l.abbreviation != "US")])
    except Exception as e:
        all_locs = []
        locations_error = (f"State list unavailable ({type(e).__name__}); "
                           "runs will cover all 52 jurisdictions.")
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "engine": "all",
                                "weeks_to_drop": 0, "weeks_to_nowcast": 0,
                                "replicates": 3, "members": 2}
    rid, res = _latest_results()
    # data panel: full series for the CURRENTLY SELECTED locations, straight
    # from the latest vintage -- visible before any run (deciding what to
    # drop requires seeing the data)
    import json as _json
    # the data panel's own dropdown defaults to US national -- seed it so the
    # panel paints without a fetch; form locations stay seeded for the fans
    sel = ["US (national)"] + [l for l in form["locations"] if l != "all"]
    series = {}
    try:
        vs = data_mod.vintages()
        tdf = pd.read_csv(data_mod.vintage_path(vs[-1]), dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        for loc in sel[:8]:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            series[loc] = {"dates": [str(d)[:10] for d in g.date],
                           "values": [float(v) for v in g.value]}
    except Exception:
        pass
    fanq = {}
    if res and _status.get("session_ran"):
        for mname, md in res["models"].items():
            good = {loc: qs for loc, qs in md.items()
                    if all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[mname] = good
    ledger_rows = Ledger().rows(5)
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs,
        "locations_error": locations_error, "form": form,
        "elapsed0": _console_elapsed(),
        "series_json": _json.dumps(series), "fanq_json": _json.dumps(fanq),
        "run_obs_json": _json.dumps((res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", "")})


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request):
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "data.html", {
        "active": "Data", "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs), "freshness": None})


@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    rows = Ledger().rows(50)
    for r in rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        # a 'running' row with no live worker = the app was closed mid-run
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Runs", "ledger": rows})


@app.post("/run/stop")
def run_stop():
    _invalidate_scans()        # the run's state is about to change
    w = _status.get("workroot")
    running = _status.get("running") or ""
    if w and running.startswith("amcmc"):
        # the adaptive-MCMC engine runs as one subprocess and ignores STOP
        # files -- say so instead of letting the button silently no-op
        _status["phase"] = ("Adaptive MCMC cannot be stopped mid-run. "
                            "It finishes on its own and records its result.")
    elif w and running:
        (Path(w) / "STOP").touch()
        if (Path(w) / "pf2s").is_dir():        # the two-strain pass polls its
            (Path(w) / "pf2s" / "STOP").touch()  # own subdir for the flag
        _status["phase"] = "stopping…"
    elif running == "starting" and not w:
        # a claim with no worker behind it (engine setup never happened) --
        # release it so one stray click doesn't wedge the console
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _status["phase"] = ""
    return RedirectResponse("/forecast#results", status_code=303)


@app.get("/api/busy")
def api_busy():
    """Per-button guard support: what would a click interrupt right now?
    console_run is the running console run's label (null when idle), retro
    maps season to status for seasons currently running, stopping, or paused,
    and phase is the console run's current phase string. The Update-data guard
    fires only while the phase contains 'materializing' or 'preparing':
    those phases read hub files that a pull mutates, whereas a pull during
    pure fitting is safe.

    A PAUSED season counts as a conflict: the worker still holds the engine
    and its workroots, so starting a run over it must warn.

    Seasons are taken from the in-memory claims AND from every run record on
    disk, so a live replay is reported even when the claim is missing. That
    matters for the archive and discard controls, whose whole safety rests on
    this answer: a season must never read as idle while a worker is writing
    into its tree."""
    running = _status.get("running")
    live = {}
    for s in _known_seasons():
        st = _season_status(s)
        if st in _RETRO_ACTIVE:
            live[s] = st
    return {
        "console_run": ((_status.get("run_label") or str(running))
                        if running else None),
        "retro": live,
        "phase": _status.get("phase", "") or "",
    }


@app.post("/data/pull")
def data_pull():
    """Explicit hub update -- looking never pulls; pulling is a button."""
    msg = data_mod.pull_hub()
    vs = data_mod.vintages()
    from flubnf.settings import HUB as _H
    comp = (" · comparators: baseline "
            + ("ok" if (_H / "model-output/FluSight-baseline").is_dir() else "missing")
            + ", official ensemble "
            + ("ok" if (_H / "model-output/FluSight-ensemble").is_dir() else "missing"))
    _flash(f"{msg[:140]}" + (f" · latest vintage {vs[-1]}" if vs else "") + comp)
    return RedirectResponse("/data", status_code=303)


@app.post("/freshness", response_class=HTMLResponse)
def freshness(request: Request):
    f = data_mod.check_freshness()
    vs = data_mod.vintages()
    return templates.TemplateResponse(request, "data.html", {
        "active": "Data", "latest_vintage": vs[-1] if vs else "none",
        "n_vintages": len(vs), "freshness": f})


def _phase(msg):
    _status["phase"] = msg


def _flash(msg: str) -> None:
    """Human-voiced notice for the next page the user sees; the log keeps
    the permanent record."""
    _status["flash"] = msg
    _status["log"].append(msg)


def _back(request: Request, fallback: str) -> RedirectResponse:
    """Redirect to the page the form was posted from (validated local path),
    so a button never yanks the user off the page they were on."""
    from urllib.parse import urlsplit
    path = urlsplit(request.headers.get("referer", "")).path
    ok = path.startswith("/") and not path.startswith("//")
    return RedirectResponse(path if ok else fallback, status_code=303)


def _harvest_params(workroot: Path) -> dict:
    """Per-location posterior medians of the fitted PF parameters, pooled
    across replicates (every params_<rep>.txt under each cell's
    out/Results/A_MCMC/Runs). Feeds the interactive model diagram.
    Non-fatal by design: an unreadable cell is skipped, and a location with
    no readable params files is simply absent from the result."""
    import json as _json
    import numpy as _np
    try:
        cells = _json.loads((workroot / "cells.json").read_text())
    except Exception:
        return {}
    pooled: dict = {}
    for c in cells:
        try:
            loc = c["location"]
            runs = Path(c["dir"]) / "out" / "Results" / "A_MCMC" / "Runs"
            for pfile in sorted(runs.glob("params_*.txt")):
                with open(pfile) as fh:
                    names = fh.readline().replace("#", " ").split()
                arr = _np.atleast_2d(_np.loadtxt(str(pfile), skiprows=1))
                if arr.size == 0 or arr.shape[1] != len(names):
                    continue
                for j, name in enumerate(names):
                    col = arr[:, j]
                    col = col[_np.isfinite(col)]
                    if col.size:
                        pooled.setdefault(loc, {}).setdefault(
                            name.removesuffix("__FREE"), []).append(col)
        except Exception:
            continue
    return {loc: {name: float(_np.median(_np.concatenate(chunks)))
                  for name, chunks in by_name.items()}
            for loc, by_name in pooled.items()}


# SetThreadExecutionState flags (Windows). ES_CONTINUOUS makes the
# requirement persist until explicitly cleared; ES_SYSTEM_REQUIRED blocks
# idle system sleep (the caffeinate -i equivalent). Clearing is
# ES_CONTINUOUS alone.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class _WinSleepGuard:
    """Windows sleep inhibitor mirroring the only part of the Popen
    interface the callers use: .terminate(). The execution-state flag is
    thread-affine, and both call sites create and terminate the guard on
    the same worker thread (the finally of the function that created it),
    which is exactly what the ES_CONTINUOUS contract requires."""

    def __init__(self, kernel32):
        self._kernel32 = kernel32

    def terminate(self):
        try:
            self._kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        except Exception:
            pass


def _windows_sleep_guard(kernel32=None):
    """SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) on the
    calling (worker) thread; returns a guard with .terminate() or None on
    any failure. `kernel32` is injectable for tests on other platforms."""
    try:
        if kernel32 is None:
            import ctypes
            kernel32 = ctypes.windll.kernel32
        prev = kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        if not prev:                    # 0 means the call failed
            return None
        return _WinSleepGuard(kernel32)
    except Exception:
        return None


def _sleep_guard():
    """Hold the machine awake while a long background run works. macOS:
    spawn `caffeinate -i -w <this pid>`, which blocks idle sleep until this
    process exits. Windows: SetThreadExecutionState (see
    _windows_sleep_guard). Returns an object with .terminate() for the
    caller to end the guard when the work ends, or None on any other
    platform or on any failure -- no run may ever depend on the guard
    (overnight laptop retrospectives die to closed-lid or idle sleep
    otherwise)."""
    import os
    import subprocess
    if sys.platform == "darwin":
        try:
            return subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except Exception:
            return None
    if sys.platform == "win32":
        return _windows_sleep_guard()
    return None


def _run_all(spec: RunSpec) -> None:
    """The competition path: engines in ascending cost, then ensemble,
    submissions, and the weekly report. Every step lands in ONE workroot and
    ONE ledger row."""
    import pandas as pd
    from app.core import ensemble as ens
    from app.core import scoring
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.submit import (quantile_rows, rows_from_quantiles,
                                 write_submission)

    import time as _time
    ledger = Ledger()
    run_id = None
    outcome = {}
    guard = _sleep_guard()          # macOS: no idle sleep mid-run
    # the route claims the clock when the user clicks; a direct call (scripts,
    # tests) starts it here instead, so elapsed is never missing
    if not _status.get("started_utc"):
        _status["started_utc"] = _time.time()
    t_start = float(_status["started_utc"])
    n_states = sum(1 for l in spec.locations
                   if str(l).upper() not in ("US", "US (NATIONAL)"))
    _status["run_label"] = (
        f"{spec.forecast_date} · {n_states} state(s) + US"
        if n_states < len(spec.locations)
        else f"{spec.forecast_date} · {len(spec.locations)} location(s)")
    # the settings that produced this run, shown on the progress card and
    # recorded in its artifacts. Set here as well as in the route so a direct
    # call (scripts, tests) is described too.
    _status["settings"] = spec_settings(spec)
    try:
        # setup INSIDE the try: a failed ledger insert or workroot lease must
        # release the running claim in the finally, not wedge it until restart
        run_id = ledger.open_run(spec, Path("pending"), {"engines": "pf,analogue"})
        workroot = lease_workroot(run_id)
        ledger.set_workroot(run_id, workroot)   # the row must name the real one
        _status["running"] = f"all:{run_id}"
        _status["workroot"] = str(workroot)
        # 1. PF (primary) -- gracefully absent on Tier-A machines (no engine
        # venv): the run proceeds with the analogue and says so, rather than
        # erroring on the first click of a fresh install.
        from flubnf.settings import PY_ENGINE, PYBNF
        fails = {}
        # observed admissions per location (vintage-true) -- used by the
        # output floor, the report's state pages, and the run page
        obs = {}
        try:
            from flubnf.settings import LOCATIONS as _LOCCSV
            from app.core.data import vintage_path as _vpo
            _lo = pd.read_csv(_LOCCSV, dtype=str)
            _n2fo = dict(zip(_lo.location_name, _lo.location.str.zfill(2)))
            tdf = pd.read_csv(_vpo(spec.forecast_date),
                              dtype={"location": str})
            tdf["location"] = tdf["location"].str.zfill(2)
            import numpy as _npo
            for loc in spec.locations:
                g = tdf[tdf.location == _n2fo.get(loc, "")].sort_values("date").tail(15)
                obs[loc] = [[str(r.date)[:10], float(r.value)]
                            for r in g.itertuples()
                            if _npo.isfinite(r.value)]
        except Exception:
            pass
        pf_samples = {}
        params: dict = {}     # fitted-parameter medians per member/location
        if spec.engine in ("all", "pf") and PY_ENGINE.exists() and PYBNF.exists():
            _phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            _phase(f"filtering {len(spec.locations)} location(s) × "
                   f"{spec.replicates} replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            pf_samples = pf_engine.collect(workroot)
            try:
                params["pf"] = _harvest_params(workroot)
            except Exception:
                pass          # the diagram goes without; the forecast stands
            # output floor: no cell leaves as a point mass (see app/core/floor.py)
            from app.core.floor import floor_samples
            pf_samples = {loc: floor_samples(
                              s, loc, spec.forecast_date,
                              recent=[v for _, v in obs.get(loc, [])])
                          for loc, s in pf_samples.items()}
        else:
            outcome["pf_skipped"] = ("analogue-only run"
                                     if spec.engine == "analogue"
                                     else "engine venv not installed (Tier A)")
            (workroot / "cells.json").write_text("[]")
        # 1b. research third member: the two-strain SIHRS. It failed the
        # full-grid ensemble gate and has no UI control; members=3 is still
        # accepted here so the variant can be run and scored for research.
        # Same engine, spec.extra variant switch, sibling subdir of the SAME
        # workroot so the run stays one ledger row and one archive entry.
        pf2s_samples = {}
        if ((spec.extra or {}).get("members") == 3
                and spec.engine in ("all", "pf")
                and PY_ENGINE.exists() and PYBNF.exists()):
            from dataclasses import replace as _dc_replace
            spec2s = _dc_replace(spec, extra={**(spec.extra or {}),
                                              "variant": "2strain"})
            w2 = workroot / "pf2s"
            w2.mkdir()
            _phase("materializing the two-strain member (BNG network generation)")
            pf_engine.prepare(spec2s, w2)
            _phase(f"fitting the two-strain member: {len(spec.locations)} "
                   f"location(s) × {spec.replicates} replicate(s)")
            status2s = pf_engine.execute(w2)
            fails2s = {k: v for k, v in status2s.items() if v != "ok"}
            outcome["pf2s_cells"] = len(status2s)
            outcome["pf2s_failures"] = fails2s
            fails.update({f"pf2s:{k}": v for k, v in fails2s.items()})
            pf2s_samples = pf_engine.collect(w2)
            try:
                params["pf2s"] = _harvest_params(w2)
            except Exception:
                pass
            from app.core.floor import floor_samples as _floor2s
            pf2s_samples = {loc: _floor2s(
                                s, loc, spec.forecast_date,
                                recent=[v for _, v in obs.get(loc, [])])
                            for loc, s in pf2s_samples.items()}
        _phase("consulting the calendar analogue")
        from app.core.floor import floor_quantiles
        an_q = {loc: floor_quantiles(q) for loc, q in an_engine.run(spec).items()}
        # 3. ensemble (vincentize: equal weights, never fitted)
        import pandas as _pd
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f_pre = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        members_by_loc = {}
        for loc in spec.locations:
            m = {}
            if loc in pf_samples:
                m["pf"] = ens.member_quantiles_from_samples(pf_samples[loc])
            if loc in an_q:
                m["analogue"] = an_q[loc]
            if loc in pf2s_samples:
                m["pf2s"] = ens.member_quantiles_from_samples(pf2s_samples[loc])
            if m:
                # equal, never-fitted weights at every member count: 50/50
                # for the two-member blend, equal thirds with the two-strain
                # member (the sealed recipe; fitting the weights scored
                # worse, pooled relWIS 0.717 against 0.704)
                members_by_loc[loc] = ens.vincentize(
                    m, weights=ens.equal_weights(m),
                    location_fips=n2f_pre.get(loc, ''))
        _phase("vincentizing the ensemble and writing submissions")
        # 4. submissions (identity in the path)
        locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
        subs = {}
        for model_id, rows in (
            ("PF-SIHRS", [r for loc, s in pf_samples.items()
                          for r in quantile_rows(s, n2f[loc], spec.forecast_date)]),
            ("Ensemble", [r for loc, q in members_by_loc.items()
                          for r in rows_from_quantiles(q, n2f[loc],
                                                       spec.forecast_date)]),
        ):
            if rows:
                subs[model_id] = str(write_submission(
                    rows, model_id, "NAU", spec.forecast_date,
                    workroot / "submission"))
        outcome["submissions"] = subs
        # 5. retrospective scoring (populates once truth exists). Contained:
        # a scoring hiccup must never erase the forecast itself -- results.json
        # and the archive land after this point (same pattern as step 5b).
        df = pd.DataFrame()
        try:
            truth, name2fips = scoring.load_truth()
            df = scoring.score_samples(pf_samples, spec.forecast_date,
                                       name2fips, truth)
            if not df.empty:
                outcome["pf_relwis"] = round(float(df.wis.sum() / df.base_wis.sum()), 3)
            df.to_json(workroot / "scores_pf.json")
        except Exception as e:
            outcome["score_error"] = str(e)[:200]
        # 5b. weekly report: map + hover cards + WIS card (fans arrive with
        # the per-state drill-down pages; keep the report honest meanwhile)
        try:
            from app.core.report import categorical_probs
            from app.core.report_v2 import CATS, build_report
            from app.core.scoring import summary_table_html
            n2a = dict(zip(locs.location_name, locs.abbreviation))
            n2p = dict(zip(locs.location_name,
                           locs.population.astype(float)))
            cards = {}
            for loc, s in pf_samples.items():
                import numpy as _np
                med1 = float(_np.median(_np.asarray(s["1"], float)))
                lo = next(c["last_observed"] for c in
                          __import__("json").loads(
                              (workroot / "cells.json").read_text())
                          if c["location"] == loc)
                probs = categorical_probs(s["1"], lo, int(n2p[loc]), 1)
                hover = (f"<b>{loc}</b><br>current: {lo:.0f}"
                         f"<br>1-wk median: {med1:.0f}<br>" +
                         "<br>".join(f"{c.replace('_',' ')}: "
                                     f"{probs.get(c,0):.0%}" for c in CATS))
                cards[n2a[loc]] = {"probs": probs, "name": loc,
                                   "abbr": n2a[loc], "fips": n2f[loc],
                                   "hover_html": hover}
            for name, abbr in n2a.items():
                cards.setdefault(abbr, {"name": name, "abbr": abbr,
                                        "fips": n2f.get(name, "")})
            wis_html = ("<div class='card'><h2>forecast accuracy "
                        "(retrospective)</h2>" + summary_table_html(df)
                        + "</div>")
            # state pages: fan + categorical bar + recent-data table per location
            from app.core.report_v2 import cat_bar, fan_figure
            # settled outcomes for backdated runs: the LATEST vintage's values
            # past the forecast origin, framed to the 4-week horizon
            settled_by_loc = {}
            try:
                _vs_all = data_mod.vintages()
                if _vs_all and _vs_all[-1] > spec.forecast_date:
                    from datetime import date as _sd, timedelta as _st
                    _lim = (_sd.fromisoformat(spec.forecast_date)
                            + _st(days=35)).isoformat()
                    ldf = pd.read_csv(data_mod.vintage_path(_vs_all[-1]),
                                      dtype={"location": str})
                    ldf["location"] = ldf["location"].str.zfill(2)
                    for loc in spec.locations:
                        g = ldf[(ldf.location == n2f.get(loc, "")) &
                                (ldf.date > spec.forecast_date) &
                                (ldf.date <= _lim)].sort_values("date")
                        pts = [(str(r.date)[:10], float(r.value))
                               for r in g.itertuples()
                               if pd.notna(r.value)]
                        if pts:
                            settled_by_loc[loc] = pts
            except Exception:
                settled_by_loc = {}
            details = {}
            for loc, s in pf_samples.items():
                fips_l = n2f.get(loc, "")
                obs_pairs = (obs.get(loc) or [])[-12:]
                from datetime import date as _dd, timedelta as _tdd
                o_t = [d for d, _ in obs_pairs]
                o_v = [v for _, v in obs_pairs]
                _base = (_dd.fromisoformat(o_t[-1]) if o_t
                         else _dd.fromisoformat(spec.forecast_date))
                f_t = [(_base + _tdd(days=7 * h)).isoformat()
                       for h in (1, 2, 3, 4)]
                samples_h = {f_t[h - 1]: s[str(h)] for h in (1, 2, 3, 4)}
                try:
                    fan = fan_figure(o_t, o_v, f_t, samples_h,
                                     title=f"{loc}: weekly admissions",
                                     settled=settled_by_loc.get(loc))
                    lo_l = o_v[-1] if o_v else 0.0
                    import numpy as _np3
                    probs_l = categorical_probs(
                        _np3.asarray(s["1"], float), lo_l,
                        int(n2p.get(loc, 1e6)), 1)
                    key = "US" if fips_l == "US" else n2a.get(loc, loc)
                    meds = [float(_np3.median(_np3.asarray(s[str(h)], float)))
                            for h in (1, 2, 3, 4)]
                    note = ("Off-season: the model finds no sustained "
                            "transmission. This forecast reflects the recent "
                            "reporting background, not epidemic growth."
                            if max(meds) <= 2 else "")
                    details[key] = {
                        "name": "United States" if fips_l == "US" else loc,
                        "note": note,
                        "fan": fan, "cat": cat_bar(probs_l),
                        "table_rows": [(d, v) for d, v in obs_pairs[-6:]]}
                except Exception:
                    continue
            nat_html = ""
            try:
                from app.core.usmap import national_svg
                us_names = [n for n in pf_samples if n2f.get(n) == "US"] or                            [n for n in pf_samples if "US" in n or "national" in n.lower()]
                if us_names:
                    un = us_names[0]
                    import numpy as _np2
                    arr = _np2.asarray(pf_samples[un]["1"], float)
                    lo_us = next((c["last_observed"] for c in
                                  __import__("json").loads(
                                      (workroot / "cells.json").read_text())
                                  if c["location"] == un), 0.0)
                    us_pop = float(_l0 := 340_000_000)
                    probs_us = categorical_probs(arr, lo_us, int(us_pop), 1)
                    hover_us = ("<b>United States</b><br>current: "
                                f"{lo_us:.0f}<br>1-wk median: "
                                f"{float(_np2.median(arr)):.0f}")
                    nat_html = national_svg({"probs": probs_us,
                                             "name": "United States",
                                             "abbr": "US", "fips": "US",
                                             "hover_html": hover_us})
            except Exception:
                nat_html = ""
            us_d = details.get("US", {})
            build_report(spec.forecast_date, cards, details,
                         {"fan": us_d.get("fan"), "acc": None,
                          "note": us_d.get("note", ""),
                          "summary_html": wis_html},
                         workroot / "report.html",
                         national_map_html=nat_html,
                         elapsed_s=_time.time() - t_start,
                         # what produced this report: the run's own settings,
                         # the application build, and the engine versions
                         settings_html=settings_html(
                             spec_settings(spec)
                             + version_pairs(RUNNING_SHA, VERSIONS)))
            outcome["report"] = str(workroot / "report.html")
        except Exception as e:
            outcome["report_error"] = str(e)[:200]
        # 6. results index for the run page
        import json as _json
        import numpy as _np
        def _qs_from_samples(s):
            out = {}
            for h in ("1", "2", "3", "4"):
                a = _np.asarray(s.get(h, []), float); a = a[_np.isfinite(a)]
                if a.size:
                    out[h] = {q: float(_np.quantile(a, float(q)))
                              for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
            return out
        def _qs_from_q(qd):
            return {h: {q: qd[h][float(q)]
                        for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                    for h in qd}
        import os as _os
        _tmp = workroot / "results.json.tmp"
        _tmp.write_text(_json.dumps({
            "spec": spec.to_json(), "forecast_date": spec.forecast_date,
            "observed": obs,
            "params": params,
            "models": {
                "pf": {loc: _qs_from_samples(s) for loc, s in pf_samples.items()},
                "analogue": {loc: _qs_from_q(q) for loc, q in an_q.items()},
                **({"pf2s": {loc: _qs_from_samples(s)
                             for loc, s in pf2s_samples.items()}}
                   if pf2s_samples else {}),
                "ensemble": {loc: _qs_from_q(q) for loc, q in members_by_loc.items()},
            }}))
        _os.replace(_tmp, workroot / "results.json")   # readers never see a half-write
        # 7. forecast archive: one folder per forecast_date, latest run wins
        try:
            outcome["archived"] = _archive_run(workroot, spec.forecast_date)
        except Exception as e:
            outcome["archive_error"] = str(e)[:200]
        _status["session_ran"] = run_id
        ledger.close_run(run_id, "failed" if fails else "ok", outcome)
        _status["log"].append(
            f"{run_id}: pf {len(pf_samples)} loc, analogue {len(an_q)}, "
            + (f"pf2s {len(pf2s_samples)}, " if pf2s_samples else "")
            + f"ensemble {len(members_by_loc)}"
            + (f", relWIS {outcome['pf_relwis']}" if "pf_relwis" in outcome else ""))
    except Exception as e:
        from app.core.engines.pf import RunStopped
        if run_id is None:
            _status["log"].append(f"run setup failed: {str(e)[:200]}")
        elif isinstance(e, RunStopped):
            ledger.close_run(run_id, "stopped", outcome)
            _status["log"].append("run stopped by user")
        else:
            ledger.close_run(run_id, "error", {"error": str(e)[:300], **outcome})
            _status["log"].append(f"{run_id}: ERROR {e}")
    finally:
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass
        # the run wrote results.json and may have archived a forecast date:
        # every cached scan that describes those is now out of date
        _invalidate_scans()
        _status["running"] = None
        _status["phase"] = ""
        _status["settings"] = []
        _status["workroot"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None


def _archive_run(workroot: Path, forecast_date: str) -> str:
    """Copy the run's deliverables to app/state/archive/<forecast_date>/,
    replacing any earlier archive for the same date."""
    import shutil
    from app.core.runs import APP_STATE
    arch = APP_STATE / "archive" / forecast_date
    if arch.exists():
        shutil.rmtree(arch)
    arch.mkdir(parents=True)
    for name in ("results.json", "report.html"):
        if (workroot / name).is_file():
            shutil.copy2(workroot / name, arch / name)
    if (workroot / "submission").is_dir():
        shutil.copytree(workroot / "submission", arch / "submission")
    return str(arch)


@ttlcache.ttl_cache()
def _scan_archive_dates(root: Path) -> list:
    import re
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name))


def _archive_dates() -> list:
    """Forecast archive listing, cached by the directory it describes: the
    Output page and its date picker both ask, and a run archiving a new date
    invalidates it."""
    from app.core.runs import APP_STATE
    return _scan_archive_dates(APP_STATE / "archive")


@app.get("/api/archive/dates")
def api_archive_dates():
    return _archive_dates()


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = [{"model": p.parent.name, "file": p.name, "abs": str(p)}
            for p in sorted(w.glob("submission/*/*.csv"))]
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    status, err, spec_json = "", "", ""
    for r in Ledger().rows(200):
        if r.get("run_id") == run_id:
            status = r.get("status", "")
            spec_json = r.get("spec", "") or ""
            try:
                err = _json.loads(r.get("outcome") or "{}").get("error", "")
            except Exception:
                err = ""
            break
    # The settings come from the LEDGER ROW's spec, which is the record of
    # record for a run; nothing is duplicated to show them here. The build
    # and engine versions are this process's, stated so the page says what
    # produced the run rather than implying it.
    return templates.TemplateResponse(request, "run.html", {
        "active": "Runs", "run_id": run_id, "status": status, "error": err,
        "label": _run_label(run_id, spec_json), "models": res.get("models", {}),
        "settings": spec_settings(spec_json),
        "versions": version_pairs(RUNNING_SHA, VERSIONS),
        "subs": subs, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    f = APP_STATE / "workroots" / run_id / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>no report for this run</p>")


@app.get("/api/series")
def api_series(locs: str = ""):
    """Data-panel series for arbitrary locations -- lets the checkboxes drive
    the plots live instead of waiting for a Run click."""
    import json as _json
    import pandas as pd
    sel = [l for l in locs.split("|") if l][:8] or ["Ohio"]
    out = {}
    try:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f_ = dict(zip(_l.location_name, _l.location.str.zfill(2)))
        n2f_["US (national)"] = "US"
        vs = data_mod.vintages()
        tdf = pd.read_csv(data_mod.vintage_path(vs[-1]), dtype={"location": str})
        tdf["location"] = tdf["location"].str.zfill(2)
        for loc in sel:
            g = tdf[tdf.location == n2f_.get(loc, "")].sort_values("date")
            g = g[pd.to_numeric(g.value, errors="coerce").notna()]
            out[loc] = {"dates": [str(d)[:10] for d in g.date],
                        "values": [float(v) for v in g.value]}
    except Exception:
        pass
    return out


def _console_elapsed(now: float | None = None) -> float | None:
    """Seconds since the running console run claimed its slot, or None when
    nothing is running. The clock starts at the CLAIM, not at the first fit:
    engine setup is part of the wait the user is sitting through."""
    import time as _time
    t0 = _status.get("started_utc")
    if not t0 or not _status.get("running"):
        return None
    return max(0.0, (now if now is not None else _time.time()) - float(t0))


@app.get("/api/progress")
def api_progress():
    import glob
    import json as _json
    import time as _time
    w = _status.get("workroot")
    out = {"running": bool(_status.get("running")),
           "phase": _status.get("phase", ""),
           "label": _status.get("run_label", ""),
           # the browser ticks the seconds itself; these two anchor it, so a
           # page reloaded an hour into a run shows the true elapsed time
           "started_utc": _status.get("started_utc"),
           "elapsed_s": _console_elapsed(),
           # the settings that produced this run, as (label, value) pairs:
           # the card renders them server-side, and a client that arrived
           # mid-run can fill them in from here
           "settings": list(_status.get("settings") or [])}
    if w:
        done = total = 0
        t0 = None
        for f in (glob.glob(w + "/status_*.json.prog")
                  + glob.glob(w + "/pf_status.json.prog")
                  + glob.glob(w + "/pf2s/pf_status.json.prog")):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        # stable denominator claimed at run start (locations x replicates);
        # discovered shard totals only ever grow toward it
        total = max(total, int(_status.get("expected_total") or 0))
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
    elif _status.get("expected_total"):
        # run claimed but workroot not created yet: report 0/N, not silence
        out["done"], out["total"] = 0, int(_status["expected_total"])
    return out


def _run_label(run_id: str, spec_json: str = "") -> str:
    """Humans read dates, not hashes: '2026-07-04 · Aug 18 09:31'."""
    import json as _json
    when = f"{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}"
    try:
        s = _json.loads(spec_json)
        return f"{s.get('forecast_date','run')} · {when}"
    except Exception:
        return when


def relwis_chip(value, cells=None, member: str = "PF") -> str:
    """The one relWIS rendering outside a scores table: the member it
    describes, tabular numerals, the ok/bad below-1-beats-baseline classes
    every other surface teaches, and the cell coverage the score rests on,
    e.g. 'PF relWIS <span class="relwis bad">4.067</span> (2 cells)'.
    Returns markup built from fixed phrases and numbers only."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    cov = ""
    if cells:
        n = int(cells)
        cov = f" ({n} cell{'s' if n != 1 else ''})"
    return (f'{member} relWIS <span class="relwis '
            f'{"ok" if v < 1 else "bad"}">{v:.3f}</span>{cov}')


def _outcome_chips(outcome_json: str) -> str:
    """One run's outcome as short chips. Returns MARKUP (rendered with
    |safe): every fragment is a fixed phrase or a number, never free text,
    so nothing user- or exception-supplied can reach the page from here.
    The raw error string is deliberately NOT printed; it stays on the run
    page, and the chip says where to find it in plain language."""
    import json as _json
    try:
        o = _json.loads(outcome_json) if isinstance(outcome_json, str) else outcome_json
    except Exception:
        return ""
    bits = []
    if "pf_cells" in o:
        n = o["pf_cells"]
        bits.append(f"PF {n} fit{'s' if n != 1 else ''}")
    if o.get("pf_failures"):
        nf = len(o["pf_failures"])
        bits.append(f'<span class="bad">{nf} failure'
                    f'{"s" if nf != 1 else ""}</span>')
    if o.get("pf_skipped"): bits.append("PF skipped (no engine)")
    if o.get("submissions"): bits.append(f"{len(o['submissions'])} submissions")
    if o.get("report"): bits.append("report ✓")
    if o.get("pf_relwis"):
        bits.append(relwis_chip(o["pf_relwis"], cells=o.get("pf_cells")))
    if o.get("error"):
        bits.append('<span class="bad">failed</span>; the full error is on '
                    'the run page')
    return " · ".join(bits)


def _latest_results():
    import json as _json
    # newest first; a half-written or corrupt results.json falls back to the
    # next run instead of turning five routes into a 500. The workroot SCAN
    # is cached (five routes ask for it); the file is read fresh every time,
    # so a re-blended ensemble is never served from a stale parse.
    for f in _workroot_results():
        try:
            return f.parent.name, _json.loads(f.read_text())
        except (_json.JSONDecodeError, OSError):
            continue
    return None, None


def _fan_svg(observed, qs):
    """Tiny inline SVG: observed tail + forecast fan (10-90, 25-75, median)."""
    # tolerate the pre-quantile results schema (medians-only floats)
    if not qs or not all(isinstance(v, dict) and "0.9" in v for v in qs.values()):
        return ""
    obs_v = [v for _, v in observed][-10:] if observed else []
    hs = sorted(qs, key=int)
    hi = max([qs[h]["0.9"] for h in hs] + obs_v + [1.0])
    W, H, n_obs = 320, 90, len(obs_v)
    n = n_obs + len(hs)
    def x(i): return 10 + i * (W - 20) / max(n - 1, 1)
    def y(v): return H - 10 - (v / hi) * (H - 22)
    def pts(seq): return " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in seq)
    band = lambda lo_k, hi_k, op: (
        f'<polygon fill="var(--gold-bright)" fill-opacity="{op}" points="'
        + pts([(n_obs - 1 + k + 1, qs[h][hi_k]) for k, h in enumerate(hs)])
        + " " + pts(reversed([(n_obs - 1 + k + 1, qs[h][lo_k])
                              for k, h in enumerate(hs)])) + '"/>')
    parts = [f'<svg viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px">']
    if obs_v:
        parts.append(f'<polyline fill="none" stroke="var(--ink)" stroke-width="1.6" '
                     f'points="{pts(list(enumerate(obs_v)))}"/>')
    parts += [band("0.1", "0.9", 0.18), band("0.25", "0.75", 0.35)]
    parts.append('<polyline fill="none" stroke="var(--gold)" stroke-width="2" points="'
                 + pts([(n_obs - 1 + k + 1, qs[h]["0.5"]) for k, h in enumerate(hs)]) + '"/>')
    parts.append('</svg>')
    return "".join(parts)


PREVIEW_ROWS = 12


@app.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    import pandas as pd
    from app.core.runs import APP_STATE
    rid, res = _latest_results()
    files = []
    if rid:
        w = APP_STATE / "workroots" / rid
        for f in sorted(w.glob("submission/*/*.csv")):
            entry = {"model": f.parent.name, "name": f.name, "path": str(f),
                     "cols": [], "rows": [], "more": 0}
            try:
                df = pd.read_csv(f, dtype=str)
                entry["cols"] = list(df.columns)
                entry["rows"] = df.head(PREVIEW_ROWS).fillna("").values.tolist()
                entry["more"] = max(len(df) - PREVIEW_ROWS, 0)
            except Exception:
                pass
            files.append(entry)
    return templates.TemplateResponse(request, "output.html", {
        "active": "Output", "rid": rid,
        "label": _run_label(rid) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "has_ensemble": bool((res or {}).get("models", {}).get("ensemble")),
        "files": files,
        "archive_dates": list(reversed(_archive_dates())),
        "has_report": bool(rid and (APP_STATE / "workroots" / rid / "report.html").is_file())})


@app.get("/output/download")
def output_download(path: str):
    """Hand the submission CSV to the browser as a real download."""
    from fastapi.responses import FileResponse
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    if p.is_relative_to(APP_STATE.resolve()) and p.is_file():   # stay inside our state
        return FileResponse(p, filename=p.name, media_type="text/csv",
                            content_disposition_type="attachment")
    return HTMLResponse("<p>file not found in app state</p>", status_code=404)


@app.post("/output/reveal")
def output_reveal(path: str = Form(...)):
    """Local desktop app: show the file in the platform's file manager
    (Finder / Explorer) rather than fake a download."""
    import subprocess
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    if str(APP_STATE.resolve()) in str(p) and p.exists():   # stay inside our state
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        elif sys.platform == "win32":
            # /select, takes the rest of the argument as the path; one
            # combined argv element avoids Explorer's comma quoting rules
            subprocess.Popen(["explorer", f"/select,{p}"])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    return RedirectResponse("/output", status_code=303)


@app.get("/output/report", response_class=HTMLResponse)
def output_report(date: str = ""):
    """Latest run's report by default; ?date=YYYY-MM-DD serves the archive."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        f = APP_STATE / "archive" / date / "report.html"
        return HTMLResponse(f.read_text() if f.is_file()
                            else f"<p>No archived report for {date}.</p>")
    rid, _ = _latest_results()
    f = APP_STATE / "workroots" / (rid or "") / "report.html"
    return HTMLResponse(f.read_text() if f.is_file()
                        else "<p>No report yet. Run the models first.</p>")


@app.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    """The canonical Models tab: one page for the model reference views,
    defaulting to the PF view. The in-page switcher (model.html) selects
    the others; the /model/<name> routes stay live underneath it, because
    exported reports and bookmarks link them directly."""
    return model_page(request, "pf")


@app.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    blurbs = {
        "pf": ("PF-SIHRS",
               "The mechanistic member. It assumes influenza moves people "
               "through Susceptible, Infected, Hospitalized, and Recovered "
               "compartments, with seasonally varying transmission and "
               "immunity that wanes back to susceptibility. The model is "
               "written in BNGL and fitted by PyBNF's sequential particle "
               "filter on the bngsim engine: each week, 10,000 candidate "
               "epidemics per state are reweighted by how well they explain "
               "the newest hospital admissions, and their spread is the "
               "forecast uncertainty. It fits weekly NHSN admissions exactly "
               "as archived on each forecast date. Measured three-season "
               "retrospective relWIS against the FluSight baseline "
               "(values below 1 beat it): 1.023 in 2023-24, 0.636 in "
               "2024-25, 0.825 in 2025-26."),
        "analogue": ("Calendar analogue",
                     "The empirical member. It assumes the current season "
                     "will resemble past seasons at the same point in the "
                     "calendar: for each forecast it pools, across all "
                     "states, the weeks from strictly earlier seasons that "
                     "fall within two calendar weeks of the forecast date, "
                     "measures the growth from each of those weeks to the "
                     "target horizon, and scales the latest observed value "
                     "by the quantiles of those growth ratios. No "
                     "epidemiological mechanism is involved. It uses the "
                     "archive of weekly NHSN admissions and nothing else. "
                     "It is difficult to beat at one week ahead and anchors "
                     "the ensemble when a season behaves unusually. "
                     "Measured three-season retrospective relWIS: 1.105 in "
                     "2023-24, 0.835 in 2024-25, 0.641 in 2025-26."),
        "pf2s": ("Two-strain SIHRS",
                 "A research variant, not a shipped ensemble member. It "
                 "models influenza A and influenza B as independent SIHRS "
                 "circuits, each with its own seasonally varying "
                 "transmission, and reports admissions as the sum of the "
                 "two. Fitting uses two data channels, both vintage-true: "
                 "weekly NHSN hospital admissions, and NREVSS typed "
                 "positives entering the likelihood as binomial counts of "
                 "influenza A among typed specimens. The initial A/B mix at "
                 "the season start comes from the same typed surveillance "
                 "series. It cleared the turning-point gate twice, on the "
                 "state panel and again on the full grid, scoring relWIS "
                 "0.953 on turn cells against 0.993 for the single-strain "
                 "filter, and 0.968 against 1.023 on the plateau season. It "
                 "failed the gate that decides membership: on identical "
                 "full-grid cells the equal-weight three-member ensemble "
                 "scored 0.719 against 0.704 for the two-member blend, so "
                 "the submitted ensemble stays at two members and this "
                 "engine is kept for research runs only."),
        "ensemble": ("Ensemble",
                     "The submitted forecast. It averages the members' "
                     "forecast quantiles with equal, unfitted weights: "
                     "50/50 across the particle filter and the analogue, "
                     "equal thirds when the two-strain member joins. "
                     "Fitting the weights on held-out seasons was evaluated "
                     "and scored worse than the equal blend (pooled relWIS "
                     "0.717 against 0.704), so no weight is tuned. The "
                     "members' errors disagree in useful ways: the blend "
                     "beats the baseline in all three replayed seasons, "
                     "which neither member does alone. Measured "
                     "three-season retrospective relWIS: 0.848 in 2023-24, "
                     "0.651 in 2024-25, 0.691 in 2025-26; pooled 0.704."),
    }
    # one-line summaries: the collapsed <details> summary on each model tab
    onelines = {
        "pf": ("The mechanistic member: an SIHRS compartmental model fitted "
               "weekly by a sequential particle filter."),
        "analogue": ("The empirical member: it scales the latest observation "
                     "by historical growth ratios from matching calendar "
                     "weeks."),
        "pf2s": ("A research variant, not shipped: influenza A and B as "
                 "parallel SIHRS circuits fitted to two data channels."),
        "ensemble": ("The submitted forecast: an equal-weight quantile "
                     "average of the member forecasts."),
    }
    # where each model tab points into the Methods page
    manchor = {"pf": "fitting", "analogue": "analogue",
               "pf2s": "two-strain", "ensemble": "ensemble"}
    if name not in blurbs:
        return HTMLResponse("unknown model", status_code=404)
    rid, res = _latest_results()
    fans = {}
    if res and name in res.get("models", {}):
        for loc, qs in res["models"][name].items():
            fans[loc] = _fan_svg(res.get("observed", {}).get(loc, []), qs)
    fanq = {}
    if res and name in res.get("models", {}):
        fanq = {loc: qs for loc, qs in res["models"][name].items()
                if all(isinstance(v, dict) for v in qs.values())}
    # ensemble page: member medians for the raw-member overlay on the fan
    overlay = {}
    if name == "ensemble" and res:
        for m, md in (res.get("models") or {}).items():
            if m == "ensemble":
                continue
            for loc, qs in md.items():
                if all(isinstance(v, dict) for v in qs.values()):
                    meds = {h: v.get("0.5") for h, v in qs.items()
                            if isinstance(v, dict) and v.get("0.5") is not None}
                    if meds:
                        overlay.setdefault(m, {})[loc] = meds
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "replicates": 3}
    return templates.TemplateResponse(request, "model.html", {
        "active": "Models", "name": name,
        "title": blurbs[name][0], "blurb": blurbs[name][1],
        "oneline": onelines[name], "manchor": manchor[name],
        "rid": rid, "label": _run_label(rid) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "fanq_json": __import__("json").dumps(fanq),
        "overlay_json": __import__("json").dumps(overlay),
        "run_obs_json": __import__("json").dumps((res or {}).get("observed", {})),
        "form": form, "status": _status})


@app.post("/model/ensemble/generate")
def generate_ensemble(request: Request):
    """(Re)blend from the latest run's stored member outputs -- no engine rerun."""
    import json as _json
    import os as _os
    from app.core import ensemble as ens
    from app.core.runs import APP_STATE
    from app.core.submit import rows_from_quantiles, write_submission
    rid, res = _latest_results()
    if not res:
        _flash("Nothing to blend yet. Run the models first.")
        return _back(request, "/model/ensemble")
    import pandas as pd
    locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    blended, sub_rows = {}, []
    for loc in (set(res["models"].get("pf", {}))
                | set(res["models"].get("analogue", {}))
                | set(res["models"].get("pf2s", {}))):
        members = {}
        for m in ("pf", "analogue", "pf2s"):
            qd = res["models"].get(m, {}).get(loc)
            if qd:
                members[m] = {h: {float(q): v for q, v in qs.items()}
                              for h, qs in qd.items()}
        if members:
            # equal, never-fitted weights, matching the live run's blend
            b = ens.vincentize(members,
                               weights=ens.equal_weights(members),
                               location_fips=n2f.get(loc, ""))
            blended[loc] = {h: {q: b[h][float(q)]
                                for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                            for h in b}
            if n2f.get(loc):
                sub_rows += rows_from_quantiles(b, n2f[loc], res["forecast_date"])
    res["models"]["ensemble"] = blended
    _invalidate_scans()               # results.json is about to change
    rp = APP_STATE / "workroots" / rid / "results.json"
    _tmp = rp.parent / "results.json.tmp"
    _tmp.write_text(_json.dumps(res))
    _os.replace(_tmp, rp)             # readers never see a half-write
    note = f"Ensemble re-blended for {len(blended)} location(s)"
    # the Output checklist points at this CSV -- write it, and be honest that
    # a re-blend from stored results carries the 5 display quantiles, not the
    # hub's full 23 (only a full run has the member samples for all 23)
    if sub_rows:
        try:
            write_submission(sub_rows, "Ensemble", "NAU", res["forecast_date"],
                             APP_STATE / "workroots" / rid / "submission")
            note += (" · submission CSV written from the 5 stored "
                     "quantiles; a full run writes all 23 hub quantiles")
        except Exception as e:
            note += f" · submission CSV skipped: {str(e)[:120]}"
    _flash(note)
    return _back(request, "/model/ensemble")


RETRO_ROOT = Path(__file__).resolve().parents[1] / "state" / "retro"
RETRO_SEAL = Path(__file__).resolve().parents[1] / "state" / "retro_seal"


def _season_root(season: str, archive: str = "") -> tuple:
    """(root, is_seal): a season may live under the app's retro root or the
    full-grid seal root; show whichever has more completed weeks so flagship
    validation runs are never invisible in the app.

    With an archive identifier the answer is exactly one directory -- the
    archived run's own tree -- so every page, the playback API, and the
    report builder read the same frozen files."""
    if archive:
        from app.core import retro
        return retro.archive_dir(RETRO_ROOT, season, archive), False
    app_root, seal_root = RETRO_ROOT / season, RETRO_SEAL / season
    if _weeks_done(seal_root) > _weeks_done(app_root):
        return seal_root, True
    return app_root, False
_retro_status: dict = {}
_retro_stop: set = set()
_retro_claim_at: dict = {}   # season -> when its in-memory claim was made
_retro_claim_at: dict = {}   # season -> when its in-memory claim was made

#: statuses that mean a season worker is alive and holding the engine
_RETRO_ACTIVE = ("running", "stopping", "paused")


class _RetroStopRequested(Exception):
    """Raised inside the season worker between weeks when a stop was asked."""


def _valid_season(season: str) -> bool:
    """Season names name directories. Anything that is not YYYY-YY is refused
    before it can reach the filesystem."""
    import re
    return bool(re.fullmatch(r"\d{4}-\d{2}", season or ""))


def _valid_archive(stamp: str) -> bool:
    """Archive identifiers name directories too. Anything that is not the
    stamp format is refused before it can reach the filesystem."""
    from app.core import retro
    return retro.valid_stamp(stamp or "")


def _live_root(season: str) -> Path:
    """Where THIS app's season worker runs, and therefore where the control
    flags and the run record live.

    This is also the ONLY tree a Run can resume, archive, or discard. A
    sealed full-grid run under RETRO_SEAL may be what the results page shows,
    but a replay never writes there, so it is never at risk from any of the
    start-over choices."""
    return RETRO_ROOT / season


@ttlcache.ttl_cache()
def _seasons_on_disk(retro_root: Path) -> tuple:
    """Seasons under a retro root carrying a run record. Cached by that
    root: the busy guard asks on every poll and on every guarded click, and
    an answer for one root must never be served for another."""
    from app.core import retro
    names = set()
    try:
        for p in Path(retro_root).iterdir():
            if (_valid_season(p.name) and p.is_dir()
                    and retro.meta_path(p).is_file()):
                names.add(p.name)
    except OSError:
        pass                          # no retro root yet: the claims are all
    return tuple(sorted(names))


def _known_seasons() -> list:
    """Seasons this process might have to speak for: the in-memory claims
    plus every season under the live retro root carrying a run record. A
    record on disk outlives the claim (an app restart drops the claim but not
    the file), and a season with a worker must never read as idle.

    The claims are read live, never cached: a claim is made in the request
    that starts a replay, and the very next busy check must see it."""
    return sorted(set(_retro_status) | set(_seasons_on_disk(RETRO_ROOT)))


@ttlcache.ttl_cache()
def _scan_archive_entries(retro_root: Path, season: str) -> list:
    from app.core import retro
    out = []
    for p in retro.list_archive_dirs(retro_root, season):
        stamp = retro.archive_stamp_of(p.name, season)
        s = retro.run_summary(p)
        size = retro.dir_size(p)
        out.append({"id": stamp, "when": retro.stamp_human(stamp),
                    "weeks": s["weeks"], "elapsed_s": s["elapsed_s"],
                    "rel": s["headline_rel"], "scored": s["scored"],
                    "size": size, "size_h": retro.human_bytes(size)})
    return out


def _archive_entries(season: str) -> list:
    """Archived runs of one season, newest first, in the shape the retro
    index lists them: when they ran, how much they contain, and what they
    scored.

    Cached, because this walks every archived tree to size it, which is the
    most expensive scan the retro index makes. The cache key is the RETRO
    ROOT as well as the season: a season name alone would let an answer
    computed against one tree be served for another, and archiving and
    deleting both invalidate it anyway."""
    return _scan_archive_entries(RETRO_ROOT, season)


def _archive_progress(root: Path, season: str) -> dict:
    """The timing block for an archived run, shaped like _retro_progress so
    the season template needs no second code path. Never active: an archived
    tree has no worker and can never gain one."""
    from app.core import retro
    meta = retro.read_meta(root)
    t = retro.timing(meta) if meta else {}
    done = _weeks_done(root)
    return {"season": season, "status": "archived", "done": done,
            # an archived tree carries its own record, so the settings shown
            # are the ones that produced THESE weeks, not the live season's
            "settings": retro.settings_summary(meta),
            "total": int(t.get("total_weeks") or done),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": t.get("mean_s"), "eta_s": None,
            "slowest_week": t.get("slowest_week"),
            "slowest_s": t.get("slowest_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "active": False}


def _season_meta(season: str) -> dict:
    """The season's run record: the live retro root first, then whichever
    root the season page shows (a sealed full-grid run keeps its own)."""
    from app.core import retro
    m = retro.read_meta(_live_root(season))
    if m:
        return m
    root, _is_seal = _season_root(season)
    return retro.read_meta(root)


def _season_status(season: str) -> str:
    """One truthful status per season: running, paused, stopping, stopped,
    done, interrupted, error: …, or "" for a season never replayed here.

    Truthfulness across an app restart is the whole point. A worker lives
    inside this process, so if the process died its season must stop
    claiming to run: the record's heartbeat decides, not the claim."""
    from app.core import retro
    mem = _retro_status.get(season, "")
    meta = _season_meta(season)
    disk = retro.effective_status(meta) if meta else ""
    if mem not in _RETRO_ACTIVE:
        _retro_claim_at.pop(season, None)   # stamp never outlives its claim
    if mem in _RETRO_ACTIVE:
        if disk == "interrupted":
            # the worker died without releasing the in-memory claim
            _retro_status[season] = "interrupted"
            return "interrupted"
        claimed_at = _retro_claim_at.get(season)
        finished = float((meta or {}).get("finished_utc") or 0)
        if (disk and (disk in ("stopped", "done") or disk.startswith("error"))
                and claimed_at and finished >= claimed_at):
            # The worker THIS claim refers to has finished (its record was
            # closed after the claim was made), so the claim is dead. Without
            # this, a "stopping" claim outlived its worker and made every
            # later Run refuse with "already replaying", wedging the season
            # until the app restarted (field-found 2026-08-21). The
            # finished-after-claimed test keeps the startup window safe: a
            # fresh claim over an older record still reads as live.
            _retro_status[season] = disk
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return disk
        if not meta and claimed_at and time.time() - claimed_at > 120:
            # claimed but no record after two minutes: the worker never got
            # going, so the claim must not outlive it either
            _retro_status[season] = ""
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return ""
        if mem == "stopping":
            return "stopping"
        # the record refines running into paused as the worker holds
        return disk if disk in ("running", "paused") else mem
    return mem or disk


def _retro_progress(season: str) -> dict:
    """Live progress and timing for one season, in the shape the retro pages
    poll. ETA comes from the MEASURED mean seconds per week times the weeks
    still to run -- far steadier than a fit-level estimate, and honest about
    how many weeks it rests on."""
    from app.core import retro
    status = _season_status(season)
    meta = _season_meta(season)
    t = retro.timing(meta) if meta else {}
    root, _is_seal = _season_root(season)
    done = _weeks_done(root)
    total = t.get("total_weeks") or len(retro.season_vintages(season))
    mean_s = t.get("mean_s")
    eta_s = None
    if status == "running" and mean_s and total and done < total:
        eta_s = mean_s * (total - done)
    return {"season": season, "status": status, "done": done,
            "total": int(total or 0),
            # what this replay was started with, from its run record
            "settings": retro.settings_summary(meta),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": mean_s, "eta_s": eta_s,
            "slowest_week": t.get("slowest_week"),
            "slowest_s": t.get("slowest_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "active": status in _RETRO_ACTIVE}


def _retro_state_names() -> list:
    """State list for the retro config form. Falls back to the packaged
    locations table when the hub is not cloned yet (fresh machine, CI), so
    the page renders instead of erroring before setup."""
    import pandas as pd
    from flubnf.settings import LOCATIONS
    from pathlib import Path as _P
    packaged = _P(__file__).resolve().parents[2] / "flubnf/data/locations.csv"
    for src in (LOCATIONS, packaged):
        try:
            locs = pd.read_csv(src, dtype=str)
            return list(locs.location_name[(locs.location.str.len() == 2)
                                           & (locs.abbreviation != "US")])
        except Exception:
            continue
    return []


@app.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request):
    from app.core.retro import available_seasons, season_vintages
    seasons = []
    for s in available_seasons():
        total = len(season_vintages(s))
        root, is_seal = _season_root(s)
        done = _weeks_done(root)
        prog = _retro_progress(s)
        status = prog["status"]
        seasons.append({"name": s, "total": total, "done": done,
                        "seal": is_seal,
                        "settings": prog["settings"],
                        "archives": _archive_entries(s),
                        "status": status,
                        "running": status in ("running", "stopping"),
                        "paused": status == "paused",
                        "active": status in _RETRO_ACTIVE,
                        "elapsed_s": prog["elapsed_s"],
                        "mean_s": prog["mean_s"],
                        "weeks_measured": prog["weeks_measured"],
                        "eta_s": prog["eta_s"],
                        "finished_utc": prog["finished_utc"],
                        "scored": (root / "scores.json").exists()})
    from flubnf.settings import PY_ENGINE, PYBNF
    return templates.TemplateResponse(request, "retro.html",
                                      {"active": "Retrospective", "seasons": seasons,
                                       "state_names": _retro_state_names(),
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


@app.get("/api/retro/progress")
def api_retro_progress(season: str = ""):
    """Live retro progress for the pages' tickers: one season when named,
    otherwise every season with a run record or an in-memory claim. The
    pages poll this instead of reloading, so a bar can tick without wiping a
    pending guard modal."""
    from app.core.retro import available_seasons
    if season:
        if not _valid_season(season):
            return {}
        return {season: _retro_progress(season)}
    out = {}
    for s in available_seasons():
        p = _retro_progress(s)
        if p["status"] or p["done"]:
            out[s] = p
    return out


@app.get("/api/retro/startover")
def api_retro_startover(season: str = ""):
    """What pressing Run on this season would actually do.

    The answer rests on the LIVE root only: that is the only tree a replay
    writes into, so it is the only one a Run would resume and the only one
    the start-over choices touch. A sealed full-grid run may be what the
    results page shows, and it is never at stake here.

    weeks == 0 means Run starts immediately with no prompt: no friction on
    the common path. The one exception is a season whose page shows a
    SEALED validation run while the live tree is empty: the card reads
    complete, so a silent instant start would violate the stated contract.
    `sealed` is then true and `weeks` counts the sealed run's weeks, so the
    client prompts with copy naming the situation; the choices collapse to
    cancel or a fresh replay, because resume, archive, and discard have no
    live tree to act on and the seal is never touched."""
    from app.core import retro
    from app.core.retro import season_vintages
    if not _valid_season(season):
        return {"season": season, "weeks": 0, "total": 0, "complete": False,
                "elapsed_s": None, "elapsed_hms": "", "finished": "",
                "status": "", "active": False, "archives": 0,
                "sealed": False}
    root = _live_root(season)
    s = retro.run_summary(root)
    total = len(season_vintages(season))
    status = _season_status(season)
    sealed = False
    if not s["weeks"]:
        shown_root, is_seal = _season_root(season)
        if is_seal and _weeks_done(shown_root):
            sealed = True
            s = retro.run_summary(shown_root)
    return {"season": season,
            "sealed": sealed,
            "weeks": s["weeks"],
            "total": total,
            "complete": bool(total and s["weeks"] >= total),
            "elapsed_s": s["elapsed_s"],
            # sub-second records render as 0:00:00, and a fabricated zero is
            # worse than saying nothing (pre-timing seasons carry none)
            "elapsed_hms": (fmt_hms(s["elapsed_s"])
                            if s["elapsed_s"] and s["elapsed_s"] >= 1.0
                            else ""),
            "finished": retro.utc_human(s["finished_utc"]
                                        or s["started_utc"]),
            "status": status,
            "active": status in _RETRO_ACTIVE,
            "archives": len(_archive_entries(season))}


@app.post("/retro/{season}/archive/{stamp}/delete")
def retro_archive_delete(request: Request, season: str, stamp: str,
                         confirm: str = Form("")):
    """Delete one archived run, permanently.

    Three gates, all server-side, because a mis-click here costs a season of
    compute: the season and stamp must be well formed, the season must not be
    replaying (a worker writing into the live tree must not have archives
    deleted out from under a listing it may be reading), and the confirmation
    field must name the season. The LIVE season is never touched."""
    from app.core import retro
    _invalidate_scans()        # an archive listing is about to change
    if not _valid_season(season) or not _valid_archive(stamp):
        _flash("Unrecognized season or archive identifier. Nothing was "
               "deleted.")
        return _back(request, "/retro")
    if _season_status(season) in _RETRO_ACTIVE:
        _flash(f"{season} is replaying. Stop it first; nothing was deleted.")
        return _back(request, "/retro")
    if confirm != season:
        _flash("The deletion was not confirmed, so nothing was deleted.")
        return _back(request, "/retro")
    p = retro.archive_dir(RETRO_ROOT, season, stamp)
    if not (p.is_dir() or p.is_symlink()):
        _flash(f"No archived {season} run from {retro.stamp_human(stamp)}. "
               "Nothing was deleted.")
        return _back(request, "/retro")
    weeks = retro.run_summary(p)["weeks"]
    size_h = retro.human_bytes(retro.dir_size(p))
    try:
        retro.delete_tree(p)
    except Exception as e:
        _flash(f"Could not delete the archived {season} run: "
               f"{type(e).__name__}: {str(e)[:160]}. Nothing else changed.")
        return _back(request, "/retro")
    _flash(f"Deleted the archived {season} run from "
           f"{retro.stamp_human(stamp)}: {weeks} completed week"
           f"{'' if weeks == 1 else 's'}, {size_h} freed. The live "
           f"{season} season was not touched.")
    return _back(request, "/retro")


def _retro_bg(season: str, locations: list, width: int,
              replicates: int = 3, particles: int = 10_000,
              settings: dict | None = None):
    """The season worker. `settings` is what the user actually chose on the
    form (the scope label and the engine preset); run_season folds in
    everything else and records the lot in run_meta.json before the first
    week, so the record says what produced these weeks even if the replay is
    interrupted."""
    from app.core import retro
    root = RETRO_ROOT / season
    _retro_status[season] = "running"
    _retro_stop.discard(season)     # no stale stop flag from a past run
    retro.clear_flags(root)         # nor a stale STOP/PAUSE file from one
    guard = _sleep_guard()          # overnight replays must outlive the lid
    try:
        def _tick(_asof):
            # run_season calls this after every week: the clean stop point.
            # Completed weeks are on disk and a restarted replay skips them.
            if season in _retro_stop:
                raise _RetroStopRequested()
        retro.run_season(root, season, locations, replicates=replicates,
                         particles=particles, width=width, progress=_tick,
                         settings=settings)
        # equal, never-fitted member weights (the sealed recipe)
        df = retro.score_season(root, season,
                                ensemble_weights={"pf": 0.5, "analogue": 0.5})
        df.to_json(root / "scores.json")
        _retro_status[season] = "done"
    except (_RetroStopRequested, retro.SeasonStopped):
        # completed weeks stay; the results page scores whatever exists
        _retro_status[season] = "stopped"
    except Exception as e:
        _retro_status[season] = f"error: {str(e)[:150]}"
    finally:
        _retro_stop.discard(season)
        _invalidate_scans()          # the season's counts and status settled
        # the flags are requests, not state: leaving one behind would stop or
        # hold the NEXT replay before it ran a week
        retro.clear_flags(root)
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass


@app.post("/retro/stop")
def retro_stop():
    """Ask every live season replay to stop after the fits now in flight.
    The flag is polled between individual fits, so the stop lands in well
    under a minute, not at the week boundary. Completed weeks stay on disk,
    an interrupted week keeps its finished fits, and a restarted replay
    resumes from exactly there (nothing completed is redone). A PAUSED
    season stops too: request_stop clears the pause so the worker wakes and
    exits."""
    from app.core import retro
    _invalidate_scans()
    stopping = []
    for season, st in list(_retro_status.items()):
        if st != "running" and _season_status(season) not in ("running",
                                                              "paused"):
            continue
        _retro_stop.add(season)
        _retro_status[season] = "stopping"
        stopping.append(season)
        retro.request_stop(_live_root(season))
    if stopping:
        _flash("Stopping " + ", ".join(sorted(stopping)) + " after the "
               "fits now in flight. Completed weeks and finished fits are "
               "kept; the replay resumes from there next time.")
    return RedirectResponse("/retro", status_code=303)


@app.post("/retro/{season}/stop")
def retro_season_stop(request: Request, season: str):
    """Stop ONE season after the fits now in flight. Safe by construction:
    every finished fit is checkpointed and the interrupted week's
    samples.json is never written, so nothing downstream sees a half-week,
    and pressing Run again refits only the cells that never ran."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was stopped.")
        return _back(request, "/retro")
    if _season_status(season) not in _RETRO_ACTIVE:
        _flash(f"{season} is not replaying, so there was nothing to stop.")
        return _back(request, "/retro")
    retro.request_stop(_live_root(season))
    _retro_stop.add(season)
    if _season_status(season) in ("running", "paused"):
        _retro_status[season] = "stopping"
        _flash(f"Stopping {season} after the fits now in flight. Completed "
               "weeks and finished fits are kept; Run resumes from there.")
    else:
        # nothing was actually replaying: resolve now rather than leaving a
        # "stopping" claim nobody will ever clear
        _retro_status[season] = "stopped"
        _retro_stop.discard(season)
        _flash(f"{season} was not replaying; it is marked stopped and Run "
               "will start it fresh or resume it.")
    return _back(request, "/retro")


@app.post("/retro/{season}/pause")
def retro_season_pause(request: Request, season: str):
    """Hold after the fits now in flight -- the flag is polled between
    individual fits, so the hold lands in well under a minute and the user
    gets the machine back. The process stays alive and the sleep guard stays
    held, so an overnight replay resumes on the same machine state it paused
    on."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was paused.")
        return _back(request, "/retro")
    if _season_status(season) not in ("running", "paused"):
        _flash(f"{season} is not replaying, so there was nothing to pause.")
        return _back(request, "/retro")
    retro.request_pause(_live_root(season))
    _flash(f"Pausing {season} after the fits now in flight. The replay "
           "holds; Resume continues it.")
    return _back(request, "/retro")


@app.post("/retro/{season}/resume")
def retro_season_resume(request: Request, season: str):
    """Release a hold. The worker picks up at the next week; the elapsed
    clock resumes where it stopped rather than restarting."""
    from app.core import retro
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was resumed.")
        return _back(request, "/retro")
    retro.clear_pause(_live_root(season))
    _flash(f"Resuming {season}.")
    return _back(request, "/retro")


@app.post("/retro/run")
def retro_run(background: BackgroundTasks, season: str = Form(...),
              locations: str = Form("panel6"),
              custom_locations: list = Form([]),
              particles: int = Form(10_000),
              replicates: int = Form(3),
              width: int = Form(4),
              engine: str = Form("pf"),
              mode: str = Form("resume"),
              confirm: str = Form("")):
    """Start (or resume) a season replay.

    `mode` is what the start-over prompt resolved to, and it is the only way
    an existing season tree is ever moved or removed:

      resume   the historical behaviour: completed weeks are kept and skipped
      archive  move the current tree to a timestamped sibling, then run clean
      discard  delete the current tree (confirmation required), then run clean

    Nothing here destroys work silently: archive is a move and reversible by
    hand, and discard refuses without a confirmation naming the season."""
    from app.core import retro
    from app.core.retro import available_seasons
    # a start may archive or discard a tree: nothing cached about it survives
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was started.")
        return RedirectResponse("/retro", status_code=303)
    if _season_status(season) in _RETRO_ACTIVE:
        _flash(f"{season} is already replaying (status: "
               f"{_season_status(season)}). One season worker runs at a "
               "time; stop it first if you want to start over.")
        return RedirectResponse("/retro", status_code=303)
    # The mirror of /api/busy, server-side: the per-button guard is client
    # convenience, and a POST that bypassed it (second tab, stale page,
    # script) must not double-book the engine over a console run or another
    # season's worker.
    if _status.get("running"):
        _flash("A console run holds the engine ("
               + (_status.get("run_label") or str(_status.get("running")))
               + "). Stop it from the Forecast tab first; nothing was "
               "started.")
        return RedirectResponse("/retro", status_code=303)
    other = sorted(x for x in _known_seasons()
                   if x != season and _season_status(x) in _RETRO_ACTIVE)
    if other:
        _flash("Another season is already replaying ("
               + ", ".join(other) + "). One season worker runs at a time; "
               "stop it first. Nothing was started.")
        return RedirectResponse("/retro", status_code=303)
    if mode not in ("resume", "archive", "discard"):
        _flash(f"'{mode}' is not one of resume, archive, or discard. "
               "Nothing was started and nothing was changed.")
        return RedirectResponse("/retro", status_code=303)
    if season not in available_seasons():
        _flash(f"Season {season} is not available. A season appears once its "
               "vintage archive exists.")
        return RedirectResponse("/retro", status_code=303)
    if engine != "pf":
        # pf2s slots in HERE later: accept engine == "pf2s", thread a
        # {"variant": "2strain"} extra through retro.run_week's RunSpec, and
        # collect the member alongside pf in samples.json.
        _flash("Only the PF engine preset is available for retrospectives "
               "at present.")
        return RedirectResponse("/retro", status_code=303)
    all_states = _retro_state_names()
    if locations == "all":
        names = all_states
    elif locations == "custom":
        names = [n for n in custom_locations if n in set(all_states)]
        if not names:
            _flash("Custom scope selected but no locations were checked. "
                   "Check at least one state and try again.")
            return RedirectResponse("/retro", status_code=303)
    else:
        names = ["Alaska", "New York", "Wyoming", "Pennsylvania",
                 "Vermont", "California"]
    # keep the knobs inside what the machine survives (budget: 0.45 fits/min)
    particles = max(1_000, min(int(particles), 100_000))
    replicates = max(1, min(int(replicates), 10))
    width = max(1, min(int(width), 16))
    # Start-over handling comes AFTER every validation above: a rejected
    # form must never have moved or removed anything first.
    live = _live_root(season)
    existing = _weeks_done(live)
    if mode == "discard":
        if confirm != season:
            _flash(f"Discarding {season} was not confirmed, so nothing was "
                   "deleted and nothing was started.")
            return RedirectResponse("/retro", status_code=303)
        if existing:
            try:
                retro.delete_tree(live)
            except Exception as e:
                _flash(f"Could not delete the {season} results: "
                       f"{type(e).__name__}: {str(e)[:160]}. Nothing was "
                       "started; the existing results are intact.")
                return RedirectResponse("/retro", status_code=303)
            _flash(f"Discarded {existing} completed week"
                   f"{'' if existing == 1 else 's'} of {season}. Starting a "
                   "fresh replay.")
    elif mode == "archive" and existing:
        try:
            dst = retro.archive_run(RETRO_ROOT, season)
        except Exception as e:
            # the move is atomic, so a failure leaves the original whole --
            # say so loudly rather than replaying over an unarchived season
            _flash(f"Could not archive {season}: {type(e).__name__}: "
                   f"{str(e)[:160]}. Nothing was started; the existing "
                   "results are intact.")
            return RedirectResponse("/retro", status_code=303)
        _flash(f"Archived {existing} completed week"
               f"{'' if existing == 1 else 's'} of {season} as "
               f"{dst.name}; it stays viewable from the season list. "
               "Starting a fresh replay.")
    # claim inside the request, not the background task, so a double submit
    # can't race two season workers over the same tree
    _invalidate_scans()       # an archive or discard just moved the tree
    _retro_status[season] = "running"
    _retro_claim_at[season] = time.time()
    # the settings recorded with the run: the scope the user picked and the
    # engine preset, which the location list alone cannot say
    background.add_task(_retro_bg, season, names, width, replicates, particles,
                        {"scope": locations, "engine": engine})
    return RedirectResponse("/retro", status_code=303)


@app.get("/retro/{season}", response_class=HTMLResponse)
def retro_results(request: Request, season: str, week: str = "",
                  archive: str = ""):
    """The season results page. `archive` selects an archived run instead of
    the live season; everything below (scores, player, per-state table, the
    report link) then reads that run's own tree."""
    import json as _json
    import numpy as np
    import pandas as pd
    from app.core import retro
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        _flash("Unrecognized archived run identifier.")
        return RedirectResponse("/retro", status_code=303)
    root, _is_seal = _season_root(season, archive)
    weeks = sorted(p.parent.name for p in (root / "weeks").glob("*/samples.json"))
    if not weeks:
        # a raw unthemed dead-end helps nobody: back to the season list,
        # which already knows how to show a 0-weeks season
        _flash(f"{season}: no completed weeks yet. Start the replay and "
               "check back shortly." if not archive else
               f"{season}: that archived run has no completed weeks, or it "
               "has been deleted.")
        return RedirectResponse("/retro", status_code=303)
    sf = root / "scores.json"
    score_error = ""
    def _stored_empty():
        try:
            import pandas as _p
            d = _p.read_json(sf)
            return d.empty or "model" not in d.columns
        except Exception:
            return True
    try:
        # Rescore when stale, when asked (?rescore=1), or when the stored file
        # is EMPTY: an early failed run writes an empty scores.json whose
        # fresh mtime would otherwise block rescoring forever (seen in the
        # field on the first laptop retrospective).
        if (not sf.exists() or request.query_params.get("rescore")
                or _stored_empty()
                or sf.stat().st_mtime < max(
                (root / "weeks" / w / "samples.json").stat().st_mtime for w in weeks)):
            retro.score_season(
                root, season,
                ensemble_weights={"pf": 0.5, "analogue": 0.5}).to_json(sf)
    except Exception as e:
        # A hidden failure here once masqueraded as "truth not settled" on a
        # fresh laptop. Show the truth: what broke, so it can be fixed.
        score_error = f"{type(e).__name__}: {str(e)[:220]}"
    try:
        df = pd.read_json(sf) if sf.exists() else pd.DataFrame()
    except Exception:
        df = pd.DataFrame()
    heads, curve, states = {}, [], []
    scoreable = (not df.empty) and ("model" in df.columns)
    if scoreable:
        for m in ("pf", "analogue", "ensemble"):
            g = df[df.model == m]
            if len(g):
                heads[m] = g.wis.sum() / g.base_wis.sum()
        for a in sorted(df["asof"].unique()):
            g = df[(df.model == "ensemble") & (df["asof"] <= a)]
            if len(g):
                curve.append((str(a)[:10], g.wis.sum() / g.base_wis.sum()))
        for loc in sorted(df.location.unique()):
            row = {"name": loc}
            for m in ("pf", "analogue", "ensemble"):
                g = df[(df.model == m) & (df.location == loc)]
                row[m] = g.wis.sum() / g.base_wis.sum() if len(g) else None
            states.append(row)
    wk = week if week in weeks else weeks[-1]
    d = _json.loads((root / "weeks" / wk / "samples.json").read_text())
    from app.core.report import categorical_probs
    from app.core.report_v2 import CATS
    from app.core.usmap import svg_map
    locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    cards = {}
    for loc, s in d["pf"].items():
        arr = np.asarray(s["1"], float)
        origin = np.asarray(s["0"], float)
        lo = float(np.median(origin[np.isfinite(origin)]))
        probs = categorical_probs(arr, lo, int(n2p[loc]), 1)
        hover = (f"<b>{loc}</b><br>1-wk median: "
                 f"{float(np.median(arr[np.isfinite(arr)])):.0f}<br>" +
                 "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                             for c in CATS))
        cards[n2f[loc]] = {"probs": probs, "name": loc, "abbr": n2a[loc],
                           "fips": n2f[loc], "hover_html": hover}
    for name, abbr in n2a.items():
        cards.setdefault(n2f.get(name, name), {"name": name, "abbr": abbr,
                                               "fips": n2f.get(name, "")})
    map_html = svg_map(cards)
    if not scoreable and not score_error:
        # scored zero cells with no exception: diagnose WHICH input is empty
        try:
            import json as _dj
            from datetime import date as _dd, timedelta as _dt
            from app.core.scoring import load_truth as _lt
            truth_d, n2f_d = _lt()
            season_dates = {w for w in weeks}
            t_rows = sum(1 for (f, d) in truth_d
                         if any(str(d.date()) > w for w in list(season_dates)[:1]))
            d0 = _dj.loads((root / "weeks" / weeks[len(weeks)//2] / "samples.json").read_text())
            import numpy as _dn
            pos_med = sum(1 for loc, sm in d0.get("pf", {}).items()
                          for h in ("1",)
                          if _dn.median(_dn.asarray(sm[h], float)) > 0)
            # walk ONE cell through every scoring step and name its killer
            import traceback as _tb
            import pandas as _dp
            from app.core import ensemble as _de
            from app.core.scoring import _baseline_cells as _dbc
            from flubnf.wis import wis as _dwis
            wk_mid = weeks[len(weeks)//2]
            loc0 = sorted(d0.get("pf", {}))[0]
            fips0 = n2f_d.get(loc0)
            T0 = _dp.Timestamp(d0["asof"])
            q0 = _de.member_quantiles_from_samples(d0["pf"][loc0]).get("1", {})
            act = truth_d.get((fips0, T0 + _dp.Timedelta(days=7)))
            med = q0.get(0.5, "KEY-MISSING")
            try:
                wv = float(_dwis(q0, act).wis) if act else "skipped"
            except Exception as we:
                wv = f"WIS-THREW {type(we).__name__}: {str(we)[:90]}"
            try:
                bb = _dbc(d0["asof"], {fips0}, truth_d)
                bv = bb.get((fips0, d0["asof"], 0), "BASELINE-MISSING")
            except Exception as be:
                bv = f"BASELINE-THREW {type(be).__name__}: {str(be)[:90]}"
            probe = (f"probe cell {loc0} asof {d0['asof']} h1: actual={act}, "
                     f"median={med}, wis={wv}, baseline={bv}; truth rows "
                     f"{len(truth_d)}, positive-median locs {pos_med}, "
                     f"weeks {len(weeks)}")
        except Exception as pe:
            probe = f"diagnostic probe failed: {type(pe).__name__}: {str(pe)[:120]}"
        score_error = "scored zero cells with no exception. " + probe
    if not scoreable and score_error:
        map_html = ("<p class='hint'>Scoring failed: <code>"
                    + score_error + "</code>. The fitted forecasts below are "
                    "intact; fix the scoring input (usually the FluSight hub "
                    "clone, via the Data tab) and reload this page.</p>")
    elif not scoreable:
        map_html = ("<p class='hint'>No scoreable weeks yet. Truth for "
                    "these forecast dates has not settled, so relWIS arrives "
                    "later; the weekly maps below are available now.</p>") + map_html
    # season-level official availability for the player's two-tier toggles:
    # which comparators submitted at least once this season, known before
    # playback starts (a week they skipped then reads as a gap, not
    # breakage)
    from app.core import playback as _playback
    try:
        official_catalog = _playback.season_official_catalog(root)
    except Exception:
        official_catalog = []
    return templates.TemplateResponse(request, "retro_season.html", {
        "active": "Retrospective", "season": season, "heads": heads, "curve": curve, "states": states,
        "weeks": weeks, "week": wk, "map_html": map_html,
        "official_catalog": official_catalog,
        "prog": (_archive_progress(root, season) if archive
                 else _retro_progress(season)),
        "archive": archive,
        "archive_when": retro.stamp_human(archive) if archive else "",
        "n_weeks": len(weeks) if scoreable else 0, "score_error": score_error})


@app.get("/api/retro/{season}/playback/{asof}")
def api_retro_playback(season: str, asof: str, archive: str = ""):
    """One stored retrospective week as a playback payload: member and
    ensemble quantile fans, settled truth, the CDC's submitted comparators,
    and running relWIS stats. Cached under <season_root>/playback_cache/.

    `archive` reads an archived run instead of the live season -- the same
    identifier the season page carries, so the player replays a frozen run
    exactly as it replays a live one."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = _season_root(season, archive)
    try:
        return playback.build_week(root, season, asof)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)


@app.get("/retro/{season}/report")
def retro_season_report(season: str, archive: str = ""):
    """Generate (cached by mtime) and download the self-contained season
    report: the season player with every week's data embedded, one HTML
    file, no server needed. `archive` builds the report for an archived run
    instead, inside that run's own tree."""
    from fastapi.responses import FileResponse, PlainTextResponse
    from app.core import playback, report_season
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = _season_root(season, archive)
    try:
        p = report_season.build_season_report(
            root, season, archive=archive,
            build=RUNNING_SHA, versions=VERSIONS)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return FileResponse(p, filename=p.name, media_type="text/html",
                        content_disposition_type="attachment")


@app.get("/api/retro/{season}/report_path")
def api_retro_report_path(season: str, archive: str = ""):
    """Build the season report if absent (same builder as the download
    route, cached by mtime) and return its absolute path. The results
    page's Reveal-in-Finder button feeds this path to /output/reveal, the
    belt-and-braces route for the native window."""
    from fastapi.responses import PlainTextResponse
    from app.core import playback, report_season
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    root, _is_seal = _season_root(season, archive)
    try:
        p = report_season.build_season_report(
            root, season, archive=archive,
            build=RUNNING_SHA, versions=VERSIONS)
    except playback.UnknownWeek as e:
        return PlainTextResponse(str(e), status_code=404)
    return {"path": str(p)}


@app.post("/run")
def run_models(request: Request,
               background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: list = Form([]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all"),
               members: int = Form(2)):
    # the pipeline's contract is Saturdays with an archived vintage; hold
    # the user to it kindly instead of failing three phases into the run
    from datetime import date as _date, timedelta as _td
    try:
        _d = _date.fromisoformat(forecast_date)
        if _d.weekday() != 5:
            _d -= _td(days=(_d.weekday() - 5) % 7)
            _flash(f"Snapped {forecast_date} to Saturday {_d}. Forecasts "
                   "align to FluSight's weekly cadence.")
            forecast_date = _d.isoformat()
    except ValueError:
        pass
    try:
        data_mod.vintage_path(forecast_date)
    except Exception:
        vs = data_mod.vintages()
        near = min(vs, key=lambda v: abs(_date.fromisoformat(v) - _date.fromisoformat(forecast_date))) if vs else None
        _flash(f"No archived data for {forecast_date}."
               + (f" Nearest available: {near}." if near else
                  " Pull the FluSight hub on the Data tab first."))
        return _back(request, "/forecast")
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates, "members": members})
    # checkboxes arrive as a list, the model pages' text input as one
    # comma-separated string inside it -- flatten both to clean names
    locations = [x.strip() for l in locations
                 for x in str(l).split(",") if x.strip()]
    if not locations:
        # nothing checked used to silently run Ohio -- ask instead
        _flash("Select at least one location, or all 52 jurisdictions. "
               "Nothing was run.")
        return _back(request, "/forecast")
    if _status.get("running"):
        _status["log"].append("A run is already in progress; not starting another.")
        return RedirectResponse("/forecast#results", status_code=303)
    # The mirror of /api/busy, server-side: a client that bypassed the
    # per-button guard (a second tab, a stale page, a script) must not
    # double-book the engine over a live season replay. The client guard is
    # convenience; this check is the protection.
    live_retro = sorted(x for x in _known_seasons()
                        if _season_status(x) in _RETRO_ACTIVE)
    if live_retro:
        _flash("A retrospective replay holds the engine ("
               + ", ".join(live_retro) + "). Stop or pause it from the "
               "Retrospective tab first; nothing was run.")
        return _back(request, "/forecast")
    # BackgroundTasks fire AFTER the redirect renders; claim the running slot
    # NOW so the page the user lands on shows the run (double-click race,
    # laptop field test 2026-08-18)
    _status["running"] = "starting"
    _invalidate_scans()         # a run is starting: nothing cached survives it
    _status["started_utc"] = __import__("time").time()   # the wall clock starts here
    _status["run_label"] = f"{forecast_date} · queued"
    if "all" in [l.lower() for l in locations]:
        import pandas as _pd
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
        us = _l.location_name[_l.abbreviation == "US"]
        if len(us):
            locs_list.append(str(us.iloc[0]))   # national, fitted directly
    else:
        locs_list = list(locations)
    if not any(str(l).upper() in ("US", "US (NATIONAL)") for l in locs_list):
        locs_list.append("US")   # national fitted directly, always
    # the label owns the arithmetic: N states the user picked, plus the
    # national fit we always add -- no phantom extra location in the count
    n_states = sum(1 for l in locs_list
                   if str(l).upper() not in ("US", "US (NATIONAL)"))
    _status["run_label"] = f"{forecast_date} · {n_states} state(s) + US · queued"
    # honest progress: the denominator (locations x replicates) is known NOW,
    # from the spec -- shard .prog files only ever grow toward it, so pct can
    # never regress when a late shard registers. Also drop the previous run's
    # workroot so its finished .prog files never flash as this run's progress.
    # Engines without per-fit shards (amcmc, analogue) get NO denominator:
    # /api/progress then reports the phase instead of fabricating 0/N.
    _status["workroot"] = None
    _status["expected_total"] = (len(locs_list) * int(replicates)
                                 * (2 if members == 3 else 1)
                                 if engine in ("all", "pf") else None)
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=locs_list,
                   weeks_to_drop=weeks_to_drop,
                   weeks_to_nowcast=weeks_to_nowcast,
                   replicates=replicates,
                   extra={"members": 3} if members == 3 else {})
    if engine in ("all", "pf", "analogue"):
        # 'analogue' rides the same pipeline with the PF block skipped --
        # the model page's "Run Calendar analogue only" button posts it
        background.add_task(_run_all, spec)
    elif engine == "amcmc":
        from app.core.engines import amcmc as am_engine
        def _bg():
            ledger = Ledger()
            rid = None
            try:
                rid = ledger.open_run(spec, Path("pending"), {"engine": "amcmc"})
                _status["running"] = f"amcmc:{rid}"
                w = lease_workroot(rid)
                ledger.set_workroot(rid, w)   # the row must name the real one
                _status["workroot"] = str(w)
                _status["phase"] = ("Adaptive MCMC: this engine does not "
                                    "report per-fit progress.")
                out = am_engine.execute(spec, w)
                n_ok = sum(1 for r in out["records"] if r.get("ok"))
                ledger.close_run(rid, "ok", {"ok_states": n_ok})
            except Exception as e:
                if rid is not None:
                    ledger.close_run(rid, "error", {"error": str(e)[:300]})
                _status["log"].append(f"adaptive MCMC run failed: {str(e)[:200]}")
            finally:
                _status["running"] = None
                _status["workroot"] = None
                _status["phase"] = ""
                _status["run_label"] = ""
                _status["expected_total"] = None
                _status["started_utc"] = None
        background.add_task(_bg)
    else:
        # an engine we don't know: release the claim instead of wedging the
        # console until restart, and say so
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _flash(f"'{engine}' is not one of the available engines. "
               "Nothing was run.")
    return RedirectResponse("/forecast#results", status_code=303)
