/* FluBNF sandbox code editor (bngl-editor.js)

   The three sandbox files get a small editor with no dependencies and no
   build step. Each textarea.code-editor is wrapped in a div.ce: a line
   number gutter on the left, a coloured copy of the text under the
   textarea, and a status line below. The textarea's own text is
   transparent, so the coloured copy shows through while the caret, the
   selection, undo and the keyboard stay the browser's own. The textarea
   remains the form field: if this script does not run, the page posts
   the same plain textareas.

   Keys: Tab inserts two spaces (or indents the selected lines), Shift+Tab
   outdents, Enter keeps the indentation, Ctrl+/ or Cmd+/ toggles a #
   comment on the selected lines, Escape then Tab leaves the editor.

   The text functions (tokenize, highlight, bracketMatch, indentLines,
   commentLines, newlineIndent, lineCol) are pure and exported on
   BnglEditor, so the tests run them under JavaScriptCore with no DOM.
   Colours come from the page's tokens through bngl-editor.css, so the
   editor follows the theme; themechange and fontsizechange re-render. */
(function (root) {
  'use strict';

  // ------------------------------------------------------------ grammar
  var ID = '[A-Za-z_][A-Za-z0-9_]*';
  var NUM = '(?:\\b\\d+\\.?\\d*|\\B\\.\\d+)(?:[eE][+-]?\\d+)?';
  var BLOCKS = 'model|parameters|molecule[ \\t]+types|seed[ \\t]+species|' +
    'observables|functions|reaction[ \\t]+rules|actions|compartments|' +
    'energy[ \\t]+patterns|population[ \\t]+maps';
  var ACTIONS = 'generate_network|simulate_ode|simulate_ssa|simulate_nf|' +
    'simulate|visualize|saveConcentrations|resetConcentrations|' +
    'setConcentration|setParameter|writeSBML|writeXML|writeNetwork|' +
    'readFile|parameter_scan';
  var VARS = 'uniform_var|loguniform_var|normal_var|lognormal_var';

  // One regex per language. cls maps each capture group to a token class;
  // an empty class is a plain word, matched so the digits inside a name
  // are not read as a number. Comments come first, so nothing inside one
  // is coloured.
  var GRAMMAR = {
    bngl: {
      re: new RegExp('(#[^\\n]*)' +
        '|\\b((?:begin|end)[ \\t]+(?:' + BLOCKS + '))\\b' +
        '|\\b(begin|end)\\b' +
        '|(<->|->)' +
        '|\\b(' + ACTIONS + ')(?=[ \\t]*\\()' +
        '|\\b(' + ID + '__FREE)\\b' +
        '|\\b(' + ID + ')(?=[ \\t]*\\()' +
        '|\\b(' + ID + ')' +
        '|(' + NUM + ')', 'g'),
      cls: [null, 'c', 'k', 'k', 'r', 'a', 'f', 'fn', '', 'n']},
    exp: {
      re: new RegExp('(#[^\\n]*)|\\b(' + ID + ')|(' + NUM + ')', 'g'),
      cls: [null, 'c', '', 'n']},
    conf: {
      re: new RegExp('(#[^\\n]*)' +
        '|\\b(' + VARS + ')\\b' +
        '|\\b(' + ID + ')(?=[ \\t]*=)' +
        '|\\b(' + ID + '__FREE)\\b' +
        '|\\b(' + ID + ')' +
        '|(' + NUM + ')', 'g'),
      cls: [null, 'c', 'v', 'key', 'f', '', 'n']}
  };

  // [start, end, class] for every coloured token of text in lang
  function tokenize(text, lang) {
    var g = GRAMMAR[lang] || GRAMMAR.exp, re = g.re, out = [], m, i;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      if (!m[0]) { re.lastIndex++; continue; }
      i = 1;
      while (i < m.length && m[i] === undefined) i++;
      if (g.cls[i]) out.push([m.index, m.index + m[0].length, g.cls[i]]);
    }
    return out;
  }

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function span(s, cls) {
    if (!s) return '';
    return cls ? '<span class="ce-' + cls + '">' + esc(s) + '</span>' : esc(s);
  }

  // one run of text as HTML, split around the marked bracket positions
  function run(text, s, e, cls, brk) {
    var html = '', i = s, j, p;
    if (brk) {
      for (j = 0; j < brk.pos.length; j++) {
        p = brk.pos[j];
        if (p >= i && p < e) {
          html += span(text.slice(i, p), cls);
          html += span(text.charAt(p), brk.ok ? 'brk' : 'brk-bad');
          i = p + 1;
        }
      }
    }
    return html + span(text.slice(i, e), cls);
  }

  // the whole text as HTML; brk is bracketMatch's answer or null. A text
  // ending in a newline gets a trailing space so its empty last line has
  // a height, as it does in the textarea.
  function highlight(text, lang, brk) {
    var toks = tokenize(text, lang), html = '', pos = 0, i, t;
    for (i = 0; i < toks.length; i++) {
      t = toks[i];
      if (t[0] > pos) html += run(text, pos, t[0], '', brk);
      html += run(text, t[0], t[1], t[2], brk);
      pos = t[1];
    }
    if (pos < text.length) html += run(text, pos, text.length, '', brk);
    if (!text || text.charAt(text.length - 1) === '\n') html += ' ';
    return html;
  }

  // ----------------------------------------------------------- brackets
  var OPEN = '([{', CLOSE = ')]}';

  // true at every position inside a # comment (all three files use #)
  function commentMask(text) {
    var m = new Array(text.length), inC = false, i, ch;
    for (i = 0; i < text.length; i++) {
      ch = text.charAt(i);
      if (ch === '\n') inC = false;
      else if (ch === '#') inC = true;
      m[i] = inC;
    }
    return m;
  }

  // the bracket at the caret (the one before it first, then the one at
  // it) and its partner: {pos: [a, b], ok: true}, {pos: [a], ok: false}
  // for one with no partner, null when the caret is not at a bracket
  function bracketMatch(text, caret) {
    var mask = commentMask(text), p = -1, c, k, want, dir, depth = 0, i, ch;
    if (caret > 0 && !mask[caret - 1] && (OPEN + CLOSE).indexOf(text.charAt(caret - 1)) >= 0) p = caret - 1;
    else if (caret < text.length && !mask[caret] && (OPEN + CLOSE).indexOf(text.charAt(caret)) >= 0) p = caret;
    if (p < 0) return null;
    c = text.charAt(p);
    k = OPEN.indexOf(c);
    if (k >= 0) { want = CLOSE.charAt(k); dir = 1; }
    else { k = CLOSE.indexOf(c); want = OPEN.charAt(k); dir = -1; }
    for (i = p; i >= 0 && i < text.length; i += dir) {
      if (mask[i]) continue;
      ch = text.charAt(i);
      if (ch === c) depth++;
      else if (ch === want && --depth === 0) return {pos: dir > 0 ? [p, i] : [i, p], ok: true};
    }
    return {pos: [p], ok: false};
  }

  // --------------------------------------------------------- line edits
  // [from, to) of the whole lines the selection [s, e) touches; a
  // selection ending just after a newline does not take the next line
  function lineRange(text, s, e) {
    var a = s > 0 ? text.lastIndexOf('\n', s - 1) + 1 : 0;
    var last = (e > s && text.charAt(e - 1) === '\n') ? e - 1 : e;
    var b = text.indexOf('\n', last);
    return [a, b < 0 ? text.length : b];
  }

  // the replaced block and where the selection lands afterwards: the
  // start moves with the first line's change, the end with the total
  function finish(text, r, block, s, e, first, total) {
    var start = Math.max(r[0], s + first), end = Math.max(start, e + total);
    return {text: text.slice(0, r[0]) + block + text.slice(r[1]),
            from: r[0], to: r[1], block: block, start: start, end: end};
  }

  // two spaces in (or, outdent, up to two spaces or one tab out) of every
  // line the selection touches
  function indentLines(text, s, e, outdent) {
    var r = lineRange(text, s, e), lines = text.slice(r[0], r[1]).split('\n');
    var i, d, m, first = 0, total = 0;
    for (i = 0; i < lines.length; i++) {
      if (outdent) {
        m = /^(?: {1,2}|\t)/.exec(lines[i]);
        d = m ? -m[0].length : 0;
        lines[i] = lines[i].slice(-d);
      } else { d = 2; lines[i] = '  ' + lines[i]; }
      if (i === 0) first = d;
      total += d;
    }
    return finish(text, r, lines.join('\n'), s, e, first, total);
  }

  // add "# " after the indentation of every non-blank line the selection
  // touches, or, when every one of them is already a comment, remove it
  function commentLines(text, s, e) {
    var r = lineRange(text, s, e), lines = text.slice(r[0], r[1]).split('\n');
    var i, d, m, first = 0, total = 0, remove = true, any = false;
    for (i = 0; i < lines.length; i++) {
      if (!/\S/.test(lines[i])) continue;
      any = true;
      if (!/^\s*#/.test(lines[i])) remove = false;
    }
    remove = remove && any;
    for (i = 0; i < lines.length; i++) {
      d = 0;
      if (remove) {
        m = /^(\s*)#( ?)/.exec(lines[i]);
        if (m) { lines[i] = m[1] + lines[i].slice(m[0].length); d = m[1].length - m[0].length; }
      } else if (/\S/.test(lines[i]) || lines.length === 1) {
        m = /^\s*/.exec(lines[i])[0];
        lines[i] = m + '# ' + lines[i].slice(m.length);
        d = 2;
      }
      if (i === 0) first = d;
      total += d;
    }
    return finish(text, r, lines.join('\n'), s, e, first, total);
  }

  // what Enter inserts: a newline plus the current line's indentation up
  // to the caret
  function newlineIndent(text, caret) {
    var a = caret > 0 ? text.lastIndexOf('\n', caret - 1) + 1 : 0;
    return '\n' + /^[ \t]*/.exec(text.slice(a, caret))[0];
  }

  function lineCol(text, pos) {
    var before = text.slice(0, pos);
    return {line: before.split('\n').length, col: pos - before.lastIndexOf('\n')};
  }

  // ---------------------------------------------------------------- DOM
  var states = [];

  function el(tag, cls) { var e = document.createElement(tag); e.className = cls; return e; }

  function build(ta) {
    var lang = ta.getAttribute('data-lang') || 'bngl';
    var wrap = el('div', 'ce'), main = el('div', 'ce-main'), gutter = el('div', 'ce-gutter');
    var lines = el('div', 'ce-lines'), body = el('div', 'ce-body'), hl = el('div', 'ce-hl');
    var scroll = el('div', 'ce-scroll'), cur = el('div', 'ce-cur'), code = el('div', 'ce-code');
    var status = el('div', 'ce-status'), st;
    wrap.setAttribute('data-lang', lang);
    gutter.setAttribute('aria-hidden', 'true');
    hl.setAttribute('aria-hidden', 'true');
    gutter.appendChild(lines);
    scroll.appendChild(cur); scroll.appendChild(code); hl.appendChild(scroll);
    ta.parentNode.insertBefore(wrap, ta);
    body.appendChild(hl); body.appendChild(ta);
    main.appendChild(gutter); main.appendChild(body);
    wrap.appendChild(main); wrap.appendChild(status);
    ta.style.fontFamily = '';           // the inline monospace fallback yields to the editor's font
    ta.setAttribute('wrap', 'off');
    st = {ta: ta, lang: lang, wrap: wrap, gutter: gutter, lines: lines, hl: hl, scroll: scroll,
          cur: cur, code: code, status: status, n: 0, lh: 0, padTop: 0, tabOut: false,
          lastText: null, lastKey: '', curSpan: null, raf: 0};
    ta.ceState = st;
    wire(st); layout(st); render(st);
    return st;
  }

  function wire(st) {
    var ta = st.ta, tick = function () { schedule(st); };
    ta.addEventListener('input', function () { sync(st); schedule(st); });
    ta.addEventListener('scroll', function () { sync(st); });
    ta.addEventListener('keydown', function (ev) { onKey(st, ev); });
    ta.addEventListener('blur', function () { st.tabOut = false; schedule(st); });
    ['keyup', 'click', 'mouseup', 'focus', 'select', 'selectionchange'].forEach(function (n) {
      ta.addEventListener(n, tick);
    });
    document.addEventListener('selectionchange', function () {
      if (document.activeElement === ta) schedule(st);
    });
    if (root.ResizeObserver) new root.ResizeObserver(function () { layout(st); }).observe(ta);
  }

  // the coloured copy and the gutter follow the textarea's scroll
  function sync(st) {
    var ta = st.ta;
    st.scroll.style.transform = 'translate(' + (-ta.scrollLeft) + 'px,' + (-ta.scrollTop) + 'px)';
    st.lines.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
  }

  // metrics the overlay needs: the line height and padding for the
  // current line, and the textarea's client box (the scrollbars excluded)
  // for the overlay's size
  function layout(st) {
    var ta = st.ta, cs = root.getComputedStyle(ta), lh = parseFloat(cs.lineHeight);
    if (!lh || isNaN(lh)) lh = 1.5 * (parseFloat(cs.fontSize) || 14);
    st.lh = lh;
    st.padTop = parseFloat(cs.paddingTop) || 0;
    st.hl.style.width = ta.clientWidth + 'px';
    st.hl.style.height = ta.clientHeight + 'px';
    st.gutter.style.height = ta.clientHeight + 'px';
    st.cur.style.height = lh + 'px';
    st.cur.style.top = (st.padTop + (lineCol(ta.value, ta.selectionStart).line - 1) * lh) + 'px';
    sync(st);
  }

  function schedule(st) {
    if (st.raf) return;
    var go = function () { st.raf = 0; render(st); };
    st.raf = root.requestAnimationFrame ? root.requestAnimationFrame(go) : setTimeout(go, 0);
  }

  function render(st) {
    var ta = st.ta, text = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    var brk = s === e ? bracketMatch(text, s) : null;
    var key = brk ? brk.pos.join(',') + (brk.ok ? '' : '!') : '', n, i, h, lc, cur;
    if (text !== st.lastText || key !== st.lastKey) {
      st.code.innerHTML = highlight(text, st.lang, brk);
      st.lastText = text; st.lastKey = key;
    }
    n = text.split('\n').length;
    if (n !== st.n) {
      for (h = '', i = 1; i <= n; i++) h += (i > 1 ? '\n' : '') + '<span>' + i + '</span>';
      st.lines.innerHTML = h;
      st.n = n; st.curSpan = null;
      st.gutter.style.width = (String(n).length + 2) + 'ch';
      layout(st);
    }
    lc = lineCol(text, s);
    cur = st.lines.children[lc.line - 1] || null;
    if (cur !== st.curSpan) {
      if (st.curSpan) st.curSpan.className = '';
      if (cur) cur.className = 'cur';
      st.curSpan = cur;
    }
    st.cur.style.top = (st.padTop + (lc.line - 1) * st.lh) + 'px';
    st.status.textContent = 'line ' + lc.line + ', col ' + lc.col + '  |  ' + n +
      (n === 1 ? ' line' : ' lines') + (st.tabOut ? '  |  Tab now moves focus' : '');
  }

  // replace [s, e) with txt through the browser's own edit command when
  // it has one, so undo still works; otherwise set the value directly
  function replaceRange(ta, s, e, txt) {
    var ok = false, v = ta.value, ev;
    ta.setSelectionRange(s, e);
    try { ok = document.execCommand(txt ? 'insertText' : 'delete', false, txt); } catch (err) { ok = false; }
    if ((!ok || ta.value === v) && v.slice(s, e) !== txt) {
      if (ta.setRangeText) ta.setRangeText(txt, s, e, 'end');
      else { ta.value = v.slice(0, s) + txt + v.slice(e); ta.setSelectionRange(s + txt.length, s + txt.length); }
      try { ev = new Event('input', {bubbles: true}); }
      catch (err) { ev = document.createEvent('Event'); ev.initEvent('input', true, false); }
      ta.dispatchEvent(ev);
    }
  }

  function applyLines(ta, r) {
    replaceRange(ta, r.from, r.to, r.block);
    ta.setSelectionRange(r.start, r.end);
  }

  function onKey(st, ev) {
    var ta = st.ta, k = ev.key, s = ta.selectionStart, e = ta.selectionEnd, text = ta.value, r;
    if (ev.isComposing || k === 'Shift' || k === 'Control' || k === 'Alt' || k === 'Meta') return;
    if (k === 'Escape') { st.tabOut = true; schedule(st); return; }
    if (k === 'Tab') {
      if (st.tabOut) { st.tabOut = false; return; }       // the browser moves focus
      ev.preventDefault();
      if (ev.shiftKey) r = indentLines(text, s, e, true);
      else if (text.slice(s, e).indexOf('\n') >= 0) r = indentLines(text, s, e, false);
      else { replaceRange(ta, s, e, '  '); return; }
      applyLines(ta, r);
      return;
    }
    st.tabOut = false;
    if (k === 'Enter' && !(ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey)) {
      ev.preventDefault();
      replaceRange(ta, s, e, newlineIndent(text, s));
    } else if (k === '/' && (ev.ctrlKey || ev.metaKey) && !ev.altKey) {
      ev.preventDefault();
      applyLines(ta, commentLines(text, s, e));
    }
  }

  // every textarea.code-editor under scope (the document by default)
  function init(scope) {
    var tas = (scope || document).querySelectorAll('textarea.code-editor'), i;
    for (i = 0; i < tas.length; i++) if (!tas[i].ceState) states.push(build(tas[i]));
    return states;
  }

  function relayout() { for (var i = 0; i < states.length; i++) layout(states[i]); }

  // theme or text size changed: measure again and redraw everything
  function refresh() {
    for (var i = 0; i < states.length; i++) { states[i].lastText = null; layout(states[i]); render(states[i]); }
  }

  root.BnglEditor = {tokenize: tokenize, highlight: highlight, bracketMatch: bracketMatch,
                     indentLines: indentLines, commentLines: commentLines,
                     newlineIndent: newlineIndent, lineCol: lineCol, init: init, refresh: refresh};

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { init(); });
    else init();
    root.addEventListener('themechange', refresh);
    root.addEventListener('fontsizechange', refresh);
    root.addEventListener('resize', relayout);
  }
})(typeof window !== 'undefined' ? window : this);
