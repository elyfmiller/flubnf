/* The Model settings panel (templates/_model_settings.html): the live
   "shipped / modified" badge, the rows that do not apply to the chosen
   engine hidden (the server ignores them too, and never records them),
   "Reset to shipped", and the override's reason made required when its
   box is ticked. The server is the authority; this only keeps the page
   honest while the form is filled in. */
(function () {
  var box = document.getElementById('model-settings');
  if (!box) return;
  var form = box.closest('form');
  var badge = document.getElementById('ms-badge');
  var ovr = document.getElementById('ms-override');
  var tick = document.getElementById('ms-ovr');
  var reason = document.getElementById('ms-reason');
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
  function nums(v) {
    return String(v).split(',').map(function (x) { return parseFloat(x); });
  }
  function isModified(el) {
    if (el.disabled) return false;
    var v = String(el.value || '').trim(), d = el.dataset.default || '';
    if (el.dataset.knob === 'run.season_start') return v !== '' && v !== seasonDefault();
    if (v === '') return false;                      // blank means shipped
    if (el.type === 'number') return parseFloat(v) !== parseFloat(d);
    if (el.dataset.knob.indexOf('pf.prior.') === 0) {
      var a = nums(v), b = nums(d);
      return a.length !== b.length || a.some(function (x, i) { return x !== b[i]; });
    }
    return v !== d;
  }
  function members() {
    var e = form && (form.querySelector('#model-pick') || form.querySelector('#retro-engine'));
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
    var ms = members();
    box.querySelectorAll('.ms-row, .ms-group').forEach(function (n) {
      n.hidden = !applies(n, ms);
    });
  }
  function update() {
    var any = inputs.some(function (el) {
      return !el.closest('[hidden]') && isModified(el);
    });
    if (badge) {
      badge.textContent = any ? 'modified' : 'shipped';
      badge.className = 'ms-badge ' + (any ? 'warn' : 'ok');
    }
    if (ovr) ovr.hidden = !any;
    if (reason) reason.required = !!(any && tick && tick.checked);
  }
  var reset = document.getElementById('ms-reset');
  if (reset) reset.addEventListener('click', function () {
    inputs.forEach(function (el) {
      if (!el.disabled) el.value = el.dataset.default || '';
    });
    if (tick) tick.checked = false;
    if (reason) reason.value = '';
    update();
  });
  box.addEventListener('input', update);
  box.addEventListener('change', update);
  if (form) form.addEventListener('change', function (e) {
    if (e.target && (e.target.id === 'model-pick' || e.target.id === 'retro-engine'
                     || e.target.name === 'forecast_date' || e.target.name === 'season')) {
      filter(); update();
    }
  });
  filter(); update();
})();
