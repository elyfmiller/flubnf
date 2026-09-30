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
# the notice's kit alert kind (shared._flash), read with it
templates.env.globals["pop_flash_kind"] = lambda: _status.pop("flash_kind", None) or "info"
# its optional detail (shared._flash(detail=)), the alert's "?" tip
templates.env.globals["pop_flash_detail"] = lambda: _status.pop("flash_detail", None) or ""
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

    Windows gets the engine file from the lab and FluBNF.bat, which unpacks
    it (no setup_engine.sh twin; setup.ps1 only diagnoses, and the GitHub
    routes need access to the private fork, so docs/ENGINE.md keeps them).
    Resolved per render via _platform() so tests can vary it. Not for
    methods.html: site_build publishes that page, and a platform-specific
    string would bake in the builder's platform.
    """
    from markupsafe import Markup
    from app.core import engine_build
    if _platform() == "win32":
        return Markup(
            "save the engine file from the lab (<code>"
            f"{engine_build.archive_name()}</code>) in your Downloads folder "
            "and open <code>FluBNF.bat</code> again; no GitHub account is "
            "needed (<code>docs\\ENGINE.md</code> has the GitHub routes)")
    if _platform() == "darwin":
        return Markup("double-click <code>SetupEngine.command</code> and "
                      "relaunch the console")
    return Markup("run <code>./setup_engine.sh</code> and relaunch the console")


def _perl_missing_hint() -> str:
    """The run preflight's Perl message (engines/pf.perl_missing_message) for
    this machine: Home's Setup card shows it when Perl is all that is
    missing, as on a first Windows open whose own PATH predates the
    Strawberry Perl it just installed."""
    from app.core.engines import pf
    return pf.perl_missing_message(_platform())


def _downloads_example(name: str) -> str:
    """An example path to `name` in this machine's Downloads folder, for a
    path field's placeholder."""
    if _platform() == "win32":
        return f"C:\\Users\\you\\Downloads\\{name}"
    if _platform() == "darwin":
        return f"/Users/you/Downloads/{name}"
    return f"/home/you/Downloads/{name}"


templates.env.globals["engine_setup_hint"] = _engine_setup_hint
templates.env.globals["perl_missing_hint"] = _perl_missing_hint
templates.env.globals["downloads_example"] = _downloads_example

# build SHA and restart banner (app/ui/versions.py)
templates.env.globals["running_sha"] = lambda: versions.RUNNING_SHA
templates.env.globals["restart_needed"] = versions._restart_needed
# the engine checkout's branch and commit, and the non-production warning
# (templates/_engine_build.html)
templates.env.globals["engine_build_view"] = versions.engine_build_view
# one settings/results renderer for progress cards, run page and both report
# exports (app/core/runs.py), so their wording cannot diverge
templates.env.globals["settings_html"] = settings_html

# the exported season report (app/core/report_season) renders the season
# page as one self-contained file: every stylesheet and script it loads is
# written into the page, and the images and fonts those name become data
# URIs, so the file needs no server and no network
_STATIC = Path(__file__).parent / "static"
_MIME = {".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png",
         ".ico": "image/x-icon"}


def _data_uri(rel: str) -> str:
    """static/<rel> as a data: URI; the URL unchanged when unreadable."""
    import base64
    f = _STATIC / rel
    try:
        raw = f.read_bytes()
    except OSError:
        return "/static/" + rel
    mime = _MIME.get(f.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def inline_static(rel: str):
    """static/<rel> written into the page: a stylesheet as <style> (its
    /static/ url()s as data URIs), a script as <script>. "</" inside a
    script is split so it cannot end the element early."""
    import re
    from markupsafe import Markup
    text = (_STATIC / rel).read_text(encoding="utf-8")
    if rel.endswith(".css"):
        text = re.sub(r"""url\((["']?)/static/([^"')]+)\1\)""",
                      lambda m: f'url("{_data_uri(m.group(2))}")', text)
        return Markup(f"<style>\n{text}\n</style>")
    return Markup("<script>\n" + text.replace("</script", "<\\/script")
                  + "\n</script>")


templates.env.globals["inline_static"] = inline_static
templates.env.globals["static_data_uri"] = _data_uri
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

# THE scored-cell rule, one sentence (scoring.CELL_RULE_NOTE), for Methods;
# read at render time, so importing the console never loads pandas
def _cell_rule_note() -> str:
    from app.core.scoring import CELL_RULE_NOTE
    return CELL_RULE_NOTE


templates.env.globals["cell_rule_note"] = _cell_rule_note


# the season verdicts' coverage reading and the player's stats-card text,
# shared with the exported season report (app/core/report_season.py)
def _cov_state(frac, level) -> str:
    from app.core.report_season import cov_state
    return cov_state(frac, level)


def _cov_text(frac) -> str:
    from app.core.report_season import cov_text
    return cov_text(frac)


def _live_scores(what: str) -> str:
    """The stats card's and the verdicts' shared text: "heading", "note",
    "metrics" (what a tile's second line holds), "legend" (the coverage
    colors' key, markup) or "states" (the per-state 95% column)."""
    from app.core import report_season
    if what == "legend":
        from markupsafe import Markup
        return Markup(report_season.COV_LEGEND)
    return {"heading": report_season.LIVE_HEADING,
            "metrics": report_season.METRICS_NOTE,
            "states": report_season.PSTATES_COV_NOTE}.get(
                what, report_season.LIVE_SCORES_NOTE)


templates.env.globals["cov_state"] = _cov_state
templates.env.globals["cov_text"] = _cov_text
templates.env.globals["live_scores"] = _live_scores


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
