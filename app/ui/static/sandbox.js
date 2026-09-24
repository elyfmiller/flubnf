/* The sandbox workbench (app/ui/templates/sandbox.html): the run
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

  root.SandboxPage = {xsFor: xsFor, fmtEta: fmtEta};
  if (typeof document === 'undefined') return;

  function $(id) { return document.getElementById(id); }

  function setup() {
    var form = $('sbform');
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
              : 'No problems found.', probs, probs.length ? 'sb-bad' : 'sb-ok'));
            if (warns.length) out.appendChild(list('Worth a look:', warns, 'sb-warn'));
            if (facts.length) {
              var p = document.createElement('p');
              p.className = 'hint';
              p.textContent = facts.join(' · ');
              out.appendChild(p);
            }
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
    var pts = {x: xs.slice(0, times.length), y: RES.meta.observed || [], mode: 'markers',
               name: RES.meta.obs_col || 'observed', marker: {color: ink, size: 6}};
    var shapes = n < t.columns ? [{type: 'line', x0: xs[n - 1], x1: xs[n - 1], y0: 0, y1: 1, yref: 'paper',
                                   line: {dash: 'dot', color: mut}}] : [];
    root.Plotly.newPlot(el, [band, med, pts], {margin: {t: 30, r: 10, l: 64, b: 48}, shapes: shapes,
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
