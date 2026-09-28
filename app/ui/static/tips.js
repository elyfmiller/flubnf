/* The "?" explainers (templates/_tips.html; styles in nau.css ".tip").
   CSS shows a tip on hover and keyboard focus; this adds click/tap
   toggling (WebKit, and so the pywebview window, never focuses a clicked
   button) and Escape to dismiss, and places the tooltip. The box is
   position:fixed, so a card's overflow never clips it: it sits under its
   button (above when there is no room below), inside the viewport. */
(function () {
  function place(t) {
    var btn = t.querySelector('.tipbtn'), b = t.querySelector('.tipbox');
    if (!btn || !b) return;
    var br = btn.getBoundingClientRect(),
        W = document.documentElement.clientWidth, H = window.innerHeight,
        w = b.offsetWidth, h = b.offsetHeight;
    var x = br.left + br.width / 2 - w / 2;
    x = Math.max(8, Math.min(x, W - 8 - w));
    var y = br.bottom + 6;
    if (y + h > H - 8) {
      // no room below: above, or (room on neither side) as low as fits
      y = br.top - 6 - h > 8 ? br.top - 6 - h : Math.max(8, H - 8 - h);
    }
    b.style.left = Math.round(x) + 'px';
    b.style.top = Math.round(y) + 'px';
  }
  function tipOf(e) {
    return e.target && e.target.closest ? e.target.closest('.tip') : null;
  }
  function closeAll(except) {
    document.querySelectorAll('.tip.open').forEach(function (t) {
      if (t !== except) t.classList.remove('open');
    });
  }
  document.addEventListener('mouseover', function (e) {
    var t = tipOf(e);
    // the pointer coming back to a dismissed tip shows it again
    if (t && !(e.relatedTarget && t.contains(e.relatedTarget)))
      t.classList.remove('dismissed');
    // a reason button's wrapper (its disabled button passes the pointer
    // through, ui-kit.css): its reason shows on hover too
    var r = !t && e.target && e.target.closest ? e.target.closest('.uk-reason') : null;
    if (r) t = r.querySelector('.uk-reason-tip .tip');
    if (t) place(t);
  });
  document.addEventListener('focusin', function (e) {
    var t = tipOf(e); if (t) { t.classList.remove('dismissed'); place(t); }
  });
  document.addEventListener('focusout', function (e) {
    var t = tipOf(e); if (t) t.classList.remove('dismissed');
  });
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.tipbtn') : null;
    var t = btn ? btn.parentNode : null;
    closeAll(t);
    if (!t) return;
    e.preventDefault();                  // a tip inside a <label> or <summary>
    // a second click hides it, though the button keeps focus and hover
    var on = !t.classList.contains('open');
    t.classList.toggle('open', on);
    t.classList.toggle('dismissed', !on);
    place(t);
  });
  // Escape hides a shown tip and goes no further, so the menu or dialog
  // the tip sits in stays open (a second Escape closes that). Capture on
  // window: before any page's own Escape handler
  window.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var shown = !!document.querySelector('.tip.open');
    closeAll(null);
    var a = document.activeElement;
    if (a && a.classList && a.classList.contains('tipbtn') &&
        !a.parentNode.classList.contains('dismissed')) {
      a.parentNode.classList.add('dismissed');
      shown = true;
    }
    if (shown) e.stopPropagation();
  }, true);
  // a shown tip follows its button on scroll and resize
  function replace() {
    document.querySelectorAll('.tip.open, .tip:focus-within, .tip:hover')
      .forEach(place);
  }
  window.addEventListener('scroll', replace, true);
  window.addEventListener('resize', replace);
})();

/* The UI kit's behavior (templates/_tips.html; styles in static/ui-kit.css;
   docs/UI-KIT.md). Toggletips: the "i" button opens its panel on click or
   Enter, keeps aria-expanded true while it is open, and places the panel
   under it inside the viewport (position:fixed, as a tooltip is, so a
   card's overflow never clips it); Escape, a click outside or focus
   leaving it closes it. Without this script a panel shows while focus is
   inside its toggletip (ui-kit.css, html:not(.uk-js)).
   window.FluBNFUI builds kit markup for page scripts: icon(name, label),
   badge(state, text), tip(id, label, text), alert(kind, text, title, tip,
   live) and progress(label, value, max, text, id), and updates it in
   place: setBadge(el, state, text), setReason(button, reason) and
   setProgress(el, value, max, text); the icon table matches the ICONS set
   in _tips.html (a test holds them equal). Loaded deferred: call it from
   handlers, not while the page parses. ES5. */
(function () {
  var root = document.documentElement;
  if (root.classList) root.classList.add('uk-js');

  function ttOf(el) {
    return el && el.closest ? el.closest('.uk-tt') : null;
  }
  function parts(w) {
    return {btn: w.querySelector('.uk-tt-btn'), pop: w.querySelector('.uk-tt-pop')};
  }
  // the panel under its button (above when there is no room below),
  // inside the viewport; the same rule as a tooltip
  function place(w) {
    var p = parts(w);
    if (!p.btn || !p.pop) return;
    p.pop.style.position = 'fixed';
    var br = p.btn.getBoundingClientRect(),
        W = document.documentElement.clientWidth, H = window.innerHeight,
        wd = p.pop.offsetWidth, h = p.pop.offsetHeight;
    var x = br.left + br.width / 2 - wd / 2;
    x = Math.max(8, Math.min(x, W - 8 - wd));
    var y = br.bottom + 6;
    if (y + h > H - 8) {
      // no room below: above, or (room on neither side) as low as fits;
      // a panel taller than the window scrolls (ui-kit.css max-height)
      y = br.top - 6 - h > 8 ? br.top - 6 - h : Math.max(8, H - 8 - h);
    }
    p.pop.style.left = Math.round(x) + 'px';
    p.pop.style.top = Math.round(y) + 'px';
  }
  function close(w, refocus) {
    var p = parts(w);
    w.classList.remove('open');
    if (p.btn) p.btn.setAttribute('aria-expanded', 'false');
    if (p.pop) { p.pop.style.position = ''; p.pop.style.left = ''; p.pop.style.top = ''; }
    if (refocus && p.btn) p.btn.focus();
  }
  function closeAll(except) {
    document.querySelectorAll('.uk-tt.open').forEach(function (w) {
      if (w !== except) close(w, false);
    });
  }
  function open(w) {
    closeAll(w);
    w.classList.add('open');
    var p = parts(w);
    if (p.btn) p.btn.setAttribute('aria-expanded', 'true');
    place(w);
  }
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('.uk-tt-btn') : null;
    if (btn) {
      var w = ttOf(btn);
      e.preventDefault();                // a toggletip inside a <summary>
      if (w.classList.contains('open')) close(w, false); else open(w);
      return;
    }
    closeAll(ttOf(e.target));            // a click inside a panel keeps it
  });
  // Escape closes an open panel and goes no further (as a tooltip's does)
  window.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var w = ttOf(document.activeElement),
        any = !!document.querySelector('.uk-tt.open');
    closeAll(w);
    if (w && w.classList.contains('open')) close(w, true);
    if (any) e.stopPropagation();
  }, true);
  // focus moving out of a toggletip (Tab past its last link) closes it
  document.addEventListener('focusout', function (e) {
    var w = ttOf(e.target);
    if (w && w.classList.contains('open') && e.relatedTarget &&
        !w.contains(e.relatedTarget)) close(w, false);
  });
  function replace() { document.querySelectorAll('.uk-tt.open').forEach(place); }
  window.addEventListener('scroll', replace, true);
  window.addEventListener('resize', replace);

  // ---- markup builders for page scripts ----
  var ICONS = {
    info: '<circle cx="8" cy="8" r="6.25"/><path d="M8 7.3v4"/><circle cx="8" cy="4.9" r=".95" fill="currentColor" stroke="none"/>',
    warning: '<path d="M8 1.9 14.6 13.5H1.4Z"/><path d="M8 6.1v3.4"/><circle cx="8" cy="11.5" r=".95" fill="currentColor" stroke="none"/>',
    error: '<path d="M5.4 1.75h5.2l3.65 3.65v5.2l-3.65 3.65H5.4L1.75 10.6V5.4Z"/><path d="M8 4.7v3.9"/><circle cx="8" cy="11" r=".95" fill="currentColor" stroke="none"/>',
    check: '<circle cx="8" cy="8" r="6.25"/><path d="m5.1 8.3 2 2 3.8-4.2"/>',
    clock: '<circle cx="8" cy="8" r="6.25"/><path d="M8 4.5V8l2.4 1.6"/>',
    download: '<path d="M8 2.1v8.2"/><path d="m4.8 7.2 3.2 3.2 3.2-3.2"/><path d="M2.4 11.4v2.2h11.2v-2.2"/>',
    upload: '<path d="M8 10.3V2.1"/><path d="m4.8 5.3 3.2-3.2 3.2 3.2"/><path d="M2.4 11.4v2.2h11.2v-2.2"/>',
    folder: '<path d="M1.9 4.3c0-.6.4-1 1-1h3.3l1.5 1.7h5.4c.6 0 1 .4 1 1v6.8c0 .6-.4 1-1 1H2.9c-.6 0-1-.4-1-1Z"/>',
    external: '<path d="M12.7 9.3v3.6c0 .6-.4 1-1 1H3.1c-.6 0-1-.4-1-1V4.3c0-.6.4-1 1-1h3.6"/><path d="M9.3 2.1h4.6v4.6"/><path d="M13.9 2.1 7.5 8.5"/>',
    lock: '<rect x="3" y="7" width="10" height="7" rx="1.4"/><path d="M5.3 7V5.1a2.7 2.7 0 0 1 5.4 0V7"/>',
    calendar: '<rect x="2" y="3.2" width="12" height="10.8" rx="1.4"/><path d="M2 6.7h12M5.2 1.8v2.8M10.8 1.8v2.8"/>',
    refresh: '<path d="M13.3 8a5.3 5.3 0 1 1-1.55-3.75"/><path d="M12.3 1.7v2.9H9.4"/>',
    dot: '<circle cx="8" cy="8" r="3.2" fill="currentColor" stroke="none"/>',
    close: '<path d="m4.3 4.3 7.4 7.4M11.7 4.3l-7.4 7.4"/>'
  };
  var STATE_ICONS = {ok: 'check', warn: 'warning', error: 'error',
                     info: 'info', neutral: 'dot', pending: 'clock'};
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function icon(name, label) {
    return '<svg class="uk-icon" viewBox="0 0 16 16" width="1em" height="1em"'
      + ' fill="none" stroke="currentColor" stroke-width="1.5"'
      + ' stroke-linecap="round" stroke-linejoin="round"'
      + (label ? ' role="img" aria-label="' + esc(label) + '"' : ' aria-hidden="true"')
      + ' focusable="false">' + (ICONS[name] || '') + '</svg>';
  }
  function badgeInner(state, text) {
    return icon(STATE_ICONS[state] || 'dot')
      + '<span class="uk-badge-t">' + esc(text) + '</span>';
  }
  function badge(state, text) {
    return '<span class="uk-badge uk-badge--' + esc(state) + '" data-state="'
      + esc(state) + '">' + badgeInner(state, text) + '</span>';
  }
  // an existing badge (tips.badge with an id) takes a new state and word
  function setBadge(el, state, text) {
    if (!el) return;
    el.className = 'uk-badge uk-badge--' + state;
    el.setAttribute('data-state', state);
    el.innerHTML = badgeInner(state, text);
  }
  // a reason button (tips.reason_button): a reason disables it and shows
  // the "?" with that reason; null enables it and hides the "?"
  function setReason(btn, reason) {
    if (!btn) return;
    var id = btn.getAttribute('data-uk-reason'),
        wrap = btn.parentNode ? btn.parentNode.querySelector('.uk-reason-tip') : null,
        box = id ? document.getElementById('tip-' + id) : null;
    btn.disabled = !!reason;
    if (reason) {
      if (id) btn.setAttribute('aria-describedby', 'tip-' + id);
      if (box) box.textContent = reason;
    } else {
      btn.removeAttribute('aria-describedby');
    }
    if (wrap) wrap.hidden = !reason;
  }
  // tips.tip's markup: the "?" and its tooltip (the text is escaped)
  function tip(id, label, text) {
    return '<span class="tip"><button type="button" class="tipbtn" aria-label="About '
      + esc(label) + '" aria-describedby="tip-' + esc(id) + '">?</button>'
      + '<span class="tipbox" role="tooltip" id="tip-' + esc(id) + '">'
      + esc(text) + '</span></span>';
  }
  // tips.alert's markup. kind: error, warn, info or ok; title: a bold lead;
  // tip: [id, text] for its "?"; live: the role, by kind when undefined
  // (error: alert, else status), '' for none (a live region holds it)
  function alert(kind, text, title, tipIdText, live) {
    var icons = {error: 'error', warn: 'warning', info: 'info', ok: 'check'},
        role = live === undefined ? (kind === 'error' ? 'alert' : 'status') : live,
        name = String(title || text || '').toLowerCase().replace(/[ .:]+$/, '');
    return '<div class="uk-alert uk-alert--' + esc(kind) + '"'
      + (role ? ' role="' + esc(role) + '"' : '') + '>' + icon(icons[kind] || 'info')
      + '<span class="uk-alert-text">'
      + (title ? '<strong>' + esc(title) + '</strong>' + (text ? ' ' : '') : '')
      + esc(text || '')
      + (tipIdText ? ' ' + tip(tipIdText[0], name, tipIdText[1]) : '')
      + '</span></div>';
  }
  // tips.progress's markup; value null (or undefined) is work without an
  // honest denominator: the bar slides. Without an id the bar is named by
  // aria-label
  function progress(label, value, max, text, id) {
    var busy = value === null || value === undefined, m = max || 100,
        pct = busy ? 0 : Math.max(0, Math.min(100, 100 * value / m));
    return '<div class="uk-progress' + (busy ? ' uk-progress--busy' : '') + '"'
      + (id ? ' id="' + esc(id) + '"' : '') + '><div class="uk-progress-head">'
      + '<span class="uk-progress-label"' + (id ? ' id="' + esc(id) + '-l"' : '') + '>'
      + esc(label) + '</span>'
      + (text ? '<span class="uk-progress-val">' + esc(text) + '</span>' : '')
      + '</div><div class="uk-progress-track" role="progressbar"'
      + (id ? ' aria-labelledby="' + esc(id) + '-l"' : ' aria-label="' + esc(label) + '"')
      + (busy ? '' : ' aria-valuemin="0" aria-valuemax="' + m + '" aria-valuenow="' + value + '"')
      + (text ? ' aria-valuetext="' + esc(text) + '"' : '') + '>'
      + '<div class="uk-progress-fill"' + (busy ? '' : ' style="width:' + pct + '%"')
      + '></div></div></div>';
  }
  // an existing progress bar (tips.progress) moves: a number fills it to
  // value/max, null makes it slide, undefined leaves the fill; text (when
  // given) is the readout beside the label
  function setProgress(el, value, max, text) {
    if (!el) return;
    var track = el.querySelector('[role=progressbar]'),
        fill = el.querySelector('.uk-progress-fill'),
        m = max || 100;
    if (value === null) {
      el.classList.add('uk-progress--busy');
      if (fill) fill.style.width = '';
      if (track) {
        track.removeAttribute('aria-valuenow');
        track.removeAttribute('aria-valuemin');
        track.removeAttribute('aria-valuemax');
      }
    } else if (typeof value === 'number') {
      el.classList.remove('uk-progress--busy');
      if (fill) fill.style.width = Math.max(0, Math.min(100, 100 * value / m)) + '%';
      if (track) {
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', String(m));
        track.setAttribute('aria-valuenow', String(Math.round(value)));
      }
    }
    if (text !== undefined && text !== null) {
      var v = el.querySelector('.uk-progress-val');
      if (!v) {
        var head = el.querySelector('.uk-progress-head');
        if (head) {
          v = document.createElement('span');
          v.className = 'uk-progress-val';
          head.appendChild(v);
        }
      }
      if (v) v.textContent = text;
      if (track) track.setAttribute('aria-valuetext', text);
    }
  }
  window.FluBNFUI = {icon: icon, badge: badge, setBadge: setBadge,
                     setReason: setReason, esc: esc, tip: tip, alert: alert,
                     progress: progress, setProgress: setProgress};
})();
