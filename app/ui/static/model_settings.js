/* The Model settings panel (templates/_model_settings.html): the live
   "default / modified" badge, the rows that do not apply to the chosen
   engine hidden (the server ignores them too, and never records them),
   "Reset to defaults", and the override's reason made required when its
   box is ticked. The server is the authority; this only keeps the page
   honest while the form is filled in.

   Every panel on the page is its own (the Retrospective tab holds the
   FluSight replay's and the own-data replay's); a panel's parts are found
   inside it, never by a page-wide id. data-engine names the model select
   a panel follows (default: #model-pick or #retro-engine in its form);
   data-kind (set by the page) hides the rows marked data-only for another
   kind of data, and a group whose rows are all hidden hides too. Loading
   the script twice sets nothing up twice. */
(function () {
  function init(box) {
    if (box.dataset.msReady) return;
    box.dataset.msReady = '1';
    var form = box.closest('form');
    var badge = box.querySelector('.ms-badge');
    var ovr = box.querySelector('.ms-override');
    var tick = box.querySelector('input[name=submit_modified]');
    var reason = box.querySelector('input[name=modified_reason]');
    var reset = box.querySelector('.ms-head > button');
    var inputs = Array.prototype.slice.call(box.querySelectorAll('[data-knob]'));

    // August 1 of the forecast date's season (RunSpec's rule); the
    // retrospective's season start is August 1 of the season name
    function seasonDefault() {
      var d = form && form.querySelector('input[name=forecast_date]');
      var s = form && form.querySelector('select[name=season]');
      var m = d ? (d.value || '').match(/^(\d{4})-(\d{2})/) : null;
      if (m) return ((+m[2] >= 8) ? +m[1] : +m[1] - 1) + '-08-01';
      m = s ? (s.value || '').match(/^(\d{4})-/) : null;
      return m ? m[1] + '-08-01' : '';
    }
    // Season start shows its default (a blank date field reads as today in
    // some browsers); it follows the date until someone types their own
    function syncSeason() {
      inputs.forEach(function (el) {
        if (el.dataset.knob !== 'run.season_start') return;
        var d = seasonDefault();
        if (el.value === '' || el.value === el.dataset.auto) {
          el.value = d;
          el.dataset.auto = d;
        }
      });
    }
    function nums(v) {
      return String(v).split(',').map(function (x) { return parseFloat(x); });
    }
    function isModified(el) {
      if (el.disabled) return false;
      if (el.dataset.optional) return false;           // adds hub rows only
      var v = String(el.value || '').trim(), d = el.dataset.default || '';
      if (el.dataset.knob === 'run.season_start') return v !== '' && v !== seasonDefault();
      if (v === '') return false;                      // blank means the default
      if (el.type === 'number') return parseFloat(v) !== parseFloat(d);
      if (el.dataset.knob.indexOf('pf.prior.') === 0) {
        var a = nums(v), b = nums(d);
        return a.length !== b.length || a.some(function (x, i) { return x !== b[i]; });
      }
      return v !== d;
    }
    function engineSelect() {
      if (box.dataset.engine) return document.getElementById(box.dataset.engine);
      return form && (form.querySelector('#model-pick') || form.querySelector('#retro-engine'));
    }
    function members() {
      var e = engineSelect();
      var v = e ? e.value : 'all';
      if (v === 'analogue') return ['analogue'];
      if (v === 'pf' && e.id === 'model-pick') return ['pf'];
      return ['pf', 'analogue'];                     // the retro "pf" runs both
    }
    function applies(node, ms) {
      return (node.dataset.affects || '').split(' ').some(function (m) {
        return ms.indexOf(m) >= 0;
      });
    }
    function filter() {
      var ms = members(), kind = box.dataset.kind || '';
      box.querySelectorAll('.ms-row').forEach(function (n) {
        n.hidden = !applies(n, ms)
          || !!(kind && n.dataset.only && n.dataset.only !== kind);
      });
      box.querySelectorAll('.ms-group').forEach(function (g) {
        var rows = Array.prototype.slice.call(g.querySelectorAll('.ms-row'));
        g.hidden = !applies(g, ms)
          || (rows.length > 0 && rows.every(function (n) { return n.hidden; }));
      });
    }
    function update() {
      var any = inputs.some(function (el) {
        return !el.closest('[hidden]') && isModified(el);
      });
      if (badge) {
        badge.textContent = any ? 'modified' : 'default';
        badge.className = 'ms-badge ' + (any ? 'warn' : 'ok');
      }
      if (ovr) ovr.hidden = !any;
      if (reason) reason.required = !!(any && tick && tick.checked);
    }
    if (reset) reset.addEventListener('click', function () {
      inputs.forEach(function (el) {
        if (!el.disabled) el.value = el.dataset.default || '';
      });
      syncSeason();
      if (tick) tick.checked = false;
      if (reason) reason.value = '';
      update();
    });
    box.addEventListener('input', update);
    box.addEventListener('change', update);
    if (form) form.addEventListener('change', function (e) {
      var t = e.target;
      if (t && (t === engineSelect() || t.id === 'model-pick' || t.id === 'retro-engine'
                || t.name === 'forecast_date' || t.name === 'season'
                || t.name === 'dataset')) {
        syncSeason(); filter(); update();
      }
    });
    // the page says the kind of data changed (the own-data replay's
    // dataset select): refilter without waiting for a form change
    box.addEventListener('ms-refilter', function () { syncSeason(); filter(); update(); });
    syncSeason(); filter(); update();
  }
  document.querySelectorAll('details[data-scope]').forEach(init);
})();
