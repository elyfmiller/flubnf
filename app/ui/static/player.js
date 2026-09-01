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
     us            optional {provenance, label, short_label, note,
                   fitted, fallback, fallback_note}: what the US national
                   series IS for this season, resolved host-side by
                   app/core/us_national. Its three provenance states are
                   "fitted" (the run fitted the national series as its own
                   location), "aggregated" (no fit; the figure is summed
                   from the state forecasts) and "officials_only" (neither;
                   the CDC comparators alone). The player never guesses
                   between them: omitted, it says officials only, which is
                   what a host that cannot answer actually knows
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

// ------------------------------------------------------ US national

// THE three provenance states of the US national series, and the fallback
// labels for each. The host resolves which one applies (app/core/
// us_national, the single resolution order) and passes cfg.us; these
// literals are the last resort for a host that passes nothing, and they
// deliberately claim the LEAST: officials only is what a player that was
// told nothing actually knows. A fitted national forecast and a
// sum-of-states aggregate are different model outputs, so the location
// entry, the chart title, and the empty-frame caption all name which.
var US_PROVENANCE = {FITTED: 'fitted', AGGREGATED: 'aggregated',
                     OFFICIALS: 'officials_only'};
var US_LABELS = /*US_LABELS_JSON*/{
  "fitted": "US national (fitted)",
  "aggregated": "US national (sum of states)",
  "officials_only": "US (official models only)"
}/*END_US_LABELS_JSON*/;

// which provenance a host config asserts; anything unrecognised, absent,
// or malformed reads as officials only
function usProvenance(us){
  var p = us && us.provenance;
  return (p === US_PROVENANCE.FITTED || p === US_PROVENANCE.AGGREGATED)
    ? p : US_PROVENANCE.OFFICIALS;
}

// the location entry's text: the host's own resolved label when it sent
// one (it can name the state count, "sum of 52 states"), else the literal
// for the provenance it asserted
function usLabel(us){
  if(us && us.label) return String(us.label);
  return US_LABELS[usProvenance(us)];
}

// whether a location string names the national row. One spelling test,
// mirroring app/core/us_national.is_us
function isUS(loc){
  var s = String(loc == null ? '' : loc).replace(/^\s+|\s+$/g, '')
            .toUpperCase();
  return s === 'US' || s === 'US (NATIONAL)' || s === 'UNITED STATES'
      || s === 'USA';
}

// how a location reads in a chart title, a legend, and a saved image's
// filename: a state by its own name, the national row by its provenance
// label, so a downloaded figure states which US series it holds
function locLabel(loc, us){
  return isUS(loc) ? usLabel(us) : String(loc);
}

// one location's entry in a payload map (truth, a model's fans). The
// selected US value is the plain code 'US'; a payload may key the same
// series under any national spelling, so the national row is matched by
// the spelling test rather than by string equality
function pickLoc(map, loc){
  if(!map) return null;
  if(map[loc] !== undefined) return map[loc];
  if(!isUS(loc)) return null;
  var ks = Object.keys(map);
  for(var i = 0; i < ks.length; i++)
    if(isUS(ks[i])) return map[ks[i]];
  return null;
}

// THE one model-name map: every surface that prints a model name reads
// this, so pf/analogue/ensemble never appear under different names on
// different surfaces. The player's legend, toggles, and stats table use it
// directly; the console templates and the season report builder read the
// SAME literal through Python (app/core/report_season.py, model_names),
// which parses the marked JSON below. Keep it a pure JSON object between
// the markers for that reason.
//
// The blend is "FluBNF Ensemble" on every human-facing surface. This entry
// used to carry the older team-prefixed name while the season tables were
// already headed "FluBNF Ensemble", so one published page printed two
// names for one model. The hub submission identity is a SEPARATE thing and
// does not change with this: forecasts still go out under the registered
// model_id built in app/core/submit.py, which is not a display name.
var MODEL_NAMES = /*MODEL_NAMES_JSON*/{
  "ensemble": "FluBNF Ensemble",
  "pf": "PF-SIHRS",
  "analogue": "Calendar analogue",
  "pf2s": "Two-strain SIHRS",
  "FluSight-ensemble": "FluSight ensemble (official)",
  "FluSight-baseline": "FluSight baseline (official)"
}/*END_MODEL_NAMES_JSON*/;

// THE one member-color map, same contract as MODEL_NAMES above: every
// surface that draws a member series reads this literal (the player
// directly, the console templates and both report builders through
// Python's model_colors parse), so a member wears one color everywhere.
// Spacing re-measured 2026-08-21 for dichromat separability (Vienot
// deuteranopia and protanopia): every pair that can share a chart now
// sits at 60+ simulated-distance under both matrices (the old slate/teal
// pair measured 27), and pf/pf2s hold 3:1 or better against all eight
// theme grounds. The gold and cyan identities are the anchors; on light
// grounds the console draws the ensemble through --gold (the readable
// accent-ink variant), which the audit also covers. Because the palette
// is dichromat-safe by construction, the CV-safe mode deliberately does
// NOT swap these member colors: only the semantic ok/bad pair and the
// outlook category scale change under data-vision="cvd", and a member
// line keeps its one identity in every mode. Keep it a pure JSON
// object between the markers.
var MODEL_COLORS = /*MODEL_COLORS_JSON*/{
  "ensemble": "#34C0F0",
  "pf": "#1979FF",
  "analogue": "#FFC72C",
  "pf2s": "#A66395"
}/*END_MODEL_COLORS_JSON*/;

// THE season-line palette's RED-GREEN-SAFE set (the season-over-season
// data charts), same marked-JSON contract as MODEL_COLORS above: the
// console reads it through Python (report_v2.season_colors). Since
// 2026-08-21 the season lines carry TWO palettes at the token layer in
// nau.css: --season-1..6 holds a normal-vision tab10-adjacent default,
// and data-vision="cvd" remaps it onto --season-cvd-1..6, whose literals
// are EXACTLY this list -- so the CV-safe toggle now visibly moves the
// season lines. Console charts resolve the tokens per draw
// (getComputedStyle) and fall back to this list where the tokens do not
// exist (the fixed-dark standalone report), which keeps the fallback the
// audited safe set. The six colors were spaced 2026-08-21 so every
// cyclically adjacent pair, and the FIRST color against both --gold
// variants (#34C0F0 on dark grounds, #0173A9 on light) that the newest
// season's line wears, measures 60+ apart under the Vienot deuteranopia
// and protanopia matrices AND in normal vision, and each color holds
// 3:1+ against all eight theme grounds. Seasons are colored newest-first
// (the newest non-gold season takes index 0, cycling when seasons
// outnumber colors), so the pair drawn beside the gold line is always
// the audited one. Any value change here or in the nau.css token blocks
// must re-clear the palette audit (app/tests/test_season_palette.py).
// Keep it a pure JSON array between the markers.
var SEASON_COLORS = /*SEASON_COLORS_JSON*/[
  "#A87300", "#3375FB", "#C9568C", "#0087AF", "#B96D36", "#8568E3"
]/*END_SEASON_COLORS_JSON*/;

// resolve one season-line color: the --season-N token where the host page
// carries the console stylesheet (normal palette by default, the cvd set
// under data-vision="cvd"), else the SEASON_COLORS literal. i counts
// newest-first from 0 and cycles.
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

// an official model that submitted somewhere in the season but not this
// week (the competition window: mid-September and June weeks legitimately
// lack files) keeps a live toggle with this transient annotation; there is
// simply nothing to draw for it this frame
var WEEK_NOTE = ' (no official submission this week)';

var DEFAULT_IDS = {prev: 'pb-prev', play: 'pb-play', next: 'pb-next',
  speed: 'pb-speed', scrub: 'pb-scrub', week: 'pb-week', loc: 'fd-loc',
  lock: 'fd-lock', models: 'fd-models', plot: 'fd-plot', msg: 'fd-msg',
  stats: 'pb-stats', status: 'pb-status', offhint: 'pb-offhint'};

// the report's fixed dark kit; the console overrides with its CSS
// variables. `card` is the surface the plot sits on: it is stated
// explicitly as the chart background (identical on screen to the old
// transparency) so the modebar's save-PNG export carries an opaque
// ground inside the file and stays readable on its own.
var DEFAULT_PALETTE = {ink: '#E9EAF4', mut: '#9AA1C4', line: '#262A45',
  card: '#151729',
  models: MODEL_COLORS,
  flusightEnsemble: '#C7CCDD'};

var PCONF = {responsive: true, displaylogo: false, scrollZoom: true,
             doubleClick: 'reset'};

// per-frame embed config: PCONF plus the save-PNG options (2x scale for a
// crisp figure, a meaningful filename naming the location and week)
function frameConf(loc, week){
  var c = {}, k;
  for(k in PCONF) c[k] = PCONF[k];
  c.toImageButtonOptions = {format: 'png', scale: 2,
    filename: ('flubnf_' + loc + '_' + week).replace(/[^\w-]+/g, '_')};
  return c;
}

// ---------------------------------------------------------- pure helpers

// chart text rides the host's type system: the root font size in px, so
// plotly sizes (which are px, never rem) track the console's A-/A/A+
// control. The static report has no such control; there this simply reads
// the report's own fixed root size once per redraw.
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

// display names come from the shared map above, keeping the two ensembles
// unmistakable in the legend, the model toggles, and the stats table
function nameOf(m){
  return MODEL_NAMES[m] || m;
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

// what the forecast-detail caption states when a frame draws no forecast
// fan for the selected location. `available` counts the models whose
// payload covers this location this week; `enabled` counts those of them
// the viewer has toggled on. Data present with everything toggled off is
// the viewer's own state and says so. A location no model covers this
// week is stated plainly instead of leaving a bare empty chart -- and for
// US the reason is structural: the fitted members are per-state, so the
// officials are the US view's only source, and a week they did not submit
// (outside the competition window) has nothing to draw.
function noForecastNote(loc, available, enabled, us){
  if(available > 0 && enabled > 0) return '';
  if(available > 0) return 'no models enabled';
  if(isUS(loc)){
    var p = usProvenance(us);
    if(p === US_PROVENANCE.FITTED)
      return 'no US national forecast stored for this week; the fitted '
        + 'national series covers the weeks the replay reached';
    if(p === US_PROVENANCE.AGGREGATED)
      return 'no US fan is drawn for this week: the scores for this season '
        + 'hold no scored US fit, and the fallback sum-of-states aggregate '
        + 'is a season score rather than a weekly forecast (choose a state '
        + 'above)';
    return 'no official US submission for this week; the fitted forecasts '
      + 'are per state (choose a state above)';
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
    // the US entry leads the list and SAYS WHAT IT IS: fitted at the
    // national level, the sum-of-states fallback, or the official models
    // alone. Any US spelling in the payload's own location list is folded
    // into that single entry so a fitted season cannot offer two US rows
    // whose difference is invisible.
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
      // a frame with nothing to draw for this location says WHY instead
      // of standing as bare axes (the US view outside the officials'
      // competition window, or every model toggled off)
      el.msg.textContent = noForecastNote(loc, avail, drawn, cfg.us);
      // truth drawn last so it sits on top; the tail beyond the now
      // marker stays visible so forecast accuracy is legible at a glance
      var p = pal();
      if(pastX.length) traces.push({x: pastX, y: pastY, mode: 'lines',
        name: 'truth (settled)', line: {color: p.ink, width: 2}});
      if(futX.length) traces.push({x: futX, y: futY, mode: 'lines',
        name: 'truth beyond now', opacity: .65,
        line: {color: p.ink, width: 1.3, dash: 'dot'}});
      // locked: explicit ranges on every redraw, so nothing jumps between
      // weeks. Unlocked: autoscale per frame. A stored user view beats
      // both until it is cleared
      // the chart title names the location the way the picker does, so a
      // US frame states its provenance on the figure itself and not only
      // in the dropdown the reader has already left behind
      var title = locLabel(loc, cfg.us);
      var lock = (el.lock && el.lock.checked) ? lockRanges(pl, loc) : null;
      // automargin: tick labels size the margins, so the tightened base
      // margins below leave no dead band and nothing clips at the A+
      // text step (locked ranges keep the ticks, and so the margins,
      // stable across playback frames)
      var xa = {gridcolor: p.line, automargin: true};
      var ya = {gridcolor: p.line, rangemode: 'tozero', automargin: true};
      if(lock && lock.x){ xa.range = lock.x.slice(); xa.autorange = false; }
      if(lock && lock.y){ ya.range = lock.y.slice(); ya.autorange = false; }
      if(P.user.x){ xa.range = P.user.x.slice(); xa.autorange = false; }
      if(P.user.y){ ya.range = P.user.y.slice(); ya.autorange = false; }
      var fs = rootFont();
      var surf = p.card || '#151729';
      // chart text on the app's type scale, in root-proportional px so the
      // A-/A/A+ control multiplies it: ticks and legend at .85rem (above
      // the .82rem hint floor), the title one step up, the now marker at
      // the hint floor itself. Base margins are tight (automargin above
      // owns the tick sides); the top band is proportional so the title
      // and the now label never collide or clip at A+.
      var L = {title: {text: title + ' · forecasts as of ' + w,
                       font: {size: Math.round(fs * .95)}},
        height: cfg.plotHeight || 400,
        margin: {l: 8, r: 8, t: Math.round(fs * 2.4), b: 8},
        paper_bgcolor: surf, plot_bgcolor: surf,
        font: {color: p.ink, family: '"DM Sans",system-ui,sans-serif',
               size: Math.round(fs * .85)},
        // horizontal legend under the plot (it pushes the bottom margin
        // out for itself): a right-hand legend of long model names was
        // eating a third of the panel width as a dead band
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
      // the saved PNG is named from the SAME label, so a downloaded US
      // figure carries its provenance in the filename rather than being
      // an anonymous "flubnf_US_2098-12-05" that could be either kind
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
  // the accessible name must track the state: a static "Play or pause"
  // label would misreport the control on every other press (WCAG 4.1.2)
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
  // the console's A-/A/A+ control dispatches this after moving the root
  // font size; the redraw picks the new size up through rootFont(). The
  // static report host has no fontsize control, so the event never fires
  // there and this listener is a graceful no-op.
  addEventListener('fontsizechange', function(){
    if(detailVisible()) drawFC();
  });

  labelPlay(false);      // the initial, paused state names itself correctly

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
