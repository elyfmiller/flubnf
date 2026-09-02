"""Season report export: one self-contained interactive HTML file.

The console's season player, frozen into a downloadable artifact. The file
carries plotly.js inline (the report_v2 pattern), every stored week's
playback payload embedded as one JSON block, and the SHARED player
(app/ui/static/player.js, the same file the console's season page loads)
inlined verbatim, fed by a getPayload backed by the embedded block. Every
future player feature lands in the console and in this export
automatically. No server and no network are needed; the file works from a
desktop or an email attachment.

Scope, by design: the export carries the season verdict (tiles, the US
national aggregate, the cumulative relWIS chart, the per-state table), the
forecast detail view, and the live relWIS table -- the same substantive
content as the console's season page, held together by the parity test
(app/tests/test_report_parity.py). The categorical weekly maps alone are
omitted, since 30-plus inline SVG maps would multiply the file size for a
view the console already serves live; the header note says so. Anything
else the page shows that the export cannot deliver must be STATED in the
artifact, never silently absent: the report builder computes what it needs
when a cache is cold, and prints the reason when it truly cannot.

Theme-aware on screen, like report_v2 (both follow the app theme since
2026-08-21, superseding the fixed-dark spec): the stylesheet embeds the
console's four theme token blocks and both accessibility modifier blocks
verbatim from nau.css, and the shared boot script resolves the theme at
open -- the console's own localStorage keys when served same-origin, the
OS preferences when opened as a standalone file. The player reads the
resolved tokens per redraw through its palette hook, so the charts follow
too. A print stylesheet flips the page to the console's light theme so the
report always prints as dark ink on a light surface. The identity stays
the console's own: DM Sans with a system fallback and no webfont fetch.

Caching: the report lands at <season_root>/<season>-FluBNF-season-report.html
and is reused while fresh (mtime vs every samples.json and scores.json),
matching the playback payload cache convention.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.core import playback, relwis, report_v2, retro
from app.core import us_national as usn
from app.core.runs import fmt_hms, settings_html, version_pairs

# console identity (nau.css dark theme), shared with report_v2
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"

# the one member-color map: the shared player's marked JSON literal,
# parsed by report_v2.model_colors (officials stay the muted greys the
# player states for itself)
MODEL_COLORS = report_v2.model_colors()

SIZE_WARN_BYTES = 25 * 1024 * 1024

# the shared player: the very file the console's season page loads. It is
# inlined verbatim at build time so both hosts run identical player code.
PLAYER_SRC = report_v2.PLAYER_SRC


def model_names() -> dict:
    """The one model-name map, read from the shared player core.

    player.js carries the map as a marked JSON literal; the player's own
    legend and toggles read it directly, and this parse hands the SAME
    names to every Python surface (this report's summary tiles, and the
    console templates via app/ui/server.py), so pf/analogue/ensemble can
    never drift apart across surfaces again. Degrades to an empty map
    (raw ids print) rather than raising."""
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


def report_path(root: Path, season: str) -> Path:
    return Path(root) / f"{season}-FluBNF-season-report.html"


def _plotlyjs() -> str:
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def _player_js() -> str:
    return PLAYER_SRC.read_text(encoding="utf-8")


def _newest_input(root: Path) -> float:
    """mtime of the newest report input: any samples.json, scores.json, or
    the shared player source itself (a player fix must refresh the export).
    """
    times = [p.stat().st_mtime for p in retro.season_sample_files(root)]
    sf = root / "scores.json"
    if sf.is_file():
        times.append(sf.stat().st_mtime)
    if PLAYER_SRC.is_file():
        times.append(PLAYER_SRC.stat().st_mtime)
    # this builder is an input to its own output: a restyle or template fix
    # here must refresh every cached export, exactly as a player fix does
    # (without this, seasons whose data never changes serve the old face
    # forever)
    src = Path(__file__)
    if src.is_file():
        times.append(src.stat().st_mtime)
    # Rebuilt playback payloads must refresh the export too: official
    # comparator files arriving (Update data on a sparse clone) rebuild the
    # per-week caches without touching any input above, and a report built
    # earlier would keep serving "pending" stats forever (field-found, the
    # third organ of the same staleness disease).
    pc = root / "playback_cache"
    if pc.is_dir():
        times.extend(f.stat().st_mtime for f in pc.glob("*.json"))
    # The hub tree itself is an input, directly: Update data drops new
    # official comparator files without touching playback_cache until
    # someone opens the console season player (the lazy heal), so a report
    # exported before that visit kept serving "pending" official stats
    # forever (audit finding). A directory's mtime moves when files land in
    # it, which is exactly the arrival this gate must see.
    try:
        from flubnf.settings import HUB
        for name in ("FluSight-ensemble", "FluSight-baseline"):
            d = HUB / "model-output" / name
            if d.is_dir():
                times.append(d.stat().st_mtime)
    except Exception:
        pass
    # the run record carries the header's wall-time line: a replay that
    # resumed and finished must refresh the export, not serve the old total
    mp = root / retro.META_NAME
    if mp.is_file():
        times.append(mp.stat().st_mtime)
    # the console stylesheet is embedded as the report's theme tokens: a
    # token change is a design change and must refresh cached exports
    if report_v2.NAU_CSS.is_file():
        times.append(report_v2.NAU_CSS.stat().st_mtime)
    return max(times)


def _timing_note(root: Path) -> str:
    """One factual line for the header: total wall time, weeks measured, and
    the mean per week. Absent when the season carries no run record (the
    sealed validation runs predate the record, and inventing a number for
    them would be worse than saying nothing)."""
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
    """The replay's settings, the application build, and the engine
    versions, so the export states exactly what produced it.

    Read from the season's own run record, which means an archived run's
    export describes that run and not the live season. Absent, never
    invented, when the record carries no settings: the sealed validation
    runs predate the record."""
    pairs = retro.settings_summary(retro.read_meta(root))
    if not pairs:
        return ""
    return settings_html(pairs + version_pairs(build, versions),
                         title=SETTINGS_MARK, cls="sub")


#: the shipped, never-self-fitted member weights, the same pair the season
#: page scores with -- the export's aggregate must be THE aggregate, not a
#: reweighted cousin
_US_AGG_WEIGHTS = dict(usn.DEFAULT_WEIGHTS)


def player_us_labels() -> dict:
    """The player's own US provenance labels, read from its marked JSON
    literal, the MODEL_NAMES pattern applied to the national row. Parsed so
    a test can hold the JS literal and us_national.LABELS together: the
    wording of the three provenance states is defined once, and neither
    host may drift from the other. Degrades to an empty map."""
    import re
    try:
        src = PLAYER_SRC.read_text(encoding="utf-8")
        m = re.search(r"/\*US_LABELS_JSON\*/\s*(\{.*?\})"
                      r"\s*/\*END_US_LABELS_JSON\*/", src, re.S)
        return json.loads(m.group(1)) if m else {}
    except Exception:
        return {}


def _us_national(root: Path, df) -> tuple:
    """(us, reason): the US national series for the export, through THE
    resolution order (app/core/us_national.resolve) -- a fitted US cell
    when the replay ran one, else the constructed sum-of-states aggregate,
    else neither. The aggregate COMPUTES when its cache is cold, exactly as
    the season page does, so an export downloaded before the page was ever
    visited still carries it; the result is cached in
    playback_cache/us_aggregate.json, which _newest_input already covers,
    so a rebuilt aggregate refreshes an already-exported report.

    When nothing can be delivered, us is None and reason states why, in
    words the artifact prints. Silent omission is the recurring failure
    class this replaced: the export must never lack a section the
    application shows without saying so."""
    if df is None:
        return None, ("the season has not been scored yet, and the national "
                      "figure joins the scored verdict table only")
    try:
        us = usn.resolve(root, df, ensemble_weights=_US_AGG_WEIGHTS)
    except Exception as e:
        return None, ("its construction failed while this export was "
                      f"built ({type(e).__name__}: {str(e)[:120]})")
    if not us.has_scores:
        return None, (us.reason or "no scoreable national cells exist for "
                                   "this season")
    return us, ""


#: calendar month number -> label, the season order the console's month
#: helper uses (app/ui/server.py _MON_NAME); restated because the report
#: builder is a core module and must not import the UI layer
_MON_NAME = {8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec", 1: "Jan",
             2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul"}

#: the cumulative chart's heading, EXACTLY the season page's own, so the
#: report-vs-app parity test can match the sections by name
CURVE_HEADING = "Cumulative ensemble relWIS through the season"


def _cumulative_curve(df) -> list:
    """[(iso week, cumulative ensemble relWIS)], the same series the
    console's season page charts: ensemble rows grouped by asof, summed,
    and accumulated (the arithmetic mirrors app/ui/server.py's
    retro_results; the parity test holds the two together)."""
    if df is None or "model" not in getattr(df, "columns", ()):
        return []
    # the pooled gate: the curve is the 52-jurisdiction cumulative figure,
    # by named policy (us_national.POOLED_INCLUDES_US), so a fitted
    # national row can never bend the season's published line
    df = usn.pooled_frame(df)
    ens_rows = df[df.model == "ensemble"]
    if not len(ens_rows):
        return []
    asofs = sorted(df["asof"].unique())
    cum = (ens_rows.groupby("asof")[["wis", "base_wis"]].sum()
           .sort_index().cumsum())
    cum = cum.reindex(asofs).ffill().dropna()
    return [(str(a)[:10], r.wis / r.base_wis) for a, r in cum.iterrows()]


def _curve_svg(curve: list) -> str:
    """The cumulative chart as one inline SVG, the season page's own
    geometry (viewBox 720x180, gridlines at 1.0 and 0.5, gold line, the
    final value printed at the endpoint, month ticks at each month change,
    corner dates). Token colors, so it follows the resolved theme."""
    vals = [v for _, v in curve]
    n = len(curve)
    hi = max(max(vals), 1.05)
    lo = min(min(vals), 0.45)
    yspan = hi - lo

    def x_at(i):
        return round(20 + i * (635 / (n - 1 if n > 1 else 1)), 1)

    def y_at(v):
        return round(12 + (hi - v) * 124 / yspan, 1)

    parts = ['<svg viewBox="0 0 720 180" style="width:100%" role="img" '
             f'aria-label="{CURVE_HEADING}">']
    for gv, gl in ((1.0, "1.0"), (0.5, "0.5")):
        gy = y_at(gv)
        parts.append(f'<line x1="20" y1="{gy}" x2="655" y2="{gy}" '
                     'stroke="var(--mut)" stroke-dasharray="3"/>'
                     f'<text x="660" y="{gy + 4}" fill="var(--mut)" '
                     f'font-size="13">{gl}</text>')
    pts = " ".join(f"{x_at(i)},{y_at(v)}" for i, (_, v) in enumerate(curve))
    parts.append('<polyline fill="none" stroke="var(--gold)" '
                 f'stroke-width="2.5" points="{pts}"/>')
    for i, (d, v) in enumerate(curve):
        parts.append(f'<circle cx="{x_at(i)}" cy="{y_at(v)}" r="3" '
                     f'fill="var(--gold)"><title>{d}: {v:.3f}</title>'
                     '</circle>')
    lx, ly = x_at(n - 1), y_at(vals[-1])
    parts.append(f'<text x="{round(lx - 8, 1)}" '
                 f'y="{round(ly - 8 if ly - 8 >= 20 else ly + 18, 1)}" '
                 'text-anchor="end" font-weight="700" font-size="17" '
                 f'fill="var(--gold)">{vals[-1]:.3f}</text>')
    prev = None
    for i, (d, _v) in enumerate(curve):
        mm = str(d)[5:7]
        if prev is not None and mm != prev and mm.isdigit():
            lab = _MON_NAME.get(int(mm), "")
            parts.append(f'<line x1="{x_at(i)}" y1="136" x2="{x_at(i)}" '
                         'y2="142" stroke="var(--mut)"/>'
                         f'<text x="{x_at(i)}" y="154" text-anchor="middle" '
                         f'fill="var(--mut)" font-size="13">{lab}</text>')
        prev = mm
    parts.append(f'<text x="20" y="168" fill="var(--mut)" font-size="13">'
                 f'{curve[0][0]}</text>')
    if n > 1:
        parts.append('<text x="655" y="168" text-anchor="end" '
                     f'fill="var(--mut)" font-size="13">{curve[-1][0]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _curve_block(df) -> str:
    """The cumulative chart as its own section, present in scored and
    unscored seasons alike: the season page always shows this card, and an
    unscored season states the same arrival note the console does rather
    than leaving a hole."""
    curve = _cumulative_curve(df)
    head = f'<h2 style="margin-top:.9rem">{CURVE_HEADING}</h2>'
    if not curve:
        return head + ('<p class="hint">Arrives with the first scored '
                       "week.</p>")
    return head + _curve_svg(curve)


def _summary_block(root: Path, weeks: list, payloads: dict) -> str:
    """The static season verdict, printed ahead of the player.

    Final relWIS tiles for each member and the ensemble come from the final
    week's cumulative stats, which are the very numbers the player's live
    table reaches at the last frame, so the static block and the player can
    never disagree. The line beneath states the weeks covered and, when the
    season's run record carries one, the total wall time. The per-state
    final table reads the season's scores.json, the same file the console's
    season page renders; when the season has not been scored yet the table
    is omitted with a plain statement rather than invented. The cumulative
    ensemble chart sits between them, the same series the season page
    draws. The US national aggregate joins both surfaces exactly as it
    does in the console -- a verdict tile and a leading table row, each
    wearing the honest independence label -- computed when its cache is
    cold; when it cannot be delivered at all, the artifact SAYS so instead
    of leaving a hole."""
    final = payloads.get(weeks[-1]) or {}
    stats = final.get("stats") or {}
    tiles = []
    for m in ("ensemble", "pf", "analogue", "pf2s"):
        v = (stats.get(m) or {}).get("cum_rel")
        if v is None:
            continue
        cls = "ok" if v < 1 else "bad"
        tiles.append('<div class="tile"><div class="tilename">'
                     + MODEL_NAMES.get(m, m) + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div></div>')
    line = f"{len(weeks)} weeks covered, {weeks[0]} to {weeks[-1]}"
    meta = retro.read_meta(root)
    if meta:
        t = retro.timing(meta)
        if t["elapsed_s"] and t["elapsed_s"] >= 1.0:
            line += (", total wall time "
                     + fmt_hms(t["elapsed_s"]) + " (h:mm:ss)")
    rows = []
    cover = "every scored cell of the season"
    df_all = playback._season_scores(root)
    # the pooled gate, applied once: every per-state figure below is the
    # 52-jurisdiction scope, and the national row is resolved separately
    df = usn.pooled_frame(df_all)
    us, us_reason = _us_national(root, df_all)
    if us and us.get("ensemble"):
        # the national figure as a verdict tile, ALWAYS labelled for what
        # it is: fitted at the national level, or constructed from the
        # state forecasts. The two are different model outputs.
        v = us["ensemble"]
        cls = "ok" if v < 1 else "bad"
        sub = ("fitted at the national level, outside the pooled figures"
               if us.is_fitted else us.fallback_note
               + ", states treated as independent")
        tiles.append('<div class="tile"><div class="tilename">'
                     + us.short_label + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div>'
                     + f'<div class="hint">{sub}</div></div>')
    if df is not None and "model" in getattr(df, "columns", ()):
        # cell coverage, stated when the scores file can supply it and
        # omitted (the generic phrase stands) rather than invented
        n = int((df.model == "ensemble").sum())
        if n:
            cover = f"the season's {n} scored ensemble cells"
    if df is not None and "location" in df.columns:
        if us:
            # the national row leads the table as a DISTINCT row, the
            # console's own placement, wearing the label that says where it
            # came from; a member with no score prints n/a
            cells = [f"<td>{us.short_label}</td>"]
            for m in ("pf", "analogue", "ensemble"):
                v = us.get(m)
                if v:
                    cells.append('<td class="num '
                                 + ("ok" if v < 1 else "bad")
                                 + f'">{v:.3f}</td>')
                else:
                    cells.append('<td class="num hint">n/a</td>')
            rows.append('<tr class="usagg">' + "".join(cells) + "</tr>")
        for loc in sorted(df.location.unique()):
            cells = [f"<td>{loc}</td>"]
            for m in ("pf", "analogue", "ensemble"):
                g = df[(df.model == m) & (df.location == loc)]
                bs = g.base_wis.sum() if len(g) else 0
                if bs:
                    v = g.wis.sum() / bs
                    cells.append('<td class="num '
                                 + ("ok" if v < 1 else "bad")
                                 + f'">{v:.3f}</td>')
                else:
                    cells.append('<td class="num hint">n/a</td>')
            rows.append("<tr>" + "".join(cells) + "</tr>")
    if rows:
        states = ('<h2 style="margin-top:.9rem">Per-state final scores</h2>'
                  '<table><thead><tr><th>State</th><th class="num">PF</th>'
                  '<th class="num">Analogue</th>'
                  '<th class="num">Ensemble</th></tr></thead><tbody>'
                  + "".join(rows) + "</tbody></table>"
                  + (f'<p class="hint">{us.note}</p>'
                     f'<p class="hint">{usn.POOLED_SCOPE_NOTE}</p>'
                     if us else ""))
    else:
        states = ('<p class="hint">Per-state scores appear here once the '
                  "season has been scored in the console.</p>")
    # a missing national figure is STATED, never a silent hole: the console
    # shows this figure, so an export without it must say why it is absent
    us_absent = ""
    if not us:
        reason = (us_reason.replace("&", "&amp;").replace("<", "&lt;")
                  or "its construction was unavailable")
        us_absent = ('<p class="hint">The US national figure the '
                     "console's season page shows is not in this export: "
                     f"{reason}.</p>")
    return ('<div class="card" id="season-summary">'
            '<h2>Season verdict</h2>'
            '<div class="tiles">' + "".join(tiles) + "</div>"
            + us_absent
            + f'<p class="sub">{line}.</p>'
            f'<p class="hint">Final relWIS pooled over {cover}, ratio of '
            "sums; below 1 beats the CDC FluSight baseline. "
            f"{usn.POOLED_SCOPE_NOTE}</p>"
            # THIS FILE LEAVES THE MACHINE. It is opened without the console
            # around it, months later, beside whatever else the reader has
            # open, and the likeliest neighbour is the CDC FluSight
            # dashboard, which publishes a DIFFERENT quantity under the same
            # name. Every other surface can lean on the pages around it;
            # this one has to carry the convention itself, in the wording
            # the console and the public site use.
            f'<p class="hint">{relwis.PUBLISHED_CONVENTION_NOTE}</p>'
            + _curve_block(df) + states + "</div>")


ARCHIVE_MARK = "Archived run"


def _archive_note(archive: str) -> str:
    """One line saying the export came from an archived run, not the live
    season. Without it two exports of the same season are indistinguishable
    once they leave the machine."""
    if not archive:
        return ""
    return ('<p class="sub">' + ARCHIVE_MARK + " "
            + retro.stamp_human(archive)
            + ", kept aside from the live season.</p>")


def build_season_report(root: Path, season: str, archive: str = "",
                        build: str = "", versions: dict | None = None) -> Path:
    """Build (or reuse, when fresh) the self-contained season report.

    `archive` is the identifier of an archived run whose tree `root` is; it
    only labels the header, since the data all comes from `root`. `build`
    and `versions` name the code that produced the export; both are omitted
    from the header rather than guessed when the caller does not know."""
    root = Path(root)
    weeks = playback.season_weeks(root)
    if not weeks:
        raise playback.UnknownWeek(
            f"{season}: no completed weeks yet, so there is no season "
            "report to build.")
    out = report_path(root, season)
    newest = _newest_input(root)
    settings_note = _settings_note(root, build, versions)
    if out.is_file() and out.stat().st_mtime >= newest:
        # a report that travelled INTO an archive with the season tree keeps
        # its old mtime, so freshness alone would serve it unlabelled: make
        # the label part of the freshness test. The settings block joins it,
        # so a report built before the settings were recorded is rebuilt
        # rather than served without them.
        # Search the WHOLE file: the markers sit in the body, megabytes past
        # the embedded plotly bundle in <head>, so an 8 KB head slice could
        # never contain them and every download rebuilt the full report
        # while believing it had checked the cache (audit finding). The
        # full read was already being paid; only the slice was wrong.
        text = out.read_text(encoding="utf-8")
        if ((not archive or ARCHIVE_MARK in text)
                and (not settings_note or SETTINGS_MARK in text)):
            return out
    payloads = {w: playback.build_week(root, season, w) for w in weeks}
    data = {"season": season, "weeks": weeks, "payloads": payloads}
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    data_json = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    plotly_js = _plotlyjs()
    player_js = _player_js()
    timing_note = (_archive_note(archive) + _timing_note(root)
                   + settings_note)
    summary = _summary_block(root, weeks, payloads)
    # the SAME resolution the summary block printed, frozen into the
    # exported player's config: one answer per file, never two
    us_obj, _ = _us_national(root, playback._season_scores(root))
    us_json = json.dumps((us_obj.as_dict() if us_obj
                          else usn.UsNational(usn.OFFICIALS_ONLY).as_dict()),
                         separators=(",", ":")).replace("</", "<\\/")
    html = _compose(season, weeks, data_json, plotly_js, player_js,
                    size_note="", timing_note=timing_note, summary=summary,
                    us_json=us_json)
    size = len(html.encode("utf-8"))
    if size > SIZE_WARN_BYTES:
        note = ('<p class="warn">Size notice: this file is %.0f MB, above '
                'the 25 MB guideline; it may open slowly and some mail '
                'systems will refuse to attach it.</p>'
                % (size / (1024 * 1024)))
        html = _compose(season, weeks, data_json, plotly_js, player_js,
                        size_note=note, timing_note=timing_note,
                        summary=summary, us_json=us_json)
    # atomic: two concurrent downloads must never interleave a garbled file
    tmp = out.with_suffix(".html.tmp")
    # newline pinned: the report is served as text (universal-newline read)
    # and downloaded raw; on Windows an unpinned write makes those two
    # deliveries different text, the exact report_v2 defect from Windows CI.
    tmp.write_text(html, encoding="utf-8", newline="\n")
    os.replace(tmp, out)
    return out


def _compose(season: str, weeks: list, data_json: str, plotly_js: str,
             player_js: str, size_note: str, timing_note: str = "",
             summary: str = "", us_json: str = "{}") -> str:
    return (_PAGE
            .replace("@@USNAT@@", us_json)
            .replace("@@BOOT@@", report_v2.theme_boot_script())
            .replace("@@THEMETOKENS@@", report_v2.theme_token_css())
            .replace("@@SEASON@@", season)
            .replace("@@NWEEKS@@", str(len(weeks)))
            .replace("@@FIRST@@", weeks[0])
            .replace("@@LAST@@", weeks[-1])
            .replace("@@MAXIDX@@", str(len(weeks) - 1))
            .replace("@@TIMING@@", timing_note)
            .replace("@@SIZENOTE@@", size_note)
            .replace("@@SUMMARY@@", summary)
            .replace("@@PLOTLY@@", plotly_js)
            .replace("@@PLAYERJS@@", player_js)
            .replace("@@DATA@@", data_json))


# The page template. Plain token replacement, never str.format: the JS and
# CSS are full of braces. Fixed dark palette painted inline throughout.
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
 .playgrid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:1rem}
 @media(max-width:1000px){.playgrid{grid-template-columns:1fr}}
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
       border-radius:10px;padding:.55rem .95rem;min-width:130px}
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
  .warn{background:#FFFFFF;border-color:#8A5A14;color:#8A5A14}
  button,select,input,label,.playerbar,.fdmodels{display:none!important}
  /* cards may break across pages (the per-state table outgrows one), but
     rows and tiles stay whole */
  .card{box-shadow:none}
  tr,.tile{break-inside:avoid}
 }
</style></head><body><main>
<header class="brandrow"><span class="brand"><em>Flu</em>BNF</span>
 <span class="brandsub">season report export</span></header>
<h1>Season report <span class="accent">@@SEASON@@</span></h1>
<p class="sub">@@NWEEKS@@ stored weeks, @@FIRST@@ to @@LAST@@.
 Self-contained: no server or network is needed. The weekly categorical
 maps are omitted; interactive maps live in the console.</p>
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
   <h2>Live relWIS</h2>
   <table id="pb-stats"><thead><tr><th>Model</th><th class="num">Week</th>
    <th class="num">Cumulative</th></tr></thead><tbody></tbody></table>
   <p class="hint" id="pb-status" aria-live="polite"></p>
   <p class="hint" id="pb-offhint" hidden>official comparators appear after
    Update data fetches their submissions</p>
   <p class="hint">relWIS below 1 beats the CDC FluSight baseline, ratio of
    sums. Week scores the current forecast's cells; cumulative pools every
    week through the playback position.</p>
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
var WEEKS = DATA.weeks, PAY = DATA.payloads;
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
var player = FluBNFPlayer.init({
  weeks: WEEKS,
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
