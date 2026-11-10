/* The Forecast form's two read-only lines (templates/forecast.html),
   redone in the browser on every change to the form, without a request.

   The Run row's time line (runWords; hub form only): the models the form
   runs, how many locations and how long, from the engine's cost model
   (static/estimate.js, FluBNFEstimate, reading the form's data-est-*
   attributes): fits = locations x Independent Runs at the week the date
   anchors on, at this computer's width, shown as the span (1 to 4 times
   the model; this computer's recorded pace at both ends, then "here").
   The Groundhog alone, or Both without the engine, says the line's
   data-gh words. routes/forecast.run_words is the same rule for the page
   as first shown (app/tests/test_forecast_runrow.py holds the two equal).

   A dataset's donor line (donorText; dataset form only): the Groundhog's
   donor weeks at the anchor week (the page's #fc-donor-data, counted at
   the shipped donor window: datasets_ui.donor_weeks), said while the
   Groundhog runs, the week has fewer than it needs, and the donor window
   and Weeks to drop are at their defaults (either moves what it finds).
   With several groups a week counts once in each, so the line says
   group-weeks (the page's unit, datasets_ui.donor_unit). It informs
   only: Run models stays on.

   ES5 (docs/UI-KIT.md); reads the form, posts nothing. */
(function (root) {
  "use strict";

  // the models, as the line names them (routes/forecast.RUN_MODELS)
  var MODELS = {all: "Oracle SIHRS and Groundhog", pf: "Oracle SIHRS",
                analogue: "Groundhog"};

  // a field as the line reads it: digits are their number, anything else
  // (blank included) is dflt (routes/forecast._whole_field)
  function whole(v, dflt) {
    var t = String(v === null || v === undefined ? "" : v)
      .replace(/^\s+|\s+$/g, "");
    return /^[0-9]+$/.test(t) ? parseInt(t, 10) : dflt;
  }

  // the line for one state of the form (o: what readRun returns; E:
  // FluBNFEstimate); "" for nothing to say (routes/forecast.run_words)
  function runWords(E, o) {
    if (!o || !MODELS.hasOwnProperty(o.engine) || !(o.locations > 0))
      return "";
    var ready = o.pf === "ready";
    if (o.engine === "pf" && !ready) return "";
    if (o.engine === "all" && !ready && o.pf !== "absent") return "";
    var where = o.locations + (o.locations === 1 ? " location" : " locations");
    if (o.engine === "analogue" || !ready)
      return o.gh ? "Groundhog, " + where + ": " + o.gh : "";
    if (!E || !o.p || o.replicates === null || o.particles === null)
      return "";
    var n = E.nObsFor(o.anchor, o.seasonStart);
    if (n === null) return "";
    var sp = E.span(E.seconds([n], o.locations * o.replicates, o.particles,
                              null, o.p), o.ratio, o.p.first);
    var w = E.human(sp[0], sp[1]);
    if (!w) return "";
    return MODELS[o.engine] + ", " + where + ": " + w + (o.ratio ? " here" : "");
  }

  // what a number box holds, and so posts: its text when that is a valid
  // floating-point number (HTML), else blank. A browser's box never holds
  // "x" or "1,000"; it does hold "1e4", "2.5" and "-3"
  var HTML_FLOAT = /^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
  function boxValue(f) {
    var t = String(f.value === null || f.value === undefined ? "" : f.value);
    var number =
      String(f.getAttribute("type") || "").toLowerCase() === "number";
    return number && !HTML_FLOAT.test(t) ? "" : t;
  }

  // Python's str.strip() (what str.isspace() calls space), and int()'s
  // own spaces (the same but U+001C to U+001F)
  var PY_STRIP = new RegExp(
    "^[\\t\\n\\x0b-\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028" +
    "\\u2029\\u202f\\u205f\\u3000]+|[\\t\\n\\x0b-\\r\\x1c-\\x1f \\x85\\xa0" +
    "\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]+$", "g");
  var PY_INT_SPACE = "[\\t\\n\\x0b-\\r \\x85\\xa0\\u1680\\u2000-\\u200a" +
                     "\\u2028\\u2029\\u202f\\u205f\\u3000]";
  var PY_INT = new RegExp("^" + PY_INT_SPACE + "*([+-]?)([0-9]+)" +
                          PY_INT_SPACE + "*$");
  // the most digits Python's int() reads from text
  // (sys.int_info.default_max_str_digits)
  var PY_INT_DIGITS = 4300;

  // a model setting's whole number (Particles, Independent Runs) as the
  // server's check reads what the box posts (app/core/knobs.py _coerce,
  // as retro_progress.js knobWhole): blank is the field's data-default;
  // else stripped, commas and underscores dropped, then Python's int(),
  // within the field's min and max. null for what the check refuses
  // ("1e4", "2.5", "0"), so the line gives no figure for a run that will
  // not start (review of #93, re-check at 099907c, finding 3)
  function knobWhole(f) {
    var t = boxValue(f).replace(PY_STRIP, "");
    if (t === "") return whole(f.getAttribute("data-default"), null);
    var m = PY_INT.exec(t.replace(/[,_]/g, ""));
    if (!m || m[2].length > PY_INT_DIGITS) return null;
    var v = parseInt(m[1] + m[2], 10);
    var lo = parseFloat(f.getAttribute("min")),
        hi = parseFloat(f.getAttribute("max"));
    if (!isFinite(v) || (isFinite(lo) && v < lo) || (isFinite(hi) && v > hi))
      return null;
    return v;
  }

  // a model setting's field (data-knob) as knobWhole reads it; null when
  // the form has no such field
  function knob(form, key) {
    var el = form.querySelector('[data-knob="' + key + '"]');
    return el ? knobWhole(el) : null;
  }

  // the form as runWords reads it: the model, the locations ("all" is the
  // line's data-all; else the ticked states and US), Independent Runs,
  // particles, the anchor week (paint() keeps it on the date field),
  // Season start, and the line's data-ratio, data-pf and data-gh
  function readRun(form, line) {
    var E = root.FluBNFEstimate;
    if (!form || !line) return null;
    var p = E ? E.params(form) : null;
    var model = form.querySelector("#model-pick");
    var all = form.querySelector("#ck-all"), us = form.querySelector("#ck-us");
    var n = 0;
    if (all && all.checked) n = whole(line.getAttribute("data-all"), 0);
    else {
      n = form.querySelectorAll("input.ck-one:checked").length;
      if (us && us.checked) n += 1;
    }
    var date = form.querySelector("input[name=forecast_date]");
    var season = form.querySelector('[data-knob="run.season_start"]');
    var ratio = parseFloat(line.getAttribute("data-ratio"));
    return {p: p, engine: model ? model.value : "", locations: n,
            replicates: knob(form, "pf.replicates"),
            particles: knob(form, "pf.particles"),
            anchor: date ? (date.getAttribute("data-anchor") || "") : "",
            seasonStart: season ? season.value : "",
            ratio: ratio > 0 ? ratio : null,
            pf: line.getAttribute("data-pf") || "",
            gh: line.getAttribute("data-gh") || ""};
  }

  // the donor line for one state of the form (o: what readDonor returns);
  // "" for nothing to say. o.unit: "group-weeks" with several groups,
  // else weeks
  function donorText(o) {
    if (!o || !o.groundhog || !o.windowDefault || !o.dropDefault) return "";
    if (typeof o.count !== "number" || !(o.need > 0) || o.count >= o.need)
      return "";
    return "The Groundhog has too little history for this week (" +
      o.count + " of " + o.need + " donor " +
      (o.unit === "group-weeks" ? "group-weeks" : "weeks") + ").";
  }

  // a model setting at its default: blank, or the same number
  function atDefault(form, key) {
    var el = form.querySelector('[data-knob="' + key + '"]');
    if (!el || el.disabled) return true;
    var v = String(el.value || "").replace(/^\s+|\s+$/g, "");
    return v === "" || parseFloat(v) === parseFloat(el.getAttribute("data-default"));
  }

  // the form as donorText reads it: the anchor week's count and the
  // unit from the page's counts, whether the Groundhog runs, and whether
  // the donor window and Weeks to drop are at their defaults
  function readDonor(form, counts) {
    if (!form || !counts || !counts.weeks) return null;
    var date = form.querySelector("input[name=forecast_date]");
    var a = date ? (date.getAttribute("data-anchor") || "") : "";
    var model = form.querySelector("#model-pick");
    var c = a && counts.weeks.hasOwnProperty(a) ? counts.weeks[a] : null;
    return {count: typeof c === "number" ? c : null, need: counts.need,
            unit: counts.unit === "group-weeks" ? "group-weeks" : "weeks",
            groundhog: !!model && model.value !== "pf",
            windowDefault: atDefault(form, "groundhog.bandwidth"),
            dropDefault: atDefault(form, "run.weeks_to_drop")};
  }

  // keep both lines current: on every change or input in the form, a
  // preset or a mode button (they set values by script), the Model
  // settings panel's reset (ms-reset) and date follow (ms-refilter), the
  // page shown again from the history, and once the deferred scripts have
  // run (the panel fills Season start). Each waits a tick, so the page's
  // own handlers (the anchor, Season start) go first.
  function bind(doc) {
    var form = doc.getElementById("fcform");
    if (!form) return null;
    var line = doc.getElementById("fc-est");
    var alert = doc.getElementById("fc-ds-donors");
    var counts = null, data = doc.getElementById("fc-donor-data");
    if (data) {
      try { counts = JSON.parse(data.textContent || "null"); }
      catch (e) { counts = null; }
    }
    function sync() {
      if (line) {
        var w = runWords(root.FluBNFEstimate, readRun(form, line));
        var t = line.querySelector(".uk-meta li > span:last-child");
        if (t) t.textContent = w;
        line.hidden = !w;
      }
      if (alert) {
        var d = donorText(readDonor(form, counts));
        var s = alert.querySelector(".uk-alert-text");
        if (s && d) s.textContent = d;
        alert.hidden = !d;
      }
    }
    if (!line && !alert) return null;
    var timer = null;
    function soon() {
      clearTimeout(timer);
      timer = setTimeout(sync, 0);
    }
    ["change", "input", "click", "fc-form-change", "ms-reset"].forEach(
      function (ev) { form.addEventListener(ev, soon); });
    Array.prototype.forEach.call(form.querySelectorAll("details[data-scope]"),
      function (d) { d.addEventListener("ms-refilter", soon); });
    // deferred, this runs before DOMContentLoaded and the panel's script
    if (doc.readyState !== "complete")
      doc.addEventListener("DOMContentLoaded", soon);
    if (root.addEventListener) root.addEventListener("pageshow", soon);
    sync();
    return {sync: sync};
  }

  var FluBNFForecastForm = {runWords: runWords, readRun: readRun,
                            donorText: donorText, readDonor: readDonor,
                            whole: whole, bind: bind, MODELS: MODELS};
  root.FluBNFForecastForm = FluBNFForecastForm;
  if (typeof module !== "undefined" && module.exports)
    module.exports = FluBNFForecastForm;
  if (typeof document !== "undefined" && document.getElementById) {
    if (document.readyState === "loading")
      document.addEventListener("DOMContentLoaded",
                                function () { bind(document); });
    else bind(document);
  }
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
