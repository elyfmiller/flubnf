/* The sandbox workbench (app/ui/templates/sandbox.html): the three
   files as tabs, the run
   settings presets and their time estimate, Check, the unsaved-changes
   chip, delete confirmations, the poll while a fit runs, and the results
   plot. Plain ES5, no build step; colours come from the page's tokens.
   The pure helpers are exported as SandboxPage for the tests. */
(function (root) {
  'use strict';

  // x positions of the trajectory columns: the observed rows at their own
  // times, the forecast columns one step apart past the last row (the step
  // the closest two rows are apart: 1 for weekly rows, gaps or not). With
  // one date per row the same offsets become dates, 7 days a unit.
  function xsFor(times, dates, columns) {
    var dt = 0, i, g, xs = [];
    for (i = 1; i < times.length; i++) {
      g = times[i] - times[i - 1];
      if (g > 0 && (!dt || g < dt)) dt = g;
    }
    dt = dt || 1;
    for (i = 0; i < columns; i++) {
      xs.push(i < times.length ? times[i]
        : times[times.length - 1] + dt * (i - times.length + 1));
    }
    if (dates && dates.length === times.length && times.length) {
      var d0 = Date.parse(dates[0] + 'T00:00:00Z'), t0 = times[0];
      xs = xs.map(function (x) {
        return new Date(d0 + (x - t0) * 7 * 864e5).toISOString().slice(0, 10);
      });
    }
    return xs;
  }

  // "about 40 s", "about 3 min", "about 1.5 h"
  function fmtEta(s) {
    if (!(s > 0)) return '';
    if (s < 90) return 'about ' + Math.max(1, Math.round(s)) + ' s';
    if (s < 5400) return 'about ' + Math.round(s / 60) + ' min';
    return 'about ' + (Math.round(s / 360) / 10) + ' h';
  }

  root.SandboxPage = {xsFor: xsFor, fmtEta: fmtEta, suggestName: suggestName};
  if (typeof document === 'undefined') return;

  function $(id) { return document.getElementById(id); }

  // a model name from a location and a date: oracle_new_york_2024-11-09
  function suggestName(loc, date) {
    var s = ('oracle_' + (loc || '') + '_' + (date || '')).toLowerCase()
      .replace(/[^a-z0-9_-]+/g, '_').replace(/_+/g, '_').replace(/_$/, '');
    return s.slice(0, 64);
  }

  // ---- the gallery's New model form: the Oracle SIHRS start asks for a
  // hub location and vintage, or a dataset group and week
  function setupNew() {
    var start = $('sbnew-start'), box = $('sbnew-shipped'), nm = $('sbnew-name');
    if (!start || !box) return;
    var loc = $('sbnew-loc'), date = $('sbnew-date'), grp = $('sbnew-group'), asof = $('sbnew-asof');
    var suggested = '';
    function each(sel, fn) { Array.prototype.forEach.call(box.querySelectorAll(sel), fn); }
    function name() {
      if (!nm || (nm.value && nm.value !== suggested)) return;
      var v = start.value, s = '';
      if (v === 'shipped:sihrs' && loc && date) s = suggestName(loc.value, date.value);
      else if (v.indexOf('shipped:dataset:') === 0 && grp) s = suggestName(grp.value, asof ? asof.value : '');
      nm.value = suggested = s;
    }
    function show() {
      var v = start.value, hub = v === 'shipped:sihrs', ds = v.indexOf('shipped:dataset:') === 0 ? v.slice(16) : '';
      box.hidden = !(hub || ds);
      // what the chosen start is: its note (the Oracle start shows its fields)
      var about = $('sbnew-about'), o = start.options[start.selectedIndex];
      if (about) about.textContent = (o && o.getAttribute('data-note')) || '';
      each('.sbnew-hub', function (e) { e.hidden = !hub; });
      each('.sbnew-ds', function (e) { e.hidden = !ds; });
      each('select, input', function (e) {
        var inHub = e.closest('.sbnew-hub'), inDs = e.closest('.sbnew-ds');
        e.disabled = box.hidden || (inHub && !hub) || (inDs && !ds);
      });
      if (grp && ds) {
        var first = null;
        Array.prototype.forEach.call(grp.options, function (o) {
          var mine = o.getAttribute('data-ds') === ds;
          o.hidden = !mine; o.disabled = !mine;
          if (mine && !first) first = o;
        });
        var cur = grp.selectedIndex >= 0 ? grp.options[grp.selectedIndex] : null;
        if (first && (!cur || cur.disabled)) first.selected = true;
        lastWeek();
      }
      name();
    }
    function lastWeek() {
      var o = grp && grp.selectedIndex >= 0 ? grp.options[grp.selectedIndex] : null;
      if (o && asof) asof.value = o.getAttribute('data-last') || asof.value;
    }
    start.addEventListener('change', show);
    [loc, date, asof].forEach(function (e) { if (e) e.addEventListener('change', name); });
    if (grp) grp.addEventListener('change', function () { lastWeek(); name(); });
    show();
  }

  // ---- the three files as tabs: without this script they stack, each
  // under its own label. The open tab is remembered per model for the
  // visit (a Save reloads the page); an upload's report opens data.exp.
  function setupTabs(form) {
    var bar = form && form.querySelector('.sbtabs');
    if (!bar) return;
    var tabs = Array.prototype.slice.call(bar.querySelectorAll('[role=tab]'));
    var key = 'sb-tab:' + form.getAttribute('data-model');
    function pick(file, focus) {
      tabs.forEach(function (t) {
        var on = t.getAttribute('data-file') === file, panel = $(t.getAttribute('aria-controls'));
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        if (panel) panel.hidden = !on;
        if (on && focus) t.focus();
      });
      Array.prototype.forEach.call(bar.querySelectorAll('.sbtabtips > [data-file]'), function (s) {
        s.hidden = s.getAttribute('data-file') !== file;
      });
      try { sessionStorage.setItem(key, file); } catch (e) { /* storage off: no memory */ }
      // the editor sizes its gutter from the textarea: measure the shown one
      try { root.dispatchEvent(new Event('resize')); } catch (e) { /* old browser */ }
    }
    var first = 'bngl';
    try { first = sessionStorage.getItem(key) || first; } catch (e) { /* storage off */ }
    var fill = form.querySelector('details.sbfill[open]');
    if (fill) first = 'exp';
    form.classList.add('sb-tabbed');
    tabs.forEach(function (t) {
      var panel = $(t.getAttribute('aria-controls'));
      if (panel) { panel.setAttribute('role', 'tabpanel'); panel.setAttribute('aria-labelledby', t.id); }
      t.addEventListener('click', function () { pick(t.getAttribute('data-file')); });
      t.addEventListener('keydown', function (e) {
        var i = tabs.indexOf(t), n = tabs.length, j = -1;
        if (e.key === 'ArrowRight') j = (i + 1) % n;
        else if (e.key === 'ArrowLeft') j = (i + n - 1) % n;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = n - 1;
        if (j < 0) return;
        e.preventDefault();
        pick(tabs[j].getAttribute('data-file'), true);
      });
    });
    bar.hidden = false;
    pick(tabs.some(function (t) { return t.getAttribute('data-file') === first; }) ? first : 'bngl');
  }

  // the page-head menus (How it works, Manage) are popovers: one open at
  // a time, and Escape or a click outside closes them, as the Display
  // menu does; Escape hands focus back to the menu's button
  function setupMenus() {
    var menus = Array.prototype.slice.call(document.querySelectorAll('details.sbmanage'));
    if (!menus.length) return;
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      menus.forEach(function (d) {
        if (!d.open) return;
        d.open = false;
        if (d.contains(document.activeElement) || document.activeElement === document.body)
          d.querySelector('summary').focus();
      });
    });
    document.addEventListener('click', function (e) {
      menus.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
    });
  }

  function setup() {
    setupNew();
    setupMenus();
    var form = $('sbform');
    setupTabs(form);
    // ---- run settings: the preset sets the particles; typing a count
    // other than a preset's reads as custom; the estimate follows
    var preset = $('sb-preset'), parts = $('sb-particles'), eta = $('sb-eta');
    function showEta() {
      if (!eta || !parts) return;
      var full = parseFloat(eta.getAttribute('data-full')) || 0;
      var n = parseInt(parts.value, 10) || 0;
      var t = fmtEta(full * n / 10000);
      eta.textContent = t ? 'Fitting takes ' + t + ' on this machine (estimated).' : '';
    }
    if (preset && parts) {
      var quick = preset.getAttribute('data-quick'), full = preset.getAttribute('data-full');
      preset.addEventListener('change', function () {
        if (preset.value === 'quick') parts.value = quick;
        if (preset.value === 'full') parts.value = full;
        if (preset.value === 'custom') parts.focus();
        showEta();
      });
      parts.addEventListener('input', function () {
        preset.value = parts.value === quick ? 'quick' : parts.value === full ? 'full' : 'custom';
        showEta();
      });
      showEta();
    }

    // ---- Load data: a hub source asks for a location, a dataset for one
    // of its groups (the range follows the group when the source changes)
    var src = $('sbfill-source'), locw = $('sbfill-locwrap'), grpw = $('sbfill-groupwrap'),
        grp = $('sbfill-group'), d0 = $('sbfill-start'), d1 = $('sbfill-end');
    function rangeFromGroup() {
      var o = grp && grp.selectedIndex >= 0 ? grp.options[grp.selectedIndex] : null;
      if (!o || !d0 || !d1) return;
      d0.value = o.getAttribute('data-first') || d0.value;
      d1.value = o.getAttribute('data-last') || d1.value;
    }
    function showSource(changed) {
      if (!src) return;
      var ds = src.value.indexOf('dataset:') === 0 ? src.value.slice(8) : '';
      if (locw) locw.hidden = !!ds;
      if (grpw) grpw.hidden = !ds;
      if (!grp) return;
      var first = null;
      Array.prototype.forEach.call(grp.options, function (o) {
        var mine = o.getAttribute('data-ds') === ds;
        o.hidden = !mine;
        o.disabled = !mine;
        if (mine && !first) first = o;
      });
      var cur = grp.selectedIndex >= 0 ? grp.options[grp.selectedIndex] : null;
      if (ds && first && (!cur || cur.disabled)) first.selected = true;
      if (ds && changed) rangeFromGroup();
    }
    if (src) {
      src.addEventListener('change', function () { showSource(true); });
      if (grp) grp.addEventListener('change', rangeFromGroup);
      showSource(false);
    }

    // ---- unsaved changes: a chip beside Save, and a warning on leaving
    var dirty = false, chip = $('sb-dirty');
    if (form) {
      form.addEventListener('input', function (e) {
        if (!e.target || e.target.tagName !== 'TEXTAREA') return;
        dirty = true;
        if (chip) chip.hidden = false;
        // a check report is of the text as it was: mark it as older
        var rep = $('sb-checked');
        if (rep && rep.firstChild) rep.classList.add('sb-stale');
      });
      form.addEventListener('submit', function () { dirty = false; });
      addEventListener('beforeunload', function (e) {
        if (!dirty) return;
        e.preventDefault();
        e.returnValue = '';
      });
    }

    // ---- Check: the editor text, read without the engine
    var check = $('sb-check'), out = $('sb-checked');
    function list(title, items, cls) {
      var wrap = document.createElement('div');
      var h = document.createElement('p');
      h.className = cls;
      h.textContent = title;
      wrap.appendChild(h);
      if (items.length) {
        var ul = document.createElement('ul');
        items.forEach(function (t) {
          var li = document.createElement('li');
          li.textContent = t;
          ul.appendChild(li);
        });
        wrap.appendChild(ul);
      }
      return wrap;
    }
    if (check && out && form) {
      check.addEventListener('click', function () {
        check.disabled = true;
        out.classList.remove('sb-stale');
        out.textContent = 'Checking.';
        fetch('/api/sandbox/models/' + encodeURIComponent(form.getAttribute('data-model')) + '/check',
              {method: 'POST', body: new FormData(form)})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            while (out.firstChild) out.removeChild(out.firstChild);
            var f = d.facts || {}, facts = [];
            if (f.suffix) facts.push('simulate suffix ' + f.suffix);
            if (f.rows) facts.push(f.rows + ' data rows');
            if (f.free && f.free.length) facts.push(f.free.length + ' fitted parameters');
            if (f.network) facts.push('network ' + f.network + (f.species != null ? ' (' + f.species + ' species, ' + f.reactions + ' reactions)' : ''));
            var probs = d.problems || [], warns = d.warnings || [];
            out.appendChild(list(probs.length ? probs.length + ' problem' + (probs.length === 1 ? '' : 's') + ': a run would fail.'
              : 'No problems found: the model can run. Only a run shows whether it fits the data.',
              probs, probs.length ? 'sb-bad' : 'sb-ok'));
            if (warns.length) out.appendChild(list('Worth a look:', warns, 'sb-warn'));
            // the model at its written values beside the data, then the facts
            [f.at_start ? f.at_start.charAt(0).toUpperCase() + f.at_start.slice(1) + '.' : '',
             facts.join(' · ')].forEach(function (text) {
              if (!text) return;
              var p = document.createElement('p');
              p.className = 'hint';
              p.textContent = text;
              out.appendChild(p);
            });
          })
          .catch(function () { out.textContent = 'The check could not be run.'; })
          .then(function () { check.disabled = false; });
      });
    }

    // ---- deletes: the shared confirmation shell, confirm filled on OK
    Array.prototype.forEach.call(document.querySelectorAll('[data-sb-delete]'), function (b) {
      b.addEventListener('click', function () {
        var f = b.form;
        if (!f) return;
        var ok = function () { dirty = false; f.confirm.value = f.ident.value; f.submit(); };
        if (!root.FluBNFConfirm) { if (root.confirm('Delete ' + b.getAttribute('data-sb-delete') + '?')) ok(); return; }
        root.FluBNFConfirm({title: 'Delete ' + b.getAttribute('data-sb-delete') + '?',
          msg: 'This permanently deletes it from the sandbox. It cannot be undone.',
          okLabel: 'Delete permanently', onOk: ok});
      });
    });

    // ---- the open run: poll while it may still be fitting, then reload
    var box = $('results');
    var live = function (s) { return s === 'running' || s === 'prepared'; };
    if (box && live(box.getAttribute('data-status'))) {
      var id = box.getAttribute('data-run');
      var timer = setInterval(function () {
        fetch('/api/sandbox/runs/' + encodeURIComponent(id)).then(function (r) { return r.json(); })
          .then(function (d) {
            if (d && d.meta && !live(d.meta.status)) {
              clearInterval(timer);
              if (!dirty) location.reload();
              else if (chip) chip.textContent = 'unsaved changes (the run ended: save, then reload)';
            }
          }).catch(function () {});
      }, 5000);
    }
    plot();
    addEventListener('themechange', plot);
    addEventListener('fontsizechange', plot);
  }

  // ---- the results plot: the 10 to 90% band and the median of the
  // trajectory, the observed counts as points
  function plot() {
    var RES = root.SANDBOX_RES, el = $('sbplot');
    if (!el || !RES || !RES.traj || !root.Plotly) return;
    var css = function (v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); };
    var fs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    function hexa(h, a) {
      h = (h || '').replace('#', '');
      if (h.length === 3) h = h.replace(/(.)/g, '$1$1');
      if (h.length !== 6) return 'transparent';
      return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')';
    }
    var t = RES.traj, times = RES.meta.time || [], dates = RES.meta.dates || [];
    var xs = xsFor(times, dates, t.columns), n = t.n_obs;
    var calendar = dates.length === times.length && times.length > 0;
    var ink = css('--ink'), mut = css('--mut'), line = css('--line'), acc = css('--accent'),
        accInk = css('--accent-ink'), surf = css('--card');
    var band = {x: xs.concat(xs.slice().reverse()), y: t.q90.concat(t.q10.slice().reverse()),
                fill: 'toself', fillcolor: hexa(acc, 0.22), line: {width: 0}, name: '10 to 90%', hoverinfo: 'skip'};
    var med = {x: xs, y: t.q50, mode: 'lines', name: 'median', line: {color: accInk, width: 2}};
    // a negative count is a missing week (the data writer's mark): no point
    var obs = (RES.meta.observed || []).map(function (v) { return v < 0 ? null : v; });
    var pts = {x: xs.slice(0, times.length), y: obs, mode: 'markers',
               name: RES.meta.obs_col || 'observed', marker: {color: ink, size: 6}};
    var traces = [band, med, pts];
    // a compared run: its band and median dashed, on the same axis
    var C = root.SANDBOX_CMP;
    if (C && C.traj && C.meta) {
      var ct = C.meta.time || [], cd = C.meta.dates || [];
      var cCal = cd.length === ct.length && ct.length > 0;
      if (cCal === calendar) {
        var cx = xsFor(ct, cCal ? cd : [], C.traj.columns), mu = css('--mut');
        traces.unshift({x: cx.concat(cx.slice().reverse()), y: C.traj.q90.concat(C.traj.q10.slice().reverse()),
                        fill: 'toself', fillcolor: hexa(mu, 0.14), line: {width: 0}, name: 'compared 10 to 90%', hoverinfo: 'skip'});
        traces.push({x: cx, y: C.traj.q50, mode: 'lines', name: 'compared median',
                     line: {color: mu, width: 2, dash: 'dash'}});
      }
    }
    var shapes = n < t.columns ? [{type: 'line', x0: xs[n - 1], x1: xs[n - 1], y0: 0, y1: 1, yref: 'paper',
                                   line: {dash: 'dot', color: mut}}] : [];
    // FluCharts (charts.js): Saturday week ticks on a dated axis, shared config
    (root.FluCharts || root.Plotly).newPlot(el, traces, {margin: {t: 30, r: 10, l: 64, b: 48}, shapes: shapes,
      paper_bgcolor: surf, plot_bgcolor: surf,
      font: {color: ink, family: '"DM Sans",system-ui,sans-serif', size: Math.round(fs * 0.85)},
      xaxis: {automargin: true, title: {text: calendar ? 'week ending' : 'time'}, gridcolor: line, zerolinecolor: line, linecolor: line, tickfont: {color: ink}},
      yaxis: {automargin: true, title: {text: RES.meta.obs_col || 'count', standoff: 10}, rangemode: 'tozero', gridcolor: line, zerolinecolor: line, linecolor: line, tickfont: {color: ink}},
      legend: {orientation: 'h', x: 0, y: 1.02, yanchor: 'bottom', font: {color: ink}}},
      {displayModeBar: false, responsive: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup);
  else setup();
})(this);
