"""Season report export: one self-contained interactive HTML file.

The console's season player, frozen into a downloadable artifact. The file
carries plotly.js inline (the report_v2 pattern), every stored week's
playback payload embedded as one JSON block, and the player implemented in
inline JS against that block. No server and no network are needed; the file
works from a desktop or an email attachment.

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

from app.core import playback

# PyBNF brand palette (dark), shared with report_v2
INK = "#E9EAF4"; MUT = "#9AA1C4"; PAPER = "#0C0D17"; CARD = "#151729"
LINE = "#262A45"; ACCENT = "#34C0F0"

# model colors, matching the console's season player: ensemble cyan,
# pf periwinkle, analogue true gold, pf2s teal; officials muted grey
MODEL_COLORS = {"ensemble": ACCENT, "pf": "#6E8FD0",
                "analogue": "#FFC72C", "pf2s": "#2BB5A0"}

SIZE_WARN_BYTES = 25 * 1024 * 1024


def report_path(root: Path, season: str) -> Path:
    return Path(root) / f"{season}-FluBNF-season-report.html"


def _plotlyjs() -> str:
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


def _newest_input(root: Path) -> float:
    """mtime of the newest report input: any samples.json, or scores.json."""
    times = [(root / "weeks" / w / "samples.json").stat().st_mtime
             for w in playback.season_weeks(root)]
    sf = root / "scores.json"
    if sf.is_file():
        times.append(sf.stat().st_mtime)
    return max(times)


def build_season_report(root: Path, season: str) -> Path:
    """Build (or reuse, when fresh) the self-contained season report."""
    root = Path(root)
    weeks = playback.season_weeks(root)
    if not weeks:
        raise playback.UnknownWeek(
            f"{season}: no completed weeks yet, so there is no season "
            "report to build.")
    out = report_path(root, season)
    newest = _newest_input(root)
    if out.is_file() and out.stat().st_mtime >= newest:
        return out
    payloads = {w: playback.build_week(root, season, w) for w in weeks}
    data = {"season": season, "weeks": weeks, "payloads": payloads}
    # "</" would end the embedding <script> early; "<\/" is the same JSON
    data_json = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    plotly_js = _plotlyjs()
    html = _compose(season, weeks, data_json, plotly_js, size_note="")
    size = len(html.encode("utf-8"))
    if size > SIZE_WARN_BYTES:
        note = ('<p class="warn">Size notice: this file is %.0f MB, above '
                'the 25 MB guideline. It remains fully functional, but it '
                'may open slowly and some mail systems will refuse to '
                'attach it.</p>' % (size / (1024 * 1024)))
        html = _compose(season, weeks, data_json, plotly_js, size_note=note)
    out.write_text(html)
    return out


def _compose(season: str, weeks: list, data_json: str, plotly_js: str,
             size_note: str) -> str:
    return (_PAGE
            .replace("@@SEASON@@", season)
            .replace("@@NWEEKS@@", str(len(weeks)))
            .replace("@@FIRST@@", weeks[0])
            .replace("@@LAST@@", weeks[-1])
            .replace("@@MAXIDX@@", str(len(weeks) - 1))
            .replace("@@SIZENOTE@@", size_note)
            .replace("@@PLOTLY@@", plotly_js)
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
   <p class="hint">relWIS below 1 beats the CDC FluSight baseline. Week
    scores the current forecast's cells; cumulative pools every week through
    the playback position.</p>
  </div>
 </div>
</div>
<script id="pbdata" type="application/json">@@DATA@@</script>
<script>
// FluBNF season player (export build): the same playback experience as the
// console's season page, driven by the embedded JSON block above instead of
// the playback API. The payload variable is ALWAYS named `pl` so the
// contract test can verify the JS reads only fields the API defines.
'use strict';
var DATA = JSON.parse(document.getElementById('pbdata').textContent);
var WEEKS = DATA.weeks, PAY = DATA.payloads;
var INK = '#E9EAF4', MUT = '#9AA1C4', LINE = '#262A45';
var COLORS = {ensemble: '#34C0F0', pf: '#6E8FD0',
              analogue: '#FFC72C', pf2s: '#2BB5A0'};
var PCONF = {responsive: true, displaylogo: false, scrollZoom: true,
             doubleClick: 'reset'};
var scrub = document.getElementById('pb-scrub');
var P = {idx: 0, playing: false, timer: null, loc: null, on: {}};
var ALLM = [], OFFS = [];

function colorOf(m){ return COLORS[m] || MUT; }
function dashOf(m){
  return m === 'FluSight-baseline' ? 'dot'
       : m === 'FluSight-ensemble' ? 'dash' : 'solid';
}
function rgba(c, a){
  var n = parseInt(c.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
    + (n & 255) + ',' + a + ')';
}
function addDays(iso, n){
  var d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// controls are built once, from the union across every embedded week, so a
// model or location present in only part of the season still gets a toggle
(function buildControls(){
  var models = {}, offs = {}, locs = {};
  WEEKS.forEach(function(w){
    var pl = PAY[w];
    if(!pl) return;
    Object.keys(pl.models || {}).forEach(function(k){ models[k] = 1; });
    Object.keys(pl.official || {}).forEach(function(k){ offs[k] = 1; });
    (pl.locations || []).forEach(function(l){ locs[l] = 1; });
  });
  OFFS = Object.keys(offs).sort();
  var ours = ['ensemble', 'pf', 'analogue', 'pf2s']
    .filter(function(k){ return models[k]; });
  ALLM = ours.concat(OFFS);
  var dflt = {ensemble: true, pf: true, analogue: true};
  ALLM.forEach(function(k){ P.on[k] = !!dflt[k]; });
  var box = document.getElementById('fd-models');
  box.innerHTML = ALLM.map(function(k){
    return '<label><input type="checkbox" data-m="' + k + '"'
      + (P.on[k] ? ' checked' : '') + '> <span class="sw" style="background:'
      + colorOf(k) + '"></span>' + k
      + (OFFS.indexOf(k) >= 0 ? ' (official)' : '') + '</label>';
  }).join('');
  box.querySelectorAll('input').forEach(function(c){
    c.addEventListener('change', function(){
      P.on[c.dataset.m] = c.checked;
      draw();
    });
  });
  // our retrospective members are per-state; the US entry is served by the
  // official models only, and says so
  var sel = document.getElementById('fd-loc');
  var names = Object.keys(locs).sort();
  sel.innerHTML = '<option value="US">US (official models only)</option>'
    + names.map(function(l){ return '<option>' + l + '</option>'; }).join('');
  P.loc = names[0] || 'US';
  sel.value = P.loc;
  sel.addEventListener('change', function(){ P.loc = sel.value; draw(); });
})();

// ---- live stats table: per enabled model, this week and cumulative ----
function renderStats(pl){
  var tb = document.querySelector('#pb-stats tbody');
  var fmt = function(v){
    return v == null
      ? '<td class="num hint">n/a</td>'
      : '<td class="num ' + (v < 1 ? 'ok' : 'bad') + '">'
        + v.toFixed(3) + '</td>';
  };
  var rows = [];
  ALLM.forEach(function(m){
    if(!P.on[m]) return;
    var st = pl && pl.stats ? pl.stats[m] : null;
    rows.push('<tr><td><span class="sw" style="background:' + colorOf(m)
      + '"></span>' + m + '</td>' + fmt(st ? st.week_rel : null)
      + fmt(st ? st.cum_rel : null) + '</tr>');
  });
  tb.innerHTML = rows.join('')
    || '<tr><td colspan="3" class="hint">no models enabled</td></tr>';
  document.getElementById('pb-status').textContent =
    pl ? '' : 'stats unavailable for this week';
}

// ---- forecast fan for one model: median plus 50% and 90% bands ----
function fan(m, byH, w, ax, ay){
  var hs = Object.keys(byH).filter(function(k){ return /^[1-4]$/.test(k); })
    .sort();
  if(!hs.length) return [];
  var xs = hs.map(function(h){ return addDays(w, 7 * (+h)); });
  var lv = function(h, t){
    var q = byH[h] || {};
    for(var k in q){ if(Math.abs(parseFloat(k) - t) < 1e-9) return q[k]; }
    return null;
  };
  var seq = function(t){ return hs.map(function(h){ return lv(h, t); }); };
  var med = seq(.5), lo5 = seq(.05), hi95 = seq(.95),
      lo25 = seq(.25), hi75 = seq(.75);
  var anchored = ax != null;
  var X = anchored ? [ax].concat(xs) : xs;
  var pad = function(a){ return anchored ? [ay].concat(a) : a; };
  var col = colorOf(m), out = [];
  var band = function(hi, lo, a){
    if(!hi.some(function(v){ return v != null; })
       || !lo.some(function(v){ return v != null; })) return;
    out.push({x: X, y: pad(hi), mode: 'lines', line: {width: 0},
      showlegend: false, hoverinfo: 'skip', legendgroup: m});
    out.push({x: X, y: pad(lo), mode: 'lines', line: {width: 0},
      fill: 'tonexty', fillcolor: rgba(col, a),
      showlegend: false, hoverinfo: 'skip', legendgroup: m});
  };
  band(hi95, lo5, .10);
  band(hi75, lo25, .18);
  out.push({x: X, y: pad(med), mode: 'lines+markers', name: m,
    line: {color: col, width: 2.2, dash: dashOf(m)}, marker: {size: 5},
    legendgroup: m});
  return out;
}

// ---- forecast detail: settled truth, a now marker, fans per model ----
function draw(){
  var w = WEEKS[P.idx];
  var pl = PAY[w] || null;
  renderStats(pl);
  var msg = document.getElementById('fd-msg');
  var el = document.getElementById('fd-plot');
  if(!pl){
    if(el.data) Plotly.purge(el);
    msg.textContent = 'forecast data unavailable for ' + w;
    return;
  }
  msg.textContent = '';
  var loc = P.loc || 'US';
  var truth = (pl.truth || {})[loc] || [];
  var pastX = [], pastY = [], futX = [], futY = [];
  truth.forEach(function(r){
    if(r[0] <= w){ pastX.push(r[0]); pastY.push(r[1]); }
    if(r[0] >= w){ futX.push(r[0]); futY.push(r[1]); }
  });
  var ax = pastX.length ? pastX[pastX.length - 1] : null;
  var ay = pastY.length ? pastY[pastY.length - 1] : null;
  var traces = [];
  ALLM.forEach(function(m){
    if(!P.on[m]) return;
    var src = OFFS.indexOf(m) >= 0 ? (pl.official || {})[m]
                                   : (pl.models || {})[m];
    var byH = src ? src[loc] : null;
    if(!byH) return;
    fan(m, byH, w, ax, ay).forEach(function(t){ traces.push(t); });
  });
  // truth drawn last so it sits on top; the tail beyond the now marker
  // stays visible so forecast accuracy is legible at a glance
  traces.push({x: pastX, y: pastY, mode: 'lines', name: 'truth (settled)',
    line: {color: INK, width: 2}});
  if(futX.length) traces.push({x: futX, y: futY, mode: 'lines',
    name: 'truth beyond now', opacity: .65,
    line: {color: INK, width: 1.3, dash: 'dot'}});
  var L = {title: {text: loc + ' \\u00b7 forecasts as of ' + w,
                   font: {size: 14}},
    height: 420, margin: {l: 50, r: 20, t: 34, b: 40},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: {color: INK},
    xaxis: {gridcolor: LINE},
    yaxis: {gridcolor: LINE, rangemode: 'tozero'},
    shapes: [{type: 'line', x0: w, x1: w, yref: 'paper', y0: 0, y1: 1,
              line: {color: MUT, width: 1.2, dash: 'dot'}}],
    annotations: [{x: w, yref: 'paper', y: 1, yanchor: 'bottom',
              showarrow: false, text: 'now',
              font: {size: 11, color: MUT}}]};
  Plotly.react(el, traces, L, PCONF);
}

// ---- the player: prev / play-pause / next, speed, scrubber, arrows ----
function labelWeek(){
  document.getElementById('pb-week').textContent =
    WEEKS[P.idx] + ' \\u00b7 week ' + (P.idx + 1) + ' of ' + WEEKS.length;
}
function seek(i, fromScrub){
  P.idx = Math.max(0, Math.min(WEEKS.length - 1, i));
  if(!fromScrub) scrub.value = P.idx;
  labelWeek();
  draw();
}
function setPlay(on){
  P.playing = on;
  document.getElementById('pb-play').textContent =
    on ? '\\u275a\\u275a Pause' : '\\u25b6 Play';
  clearInterval(P.timer);
  if(on) P.timer = setInterval(function(){
    if(P.idx >= WEEKS.length - 1){ setPlay(false); return; }
    seek(P.idx + 1);
  }, +document.getElementById('pb-speed').value);
}
document.getElementById('pb-prev').onclick = function(){ seek(P.idx - 1); };
document.getElementById('pb-next').onclick = function(){ seek(P.idx + 1); };
document.getElementById('pb-play').onclick = function(){
  if(!P.playing && P.idx >= WEEKS.length - 1) seek(0);  // replay from the top
  setPlay(!P.playing);
};
document.getElementById('pb-speed').onchange = function(){
  if(P.playing) setPlay(true);
};
scrub.addEventListener('input', function(){ seek(+scrub.value, true); });
addEventListener('keydown', function(e){
  if(e.altKey || e.ctrlKey || e.metaKey) return;
  var t = e.target && e.target.tagName;
  if(t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
  if(e.key === 'ArrowLeft'){ seek(P.idx - 1); e.preventDefault(); }
  else if(e.key === 'ArrowRight'){ seek(P.idx + 1); e.preventDefault(); }
});
seek(0);
</script>
</main></body></html>"""
