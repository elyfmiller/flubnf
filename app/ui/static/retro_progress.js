// Live retrospective ticker (retro index + season page). Drives every
// progress element on .season-card[data-active="1"]: the .rfill bar, the
// .rstat readout, every .rcount counter (one source, so no line disagrees),
// the .rbasis text (what the estimate rests on: the readout's "?" on the
// Retrospective tab, a visually hidden line on the season page), the
// .rt-stall badge (shown while the connection is lost) and the .rquip
// line. A script poll, never a meta refresh; no reload while the
// caller's busy() is true (the guard modal).
// Rules: the percentage never regresses; the ETA is the server's RANGE,
// shown as sent and decayed by the wall clock (no client smoothing: it once
// pinned the display for hours); an unestimable ETA says so rather than
// leaving a stale number; after 3 failed polls the clocks freeze and the
// basis says the connection is lost (the next success clears it); paused
// freezes the readouts, withdraws the ETA and stops the quips. Inside a
// long Oracle week the readout names the week and its fits ("week
// 2026-03-21 · 96 of 159 fits") and the bar moves by them.
//
// Also here, FluBNFRetroCost: the Retrospective Settings form's Oracle
// option says what the replay costs on this computer, from the engine's
// cost model (static/estimate.js, FluBNFEstimate) over the picked season's
// weeks, redone on every change of the form. retro_seasons._cost_words is
// the same rule on the server, for the page as first shown.
(function (root) {
  "use strict";

  function hms(t) {
    t = Math.max(0, Math.round(t));
    return Math.floor(t / 3600) + ":" +
      String(Math.floor(t / 60) % 60).padStart(2, "0") + ":" +
      String(t % 60).padStart(2, "0");
  }

  // "3.1 to 4.0 h" / "12 to 16 min" / "~3.3 h" when both ends agree; the
  // unit follows the high end, hours get one decimal
  function etaText(loS, hiS) {
    var hours = hiS >= 5400;
    function fmt(s) {
      return hours ? (s / 3600).toFixed(1) + " h"
                   : Math.max(1, Math.round(s / 60)) + " min";
    }
    var a = fmt(Math.max(0, loS)), b = fmt(Math.max(0, hiS));
    if (a === b) return "~" + a;
    return a.replace(/ (h|min)$/, "") + " to " + b;
  }

  // one card's readout from the last poll `d`: the bar's percentage (the
  // weeks stored plus the share of the week in flight's fits, never below
  // `prev`), the week count and the line. `now` is the paint's clock;
  // `eta` holds the server's range ({lo, hi, etaAt}, lo null: none)
  function readout(d, prev, now, eta) {
    var paused = (d.status === "paused");
    var wt = +d.week_fits_total || 0;
    var frac = wt > 0 ? Math.min(1, Math.max(0, (+d.week_fits_done || 0) / wt))
                      : 0;
    var pct = d.total ? 100 * Math.min(d.total, d.done + frac) / d.total : 0;
    pct = Math.max(prev, Math.min(100, pct));
    var elapsed = d.elapsed_s;
    if (elapsed != null && (d.status === "running" || d.status === "stopping"))
      elapsed += (now - d.at) / 1000;    // held while paused or stalled
    var count = d.done + "/" + d.total + " weeks";
    var line = Math.round(pct) + "% · " + count;
    // the as-of date never splits at its hyphens on a phone: a word joiner
    // (U+2060, invisible) after each keeps the hyphen the font's own
    if (d.week_asof && wt > 0)
      line += " · week " + String(d.week_asof).replace(/-/g, "-\u2060") +
              " · " + (+d.week_fits_done || 0) + " of " + wt + " fits";
    if (elapsed != null) line += " · " + hms(elapsed) + " elapsed";
    if (!paused && eta.lo != null && eta.hi != null) {
      var dt = (now - eta.etaAt) / 1000;
      line += " · " + etaText(eta.lo - dt, eta.hi - dt) + " left";
    }
    if (paused) line += " · paused";
    return {pct: pct, count: count, line: line};
  }

  function init(opts) {
    opts = opts || {};
    var busy = opts.busy || function () { return false; };
    var pollMs = opts.pollMs || 3000;
    var cards = Array.prototype.slice.call(
      document.querySelectorAll('.season-card[data-active="1"]'));
    if (!cards.length) return null;
    var S = {};
    cards.forEach(function (c) {
      S[c.dataset.season] = {
        card: c, disp: 0, lo: null, hi: null, etaAt: 0,
        quips: root.flubnfQuips ? root.flubnfQuips(c.querySelector(".rquip"), undefined,
                                     root.FLUBNF_RETRO_QUIPS)
                                : {pause: function () {}, resume: function () {}},
        d: {status: c.dataset.status, done: +c.dataset.done,
            total: +c.dataset.total, elapsed_s: null,
            eta_lo_s: null, eta_hi_s: null, eta_basis: null,
            weeks_measured: 0, at: Date.now()}
      };
    });

    // polling: hidden tab -> slow heartbeat; never stack requests; poll at
    // once on return to the tab
    var hiddenMs = opts.pollHiddenMs || 20000;
    var inflight = false, timer = null;
    // consecutive failed polls, and when the freeze began (paint() reads
    // time through it)
    var fails = 0, stalled = false, stallAt = 0;
    function schedule(ms) {
      clearTimeout(timer);
      timer = setTimeout(poll, ms);
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) schedule(0);
    });

    function poll() {
      if (inflight) { schedule(pollMs); return; }
      if (document.hidden) { schedule(hiddenMs); return; }
      inflight = true;
      fetch("/api/retro/progress")
        .then(function (r) { return r.json(); })
        .then(function (all) {
          fails = 0; stalled = false;    // any success clears the freeze
          var names = Object.keys(S);
          for (var i = 0; i < names.length; i++) {
            var n = names[i], st = S[n], p = all[n];
            if (!p) continue;
            // a status change or the first stored week (results link)
            // changes the server-rendered card: reload, not repaint
            if ((p.status !== st.card.dataset.status ||
                 (p.done > 0 && st.card.dataset.results !== "1")) && !busy()) {
              location.reload();
              return;
            }
            // take the server's range as sent; absent (paused or not yet
            // estimable) withdraws it
            if (p.eta_lo_s != null && p.eta_hi_s != null) {
              st.lo = p.eta_lo_s; st.hi = p.eta_hi_s; st.etaAt = Date.now();
            } else {
              st.lo = st.hi = null;
            }
            p.at = Date.now();
            st.d = p;
          }
        })
        .catch(function () {
          // ~9 s of silence at the 3 s cadence: freeze
          if (++fails >= 3 && !stalled) { stalled = true; stallAt = Date.now(); }
        })
        .then(function () {
          inflight = false;
          schedule(document.hidden ? hiddenMs : pollMs);
        });
    }

    function paint() {
      if (document.hidden) return;          // nothing to see: do no work
      // while stalled, time stands at the moment the freeze began
      var now = stalled ? stallAt : Date.now();
      Object.keys(S).forEach(function (n) {
        var st = S[n], d = st.d, c = st.card;
        var paused = (d.status === "paused");
        // quips hold while stalled too
        if (paused || stalled) st.quips.pause(); else st.quips.resume();
        var r = readout(d, st.disp, now, st);
        st.disp = r.pct;                                  // never regress
        var fill = c.querySelector(".rfill");
        if (fill) fill.style.width = Math.max(r.pct, 2) + "%";
        var stat = c.querySelector(".rstat");
        if (stat) stat.textContent = r.line;
        // every secondary week counter follows the headline
        Array.prototype.forEach.call(c.querySelectorAll(".rcount"),
          function (el) { el.textContent = r.count; });
        // a lost connection shows as a badge (the basis below says it too)
        var stall = c.querySelector(".rt-stall");
        if (stall) stall.hidden = !stalled;
        var basis = c.querySelector(".rbasis");
        if (basis) basis.textContent = stalled
          ? "Connection lost. Numbers paused."
          : paused
          ? "Paused; the fits in flight finished first. The clock is held and resumes with the replay."
          : (d.eta_basis
             || (d.weeks_measured
                 ? "estimate from " + d.weeks_measured + " completed week" +
                   (d.weeks_measured === 1 ? "" : "s")
                 : "estimate arrives once the first week completes"));
      });
    }

    setInterval(paint, 400);
    paint();
    poll();
    return {paint: paint};
  }

  root.FluBNFRetroTicker = {init: init,
                            _internals: {etaText: etaText, readout: readout}};

  // ---- FluBNFRetroCost: the Settings form's cost line ----

  // a field as the cost line reads it: digits are their number, anything
  // else (blank included) is `dflt` (routes/retro._whole)
  function whole(v, dflt) {
    var t = String(v === null || v === undefined ? "" : v)
      .replace(/^\s+|\s+$/g, "");
    return /^[0-9]+$/.test(t) ? parseInt(t, 10) : dflt;
  }

  // Python's str.strip() and int()'s own: what str.isspace() calls space
  var PY_SPACE = "[\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680" +
                 "\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
  var PY_STRIP = new RegExp("^" + PY_SPACE + "+|" + PY_SPACE + "+$", "g");
  // the most digits Python's int() reads from text (sys.int_info's
  // default_max_str_digits); more is refused, leading zeros included
  var PY_INT_DIGITS = 4300;

  // a model setting's whole number (Particles, Independent Runs) as the
  // server's check reads it (app/core/knobs.py _coerce): blank is the
  // field's data-default; else commas and underscores dropped, then an
  // optional sign and digits, within the field's min and max. null for
  // anything the server refuses ("1e4", "2.5", "0", 309 digits), so the
  // option gets no figure for a run that will not start (review 3 of
  // #93, re-check R5)
  function knobWhole(f) {
    var t = String(f.value === null || f.value === undefined ? "" : f.value)
      .replace(PY_STRIP, "");
    if (t === "") return whole(f.getAttribute("data-default"), null);
    t = t.replace(/[,_]/g, "").replace(PY_STRIP, "");
    var m = /^[+-]?([0-9]+)$/.exec(t);
    if (!m || m[1].length > PY_INT_DIGITS) return null;
    var v = parseInt(t, 10);
    var lo = parseFloat(f.getAttribute("min")),
        hi = parseFloat(f.getAttribute("max"));
    if (!isFinite(v) || (isFinite(lo) && v < lo) || (isFinite(hi) && v > hi))
      return null;
    return v;
  }

  // what a number box holds, and so posts: its text when that is a valid
  // floating-point number (HTML), else blank. A browser's box never holds
  // "abc" or "1,000"; it does hold "2e0", "2.0" and "-3"
  var HTML_FLOAT = /^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
  function boxValue(f) {
    var t = String(f.value === null || f.value === undefined ? "" : f.value);
    var number =
      String(f.getAttribute("type") || "").toLowerCase() === "number";
    return number && !HTML_FLOAT.test(t) ? "" : t;
  }

  // Python's int() of text: its own spaces (str.isspace() but U+001C to
  // U+001F), a sign, digits with single underscores between them
  var PY_INT_SPACE = "[\\t\\n\\x0b\\x0c\\r \\x85\\xa0\\u1680" +
                     "\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
  var PY_INT = new RegExp("^" + PY_INT_SPACE + "*([+-]?)([0-9]+(?:_[0-9]+)*)" +
                          PY_INT_SPACE + "*$");

  // the runners box as the run's POST reads what the box posts
  // (routes/retro.py retro_run): stripped, commas dropped, blank is
  // `dflt`, else Python's int() (the caller holds it to 1 and the box's
  // max, as the POST holds it to 1 to 16). null for what the POST refuses
  // ("2e0", "2.0", "1e1": not a whole number), so the option gets no
  // figure for a run that will not start (review of #93, re-check at
  // 099907c, finding 2)
  function runners(f, dflt) {
    var t = boxValue(f).replace(PY_STRIP, "").replace(/,/g, "");
    if (t === "") return dflt;
    var m = PY_INT.exec(t);
    if (!m) return null;
    var digits = m[2].replace(/_/g, "");
    if (digits.length > PY_INT_DIGITS) return null;
    return parseInt(m[1] + digits, 10);       // past a double: +-Infinity
  }

  // the cost words for one state of the form (o: what read() returns):
  // FluBNFEstimate.human of the span over o.weeks at o.fits a week
  // (locations x Independent Runs), o.particles and o.width; " here" when
  // it rests on this computer's recorded o.ratio; ", N weeks left" when
  // only the o.left weeks a resume runs are priced; "" for no figure
  function words(o) {
    var E = root.FluBNFEstimate;
    if (!E || !o || !o.p || !o.weeks || !o.weeks.length || !(o.fits > 0) ||
        o.particles === null || o.width === null) return "";
    var ns = [];
    for (var i = 0; i < o.weeks.length; i++) {
      var n = E.nObsFor(o.weeks[i], o.start);
      if (n === null) return "";
      ns.push(n);
    }
    var sp = E.span(E.seconds(ns, o.fits, o.particles, o.width, o.p),
                    o.ratio, o.p.first);
    var w = E.human(sp[0], sp[1]);
    if (!w) return "";
    if (o.ratio) w += " here";
    if (o.left) w += ", " + o.left + " week" + (o.left === 1 ? "" : "s") +
                     " left";
    return w;
  }

  // the form as words() reads it: the season's weeks (data-rt-costs),
  // the locations (the scope: the panel's count, every state box, or the
  // boxes ticked; US national adds one), Independent Runs, particles
  // (each blank at its data-default, null for what the server refuses:
  // knobWhole), the width box (runners: blank is the page's, null for
  // what the run refuses; at least 1 and never above its max) and this
  // computer's ratio (data-rt-ratio). null without the estimate's
  // attributes.
  function read(form) {
    var E = root.FluBNFEstimate;
    var p = E && form ? E.params(form) : null;
    if (!p) return null;
    var costs;
    try { costs = JSON.parse(form.getAttribute("data-rt-costs") || "{}"); }
    catch (e) { return null; }
    var ratio = parseFloat(form.getAttribute("data-rt-ratio"));
    if (!(ratio > 0)) ratio = null;
    function field(name) { return form.elements.namedItem(name); }
    function knob(name) {
      var f = field(name);
      return f ? knobWhole(f) : null;
    }
    var season = field("season"), scope = field("locations"),
        national = field("national"), wbox = field("width");
    var c = (season && costs[season.value]) || null;
    var boxes = form.querySelectorAll('input[name="custom_locations"]');
    var sv = scope ? scope.value : "panel6", n = 0, i;
    if (sv === "all") n = boxes.length;
    else if (sv === "custom") {
      for (i = 0; i < boxes.length; i++) if (boxes[i].checked) n++;
    } else {
      var po = scope ? scope.querySelector('option[value="panel6"]') : null;
      n = po ? whole(po.getAttribute("data-n"), 0) : 0;
    }
    if (n > 0 && national && national.value !== "0") n += 1;
    var reps = knob("replicates");
    var wmax = wbox ? whole(wbox.getAttribute("max"), null) : null;
    var w = wbox ? runners(wbox, p.width) : p.width;
    if (w !== null && wmax) w = Math.min(w, wmax);
    return {p: p, start: c ? c.start : "",
            weeks: c ? (c.left || c.weeks || []) : [],
            left: c && c.left ? c.left.length : 0,
            fits: reps === null ? 0 : n * reps,
            particles: knob("particles"),
            width: w === null ? null : Math.max(1, w),
            ratio: ratio};
  }

  // keep the Oracle option's words current: on every change or input in
  // the form, the Model settings panel's reset (ms-reset), and a page
  // brought back from the history
  function bind(form) {
    if (!form || !root.FluBNFEstimate || !form.elements) return null;
    var sel = form.elements.namedItem("engine");
    var opt = sel ? sel.querySelector('option[value="pf"]') : null;
    if (!opt) return null;
    var base = opt.getAttribute("data-base") || opt.textContent;
    function sync() {
      var w = words(read(form));
      opt.textContent = base + (w ? " (" + w + ")" : "");
    }
    form.addEventListener("change", sync);
    form.addEventListener("input", sync);
    form.addEventListener("ms-reset", sync);
    if (root.addEventListener) root.addEventListener("pageshow", sync);
    sync();
    return {sync: sync};
  }

  root.FluBNFRetroCost = {words: words, read: read, bind: bind,
                          whole: whole};
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
