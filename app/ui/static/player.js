/* FluBNF shared season player core (flubnf-player-v1)

   One player, two hosts. The console's retrospective season page loads this
   file with a script tag and feeds it a network-backed payload getter;
   app/core/report_season.py reads this same file at build time and inlines
   it verbatim into the standalone season report, feeding a payload getter
   backed by the report's embedded JSON block. Every player feature lands in
   both hosts automatically.

   Host contract, FluBNFPlayer.init(cfg):
     weeks         required: ordered list of ISO asof dates
     getPayload    required: function(week) -> Promise of payload or null
     mode          "live" or "static" (informational)
     catalog       optional {models, officials, locations}: build the
                   controls immediately from this union; omitted, they
                   build lazily from the first payload that arrives
     seasonOfficials optional list of official models that submitted in at
                   least one week of the season; drives the two-tier
                   availability of the official toggles, and with the
                   week's own official dict it separates "no submission"
                   from "pending" in the stats table. Omitted, it falls
                   back to catalog.officials (the static host's union) and
                   then to client-side accumulation as payloads load
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

   Kept Safari-safe on purpose: no lookbehind regexes and nothing
   asynchronous at the top level. The payload variable is ALWAYS named
   `pl` so the contract test can verify the JS reads only fields the
   playback API defines. */
(function(root){
'use strict';

var MARKER = 'FluBNF shared season player core (flubnf-player-v1)';

// the two CDC comparators are a fixed part of the UI: their toggles exist
// even when a week's payload carries no official submissions yet
var OFFICIALS = ['FluSight-baseline', 'FluSight-ensemble'];

// an official model absent for the WHOLE season gets a disabled toggle
// carrying this note instead of silently drawing nothing
var UNAVAIL_NOTE = ' (fetch via Update data on the Data tab)';

// an official model that submitted somewhere in the season but not this
// week (the competition window: mid-September and June weeks legitimately
// lack files) keeps a live toggle with this transient annotation; there is
// simply nothing to draw for it this frame
var WEEK_NOTE = ' (no official submission this week)';

var DEFAULT_IDS = {prev: 'pb-prev', play: 'pb-play', next: 'pb-next',
  speed: 'pb-speed', scrub: 'pb-scrub', week: 'pb-week', loc: 'fd-loc',
  lock: 'fd-lock', models: 'fd-models', plot: 'fd-plot', msg: 'fd-msg',
  stats: 'pb-stats', status: 'pb-status', offhint: 'pb-offhint'};

// the report's fixed dark kit; the console overrides with its CSS variables
var DEFAULT_PALETTE = {ink: '#E9EAF4', mut: '#9AA1C4', line: '#262A45',
  models: {ensemble: '#34C0F0', pf: '#6E8FD0', analogue: '#FFC72C',
           pf2s: '#2BB5A0'},
  flusightEnsemble: '#C7CCDD'};

var PCONF = {responsive: true, displaylogo: false, scrollZoom: true,
             doubleClick: 'reset'};

// ---------------------------------------------------------- pure helpers

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

// display names keep the two ensembles unmistakable in the legend, the
// model toggles, and the stats table
function nameOf(m){
  var names = {ensemble: 'NAU ensemble',
               'FluSight-ensemble': 'FluSight ensemble (official)',
               'FluSight-baseline': 'FluSight baseline (official)'};
  return names[m] || m;
}

// a user-set range from a plotly relayout event, in either of the two
// shapes plotly emits: 'xaxis.range[0]'/'[1]' pairs, or 'xaxis.range'
function relayoutRange(ev, axis){
  var a = ev[axis + '.range[0]'], b = ev[axis + '.range[1]'];
  if(a !== undefined && b !== undefined) return [a, b];
  var r = ev[axis + '.range'];
  if(r && r.length === 2) return [r[0], r[1]];
  return null;
}

// the view-state reducer: fold one relayout event into the stored user
// view {x, y}. A user zoom or pan (range keys) becomes the ACTIVE view;
// an autorange reset clears it; anything else leaves it untouched
function viewStateUpdate(cur, ev){
  cur = cur || {x: null, y: null};
  if(!ev) return cur;
  if(ev['xaxis.autorange'] || ev['yaxis.autorange'])
    return {x: null, y: null};
  var x = relayoutRange(ev, 'xaxis'), y = relayoutRange(ev, 'yaxis');
  if(!x && !y) return cur;
  return {x: x || cur.x, y: y || cur.y};
}

// per-model availability against the current payload: an official model is
// available only when this week's official dict actually carries it
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

// what one WEEK cell of the stats table reads. A real score always wins.
// Otherwise the two blank cases are distinguished: a season-cataloged
// official that filed nothing this week did not compete ("no submission"),
// while anything else is a score that has not been computed ("pending").
// weekKnown is false when the week's payload never arrived, in which case
// nothing can be concluded about who submitted and "pending" stands.
function weekCellState(v, isOfficial, weekKnown, weekHas, seasonHas){
  if(typeof v === 'number' && isFinite(v)) return 'score';
  if(isOfficial && weekKnown && !weekHas && seasonHas) return 'nosub';
  return 'pending';
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

  // season-level official availability: seeded once from the host (the
  // live host passes the server catalog, the static host's catalog union
  // covers it), then grown by every payload seen, so a hostless setup
  // still converges as weeks load
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
    var ours = ['ensemble', 'pf', 'analogue', 'pf2s']
      .filter(function(m){ return have[m]; });
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
    // our retrospective members are per-state; the US entry is served by
    // the official models only, and says so
    var locs = (cat && cat.locations) || (pl ? (pl.locations || []) : []);
    el.loc.innerHTML =
      '<option value="US">US (official models only)</option>'
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

  // ---- per-model availability, refreshed on every payload, two tiers:
  // absent this week but submitted somewhere in the season keeps a LIVE
  // toggle (with the transient no-submission note; the official simply
  // did not submit outside its competition window), while absent for the
  // whole season disables it with the Update-data fix. The user's checked
  // state is never touched either way ----
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
    // a missing score is quiet, never NaN or a crashed panel: "pending" for
    // a score not yet computed, "no submission" for a cataloged official
    // that simply filed nothing this week
    var fmt = function(v){
      return (typeof v === 'number' && isFinite(v))
        ? '<td class="num ' + (v < 1 ? 'ok' : 'bad') + '">'
          + v.toFixed(3) + '</td>'
        : '<td class="num hint">pending</td>';
    };
    // the week cell alone distinguishes the two blanks; the cumulative cell
    // keeps showing the real running number across the weeks that did have
    // a submission, so a gap week never blanks the season total
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
    // the whole-panel Update-data hint belongs only to a season with NO
    // official submissions at all; a mere in-season gap week is already
    // explained by the per-toggle notes and must not read as breakage
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
  // x spans the season window (first truth date to last asof + 28 days);
  // y spans [0, 1.15 x the season's truth peak for the location].
  // Computed once from the payload's full-season truth series and reused
  // until the location changes ----
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

  // ---- user view state: a hand zoom or pan is the ACTIVE view. It is
  // stored from plotly_relayout and reasserted on every subsequent frame,
  // overriding the lock (or auto) ranges, until it is cleared by a double
  // click, a location change, or the Lock axes toggle ----
  function bindPlot(){
    if(P.bound || !el.plot.on) return;
    P.bound = true;
    el.plot.on('plotly_relayout', function(ev){
      if(P.applying || P.suppress) return;
      P.user = viewStateUpdate(P.user, ev);
    });
    el.plot.on('plotly_doubleclick', function(){
      // plotly's own reset restores the ranges of the CURRENT frame,
      // which may be the stored user view; drop the stored view and
      // redraw so the lock (or auto) ranges reassert immediately
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
      el.msg.textContent = '';
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
      // truth drawn last so it sits on top; the tail beyond the now
      // marker stays visible so forecast accuracy is legible at a glance
      var p = pal();
      traces.push({x: pastX, y: pastY, mode: 'lines',
        name: 'truth (settled)', line: {color: p.ink, width: 2}});
      if(futX.length) traces.push({x: futX, y: futY, mode: 'lines',
        name: 'truth beyond now', opacity: .65,
        line: {color: p.ink, width: 1.3, dash: 'dot'}});
      // locked: explicit ranges on every redraw, so nothing jumps between
      // weeks. Unlocked: autoscale per frame. A stored user view beats
      // both until it is cleared
      var lock = (el.lock && el.lock.checked) ? lockRanges(pl, loc) : null;
      var xa = {gridcolor: p.line};
      var ya = {gridcolor: p.line, rangemode: 'tozero'};
      if(lock && lock.x){ xa.range = lock.x.slice(); xa.autorange = false; }
      if(lock && lock.y){ ya.range = lock.y.slice(); ya.autorange = false; }
      if(P.user.x){ xa.range = P.user.x.slice(); xa.autorange = false; }
      if(P.user.y){ ya.range = P.user.y.slice(); ya.autorange = false; }
      var L = {title: {text: loc + ' · forecasts as of ' + w,
                       font: {size: 14}},
        height: cfg.plotHeight || 400,
        margin: {l: 50, r: 20, t: 34, b: 40},
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        font: {color: p.ink},
        xaxis: xa,
        yaxis: ya,
        shapes: [{type: 'line', x0: w, x1: w, yref: 'paper', y0: 0, y1: 1,
                  line: {color: p.mut, width: 1.2, dash: 'dot'}}],
        annotations: [{x: w, yref: 'paper', y: 1, yanchor: 'bottom',
                  showarrow: false, text: 'now',
                  font: {size: 11, color: p.mut}}]};
      P.applying = true;
      var done = function(){ P.applying = false; bindPlot(); };
      var pr = Plotly.react(el.plot, traces, L, PCONF);
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
  function setPlay(on){
    P.playing = on;
    el.play.textContent = on ? '❚❚ Pause' : '▶ Play';
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
  el.scrub.addEventListener('input', function(){
    seek(+el.scrub.value, true);
  });
  // axis lock defaults ON and persists across visits; localStorage can be
  // unavailable (file: contexts, private windows), so every touch is
  // guarded. Toggling the lock clears any stored user view, so the lock
  // semantics are unchanged when no hand zoom is active
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

  // the static host passes the full-season catalog, so its controls exist
  // before the first frame; the live host builds from the first payload
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
  _internals: {
    OFFICIALS: OFFICIALS,
    UNAVAIL_NOTE: UNAVAIL_NOTE,
    WEEK_NOTE: WEEK_NOTE,
    availabilityTier: availabilityTier,
    weekCellState: weekCellState,
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
