/* The Model settings panel (templates/_model_settings.html): the live
   "default / modified" badge (a kit badge), the rows that do not apply to
   the chosen engine hidden and their fields off (the server ignores them
   too, and never records them; an off field is never checked or posted),
   "Reset to defaults", the override's reason shown and required when its
   box is ticked, and a value the browser refuses shown even while the
   panel is closed. The server is the authority; this only keeps the page
   honest while the form is filled in.

   Every panel on the page is its own (the Retrospective tab holds the
   FluSight replay's and the own-data replay's); a panel's parts are found
   inside it, never by a page-wide id. data-engine names the model select
   a panel follows (default: #model-pick or #retro-engine in its form);
   data-kind (set by the page) hides the rows marked data-only for another
   kind of data, and a group whose rows are all hidden hides too. The
   panel opens or closes as the user left it this session (sessionStorage,
   per page and panel); a run forgets it, so the page after a run shows
   the panel closed unless the server refused its settings. Loading the
   script twice sets nothing up twice. */
(function () {
  function init(box) {
    if (box.dataset.msReady) return;
    box.dataset.msReady = '1';
    var form = box.closest('form');
    // the summary's kit badge (tips.badge: icon and word)
    var badge = box.querySelector('summary .uk-badge');
    var ovr = box.querySelector('.ms-override');
    var tick = box.querySelector('input[name=submit_modified]');
    var reason = box.querySelector('input[name=modified_reason]');
    var why = box.querySelector('.ms-why');
    var reset = box.querySelector('.ms-head > button');
    var inputs = Array.prototype.slice.call(box.querySelectorAll('[data-knob]'));

    // August 1 of the forecast date's season (RunSpec's rule); the
    // retrospective's season start is August 1 of the season name
    function seasonDefault() {
      var d = form && form.querySelector('input[name=forecast_date]');
      var s = form && form.querySelector('select[name=season]');
      // the week the run anchors on (the Forecast page sets data-anchor),
      // not the typed day: a September day anchors on July's data
      var day = d ? (d.dataset.anchor || d.value || '') : '';
      var m = day.match(/^(\d{4})-(\d{2})/);
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
    // a row hidden here has its field off (data-ms-off marks the ones
    // this script turned off; a coming-later field stays off for good)
    function setOff(row, off) {
      row.querySelectorAll('[data-knob]').forEach(function (el) {
        if (off && !el.disabled) { el.disabled = true; el.dataset.msOff = '1'; }
        else if (!off && el.dataset.msOff) { el.disabled = false; delete el.dataset.msOff; }
      });
    }
    function filter() {
      var ms = members(), kind = box.dataset.kind || '';
      box.querySelectorAll('.ms-row').forEach(function (n) {
        n.hidden = !applies(n, ms)
          || !!(kind && n.dataset.only && n.dataset.only !== kind);
        setOff(n, n.hidden);
      });
      box.querySelectorAll('.ms-group').forEach(function (g) {
        var rows = Array.prototype.slice.call(g.querySelectorAll('.ms-row'));
        g.hidden = !applies(g, ms)
          || (rows.length > 0 && rows.every(function (n) { return n.hidden; }));
      });
      // the "coming later" fold hides with its last applying row
      box.querySelectorAll('.ms-later-fold').forEach(function (f) {
        var rows = Array.prototype.slice.call(f.querySelectorAll('.ms-row'));
        f.hidden = rows.length > 0 && rows.every(function (n) { return n.hidden; });
      });
    }
    // the badge takes its state's word, class and icon. The icon comes
    // from FluBNFUI (tips.js, loaded after this script): until then the
    // server's icon stays, and the next update swaps it
    if (badge) badge.dataset.icon = badge.getAttribute('data-state');
    function setBadge(state, text) {
      badge.className = 'uk-badge uk-badge--' + state;
      badge.setAttribute('data-state', state);
      var t = badge.querySelector('.uk-badge-t');
      if (t) t.textContent = text;
      var svg = badge.querySelector('svg');
      if (svg && window.FluBNFUI && badge.dataset.icon !== state) {
        svg.outerHTML = window.FluBNFUI.icon(state === 'warn' ? 'warning' : 'check');
        badge.dataset.icon = state;
      }
    }
    function update() {
      // each field off its default is marked on its row (ms-changed)
      inputs.forEach(function (el) {
        var row = el.closest('.ms-row');
        if (row) row.classList.toggle('ms-changed', isModified(el));
      });
      var any = inputs.some(function (el) {
        return !el.closest('[hidden]') && isModified(el);
      });
      if (badge) setBadge(any ? 'warn' : 'ok', any ? 'modified' : 'default');
      if (ovr) ovr.hidden = !any;
      if (why) why.hidden = !(tick && tick.checked);
      if (reason) reason.required = !!(any && tick && tick.checked);
    }
    if (reset) reset.addEventListener('click', function () {
      inputs.forEach(function (el) {
        if (!el.disabled || el.dataset.msOff) el.value = el.dataset.default || '';
      });
      syncSeason();
      if (tick) tick.checked = false;
      if (reason) reason.value = '';
      update();
    });
    // open or closed as the user left it this session; the server opens
    // it only on the page after a refusal over its settings
    // (data-refused), which a close stored earlier never undoes. A click
    // on the summary is the user's choice, never a page render
    var memo = 'ms-open:' + location.pathname + ':' + (box.id || '');
    try {
      var left = sessionStorage.getItem(memo);
      if (left === '1') box.open = true;
      else if (left === '0' && !box.hasAttribute('data-refused')) box.open = false;
    } catch (e) {}
    var sum = box.querySelector('summary');
    if (sum) sum.addEventListener('click', function () {
      setTimeout(function () {
        try { sessionStorage.setItem(memo, box.open ? '1' : '0'); } catch (e) {}
      }, 0);
    });
    if (form) {
      // a run forgets the choice: the page after it (and its automatic
      // reload when the run ends) shows the panel as the server renders it
      form.addEventListener('submit', function () {
        try { sessionStorage.removeItem(memo); } catch (e) {}
      });
      // a value the browser refuses inside the closed panel: open it and
      // show the browser's message there (a field in a closed panel shows
      // none, so Run models seemed to do nothing)
      var reporting = false;
      form.addEventListener('invalid', function (e) {
        var el = e.target;
        if (!box.contains(el) || (box.open && !reporting)) return;
        e.preventDefault();
        if (reporting) return;
        reporting = true;
        box.open = true;
        setTimeout(function () {
          reporting = false;
          try { el.reportValidity(); } catch (x) {}
        }, 0);
      }, true);
    }
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
