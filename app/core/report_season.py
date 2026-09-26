"""PRODUCTION: the season HTML export (server /retro/{season}/report).

Season report export: one self-contained interactive HTML file.

The console's season player frozen into a download: plotly.js inline, every
stored week's playback payload embedded as JSON, and the SHARED player
(app/ui/static/player.js, the file the season page loads) inlined verbatim,
so player features reach the export automatically. Works offline.

Scope: the season verdict (tiles with log-scale relWIS and coverage, the US
national aggregate, per-state table), the forecast detail view and the live
scores table, held to the season page by app/tests/test_report_parity.py.
The cumulative chart and the categorical weekly maps stay on the season
page (size); anything else the page shows that the export cannot deliver
must be STATED, never silently absent.

Theme-aware like report_v2: nau.css token blocks embedded verbatim, the
shared boot script resolves the theme at open, and a print block flips to
the light theme. DM Sans with a system fallback, no webfont fetch.

Cached at <season_root>/<season>-FluBNF-season-report.html while newer than
every input (_newest_input) and carrying the current markers
(build_season_report).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from app.core import playback, relwis, report_v2, retro
from app.core import us_national as usn
from app.core.runs import fmt_hms, settings_html, version_pairs

# the player's member colours (report_v2.model_colors); officials stay grey
MODEL_COLORS = report_v2.model_colors()

SIZE_WARN_BYTES = 25 * 1024 * 1024

# the shared player, inlined verbatim so both hosts run identical code
PLAYER_SRC = report_v2.PLAYER_SRC


def model_names() -> dict:
    """The one model-name map: player.js's marked JSON literal, parsed so
    every Python surface uses the player's names. {} (raw ids) on failure."""
    import re
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*MODEL_NAMES_JSON\*/\s*(\{.*?\})"
                      r"\s*/\*END_MODEL_NAMES_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


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


def _plotlyjs() -> str:
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def _player_js() -> str:
    # FluCharts (charts.js) first: the player draws through it (Saturday
    # week ticks, the shared chart config), as on the console page
    return (report_v2.charts_js() + "\n"
            + PLAYER_SRC.read_text(encoding="utf-8"))


def _newest_input(root: Path) -> float:
    """Newest mtime among the export's inputs: stored weeks, scores.json,
    settled truth, player.js, charts.js, this builder, playback_cache/*.json,
    the hub's official model-output dirs (new comparators land there before
    any cache rebuild), run_meta.json (wall time) and nau.css (theme tokens).
    """
    times = [p.stat().st_mtime for p in retro.season_sample_files(root)]
    sf = root / "scores.json"
    if sf.is_file():
        times.append(sf.stat().st_mtime)
    from app.core.data import truth_mtime
    times.append(truth_mtime())          # the report scores against it
    if PLAYER_SRC.is_file():
        times.append(PLAYER_SRC.stat().st_mtime)
    if report_v2.CHARTS_SRC.is_file():
        times.append(report_v2.CHARTS_SRC.stat().st_mtime)
    src = Path(__file__)
    if src.is_file():
        times.append(src.stat().st_mtime)
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
    mp = root / retro.META_NAME
    if mp.is_file():
        times.append(mp.stat().st_mtime)
    if report_v2.NAU_CSS.is_file():
        times.append(report_v2.NAU_CSS.stat().st_mtime)
    return max(times)


def _timing_note(root: Path) -> str:
    """Header line: total wall time, weeks, mean per week. Absent without a
    run record (the sealed runs predate it)."""
    meta = retro.read_meta(root)
    if not meta:
        return ""
    t = retro.timing(meta)
    if not t["elapsed_s"] or t["elapsed_s"] < 1.0:
        return ""          # a sub-second record would print a fabricated zero
    bits = [f"Total wall time {fmt_hms(t['elapsed_s'])} (h:mm:ss)",
            f"{t['weeks_completed']} weeks completed"]
    if t["mean_s"]:
        bits.append(f"mean {t['mean_s']:.0f} s per week "
                    f"over {t['weeks_measured']} timed")
    return '<p class="sub">' + ", ".join(bits) + ".</p>"


#: the settings block's own marker, used both to render it and to decide
#: that a cached report predates it (see build_season_report)
SETTINGS_MARK = "Run settings"


def _settings_note(root: Path, build: str = "",
                   versions: dict | None = None) -> str:
    """The replay's settings, app build and engine versions, from the tree's
    own run record (so an archived run describes itself). Absent when the
    record has no settings."""
    pairs = retro.settings_summary(retro.read_meta(root))
    if not pairs:
        return ""
    return settings_html(pairs + version_pairs(build, versions),
                         title=SETTINGS_MARK, cls="sub")


def player_us_labels() -> dict:
    """The player's US provenance labels (its marked JSON literal), so a
    test can hold them equal to us_national.LABELS. {} on failure."""
    import re
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*US_LABELS_JSON\*/\s*(\{.*?\})"
                      r"\s*/\*END_US_LABELS_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


def _us_national(root: Path, df) -> tuple:
    """(us, reason) via us_national.resolve: fitted US cell, else the
    sum-of-states aggregate (computed when its cache is cold), else None
    with a printable reason. Never a silent omission."""
    if df is None:
        return None, ("the season has not been scored yet, and the national "
                      "figure joins the scored verdict table only")
    try:
        us = usn.resolve(root, df)
    except Exception as e:
        return None, ("its construction failed while this export was "
                      f"built ({type(e).__name__}: {str(e)[:120]})")
    if not us.has_scores:
        return None, (us.reason or "no scoreable national cells exist for "
                                   "this season")
    return us, ""


#: the season page's cumulative chart heading, verbatim (the parity test matches it)
CURVE_HEADING = "Cumulative relWIS through the season"

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
    """"48%", or a dash without a figure. Also a Jinja global."""
    p = cov_pct(frac)
    return "–" if p is None else f"{p}%"


def _cov_span(frac, level) -> str:
    st = cov_state(frac, level)
    return (f'<span class="cov-{st}">{cov_text(frac)}</span>' if st
            else f'<span class="hint">{cov_text(frac)}</span>')


#: what the tiles' second line holds, said once under them
METRICS_NOTE = ("Log scale: the same ratio on the WIS of log(x+1) counts. "
                "Coverage: the share of the same cells whose truth fell "
                "inside the central 50, 80 and 95% intervals.")


def _metrics_html(log_rel, cov) -> str:
    """The verdict tile's second line: log-scale relWIS and 50/80/95%
    coverage, each left out when the scores cannot give it (a season
    scored before these metrics)."""
    rows = []
    if log_rel is not None:
        rows.append('<dt>log scale</dt><dd class="'
                    + ("ok" if log_rel < 1 else "bad")
                    + f'">{log_rel:.3f}</dd>')
    if cov:
        rows.append("<dt>coverage 50/80/95%</dt><dd>"
                    + " · ".join(_cov_span(cov.get(k), lv)
                                 for k, lv in COV_LEVELS) + "</dd>")
    return ('<dl class="tilekv">' + "".join(rows) + "</dl>") if rows else ""

#: in order: the two shipped members, the research member. Older
#: scores.json files also carry the retired blend's rows; they are not shown.
SEASON_MODELS = ("pf", "analogue", "pf2s")


def _cumulative_curves(df) -> dict:
    """{model: [(iso week, cumulative relWIS)]} per SEASON_MODELS entry,
    the season page's series (mirrors app/ui/routes/retro.retro_results)."""
    if df is None or "model" not in getattr(df, "columns", ()):
        return {}
    # the pooled gate: a fitted US row never bends the line
    df = usn.pooled_frame(df)
    asofs = sorted(df["asof"].unique())
    out = {}
    for m in SEASON_MODELS:
        rows = df[df.model == m]
        if not len(rows):
            continue
        cum = (rows.groupby("asof")[["wis", "base_wis"]].sum()
               .sort_index().cumsum())
        cum = cum.reindex(asofs).ffill().dropna()
        out[m] = [(str(a)[:10], r.wis / r.base_wis)
                  for a, r in cum.iterrows()]
    return out


def _cumulative_curve(df) -> list:
    """The PF's cumulative series (else the first model's); used by tests
    since the curve left the export."""
    curves = _cumulative_curves(df)
    return curves.get("pf") or next(iter(curves.values()), [])


def _oracle_named(names: dict) -> bool:
    """True while pf wears the Oracle SIHRS name on this tree (the fitted
    US note applies only then; a tree without the step names pf for the
    filter already). player.js usPfNote makes the same test."""
    return "Oracle" in str(names.get("pf", ""))


def _summary_block(root: Path, weeks: list, payloads: dict,
                   names: dict | None = None) -> str:
    """The static season verdict, printed ahead of the player.

    Tiles: the final week's cum_rel, cum_log_rel and cum_cov (the numbers
    the player's last frame shows), plus the US tile/row with its
    provenance label (or a stated reason when absent). Per-state table
    from scores.json (pooled gate): relWIS and, when the scores carry it,
    95% coverage per member; or a statement when unscored. Names from
    `names` (names_for_root)."""
    names = names_for_root(root) if names is None else names
    final = payloads.get(weeks[-1]) or {}
    stats = final.get("stats") or {}
    tiles, more = [], []
    # any tile with coverage: the colors' key goes under the tiles
    tile_cov = False
    for m in SEASON_MODELS:
        st = stats.get(m) or {}
        v = st.get("cum_rel")
        if v is None:
            continue
        cls = "ok" if v < 1 else "bad"
        tile_cov = tile_cov or bool(st.get("cum_cov"))
        more.append(_metrics_html(st.get("cum_log_rel"), st.get("cum_cov")))
        tiles.append('<div class="tile"><div class="tilename">'
                     + names.get(m, m) + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div>'
                     + more[-1] + "</div>")
    # the weeks covered and the wall time are in the report header
    # (_timing_note), so the verdict does not repeat them
    rows = []
    cover = "every scored cell of the season"
    df_all = playback._season_scores(root)
    # pooled gate once; the national row is resolved separately
    df = usn.pooled_frame(df_all)
    us, us_reason = _us_national(root, df_all)
    # the models this season scored, in order, from its own rows
    have = ([m for m in SEASON_MODELS
             if "model" in getattr(df, "columns", ()) and (df.model == m).any()]
            if df is not None else [])
    # the fitted US row of Oracle SIHRS had no Oracle step (usn.PF_US_NOTE)
    pf_us_plain = bool(us and us.is_fitted and _oracle_named(names))
    for m in have:
        if not (us and us.get(m)):
            continue
        # always labelled fitted vs constructed: different model outputs
        v = us[m]
        cls = "ok" if v < 1 else "bad"
        sub = ("fitted at the national level, outside the pooled figures"
               if us.is_fitted else us.fallback_note
               + ", states treated as independent")
        if pf_us_plain and m == "pf":
            sub = usn.PF_US_SHORT + ", " + sub
        tile_cov = tile_cov or bool(us.cov(m))
        more.append(_metrics_html(us.log_rel(m), us.cov(m)))
        tiles.append('<div class="tile"><div class="tilename">'
                     + us.short_label + ": " + names.get(m, m)
                     + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div>'
                     + more[-1] + f'<div class="hint">{sub}</div></div>')
    if have:
        # cell coverage when the scores file supplies it
        n = int((df.model == have[0]).sum())
        if n:
            cover = (f"the season's {n} scored {names.get(have[0], have[0])}"
                     " cells")
    show_cov = False
    if df is not None and "location" in df.columns:
        # per-state figures (relWIS, log-scale relWIS, coverage) from the
        # one per-jurisdiction summary (retro.state_metrics)
        per_state = retro.state_metrics(df, tuple(have))
        # a 95% coverage column per member when the scores carry coverage
        # (a season scored before it has relWIS columns only)
        show_cov = any((r.get(m) or {}).get("cov")
                       for r in per_state.values() for m in have)

        def cells_for(rel, cov) -> str:
            out = ('<td class="num ' + ("ok" if rel < 1 else "bad")
                   + f'">{rel:.3f}</td>' if rel is not None
                   else '<td class="num hint">n/a</td>')
            if show_cov:
                c95 = (cov or {}).get("95")
                st = cov_state(c95, 95)
                out += (f'<td class="num cov-{st}">{cov_text(c95)}</td>'
                        if st else '<td class="num hint">–</td>')
            return out
        if us:
            # the national row leads as a distinct, labelled row (console placement)
            cells = [f"<td>{us.short_label}</td>"]
            for m in have:
                cells.append(cells_for(us.get(m) or None, us.cov(m)))
            rows.append('<tr class="usagg">' + "".join(cells) + "</tr>")
        for loc in sorted(df.location.unique()):
            cells = [f"<td>{loc}</td>"]
            for m in have:
                pm = (per_state.get(str(loc)) or {}).get(m) or {}
                cells.append(cells_for(pm.get("rel"), pm.get("cov")))
            rows.append("<tr>" + "".join(cells) + "</tr>")
    if rows:
        if show_cov:
            # two-row head: each member over its relWIS and 95% coverage
            head = ('<tr><th rowspan="2">State</th>'
                    + "".join(f'<th colspan="2" class="grp">{names.get(m, m)}'
                              "</th>" for m in have)
                    + "</tr><tr>"
                    + "".join('<th class="num">relWIS</th>'
                              '<th class="num">95%</th>' for _m in have)
                    + "</tr>")
        else:
            head = ('<tr><th>State</th>'
                    + "".join(f'<th class="num">{names.get(m, m)}</th>'
                              for m in have) + "</tr>")
        states = ('<h2 style="margin-top:.9rem">Per-state final scores</h2>'
                  + (f'<p class="hint">{PSTATES_COV_NOTE}</p>'
                     if show_cov else "")
                  + '<div class="statscroll"><table class="pstates"><thead>'
                  + head + '</thead><tbody>'
                  + "".join(rows) + "</tbody></table></div>"
                  + (f'<p class="hint">{us.note}</p>' if us else "")
                  + (f'<p class="hint">{usn.PF_US_NOTE}</p>'
                     if pf_us_plain and "pf" in have else ""))
        # a sealed record's scores.json predates FluSight's cell rule
        # (retro.SCORES_V): this table reads it, while the tiles and the live
        # scores are scored under the rule (playback._stats)
        if not retro.scores_frame_current(df_all):
            from app.core.scoring import earlier_rule_note
            stored = ["the per-state table"]
            fresh = ["the pooled tiles", "the live scores"]
            if us:
                (stored if us.is_fitted else fresh).append("the US figures")
            states += (f'<p class="hint">'
                       f"{earlier_rule_note(stored, fresh)}</p>")
    else:
        states = ('<p class="hint">Per-state scores appear here once the '
                  "season has been scored in the console.</p>")
    # a missing national figure is stated, never a silent hole
    us_absent = ""
    if not us:
        reason = (us_reason.replace("&", "&amp;").replace("<", "&lt;")
                  or "its construction was unavailable")
        us_absent = ('<p class="hint">The US national figure is not in '
                     f"this export: {reason}.</p>")
    return ('<div class="card" id="season-summary">'
            '<h2>Season verdict</h2>'
            '<div class="tiles">' + "".join(tiles) + "</div>"
            + us_absent
            + f'<p class="hint">Final relWIS pooled over {cover}, ratio of '
            "sums; below 1 beats the CDC FluSight baseline. "
            + (METRICS_NOTE + " " if any(more) else "")
            + f"{usn.POOLED_SCOPE_NOTE}</p>"
            + (f'<p class="pblegend">{COV_LEGEND}</p>' if tile_cov else "")
            # the file leaves the machine: it carries the convention note itself
            + f'<p class="hint">{relwis.PUBLISHED_CONVENTION_NOTE}</p>'
            + states + "</div>")     # the cumulative chart stays on the season page


ARCHIVE_MARK = "Archived run"


def _names_line(names: dict) -> str:
    """The host-script line handing the tree's names to the inlined player
    (FluBNFPlayer.MODEL_NAMES, read by reference). Also a cache marker in
    build_season_report: an export under other names is rebuilt."""
    nj = json.dumps(names, separators=(",", ":")).replace("</", "<\\/")
    return f"Object.assign(FluBNFPlayer.MODEL_NAMES, {nj});"


def _archive_note(archive: str) -> str:
    """Header line marking an export of an archived run, not the live season."""
    if not archive:
        return ""
    return ('<p class="sub">' + ARCHIVE_MARK + " "
            + retro.stamp_human(archive)
            + ", kept aside from the live season.</p>")


def build_season_report(root: Path, season: str, archive: str = "",
                        build: str = "", versions: dict | None = None) -> Path:
    """Build (or reuse, when fresh) the self-contained season report.

    `archive` (the archived run `root` is) only labels the header. `build`
    and `versions` name the producing code; omitted when unknown."""
    root = Path(root)
    weeks = playback.season_weeks(root)
    if not weeks:
        raise playback.UnknownWeek(
            f"{season}: no completed weeks yet, so there is no season "
            "report to build.")
    out = report_path(root, season)
    newest = _newest_input(root)
    settings_note = _settings_note(root, build, versions)
    timing_line = _timing_note(root)
    # the tree's own names, never written into the shared module map
    names = names_for_root(root)
    names_line = _names_line(names)
    if out.is_file() and out.stat().st_mtime >= newest:
        # mtime is not enough: an archived copy keeps its old mtime, coarse
        # (Windows) timestamps can tie with run_meta, and pf's name depends on
        # the tree. So the markers must be present too. Search the whole
        # file: they sit past the inlined plotly.
        text = out.read_text(encoding="utf-8")
        if ((not archive or ARCHIVE_MARK in text)
                and (not settings_note or SETTINGS_MARK in text)
                and (not timing_line or timing_line in text)
                and names_line in text):
            return out
    payloads = {w: playback.build_week(root, season, w) for w in weeks}
    # the player's timeline carries the season's no-data weeks as
    # placeholders (no payload) and a caption per annotated week
    timeline, notes = playback.week_notes(season, weeks)
    data = {"season": season, "weeks": timeline, "payloads": payloads,
            "notes": notes, "stored_weeks": weeks}
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    data_json = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    plotly_js = _plotlyjs()
    player_js = _player_js()
    timing_note = (_archive_note(archive) + _timing_note(root)
                   + settings_note)
    summary = _summary_block(root, weeks, payloads, names)
    # the same resolution the summary printed: one answer per file
    us_obj, _ = _us_national(root, playback._season_scores(root))
    us_json = json.dumps((us_obj.as_dict() if us_obj
                          else usn.UsNational(usn.OFFICIALS_ONLY).as_dict()),
                         separators=(",", ":")).replace("</", "<\\/")
    html = _compose(season, weeks, data_json, plotly_js, player_js,
                    size_note="", timing_note=timing_note, summary=summary,
                    us_json=us_json, names_line=names_line)
    size = len(html.encode("utf-8"))
    if size > SIZE_WARN_BYTES:
        note = ('<p class="warn">Size notice: this file is %.0f MB, above '
                'the 25 MB guideline; it may open slowly and some mail '
                'systems will refuse to attach it.</p>'
                % (size / (1024 * 1024)))
        html = _compose(season, weeks, data_json, plotly_js, player_js,
                        size_note=note, timing_note=timing_note,
                        summary=summary, us_json=us_json,
                        names_line=names_line)
    # atomic: two concurrent downloads must never interleave a garbled file
    tmp = out.with_suffix(".html.tmp")
    # LF pinned: served as text and downloaded raw, which must match on Windows
    tmp.write_text(html, encoding="utf-8", newline="\n")
    os.replace(tmp, out)
    return out


def _compose(season: str, weeks: list, data_json: str, plotly_js: str,
             player_js: str, size_note: str, timing_note: str = "",
             summary: str = "", us_json: str = "{}",
             names_line: str = "") -> str:
    return (_PAGE
            .replace("@@USNAT@@", us_json)
            .replace("@@NAMES@@", names_line)
            .replace("@@BOOT@@", report_v2.theme_boot_script())
            .replace("@@THEMETOKENS@@", report_v2.theme_token_css())
            .replace("@@SEASON@@", season)
            .replace("@@NWEEKS@@", str(len(weeks)))
            .replace("@@FIRST@@", weeks[0])
            .replace("@@LAST@@", weeks[-1])
            # the scrubber's range is set by the embedded timeline at load
            .replace("@@MAXIDX@@", str(len(weeks) - 1))
            .replace("@@TIMING@@", timing_note)
            .replace("@@SIZENOTE@@", size_note)
            .replace("@@SUMMARY@@", summary)
            .replace("@@LIVEHEAD@@", LIVE_HEADING)
            .replace("@@LIVENOTE@@", LIVE_SCORES_NOTE)
            .replace("@@PLOTLY@@", plotly_js)
            .replace("@@PLAYERJS@@", player_js)
            .replace("@@DATA@@", data_json))


# The page template. Plain token replacement, never str.format: the JS and
# CSS are full of braces. Theme-aware via the embedded token blocks.
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF season report @@SEASON@@</title>
@@BOOT@@
<script>@@PLOTLY@@</script>
<style>
 /* console identity, theme-aware: the token blocks below are the console's
    own (nau.css, verbatim -- four themes plus the high-contrast and
    color-vision modifiers), selected at open by the boot script above;
    the print block at the end flips to the console's light theme so the
    report always prints as dark ink on a light surface. The face is the
    console's own with a system fallback: the report stays fully offline
    (no webfont fetch), so the stack simply upgrades to DM Sans wherever
    the font is installed */
@@THEMETOKENS@@
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);
      font:400 var(--fs-body)/1.5 "DM Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
 main{max-width:1180px;margin:0 auto;padding:1.4rem 1.2rem 3rem}
 .brandrow{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;
  margin:0 0 .8rem}
 .brand{font-size:1.45rem;font-weight:700;letter-spacing:.01em}
 .brand em{color:var(--accent);font-style:normal}
 .brandsub{color:var(--mut);font-size:.9rem}
 h1{font-size:var(--fs-h1);font-weight:700;margin:.1rem 0 .3rem;
    text-wrap:balance}
 h2{font-size:var(--fs-h2);margin:.2rem 0 .55rem;
    text-transform:uppercase;
    letter-spacing:.05em;color:var(--mut);font-weight:600}
 .accent{color:var(--accent)}
 .sub{color:var(--mut);margin:.2rem 0 1rem;font-size:var(--fs-sub)}
 /* run-settings block: the console's compact two-column grid (see
    nau.css .runsettings), restated here because the export is
    self-contained */
 .runsettings{margin:.45rem 0}
 .runsettings .kv{display:grid;grid-template-columns:max-content max-content;
    gap:.14rem 1.1rem;align-items:baseline;width:max-content;
    max-width:100%;margin:.25rem 0 0}
 .runsettings .kv dt{color:var(--mut)}
 .runsettings .kv dd{margin:0;font-weight:650;
    font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
 .warn{background:transparent;border:1px solid var(--warn);
       color:var(--warn);
       border-radius:10px;padding:.6rem .8rem;font-size:.9rem}
 .card{background:var(--card);border:1px solid var(--line);
       border-radius:10px;padding:.85rem 1rem;margin:.75rem 0;
       box-shadow:var(--shadow)}
 .row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
 button{background:transparent;color:var(--gold);
   border:1px solid var(--gold);border-radius:8px;padding:.4rem .8rem;
   font:inherit;font-weight:650;cursor:pointer}
 button:hover{background:rgba(52,192,240,.14)}
 select{background:var(--bg);color:var(--ink);
   border:1px solid var(--field-line);border-radius:8px;
   padding:.4rem .6rem;font:inherit;cursor:pointer}
 button:focus-visible,select:focus-visible,input:focus-visible{
   outline:2px solid var(--gold);outline-offset:2px}
 input[type=range]{flex:1;min-width:160px;accent-color:var(--gold)}
 .hint{color:var(--mut);font-size:var(--fs-hint)}
 /* the live scores sit under the chart: this page is at most 1180px
    wide, too narrow for the chart and the two-period table side by side.
    The table rules are the console's (nau.css, season player), restated
    because the export is self-contained */
 .playgrid{display:grid;grid-template-columns:minmax(0,1fr);gap:1rem;
    align-items:start}
 .playstats{min-width:0}
 .statscroll{overflow-x:auto;max-width:100%;scrollbar-width:thin}
 table.pbstats{width:auto}
 table.pbstats th,table.pbstats td{padding:.3rem .5rem;white-space:nowrap}
 th.grp{text-align:center;color:var(--ink);letter-spacing:.03em}
 table.pbstats th.g1,table.pbstats td.g1{border-left:1px solid var(--line)}
 table.pbstats td.gap{text-align:center}
 table.pbstats .mname{position:sticky;left:0;z-index:1;background:var(--card);
    text-align:left;white-space:normal;min-width:8.5rem}
 table.pbstats.stacked th.grp{text-align:left;padding-top:.55rem;
    text-transform:uppercase;letter-spacing:.03em}
 table.pbstats.stacked .mname{min-width:6.5rem}
 table.pbstats.stacked th,table.pbstats.stacked td{padding:.3rem .4rem}
 table.pbstats.stacked thead th{white-space:normal}
 table.pstates{width:auto;min-width:min(100%,44rem)}
 /* a phone scrolls the per-state table: the state names stay in view */
 table.pstates thead tr:first-child th:first-child,
 table.pstates tbody td:first-child{position:sticky;left:0;z-index:1;
    background:var(--card)}
 @media(max-width:480px){table.pstates td,table.pstates th{
    padding:.3rem .4rem}}
 table.pbstats tr + tr th,table.pstates tr + tr th{text-transform:none;
    letter-spacing:.02em}
 .cov-ok{color:var(--ok)}.cov-low{color:var(--bad);font-weight:650}
 .cov-wide{color:var(--warn);font-style:italic;font-weight:400}
 .pblegend{color:var(--ink);font-size:var(--fs-hint);margin:.35rem 0}
 .pbscale{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem .6rem;
    margin:0 0 .45rem}
 .seg{display:inline-flex;gap:.3rem}
 .seg button{padding:.08rem .6rem;border-radius:99px;font-size:.8rem}
 .seg button.gold{background:var(--gold-bright);border-color:var(--gold-bright);
    color:#0C0D17}
 /* a verdict tile's second line: log scale and coverage */
 .tilekv{display:grid;grid-template-columns:max-content max-content;
    gap:.05rem .7rem;margin:.3rem 0 .15rem;font-size:.85rem}
 .tilekv dt{color:var(--mut)}
 .tilekv dd{margin:0;font-weight:650;font-variant-numeric:tabular-nums}
 table{border-collapse:collapse;font-size:var(--fs-table);width:100%;
       font-variant-numeric:tabular-nums}
 td,th{padding:.38rem .6rem;border-bottom:1px solid var(--line);
       text-align:left}
 th{color:var(--mut);font-weight:600;font-size:.72rem;
    text-transform:uppercase;letter-spacing:.04em}
 td.num,th.num{text-align:right}
 /* the console's ok/bad tokens, resolved per theme by the blocks above,
    so a number wears the same alert color in the application and in this
    export; the print block restates the light-theme pair literally */
 .ok{color:var(--ok)}.bad{color:var(--bad)}
 .num.hint{color:var(--mut)}
 .tiles{display:flex;gap:.9rem;flex-wrap:wrap;margin:.2rem 0 .5rem}
 .tile{background:var(--bg);border:1px solid var(--line);
       border-radius:10px;padding:.55rem .95rem;min-width:130px;
       max-width:24rem}
 .tilename{color:var(--mut);font-size:.74rem;text-transform:uppercase;
           letter-spacing:.05em}
 .tileval{font-size:var(--fs-big);font-weight:750;
          font-variant-numeric:tabular-nums}
 .sw{width:11px;height:11px;border-radius:3px;display:inline-block;
     margin-right:.3rem;vertical-align:-1px;
     -webkit-print-color-adjust:exact;print-color-adjust:exact}
 .fdmodels{display:flex;gap:.9rem;flex-wrap:wrap;margin:.3rem 0 .5rem}
 .fdmodels label{font-size:.85rem;display:inline-flex;align-items:center;
                 gap:.25rem}
 @media print{
  :root{--bg:#FFFFFF;--card:#FFFFFF;--ink:#000F7E;--mut:#565E96;
   --line:#DCD8E9;--accent:#0173A9;--gold:#0173A9;--field-line:#DCD8E9;
   --shadow:none}
  body{background:#FFFFFF;color:#000F7E}
  .ok{color:#177245}.bad{color:#C42840}
  .cov-ok{color:#177245}.cov-low{color:#C42840}.cov-wide{color:#8A5A14}
  .warn{background:#FFFFFF;border-color:#8A5A14;color:#8A5A14}
  button,select,input,label,.playerbar,.fdmodels,.pbscale{display:none!important}
  /* cards may break across pages (the per-state table outgrows one), but
     rows and tiles stay whole */
  .card{box-shadow:none}
  tr,.tile{break-inside:avoid}
 }
</style></head><body><main>
<header class="brandrow"><span class="brand"><em>Flu</em>BNF</span>
 <span class="brandsub">season report export</span></header>
<h1>Season report <span class="accent">@@SEASON@@</span></h1>
<p class="sub">@@NWEEKS@@ stored weeks, @@FIRST@@ to @@LAST@@; a
 self-contained file (the categorical forecast maps stay in the console).</p>
@@TIMING@@
@@SIZENOTE@@
@@SUMMARY@@
<div class="card">
 <div class="row playerbar">
  <button type="button" id="pb-prev" title="Previous week (left arrow)"
    aria-label="Previous week">&#9664;</button>
  <button type="button" id="pb-play">&#9654; Play</button>
  <button type="button" id="pb-next" title="Next week (right arrow)"
    aria-label="Next week">&#9654;</button>
  <select id="pb-speed" aria-label="Playback speed">
   <option value="500">0.5 s / week</option>
   <option value="1000" selected>1 s / week</option>
   <option value="2000">2 s / week</option>
  </select>
  <input type="range" id="pb-scrub" min="0" max="@@MAXIDX@@" step="1"
         value="@@MAXIDX@@" aria-label="Week scrubber">
  <span class="hint" id="pb-week" aria-live="polite"></span>
 </div>
 <div class="playgrid">
  <div>
   <div class="row" style="margin:.2rem 0 .4rem">
    <select id="fd-loc" aria-label="Forecast location"
      style="width:auto;min-width:230px;max-width:100%"></select>
    <label style="display:inline-flex;align-items:center;gap:.35rem;
      font-size:.85rem;cursor:pointer"><input type="checkbox" id="fd-lock"
      checked> Lock axes</label>
   </div>
   <div class="fdmodels" id="fd-models"></div>
   <div id="fd-plot"></div>
   <p class="hint" id="fd-msg"></p>
  </div>
  <div class="playstats">
   <h2>@@LIVEHEAD@@</h2>
   <div class="pbscale" id="pb-scale"></div>
   <div class="statscroll"><table id="pb-stats" class="pbstats"><thead></thead>
    <tbody></tbody></table></div>
   <p class="pblegend" id="pb-legend"></p>
   <p class="hint" id="pb-status" aria-live="polite"></p>
   <p class="hint" id="pb-offhint" hidden>official comparators appear after
    Update data</p>
   <p class="hint">@@LIVENOTE@@</p>
  </div>
 </div>
</div>
<script id="pbdata" type="application/json">@@DATA@@</script>
<script>
@@PLAYERJS@@
</script>
<script>
// FluBNF season player (export host): the shared player above is inlined
// verbatim from the console's player.js at build time; this block only
// feeds it the embedded JSON block and the static host configuration. The
// payload variable is ALWAYS named `pl` so the contract test can verify
// the JS reads only fields the API defines.
'use strict';
var DATA = JSON.parse(document.getElementById('pbdata').textContent);
// WEEKS is the timeline: the stored weeks plus the season's no-data weeks,
// which have no payload and show their note (DATA.notes) instead
var WEEKS = DATA.weeks, PAY = DATA.payloads, NOTES = DATA.notes || {};
(function(){
  var s = document.getElementById('pb-scrub');
  if(s) s.max = String(Math.max(0, WEEKS.length - 1));
})();
// controls build from the union across every embedded week, so a model or
// location present in only part of the season still gets a toggle
var UNION = {models: {}, offs: {}, locs: {}};
WEEKS.forEach(function(w){
  var pl = PAY[w];
  if(!pl) return;
  Object.keys(pl.models || {}).forEach(function(k){ UNION.models[k] = 1; });
  Object.keys(pl.official || {}).forEach(function(k){ UNION.offs[k] = 1; });
  (pl.locations || []).forEach(function(l){ UNION.locs[l] = 1; });
});
// charts follow the resolved theme: the palette hook re-reads the token
// values per redraw (the same tokens the page chrome wears), with the
// player's own dark kit as the fallback for any token that fails to
// resolve. Ensemble alone stays theme-resolved through --gold, the
// readable accent-ink variant of the same cyan identity on light grounds.
// The member line colors themselves stay STATIC on purpose, in every
// theme and under the CV-safe mode: the shared palette
// (FluBNFPlayer.MODEL_COLORS) is dichromat-spaced by construction, so
// only the semantic ok/bad pair and the category scale change under
// data-vision="cvd", never a member's identity.
function css(n, fb){
  var v = getComputedStyle(document.documentElement)
    .getPropertyValue(n).trim();
  return v || fb;
}
// the season tree's own model names (report_season.names_for_root), set
// before anything draws: a sealed record or a replay from before the
// Oracle step stores the particle filter alone under pf, and the player
// must title it as the summary above does
@@NAMES@@
var player = FluBNFPlayer.init({
  weeks: WEEKS,
  notes: NOTES,
  mode: 'static',
  getPayload: function(w){ return Promise.resolve(PAY[w] || null); },
  catalog: {models: Object.keys(UNION.models),
            officials: Object.keys(UNION.offs),
            locations: Object.keys(UNION.locs).sort()},
  // the US national series and where it came from, resolved at BUILD time
  // by app/core/us_national and frozen into this file, so the exported
  // player labels its location entry, chart title, and saved-image
  // filename exactly as the console does. An export can travel far from
  // the machine that made it; it must carry the provenance with it.
  us: @@USNAT@@,
  palette: function(){
    return {ink: css('--ink', '#E9EAF4'), mut: css('--mut', '#9AA1C4'),
            line: css('--line', '#262A45'), card: css('--card', '#151729'),
            models: Object.assign({}, FluBNFPlayer.MODEL_COLORS,
                                  {ensemble: css('--gold',
                                     FluBNFPlayer.MODEL_COLORS.ensemble)}),
            flusightEnsemble: '#AAB1C9'};
  },
  plotHeight: 420
});
// the report opens on the season's LAST week: a skimmer reads the final
// verdict first, and the summary block above matches this frame; playback
// still replays from the top (Play at the end restarts at week one)
player.seek(@@MAXIDX@@);
</script>
</main></body></html>"""
