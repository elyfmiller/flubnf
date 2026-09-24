/* FluCharts: the one tick policy and chart config for every date chart
 * (console pages, the Retrospective player, the weekly and season reports).
 *
 * Every FluSight point is an MMWR week-ending Saturday, but Plotly's
 * automatic weekly ticks land on Sundays, and setting tick0 alone makes it
 * fall back to daily ticks. So each date axis gets an explicit policy:
 *   - tick0 on the data's weekday (Saturday, 2000-01-01, for hub data; a
 *     custom dataset keyed on another weekday keeps its own weekday; data
 *     on mixed weekdays is left to Plotly),
 *   - dtick in whole weeks (1, 2, 4, 8, then 13, 26, 52 for long views)
 *     chosen from the visible span and the plot width so labels never crowd,
 *   - a date tickformat (with the year once the view spans many months).
 * The policy is recomputed after zoom, pan, resize and every redraw.
 * Served as charts.js beside the console pages and inlined verbatim into
 * the reports.
 */
(function(root){
  'use strict';
  var DAY = 864e5, WEEK = 7 * DAY;
  var SAT0 = '2000-01-01';                 // a Saturday
  var SAT0_MS = Date.UTC(2000, 0, 1);
  var STEPS = [1, 2, 4, 8, 13, 26, 52];
  var SHORT_FMT = '%b %-d', LONG_FMT = '%b %-d, %Y';
  // label footprint in px at the charts' ~13.6px tick font, gap included
  var SHORT_PX = 64, LONG_PX = 100;
  // a view longer than this (in weeks, beyond one season) carries the
  // year on each label
  var LONG_SPAN = 60;

  // the one shared chart config: showTips off (Plotly's "Double-click on
  // legend" hint sat over the expanded view's Close button)
  var BASE_CONF = {responsive: true, displaylogo: false, showTips: false};

  function conf(extra){
    var c = {}, k;
    for(k in BASE_CONF) c[k] = BASE_CONF[k];
    if(extra) for(k in extra) c[k] = extra[k];
    return c;
  }

  // 'YYYY-MM-DD' (optionally with a time, as Plotly writes ranges) -> UTC ms
  function parse(v){
    if(typeof v === 'number') return v;
    if(typeof v !== 'string') return NaN;
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2})(?::(\d{2})(?::(\d{2}(?:\.\d+)?))?)?)?/
      .exec(v);
    if(!m) return NaN;
    return Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0))
      + Math.round(parseFloat(m[6] || '0') * 1000);
  }

  function iso(ms){ return new Date(ms).toISOString().slice(0, 10); }

  // tick0 for data whose points all fall on one weekday (at midnight);
  // null when there are no dates or they mix weekdays
  function anchorFor(xs){
    var wd = null, seen = false;
    for(var i = 0; i < xs.length; i++){
      var v = xs[i];
      if(v === null || v === undefined || v === '') continue;
      if(typeof v !== 'string') return null;
      var ms = parse(v);
      if(!isFinite(ms)) return null;
      if(ms % DAY !== 0) return null;
      var d = new Date(ms).getUTCDay();
      if(wd === null) wd = d; else if(d !== wd) return null;
      seen = true;
    }
    if(!seen) return null;
    return iso(SAT0_MS + ((wd - 6 + 7) % 7) * DAY);
  }

  // the tick policy for a visible range [x0, x1] on a plot `width` px wide
  function weekTicks(x0, x1, width, anchor){
    var a = parse(x0), b = parse(x1);
    var span = (isFinite(a) && isFinite(b)) ? Math.abs(b - a) / WEEK : 16;
    var long = span > LONG_SPAN;
    var px = long ? LONG_PX : SHORT_PX;
    var plotW = Math.max(160, (width || 700) - 70);
    // n labels need n - 1 gaps of px each
    var maxTicks = Math.max(2, Math.floor(plotW / px) + 1);
    var step = null;
    for(var i = 0; i < STEPS.length; i++){
      if(Math.floor(span / STEPS[i]) + 1 <= maxTicks){ step = STEPS[i]; break; }
    }
    if(step === null) step = 52 * Math.ceil(span / 52 / (maxTicks - 1));
    return {tickmode: 'linear', tick0: anchor || SAT0, dtick: step * WEEK,
            tickformat: long ? LONG_FMT : SHORT_FMT};
  }

  // the date x values of a trace list (undefined when an axis is not dates)
  function traceXs(traces){
    var out = [];
    (traces || []).forEach(function(t){
      if(!t || (t.xaxis && t.xaxis !== 'x')) return;
      var x = t.x;
      if(!x || !x.length) return;
      for(var i = 0; i < x.length; i++) out.push(x[i]);
    });
    return out;
  }

  function extent(xs){
    var lo = Infinity, hi = -Infinity;
    xs.forEach(function(v){
      var ms = parse(v);
      if(isFinite(ms)){ if(ms < lo) lo = ms; if(ms > hi) hi = ms; }
    });
    return lo <= hi ? [iso(lo), iso(hi)] : null;
  }

  function elWidth(gd, layout){
    if(layout && layout.width) return layout.width;
    return (gd && gd.clientWidth) || 700;
  }

  // fill layout.xaxis with the week policy when the traces are dated;
  // explicit tickvals (month ticks on a weeks-since-August axis) are kept
  function applyLayout(layout, traces, width){
    layout = layout || {};
    var xa = layout.xaxis = layout.xaxis || {};
    if(xa.tickvals || (xa.type && xa.type !== 'date')) return layout;
    var xs = traceXs(traces), anchor = anchorFor(xs);
    if(!anchor) return layout;
    var r = (xa.range && isFinite(parse(xa.range[0])) &&
             isFinite(parse(xa.range[1]))) ? xa.range : extent(xs);
    if(!r) return layout;
    var p = weekTicks(r[0], r[1], width, anchor);
    xa.type = 'date';
    for(var k in p) xa[k] = p[k];
    return layout;
  }

  function el(gd){
    return typeof gd === 'string' ? document.getElementById(gd) : gd;
  }

  // recompute from what is on screen (after zoom, pan, resize, redraw)
  function refit(gd){
    var fl = gd && gd._fullLayout, lay = gd && gd.layout;
    if(!fl || !fl.xaxis || fl.xaxis.type !== 'date' || !lay) return;
    var xa = lay.xaxis || {};
    if(xa.tickvals) return;
    var anchor = anchorFor(traceXs(gd.data));
    if(!anchor) return;
    var p = weekTicks(fl.xaxis.range[0], fl.xaxis.range[1], fl.width, anchor);
    if(xa.tickmode === p.tickmode && xa.tick0 === p.tick0 &&
       xa.dtick === p.dtick && xa.tickformat === p.tickformat) return;
    if(gd._fluFitting) return;
    gd._fluFitting = true;
    var upd = {'xaxis.tickmode': p.tickmode, 'xaxis.tick0': p.tick0,
               'xaxis.dtick': p.dtick, 'xaxis.tickformat': p.tickformat};
    var done = function(){ gd._fluFitting = false; };
    var pr = root.Plotly.relayout(gd, upd);
    if(pr && pr.then) pr.then(done, done); else done();
  }

  function watch(gd){
    gd = el(gd);
    if(!gd || gd._fluWatch || !gd.on) return gd;
    gd._fluWatch = true;
    var again = function(){ setTimeout(function(){ refit(gd); }, 0); };
    gd.on('plotly_relayout', again);
    gd.on('plotly_afterplot', again);
    return gd;
  }

  function plot(fn, gd, traces, layout, config){
    gd = el(gd);
    layout = applyLayout(layout, traces, elWidth(gd, layout));
    var pr = root.Plotly[fn](gd, traces, layout, conf(config));
    watch(gd);
    return pr;
  }

  // drop-in for Plotly.react / Plotly.newPlot on a chart that may be dated
  function react(gd, traces, layout, config){
    return plot('react', gd, traces, layout, config);
  }
  function newPlot(gd, traces, layout, config){
    return plot('newPlot', gd, traces, layout, config);
  }

  // a chart drawn elsewhere (the reports' baked figures): fit and watch
  function adopt(gd){
    gd = el(gd);
    if(!gd) return;
    watch(gd);
    refit(gd);
  }
  function adoptAll(scope){
    var gs = (scope || document).querySelectorAll('.js-plotly-plot');
    for(var i = 0; i < gs.length; i++) adopt(gs[i]);
  }

  var API = {conf: conf, weekTicks: weekTicks, anchorFor: anchorFor,
             applyLayout: applyLayout, react: react, newPlot: newPlot,
             refit: refit, watch: watch, adopt: adopt, adoptAll: adoptAll,
             SATURDAY: SAT0, WEEK_MS: WEEK, STEPS: STEPS.slice()};
  root.FluCharts = API;
  if(typeof module !== 'undefined' && module.exports) module.exports = API;
})(typeof window !== 'undefined' ? window : this);
