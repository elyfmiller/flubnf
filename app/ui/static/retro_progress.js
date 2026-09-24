// Live retrospective ticker (retro index + season page). Drives every
// progress element on .season-card[data-active="1"]: the .rfill bar, the
// .rstat readout, every .rcount counter (one source, so no line disagrees),
// the .rbasis hint and the .rquip line. A script poll, never a meta refresh;
// no reload while the caller's busy() is true (the guard modal).
// Rules: the percentage never regresses; the ETA is the server's RANGE,
// shown as sent and decayed by the wall clock (no client smoothing: it once
// pinned the display for hours); an unestimable ETA says so rather than
// leaving a stale number; after 3 failed polls the clocks freeze and the
// basis says the connection is lost (the next success clears it); paused
// freezes the readouts, withdraws the ETA and stops the quips.
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
        var pct = d.total ? 100 * d.done / d.total : 0;
        pct = Math.max(st.disp, Math.min(100, pct));
        st.disp = pct;                                    // never regress
        var fill = c.querySelector(".rfill");
        if (fill) fill.style.width = Math.max(pct, 2) + "%";
        var elapsed = d.elapsed_s;
        if (elapsed != null && (d.status === "running" || d.status === "stopping"))
          elapsed += (now - d.at) / 1000;    // held while paused or stalled
        var count = d.done + "/" + d.total + " weeks";
        var line = Math.round(pct) + "% · " + count;
        if (elapsed != null) line += " · " + hms(elapsed) + " elapsed";
        if (!paused && st.lo != null && st.hi != null) {
          var dt = (now - st.etaAt) / 1000;
          line += " · " + etaText(st.lo - dt, st.hi - dt) + " left";
        }
        if (paused) line += " · paused";
        var stat = c.querySelector(".rstat");
        if (stat) stat.textContent = line;
        // every secondary week counter follows the headline
        Array.prototype.forEach.call(c.querySelectorAll(".rcount"),
          function (el) { el.textContent = count; });
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
                            _internals: {etaText: etaText}};
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
