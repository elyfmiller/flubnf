"""PRODUCTION: the season HTML export (server /retro/{season}/report).

Season report export: one self-contained interactive HTML file.

The console's season player frozen into a download: plotly.js inline, every
stored week's playback payload embedded as JSON, and the SHARED player
(app/ui/static/player.js, the file the season page loads) inlined verbatim,
so player features reach the export automatically. Works offline.

Scope: the season verdict (tiles, the US national aggregate, per-state
table), the forecast detail view and the live relWIS table, held to the
season page by app/tests/test_report_parity.py. The cumulative chart and the
categorical weekly maps stay on the season page (size); anything else the
page shows that the export cannot deliver must be STATED, never silently absent.

Theme-aware like report_v2: nau.css token blocks embedded verbatim, the
shared boot script resolves the theme at open, and a print block flips to
the light theme. DM Sans with a system fallback, no webfont fetch.

Cached at <season_root>/<season>-FluBNF-season-report.html while newer than
every input (_newest_input) and carrying the current markers
(build_season_report).
"""
from __future__ import annotations

import json
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
    return names


def report_path(root: Path, season: str) -> Path:
    return Path(root) / f"{season}-FluBNF-season-report.html"


def _plotlyjs() -> str:
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def _player_js() -> str:
    return PLAYER_SRC.read_text(encoding="utf-8")


def _newest_input(root: Path) -> float:
    """Newest mtime among the export's inputs: stored weeks, scores.json,
    settled truth, player.js, this builder, playback_cache/*.json, the hub's
    official model-output dirs (new comparators land there before any cache
    rebuild), run_meta.json (wall time) and nau.css (theme tokens).
    """
    times = [p.stat().st_mtime for p in retro.season_sample_files(root)]
    sf = root / "scores.json"
    if sf.is_file():
        times.append(sf.stat().st_mtime)
    from app.core.data import truth_mtime
    times.append(truth_mtime())          # the report scores against it
    if PLAYER_SRC.is_file():
        times.append(PLAYER_SRC.stat().st_mtime)
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

#: in order: the two shipped members, the research member. Older
#: scores.json files also carry the retired blend's rows; they are not shown.
SEASON_MODELS = ("pf", "analogue", "pf2s")


def _cumulative_curves(df) -> dict:
    """{model: [(iso week, cumulative relWIS)]} per SEASON_MODELS entry,
    the season page's series (mirrors server.retro_results)."""
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


def _summary_block(root: Path, weeks: list, payloads: dict,
                   names: dict | None = None) -> str:
    """The static season verdict, printed ahead of the player.

    Tiles: the final week's cum_rel (the numbers the player's last frame
    shows), plus the US tile/row with its provenance label (or a stated
    reason when absent). Per-state table from scores.json (pooled gate), or
    a statement when unscored. Names from `names` (names_for_root)."""
    names = names_for_root(root) if names is None else names
    final = payloads.get(weeks[-1]) or {}
    stats = final.get("stats") or {}
    tiles = []
    for m in SEASON_MODELS:
        v = (stats.get(m) or {}).get("cum_rel")
        if v is None:
            continue
        cls = "ok" if v < 1 else "bad"
        tiles.append('<div class="tile"><div class="tilename">'
                     + names.get(m, m) + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div></div>')
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
    for m in have:
        if not (us and us.get(m)):
            continue
        # always labelled fitted vs constructed: different model outputs
        v = us[m]
        cls = "ok" if v < 1 else "bad"
        sub = ("fitted at the national level, outside the pooled figures"
               if us.is_fitted else us.fallback_note
               + ", states treated as independent")
        tiles.append('<div class="tile"><div class="tilename">'
                     + us.short_label + ": " + names.get(m, m)
                     + '</div>'
                     + f'<div class="tileval {cls}">{v:.3f}</div>'
                     + f'<div class="hint">{sub}</div></div>')
    if have:
        # cell coverage when the scores file supplies it
        n = int((df.model == have[0]).sum())
        if n:
            cover = (f"the season's {n} scored {names.get(have[0], have[0])}"
                     " cells")
    if df is not None and "location" in df.columns:
        if us:
            # the national row leads as a distinct, labelled row (console placement)
            cells = [f"<td>{us.short_label}</td>"]
            for m in have:
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
            for m in have:
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
                  '<table><thead><tr><th>State</th>'
                  + "".join(f'<th class="num">{names.get(m, m)}</th>'
                            for m in have)
                  + '</tr></thead><tbody>'
                  + "".join(rows) + "</tbody></table>"
                  + (f'<p class="hint">{us.note}</p>' if us else ""))
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
            f"{usn.POOLED_SCOPE_NOTE}</p>"
            # the file leaves the machine: it carries the convention note itself
            f'<p class="hint">{relwis.PUBLISHED_CONVENTION_NOTE}</p>'
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
    data = {"season": season, "weeks": weeks, "payloads": payloads}
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
            .replace("@@MAXIDX@@", str(len(weeks) - 1))
            .replace("@@TIMING@@", timing_note)
            .replace("@@SIZENOTE@@", size_note)
            .replace("@@SUMMARY@@", summary)
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
   <h2>Live relWIS</h2>
   <table id="pb-stats"><thead><tr><th>Model</th><th class="num">Week</th>
    <th class="num">Cumulative</th></tr></thead><tbody></tbody></table>
   <p class="hint" id="pb-status" aria-live="polite"></p>
   <p class="hint" id="pb-offhint" hidden>official comparators appear after
    Update data</p>
   <p class="hint">relWIS below 1 beats the CDC FluSight baseline, ratio of
    sums; cumulative pools every week so far.</p>
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
// the season tree's own model names (report_season.names_for_root), set
// before anything draws: a sealed record or a replay from before the
// Oracle step stores the particle filter alone under pf, and the player
// must title it as the summary above does
@@NAMES@@
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
