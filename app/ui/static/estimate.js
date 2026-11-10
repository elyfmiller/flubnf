/* FluBNF run-time estimate (flubnf-estimate-v1)

   The browser's copy of app/core/estimates.py: how long a run takes, from
   the engine's cost model, recomputed on every change to a run form
   without a request. Every rule and every floating-point step is the
   Python's, in the same order; app/tests/test_estimates.py holds the two
   equal.

   A form carries estimates.page_params() as data-est-* attributes, and
   FluBNFEstimate.params(form) reads them (null when they are missing):

     var E = FluBNFEstimate, p = E.params(form);
     var n = E.nObsFor(anchor, seasonStart);        // null: no usable date
     var s = E.seconds([n], fits, particles, null, p);   // null: p.width
     var sp = E.span(s, ratio, p.first);            // ratio null: none yet
     line.textContent = E.human(sp[0], sp[1]);      // "" : show nothing

   fits is locations x Independent Runs a week, priced at the width but
   never above p.mostWidth (data-est-most-width: this computer's default
   width, estimates.priced_width). The 1x end of a span is
   the cost model alone (no prepare, Oracle step or Groundhog), so a page
   shows the span, never its low end alone. Zero fits (the Groundhog
   alone) read "", never "under a minute".

   ES5 (docs/UI-KIT.md), nothing touched at load, no network.
*/
(function (root) {
  "use strict";

  // the human text's switch to hours (retro_progress.js etaText's rule),
  // and the high end below which it reads "under a minute"
  var HOURS_FROM_S = 5400, MINUTE_S = 60;
  // estimates.TOO_MANY_HOURS: from this many hours human() says nothing
  // (toFixed would write "1e+21")
  var TOO_MANY_HOURS = 1e21;

  // Python's int(): toward zero
  function toInt(x) {
    x = +x;
    if (!isFinite(x)) return 0;
    return x < 0 ? Math.ceil(x) : Math.floor(x);
  }

  // the data-est-* attributes estimates.page_params() writes
  function params(el) {
    if (!el || typeof el.getAttribute !== "function") return null;
    function get(name) { return el.getAttribute("data-est-" + name); }
    var names = ["intercept", "per-week", "forecast-weeks",
                 "reference-particles", "public-ratio", "first-span",
                 "engine", "width", "most-width"];
    for (var i = 0; i < names.length; i++) {
      if (get(names[i]) === null || get(names[i]) === undefined) return null;
    }
    var first = String(get("first-span")).split(" ");
    var p = {
      intercept: parseFloat(get("intercept")),
      perWeek: parseFloat(get("per-week")),
      forecastWeeks: parseInt(get("forecast-weeks"), 10),
      refParticles: parseInt(get("reference-particles"), 10),
      publicRatio: parseFloat(get("public-ratio")),
      first: [parseFloat(first[0]), parseFloat(first[1])],
      engine: get("engine") === "public" ? "public" : "private",
      width: Math.max(1, parseInt(get("width"), 10) || 1),
      mostWidth: Math.max(1, parseInt(get("most-width"), 10) || 1)
    };
    var nums = [p.intercept, p.perWeek, p.forecastWeeks, p.refParticles,
                p.publicRatio, p.first[0], p.first[1]];
    for (var j = 0; j < nums.length; j++) {
      if (!isFinite(nums[j])) return null;
    }
    return p;
  }

  // pf.cell_seconds for one fit: (intercept + per week x (n_obs +
  // forecast weeks)) x particles / reference, times the public ratio on
  // the public engine. `engine` null: p.engine.
  function fitSeconds(nObs, particles, p, engine) {
    var n = toInt(nObs || 0);
    var parts = toInt(particles || 0) || p.refParticles;
    var s = ((p.intercept + p.perWeek * (n + p.forecastWeeks))
             * Math.max(parts, 1) / p.refParticles);
    var eng = engine === null || engine === undefined ? p.engine : engine;
    return eng === "public" ? s * p.publicRatio : s;
  }

  // estimates.run_seconds: over the weeks (each its own n_obs),
  // ceil(fits / w) waves of fitSeconds, added one by one. w is `width`
  // (null: p.width, the page's), never above p.mostWidth
  // (estimates.priced_width).
  function seconds(weeksNObs, fits, particles, width, p, engine) {
    var w = width === null || width === undefined ? p.width
                                                  : Math.max(1, toInt(width));
    w = Math.min(w, p.mostWidth);
    var waves = Math.ceil(Math.max(0, toInt(fits || 0)) / w);
    var total = 0;
    for (var i = 0; i < (weeksNObs || []).length; i++) {
      total += waves * fitSeconds(weeksNObs[i], particles, p, engine);
    }
    return total;
  }

  // a YYYY-MM-DD day as UTC milliseconds, or null (a malformed or
  // impossible date)
  function parseDay(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s === null || s === undefined ? "" : s));
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    var t = Date.UTC(y, mo - 1, d), back = new Date(t);
    if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 ||
        back.getUTCDate() !== d) return null;
    return t;
  }

  // runs.default_season_start: August 1 of the anchor's season
  function defaultSeasonStart(anchor) {
    var a = String(anchor || "");
    if (!a) return "";
    var y = parseInt(a.slice(0, 4), 10), m = parseInt(a.slice(5, 7), 10);
    return (m >= 8 ? y : y - 1) + "-08-01";
  }

  // estimates.n_obs_for: (anchor - start) days // 7 + 1, never below 0;
  // a blank start is the anchor's season's. An upper bound (prepare drops
  // unreported weeks and weeks_to_drop). null for a blank or malformed
  // date, where the Python raises.
  function nObsFor(anchor, seasonStart) {
    var a = String(anchor || "").slice(0, 10);
    var ta = parseDay(a);
    if (ta === null) return null;
    var s = String(seasonStart || "").slice(0, 10) || defaultSeasonStart(a);
    var ts = parseDay(s);
    if (ts === null) return null;
    var days = (ta - ts) / 86400000;
    return Math.max(0, Math.floor(days / 7) + 1);
  }

  // Python's round(x, 1): the exact value rounded, a tie to even. A tie at
  // one decimal is exactly k/4 with k odd; anything else toFixed rounds
  // as Python does.
  function roundTenth(x) {
    var q = x * 4;
    if (isFinite(q) && Math.floor(q) === q && Math.abs(q % 2) === 1) {
      var t = Math.floor(x * 10);
      return (t % 2 === 0 ? t : t + 1) / 10;
    }
    return Number(x.toFixed(1));
  }

  // estimates.span: (low, high) seconds, rounded to 0.1. With this
  // computer's ratio, the model times it at both ends; without one,
  // `first` ([low, high] multiples: page_params' first span, or the
  // params object itself) times the model.
  function span(sec, ratio, first) {
    var f = ratio ? [ratio, ratio]
                  : (first && first.first ? first.first : first);
    return [roundTenth(sec * f[0]), roundTenth(sec * f[1])];
  }

  // estimates.human: etaText's rule after "about" (the unit is the high
  // end's; hours with one decimal from 90 min up; minutes never below 1);
  // "under a minute" below 60 s at the high end; "" for no estimate (and
  // for TOO_MANY_HOURS or more)
  function human(lo, hi) {
    if (typeof lo !== "number" || typeof hi !== "number") return "";
    if (!isFinite(lo) || !isFinite(hi) || !(hi > 0)) return "";
    if (hi / 3600 >= TOO_MANY_HOURS) return "";
    if (hi < MINUTE_S) return "under a minute";
    var hours = hi >= HOURS_FROM_S;
    function fmt(s) {
      return hours ? (s / 3600).toFixed(1) + " h"
                   : Math.max(1, Math.round(s / 60)) + " min";
    }
    var a = fmt(Math.max(0, lo)), b = fmt(Math.max(0, hi));
    if (a === b) return "about " + a;
    return "about " + a.replace(/ (h|min)$/, "") + " to " + b;
  }

  var FluBNFEstimate = {
    params: params,
    fitSeconds: fitSeconds,
    seconds: seconds,
    nObsFor: nObsFor,
    defaultSeasonStart: defaultSeasonStart,
    roundTenth: roundTenth,
    span: span,
    human: human,
    HOURS_FROM_S: HOURS_FROM_S,
    MINUTE_S: MINUTE_S
  };
  root.FluBNFEstimate = FluBNFEstimate;
  if (typeof module !== "undefined" && module.exports)
    module.exports = FluBNFEstimate;
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
