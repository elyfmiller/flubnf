/* The upload box (templates/_dataset_upload.html), wherever it is placed.
   A file dropped on the zone or chosen in its input is checked at once
   (POST /data/datasets/check, nothing stored) and the result box shows
   every problem, a column mapping, or a preview; changing the kind, the
   target or a column checks again. The name follows the file's name until
   typed; the kind shows what the values say until picked by hand (and is
   posted as "from the values", kind_auto=1, until then). The preview's buttons submit the form itself (POST /data/datasets),
   which stores the file and opens it where it is needed. A closed <details>
   around the box opens when a file is dragged over it. Files dropped
   elsewhere on the page are ignored instead of replacing the page. */
(function () {
  'use strict';

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function hasFiles(e) {
    var t = e.dataTransfer && e.dataTransfer.types;
    return !!t && Array.prototype.indexOf.call(t, 'Files') >= 0;
  }

  function init(form) {
    var input = form.querySelector('input[type=file]');
    var zone = form.querySelector('[data-drop]');
    var name = form.querySelector('[data-name]');
    var kind = form.querySelector('[data-kind]');
    var auto = form.querySelector('[data-kind-auto]');
    var out = form.querySelector('[data-result]');
    var go = form.querySelector('.dsup-go button');
    var fold = form.closest('details');
    var dropped = null;          // a dropped file the input could not take
    var autoName = '';           // the name last filled in from a file name
    var kindChosen = false;      // the kind was picked by hand
    var seq = 0;
    if (!input || !zone || !out || form.dataset.dsupReady) return;
    form.dataset.dsupReady = '1';
    form.classList.add('js');
    if (go) go.disabled = true;  // the preview's buttons submit instead

    function current() {
      return (input.files && input.files[0]) || dropped;
    }

    function stem(n) {
      return n.replace(/^.*[\\/]/, '').replace(/\.[^.]*$/, '').slice(0, 80);
    }

    function picked(f) {
      if (!f) return;
      if (name && (!name.value || name.value === autoName)) {
        autoName = stem(f.name);
        name.value = autoName;
      }
      if (kind && !kindChosen) {
        kind.value = '';
        if (auto) auto.value = '';
      }
      out.innerHTML = '';        // a new file: forget the old target/columns
      check();
    }

    function check() {
      var f = current();
      if (!f) return;
      var fd = new FormData(form);
      var cur = fd.get('file');
      if (!cur || !cur.name) fd.set('file', f, f.name);
      fd.delete('next');
      var my = ++seq;
      form.setAttribute('aria-busy', 'true');
      out.innerHTML = '<p class="hint">Checking ' + esc(f.name) + '…</p>';
      fetch('/data/datasets/check?where=' + encodeURIComponent(
        form.dataset.where || 'data'), {method: 'POST', body: fd,
        headers: {'Accept': 'application/json'}})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (my !== seq) return;          // a newer check superseded this
          out.innerHTML = j.html || '';
          if (kind && !kindChosen && j.inferred_kind) {
            kind.value = j.inferred_kind;
            if (auto) auto.value = '1';
          }
        })
        .catch(function () {
          if (my !== seq) return;
          out.innerHTML = '<p class="bad">The file could not be checked; '
            + 'choose it again.</p>';
        })
        .then(function () {
          if (my === seq) form.removeAttribute('aria-busy');
        });
    }

    input.addEventListener('change', function () {
      dropped = null;
      picked(input.files && input.files[0]);
    });
    if (kind) kind.addEventListener('change', function () {
      kindChosen = true;
      if (auto) auto.value = '';
      check();
    });
    if (name) name.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); check(); }
    });
    out.addEventListener('change', function (e) {
      if (e.target && e.target.hasAttribute('data-recheck')) check();
    });

    // drag and drop: the zone, and a closed fold around the box
    function over(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (fold && !fold.open) fold.open = true;
      zone.classList.add('over');
    }
    function leave() { zone.classList.remove('over'); }
    [zone, fold].forEach(function (el) {
      if (!el) return;
      el.addEventListener('dragenter', over);
      el.addEventListener('dragover', over);
      el.addEventListener('dragleave', leave);
      el.addEventListener('drop', function (e) {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.stopPropagation();
        leave();
        var fs = e.dataTransfer.files;
        if (!fs || !fs.length) return;
        dropped = null;
        try { input.files = fs; } catch (err) { /* older engines */ }
        if (!input.files || !input.files.length) {
          dropped = fs[0];
          input.required = false;  // or validation would stop the submit
        }
        picked(fs[0]);
      });
    });

    // a dropped file the input could not hold is posted by hand
    form.addEventListener('submit', function (e) {
      if ((input.files && input.files.length) || !dropped) return;
      e.preventDefault();
      var fd = new FormData(form);
      fd.set('file', dropped, dropped.name);
      var sub = e.submitter;
      if (sub && sub.name) fd.set(sub.name, sub.value);
      fetch(form.action, {method: 'POST', body: fd})
        .then(function (r) {
          if (r.redirected) { location.href = r.url; return null; }
          return r.text();
        })
        .then(function (html) {
          if (html === null) return;
          document.open(); document.write(html); document.close();
        });
    });
  }

  // a file dropped outside a zone must not replace the console
  if (!window.__dsupGuard) {
    window.__dsupGuard = true;
    window.addEventListener('dragover', function (e) {
      if (hasFiles(e)) e.preventDefault();
    });
    window.addEventListener('drop', function (e) {
      if (hasFiles(e)) e.preventDefault();
    });
  }

  function start() {
    document.querySelectorAll('form[data-dsup]').forEach(init);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
