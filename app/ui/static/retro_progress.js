// Live retrospective ticker, shared by the retro index and the season page.
//
// It drives every element marked `.season-card[data-active="1"]`: the solid
// fill on its .runbar track, the prominent .rstat readout, the .rbasis hint
// that says what the estimate rests on, and the rotating .rquip line.
//
// A script poll, never a meta refresh and never a blanket reload: the caller
// supplies a busy() predicate (the console's guard modal), and while it is
// true no reload happens, so a pending stop-and-proceed is never wiped
// mid-wait.
//
// Honesty rules, inherited from the console's run progress and paid for in
// the field:
//   * the displayed percentage is monotone non-decreasing;
//   * the ETA is EMA-smoothed (alpha .3) so it ticks down steadily instead
//     of oscillating, and a genuine upward correction is accepted only after
//     three consecutive polls above the displayed value.
// The ETA itself is steadier than the console's, because it rests on
// MEASURED seconds per completed week rather than a fit-level rate.
//
// A paused season is visually distinct: the bar holds, the readouts freeze
// (the server holds elapsed_s while paused), the ETA is withdrawn, and the
// quips stop rotating. A moving line beside a frozen bar would read as
// progress that is not happening.
window.FluBNFRetroTicker = (function () {
  "use strict";

  function hms(t) {
    t = Math.max(0, Math.round(t));
    return Math.floor(t / 3600) + ":" +
      String(Math.floor(t / 60) % 60).padStart(2, "0") + ":" +
      String(t % 60).padStart(2, "0");
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
        card: c, disp: 0, ema: null, shown: null, shownT: 0, up: 0,
        quips: window.flubnfQuips ? window.flubnfQuips(c.querySelector(".rquip"))
                                  : {pause: function () {}, resume: function () {}},
        d: {status: c.dataset.status, done: +c.dataset.done,
            total: +c.dataset.total, elapsed_s: null, eta_s: null,
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
            if (p.eta_s != null) {
              st.ema = st.ema == null ? p.eta_s : 0.3 * p.eta_s + 0.7 * st.ema;
              var cur = st.shown == null ? null
                : Math.max(0, st.shown - (Date.now() - st.shownT) / 1000);
              if (cur == null || st.ema <= cur) {
                st.shown = st.ema; st.shownT = Date.now(); st.up = 0;
              } else if (++st.up >= 3) {
                st.shown = st.ema; st.shownT = Date.now(); st.up = 0;
              }
            } else {
              st.shown = null;            // paused, or not yet estimable
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
        var line = Math.round(pct) + "% · " + d.done + "/" + d.total + " weeks";
        if (elapsed != null) line += " · " + hms(elapsed) + " elapsed";
        if (!paused && st.shown != null) {
          var rem = Math.max(0, st.shown - (Date.now() - st.shownT) / 1000);
          var m = Math.round(rem / 60);
          line += " · ~" + (m >= 90 ? (m / 60).toFixed(1) + " h" : m + " min")
            + " left";
        }
        if (paused) line += " · paused";
        var stat = c.querySelector(".rstat");
        if (stat) stat.textContent = line;
        var basis = c.querySelector(".rbasis");
        if (basis) basis.textContent = paused
          ? "Paused; the fits in flight finished first. The clock is held and resumes with the replay."
          : (d.weeks_measured
             ? "estimate from " + d.weeks_measured + " completed week" +
               (d.weeks_measured === 1 ? "" : "s")
             : "estimate arrives once the first week completes");
      });
    }

    setInterval(paint, 400);
    paint();
    poll();
    return {paint: paint};
  }

  return {init: init, hms: hms};
})();
