"""PRODUCTION: the season report download (server /retro/{season}/report).

The season report is the Retrospective season page as one self-contained
HTML file: app/ui/season_export renders retro_season.html in export mode
from the page's own context, with every stored week's playback payload and
categorical map embedded, and every stylesheet, script, font and mark
written into the page. So the file shows what the console shows (the
season scores, the season player with its forecast detail open first and
the categorical map a click away, the live scores, the cumulative chart,
the per-state table) and needs no server or network. Parity with the page
is held section by section by app/tests/test_report_parity.py.

This module keeps the names and the coverage reading the page and the
player share, and builds, caches and invalidates the file:

  1. names and inputs: model_names, names_for_root, report_path,
     _newest_input
  2. the coverage reading shared with the season page: cov_state, cov_text,
     COV_LEGEND, PSTATES_COV_NOTE, METRICS_NOTE, LIVE_HEADING,
     LIVE_SCORES_NOTE; and its cumulative lines, cumulative_curves
  3. build_season_report: cached at <season_root>/<season>-FluBNF-season-
     report.html while newer than every input and carrying the current
     marker (_report_marker)
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from app.core import html_page, playback, report_v2, retro

# ---------------------------------------------------- 1. names and inputs
# the player's member colours (report_v2.model_colors); officials stay grey
MODEL_COLORS = report_v2.model_colors()

# the shared player, inlined verbatim so both hosts run identical code
PLAYER_SRC = html_page.PLAYER_SRC


def model_names() -> dict:
    """The one model-name map: player.js's marked JSON literal, parsed so
    every Python surface uses the player's names. {} (raw ids) on failure."""
    return html_page.marked_json("MODEL_NAMES_JSON", {}, PLAYER_SRC)


# display names for the static summary: the player's own map, one source
MODEL_NAMES = model_names()


def names_for_root(root: Path, base: dict | None = None) -> dict:
    """The model-name map for ONE season tree: `base` (the shared map by
    default) with pf named for what the tree stores.

    pf is "Oracle SIHRS" only when the tree carries the Oracle step
    (site_build.tree_carries_oracle); sealed records and older replays
    store the plain filter, named site_build.PF_LABEL_FILTER (also when the
    tree is unreadable). Returns a copy: requests run on several threads."""
    from app.core import site_build
    names = dict(MODEL_NAMES if base is None else base)
    try:
        carries = site_build.tree_carries_oracle(Path(root))
    except Exception:
        carries = False
    if not carries:
        names["pf"] = site_build.PF_LABEL_FILTER
    # a replay with modified model settings never wears the shipped names
    rec = site_build.tree_knobs(Path(root))
    if rec:
        from app.core import knobs as _knobs
        hit = set()
        for key in rec:
            k = _knobs.BY_KEY.get(key)
            hit |= set(k.affects) if k else set(_knobs.MEMBERS)
        for m in sorted(hit):
            if m in names:
                names[m] = f"{names[m]} (modified settings)"
    return names


def report_path(root: Path, season: str) -> Path:
    return Path(root) / f"{season}-FluBNF-season-report.html"


def _newest_input(root: Path) -> float:
    """Newest mtime among the export's inputs: stored weeks, scores.json,
    settled truth, player.js, charts.js, this builder and html_page, the
    season page's template, route, styles and scripts,
    playback_cache/*.json, the hub's official model-output dirs (new
    comparators land there before any cache rebuild), run_meta.json (wall
    time) and nau.css (theme tokens).
    """
    from app.core.data import truth_mtime
    times = [p.stat().st_mtime for p in retro.season_sample_files(root)]
    times.append(truth_mtime())          # the report scores against it
    ui = Path(__file__).resolve().parents[1] / "ui"
    files = [root / "scores.json", PLAYER_SRC, html_page.CHARTS_SRC,
             Path(__file__), Path(html_page.__file__), root / retro.META_NAME,
             html_page.NAU_CSS,
             # the season page it renders (app/ui/season_export)
             ui / "season_export.py", ui / "routes" / "retro.py",
             ui / "templates" / "retro_season.html",
             ui / "templates" / "base.html", ui / "templates" / "_tips.html",
             ui / "static" / "ui-kit.css", ui / "static" / "tips.js",
             ui / "static" / "tabs" / "retro.css"]
    times.extend(p.stat().st_mtime for p in files if p.is_file())
    pc = root / "playback_cache"
    if pc.is_dir():
        times.extend(f.stat().st_mtime for f in pc.glob("*.json"))
    try:
        from flubnf.settings import HUB
        for name in ("FluSight-ensemble", "FluSight-baseline"):
            d = HUB / "model-output" / name
            if d.is_dir():
                times.append(d.stat().st_mtime)
    except Exception:
        pass
    return max(times)


# ------------------------------------------------- 2. the coverage reading
#: the player's stats card: heading and explanation, one copy for the season
#: page (Jinja globals) and this export
LIVE_HEADING = "Live scores"
LIVE_SCORES_NOTE = (
    "relWIS below 1 beats the CDC FluSight baseline, ratio of sums over "
    "the cells both scored, US left out. The log scale scores log(x+1) "
    "counts, so small states weigh more. Coverage is the share of those "
    "cells whose truth fell inside each central interval; a calibrated "
    "forecast sits near 50, 80 and 95%. Season so far pools every week up "
    "to this one.")

#: the central intervals whose coverage the verdicts print, key and level
COV_LEVELS = (("50", 50), ("80", 80), ("95", 95))
#: points from its interval's level within which a coverage reads ok
#: (player.js COV_TOL; a test holds the two equal), narrowed near 100 by
#: cov_tolerance
COV_TOLERANCE = 5


def cov_tolerance(level) -> float:
    """The ok band around an interval's level: COV_TOLERANCE points, or half
    the room above the level when that is less (2.5 at 95%), so a 95%
    interval that never misses reads too wide (player.js covTol)."""
    return min(COV_TOLERANCE, (100 - int(level)) / 2)


def cov_pct(frac) -> int | None:
    """A coverage fraction as the whole percentage printed (halves round
    up, as player.js Math.round does), or None."""
    try:
        f = float(frac)
    except (TypeError, ValueError):
        return None
    return math.floor(100 * f + 0.5) if math.isfinite(f) else None


def cov_state(frac, level) -> str:
    """THE coverage reading (player.js covState): "ok" within
    cov_tolerance(level) points of the interval's level, "low" further
    under (too narrow), "wide" further over (too wide), "" without a
    figure. Judged on the printed percentage, so a cell never wears a color
    its number contradicts. Also a Jinja global (the season page)."""
    p = cov_pct(frac)
    if p is None:
        return ""
    tol = cov_tolerance(level)
    if p < int(level) - tol:
        return "low"
    if p > int(level) + tol:
        return "wide"
    return "ok"


#: the coverage colors' key: the line player.js covLegend writes under the
#: live table (a test holds the two equal), also under the verdict tiles
COV_LEGEND = (
    f'Coverage color: <span class="cov-ok">within {COV_TOLERANCE} points of '
    f"nominal ({cov_tolerance(95):g} at 95%)</span> · "
    '<span class="cov-low">further under (too narrow)</span> · '
    '<span class="cov-wide">further over (too wide)</span>.')

#: the per-state tables' 95% column, said once above the table (the page
#: and this export): the whole percentages the key's rule gives at 95%
PSTATES_COV_NOTE = (
    "95%: the share of the state's scored cells inside the central 95% "
    f"interval; {math.ceil(95 - cov_tolerance(95)) - 1}% or less is too "
    f"narrow, {math.floor(95 + cov_tolerance(95)) + 1}% or more too wide.")


def cov_text(frac) -> str:
    """"48%", or "n/a" without a figure. Also a Jinja global."""
    p = cov_pct(frac)
    return "n/a" if p is None else f"{p}%"


#: what the tiles' second line holds, said once under them
METRICS_NOTE = ("Log scale: the same ratio on the WIS of log(x+1) counts. "
                "Coverage: the share of the same cells whose truth fell "
                "inside the central 50, 80 and 95% intervals.")


def cumulative_curves(df) -> dict:
    """The season page's cumulative relWIS lines: {model: [(iso week,
    running ratio of sums)]} per shipped model in the scores frame
    (relwis.MODELS order, the retired blend left out). Pooled over the
    jurisdictions only (us_national.pooled_frame): a fitted US cell never
    moves a line."""
    from app.core import relwis
    from app.core import us_national as usn
    from app.core.report_v2 import RETIRED_MODELS
    df = usn.pooled_frame(df)
    curves: dict = {}
    if df is None or df.empty or "model" not in df.columns:
        return curves
    asofs = sorted(df["asof"].unique())
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
    return curves


# ------------------------------------------------------- 3. the export
#: the report's format and what it was built for, written into the file;
#: a cached report without the current marker is rebuilt
REPORT_MARK = "flubnf-season-report 2"


def _report_marker(archive: str, names: dict) -> str:
    """The marker line for one build: the format, the archived run, and the
    names the tree gives its models (pf's follows the Oracle step)."""
    tag = json.dumps({"archive": archive or "", "names": names},
                     sort_keys=True, separators=(",", ":"))
    return f"<!-- {REPORT_MARK} {tag.replace('--', '- -')} -->"


def build_season_report(root: Path, season: str, archive: str = "",
                        build: str = "", versions: dict | None = None) -> Path:
    """Build (or reuse, when fresh) the season report: the Retrospective
    season page as one self-contained file (app/ui/season_export), cached
    beside the season's weeks.

    `archive` names the archived run `root` is. `build` and `versions` are
    accepted for older callers and not printed: the file names the build
    that exported it, and the engine build recorded with the season (its
    run settings), never this machine's installed engine."""
    root = Path(root)
    weeks = playback.season_weeks(root)
    if not weeks:
        raise playback.UnknownWeek(
            f"{season}: no completed weeks yet, so there is no season "
            "report to build.")
    out = report_path(root, season)
    marker = _report_marker(archive, names_for_root(root))
    if out.is_file() and out.stat().st_mtime >= _newest_input(root):
        # mtime is not enough: an archived copy keeps its old mtime, and
        # coarse (Windows) timestamps can tie with run_meta
        if marker in out.read_text(encoding="utf-8"):
            return out
    from app.ui.season_export import render_season_report
    html = render_season_report(root, season, archive) + "\n" + marker + "\n"
    # atomic: two concurrent downloads must never interleave a garbled file
    tmp = out.with_suffix(".html.tmp")
    # LF pinned: served as text and downloaded raw, which must match on Windows
    tmp.write_text(html, encoding="utf-8", newline="\n")
    os.replace(tmp, out)
    return out
