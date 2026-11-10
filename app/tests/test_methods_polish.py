"""Methods polish (methods.html, tabs/methods.css, knobs.py, diagrams.html).

  * a contents-bar jump lands the section title under the bar: the bar's
    height is measured again after the print button joins it and whenever
    it changes, and the Performance chip's target is its card;
  * the chip marked current is the last section whose top has passed the
    bar, and the last one once the page is scrolled to its end;
  * a prior range's rule is stated per distribution (0 ≤ low < high, or
    0 < low < high for the log-uniform priors); the panel's refusal
    already says it in words;
  * each setting's note on Methods is one plain sentence: no file paths,
    dates, names, screen figures or raw keys;
  * the two Policies folds' bodies continue from their titles;
  * printing breaks inside a card (a card taller than a page no longer
    pushes a blank page) but never inside a figure, a row of facts or a
    table row, and a split table repeats its header;
  * every table scroller can be reached by keyboard and is named, as the
    figure scrollers are.

The contents bar's script runs under node (the page's own head script)
against a stand-in page built from the rendered page's elements, laid out
and scrolled by each test; the print rules are read through the cascade
(css_cascade) with print turned on.
"""
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import css_cascade as C                                # noqa: E402
from app.core import knobs as K                        # noqa: E402
from app.core import site_build                        # noqa: E402
from app.ui.server import app as srv                   # noqa: E402

client = TestClient(srv)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="no node to run the page's script")


def _methods() -> str:
    return client.get("/methods").text


# ------------------------------------- the head script under node, a harness

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}


class _Tree(HTMLParser):
    """The page's elements as nested dicts: tag, id, class, href, open, a
    link's text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "body", "kids": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        node = {"tag": tag, "kids": []}
        for k in ("id", "class", "href"):
            if a.get(k) is not None:
                node[k] = a[k]
        if "open" in a:
            node["open"] = True
        self.stack[-1]["kids"].append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack[-1]["tag"] == "a":
            self.stack[-1]["text"] = self.stack[-1].get("text", "") + data


def page_tree(html: str) -> dict:
    t = _Tree()
    t.feed(html)
    t.close()
    return t.root


def head_script(html: str) -> str:
    """The Methods page's head script: the contents bar's reading aids."""
    bodies = [b for b in re.findall(r"<script>(.*?)</script>", html, re.S)
              if "document.querySelector('.mt-tocbar')" in b]
    assert len(bodies) == 1
    return bodies[0]


#: the stand-in page: one row of chips (44 px), two once the Print button
#: joins them; the sections the contents row names stacked top to bottom,
#: each `height` tall unless `heights` says otherwise; a 900 px window
LAYOUT = {"row": 44, "wraps": True, "head": 300, "height": 1400, "gap": 24,
          "foot": 120, "heights": {}, "inner": 900}

STUB = r"""
var SCALE = 1, pageYOffset = 0, innerHeight = LAYOUT.inner;
var win = {}, raf = [], ros = [], scrolled = [], byId = {}, all = [];
function on(map, t, f) { (map[t] = map[t] || []).push(f); }
function addEventListener(t, f) { on(win, t, f); }
function flush() { while (raf.length) raf.shift()(); }
function fire(t, e) {
  (win[t] || []).slice().forEach(function (f) { f(e || {type: t}); });
  flush();
}
function requestAnimationFrame(f) { raf.push(f); }
function setTimeout() {}
var window = {ResizeObserver: true, print: function () {}};
function ResizeObserver(cb) { this.cb = cb; ros.push(this); }
ResizeObserver.prototype.observe = function () {};
var location = {hash: HASH,
  get href() { return 'http://testserver/methods' + this.hash; }};
var history = {replaceState: function () {}};
var navigator = {};
function El(tag) {
  this.tagName = tag.toUpperCase(); this.id = ''; this.cls = [];
  this.attrs = {}; this.kids = []; this.parentElement = null; this.l = {};
  this.style = {}; this.textContent = ''; this.open = false; this.box = null;
  var self = this;
  this.classList = {contains: function (c) { return self.cls.indexOf(c) >= 0; }};
  all.push(this);
}
Object.defineProperty(El.prototype, 'className', {
  get: function () { return this.cls.join(' '); },
  set: function (v) { this.cls = String(v).split(/\s+/).filter(Boolean); }});
Object.defineProperty(El.prototype, 'parentNode', {
  get: function () { return this.parentElement; }});
Object.defineProperty(El.prototype, 'nextSibling', {get: function () {
  var p = this.parentElement;
  return p ? p.kids[p.kids.indexOf(this) + 1] || null : null; }});
El.prototype.matches = function (s) {
  return s[0] === '.' ? this.cls.indexOf(s.slice(1)) >= 0
                      : this.tagName === s.toUpperCase(); };
El.prototype.closest = function (s) {
  for (var e = this; e; e = e.parentElement) if (e.matches(s)) return e;
  return null; };
El.prototype.walk = function (f) {
  this.kids.forEach(function (k) { f(k); k.walk(f); }); };
El.prototype.querySelectorAll = function (s) {
  var out = [];
  if (s === 'a[href^="#"]')
    this.walk(function (e) {
      if (e.tagName === 'A' && /^#/.test(e.getAttribute('href') || '')) out.push(e); });
  else this.walk(function (e) { if (e.matches(s)) out.push(e); });
  return out; };
El.prototype.querySelector = function (s) { return this.querySelectorAll(s)[0] || null; };
El.prototype.appendChild = function (c) { c.parentElement = this; this.kids.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
  var i = ref ? this.kids.indexOf(ref) : -1;
  c.parentElement = this;
  if (i < 0) this.kids.push(c); else this.kids.splice(i, 0, c);
  return c; };
El.prototype.removeChild = function (c) { this.kids.splice(this.kids.indexOf(c), 1); };
El.prototype.getAttribute = function (k) { return k in this.attrs ? this.attrs[k] : null; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
El.prototype.removeAttribute = function (k) { delete this.attrs[k]; };
El.prototype.addEventListener = function (t, f) { on(this.l, t, f); };
El.prototype.getBoundingClientRect = function () {
  for (var e = this; e && !e.box; e = e.parentElement);
  var b = e ? e.box : {top: 0, height: 0}, t = b.top - pageYOffset;
  return {top: t, bottom: t + b.height, left: 0, right: 0, width: 0,
          height: b.height}; };
El.prototype.scrollIntoView = function () { scrolled.push(this.id); };
El.prototype.select = function () {};
function build(n, parent) {
  var e = new El(n.tag);
  if (n.id) { e.id = n.id; byId[n.id] = e; }
  if (n.class) e.className = n.class;
  if (n.href != null) e.attrs.href = n.href;
  if (n.open) e.open = true;
  if (n.text) e.textContent = n.text;
  if (parent) parent.appendChild(e);
  (n.kids || []).forEach(function (k) { build(k, e); });
  return e;
}
var body = build(TREE, null);
var de = {style: {p: {}, setProperty: function (k, v) { this.p[k] = v; }},
  attrs: {}, getAttribute: function (k) { return this.attrs[k] || null; },
  setAttribute: function (k, v) { this.attrs[k] = v; }, scrollHeight: 0};
var docl = {};
var document = {documentElement: de, body: body,
  addEventListener: function (t, f) { on(docl, t, f); },
  getElementById: function (id) { return byId[id] || null; },
  querySelector: function (s) { return body.querySelector(s); },
  querySelectorAll: function (s) {
    if (s === '.mt-doc details:not([open])')
      return body.querySelector('.mt-doc').querySelectorAll('details')
                 .filter(function (d) { return !d.open; });
    return body.querySelectorAll(s); },
  createElement: function (t) { return new El(t); },
  execCommand: function () { return false; }};
var bar = document.querySelector('.mt-tocbar'), toc = document.querySelector('.mt-toc');
Object.defineProperty(bar, 'offsetHeight', {get: function () {
  var rows = LAYOUT.wraps && bar.querySelector('.mt-print') ? 2 : 1;
  return Math.round(rows * LAYOUT.row * SCALE); }});
toc.scrollWidth = toc.clientWidth = 0;
var chips = toc.querySelectorAll('a[href^="#"]'), y = LAYOUT.head;
chips.forEach(function (a) {
  var t = byId[a.getAttribute('href').slice(1)], card = t.closest('.card') || t;
  card.box = {top: y, height: LAYOUT.heights[t.id] || LAYOUT.height};
  y += card.box.height + LAYOUT.gap;
});
de.scrollHeight = y + LAYOUT.foot;
"""

DRIVE = r"""
// as a browser: a scroll event only when the page moves
function scrollTo_(to) {
  to = Math.max(0, Math.min(to, de.scrollHeight - innerHeight));
  if (to === pageYOffset) return flush();
  pageYOffset = to;
  fire('scroll');
}
function topOf(id) { var t = byId[id]; return (t.closest('.card') || t).box.top; }
var out = [];
function snap(label) {
  var folds = {};
  all.forEach(function (e) { if (e.tagName === 'DETAILS' && e.id) folds[e.id] = e.open; });
  out.push({label: label,
    current: chips.filter(function (a) { return a.getAttribute('aria-current') === 'location'; })
                  .map(function (a) { return a.getAttribute('href'); }),
    tocH: de.style.p['--mt-toc-h'] || null, folds: folds,
    scrolled: scrolled.splice(0), atEnd: pageYOffset >= de.scrollHeight - innerHeight});
}
(docl.DOMContentLoaded || []).forEach(function (f) { f(); });
flush();
snap('load');
STEPS.forEach(function (s) {
  if (s.do === 'scroll') scrollTo_(s.y);
  else if (s.do === 'top') scrollTo_(topOf(s.id) - (bar.offsetHeight + 8) + (s.by || 0));
  else if (s.do === 'end') scrollTo_(de.scrollHeight);
  else if (s.do === 'up') scrollTo_(pageYOffset - s.by);
  else if (s.do === 'click') {
    // a chip: the press, the click, the browser's jump (the target's top
    // under the bar: its scroll margin), then the address changes
    var a = chips.filter(function (l) { return l.getAttribute('href') === s.href; })[0];
    fire('mousedown');
    (a.l.click || []).forEach(function (f) { f({type: 'click'}); });
    scrollTo_(topOf(s.href.slice(1)) - (bar.offsetHeight + 8));
    location.hash = s.href;
    fire('hashchange');
  }
  else if (s.do === 'wheel') fire('wheel');
  else if (s.do === 'key') fire('keydown', {type: 'keydown', key: s.key});
  else if (s.do === 'hash') { location.hash = s.to; fire('hashchange'); }
  else if (s.do === 'text') {
    // the text size changes: the bar's own size changes and its observer
    // is told (no window resize, no fontsizechange)
    SCALE = s.scale;
    ros.forEach(function (o) { o.cb([]); });
  }
  snap(s.label || s.do);
});
console.log(JSON.stringify(out));
"""


def run_methods(tmp_path, steps=(), hash_="", layout=None, html=None):
    """The Methods page's head script on the stand-in page: a snapshot
    (current chip, --mt-toc-h, each fold's open state, what was scrolled
    into view) after load and after each step."""
    html = html or _methods()
    lay = dict(LAYOUT, **(layout or {}))
    drv = tmp_path / "methods-head.js"
    drv.write_text(
        f"var LAYOUT = {json.dumps(lay)};\nvar HASH = {json.dumps(hash_)};\n"
        f"var STEPS = {json.dumps(list(steps))};\n"
        f"var TREE = {json.dumps(page_tree(html))};\n"
        + STUB + head_script(html) + "\n" + DRIVE, encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


#: the last two sections short enough to share the final screen
SHORT_END = {"heights": {"stack": 300, "policies": 250}}


# ------------------------------------------------- ME-04: jumps land in view

@needs_node
def test_the_bar_is_measured_after_the_print_button_and_when_it_changes(tmp_path):
    # one row of chips, two once the Print button joins them: the scroll
    # margin (--mt-toc-h) is the two rows' height once the page is ready,
    # and follows the bar when its own size changes (text size, fonts)
    got = run_methods(tmp_path, [{"do": "text", "scale": 1.6},
                                 {"do": "text", "scale": 1.0}])
    assert [s["tocH"] for s in got] == ["88px", "141px", "88px"]
    # a bar that keeps one row keeps its one-row height
    one = run_methods(tmp_path, layout={"wraps": False})
    assert one[0]["tocH"] == "44px"


def test_the_performance_chips_target_is_its_card():
    html = _methods()
    # the Performance chip's target is its card, as the other chips' are
    assert '<div class="card" id="performance"><h2>Measured performance</h2>' in html
    assert '<span id="performance"></span>' not in html


def test_the_site_harvest_still_drops_the_performance_card():
    site = site_build.harvest_methods({k: "x" for k in ("pybnf", "bngsim",
                                                        "bionetgen", "fastapi",
                                                        "plotly")})
    assert "Measured performance" not in site
    assert 'id="performance"' not in site


# ----------------------------------------- ME-05: the chip that reads current

@needs_node
def test_the_current_chip_is_the_last_section_passed_and_the_last_at_the_end(tmp_path):
    # the last two sections share the final screen, so neither can reach
    # the band under the bar
    got = run_methods(tmp_path, [
        {"do": "top", "id": "oracle", "by": 200, "label": "in oracle"},
        {"do": "top", "id": "two-strain", "by": -40, "label": "under the band"},
        {"do": "top", "id": "two-strain", "label": "at the band"},
        {"do": "end"}], layout=SHORT_END)
    at = {s["label"]: s["current"] for s in got}
    assert at["load"] == ["#purpose"]
    assert at["in oracle"] == ["#oracle"]
    assert at["under the band"] == ["#oracle"]
    assert at["at the band"] == ["#two-strain"]
    assert got[-1]["atEnd"] and at["end"] == ["#policies"]


# --------------------------------------------- ME-13: the prior range's rule

def test_a_prior_ranges_rule_is_stated_per_distribution():
    assert K.BY_KEY["pf.prior.mult"].range_text() == "0 < low < high"
    assert K.BY_KEY["pf.prior.r"].range_text() == "0 < low < high"
    assert K.BY_KEY["pf.prior.Reff"].range_text() == "0 ≤ low < high"
    assert K.BY_KEY["pf.prior.eps1"].range_text() == "0 ≤ low < high"
    html = _methods()
    row = html.split('id="set-pf-prior-mult"', 1)[1].split("</tr>", 1)[0]
    assert '<td data-label="Range">0 &lt; low &lt; high</td>' in row
    row = html.split('id="set-pf-prior-Reff"', 1)[1].split("</tr>", 1)[0]
    assert '<td data-label="Range">0 ≤ low &lt; high</td>' in row
    assert "the engine's rule" not in html


# ------------------------------------------------ ME-16: the notes are plain

def test_each_settings_note_is_one_plain_sentence():
    from app.ui.routes.methods import settings_reference
    notes = [r["note"] for g in settings_reference() for r in g["rows"]
             if r["note"]]
    assert len(notes) == 11
    keys = "|".join(re.escape(k) for k in K.BY_KEY)
    for n in notes:
        assert n.endswith(".") and ". " not in n, n
        assert len(n.split()) <= 45, n
        assert not re.search(keys, n), n                    # labels, not keys
        assert not re.search(r"docs/|\d{4}-\d{2}-\d{2}|Spencer|Ely|"
                             r"Pre-registered|rho\*mult|season_total", n), n
    html = client.get("/methods").text
    assert "Pre-registered screen" not in html and "Spencer Fox" not in html
    # what the sealed record ran stays
    assert "the sealed record ran 0.30" in K.BY_KEY["pf.jitter"].note


# ------------------------------------------- ME-18: the fold bodies continue

def test_the_policies_folds_do_not_repeat_their_titles():
    html = _methods()
    for fid, start in (("mt-newest", "<p>It is the forecaster's decision, per state"),
                       ("mt-sealcaveats", "<p>Seven of 76 sealed weeks' vintages")):
        body = html.split(f'id="{fid}"', 1)[1].split("</details>", 1)[0]
        body = body.split('<div class="uk-fold-body">', 1)[1].strip()
        assert body.startswith(start), (fid, body[:80])


# ---------------------------------------------- ME-21: printing breaks inside

#: a printed page's width in CSS px (Letter or A4 less the margins)
PRINT_W = 720
PRINT = ("print",)
CARD = ("html", "body", "main", "div.mt-doc", "div.card")


def _printed(cas, chain, prop):
    """The value the cascade gives `prop` on `chain` when printing."""
    return cas.value(C.path(*chain), prop, PRINT_W, on=PRINT)


def test_printing_breaks_inside_a_card_but_not_a_figure_or_table():
    cas = C.Cascade.page("tabs/methods.css", "tabs/models.css")
    # a card may split across pages (one taller than a page pushed a blank
    # page before it): nothing makes it avoid a break
    for chain in (CARD, CARD[:-1] + ("div.card#performance",)):
        for prop in ("break-inside", "page-break-inside"):
            assert _printed(cas, chain, prop) in (None, "auto"), (chain, prop)
    # a figure, its scroller, a row of facts and a table row never split
    for inner in (("figure",), ("div.figscroll[tabindex=0][role=region]",),
                  ("dl.uk-stats",), ("div.mt-scroll", "table", "tbody", "tr"),
                  ("details.uk-fold.mt-fold", "div.uk-fold-body",
                   "div.mt-setscroll", "table", "tbody", "tr")):
        for prop in ("break-inside", "page-break-inside"):
            assert _printed(cas, CARD + inner, prop) == "avoid", (inner, prop)
    # a split table repeats its header on the next page
    for table in (("div.mt-scroll", "table"),
                  ("details.uk-fold.mt-fold", "div.uk-fold-body",
                   "div.mt-setscroll", "table")):
        assert _printed(cas, CARD + table + ("thead",), "display") == \
            "table-header-group", table
    # a title stays with what follows it
    for title in (("h2",), ("h3",), ("details.uk-fold", "summary")):
        assert _printed(cas, CARD + title, "break-after") == "avoid", title


# ------------------------------------------ ME-22: the table scrollers reach

def test_every_table_scroller_can_be_reached_and_is_named():
    html = _methods()
    assert '<div style="overflow-x:auto">' not in html
    wrappers = re.findall(r'<div class="(mt-scroll|mt-setscroll|eqvars-scroll)"([^>]*)>', html)
    assert len(wrappers) >= 8, len(wrappers)
    for cls, attrs in wrappers:
        assert 'tabindex="0"' in attrs and 'role="region"' in attrs, (cls, attrs)
        assert re.search(r'aria-label="[^"]+ \(scrolls\)"', attrs), (cls, attrs)
    for label in ("Record by season (scrolls)",
                  "Measured performance by season (scrolls)",
                  "Components and versions (scrolls)", "Variables (scrolls)",
                  "Fixed by the model definition (scrolls)",
                  "Fit window (scrolls)"):
        assert f'aria-label="{label}"' in html, label
    # each settings group's table is named after the group
    groups = html.count('<details class="uk-fold mt-fold" id="mt-set-')
    assert groups >= 4
    assert len(re.findall(r'aria-label="[^"]+ \(scrolls\)"', html)) >= groups + 5
    css = (STATIC / "tabs" / "methods.css").read_text()
    assert ".mt-scroll{overflow-x:auto}" in css
    assert ".mt-scroll:focus-visible,.mt-setscroll:focus-visible,.eqvars-scroll:focus-visible{" in css
    # the model pages share the variables table
    assert 'class="eqvars-scroll" tabindex="0" role="region" aria-label="Variables (scrolls)"' \
        in client.get("/models").text
