// Live retrospective ticker, shared by the retro index and the season page.
//
// It drives every element on `.season-card[data-active="1"]` that states
// progress: the solid fill on its .runbar track, the prominent .rstat
// readout, every secondary .rcount week counter (so no line on the card can
// disagree with the headline), the .rbasis hint that says what the estimate
// rests on, and the rotating .rquip line.
//
// A script poll, never a meta refresh and never a blanket reload: the caller
// supplies a busy() predicate (the console's guard modal), and while it is
// true no reload happens, so a pending stop-and-proceed is never wiped
// mid-wait.
//
// Honesty rules, inherited from the console's run progress and paid for in
// the field:
//   * the displayed percentage is monotone non-decreasing;
//   * the remaining time is a RANGE, not a point: the server recomputes it
//     on every poll from measured per-week seconds (recency-weighted, and
//     shaped by a completed season's week profile when one exists), and
//     between polls the shown range ticks down with the wall clock, so the
//     number always moves while work is happening;
//   * when the estimate cannot be computed yet the basis line says so
//     plainly; a stale number is never left standing in its place.
// The previous ticker smoothed the server's point estimate with an EMA and
// resisted upward corrections; against a server value that barely moved
// (the global-mean estimate cancelled its own inputs), that pinned the
// display to one number for hours. Nothing here smooths any more: the
// server's range is shown as sent and decays in real time.
//
// A paused season is visually distinct: the bar holds, the readouts freeze
// (the server holds elapsed_s while paused), the estimate is withdrawn, and
// the quips stop rotating. A moving line beside a frozen bar would read as
// progress that is not happening.
(function (root) {
  "use strict";

  function hms(t) {
    t = Math.max(0, Math.round(t));
    return Math.floor(t / 3600) + ":" +
      String(Math.floor(t / 60) % 60).padStart(2, "0") + ":" +
      String(t % 60).padStart(2, "0");
  }

  // "3.1 to 4.0 h" / "12 to 16 min" / "~3.3 h" when both ends agree. The
  // unit follows the high end, so a range never mixes units, and hours get
  // one decimal: honest movement stays visible without false precision.
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
        quips: root.flubnfQuips ? root.flubnfQuips(c.querySelector(".rquip"))
                                : {pause: function () {}, resume: function () {}},
        d: {status: c.dataset.status, done: +c.dataset.done,
            total: +c.dataset.total, elapsed_s: null,
            eta_lo_s: null, eta_hi_s: null, eta_basis: null,
            weeks_measured: 0, at: Date.now()}
      };
    });

    // Polling discipline, which matters most exactly when the server is
    // slowest (a replay has the cores): a HIDDEN tab drops to a slow
    // heartbeat rather than asking every three seconds for readouts nobody
    // can see, and a request still in flight suppresses the next tick
    // instead of stacking a second one behind a slow reply. Returning to
    // the tab polls at once, so the bar is current when it is looked at.
    var hiddenMs = opts.pollHiddenMs || 20000;
    var inflight = false, timer = null;
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
          var names = Object.keys(S);
          for (var i = 0; i < names.length; i++) {
            var n = names[i], st = S[n], p = all[n];
            if (!p) continue;
            // the controls and the card's shape are the server's to render:
            // a status change (or the first stored week, which earns the
            // results link) needs a reload rather than a repaint
            if ((p.status !== st.card.dataset.status ||
                 (p.done > 0 && st.card.dataset.results !== "1")) && !busy()) {
              location.reload();
              return;
            }
            // the server recomputed the whole range this poll: take it as
            // sent, both directions, and let paint() decay it until the
            // next poll lands. Absent means paused or not yet estimable,
            // and the display withdraws rather than holding a stale value.
            if (p.eta_lo_s != null && p.eta_hi_s != null) {
              st.lo = p.eta_lo_s; st.hi = p.eta_hi_s; st.etaAt = Date.now();
            } else {
              st.lo = st.hi = null;
            }
            p.at = Date.now();
            st.d = p;
          }
        })
        .catch(function () {})
        .then(function () {
          inflight = false;
          schedule(document.hidden ? hiddenMs : pollMs);
        });
    }

    function paint() {
      if (document.hidden) return;          // nothing to see: do no work
      Object.keys(S).forEach(function (n) {
        var st = S[n], d = st.d, c = st.card;
        var paused = (d.status === "paused");
        if (paused) st.quips.pause(); else st.quips.resume();
        var pct = d.total ? 100 * d.done / d.total : 0;
        pct = Math.max(st.disp, Math.min(100, pct));
        st.disp = pct;                                    // never regress
        var fill = c.querySelector(".rfill");
        if (fill) fill.style.width = Math.max(pct, 2) + "%";
        var elapsed = d.elapsed_s;
        if (elapsed != null && (d.status === "running" || d.status === "stopping"))
          elapsed += (Date.now() - d.at) / 1000;          // held while paused
        var count = d.done + "/" + d.total + " weeks";
        var line = Math.round(pct) + "% · " + count;
        if (elapsed != null) line += " · " + hms(elapsed) + " elapsed";
        if (!paused && st.lo != null && st.hi != null) {
          var dt = (Date.now() - st.etaAt) / 1000;
          line += " · " + etaText(st.lo - dt, st.hi - dt) + " left";
        }
        if (paused) line += " · paused";
        var stat = c.querySelector(".rstat");
        if (stat) stat.textContent = line;
        // every secondary week counter on the card follows the headline:
        // one source of truth, so no line can go stale beside a live one
        Array.prototype.forEach.call(c.querySelectorAll(".rcount"),
          function (el) { el.textContent = count; });
        var basis = c.querySelector(".rbasis");
        if (basis) basis.textContent = paused
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

  root.FluBNFRetroTicker = {init: init, hms: hms,
                            _internals: {etaText: etaText}};
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
