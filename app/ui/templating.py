"""The console's one Jinja environment and the helpers its pages share.

`templates` renders every page (and, through site_build, the public site).
Its globals and filters are registered here, each in the form it has always
had: function objects captured at registration, and late-bound lambdas
(model_name, running_sha, pop_flash) that read their name at render time.
server.py adds the two globals that belong to a tab (sandbox_storage,
dataset_upload_mb). Also here: the model-name and color maps, the season
month axis, and the harmonic figure's geometry.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.runs import fmt_hms, results_html, settings_html
from app.ui import versions
from app.ui.state import _status

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["pop_flash"] = lambda: _status.pop("flash", None)
# one wall-time format everywhere the console shows a duration
templates.env.filters["hms"] = fmt_hms


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

# build SHA and restart banner (app/ui/versions.py)
templates.env.globals["running_sha"] = lambda: versions.RUNNING_SHA
templates.env.globals["restart_needed"] = versions._restart_needed
# the engine checkout's branch and commit, and the non-production warning
# (templates/_engine_build.html)
templates.env.globals["engine_build_view"] = versions.engine_build_view
# one settings/results renderer for progress cards, run page and both report
# exports (app/core/runs.py), so their wording cannot diverge
templates.env.globals["settings_html"] = settings_html
templates.env.globals["results_html"] = results_html


# === Model names, relWIS/Oracle wording, member and season colors ===
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


# === Season month axis (the one source of month-boundary week offsets) ===
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
