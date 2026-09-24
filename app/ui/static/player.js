/* FluBNF shared season player core (flubnf-player-v1)

   One player, two hosts: the console's season page loads it with a script
   tag (network-backed payloads); app/core/report_season.py inlines it
   verbatim into the standalone season report (embedded-JSON payloads).

   Host contract, FluBNFPlayer.init(cfg):
     weeks         required: ordered list of ISO asof dates
     getPayload    required: function(week) -> Promise of payload or null
     mode          "live" or "static" (informational)
     catalog       optional {models, officials, locations}: build the
                   controls immediately from this union; omitted, they
                   build lazily from the first payload that arrives
     us            optional {provenance, label, short_label, note,
                   fitted, fallback, fallback_note} from app/core/us_national;
                   provenance is fitted | aggregated (sum of states) |
                   officials_only. Omitted: officials only (never guessed)
     seasonOfficials optional list of officials that submitted in some week;
                   separates "no submission" from "pending". Omitted: falls
                   back to catalog.officials, then accumulates from payloads
     palette       optional function() -> theme colors, re-read per redraw
     payloadError  optional function(week) -> message for a failed week
     isCached      optional function(week) -> true when getPayload(week)
                   resolves without a wait (drives the loading hints)
     detailVisible optional function() -> false while the host shows some
                   other view (the console's outlook map); stats still
                   update on every seek either way
     onSeek        optional function(week, idx): host hook on every seek
     preload       optional function(week): host hook for the next week
     plotHeight    optional plot height in px (default 400)
     ids           optional DOM id overrides, see DEFAULT_IDS

   Safari-safe: no lookbehind regexes, nothing asynchronous at top level.
   The payload variable is ALWAYS `pl` (a contract test checks the fields
   read against the playback API). */
(function(root){
'use strict';

var MARKER = 'FluBNF shared season player core (flubnf-player-v1)';

// the two CDC comparators always get toggles, even before any submission
var OFFICIALS = ['FluSight-baseline', 'FluSight-ensemble'];

// ------------------------------------------------------ US national

// THE three provenance states of the US national series. The host resolves
// which applies (app/core/us_national) and passes cfg.us; these labels are
// the fallback and claim the LEAST (officials only). Fitted and
// sum-of-states are different outputs, so every US label names which.
var US_PROVENANCE = {FITTED: 'fitted', AGGREGATED: 'aggregated',
                     OFFICIALS: 'officials_only'};
var US_LABELS = /*US_LABELS_JSON*/{
  "fitted": "US national (fitted)",
  "aggregated": "US national (sum of states)",
  "officials_only": "US (official models only)"
}/*END_US_LABELS_JSON*/;

// anything unrecognised, absent or malformed reads as officials only
function usProvenance(us){
  var p = us && us.provenance;
  return (p === US_PROVENANCE.FITTED || p === US_PROVENANCE.AGGREGATED)
    ? p : US_PROVENANCE.OFFICIALS;
}

// the host's resolved label when sent, else the provenance literal
function usLabel(us){
  if(us && us.label) return String(us.label);
  return US_LABELS[usProvenance(us)];
}

// mirrors app/core/us_national.is_us
function isUS(loc){
  var s = String(loc == null ? '' : loc).replace(/^\s+|\s+$/g, '')
            .toUpperCase();
  return s === 'US' || s === 'US (NATIONAL)' || s === 'UNITED STATES'
      || s === 'USA';
}

// title/legend/filename text: the US row by its provenance label
function locLabel(loc, us){
  return isUS(loc) ? usLabel(us) : String(loc);
}

// one location's entry in a payload map; the national row matches any US
// spelling, not just 'US'
function pickLoc(map, loc){
  if(!map) return null;
  if(map[loc] !== undefined) return map[loc];
  if(!isUS(loc)) return null;
  var ks = Object.keys(map);
  for(var i = 0; i < ks.length; i++)
    if(isUS(ks[i])) return map[ks[i]];
  return null;
}

// THE one model-name map for every surface. Python parses the marked JSON
// (app/core/report_season.py model_names), so keep it pure JSON between the
// markers. "analogue" is the Groundhog; "ensemble" is retired (stored runs
// before 2026-09-22). Hub model_ids are built in app/core/submit.py.
var MODEL_NAMES = /*MODEL_NAMES_JSON*/{
  "ensemble": "FluBNF Ensemble (retired)",
  "pf": "Oracle SIHRS",
  "analogue": "Groundhog",
  "pf2s": "Two-strain SIHRS",
  "FluSight-ensemble": "FluSight ensemble (official)",
  "FluSight-baseline": "FluSight baseline (official)"
}/*END_MODEL_NAMES_JSON*/;

// THE one member-color map (same marked-JSON contract; Python's
// model_colors parses it), so a member wears one color everywhere. Every
// pair that can share a chart is 60+ apart under Vienot deuteranopia and
// protanopia, and pf/pf2s hold 3:1 on all eight theme grounds (audited in
// test_a11y_modes.py), so the CV-safe mode deliberately does
// NOT swap these member colors. Keep it pure JSON between the markers.
var MODEL_COLORS = /*MODEL_COLORS_JSON*/{
  "ensemble": "#34C0F0",
  "pf": "#1979FF",
  "analogue": "#FFC72C",
  "pf2s": "#A66395"
}/*END_MODEL_COLORS_JSON*/;

// THE season-line palette's RED-GREEN-SAFE set (marked JSON, parsed by
// report_v2.season_colors). nau.css --season-1..6 is the normal-vision
// default; data-vision="cvd" remaps it onto --season-cvd-1..6, which equal
// this list. Charts resolve the tokens per draw and fall back here (the
// fixed-dark report). Every adjacent pair, and index 0 against both --gold
// variants, is 60+ apart under Vienot deuteranopia/protanopia and in normal
// vision; seasons color newest-first so the pair beside the gold newest
// line is the audited one. Any change here or in the nau.css tokens must
// re-clear app/tests/test_season_palette.py. Keep it pure JSON between the
// markers.
var SEASON_COLORS = /*SEASON_COLORS_JSON*/[
  "#A87300", "#3375FB", "#C9568C", "#0087AF", "#B96D36", "#8568E3"
]/*END_SEASON_COLORS_JSON*/;

// --season-N token where the page has the console stylesheet, else the
// SEASON_COLORS literal; i counts newest-first from 0 and cycles
function seasonColor(i){
  var n = SEASON_COLORS.length, k = ((i % n) + n) % n;
  try{
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue('--season-' + (k + 1)).trim();
    if(v) return v;
  }catch(e){}
  return SEASON_COLORS[k];
}

// an official model absent for the WHOLE season gets a disabled toggle
// carrying this note instead of silently drawing nothing
var UNAVAIL_NOTE = ' (fetch via Update data on the Data tab)';

// an official that submitted somewhere in the season but not this week
// (outside the competition window) keeps a live toggle with this note
var WEEK_NOTE = ' (no official submission this week)';

var DEFAULT_IDS = {prev: 'pb-prev', play: 'pb-play', next: 'pb-next',
  speed: 'pb-speed', scrub: 'pb-scrub', week: 'pb-week', loc: 'fd-loc',
  lock: 'fd-lock', models: 'fd-models', plot: 'fd-plot', msg: 'fd-msg',
  stats: 'pb-stats', status: 'pb-status', offhint: 'pb-offhint'};

// the report's fixed dark kit (the console passes its CSS variables).
// `card` is the explicit chart background so a saved PNG has an opaque ground.
var DEFAULT_PALETTE = {ink: '#E9EAF4', mut: '#9AA1C4', line: '#262A45',
  card: '#151729',
  models: MODEL_COLORS,
  flusightEnsemble: '#C7CCDD'};

var PCONF = {responsive: true, displaylogo: false, scrollZoom: true,
             doubleClick: 'reset'};

// PCONF plus save-PNG options: 2x scale, filename naming location and week
function frameConf(loc, week){
  var c = {}, k;
  for(k in PCONF) c[k] = PCONF[k];
  c.toImageButtonOptions = {format: 'png', scale: 2,
    filename: ('flubnf_' + loc + '_' + week).replace(/[^\w-]+/g, '_')};
  return c;
}

// ---------------------------------------------------------- pure helpers

// root font size in px, so plotly text (px only) tracks the A-/A/A+ control
function rootFont(){
  try{
    return parseFloat(
      getComputedStyle(document.documentElement).fontSize) || 16;
  }catch(e){ return 16; }
}

function rgba(c, a){
  if(c && c[0] === '#' && c.length === 7){
    var n = parseInt(c.slice(1), 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
      + (n & 255) + ',' + a + ')';
  }
  return c;
}

function addDays(iso, n){
  var d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function dashOf(m){
  return m === 'FluSight-baseline' ? 'dot'
       : m === 'FluSight-ensemble' ? 'dash' : 'solid';
}

function nameOf(m){
  return MODEL_NAMES[m] || m;
}

// a user-set range from a plotly relayout event, in either shape plotly
// emits: 'xaxis.range[0]'/'[1]' pairs, or 'xaxis.range'
function relayoutRange(ev, axis){
  var a = ev[axis + '.range[0]'], b = ev[axis + '.range[1]'];
  if(a !== undefined && b !== undefined) return [a, b];
  var r = ev[axis + '.range'];
  if(r && r.length === 2) return [r[0], r[1]];
  return null;
}

// fold one relayout event into the stored user view {x, y}: zoom/pan sets
// it, an autorange reset clears it, anything else leaves it
function viewStateUpdate(cur, ev){
  cur = cur || {x: null, y: null};
  if(!ev) return cur;
  if(ev['xaxis.autorange'] || ev['yaxis.autorange'])
    return {x: null, y: null};
  var x = relayoutRange(ev, 'xaxis'), y = relayoutRange(ev, 'yaxis');
  if(!x && !y) return cur;
  return {x: x || cur.x, y: y || cur.y};
}

// an official is available only when this week's official dict carries it
function officialAvailability(pl, officials){
  var off = (pl && pl.official) || {}, out = {};
  officials.forEach(function(m){ out[m] = !!off[m]; });
  return out;
}

// two-tier availability verdict for one official model's toggle:
//   present this week            -> enabled, no note
//   absent this week, but the model submitted somewhere in the season
//                                -> enabled, transient no-submission note
//   absent across the whole season
//                                -> disabled, the Update-data fix note
// the toggle's checked state is never touched in any tier
function availabilityTier(weekHas, seasonHas){
  if(weekHas) return {disabled: false, note: ''};
  if(seasonHas) return {disabled: false, note: WEEK_NOTE};
  return {disabled: true, note: UNAVAIL_NOTE};
}

// one WEEK cell of the stats table: a real score wins; a season-cataloged
// official that filed nothing this week reads "no submission"; anything
// else (including a week whose payload never arrived) reads "pending"
function weekCellState(v, isOfficial, weekKnown, weekHas, seasonHas){
  if(typeof v === 'number' && isFinite(v)) return 'score';
  if(isOfficial && weekKnown && !weekHas && seasonHas) return 'nosub';
  return 'pending';
}

// models offered, in display order: the ones that ship. A stored season's
// retired blend is never offered (report_v2.RETIRED_MODELS is the same set)
var RETIRED_MODELS = ['ensemble'];
function offeredModels(have){
  return ['pf', 'analogue', 'pf2s'].filter(function(m){
    return have[m] && RETIRED_MODELS.indexOf(m) < 0;
  });
}

// caption when a frame draws no fan: `available` models cover the location
// this week, `enabled` of them are toggled on. For US the reason depends on
// provenance (officials are the only source when nothing was fitted).
function noForecastNote(loc, available, enabled, us){
  if(available > 0 && enabled > 0) return '';
  if(available > 0) return 'no models enabled';
  if(isUS(loc)){
    var p = usProvenance(us);
    if(p === US_PROVENANCE.FITTED)
      return 'no US national forecast stored for this week';
    if(p === US_PROVENANCE.AGGREGATED)
      return 'no US fan: the sum-of-states aggregate is a season score, '
        + 'not a weekly forecast (choose a state)';
    return 'no official US submission this week; our forecasts are per '
      + 'state (choose a state)';
  }
  return 'no forecast for ' + loc + ' this week';
}

// ---------------------------------------------------------------- player

function createPlayer(cfg){
  var weeks = cfg.weeks || [];
  var ids = {}, k;
  for(k in DEFAULT_IDS) ids[k] = DEFAULT_IDS[k];
  if(cfg.ids) for(k in cfg.ids) ids[k] = cfg.ids[k];
  var el = {};
  for(k in ids) el[k] = document.getElementById(ids[k]);

  var pal = function(){
    return cfg.palette ? cfg.palette() : DEFAULT_PALETTE;
  };
  var detailVisible = cfg.detailVisible || function(){ return true; };
  var isCached = cfg.isCached || function(){ return true; };

  var P = {idx: (el.scrub && +el.scrub.value) || 0, playing: false,
           timer: null, loc: null, built: false, on: {}, pl: null,
           user: {x: null, y: null}, bound: false, applying: false,
           suppress: false};
  var ALLM = [], OFFS = OFFICIALS.slice();

  // season-level official availability: seeded from the host, then grown
  // by every payload seen
  var seasonOffs = {};
  ((cfg.seasonOfficials || (cfg.catalog && cfg.catalog.officials)) || [])
    .forEach(function(m){ seasonOffs[m] = 1; });

  function colorOf(m){
    var p = pal();
    if(m === 'FluSight-ensemble') return p.flusightEnsemble;
    return (p.models || {})[m] || p.mut;
  }

  function failMsg(w, dflt){
    var m = cfg.payloadError ? cfg.payloadError(w) : null;
    return m || dflt;
  }

  // ---- controls: built once, from cfg.catalog (the static host passes
  // the union across every embedded week) or from the first payload ----
  function buildControls(pl){
    if(P.built) return;
    var cat = cfg.catalog || null;
    if(!cat && !pl) return;
    P.built = true;
    var offs = {};
    OFFICIALS.forEach(function(m){ offs[m] = 1; });
    ((cat && cat.officials) || []).forEach(function(m){ offs[m] = 1; });
    if(pl) Object.keys(pl.official || {}).forEach(function(m){
      offs[m] = 1;
    });
    OFFS = Object.keys(offs).sort();
    var have = {};
    ((cat && cat.models) || (pl ? Object.keys(pl.models || {}) : []))
      .forEach(function(m){ have[m] = 1; });
    // the models that ship, never the retired blend (offeredModels)
    var ours = offeredModels(have);
    ALLM = ours.concat(OFFS);
    var dflt = {ensemble: true, pf: true, analogue: true};
    ALLM.forEach(function(m){ if(!(m in P.on)) P.on[m] = !!dflt[m]; });
    el.models.innerHTML = ALLM.map(function(m){
      return '<label class="ck"><input type="checkbox" data-m="' + m + '"'
        + (P.on[m] ? ' checked' : '') + '> <span class="sw" '
        + 'style="background:' + colorOf(m) + '"></span>' + nameOf(m)
        + '<span class="hint" data-avail="' + m + '"></span></label>';
    }).join('');
    el.models.querySelectorAll('input').forEach(function(c){
      c.addEventListener('change', function(){
        P.on[c.dataset.m] = c.checked;
        if(detailVisible()) drawFC(); else renderStats(P.pl);
      });
    });
    // the US entry leads and names its provenance; every US spelling in
    // the payload folds into it (never two US rows)
    var locs = ((cat && cat.locations) || (pl ? (pl.locations || []) : []))
      .filter(function(l){ return !isUS(l); });
    el.loc.innerHTML =
      '<option value="US">' + usLabel(cfg.us) + '</option>'
      + locs.map(function(l){ return '<option>' + l + '</option>'; })
        .join('');
    P.loc = P.loc || locs[0] || 'US';
    el.loc.value = P.loc;
    el.loc.addEventListener('change', function(){
      P.loc = el.loc.value;
      P.user = {x: null, y: null};   // a new location voids the hand zoom
      drawFC();
    });
  }

  // ---- per-model availability, refreshed on every payload (tiers: see
  // availabilityTier); the checked state is never touched ----
  function updateAvailability(pl){
    if(!pl) return;
    Object.keys(pl.official || {}).forEach(function(m){
      seasonOffs[m] = 1;
    });
    if(!P.built) return;
    var av = officialAvailability(pl, OFFS);
    OFFS.forEach(function(m){
      var box = el.models.querySelector('input[data-m="' + m + '"]');
      var note = el.models.querySelector('[data-avail="' + m + '"]');
      if(!box) return;
      var tier = availabilityTier(av[m], !!seasonOffs[m]);
      box.disabled = tier.disabled;
      if(note) note.textContent = tier.note;
    });
  }

  // ---- live stats table: per enabled model, this week and cumulative ----
  function renderStats(pl){
    P.pl = pl || null;
    if(pl) buildControls(pl);
    updateAvailability(pl);
    var tb = el.stats.querySelector('tbody');
    // a missing score reads "pending", never NaN
    var fmt = function(v){
      return (typeof v === 'number' && isFinite(v))
        ? '<td class="num ' + (v < 1 ? 'ok' : 'bad') + '">'
          + v.toFixed(3) + '</td>'
        : '<td class="num hint">pending</td>';
    };
    // only the week cell distinguishes the blanks; the cumulative cell keeps
    // its running number through gap weeks
    var av = pl ? officialAvailability(pl, OFFS) : null;
    var weekCell = function(v, m){
      var s = weekCellState(v, OFFS.indexOf(m) >= 0, !!av,
                            !!(av && av[m]), !!seasonOffs[m]);
      return s === 'nosub' ? '<td class="num hint">no submission</td>'
                           : fmt(s === 'score' ? v : null);
    };
    var rows = [];
    ALLM.forEach(function(m){
      if(!P.on[m]) return;
      var st = pl && pl.stats ? pl.stats[m] : null;
      var dbg = (st && st.debug)
        ? '<tr><td colspan="3" class="hint" style="font-size:.78rem">'
          + String(st.debug).replace(/</g, '&lt;') + '</td></tr>'
        : '';
      rows.push('<tr><td><span class="sw" style="background:' + colorOf(m)
        + '"></span>' + nameOf(m) + '</td>'
        + weekCell(st ? st.week_rel : null, m)
        + fmt(st ? st.cum_rel : null) + '</tr>' + dbg);
    });
    tb.innerHTML = rows.join('')
      || '<tr><td colspan="3" class="hint">no models enabled</td></tr>';
    el.status.textContent =
      pl ? '' : failMsg(weeks[P.idx], 'stats unavailable for this week');
    // the panel-wide Update-data hint only for a season with NO official
    // submissions at all (gap weeks have per-toggle notes)
    if(el.offhint)
      el.offhint.hidden = !pl || Object.keys(pl.official || {}).length > 0
        || Object.keys(seasonOffs).length > 0;
  }

  // ---- forecast fan for one model: median plus 50% and 90% bands ----
  function fan(m, byH, w, ax, ay){
    var hs = Object.keys(byH)
      .filter(function(h){ return /^[1-4]$/.test(h); }).sort();
    if(!hs.length) return [];
    var xs = hs.map(function(h){ return addDays(w, 7 * (+h)); });
    var lv = function(h, t){
      var q = byH[h] || {}, qk;
      for(qk in q){ if(Math.abs(parseFloat(qk) - t) < 1e-9) return q[qk]; }
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
    // ours: full bands; the official ensemble: a very faint band; the
    // official baseline: a bare dotted median, no band at all
    var official = OFFS.indexOf(m) >= 0;
    if(m !== 'FluSight-baseline'){
      band(hi95, lo5, official ? .05 : .10);
      band(hi75, lo25, official ? .08 : .18);
    }
    out.push({x: X, y: pad(med), mode: 'lines+markers', name: nameOf(m),
      line: {color: col, width: 2.2, dash: dashOf(m)}, marker: {size: 5},
      legendgroup: m});
    return out;
  }

  // ---- axis lock: fixed ranges per location so playback never jumps.
  // x: first truth date to last asof + 28 days; y: [0, 1.15 x truth peak].
  // Computed once per location ----
  var AXR = {loc: null, x: null, y: null};
  function lockRanges(pl, loc){
    if(AXR.loc === loc && AXR.x) return AXR;
    var truth = (pl.truth || {})[loc] || [];
    AXR.loc = loc; AXR.x = null; AXR.y = null;
    if(truth.length){
      var mx = 0;
      truth.forEach(function(r){ if(r[1] > mx) mx = r[1]; });
      AXR.x = [truth[0][0], addDays(weeks[weeks.length - 1], 28)];
      AXR.y = [0, 1.15 * (mx || 1)];
    }
    return AXR;
  }

  // ---- user view state: a hand zoom/pan overrides the lock (or auto)
  // ranges on every frame until a double click, a location change, or the
  // Lock axes toggle clears it ----
  function bindPlot(){
    if(P.bound || !el.plot.on) return;
    P.bound = true;
    el.plot.on('plotly_relayout', function(ev){
      if(P.applying || P.suppress) return;
      P.user = viewStateUpdate(P.user, ev);
    });
    el.plot.on('plotly_doubleclick', function(){
      // plotly's reset would restore the stored user view; drop it and
      // redraw so the lock (or auto) ranges reassert
      P.suppress = true;
      P.user = {x: null, y: null};
      setTimeout(function(){ P.suppress = false; drawFC(); }, 0);
    });
  }

  // ---- forecast detail: settled truth, a now marker, fans per model ----
  var fcSeq = 0;
  function drawFC(){
    var tok = ++fcSeq, w = weeks[P.idx];
    if(!isCached(w)) el.msg.textContent = 'loading ' + w + '…';
    cfg.getPayload(w).then(function(pl){
      if(tok !== fcSeq) return;
      renderStats(pl);
      if(!pl){
        if(el.plot.data) Plotly.purge(el.plot);
        el.msg.textContent =
          failMsg(w, 'forecast data unavailable for ' + w);
        return;
      }
      var loc = P.loc || 'US';
      var truth = pickLoc(pl.truth || {}, loc) || [];
      var pastX = [], pastY = [], futX = [], futY = [];
      truth.forEach(function(r){
        if(r[0] <= w){ pastX.push(r[0]); pastY.push(r[1]); }
        if(r[0] >= w){ futX.push(r[0]); futY.push(r[1]); }
      });
      var ax = pastX.length ? pastX[pastX.length - 1] : null;
      var ay = pastY.length ? pastY[pastY.length - 1] : null;
      var traces = [], avail = 0, drawn = 0;
      ALLM.forEach(function(m){
        var src = OFFS.indexOf(m) >= 0 ? (pl.official || {})[m]
                                       : (pl.models || {})[m];
        var byH = src ? pickLoc(src, loc) : null;
        if(!byH) return;
        avail++;
        if(!P.on[m]) return;
        drawn++;
        fan(m, byH, w, ax, ay).forEach(function(t){ traces.push(t); });
      });
      // an empty frame says WHY instead of standing as bare axes
      el.msg.textContent = noForecastNote(loc, avail, drawn, cfg.us);
      // truth drawn last (on top); the tail beyond now stays visible
      var p = pal();
      if(pastX.length) traces.push({x: pastX, y: pastY, mode: 'lines',
        name: 'truth (settled)', line: {color: p.ink, width: 2}});
      if(futX.length) traces.push({x: futX, y: futY, mode: 'lines',
        name: 'truth beyond now', opacity: .65,
        line: {color: p.ink, width: 1.3, dash: 'dot'}});
      // locked ranges, else autoscale; a stored user view beats both. The
      // title names US provenance on the figure itself.
      var title = locLabel(loc, cfg.us);
      var lock = (el.lock && el.lock.checked) ? lockRanges(pl, loc) : null;
      // automargin: tick labels size the margins (nothing clips at A+)
      var xa = {gridcolor: p.line, automargin: true};
      var ya = {gridcolor: p.line, rangemode: 'tozero', automargin: true};
      if(lock && lock.x){ xa.range = lock.x.slice(); xa.autorange = false; }
      if(lock && lock.y){ ya.range = lock.y.slice(); ya.autorange = false; }
      if(P.user.x){ xa.range = P.user.x.slice(); xa.autorange = false; }
      if(P.user.y){ ya.range = P.user.y.slice(); ya.autorange = false; }
      var fs = rootFont();
      var surf = p.card || '#151729';
      // text in root-proportional px (ticks/legend .85, title .95, now
      // marker .82); the top band scales so title and now label never
      // collide at A+
      var L = {title: {text: title + ' · forecasts as of ' + w,
                       font: {size: Math.round(fs * .95)}},
        height: cfg.plotHeight || 400,
        margin: {l: 8, r: 8, t: Math.round(fs * 2.4), b: 8},
        paper_bgcolor: surf, plot_bgcolor: surf,
        font: {color: p.ink, family: '"DM Sans",system-ui,sans-serif',
               size: Math.round(fs * .85)},
        // legend under the plot (a right-hand one ate a third of the width)
        legend: {orientation: 'h', x: 0, xanchor: 'left',
                 y: -0.22, yanchor: 'top'},
        xaxis: xa,
        yaxis: ya,
        shapes: [{type: 'line', x0: w, x1: w, yref: 'paper', y0: 0, y1: 1,
                  line: {color: p.mut, width: 1.2, dash: 'dot'}}],
        annotations: [{x: w, yref: 'paper', y: 1, yanchor: 'bottom',
                  showarrow: false, text: 'now',
                  font: {size: Math.round(fs * .82), color: p.mut}}]};
      P.applying = true;
      var done = function(){ P.applying = false; bindPlot(); };
      // the saved PNG's filename carries the same (provenance) label
      var pr = Plotly.react(el.plot, traces, L, frameConf(title, w));
      if(pr && pr.then) pr.then(done, done); else done();
    });
  }

  // ---- the player: prev / play-pause / next, speed, scrubber, arrows ----
  function labelWeek(){
    el.week.textContent = weeks[P.idx] + ' · week ' + (P.idx + 1)
      + ' of ' + weeks.length;
  }
  function seek(i, fromScrub){
    P.idx = Math.max(0, Math.min(weeks.length - 1, i));
    if(!fromScrub) el.scrub.value = P.idx;
    labelWeek();
    var w = weeks[P.idx];
    if(!isCached(w)) el.status.textContent = 'loading ' + w + '…';
    if(cfg.onSeek) cfg.onSeek(w, P.idx);
    if(detailVisible()){
      drawFC();
    } else {
      cfg.getPayload(w).then(function(pl){
        if(weeks[P.idx] === w) renderStats(pl);
      });
    }
    if(P.idx + 1 < weeks.length){    // preload: stepping stays smooth
      var nw = weeks[P.idx + 1];
      cfg.getPayload(nw);
      if(cfg.preload) cfg.preload(nw);
    }
  }
  // the accessible name tracks the state (WCAG 4.1.2)
  function labelPlay(on){
    el.play.setAttribute('aria-label', on ? 'Pause' : 'Play');
  }
  function setPlay(on){
    P.playing = on;
    el.play.textContent = on ? '❚❚ Pause' : '▶ Play';
    labelPlay(on);
    clearInterval(P.timer);
    if(on) P.timer = setInterval(function(){
      if(P.idx >= weeks.length - 1){ setPlay(false); return; }
      seek(P.idx + 1);
    }, +el.speed.value);
  }
  el.prev.onclick = function(){ seek(P.idx - 1); };
  el.next.onclick = function(){ seek(P.idx + 1); };
  el.play.onclick = function(){
    if(!P.playing && P.idx >= weeks.length - 1) seek(0);  // replay from top
    setPlay(!P.playing);
  };
  el.speed.onchange = function(){ if(P.playing) setPlay(true); };
  // scrub draws coalesce to one per animation frame (a fast drag otherwise
  // queues seconds of Plotly.react); other seeks stay immediate
  var wantIdx = null, rafP = false;
  el.scrub.addEventListener('input', function(){
    wantIdx = +el.scrub.value;
    if(rafP) return;
    rafP = true;
    requestAnimationFrame(function(){
      rafP = false;
      seek(wantIdx, true);
    });
  });
  // axis lock defaults ON and persists (localStorage guarded: file: and
  // private windows); toggling it clears the stored user view
  if(el.lock){
    try{ el.lock.checked = localStorage.getItem('flubnf-axis-lock') !== '0'; }
    catch(e){}
    el.lock.addEventListener('change', function(){
      try{
        localStorage.setItem('flubnf-axis-lock',
                             el.lock.checked ? '1' : '0');
      }catch(e){}
      P.user = {x: null, y: null};
      if(detailVisible()) drawFC();
    });
  }
  addEventListener('keydown', function(e){
    if(e.altKey || e.ctrlKey || e.metaKey) return;
    var t = e.target && e.target.tagName;
    if(t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    if(e.key === 'ArrowLeft'){ seek(P.idx - 1); e.preventDefault(); }
    else if(e.key === 'ArrowRight'){ seek(P.idx + 1); e.preventDefault(); }
  });
  addEventListener('themechange', function(){
    renderStats(P.pl);
    if(detailVisible()) drawFC();
  });
  // fired by the console's A-/A/A+ control (never in the static report)
  addEventListener('fontsizechange', function(){
    if(detailVisible()) drawFC();
  });

  labelPlay(false);      // the initial, paused state names itself correctly

  // the static host passes the catalog; the live host builds on first payload
  if(cfg.catalog) buildControls(null);

  return {
    seek: seek,
    idx: function(){ return P.idx; },
    week: function(){ return weeks[P.idx]; },
    drawFC: drawFC,
    renderStats: renderStats,
    setPlay: setPlay,
    viewState: function(){ return {x: P.user.x, y: P.user.y}; }
  };
}

var FluBNFPlayer = {
  MARKER: MARKER,
  init: createPlayer,
  MODEL_NAMES: MODEL_NAMES,
  MODEL_COLORS: MODEL_COLORS,
  SEASON_COLORS: SEASON_COLORS,
  seasonColor: seasonColor,
  _internals: {
    OFFICIALS: OFFICIALS,
    MODEL_NAMES: MODEL_NAMES,
    UNAVAIL_NOTE: UNAVAIL_NOTE,
    WEEK_NOTE: WEEK_NOTE,
    availabilityTier: availabilityTier,
    weekCellState: weekCellState,
    noForecastNote: noForecastNote,
    offeredModels: offeredModels,
    RETIRED_MODELS: RETIRED_MODELS,
    US_LABELS: US_LABELS,
    US_PROVENANCE: US_PROVENANCE,
    usProvenance: usProvenance,
    usLabel: usLabel,
    isUS: isUS,
    locLabel: locLabel,
    pickLoc: pickLoc,
    rgba: rgba,
    addDays: addDays,
    dashOf: dashOf,
    nameOf: nameOf,
    relayoutRange: relayoutRange,
    viewStateUpdate: viewStateUpdate,
    officialAvailability: officialAvailability
  }
};
root.FluBNFPlayer = FluBNFPlayer;
if(typeof module !== 'undefined' && module.exports)
  module.exports = FluBNFPlayer;
})(typeof window !== 'undefined' ? window
   : typeof globalThis !== 'undefined' ? globalThis : this);
