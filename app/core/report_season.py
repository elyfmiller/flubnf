"""Season report export: one self-contained interactive HTML file.

The console's season player, frozen into a downloadable artifact. The file
carries plotly.js inline (the report_v2 pattern), every stored week's
playback payload embedded as one JSON block, and the SHARED player
(app/ui/static/player.js, the same file the console's season page loads)
inlined verbatim, fed by a getPayload backed by the embedded block. Every
future player feature lands in the console and in this export
automatically. No server and no network are needed; the file works from a
desktop or an email attachment.

Scope, by design: the export carries the forecast detail view and the live
relWIS table. The categorical weekly maps are omitted, since 30-plus inline
SVG maps would multiply the file size for a view the console already serves
live; the header note says so.

Fixed dark kit theme, like report_v2: single-theme by design, every color
painted explicitly.

Caching: the report lands at <season_root>/<season>-FluBNF-season-report.html
and is reused while fresh (mtime vs every samples.json and scores.json),
matching the playback payload cache convention.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core import playback, retro
from app.core.runs import fmt_hms, settings_html, version_pairs

# PyBNF brand palette (dark), shared with report_v2
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"

# model colors, matching the console's season player: ensemble cyan,
# pf periwinkle, analogue true gold, pf2s teal; officials muted grey
MODEL_COLORS = {"ensemble": ACCENT, "pf": "#6E8FD0",
                "analogue": "#FFC72C", "pf2s": "#2BB5A0"}

SIZE_WARN_BYTES = 25 * 1024 * 1024

# the shared player: the very file the console's season page loads. It is
# inlined verbatim at build time so both hosts run identical player code.
PLAYER_SRC = Path(__file__).resolve().parents[1] / "ui" / "static" \
    / "player.js"


def report_path(root: Path, season: str) -> Path:
    return Path(root) / f"{season}-FluBNF-season-report.html"


def _plotlyjs() -> str:
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def _player_js() -> str:
    return PLAYER_SRC.read_text()


def _newest_input(root: Path) -> float:
    """mtime of the newest report input: any samples.json, scores.json, or
    the shared player source itself (a player fix must refresh the export).
    """
    times = [(root / "weeks" / w / "samples.json").stat().st_mtime
             for w in playback.season_weeks(root)]
    sf = root / "scores.json"
    if sf.is_file():
        times.append(sf.stat().st_mtime)
    if PLAYER_SRC.is_file():
        times.append(PLAYER_SRC.stat().st_mtime)
    # Rebuilt playback payloads must refresh the export too: official
    # comparator files arriving (Update data on a sparse clone) rebuild the
    # per-week caches without touching any input above, and a report built
    # earlier would keep serving "pending" stats forever (field-found, the
    # third organ of the same staleness disease).
    pc = root / "playback_cache"
    if pc.is_dir():
        times.extend(f.stat().st_mtime for f in pc.glob("*.json"))
    # the run record carries the header's wall-time line: a replay that
    # resumed and finished must refresh the export, not serve the old total
    mp = root / retro.META_NAME
    if mp.is_file():
        times.append(mp.stat().st_mtime)
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
        head = out.read_text()[:8192]
        if ((not archive or ARCHIVE_MARK in head)
                and (not settings_note or SETTINGS_MARK in head)):
            return out
    payloads = {w: playback.build_week(root, season, w) for w in weeks}
    data = {"season": season, "weeks": weeks, "payloads": payloads}
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    data_json = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    plotly_js = _plotlyjs()
    player_js = _player_js()
    timing_note = (_archive_note(archive) + _timing_note(root)
                   + settings_note)
    html = _compose(season, weeks, data_json, plotly_js, player_js,
                    size_note="", timing_note=timing_note)
    size = len(html.encode("utf-8"))
    if size > SIZE_WARN_BYTES:
        note = ('<p class="warn">Size notice: this file is %.0f MB, above '
                'the 25 MB guideline. It remains fully functional, but it '
                'may open slowly and some mail systems will refuse to '
                'attach it.</p>' % (size / (1024 * 1024)))
        html = _compose(season, weeks, data_json, plotly_js, player_js,
                        size_note=note, timing_note=timing_note)
    out.write_text(html)
    return out


def _compose(season: str, weeks: list, data_json: str, plotly_js: str,
             player_js: str, size_note: str, timing_note: str = "") -> str:
    return (_PAGE
            .replace("@@SEASON@@", season)
            .replace("@@NWEEKS@@", str(len(weeks)))
            .replace("@@FIRST@@", weeks[0])
            .replace("@@LAST@@", weeks[-1])
            .replace("@@MAXIDX@@", str(len(weeks) - 1))
            .replace("@@TIMING@@", timing_note)
            .replace("@@SIZENOTE@@", size_note)
            .replace("@@PLOTLY@@", plotly_js)
            .replace("@@PLAYERJS@@", player_js)
            .replace("@@DATA@@", data_json))


# The page template. Plain token replacement, never str.format: the JS and
# CSS are full of braces. Fixed dark palette painted inline throughout.
_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluBNF season report @@SEASON@@</title>
<script>@@PLOTLY@@</script>
<style>
 body{margin:0;background:#0C0D17;color:#E9EAF4;font:15px/1.55 system-ui}
 main{max-width:1180px;margin:0 auto;padding:1.4rem 1.2rem 3rem}
 h1{font-size:1.4rem;margin:.2rem 0}
 h2{font-size:1.05rem;margin:.2rem 0 .6rem}
 .accent{color:#34C0F0}
 .sub{color:#9AA1C4;margin:.2rem 0 1rem;font-size:.92rem}
 .warn{background:#2A2313;border:1px solid #8A6D3B;color:#F0C36D;
       border-radius:10px;padding:.6rem .8rem;font-size:.9rem}
 .card{background:#151729;border:1px solid #262A45;border-radius:12px;
       padding:.9rem;margin:.8rem 0}
 .row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
 button,select{background:#151729;color:#E9EAF4;border:1px solid #262A45;
   border-radius:9px;padding:.4rem .8rem;font:inherit;cursor:pointer}
 button:hover{border-color:#34C0F0}
 button:focus-visible{outline:2px solid #34C0F0;outline-offset:2px}
 input[type=range]{flex:1;min-width:160px;accent-color:#34C0F0}
 .hint{color:#9AA1C4;font-size:.82rem}
 .playgrid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:1rem}
 @media(max-width:1000px){.playgrid{grid-template-columns:1fr}}
 table{border-collapse:collapse;font-size:.85rem;width:100%;
       font-variant-numeric:tabular-nums}
 td,th{padding:.3rem .5rem;border-bottom:1px solid #262A45;text-align:left}
 th{color:#9AA1C4;font-weight:600;font-size:.72rem;text-transform:uppercase}
 td.num,th.num{text-align:right}
 .ok{color:#7FC97F}.bad{color:#E8A33D}
 .sw{width:11px;height:11px;border-radius:3px;display:inline-block;
     margin-right:.3rem;vertical-align:-1px}
 .fdmodels{display:flex;gap:.9rem;flex-wrap:wrap;margin:.3rem 0 .5rem}
 .fdmodels label{font-size:.85rem;display:inline-flex;align-items:center;
                 gap:.25rem}
</style></head><body><main>
<h1>FluBNF season report <span class="accent">@@SEASON@@</span></h1>
<p class="sub">@@NWEEKS@@ stored weeks, @@FIRST@@ to @@LAST@@. This file is
 self-contained: all forecast data is embedded and no server or network is
 needed. The export carries the forecast detail view and the live relWIS
 table; interactive maps live in the console.</p>
@@TIMING@@
@@SIZENOTE@@
<div class="card">
 <div class="row playerbar">
  <button type="button" id="pb-prev" title="Previous week (left arrow)"
    aria-label="Previous week">&#9664;</button>
  <button type="button" id="pb-play" aria-label="Play or pause">&#9654; Play</button>
  <button type="button" id="pb-next" title="Next week (right arrow)"
    aria-label="Next week">&#9654;</button>
  <select id="pb-speed" aria-label="Playback speed">
   <option value="500">0.5 s / week</option>
   <option value="1000" selected>1 s / week</option>
   <option value="2000">2 s / week</option>
  </select>
  <input type="range" id="pb-scrub" min="0" max="@@MAXIDX@@" step="1"
         value="0" aria-label="Week scrubber">
  <span class="hint" id="pb-week"></span>
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
   <p class="hint" id="pb-status"></p>
   <p class="hint" id="pb-offhint" hidden>official comparators appear after
    Update data fetches their submissions</p>
   <p class="hint">relWIS below 1 beats the CDC FluSight baseline. Week
    scores the current forecast's cells; cumulative pools every week through
    the playback position.</p>
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
var player = FluBNFPlayer.init({
  weeks: WEEKS,
  mode: 'static',
  getPayload: function(w){ return Promise.resolve(PAY[w] || null); },
  catalog: {models: Object.keys(UNION.models),
            officials: Object.keys(UNION.offs),
            locations: Object.keys(UNION.locs).sort()},
  plotHeight: 420
});
player.seek(0);
</script>
</main></body></html>"""
