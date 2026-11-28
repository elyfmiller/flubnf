"""The help popups' behavior (static/tips.js), run on served pages
(served_dom: jsc here, node in CI) after the 2026-11-27 user review, B14:
a "?" stayed open after Escape and covered the select it explained.

  * Escape hides a shown tip however it was shown (a click, keyboard
    focus, the pointer resting on it) and goes no further; focus in the
    box (its glossary link) goes back to its "?" first. With nothing
    shown it passes on, so a dialog's own Escape still works.
  * a click outside hides a shown tip; a click inside its box (the
    glossary link, its text) keeps it; a click on another "?" swaps them.
    A toggletip's panel closes the same two ways.
  * a reason button (tips.reason_button): a click or tap on the disabled
    button lands on its wrapper and keeps the reason it shows; an enabled
    one has no reason to show, so the pointer on it, or on one enabled
    while the pointer rests there, never holds an Escape back.
  * placement (FluBNFUI.place, one rule for both): under the button,
    above it when under it would cover a form control (the field a
    label's "?" explains, a drop zone) and above fits, inside the window
    at phone width too.

The served markup is the page's own: the scripts find the tips by their
own selectors. Geometry is the test's (served_dom has no layout): each
element named below gets a box, every other one is not drawn.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import datasets as D                       # noqa: E402
from app.ui import datasets_ui as DU                     # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402
from app.ui.server import app as srv                    # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_dataset_engines import grouped_bytes           # noqa: E402

client = TestClient(srv)
TIPS_JS = Path(__file__).resolve().parents[1] / "ui" / "static" / "tips.js"
pytestmark = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

#: what tips.js reads of a browser that served_dom's MiniDOM leaves out:
#: classList, closest, contains, style, focus and activeElement, the
#: root element, a window with its listeners, and a layout: BOX(el, x, y,
#: w, h) draws one element, VIEW(w, h) sets the window
PRELUDE = r"""
var P = Object.getPrototypeOf(document);
var LAYOUT = [];
function rectOf(el) {
  for (var i = 0; i < LAYOUT.length; i++) if (LAYOUT[i][0] === el) return LAYOUT[i][1];
  return {left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0};
}
function BOX(el, x, y, w, h) {
  if (!el) throw new Error('BOX: no element');
  LAYOUT.push([el, {left: x, top: y, right: x + w, bottom: y + h, width: w, height: h}]);
}
P.getBoundingClientRect = function () { return rectOf(this); };
Object.defineProperty(P, 'offsetWidth', {get: function () { return rectOf(this).width; }});
Object.defineProperty(P, 'offsetHeight', {get: function () { return rectOf(this).height; }});
P.closest = function (sel) {
  for (var n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(sel)) return n;
  return null;
};
P.contains = function (o) {
  for (var n = o; n; n = n.parentNode) if (n === this) return true;
  return false;
};
Object.defineProperty(P, 'classList', {get: function () {
  var el = this;
  function list() { return (el.getAttribute('class') || '').split(/\s+/).filter(Boolean); }
  return {
    contains: function (c) { return list().indexOf(c) >= 0; },
    add: function (c) { var l = list(); if (l.indexOf(c) < 0) l.push(c); el.setAttribute('class', l.join(' ')); },
    remove: function (c) { el.setAttribute('class', list().filter(function (x) { return x !== c; }).join(' ')); },
    toggle: function (c, on) {
      if (on === undefined) on = list().indexOf(c) < 0;
      if (on) this.add(c); else this.remove(c);
      return on;
    }
  };
}});
Object.defineProperty(P, 'style', {get: function () { return this._style || (this._style = {}); }});
function EV(type, target, extra) {
  var e = {type: type, bubbles: true, target: target, relatedTarget: null,
           stopped: false, prevented: false,
           stopPropagation: function () { this.stopped = true; },
           preventDefault: function () { this.prevented = true; }};
  for (var k in extra || {}) e[k] = extra[k];
  return e;
}
document.activeElement = null;
P.focus = function () {
  var prev = document.activeElement;
  if (prev === this) return;
  document.activeElement = this;
  if (prev) prev.dispatchEvent(EV('focusout', prev, {relatedTarget: this}));
  this.dispatchEvent(EV('focusin', this, {relatedTarget: prev}));
};
document.documentElement = document.querySelector('html');
var window = {innerHeight: 800, L: {},
  addEventListener: function (t, fn) { (this.L[t] = this.L[t] || []).push(fn); }};
function VIEW(w, h) { document.documentElement.clientWidth = w; window.innerHeight = h; }
VIEW(1000, 800);
// the browser's order: window's capture listeners first, then the target
// and its ancestors (unless one stopped it)
function KEY(key) {
  var t = document.activeElement || document.documentElement,
      e = EV('keydown', t, {key: key});
  (window.L.keydown || []).forEach(function (fn) { fn(e); });
  if (!e.stopped) t.dispatchEvent(e);
  return e;
}
function CLICK(el) { var e = EV('click', el); el.dispatchEvent(e); return e; }
function HOVER(el, from) { el.dispatchEvent(EV('mouseover', el, {relatedTarget: from || null})); }
function LEAVE(el, to) { el.dispatchEvent(EV('mouseout', el, {relatedTarget: to || null})); }
function TIP(id) { return document.getElementById('tip-' + id).parentNode; }
function STATE(id) {
  var c = ' ' + TIP(id).getAttribute('class') + ' ';
  return {open: c.indexOf(' open ') >= 0, hidden: c.indexOf(' dismissed ') >= 0};
}
"""


def _page(url: str) -> str:
    r = client.get(url)
    assert r.status_code == 200, (url, r.text[:300])
    return r.text


def _run(tmp_path, url, body):
    return SD.run(tmp_path, _page(url), [TIPS_JS], body, prelude=PRELUDE)


# ------------------------------------------------------- Escape hides it

def test_escape_hides_a_tip_however_it_was_shown(tmp_path):
    """The Data tab's upload "?" (its subject is the file; it ends with
    its glossary link): shown by a click, by focus, by the pointer, Escape
    hides it every time and the page's own Escape handlers never see that
    press; with nothing shown, Escape passes on."""
    out = _run(tmp_path, "/data", """
      var id = 'dsup-data-about', t = TIP(id), btn = t.querySelector('.tipbtn'),
          link = t.querySelector('.tipbox a.uk-term'), r = {};
      var dataEl = document.querySelector('main');
      r.idle = KEY('Escape').stopped;
      CLICK(btn);
      r.clicked = STATE(id);
      var e = KEY('Escape');
      r.afterClick = [STATE(id), e.stopped];
      // the pointer back: shown again; Escape hides it while it rests there
      LEAVE(btn, dataEl); HOVER(btn, dataEl);
      r.rehover = STATE(id);
      e = KEY('Escape');
      r.afterHover = [STATE(id), e.stopped];
      // keyboard focus on the "?", then on its glossary link in the box
      LEAVE(btn, dataEl);
      btn.focus();
      r.focused = STATE(id);
      link.focus();
      r.onLink = STATE(id);
      e = KEY('Escape');
      r.afterLink = [STATE(id), e.stopped, document.activeElement === btn];
      // the next Escape has nothing to hide: it goes on to the page
      r.second = KEY('Escape').stopped;
      return r;
    """)
    shown = {"open": False, "hidden": False}
    assert out["idle"] is False
    assert out["clicked"] == {"open": True, "hidden": False}
    assert out["afterClick"] == [{"open": False, "hidden": True}, True]
    assert out["rehover"] == shown
    assert out["afterHover"] == [{"open": False, "hidden": True}, True]
    assert out["focused"] == shown and out["onLink"] == shown
    assert out["afterLink"] == [{"open": False, "hidden": True}, True, True]
    assert out["second"] is False


# ------------------------------------------------- a click outside hides it

def test_a_click_outside_hides_a_tip_and_a_click_inside_keeps_it(tmp_path):
    out = _run(tmp_path, "/data", """
      var a = TIP('dsup-data-about'), b = TIP('archive'), r = {};
      var aBtn = a.querySelector('.tipbtn'), bBtn = b.querySelector('.tipbtn');
      CLICK(aBtn);
      // its glossary link and its words keep it
      CLICK(a.querySelector('.tipbox a.uk-term'));
      CLICK(a.querySelector('.tipbox'));
      r.inside = STATE('dsup-data-about');
      // the field under it: hidden
      CLICK(document.getElementById('dsup-data-kind'));
      r.outside = STATE('dsup-data-about');
      // focus resting on a "?" (a browser that focuses a clicked button):
      // a click elsewhere hides it too
      aBtn.focus();
      CLICK(document.querySelector('h1'));
      r.focusedOutside = STATE('dsup-data-about');
      // another "?": that one opens, the first hides
      a.classList.remove('dismissed');
      CLICK(aBtn);
      CLICK(bBtn);
      r.swapped = [STATE('dsup-data-about'), STATE('archive')];
      // a second click on the same "?" hides it
      CLICK(bBtn);
      r.again = STATE('archive');
      return r;
    """)
    assert out["inside"] == {"open": True, "hidden": False}
    assert out["outside"] == {"open": False, "hidden": True}
    assert out["focusedOutside"] == {"open": False, "hidden": True}
    assert out["swapped"] == [{"open": False, "hidden": True},
                              {"open": True, "hidden": False}]
    assert out["again"] == {"open": False, "hidden": True}


# ------------------------------------------------------ a reason button

@pytest.fixture
def two_datasets(tmp_path, monkeypatch):
    """The Data tab's list with two datasets, a replay on the first: its
    Delete is served off with its reason (tips.reason_button, off=True),
    the other's on with its "?" hidden (off=False)."""
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    busy = D.ingest(grouped_bytes(), "Kids", kind="count")
    D.ingest(grouped_bytes(groups=("Adult", "Pediatric")), "Adults",
             kind="count")
    monkeypatch.setitem(DU._REPLAY, "id", busy.id)
    ui_shared._invalidate_scans()
    yield
    ui_shared._invalidate_scans()


#: the two Delete buttons by state, each with its wrapper and reason id
_DELETES = """
  var off = null, on = null, all = document.querySelectorAll('button[data-del-dataset]');
  for (var i = 0; i < all.length; i++) if (all[i].disabled) off = all[i]; else on = all[i];
  var offWrap = off.parentNode, onWrap = on.parentNode,
      offId = off.getAttribute('data-uk-reason'), onId = on.getAttribute('data-uk-reason');
"""


def test_a_click_on_a_disabled_button_keeps_its_reason(tmp_path, two_datasets):
    """The disabled button lets the pointer through (ui-kit.css), so the
    click or tap lands on its wrapper, the reason's hover host but not
    inside the tip: the reason it shows stays up. On a phone a tap is the
    pointer arriving, then the click. A click elsewhere still hides it,
    and so does Escape."""
    out = _run(tmp_path, "/data", _DELETES + """
      var r = {served: [all.length, offWrap.className, onWrap.className,
                        document.getElementById('tip-' + offId).textContent]};
      HOVER(offWrap);
      r.hovered = STATE(offId);
      CLICK(offWrap);
      r.clicked = STATE(offId);
      CLICK(offWrap);
      r.again = STATE(offId);
      CLICK(document.querySelector('h1'));
      r.elsewhere = STATE(offId);
      // the pointer back on it, then Escape
      LEAVE(offWrap); HOVER(offWrap);
      var e = KEY('Escape');
      r.escape = [STATE(offId), e.stopped];
      return r;
    """)
    shown = {"open": False, "hidden": False}
    # served off, with its reason, beside the free one
    assert out["served"] == [2, "uk-reason", "uk-reason",
                             "A replay on it is in progress."]
    assert out["hovered"] == shown
    assert out["clicked"] == shown and out["again"] == shown
    assert out["elsewhere"] == {"open": False, "hidden": True}
    assert out["escape"] == [{"open": False, "hidden": True}, True]


def test_an_enabled_reason_button_never_holds_escape_back(tmp_path,
                                                          two_datasets):
    """An enabled reason button's "?" is hidden: the pointer on it shows
    nothing, so Escape goes on to the page (the Display menu, the Manage
    menu, a dialog). The same once a script enables the button the pointer
    rests on (FluBNFUI.setReason(button, null)), or removes a tip the
    pointer was on."""
    out = _run(tmp_path, "/data", _DELETES + """
      var r = {onHidden: onWrap.querySelector('.uk-reason-tip').hidden},
          main = document.querySelector('main');
      HOVER(on, main);
      r.onButton = KEY('Escape').stopped;
      HOVER(onWrap, main);
      r.onWrap = KEY('Escape').stopped;
      // the pointer on the off one, which its replay's end enables
      HOVER(offWrap, main);
      r.offShown = KEY('Escape').stopped;
      LEAVE(offWrap, main); HOVER(offWrap, main);
      window.FluBNFUI.setReason(off, null);
      r.enabledUnder = KEY('Escape').stopped;
      // a tip the pointer is on, removed by a script that redraws its part
      var t = TIP('archive'), p = t.parentNode, tb = t.querySelector('.tipbtn');
      HOVER(tb, main);
      r.tipShown = KEY('Escape').stopped;
      LEAVE(tb, main); HOVER(tb, main);
      p.childNodes.splice(p.childNodes.indexOf(t), 1); t.parentNode = null;
      r.removed = KEY('Escape').stopped;
      return r;
    """)
    assert out == {"onHidden": True, "onButton": False, "onWrap": False,
                   "offShown": True, "enabledUnder": False,
                   "tipShown": True, "removed": False}


def test_a_toggletip_closes_on_escape_and_on_a_click_outside(tmp_path):
    out = _run(tmp_path, "/output", """
      var w = document.getElementById('tt-out-files').parentNode,
          btn = w.querySelector('.uk-tt-btn'), r = {};
      function st() { return [w.classList.contains('open'), btn.getAttribute('aria-expanded')]; }
      CLICK(btn); r.open = st();
      CLICK(w.querySelector('.uk-tt-pop a.uk-term')); r.inside = st();
      var e = KEY('Escape'); r.esc = st().concat([e.stopped]);
      CLICK(btn); CLICK(document.querySelector('h1')); r.outside = st();
      return r;
    """)
    assert out["open"] == [True, "true"] and out["inside"] == [True, "true"]
    assert out["esc"] == [False, "false", True]
    assert out["outside"] == [False, "false"]


# ------------------------------------------------------------- placement

#: the "Values" field's "?" on the Data tab's upload box, and the select it
#: explains right under it: the review's case (a help over the select)
_FIELD = """
  var t = TIP('dsup-data-kind'), btn = t.querySelector('.tipbtn'),
      box = t.querySelector('.tipbox'),
      sel = document.getElementById('dsup-data-kind');
  BOX(btn, 300, 400, 18, 18);
  BOX(box, 0, 0, 260, 80);
"""


def test_a_tip_goes_under_its_button_unless_that_covers_a_field(tmp_path):
    out = _run(tmp_path, "/data", _FIELD + """
      var r = {};
      // nothing drawn under it: under the button, centered on it
      HOVER(btn);
      r.clear = [box.style.left, box.style.top];
      // the select it explains right under it: above the button instead
      BOX(sel, 200, 424, 300, 32);
      HOVER(btn);
      r.field = [box.style.left, box.style.top];
      r.side = window.FluBNFUI.place(btn, box);
      // shown by a click or by focus, placed the same way
      CLICK(btn); r.clicked = box.style.top;
      btn.focus(); r.focused = box.style.top;
      return r;
    """)
    # x: 300 + 9 - 130; under: 418 + 6; above: 400 - 6 - 80
    assert out["clear"] == ["179px", "424px"]
    assert out["field"] == ["179px", "314px"] and out["side"] == "above"
    assert out["clicked"] == "314px" and out["focused"] == "314px"


def test_a_control_in_a_closed_menu_does_not_count(tmp_path):
    """The Display menu is a closed <details> on every page: its theme
    choices (labels) keep boxes in some browsers though nothing shows.
    Under a tip they leave it below; open the menu and they count; its
    own row (the summary) shows and counts while it is closed."""
    out = _run(tmp_path, "/data", _FIELD + """
      var menu = document.querySelector('details.display'),
          pick = menu.querySelector('label.dm-th');
      BOX(pick, 250, 430, 80, 80);
      var r = [window.FluBNFUI.place(btn, box)];
      menu.setAttribute('open', '');
      r.push(window.FluBNFUI.place(btn, box));
      // the menu's own summary shows while it is closed
      menu.removeAttribute('open');
      BOX(menu.querySelector('summary'), 250, 430, 80, 30);
      r.push(window.FluBNFUI.place(btn, box));
      return r;
    """)
    assert out == ["below", "above", "above"]


def test_the_row_that_holds_the_tip_does_not_count(tmp_path):
    """A "?" in a fold's row (a summary) or a label: that row reaching
    under the button is the tip's own place, not a field to keep clear."""
    out = _run(tmp_path, "/data", _FIELD + """
      var row = t.parentNode;                   // the label's row
      var lab = row.querySelector('label');
      // the tip moved into its label, whose box reaches under the button
      lab.childNodes.push(t); t.parentNode = lab;
      BOX(lab, 200, 396, 140, 40);
      return window.FluBNFUI.place(btn, box);
    """)
    assert out == "below"


def test_a_drop_zone_under_a_tip_sends_it_above(tmp_path):
    """The Weekly CSV "?" sits over its drop zone, a label (B14: the
    Archive and Weekly CSV popups overlapped the drop zone's words)."""
    out = _run(tmp_path, "/data", """
      var t = TIP('dsup-data-about'), btn = t.querySelector('.tipbtn'),
          box = t.querySelector('.tipbox'),
          zone = document.querySelector('label.dsdrop');
      BOX(btn, 120, 300, 18, 18);
      BOX(box, 0, 0, 280, 150);
      BOX(zone, 30, 330, 360, 60);
      return [window.FluBNFUI.place(btn, box), box.style.top];
    """)
    assert out == ["above", "144px"]                      # 300 - 6 - 150


def test_it_stays_inside_the_window_and_takes_the_side_that_fits(tmp_path):
    out = _run(tmp_path, "/data", _FIELD + """
      var r = {};
      BOX(sel, 200, 424, 300, 32);
      // too near the top for above: under, though it covers the select
      LAYOUT.length = 0;
      BOX(btn, 300, 40, 18, 18); BOX(box, 0, 0, 260, 80); BOX(sel, 200, 64, 300, 32);
      r.top = [window.FluBNFUI.place(btn, box), box.style.top];
      // too near the bottom for under: above
      LAYOUT.length = 0;
      BOX(btn, 300, 760, 18, 18); BOX(box, 0, 0, 260, 80);
      r.bottom = [window.FluBNFUI.place(btn, box), box.style.top];
      // a phone, the "?" at the right edge: the box ends 8px inside it
      VIEW(375, 812);
      LAYOUT.length = 0;
      BOX(btn, 345, 300, 18, 18); BOX(box, 0, 0, 300, 80);
      r.phone = [box.style.left, window.FluBNFUI.place(btn, box), box.style.left];
      // and at the left edge, 8px from it
      LAYOUT.length = 0;
      BOX(btn, 4, 300, 18, 18); BOX(box, 0, 0, 300, 80);
      window.FluBNFUI.place(btn, box);
      r.left = box.style.left;
      // room on neither side: as low as fits
      VIEW(375, 120);
      LAYOUT.length = 0;
      BOX(btn, 100, 50, 18, 18); BOX(box, 0, 0, 300, 100);
      window.FluBNFUI.place(btn, box);
      r.squeezed = box.style.top;
      return r;
    """)
    assert out["top"] == ["below", "64px"]
    assert out["bottom"] == ["above", "674px"]            # 760 - 6 - 80
    assert out["phone"][1:] == ["below", "67px"]          # 375 - 8 - 300
    assert out["left"] == "8px"
    assert out["squeezed"] == "12px"                      # 120 - 8 - 100


def test_a_toggletip_panel_is_placed_by_the_same_rule(tmp_path):
    out = _run(tmp_path, "/output", """
      var w = document.getElementById('tt-out-files').parentNode,
          btn = w.querySelector('.uk-tt-btn'), pop = w.querySelector('.uk-tt-pop');
      BOX(btn, 300, 200, 18, 18);
      BOX(pop, 0, 0, 400, 120);
      // a control under the button (the page's first select, input or
      // button outside the toggletip and outside a closed menu): the
      // panel opens above it
      var any = document.querySelectorAll('select, input, button'), other = null;
      for (var i = 0; i < any.length && !other; i++) {
        var c = any[i], shut = false;
        for (var n = c.parentNode; n && n.nodeType === 1; n = n.parentNode)
          if (n.localName === 'details' && !n.hasAttribute('open')) shut = true;
        if (!w.contains(c) && !shut && c.getAttribute('type') !== 'hidden') other = c;
      }
      BOX(other, 250, 240, 120, 30);
      CLICK(btn);
      return [pop.style.position, pop.style.left, pop.style.top];
    """)
    assert out == ["fixed", "109px", "74px"]              # 200 - 6 - 120
