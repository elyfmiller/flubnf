/* The upload box (templates/_dataset_upload.html), wherever it is placed.
   A file dropped on the zone or chosen in its input is checked at once
   (POST /data/datasets/check, nothing stored) and the result box shows
   every problem, a column mapping, or a preview; changing the kind, the
   target or a column checks again. Several files (chosen together, dropped
   together, or a folder, chosen by the box's folder link where the
   browser offers one, or dropped) are checked together as one dataset's
   snapshots, one file per as_of; a folder gives its CSV, TSV and TXT
   files, each posted with its folder path so the name can be the
   folder's. The name follows the file's name (with
   the chosen target of a file that holds several) until typed; the kind
   shows what the values say until picked by hand (and is posted as "from
   the values", kind_auto=1, until then), back to "from the values" when a
   re-check finds they say nothing, and new files forget a kind picked
   for the last ones. A column or
   target select inside the result keeps the focus across its re-check:
   the result stays up (dimmed) and the same select is focused in the new
   one. A short status line (role=status) says what the check found; the
   result itself is not a live region, so it is not read out each time.
   The preview's buttons submit the form itself (POST /data/datasets),
   which stores the files and opens them where they are needed. A closed
   <details> around the box opens when a file is dragged over it. Files
   dropped elsewhere on the page are ignored instead of replacing the
   page. */
(function () {
  'use strict';

  var TABLES = /\.(csv|tsv|txt)$/i;

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function hasFiles(e) {
    var t = e.dataTransfer && e.dataTransfer.types;
    return !!t && Array.prototype.indexOf.call(t, 'Files') >= 0;
  }

  function list(fs) {
    return fs ? Array.prototype.slice.call(fs) : [];
  }

  // a file's name with its folder, when it came from one
  function pathOf(f) {
    return f.flubnfPath || f.webkitRelativePath || f.name;
  }

  // a dropped folder's files (walked to any depth), or null when nothing
  // dropped is a folder; entries must be taken while the drop event runs
  function folderFiles(dt) {
    var items = dt && dt.items, entries = [], i, en;
    if (!items || !items.length) return null;
    for (i = 0; i < items.length; i++) {
      en = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
      if (en) entries.push(en);
    }
    if (!entries.some(function (x) { return x.isDirectory; })) return null;
    function walk(en) {
      if (en.isFile) {
        return new Promise(function (res) {
          en.file(function (f) {
            f.flubnfPath = en.fullPath.replace(/^\//, '');
            res([f]);
          }, function () { res([]); });
        });
      }
      if (!en.isDirectory) return Promise.resolve([]);
      var reader = en.createReader(), all = [];
      return new Promise(function (res) {
        (function more() {
          reader.readEntries(function (batch) {
            if (batch.length) { all.push.apply(all, batch); more(); return; }
            Promise.all(all.map(walk)).then(function (xs) {
              res([].concat.apply([], xs));
            });
          }, function () { res([]); });
        })();
      });
    }
    return Promise.all(entries.map(walk)).then(function (xs) {
      return [].concat.apply([], xs).filter(function (f) {
        return TABLES.test(f.name);
      }).sort(function (a, b) {
        return pathOf(a) < pathOf(b) ? -1 : pathOf(a) > pathOf(b) ? 1 : 0;
      });
    });
  }

  function init(form) {
    var input = form.querySelector('input[type=file]');
    var folder = form.querySelector('[data-folder]');
    var zone = form.querySelector('[data-drop]');
    var name = form.querySelector('[data-name]');
    var kind = form.querySelector('[data-kind]');
    var auto = form.querySelector('[data-kind-auto]');
    var out = form.querySelector('[data-result]');
    var status = form.querySelector('[data-dsup-status]');
    var go = form.querySelector('.dsup-go button');
    var fold = form.closest('details');
    var dropped = null;          // files the input could not take
    var autoName = '';           // the name last filled in from a file name
    var kindChosen = false;      // the kind was picked by hand (this file)
    var seq = 0;
    if (!input || !zone || !out || form.dataset.dsupReady) return;
    form.dataset.dsupReady = '1';
    form.classList.add('js');
    if (go) go.disabled = true;  // the preview's buttons submit instead
    // a folder of snapshots, where the browser can pick one
    if (folder && 'webkitdirectory' in folder) {
      var wrap = form.querySelector('[data-folder-wrap]');
      if (wrap) wrap.hidden = false;
    }

    function current() {
      if (dropped && dropped.length) return dropped;
      return list(input.files);
    }

    function stem(n) {
      return n.replace(/^.*[\\/]/, '').replace(/\.[^.]*$/, '').slice(0, 80);
    }

    // what the zone says was chosen: a file's name, or how many
    function said(fs) {
      if (fs.length === 1) return fs[0].name;
      var p = pathOf(fs[0]), dir = p.indexOf('/') > 0 ? p.split('/')[0] : '';
      return fs.length + ' files' + (dir ? ' from ' + dir : '');
    }

    var shown = form.querySelector('[data-file]');
    function picked(fs) {
      if (!fs || !fs.length) return;
      form.classList.add('has-file');
      if (shown) shown.textContent = said(fs);
      if (name && (!name.value || name.value === autoName)) {
        // several files: the check answers with the folder's name
        autoName = fs.length === 1 ? stem(fs[0].name) : '';
        name.value = autoName;
      }
      if (kind) {                // new files: their own values decide
        kindChosen = false;
        kind.value = '';
        if (auto) auto.value = '';
      }
      out.innerHTML = '';        // new files: forget the old target/columns
      check();
    }

    // put files in the input when it can hold them (a native submit then
    // posts them), else keep them for the submit below
    function hold(fs) {
      dropped = null;
      try {
        if (typeof DataTransfer !== 'undefined') {
          var dt = new DataTransfer();
          fs.forEach(function (f) { dt.items.add(f); });
          input.files = dt.files;
        } else {
          input.files = fs;
        }
      } catch (err) { /* older engines */ }
      if (!input.files || input.files.length !== fs.length) {
        dropped = fs;
        input.required = false;  // or validation would stop the submit
      }
    }

    function say(text) {
      if (status) status.textContent = text;
    }

    // the control inside the result that had the focus, found again in
    // the new result by its id; else its first select or action button
    function refocus(id) {
      var el = id ? document.getElementById(id) : null;
      if (!el || !out.contains(el)) {
        el = out.querySelector('select, .dsup-actions button');
      }
      if (!el) {
        out.setAttribute('tabindex', '-1');
        el = out;
      }
      el.focus();
    }

    // the form's fields with the chosen files (several: each under its
    // folder path)
    function body(fs) {
      var fd = new FormData(form);
      if (fs.length === 1) {
        var cur = fd.get('file');
        if (!cur || !cur.name) fd.set('file', fs[0], fs[0].name);
      } else {
        fd.delete('file');
        fs.forEach(function (f) { fd.append('file', f, pathOf(f)); });
      }
      return fd;
    }

    function check() {
      var fs = current();
      if (!fs.length) return;
      var fd = body(fs);
      fd.delete('next');
      var my = ++seq;
      var act = document.activeElement;
      var keep = act && act !== out && out.contains(act) ? act.id : null;
      var what = said(fs);
      form.setAttribute('aria-busy', 'true');
      say('Checking ' + what + '…');
      if (keep === null) {
        out.innerHTML = '<p class="hint">Checking ' + esc(what) + '…</p>';
      }
      fetch('/data/datasets/check?where=' + encodeURIComponent(
        form.dataset.where || 'data'), {method: 'POST', body: fd,
        headers: {'Accept': 'application/json'}})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (my !== seq) return;          // a newer check superseded this
          out.innerHTML = j.html || '';
          if (keep !== null) refocus(keep);
          if (name && j.name && (!name.value || name.value === autoName)) {
            autoName = j.name;     // the file's name, with its target
            name.value = autoName;
          }
          if (kind && !kindChosen) {   // what these values say, or nothing
            kind.value = j.inferred_kind || '';
            if (auto) auto.value = j.inferred_kind ? '1' : '';
          }
          say(j.status || '');
        })
        .catch(function () {
          if (my !== seq) return;
          var msg = 'The files could not be checked; choose them again.';
          if (fs.length === 1) {
            msg = 'The file could not be checked; choose it again.';
          }
          out.innerHTML = '<p class="bad">' + msg + '</p>';
          if (keep !== null) refocus(null);
          say(msg);
        })
        .then(function () {
          if (my === seq) form.removeAttribute('aria-busy');
        });
    }

    input.addEventListener('change', function () {
      dropped = null;
      picked(list(input.files));
    });
    if (folder) folder.addEventListener('change', function () {
      var fs = list(folder.files).filter(function (f) {
        return TABLES.test(f.name);
      });
      folder.value = '';
      if (!fs.length) {
        say('That folder holds no CSV, TSV or TXT files.');
        out.innerHTML = '<p class="bad">That folder holds no CSV, TSV or '
          + 'TXT files.</p>';
        return;
      }
      hold(fs);
      picked(fs);
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
        var walked = folderFiles(e.dataTransfer);
        if (walked) {                // a folder (or several): its tables
          say('Reading the folder…');
          walked.then(function (fs) {
            if (!fs.length) {
              say('That folder holds no CSV, TSV or TXT files.');
              return;
            }
            hold(fs);
            picked(fs);
          });
          return;
        }
        var fs = e.dataTransfer.files;
        if (!fs || !fs.length) return;
        dropped = null;
        try { input.files = fs; } catch (err) { /* older engines */ }
        if (!input.files || !input.files.length) {
          dropped = list(fs);
          input.required = false;  // or validation would stop the submit
        }
        picked(list(fs));
      });
    });

    // files the input could not hold are posted by hand
    form.addEventListener('submit', function (e) {
      if (!dropped || !dropped.length) return;
      e.preventDefault();
      var fd = body(dropped);
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
