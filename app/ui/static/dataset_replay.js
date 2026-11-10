/* The Retrospective tab's own-data replay form
   (templates/_dataset_replay.html): two read-only lines beside Replay,
   recomputed in the browser whenever the form changes, with no request.

     the donor badge  "Groundhog donors: enough in 3 of 38 weeks": the
                      weeks of From..To whose Groundhog donor weeks reach
                      the need at every horizon (datasets_ui.donor_weeks,
                      embedded as #dsr-donor-data). It informs only:
                      Replay stays on. Counted at the shipped donor
                      window, so it hides while the panel's donor window
                      is changed.
     the time line    with the filter, the engine's cost model
                      (static/estimate.js, FluBNFEstimate): the weeks'
                      observed weeks from the season start, groups x
                      Independent Runs fits a week, the panel's
                      particles, shown as the span; the Groundhog alone
                      "under a minute" up to the form's data-gh-quick
                      (weeks x groups x data cells), else nothing. An
                      Independent Runs or particles field the server
                      would refuse (intOf) says nothing either.

   datasets_ui.donor_line and replay_estimate render both for the default
   range so the form reads right without script, by the same rules
   (app/tests/test_dataset_donor_weeks.py holds them equal).
   ES5 (docs/UI-KIT.md). */
(function (root) {
  "use strict";

  // the weeks of `dates` (ISO, ascending) from `first` to `last`,
  // inclusive (a blank end is open), as custom_retro.weeks_between
  function weeksIn(dates, first, last) {
    var out = [];
    for (var i = 0; i < dates.length; i++) {
      var w = dates[i];
      if ((!first || w >= first) && (!last || w <= last)) out.push(w);
    }
    return out;
  }

  // datasets_ui.donor_line: [state, text], ["", ""] with no week
  function donorBadge(weeks, counts, need) {
    if (!weeks.length) return ["", ""];
    var ok = 0;
    for (var i = 0; i < weeks.length; i++) {
      if ((counts[weeks[i]] || 0) >= need) ok++;
    }
    return [ok === weeks.length ? "ok" : "warn",
            "Groundhog donors: enough in " + ok + " of " + weeks.length +
            " week" + (weeks.length === 1 ? "" : "s")];
  }

  // datasets_ui.replay_estimate: the time line's text, "" for none.
  // `E` is FluBNFEstimate, `p` its params(form); `o` holds weeks (ISO),
  // groups, engine, replicates, particles, seasonStart, cells, quick
  function estimate(E, p, o) {
    var weeks = o.weeks || [];
    if (!weeks.length) return "";
    if (o.engine !== "all") {
      return weeks.length * o.groups * o.cells <= o.quick
        ? "under a minute" : "";
    }
    if (!E || !p) return "";
    var nobs = [];
    for (var i = 0; i < weeks.length; i++) {
      var n = E.nObsFor(weeks[i], o.seasonStart);
      if (n === null) return "";
      nobs.push(n);
    }
    var s = E.seconds(nobs, o.groups * o.replicates, o.particles, null, p);
    var sp = E.span(s, null, p.first);
    return E.human(sp[0], sp[1]);
  }

  // a panel field by its knob: its value, else its default ("" when it
  // has neither, or the field is not on the page)
  function knob(form, key) {
    var el = form.querySelector('[data-knob="' + key + '"]');
    if (!el) return {value: "", def: "", el: null};
    return {value: String(el.value || "").replace(/^\s+|\s+$/g, ""),
            def: el.getAttribute("data-default") || "", el: el};
  }

  // a whole number as the server reads the field (app/core/knobs.py:
  // commas and underscores dropped, then a plain integer within the
  // field's min and max); blank is its default, else `fallback`; null for
  // anything the server would refuse ("1e4", "2.5", "0"), so the line
  // times no replay that will not start
  function intOf(k, fallback) {
    var t = k.value.replace(/[,_]/g, "");
    if (t === "") {
      var d = parseInt(k.def, 10);
      return isFinite(d) && d > 0 ? d : fallback;
    }
    if (!/^[+-]?[0-9]+$/.test(t)) return null;
    var v = parseInt(t, 10);
    var lo = k.el ? parseFloat(k.el.getAttribute("min")) : NaN;
    var hi = k.el ? parseFloat(k.el.getAttribute("max")) : NaN;
    if ((isFinite(lo) && v < lo) || (isFinite(hi) && v > hi)) return null;
    return v;
  }

  function init(form) {
    if (!form || form.getAttribute("data-dsr-ready")) return;
    form.setAttribute("data-dsr-ready", "1");
    var dataEl = document.getElementById("dsr-donor-data");
    var data = null;
    try { data = JSON.parse(dataEl ? dataEl.textContent : "null"); }
    catch (e) { data = null; }
    var first = form.querySelector('[name="first"]');
    var last = form.querySelector('[name="last"]');
    var groups = form.querySelector('[name="groups"]');
    var engine = form.querySelector('[name="engine"]');
    var line = document.getElementById("dsr-donor-line");
    var badge = document.getElementById("dsr-donors");
    var est = document.getElementById("dsr-est");
    var estText = est ? est.querySelector(".uk-meta li > span:last-child")
                      : null;
    var E = root.FluBNFEstimate;
    var p = E ? E.params(form) : null;
    var dates = [];
    if (first) {
      for (var i = 0; i < first.options.length; i++) {
        dates.push(first.options[i].value);
      }
    }
    var cells = parseInt(form.getAttribute("data-cells"), 10) || 0;
    var quick = parseFloat(form.getAttribute("data-gh-quick")) || 0;

    function nGroups() {
      if (!groups) return 1;
      var n = 0;
      for (var j = 0; j < groups.options.length; j++) {
        if (groups.options[j].selected) n++;
      }
      // none picked replays every group (datasets_ui.replay_start)
      return n || groups.options.length || 1;
    }

    function update() {
      var weeks = weeksIn(dates, first ? first.value : "",
                          last ? last.value : "");
      if (line && badge && data && data.weeks) {
        var bw = knob(form, "groundhog.bandwidth");
        var b = donorBadge(weeks, data.weeks, data.need);
        // counted at the shipped donor window: said only there
        var off = !b[1] || (bw.el && bw.value !== "" && bw.value !== bw.def);
        line.hidden = !!off;
        if (!off) {
          var ui = root.FluBNFUI;
          if (ui && ui.setBadge) {
            ui.setBadge(badge, b[0], b[1]);
          } else {
            var t = badge.querySelector(".uk-badge-t");
            if (t) t.textContent = b[1];
          }
        }
      }
      if (est && estText) {
        var eng = engine ? engine.value : "analogue";
        var reps = intOf(knob(form, "pf.replicates"), 3);
        var parts = intOf(knob(form, "pf.particles"), 10000);
        // the filter's fields matter only when it runs
        var text = eng === "all" && (reps === null || parts === null) ? ""
          : estimate(E, p, {
            weeks: weeks, groups: nGroups(), engine: eng,
            replicates: reps, particles: parts,
            seasonStart: knob(form, "run.season_start").value,
            cells: cells, quick: quick});
        est.hidden = !text;
        if (text) estText.textContent = text;
      }
    }
    form.addEventListener("change", update);
    form.addEventListener("input", update);
    // the panel's Reset sets the fields without an event
    form.addEventListener("click", function (e) {
      if (e.target && e.target.id === "dsr-ms-reset") setTimeout(update, 0);
    });
    update();
  }

  var FluBNFDatasetReplay = {
    weeksIn: weeksIn,
    donorBadge: donorBadge,
    estimate: estimate,
    intOf: intOf,
    init: init
  };
  root.FluBNFDatasetReplay = FluBNFDatasetReplay;

  if (typeof document !== "undefined" && document.getElementById) {
    var start = function () { init(document.getElementById("dsr-form")); };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
