"""FastAPI operations console: every tab of the FluBNF app in one module.

Server-rendered (locked decision: FastAPI + templates, no build chain).
Run:  .venv/bin/uvicorn app.ui.server:app --port 8710

Contents, in file order (each section starts with a `# === ... ===` banner;
templates under app/ui/templates):

  Bootstrap           app, /static, CSRF guard, Jinja globals, build SHA
  Shared              model names/colors, season month axis, cached scans
  Forecast state      ENGINES, _status, _engine_lock, component versions,
                      GET /api/versions, anchor dates
  Home                GET /, GET /api/outlook-ready            home.html
  Methods             GET /methods                             methods.html
  Forecast            GET /forecast                            forecast.html
  Data                GET /data                                data.html
  Storage             GET /storage (= /runs), POST /runs/clear,
                      /storage/delete, /storage/clear-workroots,
                      GET /api/storage/reclaim, POST /storage/reclaim
                                                               runs.html
  Console controls    POST /run/stop, GET /api/busy, POST /data/pull,
                      POST /freshness (renders data.html)
  Forecast pipeline   _harvest_params, sleep guard, _write_weekly_report,
                      _run_all, _archive_run, submission files
  Run pages           GET /runs/{id}, /report, /report/download,
                      POST /runs/{id}/rerun                    run.html
  Forecast APIs       GET /api/series, GET /api/progress
  Output              GET /output, /output/download, POST /output/reveal,
                      GET /output/report, /output/report/download
                                                               output.html
  Sandbox             GET /sandbox, POST /sandbox/*, GET /api/sandbox/*
                                                               sandbox.html
  Models              GET /models, /model/{name}               model.html
  Retrospective       roots/claims/status, ETA estimate
                      GET /retro, /api/retro/progress, /api/retro/startover,
                      POST /retro/{s}/archive/{stamp}/delete   retro.html
                      results preparation, GET /api/retro/{s}/results_status
                      worker _retro_bg, POST /retro/stop, /retro/{s}/stop,
                      /pause, /resume, POST /retro/run
                      GET /retro/{s}, /api/retro/{s}/playback/{asof},
                      /mapswap/{asof}, /retro/{s}/report,
                      /api/retro/{s}/report_path           retro_season.html
  Forecast            POST /run (form and rerun entry to _run_all)
  Startup warm        _start_background_warm() at import
"""
from __future__ import annotations

import html as _htmlmod
import threading
import time
import sys
from collections import OrderedDict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _trace(msg: str) -> None:
    """Startup trace: server half of flubnf/cli.py's _trace (same format and
    FLUBNF_STARTUP_TRACE file, so the two interleave); free when unset."""
    import os as _os
    path = _os.environ.get("FLUBNF_STARTUP_TRACE")
    if not path:
        return
    t = time.time()
    line = (f"{t:.3f} {time.strftime('%H:%M:%S', time.localtime(t))}"
            f".{int(t * 1000) % 1000:03d} [pid {_os.getpid()} srv] {msg}")
    try:
        with open(path, "a") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr, flush=True)


_trace("import begin (fastapi + app.core next)")

from fastapi import BackgroundTasks, FastAPI, Form, Request     # noqa: E402
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse,  # noqa: E402
                               RedirectResponse)
from fastapi.templating import Jinja2Templates                  # noqa: E402

from app.core import horizons as _hzmod                         # noqa: E402
from app.core import ttlcache                                   # noqa: E402


class _LazyDataMod:
    """app.core.data, resolved on first attribute use: importing it here
    would put pandas on the server-import path, which delays the window
    opening. The first use rebinds the global `data_mod` to the module."""

    def __getattr__(self, name):
        from app.core import data as real
        globals()["data_mod"] = real
        return getattr(real, name)


data_mod = _LazyDataMod()
from app.core import runs as _runs
from app.core.runs import (Ledger, RunSpec, fmt_hms,            # noqa: E402
                           lease_workroot, results_html, settings_html,
                           spec_settings, version_pairs)

# === Bootstrap: app, static mount, templates, CSRF guard ===
app = FastAPI(title="FluBNF")
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["pop_flash"] = lambda: _status.pop("flash", None)
# one wall-time format everywhere the console shows a duration
templates.env.filters["hms"] = fmt_hms

#: Hostnames a state-changing request may name. Host/Origin are what a
#: cross-site form-POST or DNS-rebinding page cannot forge. "testserver" is
#: Starlette's TestClient (no dot, so never a public DNS name).
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "testserver"}


def _authority_hostname(authority: str) -> str:
    """Hostname of a Host header value or an Origin URL: lowercased, port
    and IPv6 brackets stripped, "" when it cannot be parsed (and "" is
    never a local hostname, so unparseable means refused)."""
    from urllib.parse import urlsplit
    try:
        host = urlsplit(authority if "//" in authority
                        else "//" + authority).hostname
    except ValueError:
        return ""
    return host or ""


@app.middleware("http")
async def _same_host_guard(request: Request, call_next):
    """CSRF guard for a cookie-less loopback tool: POST/PUT/DELETE must carry
    a localhost Host and, if present, a localhost Origin. GET stays open
    (reports, pywebview, polls); every mutating control is a POST."""
    if request.method in ("POST", "PUT", "DELETE"):
        if (_authority_hostname(request.headers.get("host", ""))
                not in _LOCAL_HOSTNAMES):
            return PlainTextResponse(
                "Refused: the Host header does not name localhost.\n",
                status_code=403)
        origin = request.headers.get("origin")
        if (origin is not None
                and _authority_hostname(origin) not in _LOCAL_HOSTNAMES):
            return PlainTextResponse(
                "Refused: cross-origin request, the Origin header does "
                "not name localhost.\n", status_code=403)
    return await call_next(request)


def _script_json(obj) -> str:
    """JSON for an inline <script> block marked | safe: "<" becomes \\u003c
    so no value can close the script element. Every *_json template value
    goes through here."""
    import json as _json
    return _json.dumps(obj).replace("<", "\\u003c")


def _platform() -> str:
    """sys.platform behind a seam tests can patch (patching sys.platform
    itself breaks shutil.which and more)."""
    return sys.platform


def _engine_setup_hint():
    """HTML clause telling this machine's user how to enable the PF engine.

    Windows gets setup.ps1 + docs/WINDOWS.md (no setup_engine.sh twin: the
    PyBNF fork is private). Resolved per render via _platform() so tests can
    vary it. Not for methods.html: site_build publishes that page, and a
    platform-specific string would bake in the builder's platform.
    """
    from markupsafe import Markup
    if _platform() == "win32":
        return Markup(
            "run <code>powershell -NoProfile -ExecutionPolicy Bypass -File "
            "setup.ps1</code>, which reports what is still missing; the "
            "engine also needs the private PyBNF fork, so read "
            "<code>docs\\WINDOWS.md</code> first")
    if _platform() == "darwin":
        return Markup("double-click <code>SetupEngine.command</code> and "
                      "relaunch the console")
    return Markup("run <code>./setup_engine.sh</code> and relaunch the console")


templates.env.globals["engine_setup_hint"] = _engine_setup_hint

# === Bootstrap: build SHA and restart banner ===
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


@ttlcache.ttl_cache(ttl_s=10.0)
def _repo_sha_on_disk() -> str:
    """Cached HEAD (10 s): the restart banner reads it on every render, and
    a git subprocess per page (~20 ms) was the largest fixed render cost."""
    return _repo_sha()


def _restart_needed() -> bool:
    """True when a pull landed but this process still runs the old build
    (templates and static files reload; server logic does not)."""
    sha = _repo_sha_on_disk()
    return bool(sha and RUNNING_SHA and sha != RUNNING_SHA)


templates.env.globals["running_sha"] = lambda: RUNNING_SHA
templates.env.globals["restart_needed"] = _restart_needed
# one settings/results renderer for progress cards, run page and both report
# exports (app/core/runs.py), so their wording cannot diverge
templates.env.globals["settings_html"] = settings_html
templates.env.globals["results_html"] = results_html


# === Shared: model names, relWIS/Oracle wording, member and season colors ===
def _model_names() -> dict:
    """The one model-name map (player.js JSON literal, parsed by
    report_season.py); every surface that prints a model name reads it."""
    from app.core.report_season import MODEL_NAMES
    return MODEL_NAMES


templates.env.globals["model_name"] = lambda m: _model_names().get(m, m)


def _names_for_root(root) -> dict:
    """Model-name map for one season tree: pf is "Particle filter alone"
    unless the tree carries the Oracle step (older records store the bare
    filter under pf). One implementation, report_season.names_for_root, so
    season page, index and exported report agree."""
    from app.core import report_season
    try:
        return report_season.names_for_root(root, _model_names())
    except Exception:
        from app.core.site_build import PF_LABEL_FILTER
        return dict(_model_names(), pf=PF_LABEL_FILTER)


def _pf_name(root) -> str:
    """pf's name on one season tree (see _names_for_root)."""
    return _names_for_root(root).get("pf", "pf")


def _name_fn(names: dict):
    """model_name over one tree's names; passed in a page's context it
    shadows the global for that render."""
    return lambda m: names.get(m, m)


# The one relWIS convention sentence (relwis.PUBLISHED_CONVENTION_NOTE) and the
# Oracle SIHRS wording (app/core/oracle_text): globals so home, Methods, the
# public site (rendered through this env) and reports share one copy.
from app.core.relwis import PUBLISHED_CONVENTION_NOTE     # noqa: E402

templates.env.globals["relwis_convention_note"] = PUBLISHED_CONVENTION_NOTE

from app.core import oracle_text as _oracle_text              # noqa: E402

templates.env.globals["oracle_text"] = _oracle_text


def _member_colors() -> dict:
    """The one member-color map (player.js JSON literal, parsed by
    report_v2.py). Consumers draw the legacy ensemble with --gold on light
    grounds."""
    from app.core.report_v2 import model_colors
    return model_colors()


def _season_colors() -> list:
    """The one season-line palette (player.js SEASON_COLORS, parsed by
    report_v2.season_colors); already CV-safe, so never remapped."""
    from app.core.report_v2 import season_colors
    return season_colors()


# === Shared: season month axis (the one source of month-boundary week offsets) ===
#: Season month lengths from August, non-leap (invisible at week resolution).
#: Every season-week axis derives its month ticks from this table.
_MONTH_DAYS = (("Aug", 31), ("Sep", 30), ("Oct", 31), ("Nov", 30),
               ("Dec", 31), ("Jan", 31), ("Feb", 28), ("Mar", 31),
               ("Apr", 30), ("May", 31), ("Jun", 30), ("Jul", 31))

#: calendar month number -> label, in the season's own order
_MON_NAME = {i % 12 + 1: name
             for i, (name, _) in enumerate(_MONTH_DAYS, start=7)}


def _season_months() -> list:
    """[(label, weeks since August 1)] for each month start of the season."""
    out, day = [], 0
    for name, ndays in _MONTH_DAYS:
        out.append((name, round(day / 7.0, 2)))
        day += ndays
    return out


SEASON_MONTHS = _season_months()
templates.env.globals["season_months"] = SEASON_MONTHS


def _season_week_name(week: float) -> str:
    """A week offset from August 1 as calendar language ('early Jan' for
    week 22)."""
    day = int(round(week * 7)) % 365
    for name, ndays in _MONTH_DAYS:
        if day < ndays:
            third = ("early" if day < ndays / 3
                     else "mid" if day < 2 * ndays / 3 else "late")
            return f"{third} {name}"
        day -= ndays
    return ""


templates.env.globals["season_week_name"] = _season_week_name


def _month_ticks_for_dates(dates) -> list:
    """[(index, month label)] at every month change across ordered ISO dates
    (ticks for a date-indexed axis)."""
    out, prev = [], None
    for i, d in enumerate(dates):
        mm = str(d)[5:7]
        if prev is not None and mm != prev and mm.isdigit():
            out.append((i, _MON_NAME.get(int(mm), "")))
        prev = mm
    return out


templates.env.globals["month_ticks_for_dates"] = _month_ticks_for_dates


def _harmonic_fig(eps: float = 0.35, phis=(22.0,), x0: float = 62.0,
                  x1: float = 540.0, y_bot: float = 170.0, y_top: float = 20.0,
                  r_lo: float = 0.55, r_hi: float = 1.55, n: int = 104) -> dict:
    """Geometry for the (illustrative) seasonal-harmonic figure in diagrams.html.

    Curve: exp(eps * cos(2*pi*(t - phi)/52)), t in [0, 52] weeks since Aug 1,
    weeks mapped onto [x0, x1] and the rate band [r_lo, r_hi] onto
    [y_bot, y_top]. Returns one SVG path per phi, the pixel rows of exp(+eps),
    exp(-eps) and 1.0, each peak's x, and quarterly month ticks from
    SEASON_MONTHS closed by the wrap-around August at week 52.
    """
    import math

    def y(rel: float) -> float:
        return y_bot + (y_top - y_bot) * (rel - r_lo) / (r_hi - r_lo)

    def x(t: float) -> float:
        return x0 + (x1 - x0) * t / 52.0

    paths = []
    for phi in phis:
        pts = []
        for i in range(n + 1):
            t = 52.0 * i / n
            rel = math.exp(eps * math.cos(2.0 * math.pi * (t - phi) / 52.0))
            pts.append(("M" if i == 0 else "L") + f"{x(t):.1f},{y(rel):.1f}")
        paths.append(" ".join(pts))
    return {"paths": paths,
            "y_hi": round(y(math.exp(eps)), 1),
            "y_lo": round(y(math.exp(-eps)), 1),
            "y_one": round(y(1.0), 1),
            "peaks": [round(x(p), 1) for p in phis],
            "ticks": ([(m, round(x(wk), 1)) for m, wk in SEASON_MONTHS[::3]]
                      + [("Aug", round(x(52.0), 1))])}


templates.env.globals["harmonic_fig"] = _harmonic_fig

# === Forecast console state ===
# LEGACY names: "ensemble" is the blend retired 2026-09-22 and "amcmc" the
# sampler removed 2026-09-07; readers keep old rows/results, nothing writes them.
ENGINES = ("all", "pf", "analogue")  # "all" = pf + analogue
_status: dict = {"running": None, "log": []}
_last_form: dict = {}

#: ONE lock around every engine busy check and the claim it protects (routes
#: run on a threadpool; an unlocked check-then-claim let two submits both
#: start). Held for check+claim only, never while a run executes. Server-side
#: busy checks mirror /api/busy: the client guard is convenience only.
_engine_lock = threading.Lock()

#: Statuses offered the one-click re-run. Console fits hold no checkpoint, so
#: it is a FRESH run with the recorded settings (never worded "resume").
RERUN_STATUSES = ("stopped", "error", "failed", "interrupted", "partial")

# === Component versions and startup warm ===
#: pybnf/bngsim probe run by the engine venv's interpreter. Like the generated
#: runners (pf.py _RUNNER, retro.py _RETRO_RUNNER) it puts the PyBNF checkout
#: first on sys.path, and reads __version__ from the imported pybnf.py (the
#: fork runs from a checkout, not pip); importlib.metadata is the fallback.
_VERSION_PROBE = '''
import json, os, re, sys
sys.path.insert(0, %r)
from importlib.metadata import version
d = {}
for p in ("pybnf", "bngsim"):
    try:
        d[p] = version(p)
    except Exception:
        d[p] = "not installed"
try:
    import pybnf
    src = open(os.path.join(os.path.dirname(pybnf.__file__), "pybnf.py")).read()
    m = re.search(r'^__version__\\s*=\\s*"(.*)"', src, re.M)
    if m:
        d["pybnf"] = m.group(1)
except Exception:
    pass
print(json.dumps(d))
'''


def _component_versions() -> dict:
    """Versions of the components named in user-facing copy: console
    packages via importlib.metadata, pybnf/bngsim via _VERSION_PROBE,
    BioNetGen from the VERSION file beside BNG2.pl; 'not installed' when
    unresolvable.

    Slow (~1 s, engine-venv subprocess): never call at import. _warm_versions
    runs it on the warm thread; until then VERSIONS serves the persisted
    snapshot or pending markers, and pages fill in via /api/versions."""
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("fastapi", "jinja2", "plotly", "pandas", "numpy"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    out["bionetgen"] = "not installed"
    try:
        from flubnf.settings import BNG
        vf = Path(BNG).parent / "VERSION"
        if vf.is_file():
            out["bionetgen"] = vf.read_text().strip()
        elif Path(BNG).exists():
            out["bionetgen"] = "installed"
    except Exception:
        pass
    # Perl: BNG2.pl needs it (without it every location fails at preparation)
    import shutil as _shutil
    out["perl"] = _shutil.which("perl") or "not installed"
    out["pybnf"] = out["bngsim"] = "not installed"
    try:
        import json
        import subprocess
        from flubnf.settings import PY_ENGINE, PYBNF
        if Path(PY_ENGINE).exists():
            r = subprocess.run(
                [str(PY_ENGINE), "-c", _VERSION_PROBE % (str(PYBNF),)],
                capture_output=True, text=True, timeout=15)
            out.update(json.loads(r.stdout.strip() or "{}"))
    except Exception:
        pass
    return out


#: unresolved-version marker; pages poll /api/versions while any remains
VERSION_PENDING = "resolving…"

#: last launch's resolved probe, so a restart skips the pending markers
_VERSIONS_SNAPSHOT = (Path(__file__).resolve().parents[1]
                      / "state" / "component_versions.json")

_VERSION_KEYS = ("fastapi", "jinja2", "plotly", "pandas", "numpy",
                 "bionetgen", "perl", "pybnf", "bngsim")


def _versions_initial() -> dict:
    """VERSIONS at import: the persisted snapshot, else pending markers. The
    warm probe updates this dict IN PLACE (templates hold the reference)."""
    import json as _json
    out = {k: VERSION_PENDING for k in _VERSION_KEYS}
    try:
        snap = _json.loads(_VERSIONS_SNAPSHOT.read_text())
        if isinstance(snap, dict):
            out.update({k: str(v) for k, v in snap.items()
                        if k in _VERSION_KEYS})
    except Exception:
        pass
    return out


VERSIONS = _versions_initial()


def versions_resolved() -> bool:
    return VERSION_PENDING not in VERSIONS.values()


def _engine_versions_for_ledger(engines: str) -> dict:
    """engine_versions for a new ledger row: {"engines": ...} (the key
    historical rows hold) plus each resolved engine component version.
    Pending/'not installed' are probe states, never recorded as versions."""
    out = {"engines": engines}
    for key in ("pybnf", "bngsim", "bionetgen"):
        v = VERSIONS.get(key)
        if v and v not in (VERSION_PENDING, "not installed", "installed"):
            out[key] = str(v)
    return out


def _warm_versions() -> None:
    """The real probe, off the first-paint path: resolve, update VERSIONS in
    place, persist the snapshot for the next launch. Never raises."""
    import json as _json
    try:
        VERSIONS.update(_component_versions())
        _VERSIONS_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _VERSIONS_SNAPSHOT.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(VERSIONS))
        import os as _os
        _os.replace(tmp, _VERSIONS_SNAPSHOT)
    except Exception:
        pass


#: set once the warm pass finished its outlook computation (success or not)
_WARM_DONE = __import__("threading").Event()


def _outlook_ready() -> bool:
    """Whether home can render its outlook inline without paying the first
    science import: warm pass done, or pandas already loaded. False only on
    a cold first paint (home then serves the preparing silhouette)."""
    return _WARM_DONE.is_set() or "pandas" in sys.modules


def _start_background_warm() -> None:
    """Daemon thread started at import: version probe, home template and
    outlook (always, since even the empty silhouette pays the science
    imports), latest vintage frame and report modules. Best-effort: never
    delays the first request, failures are silent."""
    import threading

    def _warm():
        t0 = time.perf_counter()
        _trace("warm: thread begin (versions probe)")
        _warm_versions()
        _trace(f"warm: versions done at +{time.perf_counter() - t0:.2f}s")
        try:
            templates.env.get_template("home.html")     # compile once, here
        except Exception:
            pass
        _trace(f"warm: template done at +{time.perf_counter() - t0:.2f}s")
        try:
            rid, _res = _latest_results()
            _outlook_block(rid)
        except Exception:
            pass
        finally:
            _WARM_DONE.set()
        _trace(f"warm: outlook done at +{time.perf_counter() - t0:.2f}s")
        # pre-fill the latest vintage frame for the Forecast tab's first click
        try:
            vs = data_mod.vintages()
            if vs:
                _vintage_frame(str(data_mod.vintage_path(vs[-1])))
            templates.env.get_template("forecast.html")
            # model-name/color maps ride the report modules (~0.6 s import)
            from app.core import report_season, report_v2   # noqa: F401
        except Exception:
            pass
        _trace(f"warm: forecast done at +{time.perf_counter() - t0:.2f}s")

    threading.Thread(target=_warm, daemon=True,
                     name="flubnf-startup-warm").start()


@app.get("/api/versions")
def api_versions():
    """Versions as known now, and whether the probe landed (home and Methods
    poll this while a value is pending)."""
    return {"versions": dict(VERSIONS), "resolved": versions_resolved()}


# === Forecast: anchor dates ===
def resolve_anchor(day: str, vintages=None):
    """(anchor_vintage, why) for any typed date; ONE definition for the
    form's anchor line and the run, so they cannot disagree.

    A non-Saturday snaps back to Saturday, then to the newest archived
    vintage. A typed Saturday is returned as-is even when its vintage is
    missing (the caller refuses it rather than re-aiming).
    """
    from datetime import date as _d, timedelta as _td
    try:
        d = _d.fromisoformat(day)
    except (ValueError, TypeError):
        return None, ""
    if vintages is None:
        try:
            vintages = data_mod.vintages()
        except Exception:
            vintages = []
    if d.weekday() == 5:
        return day, "typed"
    sat = (d - _td(days=(d.weekday() - 5) % 7)).isoformat()
    earlier = [v for v in vintages if v <= sat]
    if earlier and earlier[-1] != sat:
        return earlier[-1], "not-published-yet"
    return (earlier[-1] if earlier else sat), "snapped"


def _default_forecast_date() -> str:
    """Latest Saturday, clamped to the latest archived vintage (the hub
    stops publishing off-season)."""
    import datetime as dt
    d = dt.date.today()
    sat = str(d - dt.timedelta(days=(d.weekday() - 5) % 7))
    vs = data_mod.vintages()
    return min(sat, vs[-1]) if vs else sat


# === Shared: cached filesystem scans ===
# Short-TTL caches (app/core/ttlcache.py) for directory scans repeated per
# render; keyed by path so a switched state root never serves another's
# answer. Every state-changing action calls _invalidate_scans().

@ttlcache.ttl_cache()
def _weeks_done(root: Path) -> int:
    """Completed weeks in a season tree (stored samples.json count): the
    retro pages' hot scan."""
    from app.core import retro
    root = Path(root)
    try:
        return len(retro.season_sample_files(root))
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
    """Workroot results.json paths, newest first (scan cached, files read
    fresh by the caller)."""
    from app.core.runs import APP_STATE
    return _scan_results(APP_STATE / "workroots")


def _invalidate_scans() -> None:
    """Drop every cached scan; state-changing actions call this."""
    ttlcache.clear_all()


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """PyBNF brand kit favicon (small-size mark)."""
    from fastapi.responses import FileResponse
    ico = Path(__file__).parent / "static" / "brand" / "favicon.ico"
    return FileResponse(ico, media_type="image/x-icon")


# === Home (/): outlook map, diagram feed -> home.html ===
def _outlook_cards(res: dict | None, rid: str | None = None) -> tuple:
    """(fips -> hover card for svg_map, source meta) for the home outlook.

    Exact path: the run's report bundle (report_inputs.json), so home shows
    the weekly report's categories; used as-is when it holds >= 2 per-model
    card sets. Otherwise one card set per stored model is approximated from
    results.json quantiles (categorical_probs_from_quantiles): meta
    approx=True, meta["by_model"] funds the toggle. A pre-v3 bundle that
    cannot fund a toggle keeps its exact single-model cards. Card-less
    states get empty cards so the full silhouette renders."""
    import json as _json

    from app.core import report_v2
    from app.core.report import categorical_probs_from_quantiles
    from app.core.report_v2 import CATS
    from app.core.runs import APP_STATE
    bundle_cards = bundle_meta = None
    if rid:
        try:
            b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
            if b.is_file():
                bundle = _json.loads(b.read_text())
                if (bundle.get("version")
                        in report_v2.SUPPORTED_BUNDLE_VERSIONS):
                    cards = {c["fips"]: c
                             for c in (bundle.get("cards") or {}).values()
                             if isinstance(c, dict) and c.get("fips")}
                    model = bundle.get("cards_model") or "pf"
                    if (model not in report_v2.RETIRED_MODELS
                            and any(c.get("probs") for c in cards.values())):
                        bundle_cards = cards
                        bundle_meta = {"model": model, "approx": False,
                                       "label": report_v2.MODEL_LABEL.get(
                                           model, report_v2.MODEL_LABEL["pf"]),
                                       # bundle v4 coverage; None -> 'no data'
                                       "fitted_fips": bundle.get(
                                           "fitted_fips")}
                        # >= 2 per-model card sets: exact cards and toggle
                        cbm = bundle.get("cards_by_model") or {}
                        if sum(1 for cs in cbm.values()
                               if any(isinstance(c, dict) and c.get("probs")
                                      for c in (cs or {}).values())) >= 2:
                            return bundle_cards, bundle_meta
        except Exception:
            bundle_cards = bundle_meta = None   # broken bundle: approximate
    _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2f = dict(zip(_l.location_name, _l.location.str.zfill(2)))
    n2a = dict(zip(_l.location_name, _l.abbreviation))
    n2p = dict(zip(_l.location_name, _l.population.astype(float)))
    models = (res or {}).get("models", {})
    # PF first, then the Groundhog (a legacy run's blend is not shown)
    model = next((m for m in ("pf", "analogue") if models.get(m)), "pf")
    observed = (res or {}).get("observed", {})
    by_model: dict = {}
    models = _hzmod.models_to_canonical(models)
    for mname, md in models.items():
        cards = {}
        for loc, qd in (md or {}).items():
            fips = n2f.get(loc, "")
            q1 = (qd or {}).get("0")      # one week ahead, canonical
            obs = observed.get(loc) or []
            # tolerate the pre-quantile results schema (medians-only floats)
            if len(fips) != 2 or not isinstance(q1, dict) or not obs:
                continue
            lo = float(obs[-1][1])
            probs = categorical_probs_from_quantiles(q1, lo, int(n2p[loc]), 0)
            if not probs:
                continue
            vals = [float(v) for v in q1.values()]
            med1 = float(q1.get("0.5", vals[len(vals) // 2]))
            # hover_html reaches innerHTML: escape the name at the source
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>current: {lo:.0f}"
                     f"<br>1-wk median: {med1:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                                 for c in CATS))
            cards[fips] = {"probs": probs, "name": loc,
                           "abbr": n2a.get(loc, ""),
                           "fips": fips, "hover_html": hover}
        if cards:
            by_model[mname] = cards
    # the retired blend is never the map, even on a legacy run
    from app.core.report_v2 import RETIRED_MODELS
    by_model = {m: c for m, c in by_model.items() if m not in RETIRED_MODELS}
    if model not in by_model and by_model:
        model = next(iter(by_model))
    # no toggle possible: an exact single-model bundle beats the approximation
    if bundle_cards is not None and len(by_model) < 2:
        return bundle_cards, bundle_meta
    cards = dict(by_model.get(model) or {})
    for name, fips in n2f.items():
        if len(fips) == 2:
            cards.setdefault(fips, {"name": name, "abbr": n2a.get(name, ""),
                                    "fips": fips})
    from app.core.report_v2 import MODEL_LABEL
    return cards, {"model": model, "approx": True,
                   "label": MODEL_LABEL.get(model, MODEL_LABEL["pf"]),
                   "by_model": by_model}


def _outlook_models(rid: str | None) -> dict:
    """{model: {fips: card}} from the bundle's cards_by_model (v3), models
    with data only; {} for older bundles (home then uses _outlook_cards'
    approximate sets)."""
    import json as _json

    from app.core import report_v2
    from app.core.runs import APP_STATE
    if not rid:
        return {}
    try:
        b = APP_STATE / "workroots" / rid / report_v2.BUNDLE_NAME
        if not b.is_file():
            return {}
        bundle = _json.loads(b.read_text())
        if bundle.get("version") not in report_v2.SUPPORTED_BUNDLE_VERSIONS:
            return {}
        out = {}
        for m, cards in (bundle.get("cards_by_model") or {}).items():
            byf = {c["fips"]: c for c in (cards or {}).values()
                   if isinstance(c, dict) and c.get("fips")
                   and c.get("probs")}
            if byf:
                out[m] = byf
        return out
    except Exception:
        return {}          # a broken bundle degrades to the plain map


def _diagram_data(res: dict | None) -> dict:
    """Per-location annotations for the compartment diagram: fitted-parameter
    medians (results.json 'params'), last observation, 1-week median. No
    template reads the 'diagram' key today; test_pages covers this."""
    out = {"date": "", "has_pf2s": False, "locations": {}, "order": []}
    if not res:
        return out
    try:
        out["date"] = res.get("forecast_date", "") or ""
        params = res.get("params") or {}
        pf_p = params.get("pf") or {}
        p2_p = params.get("pf2s") or {}
        models = _hzmod.models_to_canonical(res.get("models") or {})
        out["has_pf2s"] = bool(p2_p) or bool(models.get("pf2s"))
        observed = res.get("observed") or {}
        picked = (models.get("pf") or models.get("analogue")
                  or models.get("ensemble") or {})
        for loc in set(pf_p) | set(p2_p) | set(observed) | set(picked):
            e = {}
            if isinstance(pf_p.get(loc), dict) and pf_p[loc]:
                e["pf"] = pf_p[loc]
            if isinstance(p2_p.get(loc), dict) and p2_p[loc]:
                e["pf2s"] = p2_p[loc]
            obs = observed.get(loc) or []
            if obs:
                e["obs"] = obs[-1]
            q1 = (picked.get(loc) or {}).get("0")   # one week ahead
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


def _outlook_results_mtime(rid: str | None) -> float:
    """Outlook cache-key term: the run's results.json mtime (0.0 if none)."""
    if not rid:
        return 0.0
    from app.core.runs import APP_STATE
    try:
        return (APP_STATE / "workroots" / rid / "results.json").stat().st_mtime
    except OSError:
        return 0.0


@ttlcache.ttl_cache(ttl_s=300.0)
def _outlook_block_cached(rid: str | None, mtime: float) -> dict:
    """Home outlook (map, caption facts, model toggle), cached per (run,
    results mtime) so the long TTL never serves a stale map."""
    import json as _json
    res = None
    if rid:
        from app.core.runs import APP_STATE
        try:
            res = _json.loads((APP_STATE / "workroots" / rid
                               / "results.json").read_text())
        except Exception:
            res = None
    # latest run's outlook, else the empty-country silhouette
    map_svg, outlook_date, outlook_n = "", "", 0
    outlook_src: dict = {}
    outlook_toggle = ""
    try:
        from app.core import report_v2, usmap
        from app.core.usmap import map_legend, svg_map
        cards = {}
        try:
            cards, outlook_src = _outlook_cards(res, rid)
            if any(c.get("probs") for c in cards.values()):
                outlook_date = (res or {}).get("forecast_date", "")
            else:
                outlook_src = {}      # an empty map needs no model label
        except Exception:
            pass                      # no LOCATIONS/hub -> bare silhouette
        with_data = {c["abbr"] for c in cards.values() if c.get("probs")}
        # caption counts only colored jurisdictions (US has no state shape)
        outlook_n = len(with_data - {"US"})
        # fitted_fips (bundle v4) lets hovers tell a reporting gap from 'not
        # fitted'; absent -> hovers claim only 'no data'
        scope = outlook_src.get("fitted_fips") if outlook_src else None
        scope = set(scope) if scope is not None else None
        map_svg = ("<div style='max-width:880px;margin:0 auto'>"
                   "<script>window.MAP_LINK='/output/report';</script>"
                   + svg_map(cards, clickable=with_data, scope_fips=scope)
                   + map_legend() + "</div>")
        # toggle from the v3 bundle's per-model cards, else the approximate
        # sets; fewer than two models -> label only, never a dead control
        try:
            by_model = _outlook_models(rid) if outlook_src else {}
            if not by_model and outlook_src.get("approx"):
                by_model = outlook_src.get("by_model") or {}
            order = report_v2.toggle_models(by_model)
            if len(order) >= 2:
                default = (outlook_src.get("model")
                           if outlook_src.get("model") in order
                           else order[0])
                payload = {m: {"states": usmap.state_swap_payload(
                                   by_model[m], scope_fips=scope),
                               "us": {}}
                           for m in order}
                outlook_toggle = usmap.model_toggle(
                    order, report_v2.MODEL_LABEL, default, payload,
                    group_id="outlook-model", btn_class="quiet",
                    active_class="gold", wrap_class="row viewtabs")
        except Exception:
            outlook_toggle = ""
    except Exception:
        pass
    return {"map_svg": map_svg, "outlook_date": outlook_date,
            "outlook_n": outlook_n,
            "label": outlook_src.get("label", ""),
            "approx": bool(outlook_src.get("approx")),
            "toggle": outlook_toggle}


def _outlook_block(rid: str | None) -> dict:
    return _outlook_block_cached(rid, _outlook_results_mtime(rid))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    _t0 = time.perf_counter()
    _trace("home: request begin")
    try:
        rid, res = _latest_results()
    except Exception:
        rid, res = None, None
    pending = not _outlook_ready()
    if pending:
        # give the warm pass 1.5 s so a warm machine paints complete
        _WARM_DONE.wait(1.5)
        pending = not _outlook_ready()
    if pending:
        # truly cold start: silhouette + preparing note now; the page polls
        # /api/outlook-ready and reloads once
        from app.core.usmap import map_legend, svg_map
        ob = {"map_svg": ("<div style='max-width:880px;margin:0 auto'>"
                          + svg_map({}, clickable=set()) + map_legend()
                          + "</div>"),
              "outlook_date": "", "outlook_n": 0,
              "label": "", "approx": False, "toggle": ""}
    else:
        ob = _outlook_block(rid)
    _trace(f"home: outlook ready at +{time.perf_counter() - _t0:.2f}s "
           f"(pending={pending}), rendering")
    return templates.TemplateResponse(request, "home.html", {
        "active": "Home", "map_svg": ob["map_svg"],
        "outlook_date": ob["outlook_date"],
        "outlook_n": ob["outlook_n"],
        "outlook_model_label": ob["label"],
        "outlook_approx": ob["approx"],
        "outlook_toggle": ob["toggle"],
        "outlook_pending": pending,
        "versions": VERSIONS, "diagram": _diagram_data(res),
        "missing": __import__("flubnf.settings", fromlist=["check"]).check(verbose=False)})


@app.get("/api/outlook-ready")
def api_outlook_ready():
    """Whether home's outlook now renders inline (polled by the cold first
    paint's preparing state)."""
    return {"ready": _outlook_ready()}


# === Methods (/methods) -> methods.html ===
@app.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request):
    """Methodology reference: the SIHRS compartment model, the fitting
    machinery, the Oracle step, the Groundhog, and the data and verification
    policies."""
    return templates.TemplateResponse(request, "methods.html", {
        "active": "Methods", "versions": VERSIONS})


# === Forecast (/forecast) -> forecast.html ===
@app.get("/forecast", response_class=HTMLResponse)
def forecast_page(request: Request):
    import pandas as pd
    from flubnf.settings import load_locations
    # a missing state list must be visible: without it runs cover all 52
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
                                "replicates": 3, "members": 2, "season_start": ""}
    rid, res = _latest_results()
    # data panel: latest-vintage series for the selected locations (visible
    # before any run); seeded with US national, the panel's default
    import json as _json
    sel = ["US (national)"] + [l for l in form["locations"] if l != "all"]
    series = {}
    try:
        vs = data_mod.vintages()
        tdf = _vintage_frame(str(data_mod.vintage_path(vs[-1])))
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
    # fans: the latest STORED run's models (no session gate: they survive a
    # restart; the card title names the run's date)
    if res:
        for mname, md in res["models"].items():
            good = {loc: qs for loc, qs in md.items()
                    if all(isinstance(v, dict) for v in qs.values())}
            if good:
                fanq[mname] = good
        # the shipped models only: a legacy run's retired blend is not drawn
        from app.core.report_v2 import toggle_models
        fanq = {m: fanq[m] for m in toggle_models(fanq)}
    ledger_rows = Ledger().rows(5)
    for r in ledger_rows:
        r["label"] = _run_label(r["run_id"], r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        r["settings"] = spec_settings(r.get("spec", ""))
        # the latest-run card links the weekly report when one exists
        try:
            r["has_report"] = bool(_json.loads(r.get("outcome")
                                               or "{}").get("report"))
        except Exception:
            r["has_report"] = False
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
    # archived Saturdays, newest first, for the form's picker (the native
    # date popup fails in some webviews); str() because the list is
    # serialised into the page and date objects would break the render
    try:
        vintage_dates = [str(v) for v in reversed(data_mod.vintages())]
    except Exception:
        vintage_dates = []
    _anchor, _ = resolve_anchor(form.get("forecast_date", ""), vintage_dates)
    anchor_note = (f"Anchored on the archived week ending {_anchor}."
                   if _anchor else "No archived week on or before that date.")
    return templates.TemplateResponse(request, "forecast.html", {
        "active": "Forecast", "engines": ENGINES, "status": _status,
        "ledger": ledger_rows, "all_locs": all_locs,
        "vintage_dates": vintage_dates, "anchor_note": anchor_note,
        "default_date": _default_forecast_date(),
        "locations_error": locations_error, "form": form,
        "elapsed0": _console_elapsed(),
        "series_json": _script_json(series), "fanq_json": _script_json(fanq),
        "model_names_json": _script_json(_model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "season_colors_json": _script_json(_season_colors()),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "fc_date": (res or {}).get("forecast_date", "")})


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
    return data_mod.vintage_summary(date)


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_locations(path: str, date: str) -> tuple:
    return tuple(data_mod.vintage_location_names(date))


@ttlcache.ttl_cache(ttl_s=VINTAGE_TTL_S)
def _vintage_series(path: str, date: str, loc: str) -> dict:
    return data_mod.vintage_series(date, loc)


def _data_context(loc: str = "", vintage: str = "", freshness=None) -> dict:
    """Data page context: the latest vintage's freshness panel and the
    vintage browser's selection. Read-only; bad selections fall back to the
    defaults with a note, never an error page."""
    import re as _re
    vs = data_mod.vintages()
    ctx = {"active": "Data", "latest_vintage": vs[-1] if vs else "none",
           "n_vintages": len(vs), "freshness": freshness,
           "latest": None, "vintages": list(reversed(vs)),
           "sel_vintage": "", "sel_loc": "", "loc_names": [],
           "sel_summary": None, "series_table": [], "series_n": 0,
           "series_json": "null", "peak": None, "view_note": "",
           # season-over-season chart palette (fallback for --season-N)
           "season_colors_json": _script_json(_season_colors())}
    ctx["vintage_rows"] = _vintage_rows(vs)
    if not vs:
        return ctx
    latest = vs[-1]
    try:
        ctx["latest"] = _vintage_summary(
            str(data_mod.vintage_path(latest)), latest)
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
        pv = str(data_mod.vintage_path(sel_v))
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


@app.get("/data", response_class=HTMLResponse)
def data_page(request: Request, loc: str = "", vintage: str = ""):
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(loc, vintage))


# === Storage (/storage, /runs): inventory, delete, clear, reclaim -> runs.html ===
# The sealed records and the hub clone are never deletable (no control, and
# refused again on POST); running/paused trees are refused server-side.
# Every destructive POST requires a confirmation naming exactly what the
# user saw (name or count); a stale confirmation deletes nothing.

@ttlcache.ttl_cache(ttl_s=60.0)
def _tree_size(path: str) -> int:
    from app.core import retro
    return retro.dir_size(Path(path))


def _storage_protected(p: Path) -> bool:
    """True when a path lies inside a sealed record or the hub clone."""
    from flubnf.settings import HUB
    try:
        rp = Path(p).resolve()
    except OSError:
        return True                      # unresolvable: refuse, never guess
    for root in [base for base, _ in _sealed_roots()] + [HUB]:
        try:
            r = Path(root).resolve()
            if rp == r or rp.is_relative_to(r):
                return True
        except OSError:
            continue
    return False


def _live_workroot_ids() -> set:
    """Workroot directory names a worker may be writing into right now."""
    out = set()
    running = _status.get("running") or ""
    if running and ":" in running:
        out.add(running.split(":", 1)[1])
    w = _status.get("workroot")
    if w:
        out.add(Path(w).name)
    return out


def _storage_inventory() -> dict:
    """Storage panel rows with sizes: workroots, live retro seasons, retro
    archives, report archives (each with a busy flag), plus the protected
    trees (no controls). total_bytes/total_h sum the four managed
    categories only."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE, is_research, run_display
    from flubnf.settings import HUB
    inv = {"workroots": [], "retro": [], "retro_archives": [],
           "report_archives": [], "protected": [],
           "total_bytes": 0, "total_h": ""}
    live_ids = _live_workroot_ids()
    console_busy = bool(_status.get("running"))
    # ledger rows label each workroot; one without a row reads as unrecorded
    try:
        led_rows = {r["run_id"]: r for r in Ledger().rows(100_000)}
    except Exception:
        led_rows = {}
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            size = _tree_size(str(p))
            inv["total_bytes"] += size
            row = led_rows.get(p.name) or {}
            disp = run_display(p.name, row.get("spec"),
                               row.get("created_utc"))
            inv["workroots"].append({
                "id": p.name, "size_h": retro.human_bytes(size),
                "label": disp["what"], "when": disp["when"],
                "scope": disp["scope"], "recorded": disp["recorded"],
                "research": is_research(row.get("spec", "")),
                "busy": p.name in live_ids})
    if RETRO_ROOT.is_dir():
        for p in sorted(RETRO_ROOT.iterdir()):
            if not p.is_dir() and not p.is_symlink():
                continue
            if _valid_season(p.name):
                st = _season_status(p.name)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro"].append({
                    "id": p.name, "size_h": retro.human_bytes(size),
                    "status": st, "busy": st in _RETRO_ACTIVE})
                continue
            m = _re.match(r"(\d{4}-\d{2})", p.name)
            if m and retro.archive_stamp_of(p.name, m.group(1)):
                season = m.group(1)
                stamp = retro.archive_stamp_of(p.name, season)
                size = _tree_size(str(p))
                inv["total_bytes"] += size
                inv["retro_archives"].append({
                    "id": p.name, "season": season,
                    "when": retro.stamp_human(stamp),
                    "size_h": retro.human_bytes(size),
                    "busy": _season_status(season) in _RETRO_ACTIVE})
    arch = APP_STATE / "archive"
    for d in reversed(_scan_archive_dates(arch)):
        size = _tree_size(str(arch / d))
        inv["total_bytes"] += size
        inv["report_archives"].append({
            "id": d, "size_h": retro.human_bytes(size),
            "busy": console_busy})
    for label, p in (("Production engine record", RETRO_RESEAL),
                     ("Sealed validation record", RETRO_SEAL),
                     ("FluSight hub clone", HUB)):
        if Path(p).exists():
            inv["protected"].append({
                "label": label, "path": str(p),
                "size_h": retro.human_bytes(_tree_size(str(p)))})
    inv["total_h"] = retro.human_bytes(inv["total_bytes"])
    return inv


def _clearable_workroots() -> list:
    """[{"id", "bytes"}] newest first: every workroot except the active
    run's and anything inside a protected tree."""
    from app.core.runs import APP_STATE
    live = _live_workroot_ids()
    out = []
    wr = APP_STATE / "workroots"
    if wr.is_dir():
        for p in sorted((d for d in wr.iterdir() if d.is_dir()),
                        key=lambda d: d.name, reverse=True):
            if p.name in live or _storage_protected(p):
                continue
            out.append({"id": p.name, "bytes": _tree_size(str(p))})
    return out


def _clearable_run_ids(ledger) -> list:
    """Ledger run ids the clear control may remove: all but the active
    run's row."""
    live = _status.get("running") or ""
    out = []
    for r in ledger.rows(100_000):
        rid = r.get("run_id") or ""
        if r.get("status") == "running" and live.endswith(rid) and rid:
            continue
        out.append(rid)
    return out


@app.get("/storage", response_class=HTMLResponse)
@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    """Storage tab: storage panel, then the run ledger. /runs is a kept
    alias (old reports and bookmarks link it)."""
    from app.core.runs import APP_STATE, is_research
    from app.core import retro
    ledger = Ledger()
    rows = ledger.rows(50)
    for r in rows:
        # the research badge carries the tag, so the label stays untagged
        r["label"] = _run_label(r["run_id"], r.get("spec", ""), tag=False)
        r["research"] = is_research(r.get("spec", ""))
        r["chips"] = _outcome_chips(r.get("outcome", ""))
        # a 'running' row with no live worker = the app was closed mid-run
        if r["status"] == "running" and not (_status.get("running") or "").endswith(r["run_id"]):
            r["status"] = "interrupted"
        # a deleted workroot keeps its row and shows a dash for disk use
        w = APP_STATE / "workroots" / r["run_id"]
        r["disk_h"] = (retro.human_bytes(_tree_size(str(w)))
                       if w.is_dir() else None)
    cw = _clearable_workroots()
    return templates.TemplateResponse(request, "runs.html", {
        "active": "Storage", "ledger": rows,
        "clear_count": len(_clearable_run_ids(ledger)),
        "storage": _storage_inventory(),
        # clear-all: count and weight, named by the confirmation
        "clear_workroots": {"count": len(cw),
                            "size_h": retro.human_bytes(
                                sum(w["bytes"] for w in cw))}})


@app.post("/runs/clear")
def runs_clear(request: Request, confirm: str = Form("")):
    """Clear every completed ledger row (confirmation = the count seen).
    Never the active run's row; never deletes workroot data on disk."""
    _invalidate_scans()
    ledger = Ledger()
    ids = _clearable_run_ids(ledger)
    if not ids:
        _flash("The run ledger has no completed rows to clear.")
        return _back(request, "/storage")
    if confirm != str(len(ids)):
        _flash("The ledger changed since this page was rendered "
               f"({len(ids)} clearable row{'' if len(ids) == 1 else 's'} "
               "now). Nothing was cleared; review and confirm again.")
        return _back(request, "/storage")
    n = ledger.delete_runs(ids)
    _invalidate_scans()
    _flash(f"Cleared {n} completed row{'' if n == 1 else 's'} from the run "
           "ledger. No data on disk was deleted: the runs' workroots stay "
           "in the storage panel until deleted there.")
    return _back(request, "/storage")


def _storage_target(kind: str, ident: str):
    """(path, busy_reason) for one storage delete request, after all
    validation EXCEPT the confirmation; (None, message) when refused."""
    import re as _re
    from app.core import retro
    from app.core.runs import APP_STATE
    if kind == "workroot":
        if not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", ident or ""):
            return None, "Unrecognized workroot name."
        p = APP_STATE / "workroots" / ident
        if ident in _live_workroot_ids():
            return None, (f"The run {ident} is active; its workroot cannot "
                          "be deleted while it runs.")
        base = APP_STATE / "workroots"
    elif kind == "retro-season":
        if not _valid_season(ident):
            return None, "Unrecognized season name."
        if _season_status(ident) in _RETRO_ACTIVE:
            return None, (f"{ident} is replaying (status: "
                          f"{_season_status(ident)}); stop it first.")
        p = RETRO_ROOT / ident
        base = RETRO_ROOT
    elif kind == "retro-archive":
        m = _re.match(r"(\d{4}-\d{2})", ident or "")
        stamp = (retro.archive_stamp_of(ident, m.group(1)) if m else "")
        if not stamp:
            return None, "Unrecognized archived run identifier."
        season = m.group(1)
        if _season_status(season) in _RETRO_ACTIVE:
            return None, (f"{season} is replaying; stop it before deleting "
                          "its archived runs.")
        p = RETRO_ROOT / ident
        base = RETRO_ROOT
    elif kind == "report-archive":
        if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", ident or ""):
            return None, "Unrecognized report archive date."
        if _status.get("running"):
            return None, ("A console run is in progress and may be writing "
                          "the archive; stop it first.")
        p = APP_STATE / "archive" / ident
        base = APP_STATE / "archive"
    else:
        return None, "Unrecognized storage kind."
    # Containment by construction (separator-free identifiers). Not resolved
    # here: a symlinked season is legitimate (delete_tree removes the link),
    # but _storage_protected resolves, so a link into a protected tree fails.
    assert p.parent == Path(base), "storage target escaped its parent"
    if _storage_protected(p):
        return None, ("That tree is protected (the sealed validation "
                      "record and the hub clone are never deletable from "
                      "the interface).")
    if not (p.is_dir() or p.is_symlink()):
        return None, "Nothing is on disk under that name."
    return p, ""


@app.post("/storage/delete")
def storage_delete(request: Request, kind: str = Form(""),
                   ident: str = Form(""), confirm: str = Form("")):
    """Delete one storage entry permanently: validate, refuse busy or
    protected, then require the confirmation to name the entry."""
    from app.core import retro
    _invalidate_scans()
    p, why = _storage_target(kind, ident)
    if p is None:
        _flash(f"{why} Nothing was deleted.")
        return _back(request, "/storage")
    if confirm != ident:
        _flash("The deletion was not confirmed, so nothing was deleted.")
        return _back(request, "/storage")
    size_h = retro.human_bytes(retro.dir_size(p))
    try:
        retro.delete_tree(p)
    except Exception as e:
        _flash(f"Could not delete {ident}: {type(e).__name__}: "
               f"{str(e)[:160]}. Nothing else changed.")
        return _back(request, "/storage")
    _invalidate_scans()
    noun = {"workroot": "workroot", "retro-season": "retrospective season",
            "retro-archive": "archived retrospective run",
            "report-archive": "report archive"}.get(kind, "entry")
    tail = (" Its ledger row remains as the run's record."
            if kind == "workroot" else "")
    _flash(f"Deleted the {noun} {ident}: {size_h} freed.{tail}")
    return _back(request, "/storage")


@app.post("/storage/clear-workroots")
def storage_clear_workroots(request: Request, confirm: str = Form("")):
    """Delete every completed run's workroot (confirmation = the count
    seen). Live/protected checks repeat per directory; ledger rows stay."""
    from app.core import retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    items = _clearable_workroots()
    if not items:
        _flash("No completed run workroots are on disk to delete.")
        return _back(request, "/storage")
    if confirm != str(len(items)):
        _flash("The storage panel changed since this page was rendered "
               f"({len(items)} deletable workroot"
               f"{'' if len(items) == 1 else 's'} now). Nothing was "
               "deleted; review and confirm again.")
        return _back(request, "/storage")
    live = _live_workroot_ids()
    freed, n = 0, 0
    for it in items:
        p = APP_STATE / "workroots" / it["id"]
        # re-checked: a run claimed since the render keeps its workroot
        if it["id"] in live or _storage_protected(p) \
                or not (p.is_dir() or p.is_symlink()):
            continue
        try:
            size = retro.dir_size(p)
            retro.delete_tree(p)
            freed += size
            n += 1
        except Exception:
            continue          # one stuck tree must not sink the sweep
    _invalidate_scans()
    _flash(f"Deleted {n} completed run workroot{'' if n == 1 else 's'}: "
           f"{retro.human_bytes(freed)} freed. Every ledger row is kept "
           "and shows a dash for disk use.")
    return _back(request, "/storage")


# === Storage: reclaim (prune completed intermediates, compress samples) ===
# GET is a dry run by category; POST performs it behind a counts
# confirmation. Classification lives in app/core/reclaim.py; samples gzip
# losslessly with mtimes kept, so every score and export is reproducible.

def _reclaim_skips() -> tuple:
    """(season entry names, workroot names) the reclaim must not touch right
    now: seasons replaying or mid-finalize, and the active run's workroot."""
    skip_seasons = {s for s in _known_seasons()
                    if _season_status(s) in _RETRO_ACTIVE}
    for key, job in list(_results_jobs.items()):
        if job and not job["done"].is_set():
            skip_seasons.add(Path(key).name)
    return skip_seasons, set(_live_workroot_ids())


def _reclaim_survey() -> dict:
    from app.core import reclaim
    from app.core.runs import APP_STATE
    skip_seasons, skip_workroots = _reclaim_skips()
    return reclaim.survey(RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)


@app.get("/api/storage/reclaim")
def api_storage_reclaim():
    """Dry run: what a reclaim would free, by category (no side effects).
    'confirm' must match storage_reclaim's counts token."""
    from app.core import retro
    plan = _reclaim_survey()
    hb = retro.human_bytes
    cats = []
    if plan["week_bytes"]:
        cats.append({
            "label": "Completed-week fit intermediates",
            "bytes": plan["week_bytes"], "bytes_h": hb(plan["week_bytes"]),
            "detail": (f"{plan['weeks']} completed weeks across "
                       f"{len(plan['season_ids'])} season "
                       f"tree{'' if len(plan['season_ids']) == 1 else 's'}")})
    if plan["workroot_bytes"]:
        cats.append({
            "label": "Completed-run workroot intermediates",
            "bytes": plan["workroot_bytes"],
            "bytes_h": hb(plan["workroot_bytes"]),
            "detail": (f"{plan['workroots']} completed "
                       f"run{'' if plan['workroots'] == 1 else 's'}; "
                       "results, reports, and submissions are kept")})
    if plan["compress_files"]:
        cats.append({
            "label": "Stored-sample compression (lossless gzip)",
            "bytes": plan["est_compress_saved"],
            "bytes_h": hb(plan["est_compress_saved"]),
            "detail": (f"{plan['compress_files']} stored weeks, "
                       f"{hb(plan['compress_bytes'])} now; estimated "
                       f"{hb(plan['est_compress_saved'])} freed, every week "
                       "stays scoreable and playable")})
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    return {"categories": cats, "total": plan["total_est"],
            "total_h": hb(plan["total_est"]), "confirm": counts}


@app.post("/storage/reclaim")
def storage_reclaim(request: Request, confirm: str = Form("")):
    """Perform the reclaim the dry run described (confirmation = its
    weeks/workroots/files counts). Busy and protection rules re-apply per
    entry."""
    from app.core import reclaim, retro
    from app.core.runs import APP_STATE
    _invalidate_scans()
    plan = _reclaim_survey()
    counts = f"{plan['weeks']}/{plan['workroots']}/{plan['compress_files']}"
    if plan["total_est"] <= 0 and plan["compress_files"] == 0:
        _flash("There is nothing to reclaim: no completed week or run "
               "carries intermediates and every stored week is already "
               "compressed.")
        return _back(request, "/storage")
    if confirm != counts:
        _flash("The storage panel changed since this report was made "
               "(a run finished or files moved). Nothing was deleted; "
               "review the reclaim report and confirm again.")
        return _back(request, "/storage")
    skip_seasons, skip_workroots = _reclaim_skips()
    out = reclaim.execute(RETRO_ROOT, APP_STATE / "workroots",
                          skip_seasons=skip_seasons,
                          skip_workroots=skip_workroots)
    _invalidate_scans()
    hb = retro.human_bytes
    bits = []
    if out["week_bytes"]:
        bits.append(f"{hb(out['week_bytes'])} of fit intermediates from "
                    f"{out['weeks']} completed week"
                    f"{'' if out['weeks'] == 1 else 's'}")
    if out["workroot_bytes"]:
        bits.append(f"{hb(out['workroot_bytes'])} from "
                    f"{out['workroots']} completed run workroot"
                    f"{'' if out['workroots'] == 1 else 's'}")
    if out["compress_files"]:
        bits.append(f"{hb(out['compress_saved'])} by compressing "
                    f"{out['compress_files']} stored week"
                    f"{'' if out['compress_files'] == 1 else 's'} in place")
    _flash(f"Reclaimed {hb(out['total'])}: " + "; ".join(bits) + ". Every "
           "stored week, score, report, and submission file is kept; the "
           "sealed validation record and the hub clone were not touched.")
    return _back(request, "/storage")


# === Console controls: /run/stop, /api/busy, /data/pull, /freshness ===
@app.post("/run/stop")
def run_stop():
    _invalidate_scans()
    w = _status.get("workroot")
    running = _status.get("running") or ""
    if w and running:
        (Path(w) / "STOP").touch()
        if (Path(w) / "pf2s").is_dir():        # the two-strain pass polls its
            (Path(w) / "pf2s" / "STOP").touch()  # own subdir for the flag
        _status["phase"] = "stopping…"
    elif running == "starting" and not w:
        # a claim with no worker behind it: release it so the console unwedges
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _status["phase"] = ""
    return RedirectResponse("/forecast#results", status_code=303)


@app.get("/api/busy")
def api_busy():
    """What would a click interrupt now? console_run: the running run's
    label (null when idle); retro: {season: status} for running, stopping
    or paused seasons (paused still holds the engine); phase: the console
    phase (the Update-data guard fires only on 'materializing'/'preparing',
    which read hub files). Seasons come from claims AND on-disk records, so
    a live replay never reads idle."""
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
    ok, msg = data_mod.pull_hub()
    _invalidate_scans()
    if not ok:
        _flash("Updating the hub clone FAILED: "
               + (msg[:200] or "git exited nonzero with no message")
               + ". The local archive is unchanged; check the network and "
               "the hub clone, then try again.")
        return RedirectResponse("/data", status_code=303)
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
    return templates.TemplateResponse(request, "data.html",
                                      _data_context(freshness=f))


# === Request helpers ===
def _phase(msg):
    _status["phase"] = msg


def _flash(msg: str) -> None:
    """Notice for the next page the user sees (also appended to the log).
    Unconsumed messages join rather than overwrite."""
    prev = _status.get("flash")
    _status["flash"] = f"{prev}  {msg}" if prev and msg not in prev else msg
    _status["log"].append(msg)


def _back(request: Request, fallback: str) -> RedirectResponse:
    """Redirect back to the posting page (validated local path)."""
    from urllib.parse import urlsplit
    path = urlsplit(request.headers.get("referer", "")).path
    ok = path.startswith("/") and not path.startswith("//")
    return RedirectResponse(path if ok else fallback, status_code=303)


# === Forecast pipeline: param harvest, sleep guard, weekly report, _run_all ===
def _harvest_params(workroot: Path) -> dict:
    """Per-location posterior medians of the fitted PF parameters, pooled
    across replicates (params_*.txt under each cell's out/Results/PF/Runs),
    stored as results.json 'params'. Unreadable cells are skipped."""
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
            runs = Path(c["dir"]) / "out" / "Results" / "PF" / "Runs"
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


# SetThreadExecutionState flags: CONTINUOUS persists until cleared (clear =
# CONTINUOUS alone); SYSTEM_REQUIRED blocks idle sleep (caffeinate -i).
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class _WinSleepGuard:
    """Windows sleep inhibitor with Popen's .terminate(). The flag is
    thread-affine: create and terminate on the same worker thread."""

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
    """Keep the machine awake during a long run: macOS `caffeinate -i -w
    <pid>`, Windows _windows_sleep_guard. Returns an object with
    .terminate(), or None elsewhere or on failure (no run depends on it)."""
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


def _write_weekly_report(spec, workroot: Path, pf_samples: dict, obs: dict,
                         df, locs, n2f: dict, elapsed_s: float,
                         outcome: dict, an_q: dict | None = None,
                         ens_q: dict | None = None) -> None:
    """Step 5b of _run_all: build the report inputs bundle, save it as
    report_inputs.json, then render report.html FROM it (one render path,
    so _report_for_serving can rebuild after a design change).

    Map cards for every model (pf reduced to the 23-level grid; an_q =
    Groundhog quantiles, loc -> horizon -> {level: value}) come from the
    one quantile-CDF path; the map renders PF-first and cards_model records
    which. State drill-down fans are PF's. `ens_q` (retired blend) is
    accepted and ignored. Mutates `outcome`; the caller contains failures."""
    import json as _json
    from datetime import date as _dd
    from datetime import timedelta as _tdd

    import numpy as _np
    import pandas as pd

    from app.core import ensemble as _ens
    from app.core import report_v2
    from app.core.report import (categorical_probs,
                                 categorical_probs_from_quantiles)
    from app.core.report_v2 import CATS
    from app.core.scoring import summary_table_html
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    # cells.json is read only when there are fitted samples
    cells = (_json.loads((workroot / "cells.json").read_text())
             if pf_samples else [])
    ens_q = ens_q or {}
    an_q = an_q or {}
    # PF on the members' 23-level grid, so its cards use the same CDF path
    pf_q = {loc: _ens.member_quantiles_from_samples(s)
            for loc, s in pf_samples.items()}

    def _last_obs(loc):
        o = obs.get(loc) or []
        if o:
            return float(o[-1][1])
        for c in cells:               # degraded runs: cells.json still
            if c.get("location") == loc:  # knows the anchor value
                return float(c.get("last_observed", 0.0))
        return None

    def _q1_of(qd):
        q1 = (qd or {}).get("0", (qd or {}).get(0))   # one week ahead
        return q1 if isinstance(q1, dict) and q1 else None

    def _q_cards(q_by_loc):
        """abbr -> hover card from ONE model's quantiles."""
        out = {}
        for loc, qd in (q_by_loc or {}).items():
            q1 = _q1_of(qd)
            lo = _last_obs(loc)
            if q1 is None or lo is None or loc not in n2a:
                continue
            probs = categorical_probs_from_quantiles(
                q1, lo, int(n2p.get(loc, 0)), 0)
            if not probs:
                continue
            med1 = float(min(q1.items(),
                             key=lambda kv: abs(float(kv[0]) - 0.5))[1])
            # hover_html reaches innerHTML: escape the name
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>current: {lo:.0f}"
                     f"<br>1-wk median: {med1:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: "
                                 f"{probs.get(c,0):.0%}" for c in CATS))
            out[n2a[loc]] = {"probs": probs, "name": loc,
                             "abbr": n2a[loc], "fips": n2f.get(loc, ""),
                             "hover_html": hover}
        return out

    def _q_nat_card(q_by_loc):
        """The national card from the SAME model's quantiles (never
        cross-filled from another member)."""
        us_names = [n for n in (q_by_loc or {}) if n2f.get(n) == "US"] or \
                   [n for n in (q_by_loc or {})
                    if "US" in n or "national" in n.lower()]
        un = us_names[0] if us_names else None
        q1 = _q1_of((q_by_loc or {}).get(un)) if un else None
        lo_us = _last_obs(un) if un else None
        if q1 is None or lo_us is None:
            return None
        probs_us = categorical_probs_from_quantiles(
            q1, lo_us, 340_000_000, 0)
        if not probs_us:
            return None
        med_us = float(min(q1.items(),
                           key=lambda kv: abs(float(kv[0]) - 0.5))[1])
        hover_us = ("<b>United States</b><br>current: "
                    f"{lo_us:.0f}<br>1-wk median: {med_us:.0f}")
        return {"probs": probs_us, "name": "United States",
                "abbr": "US", "fips": "US", "hover_html": hover_us}

    cards_by_model = {}
    nat_cards = {}
    for model, q_by_loc in (("pf", pf_q), ("analogue", an_q)):
        c = _q_cards(q_by_loc)
        if c:
            cards_by_model[model] = c
            nc = _q_nat_card(q_by_loc)
            if nc:
                nat_cards[model] = nc
    # PF colors the rendered map; the toggle offers the Groundhog
    cards_model = next((m for m in ("pf", "analogue")
                        if m in cards_by_model), "pf")
    cards = dict(cards_by_model.get(cards_model, {}))
    for name, abbr in n2a.items():
        cards.setdefault(abbr, {"name": name, "abbr": abbr,
                                "fips": n2f.get(name, "")})
    wis_html = ("<div class='card'><h2>forecast accuracy "
                "(retrospective)</h2>" + summary_table_html(df)
                + "</div>")
    # settled outcomes for backdated runs: the LATEST vintage's values
    # past the forecast origin, framed to the 4-week horizon
    settled_by_loc = {}
    try:
        _vs_all = data_mod.vintages()
        if _vs_all and _vs_all[-1] > spec.forecast_date:
            _lim = (_dd.fromisoformat(spec.forecast_date)
                    + _tdd(days=28)).isoformat()
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
    # state pages as DATA; render_bundle draws the figures
    details = {}
    for loc, s in pf_samples.items():
        fips_l = n2f.get(loc, "")
        obs_pairs = (obs.get(loc) or [])[-12:]
        o_t = [d for d, _ in obs_pairs]
        o_v = [v for _, v in obs_pairs]
        _base = (_dd.fromisoformat(o_t[-1]) if o_t
                 else _dd.fromisoformat(spec.forecast_date))
        # canonical horizons: hub label h is h+1 weeks past the anchor
        f_t = [(_base + _tdd(days=7 * (h + 1))).isoformat()
               for h in (0, 1, 2, 3)]
        samples_h = {f_t[h]: s[str(h)] for h in (0, 1, 2, 3)}
        try:
            q_by_t = report_v2.fan_quantiles(f_t, samples_h)
            lo_l = o_v[-1] if o_v else 0.0
            # one week ahead = canonical "0", matching the fan above
            probs_l = categorical_probs(
                _np.asarray(s["0"], float), lo_l,
                int(n2p.get(loc, 1e6)), 1)
            key = "US" if fips_l == "US" else n2a.get(loc, loc)
            meds = [q_by_t[t]["0.5"] for t in f_t]
            note = ("Off-season: the model finds no sustained "
                    "transmission. This forecast reflects the recent "
                    "reporting background, not epidemic growth."
                    if max(meds) <= 2 else "")
            details[key] = {
                "name": "United States" if fips_l == "US" else loc,
                "note": note,
                "fan": {"observed_times": o_t, "observed": o_v,
                        "forecast_times": f_t, "quantiles": q_by_t,
                        "title": f"{loc}: weekly admissions",
                        "settled": settled_by_loc.get(loc)},
                "cat_probs": probs_l,
                "table_rows": [(d, v) for d, v in obs_pairs[-6:]]}
        except Exception:
            continue
    # national card from the same model as the rendered state cards
    nat_card = nat_cards.get(cards_model)
    bundle = {"version": report_v2.BUNDLE_VERSION,
              "reference_date": spec.forecast_date,
              # v2: which model computed the map cards
              "cards_model": cards_model,
              "cards": cards, "details": details,
              # v4: states this run covered (reporting gap vs never fitted)
              "fitted_fips": sorted({n2f.get(l) for l in spec.locations
                                     if n2f.get(l) and n2f.get(l) != "US"}),
              # v3: every model's cards (the outlook toggle's data)
              "cards_by_model": cards_by_model,
              "national_map_cards": nat_cards,
              "national": {"summary_html": wis_html},
              "national_map_card": nat_card,
              "elapsed_s": elapsed_s,
              # run settings, app build and engine versions
              "settings_html": settings_html(
                  spec_settings(spec)
                  + version_pairs(RUNNING_SHA, VERSIONS))}
    try:
        bp = report_v2.save_bundle(bundle, workroot)
        outcome["report_inputs_bytes"] = bp.stat().st_size
    except Exception as e:    # the report is never hostage to its bundle
        outcome["report_inputs_error"] = str(e)[:200]
    report_v2.render_bundle(bundle, workroot / "report.html")
    outcome["report"] = str(workroot / "report.html")


def _pf_engine_state() -> str:
    """This machine's PF engine in one word:

      absent   no engine venv/fork: analogue-only Tier A, the run proceeds
      broken   venv + fork path but no pybnf/pf.py: every fit would fail
      ready    the fork provides fit_type = pf

    Installed-ness is defined once, in app.core.engines.pf.engine_available.
    """
    from flubnf.settings import PY_ENGINE, PYBNF
    from app.core.engines import pf as pf_engine
    if not (PY_ENGINE.exists() and PYBNF.exists()):
        return "absent"
    return "ready" if pf_engine.engine_available() else "broken"


def _run_all(spec: RunSpec) -> None:
    """The competition path: engines in ascending cost, then the two
    standalone submissions (no blend; each under its own hub identity,
    submit.MODEL_ABBR), scoring and the weekly report. One workroot, one
    ledger row."""
    import pandas as pd
    from app.core import scoring
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.submit import (hub_model_id, quantile_rows,
                                 rows_from_quantiles, write_submission)

    import time as _time
    ledger = Ledger()
    run_id = None
    outcome = {}
    guard = _sleep_guard()          # macOS: no idle sleep mid-run
    # the route starts the clock on click; direct calls (scripts, tests) here
    if not _status.get("started_utc"):
        _status["started_utc"] = _time.time()
    t_start = float(_status["started_utc"])
    n_states = sum(1 for l in spec.locations
                   if str(l).upper() not in ("US", "US (NATIONAL)"))
    _status["run_label"] = (
        f"{spec.forecast_date} · {n_states} state(s) + US"
        if n_states < len(spec.locations)
        else f"{spec.forecast_date} · {len(spec.locations)} location(s)")
    # also set by the route; here so direct calls are described too
    _status["settings"] = spec_settings(spec)
    try:
        # setup INSIDE the try so a failed insert/lease releases the claim;
        # the row's engine_versions (not this process's) is "Produced by"
        run_id = ledger.open_run(spec, Path("pending"),
                                 _engine_versions_for_ledger("pf,analogue"))
        workroot = lease_workroot(run_id)
        ledger.set_workroot(run_id, workroot)   # the row must name the real one
        _status["running"] = f"all:{run_id}"
        _status["workroot"] = str(workroot)
        # 1. PF (primary); absent on Tier-A machines, where the run proceeds
        # with the analogue (see _pf_engine_state)
        fails = {}
        # observed admissions per location (vintage-true): floor, report, run page
        obs = {}
        try:
            from flubnf.settings import LOCATIONS as _LOCCSV
            from app.core.data import vintage_path as _vpo
            _lo = pd.read_csv(_LOCCSV, dtype=str)
            _n2fo = dict(zip(_lo.location_name, _lo.location.str.zfill(2)))
            tdf = pd.read_csv(_vpo(spec.forecast_date),
                              dtype={"location": str})
            tdf["location"] = tdf["location"].str.zfill(2)
            # nowcast rule: the engines treat the same-day row as unreported,
            # so obs must not see it (else cards announce a spurious surge)
            if getattr(spec, "drop_same_day", False):
                tdf = tdf[tdf["date"].astype(str).str[:10]
                          != str(spec.forecast_date)]
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
        pf_wanted = spec.engine in ("all", "pf")
        pf_state = _pf_engine_state()
        # A broken install is refused, not skipped: an analogue-only ship
        # would hide the fault. The reason is recorded so the run page names
        # the path and the fix.
        if pf_wanted and pf_state == "broken":
            msg = pf_engine.engine_missing_message()
            outcome["pf_engine_broken"] = msg
            raise RuntimeError(msg)
        if pf_wanted and pf_state == "ready":
            _phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            _phase(f"filtering {len(spec.locations)} location(s) × "
                   f"{spec.replicates} replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            pf_samples = pf_engine.collect(workroot)
            # the Oracle step (app/core/oracle.py), before anything downstream
            # and before the floor. oracle = none is research: file withheld
            # in step 4, oracle.json records the step did not run.
            from app.core import oracle as oracle_mod
            if oracle_mod.wanted(spec.extra):
                _phase("the Oracle step: the donor bank from the vintage")
                pf_raw = pf_samples
                pf_samples, oprov = oracle_mod.apply_week(
                    pf_raw, spec.forecast_date, workroot, extra=spec.extra,
                    weeks_to_drop=int(spec.weeks_to_drop or 0),
                    drop_same_day=bool(getattr(spec, "drop_same_day", False)))
                outcome["oracle"] = oprov["bank"]["label"]
                try:
                    oracle_mod.write_filter_record(workroot, spec.forecast_date,
                                                   pf_raw)
                except Exception:
                    pass      # the kept copy is a courtesy; the member stands
            else:
                oracle_mod.write_not_applied(
                    workroot, spec.forecast_date,
                    "the run asked for the plain filter (oracle = none)")
                outcome["oracle"] = "none"
            try:
                params["pf"] = _harvest_params(workroot)
            except Exception:
                pass
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
        # 1b. RESEARCH third member: the two-strain SIHRS (members=3, no UI
        # control), in a pf2s subdir of the same workroot (one row, one archive)
        pf2s_samples = {}
        if ((spec.extra or {}).get("members") == 3
                and pf_wanted and pf_state == "ready"):
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
        # 2. the Groundhog: calendar analogue + the aux donors _run_extra put
        # in spec.extra (none = research bare analogue). Always runs (instant);
        # its FILE is written only when the run asked for it.
        _phase("consulting the Groundhog")
        from app.core.floor import floor_quantiles
        an_q = {loc: floor_quantiles(q)
                for loc, q in an_engine.run(spec).items()}
        outcome["analogue_aux"] = str(
            (spec.extra or {}).get("analogue_aux") or "")
        # 3. no blend: each member is its own submission; PF failures are just
        # absent from its file (the row's failure count names them)
        _phase("writing submissions")
        # 4. submissions (identity in the path)
        locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
        subs = {}
        # model keys are submit.MODEL_ABBR's (model-output/<team>-<model>/);
        # the writer refuses a file date its rows do not carry
        from app.core.runs import is_research as _is_research
        _research = _is_research(spec)

        def _withhold(reason: str) -> None:
            # one outcome key, every withheld file named in it
            prior = outcome.get("submission_withheld")
            outcome["submission_withheld"] = (f"{prior}; {reason}" if prior
                                              else reason)
        for model, rows in (
            ("pf", [r for loc, s in pf_samples.items()
                    for r in quantile_rows(s, n2f[loc], spec.forecast_date)]),
            ("analogue", [r for loc, q in an_q.items()
                          for r in rows_from_quantiles(q, n2f[loc],
                                                       spec.forecast_date)]),
        ):
            if not rows:
                continue
            if model == "analogue" and spec.engine == "pf":
                # Oracle SIHRS-only run: Groundhog consulted for pages only
                continue
            if model == "analogue" and not (spec.extra or {}).get("aux_pools"):
                # bare analogue is research: no hub-named file (audit rr-1)
                _withhold(
                    "Groundhog: the run carried no auxiliary donors, so "
                    "this is the bare calendar analogue and does not ship "
                    "under the Groundhog's hub name")
                continue
            if model == "pf" and outcome.get("oracle") == "none":
                # plain filter is research too: no hub-named file
                _withhold(
                    "Oracle SIHRS: the run asked for the plain filter "
                    "(oracle = none), a research configuration that does "
                    "not ship under the Oracle SIHRS hub name")
                continue
            # contained per model: a writer refusal (rows the hub would
            # bounce) costs that file, never the run; recorded for the run page
            try:
                subs[hub_model_id(model)] = str(write_submission(
                    rows, model, spec.forecast_date,
                    workroot / "submission"))
            except Exception as e:
                outcome.setdefault("submission_errors", {})[
                    hub_model_id(model)] = str(e)[:400]
        outcome["submissions"] = subs
        # 5. retrospective scoring (once truth exists); contained, like 5b
        df = pd.DataFrame()
        try:
            truth, name2fips = scoring.load_truth()
            df = scoring.score_samples(pf_samples, spec.forecast_date,
                                       name2fips, truth)
            # stamp the truth source now: a later load_truth elsewhere could
            # swap the module global before the WIS card renders
            df.attrs["truth_source"] = scoring.TRUTH_SOURCE
            if not df.empty:
                # POOLED_INCLUDES_US gate (us_national.pooled_frame): the fitted
                # US cell is the sum of the others and would dominate
                from app.core.us_national import pooled_frame
                pdf = pooled_frame(df)
                if not pdf.empty:
                    outcome["pf_relwis"] = round(
                        float(pdf["wis"].sum() / pdf["base_wis"].sum()), 3)
                    outcome["pf_relwis_cells"] = int(len(pdf))
            df.to_json(workroot / "scores_pf.json")
            # the Groundhog, same formula and gate
            from app.core.us_national import pooled_frame as _pooled
            for mname, qs in (("analogue", an_q),):
                try:
                    mdf = scoring.score_quantiles(qs or {}, spec.forecast_date,
                                                  name2fips, truth)
                    if not mdf.empty:
                        mp = _pooled(mdf)
                        if not mp.empty:
                            outcome[f"{mname}_relwis"] = round(
                                float(mp["wis"].sum() / mp["base_wis"].sum()), 3)
                            outcome[f"{mname}_relwis_cells"] = int(len(mp))
                        mdf.to_json(workroot / f"scores_{mname}.json")
                except Exception as e:
                    outcome[f"{mname}_score_error"] = str(e)[:200]
        except Exception as e:
            outcome["score_error"] = str(e)[:200]
        # 5b. weekly report from its inputs bundle; contained
        try:
            _write_weekly_report(spec, workroot, pf_samples, obs, df, locs,
                                 n2f, _time.time() - t_start, outcome,
                                 an_q=an_q)
        except Exception as e:
            outcome["report_error"] = str(e)[:200]
        # 6. results index for the run page
        import json as _json
        import numpy as _np
        from app.core import horizons as _hz
        def _qs_from_samples(s):
            out = {}
            for h in _hz.HORIZONS:
                a = _np.asarray(s.get(h, []), float); a = a[_np.isfinite(a)]
                if a.size:
                    out[h] = {q: float(_np.quantile(a, float(q)))
                              for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
            return out
        def _qs_from_q(qd):
            return {h: {q: qd[h][float(q)]
                        for q in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                    for h in qd}
        from app.core.horizons import models_to_stored as _hz_stored
        import os as _os
        _tmp = workroot / "results.json.tmp"
        _tmp.write_text(_json.dumps({
            "spec": spec.to_json(), "forecast_date": spec.forecast_date,
            "research": _research,
            # bank as stream@digest8, or "none"; full record in oracle.json
            "oracle": outcome.get("oracle"),
            "observed": obs,
            "params": params,
            # STORED horizon convention (old workroots use it too); readers
            # go through horizons.models_to_canonical
            "models": _hz_stored({
                "pf": {loc: _qs_from_samples(s) for loc, s in pf_samples.items()},
                "analogue": {loc: _qs_from_q(q) for loc, q in an_q.items()},
                **({"pf2s": {loc: _qs_from_samples(s)
                             for loc, s in pf2s_samples.items()}}
                   if pf2s_samples else {}),
            })}))
        _os.replace(_tmp, workroot / "results.json")   # readers never see a half-write
        # 7. forecast archive: one folder per date, latest run wins; only the
        # shipped product's full run archives (audit rr-1)
        if _research:
            outcome["archived"] = "skipped: research run"
        elif spec.engine in ("analogue", "pf"):
            outcome["archived"] = (f"skipped: {'analogue' if spec.engine == 'analogue' else 'Oracle SIHRS'}"
                                   "-only run is not the date's forecast")
        else:
            try:
                outcome["archived"] = _archive_run(workroot, spec.forecast_date)
            except Exception as e:
                outcome["archive_error"] = str(e)[:200]
        # the pipeline completed: fit failures make it "partial" (the chips
        # count them); "failed"/"error" are reserved for runs that died
        ledger.close_run(run_id, "partial" if fails else "ok", outcome)
        # prune per-cell fit trees once the record is on disk; a run with
        # failures keeps them as evidence. Never fatal.
        if not fails:
            try:
                from app.core import reclaim
                reclaim.prune_workroot(workroot)
            except Exception:
                pass
        _status["log"].append(
            f"{run_id}: pf {len(pf_samples)} loc, groundhog {len(an_q)}"
            + (f", pf2s {len(pf2s_samples)}" if pf2s_samples else "")
            + "".join(f", {m} relWIS {outcome[k]}" for m, k in
                      (("pf", "pf_relwis"), ("groundhog", "analogue_relwis"))
                      if k in outcome))
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
        _invalidate_scans()
        _status["running"] = None
        _status["phase"] = ""
        _status["settings"] = []
        _status["workroot"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None


# === Forecast archive and submission files ===
def _archive_run(workroot: Path, forecast_date: str) -> str:
    """Copy the run's deliverables to app/state/archive/<forecast_date>/,
    replacing any earlier archive for the date. Built beside, then swapped:
    a crash mid-copy costs this attempt, never the existing record."""
    import os
    import shutil
    from app.core.report_v2 import BUNDLE_NAME
    from app.core.runs import APP_STATE
    arch = APP_STATE / "archive" / forecast_date
    build = arch.with_name(arch.name + ".building")
    old = arch.with_name(arch.name + ".old")
    arch.parent.mkdir(parents=True, exist_ok=True)
    if build.exists():          # an interrupted attempt's half-built tree
        shutil.rmtree(build)
    if old.exists():
        if arch.exists():       # both present: the old copy is surplus
            shutil.rmtree(old)
        else:                   # crashed between the two renames below:
            os.replace(old, arch)   # the parked previous archive comes back
    build.mkdir(parents=True)
    try:
        # the report travels with its inputs bundle (rebuildable)
        for name in ("results.json", "report.html", BUNDLE_NAME):
            if (workroot / name).is_file():
                shutil.copy2(workroot / name, build / name)
        if (workroot / "submission").is_dir():
            shutil.copytree(workroot / "submission", build / "submission")
    except BaseException:
        shutil.rmtree(build, ignore_errors=True)
        raise
    if arch.exists():
        os.replace(arch, old)   # park the previous archive
    os.replace(build, arch)
    if old.exists():
        shutil.rmtree(old, ignore_errors=True)
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
    """Forecast archive dates for the Output page, cached by directory."""
    from app.core.runs import APP_STATE
    return _scan_archive_dates(APP_STATE / "archive")


def _registered_model_ids() -> set:
    """Hub model identities this project may write (directory names), from
    submit.MODEL_ABBR (checked against model-metadata/ by the suite)."""
    from app.core.submit import MODEL_ABBR, hub_model_id
    return {hub_model_id(k) for k in MODEL_ABBR}


def _submission_files(d: Path) -> list:
    """Submission CSVs under a workroot/archive dir, each marked submittable
    iff its directory (the hub model id) is registered. Retired identities
    (NAU-Ensemble, NAU-PF-SIHRS) stay listed as the run's record but are not
    downloadable: the hub would reject them under genuine-looking names."""
    ok = _registered_model_ids()
    return [{"model": p.parent.name, "name": p.name, "path": str(p),
             "submittable": p.parent.name in ok}
            for p in sorted(Path(d).glob("submission/*/*.csv"))]


# === Run pages (/runs/{id}, report, download, rerun) -> run.html ===
@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    import json as _json
    from app.core.runs import APP_STATE, Ledger
    w = APP_STATE / "workroots" / run_id
    res = {}
    if (w / "results.json").is_file():
        res = _json.loads((w / "results.json").read_text())
    subs = _submission_files(w)
    report = (w / "report.html").name if (w / "report.html").is_file() else None
    status, err, spec_json = "", "", ""
    o = {}
    sub_errors: dict = {}
    pf_failures: dict = {}
    step_errors: dict = {}
    ens_analogue_only: list = []
    ens_withheld = ""
    row_sha, row_engine_versions = "", {}
    for r in Ledger().rows(200):
        if r.get("run_id") == run_id:
            status = r.get("status", "")
            spec_json = r.get("spec", "") or ""
            row_sha = r.get("flubnf_sha", "") or ""
            try:
                ev = _json.loads(r.get("engine_versions") or "{}")
                row_engine_versions = ev if isinstance(ev, dict) else {}
            except Exception:
                row_engine_versions = {}
            try:
                o = _json.loads(r.get("outcome") or "{}")
                err = o.get("error", "")
                sub_errors = o.get("submission_errors", {}) or {}
                # failures and step errors in full (the chips only count them)
                pf_failures = o.get("pf_failures", {}) or {}
                step_errors = {k: str(o[k]) for k in
                               ("score_error", "archive_error",
                                "report_inputs_error", "report_error")
                               if o.get(k)}
            except Exception:
                err = ""
            break
    # a 'running' row with no live worker = the app was closed mid-run
    if status == "running" and not (_status.get("running") or "").endswith(run_id):
        status = "interrupted"
    # settings, build and engine versions all from the ledger row: "Produced
    # by" must never print this process's build. Names-only engine_versions
    # rows yield an app-build-only block (version_pairs omits unknowns).
    from app.core.runs import is_research
    return templates.TemplateResponse(request, "run.html", {
        "active": "Storage", "run_id": run_id, "status": status, "error": err,
        "results": results_html(o, spec_json),
        # the page shows a research badge, so the label stays untagged
        "label": _run_label(run_id, spec_json, tag=False),
        "research": is_research(spec_json),
        "models": res.get("models", {}),
        "settings": spec_settings(spec_json),
        "versions": version_pairs(row_sha, row_engine_versions),
        "can_rerun": bool(spec_json) and status in RERUN_STATUSES,
        "pf_failures": pf_failures, "step_errors": step_errors,
        "subs": subs, "sub_errors": sub_errors, "report": report})


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(run_id: str):
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    if not (d / "report.html").is_file():
        return HTMLResponse("<p>no report for this run</p>")
    # rebuilt if stale, as /output/report
    return HTMLResponse(_report_for_serving(d))


@app.get("/runs/{run_id}/report/download")
def run_report_download(run_id: str):
    """Save this run's weekly report, named for the run's forecast date."""
    from app.core.runs import APP_STATE
    d = APP_STATE / "workroots" / run_id
    date = ""
    try:
        import json as _json
        date = _json.loads((d / "results.json").read_text()).get(
            "forecast_date", "")
    except Exception:
        pass                 # no results.json yet: fall back to the run id
    return _weekly_report_file(d, date or run_id)


@app.post("/runs/{run_id}/rerun")
def run_rerun(request: Request, background: BackgroundTasks, run_id: str):
    """Re-run a recorded console run: a FRESH run (no checkpoint) with the
    row's exact spec through the /run path (its vintage and busy checks);
    refuses if that path cannot reproduce the spec verbatim."""
    import json as _json
    from dataclasses import asdict as _asdict
    from datetime import date as _date
    row = next((r for r in Ledger().rows(500)
                if r.get("run_id") == run_id), None)
    try:
        d = _json.loads((row or {}).get("spec") or "")
    except (ValueError, TypeError):
        d = None
    if not isinstance(d, dict) or not d.get("forecast_date"):
        _flash("That run's settings were not recorded, so it cannot be "
               "re-run from here. Set the run up on the Forecast form "
               "instead. Nothing was started.")
        return _back(request, "/forecast")
    members = 3 if (d.get("extra") or {}).get("members") == 3 else 2
    locs = [str(l) for l in (d.get("locations") or [])]
    # aux pools re-run their preset (name before the digest tag); none = bare
    _x = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    aux = (str(_x.get("analogue_aux") or "").split("+", 1)[0]
           if _x.get("aux_pools") else "")
    # likewise a plain-filter row re-runs the plain filter
    oracle = "none" if str(_x.get("oracle") or "") == "none" else None
    # what /run would build, compared field by field with the stored spec
    candidate = RunSpec(
        engine=str(d.get("engine") or ""),
        forecast_date=str(d.get("forecast_date") or ""),
        season_start=str(d.get("season_start") or ""),
        locations=(locs if any(l.upper() in ("US", "US (NATIONAL)")
                               for l in locs) else locs + ["US"]),
        weeks_to_drop=int(d.get("weeks_to_drop") or 0),
        weeks_to_nowcast=int(d.get("weeks_to_nowcast") or 0),
        # pre-nowcast-rule rows kept the same-day week: reproduce, not default
        drop_same_day=bool(d.get("drop_same_day", False)),
        replicates=int(d.get("replicates") or 3),
        particles=int(d.get("particles") or 10_000),
        extra=_run_extra(members, _spec_mode(d), aux, oracle))
    # a row recorded before the mode existed reads as a real-time run
    if isinstance(d.get("extra"), dict):
        d["extra"].setdefault("mode", "realtime")
    else:
        d["extra"] = {"mode": "realtime"}
    recon = _asdict(candidate)
    off = [k for k in sorted(d) if recon.get(k) != d[k]]
    try:
        if _date.fromisoformat(candidate.forecast_date).weekday() != 5:
            off.append("forecast_date")   # /run would snap it: not verbatim
    except ValueError:
        off.append("forecast_date")
    if not (1_000 <= candidate.particles <= 100_000):
        off.append("particles")           # /run would clamp it: not verbatim
    if off:
        _flash("This run's recorded settings cannot be reproduced from the "
               "console path (" + ", ".join(dict.fromkeys(off)) + " differ "
               "from what the form would run), so nothing was started. "
               "Re-run it from a script using its ledger row.")
        return _back(request, "/forecast")
    return run_models(request, background,
                      forecast_date=candidate.forecast_date,
                      locations=locs,
                      weeks_to_drop=candidate.weeks_to_drop,
                      weeks_to_nowcast=candidate.weeks_to_nowcast,
                      replicates=candidate.replicates,
                      season_start=candidate.season_start,
                      engine=candidate.engine,
                      members=members,
                      particles=candidate.particles,
                      mode=_spec_mode(d),
                      drop_same_day=1 if candidate.drop_same_day else 0,
                      aux=aux, oracle=oracle)


# === Forecast APIs: /api/series, /api/progress ===
@app.get("/api/series")
def api_series(locs: str = ""):
    """Data-panel series for the checked locations (live, before any run)."""
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
    """Seconds since the console run claimed its slot (setup counts), or
    None when idle."""
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
           # anchors for the browser's own ticking clock
           "started_utc": _status.get("started_utc"),
           "elapsed_s": _console_elapsed(),
           # (label, value) pairs for a client that arrived mid-run
           "settings": list(_status.get("settings") or [])}
    if w:
        done = total = 0
        t0 = None
        # pf_status*.json.prog: the pre-shard merged name and per-shard files
        for f in (glob.glob(w + "/pf_status*.json.prog")
                  + glob.glob(w + "/pf2s/pf_status*.json.prog")):
            try:
                d = _json.loads(open(f).read())
                done += d["done"]; total += d["total"]
                t0 = min(t0 or d["t0"], d["t0"])
            except Exception:
                pass
        # stable denominator from the claim; shard totals grow toward it
        total = max(total, int(_status.get("expected_total") or 0))
        out["done"], out["total"] = done, total
        if done and total and t0:
            rate = (_time.time() - t0) / done
            out["eta_s"] = int(rate * (total - done))
    elif _status.get("expected_total"):
        # run claimed but workroot not created yet: report 0/N, not silence
        out["done"], out["total"] = 0, int(_status["expected_total"])
    return out


# === Shared: run labels, outcome chips, latest results ===
def _run_label(run_id: str, spec_json: str = "", tag: bool = True) -> str:
    """'2026-07-04 · 08-18 09:31' (forecast date · run time). Research runs
    get ' · research' unless tag=False (pages with a styled badge)."""
    import json as _json
    from app.core.runs import is_research
    when = f"{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}"
    suffix = " · research" if (tag and is_research(spec_json)) else ""
    try:
        s = _json.loads(spec_json)
        return f"{s.get('forecast_date','run')} · {when}{suffix}"
    except Exception:
        return when + suffix


def _run_extra(members: int, mode: str, aux: str | None = None,
               oracle: str | None = None) -> dict:
    """spec.extra for a console run: form mode, members=3 research flag,
    Groundhog aux pools (recorded in the spec so it replays), Oracle switch.

    aux: None = shipped (analogue.SHIPPED_AUX, digests recorded), a preset
    name, or "" = bare analogue (research; file withheld).
    oracle: None = shipped Oracle SIHRS, "none" = plain filter (research;
    file withheld); anything else raises."""
    from app.core.engines import analogue as _an
    mode = mode if mode in ("realtime", "vintage") else "realtime"
    extra = {"mode": mode}
    if members == 3:
        extra["members"] = 3
    name = _an.SHIPPED_AUX if aux is None else str(aux)
    if name:
        fn = _an.aux_preset(name)                # unknown name raises here
        extra["aux_pools"] = fn(None, 0, None)["aux_pools"]
        extra["analogue_aux"] = fn.__name__.split(":", 1)[1]
    if oracle is not None and str(oracle) != "":
        if str(oracle) != "none":
            raise ValueError(f"oracle must be 'none' (the plain filter, a "
                             f"research run) or absent, not {oracle!r}")
        extra["oracle"] = "none"
    return extra


def _spec_mode(d: dict) -> str:
    extra = d.get("extra") if isinstance(d.get("extra"), dict) else {}
    m = str(extra.get("mode") or "realtime")
    return m if m in ("realtime", "vintage") else "realtime"


def relwis_chip(value, cells=None, member: str = "PF") -> str:
    """The one relWIS rendering outside a scores table, e.g. 'PF relWIS
    <span class="relwis bad">4.067</span> vs FluSight baseline, ratio of
    sums (2 cells)'. Always names convention and baseline (the CDC's
    pairwise quantity is not comparable). Markup from fixed phrases and
    numbers only."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    cov = ""
    if cells:
        n = int(cells)
        cov = f" ({n} cell{'s' if n != 1 else ''})"
    return (f'{member} relWIS <span class="relwis '
            f'{"ok" if v < 1 else "bad"}">{v:.3f}</span>'
            f' vs FluSight baseline, ratio of sums{cov}')


def _pf_member_label(o: dict) -> str:
    """The mechanistic member's name on one ledger row: "Oracle SIHRS",
    "plain filter" (oracle = none), or "PF" (rows from before the step)."""
    ox = (o or {}).get("oracle")
    if ox == "none":
        return "plain filter"
    return "Oracle SIHRS" if ox else "PF"


def _outcome_chips(outcome_json: str) -> str:
    """One run's outcome as short chips: MARKUP (|safe) of fixed phrases and
    numbers only; raw error strings stay on the run page."""
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
    # no engine is a configuration; a broken install is a fault
    if o.get("pf_engine_broken"):
        bits.append('<span class="bad">PF engine install incomplete</span>')
    if o.get("submissions"): bits.append(f"{len(o['submissions'])} submissions")
    if o.get("submission_errors"):
        ns = len(o["submission_errors"])
        bits.append(f'<span class="bad">{ns} submission'
                    f'{"s" if ns != 1 else ""} refused</span>')
    if o.get("submission_withheld"):
        # deliberate withholding (research run); the run page names the model
        bits.append('<span class="hint">submission withheld '
                    '(research run)</span>')
    if o.get("report"): bits.append("report ✓")
    if o.get("pf_relwis"):
        # scored-cell count; older rows only carry the fit-cell count
        bits.append(relwis_chip(o["pf_relwis"],
                                cells=o.get("pf_relwis_cells",
                                            o.get("pf_cells")),
                                member=_pf_member_label(o)))
    # every scored member (older rows' retired-blend keys are not shown)
    for key, member in (("analogue_relwis", "Groundhog"),):
        if o.get(key):
            bits.append(relwis_chip(o[key], cells=o.get(f"{key}_cells"),
                                    member=member))
    if o.get("error"):
        bits.append('<span class="bad">failed</span>; the full error is on '
                    'the run page')
    return " · ".join(bits)


def _latest_results():
    """(run_id, results) of the newest non-research run, or (None, None).
    A corrupt results.json falls through to the next run; the file is read
    fresh (only the scan is cached). Research runs are skipped because
    every caller is a shipped-product surface (audit rr-1)."""
    import json as _json
    from app.core.runs import is_research
    for f in _workroot_results():
        try:
            res = _json.loads(f.read_text())
        except (_json.JSONDecodeError, OSError):
            continue
        if res.get("research") or is_research(res.get("spec", "")):
            continue
        return f.parent.name, res
    return None, None


# === Output (/output): submissions, downloads, weekly report -> output.html ===
PREVIEW_ROWS = 12


@app.get("/output", response_class=HTMLResponse)
def output_page(request: Request):
    import pandas as pd
    from app.core.runs import APP_STATE
    rid, res = _latest_results()
    files = []
    if rid:
        for entry in _submission_files(APP_STATE / "workroots" / rid):
            entry.update({"cols": [], "rows": [], "more": 0})
            try:
                df = pd.read_csv(entry["path"], dtype=str)
                entry["cols"] = list(df.columns)
                entry["rows"] = df.head(PREVIEW_ROWS).fillna("").values.tolist()
                entry["more"] = max(len(df) - PREVIEW_ROWS, 0)
            except Exception:
                pass
            files.append(entry)
    return templates.TemplateResponse(request, "output.html", {
        "active": "Output", "rid": rid,
        # the stored spec lets the label carry the research tag
        "label": _run_label(rid, (res or {}).get("spec", "")) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "files": files,
        "archive_dates": list(reversed(_archive_dates())),
        "has_report": bool(rid and (APP_STATE / "workroots" / rid / "report.html").is_file())})


@app.get("/output/download")
def output_download(path: str):
    """Download a submission CSV. The file must be inside app state, and a
    submission/ file must sit under a registered hub model's directory (the
    listings' rule, enforced here for hand-edited URLs)."""
    from fastapi.responses import FileResponse
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    if not (p.is_relative_to(APP_STATE.resolve()) and p.is_file()):
        return HTMLResponse("<p>file not found in app state</p>", status_code=404)
    if p.parent.parent.name == "submission" \
            and p.parent.name not in _registered_model_ids():
        return HTMLResponse(
            f"<p>{p.parent.name} is not a registered hub model. This file "
            "was written under a retired identity and the hub would reject "
            "it, so it is not offered as a submission. Use Show in Finder "
            "to open it for reference.</p>", status_code=409)
    return FileResponse(p, filename=p.name, media_type="text/csv",
                        content_disposition_type="attachment")


@app.post("/output/reveal")
def output_reveal(path: str = Form(...)):
    """Show the file in Finder / Explorer (a local desktop app)."""
    import subprocess
    from app.core.runs import APP_STATE
    p = Path(path).resolve()
    # containment via is_relative_to, as in /output/download: a string-prefix
    # test would admit siblings such as app/state_defaults
    if p.is_relative_to(APP_STATE.resolve()) and p.exists():
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        elif sys.platform == "win32":
            # one argv element: Explorer's /select, has odd comma quoting
            subprocess.Popen(["explorer", f"/select,{p}"])
        else:
            subprocess.Popen(["xdg-open", str(p.parent)])
    return RedirectResponse("/output", status_code=303)


#: report path -> builder-sources mtime of a failed rebuild: retry once per
#: builder change, never per request
_REPORT_REBUILD_FAILED: dict = {}


def _report_for_serving(dirpath: Path) -> str:
    """The stored weekly report, rebuilt in place from its inputs bundle
    when older than the builder sources (report_v2.builder_sources_mtime).
    Without a bundle, report_v2.legacy_theme_carry restyles at serve time
    (file untouched). Any failure serves the stored file: never a 500."""
    from app.core import report_v2
    f = Path(dirpath) / "report.html"
    text = f.read_text()
    try:
        src_m = report_v2.builder_sources_mtime()
        if f.stat().st_mtime >= src_m:
            return text                                    # fresh: verbatim
        b = Path(dirpath) / report_v2.BUNDLE_NAME
        if not b.is_file():
            return report_v2.legacy_theme_carry(text)
        if _REPORT_REBUILD_FAILED.get(str(f)) == src_m:
            return text
        try:
            import json as _json
            bundle = _json.loads(b.read_text())
            if bundle.get("version") not in \
                    report_v2.SUPPORTED_BUNDLE_VERSIONS:
                raise ValueError("unknown report bundle version "
                                 f"{bundle.get('version')!r}")
            report_v2.render_bundle(bundle, f)
            return f.read_text()
        except Exception:
            _REPORT_REBUILD_FAILED[str(f)] = src_m
            return text
    except Exception:
        return text


@app.get("/output/report", response_class=HTMLResponse)
def output_report(date: str = ""):
    """Latest run's report, or ?date=YYYY-MM-DD from the archive (both via
    _report_for_serving)."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        d = APP_STATE / "archive" / date
        if not (d / "report.html").is_file():
            return HTMLResponse(f"<p>No archived report for {date}.</p>")
        return HTMLResponse(_report_for_serving(d))
    rid, _ = _latest_results()
    d = APP_STATE / "workroots" / (rid or "")
    if not (d / "report.html").is_file():
        return HTMLResponse("<p>No report yet. Run the models first.</p>")
    return HTMLResponse(_report_for_serving(d))


def _weekly_report_name(date: str) -> str:
    """Saved weekly report name, dated (every run writes report.html)."""
    return f"FluBNF-weekly-report-{date}.html" if date \
        else "FluBNF-weekly-report.html"


def _weekly_report_file(dirpath: Path, date: str):
    """The weekly report as a download, refreshed first (same bytes as the
    page); missing -> 404."""
    from fastapi.responses import FileResponse
    f = Path(dirpath) / "report.html"
    if not f.is_file():
        return HTMLResponse("<p>No report to download.</p>", status_code=404)
    _report_for_serving(dirpath)
    return FileResponse(f, filename=_weekly_report_name(date),
                        media_type="text/html",
                        content_disposition_type="attachment")


@app.get("/output/report/download")
def output_report_download(date: str = ""):
    """/output/report's file, as a download."""
    import re
    from app.core.runs import APP_STATE
    if date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return HTMLResponse("<p>Invalid date. Expected YYYY-MM-DD.</p>",
                                status_code=400)
        return _weekly_report_file(APP_STATE / "archive" / date, date)
    rid, res = _latest_results()
    return _weekly_report_file(APP_STATE / "workroots" / (rid or ""),
                               (res or {}).get("forecast_date", ""))


# === Sandbox (/sandbox): user models on the same engine -> sandbox.html ===
# app/core/sandbox.py; nothing here touches the ledger, Output, retro or seal.
from app.core import sandbox as sandbox_mod                      # noqa: E402

_sandbox_status: dict = {"running": None}


def _sandbox_busy_reason() -> str:
    """Why a sandbox fit may not start now ("" when the engine is free)."""
    if _status.get("running"):
        return "a console run is fitting"
    live = [x for x in _known_seasons() if _season_status(x) in _RETRO_ACTIVE]
    if live:
        return "a retrospective replay is running (" + ", ".join(live) + ")"
    if _sandbox_status.get("running"):
        return f"sandbox run {_sandbox_status['running']} is still fitting"
    return ""


def _sandbox_run_id(run_id: str) -> str:
    if not run_id or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise sandbox_mod.SandboxError(f"{run_id!r} is not a sandbox run")
    return run_id


@app.get("/sandbox", response_class=HTMLResponse)
def sandbox_page(request: Request, run: str = "", model: str = ""):
    models = sandbox_mod.list_models()
    have = {m["name"] for m in models}
    examples = [e for e in sandbox_mod.list_examples() if e not in have]
    runs = sandbox_mod.list_runs()[:25]
    res = None
    try:
        if run:
            res = sandbox_mod.results(sandbox_mod.RUNS / _sandbox_run_id(run))
        elif runs:
            res = sandbox_mod.results(sandbox_mod.RUNS / runs[0]["run_id"])
    except Exception as e:
        _flash(f"That sandbox run could not be read: {e}")
        res = None
    editing = None
    if model:
        try:
            editing = {"name": sandbox_mod.check_name(model),
                       **sandbox_mod.read_model(model)}
        except Exception as e:
            _flash(str(e))
    return templates.TemplateResponse(request, "sandbox.html", {
        "active": "Sandbox", "models": models, "examples": examples,
        "runs": runs, "res": res, "res_json": _script_json(res or {}),
        "editing": editing, "busy": _sandbox_busy_reason(),
        "running_id": _sandbox_status.get("running"),
        "dry_particles": sandbox_mod.DRY_RUN_PARTICLES,
        # the archive as a data source (empty lists with no hub)
        "locations": sandbox_mod.locations(),
        "vintages": sandbox_mod.vintages(),
        "data_range": sandbox_mod.default_range(sandbox_mod.vintages()),
        "data_source": (sandbox_mod.read_data_source(editing["name"])
                        if editing else None)})


@app.post("/sandbox/add-example")
def sandbox_add_example(request: Request, name: str = Form(...)):
    try:
        sandbox_mod.add_example(name)
        _flash(f"Example {name} copied into the sandbox.")
        return RedirectResponse(f"/sandbox?model={name}", status_code=303)
    except Exception as e:
        _flash(str(e))
        return _back(request, "/sandbox")


@app.post("/sandbox/new")
def sandbox_new(request: Request, name: str = Form(...)):
    """A new model from the skeleton's three files (fits as written)."""
    name = (name or "").strip()
    try:
        sandbox_mod.new_model(name)
        _flash(f"New model {name} written from the skeleton; edit it below.")
        return RedirectResponse(f"/sandbox?model={name}", status_code=303)
    except Exception as e:
        _flash(str(e))
        return _back(request, "/sandbox")


@app.post("/sandbox/models/{name}/save")
def sandbox_save(request: Request, name: str,
                 model_bngl: str = Form(""), data_exp: str = Form(""),
                 priors_conf: str = Form("")):
    try:
        sandbox_mod.save_model(name, {"model.bngl": model_bngl,
                                      "data.exp": data_exp,
                                      "priors.conf": priors_conf})
        _flash(f"Saved {name}. Run it to check that the network generates.")
    except Exception as e:
        _flash(str(e))
    return _back(request, f"/sandbox?model={name}")


@app.post("/sandbox/models/{name}/fill-data")
def sandbox_fill_data(request: Request, name: str, location: str = Form(""),
                      start: str = Form(""), end: str = Form(""),
                      source: str = Form("settled")):
    """data.exp from the hub archive: one location's weekly admissions over
    a range, settled truth or one vintage. Missing weeks dropped and
    counted, never imputed."""
    from urllib.parse import quote
    src = (source or "settled").strip()
    asof = None if src == "settled" else src
    try:
        info = sandbox_mod.fill_data(name, (location or "").strip(),
                                     (start or "").strip(),
                                     (end or "").strip(), asof=asof)
        what = ("settled truth" if info["asof"] == "settled"
                else f"vintage of {info['asof']}")
        msg = (f"data.exp filled: {info['location']}, {info['start']} to "
               f"{info['end']}, {what}, {info['rows']} weeks")
        if info["dropped"]:
            msg += f", {info['dropped']} missing weeks dropped"
        _flash(msg)
    except Exception as e:
        _flash(str(e))
    return RedirectResponse(f"/sandbox?model={quote(str(name))}",
                            status_code=303)


@app.post("/sandbox/run")
def sandbox_run(request: Request, model: str = Form(...),
                particles: int = Form(sandbox_mod.DRY_RUN_PARTICLES),
                jitter: float = Form(0.15), forecast_weeks: int = Form(4),
                seed: int = Form(0)):
    why = _sandbox_busy_reason()
    if why:
        _flash(f"Not started: {why}. The sandbox waits for the engine.")
        return _back(request, "/sandbox")
    try:
        workroot = sandbox_mod.prepare(model, particles=particles,
                                       jitter=jitter,
                                       forecast_weeks=forecast_weeks,
                                       seed=seed)
    except Exception as e:
        _flash(f"Not started: {e}")
        return _back(request, f"/sandbox?model={model}")
    run_id = workroot.name
    _sandbox_status["running"] = run_id

    def _go():
        try:
            sandbox_mod.run(workroot)
        finally:
            if _sandbox_status.get("running") == run_id:
                _sandbox_status["running"] = None

    threading.Thread(target=_go, daemon=True, name=f"sandbox-{run_id}").start()
    _flash(f"Sandbox run {run_id} started with {particles} particles.")
    return _back(request, f"/sandbox?run={run_id}")


@app.get("/api/sandbox/models/{name}/contactmap")
def api_sandbox_contactmap(name: str):
    """The model's contact map as an inline SVG, drawn by BNG2.pl's
    visualize action on a copy of the model (no engine, no run)."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        cm = contactmap.parse(contactmap.graphml_from_bngl(files["model.bngl"], work))
        return {"svg": contactmap.svg(cm), "molecules": len(cm["molecules"]),
                "bonds": len(cm["bonds"]), "graph": contactmap.contact_graph(cm)}
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)


@app.get("/api/sandbox/models/{name}/network")
def api_sandbox_network(name: str):
    """BNG2.pl's generated reaction network as inline SVG (generate-only
    copy, no run); too large -> counts and a note. "graph" always returned."""
    from app.core import contactmap
    try:
        files = sandbox_mod.read_model(name)
        work = sandbox_mod.SANDBOX / "contactmap" / sandbox_mod.check_name(name)
        net = contactmap.parse_net(contactmap.network_from_bngl(files["model.bngl"], work))
        drawing = contactmap.svg_network(net)
        out = {"svg": drawing if drawing.startswith("<svg") else "",
               "species": len(net["species"]), "reactions": len(net["reactions"]),
               "graph": contactmap.network_graph(net)}
        if not out["svg"]:
            out["note"] = drawing
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)[:1500]}, status_code=200)


@app.get("/api/sandbox/runs/{run_id}")
def api_sandbox_run(run_id: str):
    try:
        return sandbox_mod.results(sandbox_mod.RUNS / _sandbox_run_id(run_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=404)


# === Models (/models, /model/{name}) -> model.html ===
@app.get("/models", response_class=HTMLResponse)
def models_page(request: Request):
    """The Models tab, defaulting to the PF view; /model/<name> routes stay
    live (reports and bookmarks link them)."""
    return model_page(request, "pf")


@app.get("/model/{name}", response_class=HTMLResponse)
def model_page(request: Request, name: str):
    ot = _oracle_text
    rec = ot.RECORD
    blurbs = {
        "pf": ("Oracle SIHRS",
               "The mechanistic model, submitted on its own: a mechanistic "
               "forecast whose growth is blended with donor growth from past "
               "seasons. It is built on the SIHRS compartment model: "
               "influenza moves people through Susceptible, Infected, "
               "Hospitalized and Recovered compartments, with seasonally "
               "varying transmission and immunity that wanes back to "
               "susceptibility, written in BNGL. Each week PyBNF's "
               "sequential particle filter, on the bngsim engine, fits that "
               "model from the season's start on August 1 through the newest "
               "week of NHSN admissions exactly as archived on the forecast "
               "date: 10,000 candidate epidemics per state are reweighted by "
               "how well they explain the data, and their spread is the "
               "filter's own uncertainty. On its own a filter carries the "
               "growth it sees today forward; it cannot know how a season "
               "usually turns. Past seasons can, so after the fit the "
               "Oracle step blends them in, on the same calendar-donor principle "
               "the Groundhog uses: each of the filter's forecast sample "
               "paths draws one donor growth path from an earlier season at "
               "the same calendar week (within two epiweeks, any "
               "jurisdiction), and its growth over the next four weeks "
               "becomes the geometric mean, half and half, of the filter's "
               "own growth at the forecast origin and the donor's. The "
               "blended growth is propagated in closed form from the "
               "filter's own current state, so the filter's uncertainty and "
               "the donors' spread both survive. " + ot.BANK_TEXT["pool"] +
               " Every rule of the step and of its donor bank was frozen by "
               "a pre-registration before either was scored "
               "(docs/ORACLE-SIHRS.md). On the stored 2024-25 and 2025-26 "
               "forecasts it scores relWIS " + ot.fmt(rec["both"]["oracle"])
               + " against the plain filter's " + ot.fmt(rec["both"]["filter"])
               + " on the same " + ot.cells(rec["both"]["cells"]) + " cells ("
               + ot.fmt(rec["2024-25"]["oracle"]) + " and "
               + ot.fmt(rec["2025-26"]["oracle"]) + " by season; FluSight "
               "baseline, ratio of sums, values below 1 beat it), "
               + ot.fmt(rec["2023-24"]["oracle"]) + " against "
               + ot.fmt(rec["2023-24"]["filter"]) + " in 2023-24 and "
               + ot.fmt(rec["three"]["oracle"]) + " against "
               + ot.fmt(rec["three"]["filter"]) + " over the three seasons. "
               + ot.BANK_TEXT["coverage"] + " " + ot.caveat() +
               " The Groundhog applies donor "
               "growth ratios to the last observed count; the Oracle SIHRS "
               "applies donor growth to the mechanistic state. The two are "
               "submitted as separate models and nothing is blended between "
               "them. The filter alone, three seasons replayed with the "
               "production engine: 0.840 in 2023-24, 0.797 in 2024-25, 0.846 "
               "in 2025-26."),
        "analogue": ("Groundhog",
                     "The empirical model, submitted on its own. It assumes "
                     "the current season will resemble past seasons at the "
                     "same point in the calendar: for each forecast it "
                     "pools, across all states, the weeks from strictly "
                     "earlier seasons that fall within two MMWR epiweeks "
                     "of the forecast date, measures the growth from each "
                     "of those weeks to the target horizon, and scales the "
                     "latest observed value by the quantiles of those "
                     "growth ratios. No epidemiological mechanism is "
                     "involved. Two donor histories feed it: the archive of "
                     "weekly NHSN admissions, and a committed bank of "
                     "FluSurv-NET hospitalization rates read the same way, "
                     "its growth ratios shrunk toward the admissions scale "
                     "by a factor fitted on strictly earlier seasons and "
                     "averaged in at a fixed equal weight. One prior "
                     "season, 2021-22, is excluded from the admissions "
                     "pool: it peaked in April 2022 and survives in the "
                     "archive only as its growth phase, so a "
                     "calendar-matched pool reads it with the wrong sign. "
                     "Measured three-season retrospective relWIS vs the "
                     "FluSight baseline, ratio of sums, on 15,340 cells: "
                     "0.722 in 2023-24, 0.653 in 2024-25, 0.651 in "
                     "2025-26, pooled 0.666; the same engine without the "
                     "FluSurv-NET donors, the calendar analogue that "
                     "shipped inside the blend until 2026-09-22, scores "
                     "0.771 on the same cells."),
        "pf2s": ("Two-strain SIHRS",
                 "A research variant, not a shipped model. It "
                 "models influenza A and influenza B as independent SIHRS "
                 "circuits, each with its own seasonally varying "
                 "transmission, and reports admissions as the sum of the "
                 "two. Fitting uses two data channels, both vintage-true: "
                 "weekly NHSN hospital admissions, and NREVSS typed "
                 "positives entering the likelihood as binomial counts of "
                 "influenza A among typed specimens. The initial A/B mix at "
                 "the season start comes from the same typed surveillance "
                 "series. It is stronger than the single-strain filter at "
                 "turning points, but when the blend still shipped, adding "
                 "it scored worse on the full grid: relWIS 0.719 against "
                 "0.704 for the two-member blend (vs the FluSight "
                 "baseline, ratio of sums, measured before the 2021-22 "
                 "donor exclusion). This engine is kept for research runs "
                 "only."),
    }
    # no page for the retired blend (LosAlamos_NAU-CModel_Flu, see ENGINES)
    # one-line summaries: the collapsed <details> summary on each model tab
    onelines = {
        "pf": ("The mechanistic model: the SIHRS compartment model fitted "
               "weekly by a particle filter, its forecast growth blended with "
               "donor growth from past seasons at the same calendar week."),
        "analogue": ("The empirical model: it scales the latest observation "
                     "by historical growth ratios from matching calendar "
                     "weeks, with banked FluSurv-NET donors."),
        "pf2s": ("A research variant, not shipped: influenza A and B as "
                 "parallel SIHRS circuits fitted to two data channels."),
    }
    # where each model tab points into the Methods page
    manchor = {"pf": "oracle", "analogue": "analogue",
               "pf2s": "two-strain"}
    if name not in blurbs:
        return HTMLResponse("unknown model", status_code=404)
    rid, res = _latest_results()
    fanq = {}
    if res and name in res.get("models", {}):
        fanq = {loc: qs for loc, qs in res["models"][name].items()
                if all(isinstance(v, dict) for v in qs.values())}
    # the member overlay belonged to the retired blend's page: always empty
    overlay = {}
    form = dict(_last_form) or {"forecast_date": _default_forecast_date(),
                                "locations": ["all"], "replicates": 3}
    # BNGL-backed models show their template source, read at render time
    bngl_files = {"pf": "SIHRS_pop_min.bngl",
                  "pf2s": "SIHRS_pop_2strain_min.bngl"}
    bngl_src, bngl_file = "", bngl_files.get(name, "")
    if bngl_file:
        try:
            bngl_src = (REPO / "flubnf" / "templates" / bngl_file).read_text(
                encoding="utf-8")
        except OSError:
            bngl_src, bngl_file = "", ""
    return templates.TemplateResponse(request, "model.html", {
        "active": "Models", "name": name,
        # title from the shared model-name map
        "title": _model_names().get(name, blurbs[name][0]),
        "blurb": blurbs[name][1],
        "model_names_json": _script_json(_model_names()),
        "member_colors_json": _script_json(_member_colors()),
        "oneline": onelines[name], "manchor": manchor[name],
        # the research run control (research_run.html) lives ONLY on the
        # two-strain view, never on the Forecast form
        "research_panel": name == "pf2s",
        "rid": rid,
        "label": _run_label(rid, (res or {}).get("spec", "")) if rid else "",
        "date": (res or {}).get("forecast_date", ""),
        "fanq_json": _script_json(fanq),
        "overlay_json": _script_json(overlay),
        "run_obs_json": _script_json((res or {}).get("observed", {})),
        "bngl_src": bngl_src, "bngl_file": bngl_file,
        "form": form, "status": _status})




# === Retrospective core: roots, claims, season status ===
RETRO_ROOT = Path(__file__).resolve().parents[1] / "state" / "retro"
# The sealed full-grid records, read only: the reseal (production engine,
# the Home/Methods figures) first, then v1.0.0's seal (history).
RETRO_RESEAL = Path(__file__).resolve().parents[1] / "state" / "retro_reseal"
RETRO_SEAL = Path(__file__).resolve().parents[1] / "state" / "retro_seal"


def _sealed_roots() -> tuple:
    """((root, label), ...) in preference order, read at call time (tests
    repoint the roots)."""
    return ((RETRO_RESEAL, "the production engine's record (reseal of "
                           "2026-09-07), the figures on Home and Methods"),
            (RETRO_SEAL, "sealed v1.0.0 engine record (retired raw-space "
                         "kernel); the production engine scores 0.723 "
                         "pooled, see Methods"))


def _sealed_label(root: Path) -> str:
    """The label of the sealed record `root` lies in, or an empty string."""
    for base, label in _sealed_roots():
        try:
            if Path(root).resolve().is_relative_to(Path(base).resolve()):
                return label
        except OSError:
            continue
    return ""


def _season_root(season: str, archive: str = "") -> tuple:
    """(root, is_seal): whichever of the app's retro root and the sealed
    records has the most completed weeks (ties: app, reseal, seal). With an
    archive id, exactly that archived tree."""
    if archive:
        from app.core import retro
        return retro.archive_dir(RETRO_ROOT, season, archive), False
    best, is_seal = RETRO_ROOT / season, False
    n = _weeks_done(best)
    for base, _label in _sealed_roots():
        m = _weeks_done(base / season)
        if m > n:
            best, is_seal, n = base / season, True, m
    return best, is_seal
_retro_status: dict = {}
_retro_stop: set = set()
_retro_claim_at: dict = {}   # season -> when its in-memory claim was made

#: statuses that mean a season worker is alive and holding the engine
_RETRO_ACTIVE = ("running", "stopping", "paused")


class _RetroStopRequested(Exception):
    """Raised inside the season worker between weeks when a stop was asked."""


def _valid_season(season: str) -> bool:
    """YYYY-YY only (season names become directory names)."""
    import re
    return bool(re.fullmatch(r"\d{4}-\d{2}", season or ""))


def _valid_archive(stamp: str) -> bool:
    """Archive stamp format only (it becomes a directory name)."""
    from app.core import retro
    return retro.valid_stamp(stamp or "")


def _live_root(season: str) -> Path:
    """Where this app's season worker runs (control flags, run record): the
    only tree a Run can resume, archive or discard. Sealed trees are never
    written."""
    return RETRO_ROOT / season


@ttlcache.ttl_cache()
def _seasons_on_disk(retro_root: Path) -> tuple:
    """Seasons under a retro root carrying a run record (cached per root)."""
    from app.core import retro
    names = set()
    try:
        for p in Path(retro_root).iterdir():
            if (_valid_season(p.name) and p.is_dir()
                    and retro.meta_path(p).is_file()):
                names.add(p.name)
    except OSError:
        pass                          # no retro root yet
    return tuple(sorted(names))


def _known_seasons() -> list:
    """In-memory claims (read live, never cached) plus every season with a
    run record on disk (records outlive claims across restarts)."""
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
                    "rel": s["headline_rel"], "rels": s.get("headline_rels"),
                    # each archive is its own tree, named for what it holds
                    "pf_name": _pf_name(p),
                    "scored": s["scored"],
                    "size": size, "size_h": retro.human_bytes(size)})
    return out


def _archive_entries(season: str) -> list:
    """Archived runs of one season, newest first, as the retro index lists
    them (cached per root + season: sizing every tree is the index's most
    expensive scan)."""
    return _scan_archive_entries(RETRO_ROOT, season)


def _archive_progress(root: Path, season: str) -> dict:
    """An archived run's timing block, shaped like _retro_progress; never
    active."""
    from app.core import retro
    meta = retro.read_meta(root)
    t = retro.timing(meta) if meta else {}
    done = _weeks_done(root)
    return {"season": season, "status": "archived", "done": done,
            # the archive's own settings, not the live season's
            "settings": retro.settings_summary(meta),
            "total": int(t.get("total_weeks") or done),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": t.get("mean_s"), "eta_s": None,
            "eta_lo_s": None, "eta_hi_s": None, "eta_basis": None,
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
    """One status per season: running, paused, stopping, stopped, done,
    interrupted, error: …, or "". Across restarts the record's heartbeat
    decides, not the in-memory claim."""
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
            # the claimed worker finished after the claim was made: the claim
            # is dead (else "stopping" wedges Run). A fresh claim over an
            # older record still reads as live.
            _retro_status[season] = disk
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return disk
        if not meta and claimed_at and time.time() - claimed_at > 120:
            # no record two minutes after the claim: the worker never started
            _retro_status[season] = ""
            _retro_stop.discard(season)
            _retro_claim_at.pop(season, None)
            return ""
        if mem == "stopping":
            return "stopping"
        # the record refines running into paused as the worker holds
        return disk if disk in ("running", "paused") else mem
    return mem or disk


# === Retrospective: remaining-time estimate for a live replay ===
# Week cost climbs ~3x through a season, so a global mean freezes. Level =
# recency-weighted measured weeks (half-life 3); shape = a completed
# same-scope run's per-week profile; time spent in the in-flight week is
# credited. Reported as a range with its basis.

def _scope_key(meta: dict):
    """Hashable location-scope identity of a run record (None without
    settings): panel6/all plus '+us' when the national row was fitted
    (heavier weeks); a custom selection by its exact location list."""
    s = (meta or {}).get("settings")
    if not isinstance(s, dict) or not s:
        return None
    scope = str(s.get("scope") or "")
    if scope in ("panel6", "all"):
        from app.core import us_national as usn
        locs = [str(l) for l in (s.get("locations") or [])]
        nat = (any(usn.is_us(l) for l in locs) if locs
               else bool(s.get("national")))
        return scope + ("+us" if nat else "")
    locs = tuple(sorted(str(l) for l in (s.get("locations") or [])))
    return locs or None


#: fewest measured weeks a completed run needs before its per-week seconds
#: can serve as a season shape for another run's estimate
_PROFILE_MIN_WEEKS = 8


@ttlcache.ttl_cache()
def _profile_scan(retro_root: Path, seal_root: Path, season: str,
                  scope_key) -> tuple | None:
    """The same-scope completed run (most measured weeks) whose per-week
    seconds shape the estimate: other seasons' live and sealed trees and
    every archived run, including this season's. Cached by both roots.

    Returns (season_label, ((position 0..1, relative_cost), ...)) or None
    (the estimate then uses its default shape)."""
    if not scope_key:
        return None
    from app.core import retro
    best = None
    for s in retro.available_seasons():
        roots = []
        if s != season:
            roots.append(Path(retro_root) / s)
            roots.append(Path(seal_root) / s)
        roots.extend(retro.list_archive_dirs(retro_root, s))
        for r in roots:
            m = retro.read_meta(r)
            if not m or _scope_key(m) != scope_key:
                continue
            ws = {k: float(v)
                  for k, v in (m.get("week_seconds") or {}).items()
                  if isinstance(v, (int, float)) and float(v) > 0}
            if len(ws) < _PROFILE_MIN_WEEKS:
                continue          # too few weeks to carry a season's shape
            if best is None or len(ws) > best[2]:
                vals = [ws[k] for k in sorted(ws)]
                mean = sum(vals) / len(vals)
                n = len(vals)
                pts = tuple((i / (n - 1) if n > 1 else 0.0, v / mean)
                            for i, v in enumerate(vals))
                best = (s, pts, n)
    return (best[0], best[1]) if best else None


def _eta_estimate(measured, remaining, profile=None, spent_s=0.0,
                  overhead_s=0.0):
    """The remaining-time estimate itself; pure, so tests can replay
    recorded seasons week by week.

    measured    [(position, seconds)] for this run's completed weeks,
                ascending by week; position is the week's fractional place
                in its season, 0..1.
    remaining   [position] for the weeks still to run, the week in flight
                first.
    profile     ((position, relative_cost), ...) from a completed
                same-scope run, or None for a flat profile.
    spent_s     seconds already inside the week in flight.
    overhead_s  per-week seconds this run spends between weeks, measured
                from its own record.

    Returns (lo_s, mid_s, hi_s) or None when nothing is measured. The band
    is the larger of the weighted spread and a schedule calibrated on the
    recorded seasons (test_retro_eta.py), widened with no profile or few
    weeks, and treated as correlated across weeks (never shrunk by count)."""
    if not measured or not remaining:
        return None
    if not profile:
        # No same-scope profile: assume a linear 0.55x -> 1.40x ramp (each
        # week refits from season start, so cost grows). Chosen as the
        # smallest worst-season error among linear ramps replayed against the
        # recorded full-grid seasons (data: app/tests/test_retro_eta.py); a
        # flat default biased the estimate ~40 min low.
        profile = ((0.0, 0.55), (1.0, 1.40))
        default_shape = True
    else:
        default_shape = False

    def cost(p):
        if not profile:
            return 1.0
        if p <= profile[0][0]:
            return profile[0][1]
        for (p0, c0), (p1, c1) in zip(profile, profile[1:]):
            if p <= p1:
                return c0 + ((c1 - c0) * (p - p0) / (p1 - p0)
                             if p1 > p0 else 0.0)
        return profile[-1][1]

    n = len(measured)
    half_life = 3.0               # weeks: the recent past predicts the next
    wts = [0.5 ** ((n - 1 - j) / half_life) for j in range(n)]
    ratios = [s / max(cost(p), 1e-9) for p, s in measured]
    wsum = sum(wts)
    level = sum(w * r for w, r in zip(wts, ratios)) / wsum
    if level <= 0:
        return None
    var = sum(w * (r - level) ** 2 for w, r in zip(wts, ratios)) / wsum
    rel = (var ** 0.5) / level
    preds = [level * cost(q) + max(0.0, float(overhead_s))
             for q in remaining]
    left = max(0.0, sum(preds) - min(max(0.0, float(spent_s)), preds[0]))
    frac_rem = len(remaining) / (n + len(remaining))
    u = max(rel, 0.10 + 0.20 * frac_rem + (0.15 if default_shape else 0.0))
    if n < 3:
        u = max(u, 0.50)          # one or two weeks cannot claim precision
    elif n < 6:
        u = max(u, 0.25)
    return (left * (1.0 - u), left, left * (1.0 + u))


def _inflight_spent(root: Path, remaining: list, now: float) -> float:
    """Seconds already inside the in-flight week (the most recently started
    remaining week directory); zero between weeks."""
    weeks = Path(root) / "weeks"
    best = None
    for asof in remaining:
        wd = weeks / asof
        if not wd.is_dir():
            continue
        try:
            t0 = min((f.stat().st_mtime for f in wd.iterdir()), default=None)
        except OSError:
            continue
        if t0 is not None and (best is None or t0 > best):
            best = t0
    return max(0.0, now - best) if best is not None else 0.0


def _season_eta(meta: dict, season: str, root: Path, t: dict) -> tuple | None:
    """_eta_estimate for a live season: positions from the vintage calendar
    (index fallback), same-scope profile, in-flight seconds, measured
    between-week overhead. Returns (lo_s, mid_s, hi_s, basis) or None."""
    from app.core import retro
    ws = {k: float(v) for k, v in ((meta or {}).get("week_seconds") or {}).items()
          if isinstance(v, (int, float)) and float(v) > 0}
    if not ws:
        return None
    completed = {p.parent.name for p in retro.season_sample_files(root)}
    done = len(completed)
    vintages = list(retro.season_vintages(season))
    if vintages and completed <= set(vintages) and len(vintages) > done:
        posmap = {v: (i / (len(vintages) - 1) if len(vintages) > 1 else 0.0)
                  for i, v in enumerate(vintages)}
        measured = [(posmap.get(k, 1.0), ws[k]) for k in sorted(ws)]
        remaining_names = [v for v in vintages if v not in completed]
        remaining = [posmap[v] for v in remaining_names]
    else:
        # no calendar: place weeks by index; no in-flight credit
        total = max(int(t.get("total_weeks") or 0), done + 1)
        denom = max(total - 1, 1)
        keys = sorted(ws)
        measured = [(j / denom, ws[k]) for j, k in enumerate(keys)]
        remaining_names = []
        remaining = [(done + i) / denom for i in range(total - done)]
    if not remaining:
        return None
    now = time.time()
    spent = (_inflight_spent(root, remaining_names, now)
             if remaining_names else 0.0)
    elapsed = float(t.get("elapsed_s") or 0.0)
    overhead = min(120.0, max(0.0, elapsed - sum(ws.values()) - spent)
                   / max(1, len(ws)))
    prof = _profile_scan(RETRO_ROOT, RETRO_SEAL, season, _scope_key(meta))
    est = _eta_estimate(measured, remaining,
                        profile=(prof[1] if prof else None),
                        spent_s=spent, overhead_s=overhead)
    if est is None:
        return None
    basis = "estimate from %d completed week%s" % (
        len(ws), "" if len(ws) == 1 else "s")
    if prof:
        basis += ", weighted by the %s week profile" % prof[0]
    else:
        basis += ", shaped by the recorded full-grid week profile"
    return est[0], est[1], est[2], basis


def _retro_progress(season: str) -> dict:
    """Live progress and timing for one season, as the retro pages poll it.
    The ETA range (_season_eta) is null unless running and computable."""
    from app.core import retro
    status = _season_status(season)
    meta = _season_meta(season)
    t = retro.timing(meta) if meta else {}
    root, _is_seal = _season_root(season)
    done = _weeks_done(root)
    total = t.get("total_weeks") or len(retro.season_vintages(season))
    mean_s = t.get("mean_s")
    eta_lo = eta_s = eta_hi = eta_basis = None
    if status == "running" and total and done < total:
        est = _season_eta(meta, season, root, t)
        if est:
            eta_lo, eta_s, eta_hi, eta_basis = est
    return {"season": season, "status": status, "done": done,
            "total": int(total or 0),
            "settings": retro.settings_summary(meta),
            "elapsed_s": t.get("elapsed_s"),
            "weeks_measured": t.get("weeks_measured") or 0,
            "mean_s": mean_s, "eta_s": eta_s,
            "eta_lo_s": eta_lo, "eta_hi_s": eta_hi, "eta_basis": eta_basis,
            "slowest_week": t.get("slowest_week"),
            "slowest_s": t.get("slowest_s"),
            "started_utc": t.get("started_utc"),
            "finished_utc": t.get("finished_utc"),
            "active": status in _RETRO_ACTIVE}


# === Retrospective index (/retro) and its APIs -> retro.html ===
def _retro_state_names() -> list:
    """State list for the retro form; packaged locations table when the hub
    is not cloned yet."""
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


def _retro_national_name() -> str:
    """The hub's location_name for the national row (as truth and the
    forecast path name it); falls back to the FIPS code."""
    import pandas as pd
    from flubnf.settings import LOCATIONS
    from pathlib import Path as _P
    from app.core import us_national as usn
    packaged = _P(__file__).resolve().parents[2] / "flubnf/data/locations.csv"
    for src in (LOCATIONS, packaged):
        try:
            locs = pd.read_csv(src, dtype=str)
            hit = locs.location_name[locs.abbreviation == "US"]
            if len(hit):
                return str(hit.iloc[0])
        except Exception:
            continue
    return usn.US_FIPS


@app.get("/retro", response_class=HTMLResponse)
def retro_index(request: Request):
    from app.core import retro as _retro
    from app.core.retro import available_seasons, season_vintages
    seasons = []
    for s in available_seasons():
        total = len(season_vintages(s))
        root, is_seal = _season_root(s)
        done = _weeks_done(root)
        prog = _retro_progress(s)
        status = prog["status"]
        # head scores: one relWIS per scored model
        _summ = _retro.run_summary(root)
        rel = _summ.get("headline_rel")
        rels = _summ.get("headline_rels") or ({"": rel} if rel is not None
                                              else {})
        # one-click resume from the LIVE root's record (never the seal's)
        resume_fields = None
        if status in ("stopped", "interrupted"):
            resume_fields = _retro.resume_form_fields(
                _retro.read_meta(_live_root(s)))
        seasons.append({"name": s, "total": total, "done": done,
                        "seal": is_seal,
                        "seal_label": _sealed_label(root) if is_seal else "",
                        "rel": rel, "rels": rels,
                        # sealed records store the bare filter under pf
                        "pf_name": _pf_name(root),
                        "resume_fields": resume_fields,
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
    from app.core.engines.pf import DEFAULT_SHARD_WIDTH, SHARD_WIDTH_CAP
    return templates.TemplateResponse(request, "retro.html",
                                      {"active": "Retrospective", "seasons": seasons,
                                       "state_names": _retro_state_names(),
                                       "default_width": DEFAULT_SHARD_WIDTH,
                                       "width_cap": SHARD_WIDTH_CAP,
                                       "engine_ok": PY_ENGINE.exists()
                                       and PYBNF.exists()})


@app.get("/api/retro/progress")
def api_retro_progress(season: str = ""):
    """Live retro progress for the tickers: one season, or every season
    with a record or claim (polled, so a guard modal is not wiped)."""
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
    """What pressing Run on this season would do, from the LIVE root only.

    weeks == 0: Run starts with no prompt. Exception: an empty live tree
    under a shown SEALED run returns sealed=True with the sealed weeks, so
    the client prompts (choices: cancel or a fresh replay)."""
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
            # blank rather than a fabricated 0:00:00
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
    """Delete one archived run permanently: well-formed ids, season not
    replaying, confirmation names the season. The live season is never
    touched."""
    from app.core import retro
    _invalidate_scans()
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


# === Retrospective: results preparation (season finalize, off request paths) ===
# Scoring a season takes minutes, so finalize runs as one background job per
# season root, shared by the worker (before marking done) and page visits
# that find stale caches (they poll /api/retro/{season}/results_status).

#: grace wait before the results route renders the preparing state (small
#: seasons and test trees finish inside it)
_RESULTS_GRACE_S = 1.5

_results_jobs: dict = {}          # str(root) -> job record
_results_lock = __import__("threading").Lock()


def _scoring_failed_hint(score_error: str) -> str:
    """The season map panel's scoring-failed fragment; score_error is
    escaped HERE (the template injects map_html with | safe)."""
    return ("<p class='hint'>Scoring failed: <code>"
            + _htmlmod.escape(score_error) + "</code>. The fitted forecasts "
            "below are intact; fix the scoring input (usually the FluSight "
            "hub clone, via the Data tab) and reload this page.</p>")


def _week_map_cards_by_model(root: Path, wk: str) -> dict:
    """{model: {fips: card}} for one stored retro week, every model it
    stored: each member's 23-level quantile sidecar
    (retro.week_member_quantiles) through the categorical CDF, anchor-week
    median as baseline.

    Disk-cached in playback_cache/map_cards/<wk>.json keyed by samples
    mtime. A SUBDIRECTORY because report_season._newest_input globs
    playback_cache/*.json as report inputs: cache warming must not look
    like new data."""
    import json as _json
    import numpy as np
    from app.core import retro
    from app.core.categorical import CATS, probs_from_quantiles
    root = Path(root)
    sp = retro.week_samples_path(root, wk)
    if sp is None:
        return {}
    try:
        mtime = int(sp.stat().st_mtime)
    except OSError:
        return {}
    cf = root / "playback_cache" / "map_cards" / f"{wk}.json"
    try:
        cached = _json.loads(cf.read_text())
        if cached.get("mtime") == mtime and cached.get("v") == 2:
            return cached["cards"]
    except Exception:
        pass
    locs = __import__("flubnf.settings",
                      fromlist=["load_locations"]).load_locations()
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2p = dict(zip(locs.location_name, locs.population.astype(float)))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    # baseline: the PF's origin draws (the reported value replicated); an
    # analogue-only week has none, so read the week's vintage instead
    mq = retro.week_member_quantiles(root, wk)
    base = {}
    try:
        d = retro.read_samples(sp)
        for loc, sm in (d.get("pf") or {}).items():
            o = np.asarray(sm.get(_hzmod.ORIGIN, []), float)
            o = o[np.isfinite(o)]
            if o.size:
                base[loc] = float(np.median(o))
    except Exception:
        pass
    if not base:
        try:
            base = _last_reported_before(wk, n2f)
        except Exception:
            base = {}
    by_model = {}
    for model, by_loc in mq.items():
        cards = {}
        for loc, qs in by_loc.items():
            q1 = qs.get("0")                      # one week ahead, canonical
            lo = base.get(loc)
            if not q1 or lo is None or loc not in n2f:
                continue
            probs = probs_from_quantiles(q1, lo, int(n2p.get(loc, 0)), 0)
            if not probs:
                continue
            med = float(q1.get(0.5, 0.0))
            # hover_html reaches innerHTML: escape the name
            hover = (f"<b>{_htmlmod.escape(loc)}</b><br>1-wk median: "
                     f"{med:.0f}<br>" +
                     "<br>".join(f"{c.replace('_',' ')}: {probs.get(c,0):.0%}"
                                 for c in CATS))
            cards[n2f[loc]] = {"probs": probs, "name": loc,
                               "abbr": n2a.get(loc, ""), "fips": n2f[loc],
                               "hover_html": hover}
        if cards:
            by_model[model] = cards
    try:
        # write beside, then replace
        import os as _os
        cf.parent.mkdir(parents=True, exist_ok=True)
        tmp = cf.with_name(cf.name + ".tmp")
        tmp.write_text(_json.dumps({"mtime": mtime, "v": 2, "cards": by_model}))
        _os.replace(tmp, cf)
    except Exception:
        pass                      # an unwritable cache costs speed, not truth
    return by_model


def _last_reported_before(wk: str, n2f: dict) -> dict:
    """{location: last reported value} from the vintage dated `wk`, the
    baseline a week stores no anchor draws for."""
    import pandas as pd
    df = pd.read_csv(data_mod.vintage_path(wk), dtype={"location": str})
    df["location"] = df["location"].str.zfill(2)
    df = df[df.date <= wk].dropna(subset=["value"]).sort_values("date")
    last = df.groupby("location")["value"].last()
    return {loc: float(last[f]) for loc, f in n2f.items() if f in last.index}


def _retro_map_models(by_model: dict) -> list:
    """Models a week's map can show, in display order (a stored blend only
    when the week holds nothing else)."""
    from app.core import report_v2
    order = report_v2.toggle_models(by_model)
    return order or [m for m in report_v2.MODEL_ORDER if m in by_model]


def _week_map_cards(root: Path, wk: str) -> dict:
    """The first display-order model's cards for the week (the default
    view before the toggle)."""
    by_model = _week_map_cards_by_model(root, wk)
    order = _retro_map_models(by_model)
    return dict(by_model[order[0]]) if order else {}


def _ensure_results_job(root: Path, season: str,
                        force: bool = False) -> dict:
    """Start or join THE finalize job for this root (one per root; racing
    callers share the record, whose 'done' event fires when caches are
    ready). `force` rescores; ignored when joining a running job."""
    import threading
    from app.core import retro
    key = str(root)
    with _results_lock:
        job = _results_jobs.get(key)
        if job and not job["done"].is_set():
            return job
        if _is_sealed_root(root):
            # the sealed record is read only: nothing is scored into it
            job = {"phase": "sealed", "t0": time.time(),
                   "done": threading.Event(), "seconds": 0.0,
                   "season": season, "inputs": None,
                   "error": "the sealed validation record is read only; "
                            "its scores stand and are never recomputed"}
            job["done"].set()
            _results_jobs[key] = job
            return job
        job = {"phase": "preparing", "t0": time.time(),
               "done": threading.Event(), "error": "", "seconds": None,
               "season": season,
               "inputs": retro.newest_samples_mtime(root)}
        _results_jobs[key] = job

    def _run():
        try:
            job["seconds"] = retro.finalize_season(
                root, season,
                phase_cb=lambda p: job.__setitem__("phase", p),
                force=force)
            # warm the default view's (last week's) map cards
            wks = [p.parent.name for p in retro.season_sample_files(root)]
            if wks:
                _week_map_cards(root, wks[-1])
        except Exception as e:
            job["error"] = f"{type(e).__name__}: {str(e)[:220]}"
        finally:
            job["done"].set()
            _invalidate_scans()

    threading.Thread(target=_run, daemon=True,
                     name=f"flubnf-results-{season}").start()
    return job


def _job_covered(root: Path) -> dict | None:
    """The completed job that ran on this root's CURRENT inputs, or None.
    Empty scores plus a covering job means truth has not settled (or
    job['error']): render that state, do not recompute every visit."""
    from app.core import retro
    job = _results_jobs.get(str(root))
    if (job and job["done"].is_set()
            and job["inputs"] >= retro.newest_samples_mtime(root)):
        return job
    return None


#: LRU of parsed scores.json frames keyed by (path, mtime_ns, size), so a
#: rescore invalidates by construction. ~50 MB per frame; cap 3 holds the
#: three sealed seasons without eviction while bounding archive sweeps.
_SCORES_FRAMES_MAX = 3
_SCORES_FRAMES: "OrderedDict" = OrderedDict()


def _scores_df(root: Path):
    """Parsed scores.json for this root (None if missing/unparseable), one
    parse per file content. Callers must not mutate the frame."""
    import pandas as pd
    sf = Path(root) / "scores.json"
    try:
        st = sf.stat()
    except OSError:
        return None
    key = (str(sf), st.st_mtime_ns, st.st_size)
    hit = _SCORES_FRAMES.get(key)
    if hit is not None:
        _SCORES_FRAMES.move_to_end(key)      # least-recently-used ordering
        return hit
    try:
        df = pd.read_json(sf)
    except Exception:
        return None
    _SCORES_FRAMES[key] = df
    while len(_SCORES_FRAMES) > _SCORES_FRAMES_MAX:
        _SCORES_FRAMES.popitem(last=False)   # evict one, never flush the lot
    return df


#: LRU of season relWIS figures keyed by scores identity, convention and (for
#: pairwise, ~3 s per season) the field data's identity. Entries are small.
_RELWIS_FIGS_MAX = 12
_RELWIS_FIGS: "OrderedDict" = OrderedDict()


def _relwis_conventions() -> list:
    """The convention switch's options; the project's own (the default,
    and every sealed number's) first."""
    from app.core import relwis
    return [relwis.CONVENTION_INFO[k] for k in relwis.CONVENTIONS]


def _relwis_figures(root: Path, convention: str):
    """This root's relWIS figures under ONE convention, cached on identity.
    Without the FluSight field data, pairwise figures carry the reason and
    NO numbers; never substitute the other convention (app/core/relwis).
    """
    from app.core import relwis
    from app.core import us_national as usn
    conv = relwis.convention_of(convention)
    # the field (600k+ cells) only when the convention needs it
    field = relwis.load_field_cells() if conv == relwis.PAIRWISE else None
    sf = Path(root) / "scores.json"
    try:
        st = sf.stat()
        ident = (st.st_mtime_ns, st.st_size)
    except OSError:
        ident = (0, 0)
    key = (str(sf), ident, conv,
           (field.stamp, field.reason) if field is not None else ())
    hit = _RELWIS_FIGS.get(key)
    if hit is not None:
        _RELWIS_FIGS.move_to_end(key)
        return hit
    figs = relwis.season_figures(usn.pooled_frame(_scores_df(root)), conv,
                                 field=field)
    _RELWIS_FIGS[key] = figs
    while len(_RELWIS_FIGS) > _RELWIS_FIGS_MAX:
        _RELWIS_FIGS.popitem(last=False)
    return figs


def _is_sealed_root(root: Path) -> bool:
    """Whether root lies under a sealed record: read only, never stale and
    never rescored, even when the hub's truth moves on."""
    try:
        parents = Path(root).resolve().parents
        return any(Path(base).resolve() in parents
                   for base, _ in _sealed_roots())
    except OSError:
        return False


def _scores_current_fast(root: Path) -> bool:
    """retro.scores_current's rule (exists, parses, newer than every week
    and the hub's truth) from stats and the cached parse. Sealed roots are
    current whenever their scores parse."""
    from app.core import retro
    root = Path(root)
    weeks = retro.season_sample_files(root)
    if not weeks:
        return True
    sf = root / "scores.json"
    if not sf.is_file():
        return False
    if _is_sealed_root(root):
        return _scores_df(root) is not None
    try:
        from app.core.data import truth_mtime
        if sf.stat().st_mtime < max([p.stat().st_mtime for p in weeks]
                                    + [truth_mtime()]):
            return False           # older than a sample, or than the truth
    except OSError:
        return False
    return _scores_df(root) is not None


def _scores_scoreable_fast(root: Path) -> bool:
    """retro.scores_scoreable's exact rule (a model column and at least one
    cell), from the shared cached parse."""
    df = _scores_df(root)
    return df is not None and (not df.empty) and ("model" in df.columns)


def _results_pending(root: Path) -> str:
    """'' when the results page can render from caches alone, else why not
    (stats and cached reads only, never computation)."""
    from app.core import retro
    if not _scores_current_fast(root):
        return "scores stale"
    if not _scores_scoreable_fast(root):
        return "" if _job_covered(root) else "scores empty"
    if not retro.national_aggregate_fresh(root):
        return "national aggregate stale"
    return ""


@app.get("/api/retro/{season}/results_status")
def api_retro_results_status(season: str, archive: str = ""):
    """The preparing state's poll: is the finalize job still working, and in
    which phase. Never starts work (the results page does)."""
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return {"pending": False, "error": "unrecognized archive"}
    if not _valid_season(season):
        return {"pending": False, "error": "unrecognized season"}
    root, _is_seal = _season_root(season, archive)
    job = _results_jobs.get(str(root))
    if job and not job["done"].is_set():
        return {"pending": True, "phase": job["phase"],
                "elapsed_s": round(time.time() - job["t0"], 1)}
    return {"pending": False, "error": (job or {}).get("error", "")}


# === Retrospective: season worker and run controls ===
def _retro_bg(season: str, locations: list, width: int,
              replicates: int = 3, particles: int = 10_000,
              settings: dict | None = None, engine: str = "pf"):
    """The season worker. `settings` is the form's choices (scope label,
    engine preset); run_season records them with the rest in run_meta.json
    before the first week."""
    from app.core import retro
    root = RETRO_ROOT / season
    _retro_status[season] = "running"
    _retro_stop.discard(season)     # no stale stop flag from a past run
    retro.clear_flags(root)         # nor a stale STOP/PAUSE file from one
    guard = _sleep_guard()          # overnight replays must outlive the lid
    try:
        def _tick(_asof):
            # called after every week: the clean stop point
            if season in _retro_stop:
                raise _RetroStopRequested()
        retro.run_season(root, season, locations, replicates=replicates,
                         particles=particles, width=width, progress=_tick,
                         settings=settings, engine=engine)
        # finalize (score, national aggregate, playback caches) BEFORE the
        # season reads done, via the shared job registry
        job = _ensure_results_job(root, season)
        job["done"].wait()
        if job.get("seconds"):
            retro.record_finalize(root, job["seconds"])
        if job["error"]:
            _retro_status[season] = f"error: {job['error'][:150]}"
        else:
            _retro_status[season] = "done"
    except (_RetroStopRequested, retro.SeasonStopped):
        # completed weeks stay; the results page scores whatever exists
        _retro_status[season] = "stopped"
    except Exception as e:
        _retro_status[season] = f"error: {str(e)[:150]}"
    finally:
        _retro_stop.discard(season)
        _invalidate_scans()
        # flags are requests: a leftover one would stop the NEXT replay
        retro.clear_flags(root)
        if guard is not None:
            try:
                guard.terminate()
            except Exception:
                pass


@app.post("/retro/stop")
def retro_stop():
    """Stop every live replay after the fits in flight (polled between fits).
    Finished fits are kept and a restart resumes there. Paused seasons stop
    too (request_stop clears the pause)."""
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
    """Stop ONE season after the fits in flight. Finished fits are
    checkpointed and a half-week never writes samples.json."""
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
        # not replaying: resolve now, never leave an orphan "stopping" claim
        _retro_status[season] = "stopped"
        _retro_stop.discard(season)
        _flash(f"{season} was not replaying; it is marked stopped and Run "
               "will start it fresh or resume it.")
    return _back(request, "/retro")


@app.post("/retro/{season}/pause")
def retro_season_pause(request: Request, season: str):
    """Hold after the fits in flight (polled between fits). The worker and
    its sleep guard stay alive."""
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
    """Release a hold; the elapsed clock resumes, not restarts."""
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
              national: str = Form("1"),
              particles: int = Form(10_000),
              replicates: int = Form(3),
              width: int = Form(4),
              engine: str = Form("pf"),
              mode: str = Form("resume"),
              confirm: str = Form("")):
    """Start (or resume) a season replay.

    `national`: fit US too (default, like the Forecast tab); "0" = states
    only (a resumed 52-jurisdiction run posts its recorded answer).

    `mode`, the only way an existing season tree is moved or removed:

      resume   completed weeks are kept and skipped
      archive  move the current tree to a timestamped sibling, then run clean
      discard  delete the current tree (confirmation required), then run clean
    """
    from app.core import retro
    from app.core.retro import available_seasons
    _invalidate_scans()
    if not _valid_season(season):
        _flash("Unrecognized season name. Nothing was started.")
        return RedirectResponse("/retro", status_code=303)
    # busy checks, the archive/discard move and the claim all run under
    # _engine_lock (the move is part of claiming the tree); the worker does not
    with _engine_lock:
        if _season_status(season) in _RETRO_ACTIVE:
            _flash(f"{season} is already replaying (status: "
                   f"{_season_status(season)}). One season worker runs at a "
                   "time; stop it first if you want to start over.")
            return RedirectResponse("/retro", status_code=303)
        # server-side mirror of /api/busy (see _engine_lock)
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
            _flash(f"Season {season} is not available. A season appears once "
                   "its vintage archive exists.")
            return RedirectResponse("/retro", status_code=303)
        if engine not in retro.ENGINES:
            # a future pf2s preset: accept it here, pass {"variant": "2strain"}
            # through retro.run_week's RunSpec, collect it beside pf
            _flash("The engine presets for a retrospective are the Oracle "
                   "SIHRS and the Groundhog, or the Groundhog alone.")
            return RedirectResponse("/retro", status_code=303)
        from app.core import us_national as usn
        all_states = _retro_state_names()
        if locations == "all":
            names = list(all_states)
        elif locations == "custom":
            # a resumed run resubmits its list verbatim, US included
            names = [n for n in custom_locations
                     if n in set(all_states) or usn.is_us(n)]
            if not names:
                _flash("Custom scope selected but no locations were checked. "
                       "Check at least one state and try again.")
                return RedirectResponse("/retro", status_code=303)
        else:
            names = ["Alaska", "New York", "Wyoming", "Pennsylvania",
                     "Vermont", "California"]
        # US rides on every scope unless states only (with_us is idempotent)
        fit_national = str(national).strip().lower() not in ("0", "false",
                                                             "no", "off", "")
        if fit_national:
            names = usn.with_us(names, _retro_national_name())
        # keep the knobs inside what the machine survives (budget: 0.45 fits/min)
        particles = max(1_000, min(int(particles), 100_000))
        replicates = max(1, min(int(replicates), 10))
        width = max(1, min(int(width), 16))
        # start-over handling only AFTER all validation
        live = _live_root(season)
        existing = _weeks_done(live)
        if mode == "resume" and existing:
            # never resume a tree with the other engine preset (weeks would be
            # skipped as done or mislabeled); the record says what ran
            was = str((retro.read_meta(live) or {}).get("settings", {})
                      .get("engine") or "pf")
            if was != engine:
                _flash(f"{season} has {existing} completed week"
                       f"{'' if existing == 1 else 's'} replayed with the "
                       f"{retro_engine_label(was)} preset; the "
                       f"{retro_engine_label(engine)} preset cannot resume "
                       "them. Archive or discard the existing results to "
                       "run it. Nothing was started.")
                return RedirectResponse("/retro", status_code=303)
        if mode == "discard":
            if confirm != season:
                _flash(f"Discarding {season} was not confirmed, so nothing "
                       "was deleted and nothing was started.")
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
                       f"{'' if existing == 1 else 's'} of {season}. Starting "
                       "a fresh replay.")
        elif mode == "archive" and existing:
            try:
                dst = retro.archive_run(RETRO_ROOT, season)
            except Exception as e:
                # the move is atomic: a failure leaves the original whole
                _flash(f"Could not archive {season}: {type(e).__name__}: "
                       f"{str(e)[:160]}. Nothing was started; the existing "
                       "results are intact.")
                return RedirectResponse("/retro", status_code=303)
            _flash(f"Archived {existing} completed week"
                   f"{'' if existing == 1 else 's'} of {season} as "
                   f"{dst.name}; it stays viewable from the season list. "
                   "Starting a fresh replay.")
        # claim in the request (not the task) so double submits cannot race
        _invalidate_scans()
        _retro_status[season] = "running"
        _retro_claim_at[season] = time.time()
    # recorded settings the location list alone cannot say
    background.add_task(_retro_bg, season, names, width, replicates, particles,
                        {"scope": locations, "engine": engine,
                         "national": bool(fit_national)}, engine)
    return RedirectResponse("/retro", status_code=303)


#: the retrospective engine presets as the form and the record name them
RETRO_ENGINE_LABELS = {"pf": "Oracle SIHRS and the Groundhog",
                       "analogue": "Groundhog only"}


def retro_engine_label(engine: str) -> str:
    return RETRO_ENGINE_LABELS.get(str(engine), str(engine))


# === Retrospective season page (/retro/{season}) and its APIs -> retro_season.html ===
@app.get("/retro/{season}", response_class=HTMLResponse)
def retro_results(request: Request, season: str, week: str = "",
                  archive: str = "", conv: str = ""):
    """The season results page; `archive` selects an archived run's tree.
    `conv` picks the ONE relWIS convention (app/core/relwis) for the whole
    page: ratio of sums (default) or the CDC's pairwise figure, never mixed;
    panels it cannot express say so."""
    import pandas as pd
    from app.core import relwis
    from app.core import retro
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        _flash("Unrecognized archived run identifier.")
        return RedirectResponse("/retro", status_code=303)
    root, _is_seal = _season_root(season, archive)
    # this tree's names, passed as model_name (shadows the global)
    names = _names_for_root(root)
    weeks = [p.parent.name for p in retro.season_sample_files(root)]
    if not weeks:
        # back to the season list, which shows a 0-weeks season
        _flash(f"{season}: no completed weeks yet. Start the replay and "
               "check back shortly." if not archive else
               f"{season}: that archived run has no completed weeks, or it "
               "has been deleted.")
        return RedirectResponse("/retro", status_code=303)
    score_error = ""
    # Heavy scoring never runs in-request: stale caches or ?rescore=1 start
    # the background finalize job and the page shows a polled preparing
    # state (after a short grace wait). A job covering these exact inputs is
    # believed, so an unsettled-truth season never loops.
    if ((request.query_params.get("rescore") and not _is_sealed_root(root))
            or _results_pending(root)):
        job = _ensure_results_job(
            root, season, force=bool(request.query_params.get("rescore")))
        job["done"].wait(_RESULTS_GRACE_S)
        if not job["done"].is_set():
            return templates.TemplateResponse(request, "retro_season.html", {
                "active": "Retrospective", "season": season,
                "model_name": _name_fn(names),
                "preparing": {"phase": job["phase"],
                              "elapsed_s": round(time.time() - job["t0"], 1)},
                "archive": archive,
                "archive_when": retro.stamp_human(archive) if archive else "",
                "heads": {}, "curve": [], "curves": {}, "states": [],
                "season_models": [], "member_colors": _member_colors(),
                "us_row": None,
                "us": None, "pooled_note": "",
                "conv": relwis.DEFAULT_CONVENTION, "figs": None,
                "weeks": weeks, "week": weeks[-1], "map_html": "",
                "official_catalog": [], "prog": None, "n_weeks": 0})
        if job["error"]:
            # show the failure, never pass it off as "truth not settled"
            score_error = job["error"]
    else:
        covered = _job_covered(root)
        if covered and covered.get("error") and not _scores_scoreable_fast(root):
            score_error = covered["error"]
    from app.core import us_national as usn
    df_all = _scores_df(root)
    if df_all is None:
        df_all = pd.DataFrame()
    # THE pooled gate: every figure below uses the 52-jurisdiction frame; the
    # national row is resolved separately, so fitting US never moves the headline
    df = usn.pooled_frame(df_all)
    heads, curve, states = {}, [], []
    curves: dict = {}
    scoreable = (not df.empty) and ("model" in df.columns)
    # THE convention gate: one figures object for tiles and table; with no
    # numbers (pairwise without field data) the page says why, never falls back
    convention = relwis.convention_of(conv)
    figs = _relwis_figures(root, convention) if scoreable else None
    # a season scored before 2026-09-22 also carries the retired blend's
    # rows; they are read (scoring stays whole) but never shown
    from app.core.report_v2 import RETIRED_MODELS
    if figs is not None and figs.available:
        heads = {m: v for m, v in figs.values.items()
                 if m not in RETIRED_MODELS}
        states = list(figs.states)
    if scoreable and convention == relwis.RATIO_OF_SUMS:
        # the cumulative curve is a running ratio of sums: this convention only
        asofs = sorted(df["asof"].unique())
        # one line per shipped model in the frame (relwis.MODELS order)
        for m in relwis.MODELS:
            if m in RETIRED_MODELS:
                continue
            g = df[df.model == m]
            if not len(g):
                continue
            cum = g.groupby("asof")[["wis", "base_wis"]].sum() \
                   .sort_index().cumsum()
            cum = cum.reindex(asofs).ffill().dropna()
            curves[m] = [(str(a)[:10], r.wis / r.base_wis)
                         for a, r in cum.iterrows()]
        curve = curves.get("pf") or next(iter(curves.values()), [])
    # national series via usn.resolve (fitted > constructed > officials), with
    # its provenance label printed; a failure never costs the page
    us = None
    if scoreable:
        try:
            us = usn.resolve(root, df_all)
        except Exception:
            us = None
    # us_row (member -> relWIS plus provenance) is a ratio of sums, so it is
    # offered to that convention only; `us` resolves either way for the player
    us_row = (us.as_dict() if (us is not None and us.has_scores
                               and convention == relwis.RATIO_OF_SUMS)
              else None)
    wk = week if week in weeks else weeks[-1]
    from app.core.usmap import svg_map
    locs = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
    n2a = dict(zip(locs.location_name, locs.abbreviation))
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    by_model = _week_map_cards_by_model(root, wk)
    map_models = _retro_map_models(by_model)
    cards = dict(by_model[map_models[0]]) if map_models else {}
    for name, abbr in n2a.items():
        cards.setdefault(n2f.get(name, name), {"name": name, "abbr": abbr,
                                               "fips": n2f.get(name, "")})
    # model switch (home's control) when the week stored >= 2 models
    map_toggle = ""
    if len(map_models) >= 2:
        from app.core import report_v2
        from app.core import usmap as _usmap
        # report_v2.MODEL_LABEL, with pf's following this tree's name
        map_labels = dict(report_v2.MODEL_LABEL)
        if names.get("pf") != _model_names().get("pf"):
            map_labels["pf"] = f"{names['pf']} outlook"
        map_toggle = _usmap.model_toggle(
            map_models, map_labels, map_models[0],
            {m: {"states": _usmap.state_swap_payload(by_model[m]), "us": {}}
             for m in map_models},
            group_id="retro-model", btn_class="quiet",
            active_class="gold", wrap_class="row viewtabs")
    map_html = map_toggle + svg_map(cards)
    if not scoreable and not score_error:
        # scored zero cells with no exception: diagnose WHICH input is empty
        try:
            from app.core.scoring import load_truth as _lt
            truth_d, n2f_d = _lt()
            d0 = retro.read_week_samples(root, weeks[len(weeks)//2])
            import numpy as _dn
            pos_med = sum(1 for loc, sm in d0.get("pf", {}).items()
                          for h in ("1",)
                          if _dn.median(_dn.asarray(sm[h], float)) > 0)
            # walk ONE cell through every scoring step and name its killer
            import pandas as _dp
            from app.core import ensemble as _de
            from app.core.scoring import _baseline_cells as _dbc
            from flubnf.wis import wis as _dwis
            loc0 = sorted(d0.get("pf", {}))[0]
            fips0 = n2f_d.get(loc0)
            T0 = _dp.Timestamp(d0["asof"])
            q0 = _de.member_quantiles_from_samples(d0["pf"][loc0]).get("0", {})
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
            # zero cells is benign only when truth has not settled: only then
            # the calm "No scoreable weeks yet" text. Probe the earliest week
            # too (its truth may have settled while the middle week's has not).
            d_first = retro.read_week_samples(root, weeks[0])
            Tf = _dp.Timestamp(d_first["asof"])
            have_truth = sum(
                1 for dd, TT in ((d0, T0), (d_first, Tf))
                for loc in dd.get("pf", {})
                if truth_d.get((n2f_d.get(loc),
                                TT + _dp.Timedelta(days=7))) is not None)
        except Exception as pe:
            probe = f"diagnostic probe failed: {type(pe).__name__}: {str(pe)[:120]}"
            have_truth = -1      # unknown: surface the probe, never the calm text
        if have_truth != 0:
            score_error = "scored zero cells with no exception. " + probe
    if not scoreable and score_error:
        map_html = _scoring_failed_hint(score_error)
    elif not scoreable:
        map_html = ("<p class='hint'>No scoreable weeks yet. Truth for "
                    "these forecast dates has not settled, so relWIS arrives "
                    "later; the weekly maps below are available now.</p>") + map_html
    # comparators that submitted at least once this season (player toggles)
    from app.core import playback as _playback
    try:
        official_catalog = _playback.season_official_catalog(root)
    except Exception:
        official_catalog = []
    return templates.TemplateResponse(request, "retro_season.html", {
        "active": "Retrospective", "season": season, "heads": heads,
        "model_name": _name_fn(names),
        "curve": curve, "curves": curves, "states": states,
        "member_colors": _member_colors(),
        # the shipped models this season scored, in table order
        "season_models": [m for m in relwis.MODELS
                          if m not in RETIRED_MODELS
                          and (m in heads or m in curves
                          or any((r.get(m) if isinstance(r, dict)
                                  else getattr(r, m, None))
                                 for r in states))],
        "us_row": us_row,
        # provenance travels WITH the numbers (fitted vs constructed)
        "us": (us.as_dict() if us is not None
               else usn.UsNational(usn.OFFICIALS_ONLY).as_dict()),
        "pooled_note": usn.POOLED_SCOPE_NOTE,
        "conv": convention, "figs": figs,
        "weeks": weeks, "week": wk, "map_html": map_html,
        "official_catalog": official_catalog,
        "prog": (_archive_progress(root, season) if archive
                 else _retro_progress(season)),
        "archive": archive,
        "archive_when": retro.stamp_human(archive) if archive else "",
        "n_weeks": len(weeks) if scoreable else 0})


@app.get("/api/retro/{season}/playback/{asof}")
def api_retro_playback(season: str, asof: str, archive: str = ""):
    """One stored retro week as a playback payload (member fans, settled
    truth, CDC comparators, running relWIS), cached under
    <season_root>/playback_cache/. `archive` reads an archived run."""
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


@app.get("/api/retro/{season}/mapswap/{asof}")
def api_retro_mapswap(season: str, asof: str, archive: str = ""):
    """One stored week's map as a swap payload (fips -> fill, opacity,
    hover) from the cached cards: the player renders the SVG once and
    swaps fills per frame."""
    from fastapi.responses import PlainTextResponse
    from app.core.usmap import state_swap_payload
    if archive and not (_valid_season(season) and _valid_archive(archive)):
        return PlainTextResponse("unrecognized archived run identifier",
                                 status_code=404)
    # the week is a path segment: date-shaped only
    import re as _re
    if not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", asof):
        return PlainTextResponse(f"no stored week {asof}", status_code=404)
    root, _is_seal = _season_root(season, archive)
    from app.core import retro as _retro
    if _retro.week_samples_path(root, asof) is None:
        return PlainTextResponse(f"no stored week {asof}", status_code=404)
    by_model = _week_map_cards_by_model(root, asof)
    order = _retro_map_models(by_model)
    models = {m: {"states": state_swap_payload(by_model[m])} for m in order}
    default = order[0] if order else ""
    # `states`: the default model's (the pre-per-model shape)
    return {"default": default, "models": models,
            "states": (models[default]["states"] if default
                       else state_swap_payload({}))}


@app.get("/retro/{season}/report")
def retro_season_report(season: str, archive: str = ""):
    """Build (cached by mtime) and download the self-contained season report
    (player plus every week's data, one HTML file); `archive` = that run's."""
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
    """Build the season report if absent and return its path (the results
    page's Reveal button posts it to /output/reveal)."""
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


# === Forecast: POST /run (form and rerun entry to _run_all) ===
@app.post("/run")
def run_models(request: Request,
               background: BackgroundTasks,
               forecast_date: str = Form(...),
               locations: list = Form([]),
               weeks_to_drop: int = Form(0),
               weeks_to_nowcast: int = Form(0),
               replicates: int = Form(3),
               engine: str = Form("all"),
               members: int = Form(2),
               particles: int = Form(10_000),
               season_start: str = Form(""),   # blank = Aug 1 of the season
               mode: str = Form("realtime"),   # recorded: vintage or real-time
               # re-run-only fields (not on the form): None/0 = today's
               # shipped config; /runs/{id}/rerun passes the row's values
               drop_same_day: int = Form(0),
               aux: str | None = Form(None),    # Groundhog donors; "" = bare
               oracle: str | None = Form(None)):  # "none" = plain filter
    # non-Saturdays snap via resolve_anchor; a typed Saturday is honoured or
    # refused below (never re-aimed)
    from datetime import date as _date
    try:
        _d = _date.fromisoformat(forecast_date)
        if _d.weekday() != 5:
            # the form already shows this anchor; no banner
            _pick, _ = resolve_anchor(forecast_date)
            forecast_date = _pick or forecast_date
    except ValueError:
        pass
    try:
        data_mod.vintage_path(forecast_date)
    except Exception:
        # archive gaps are real (holiday weeks): suggest the nearest EARLIER
        # vintage only; a later one would leak hindsight
        vs = data_mod.vintages()
        earlier = [v for v in vs if v <= forecast_date]
        near = max(earlier) if earlier else (min(vs) if vs else None)
        if near and _last_form:
            _last_form["forecast_date"] = near
        if not vs:
            _flash(f"No archived data for {forecast_date}. Pull the "
                   "FluSight hub on the Data tab first.")
        elif earlier:
            _flash(f"The FluSight hub archived no data snapshot dated "
                   f"{forecast_date}; such gaps are real, usually holiday "
                   "weeks. The graphs still show a point at that date "
                   "because they draw today's settled data, which was not "
                   "yet reported on the day itself. Nearest earlier "
                   f"archived Saturday: {near}. A later one would leak a "
                   "week of hindsight, so it is not offered.")
        else:
            _flash(f"No archived data for {forecast_date}; the archive "
                   f"starts at {near}.")
        return _back(request, "/forecast")
    # season start: blank = RunSpec's Aug 1 rule; a typed value must precede
    # the forecast week by < 400 days, else refused out loud and defaulted.
    # A direct call (rerun) may pass the Form default object: treat as blank.
    season_start = (season_start if isinstance(season_start, str) else "").strip()
    if season_start:
        from datetime import date as _sd, timedelta as _std
        try:
            _ss, _fd = _sd.fromisoformat(season_start), _sd.fromisoformat(forecast_date)
            if not (_fd - _std(days=400) <= _ss < _fd):
                raise ValueError("outside the allowed window")
        except (ValueError, TypeError):
            _flash(f"Season start {season_start} is not a date before the "
                   f"forecast week and within 400 days of it; using "
                   f"{_runs.default_season_start(forecast_date)}.")
            season_start = ""
    _last_form.update({"forecast_date": forecast_date, "locations": locations,
                       "engine": engine, "weeks_to_drop": weeks_to_drop,
                       "weeks_to_nowcast": weeks_to_nowcast,
                       "replicates": replicates, "members": members,
                       "season_start": season_start})
    # checkboxes arrive as a list, text inputs as comma-separated strings
    locations = [x.strip() for l in locations
                 for x in str(l).split(",") if x.strip()]
    if not locations:
        _flash("Select at least one location, or all 52 jurisdictions. "
               "Nothing was run.")
        return _back(request, "/forecast")
    # busy check + claim under _engine_lock (see its comment)
    with _engine_lock:
        if _status.get("running"):
            _status["log"].append("A run is already in progress; not starting another.")
            return RedirectResponse("/forecast#results", status_code=303)
        live_retro = sorted(x for x in _known_seasons()
                            if _season_status(x) in _RETRO_ACTIVE)
        if live_retro:
            _flash("A retrospective replay holds the engine ("
                   + ", ".join(live_retro) + "). Stop or pause it from the "
                   "Retrospective tab first; nothing was run.")
            return _back(request, "/forecast")
        # background tasks fire after the redirect: claim NOW so the landing
        # page shows the run
        _status["running"] = "starting"
        _invalidate_scans()
        _status["started_utc"] = __import__("time").time()
        _status["run_label"] = f"{forecast_date} · queued"
    from app.core import us_national as _usn
    if "all" in [l.lower() for l in locations]:
        _l = __import__("flubnf.settings", fromlist=["load_locations"]).load_locations()
        locs_list = list(_l.location_name[(_l.location.str.len() == 2)
                                          & (_l.abbreviation != "US")])
        us = _l.location_name[_l.abbreviation == "US"]
        if len(us):
            locs_list.append(str(us.iloc[0]))   # national, fitted directly
    else:
        locs_list = list(locations)
    # national always fitted (as on the Retrospective tab)
    locs_list = _usn.with_us(locs_list)
    n_states = len(_usn.state_names(locs_list))
    _status["run_label"] = f"{forecast_date} · {n_states} state(s) + US · queued"
    # progress denominator known now (shards grow toward it); clear the old
    # workroot so its .prog files never show. The analogue alone gets none.
    _status["workroot"] = None
    _status["expected_total"] = (len(locs_list) * int(replicates)
                                 * (2 if members == 3 else 1)
                                 if engine in ("all", "pf") else None)
    # particles: only the research form posts it; clamped like the retro form
    asked = int(particles)
    particles = max(1_000, min(asked, 100_000))
    if particles != asked:
        _flash(f"Particles clamped from {asked:,} to {particles:,}, the range "
               "this machine survives.")
    # clamp every form number server-side (replicates = 0 once ran zero fits)
    replicates = max(1, min(int(replicates), 9))
    weeks_to_drop = max(0, min(int(weeks_to_drop), 4))
    # mode follows the anchor: real-time means the newest archived vintage
    try:
        newest = data_mod.vintages()[-1]
    except Exception:
        newest = None
    if newest and mode == "realtime" and forecast_date != newest:
        mode = "vintage"
        _flash(f"Anchored on the archived week {forecast_date}, not the "
               f"newest vintage ({newest}): recorded as a vintage run.")
    spec = RunSpec(engine=engine, forecast_date=forecast_date,
                   locations=locs_list,
                   season_start=season_start,
                   weeks_to_drop=weeks_to_drop,
                   weeks_to_nowcast=weeks_to_nowcast,
                   drop_same_day=bool(int(drop_same_day)),
                   replicates=replicates,
                   particles=particles,
                   extra=_run_extra(members, mode, aux, oracle))

    if engine in ("all", "pf", "analogue"):
        # 'analogue' = the same pipeline with the PF block skipped
        background.add_task(_run_all, spec)
    else:
        # unknown engine: release the claim rather than wedge the console
        _status["running"] = None
        _status["run_label"] = ""
        _status["expected_total"] = None
        _status["started_utc"] = None
        _flash(f"'{engine}' is not one of the available engines. "
               "Nothing was run.")
    return RedirectResponse("/forecast#results", status_code=303)


# === Startup warm (LAST, so every function it reaches is defined) ===
_trace("import complete, starting background warm")
_start_background_warm()
