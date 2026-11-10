"""A served page as its scripts see it, for jsc or node (no browser driver
is installed here): the HTML the server rendered, parsed into a small DOM,
and the page's own static scripts run against it as they are served.

The point (review 3 of #93, finding 13): a test of a page script that
builds its own stand-in form, keyed by the selectors the script uses,
passes with the page's wiring broken (an id renamed in the template, an
attribute dropped). Here the script finds its elements in the served
markup, by its own selectors, or not at all.

  tree(html)      the page as nested {"tag", "attrs", "kids"} (text as
                  strings), for MINIDOM_JS
  run(tmp, html, scripts, body, prelude="")
                  load the page into `document`, run `prelude` (what the
                  page's inline scripts would have done first), then each
                  script file, then `body` (a function body whose return
                  value comes back, through JSON)

MINIDOM_JS covers what the console's form scripts use: getElementById,
querySelector(All) for simple selectors (tag, #id, .class, [attr],
[attr=value], :checked, :first-child, :last-child) joined by descendant
or child combinators, attributes, value, checked, selected, options,
disabled, hidden, textContent, and events that bubble. Anything else it
is asked for throws, so a test fails rather than passing on a guess.
Timers queue until flush() runs them (the scripts wait a tick).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
HAVE_JS = JSC.is_file() or bool(NODE)

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#document", "attrs": {}, "kids": []}
        self.stack = [self.root]

    def _node(self, tag, attrs):
        a = {}
        for k, v in attrs:
            a.setdefault(k, "" if v is None else v)    # the first one wins
        return {"tag": tag, "attrs": a, "kids": []}

    def handle_starttag(self, tag, attrs):
        if tag == "option" and self.stack[-1]["tag"] == "option":
            self.stack.pop()                     # an option ends the last
        node = self._node(tag, attrs)
        self.stack[-1]["kids"].append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1]["kids"].append(self._node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1]["kids"].append(data)


def tree(html: str) -> dict:
    """The page as nested {"tag", "attrs", "kids"}, text as strings."""
    t = _Tree()
    t.feed(html)
    t.close()
    return t.root


MINIDOM_JS = r"""
var MiniDOM = (function () {
  "use strict";
  function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  function Text(s, parent) { this.nodeType = 3; this.data = s;
                             this.parentNode = parent; }

  function El(spec, parent, doc) {
    this.nodeType = spec.tag === "#document" ? 9 : 1;
    this.localName = spec.tag;
    this.tagName = spec.tag.toUpperCase();
    this.attrs = {};
    for (var k in spec.attrs) if (own(spec.attrs, k))
      this.attrs[k] = spec.attrs[k];
    this.parentNode = parent || null;
    this.ownerDocument = doc || this;
    this.listeners = {};
    this.childNodes = [];
    for (var i = 0; i < spec.kids.length; i++) {
      var c = spec.kids[i];
      this.childNodes.push(typeof c === "string" ? new Text(c, this)
                           : new El(c, this, this.ownerDocument));
    }
    if (this.localName === "input") {
      this._value = own(this.attrs, "value") ? this.attrs.value : "";
      this.checked = own(this.attrs, "checked");
    } else if (this.localName === "textarea") {
      this._value = this.textContent;
    } else if (this.localName === "option") {
      this.selected = own(this.attrs, "selected");
    }
  }
  El.prototype.getAttribute = function (n) {
    return own(this.attrs, n) ? this.attrs[n] : null; };
  El.prototype.setAttribute = function (n, v) { this.attrs[n] = String(v); };
  El.prototype.removeAttribute = function (n) { delete this.attrs[n]; };
  El.prototype.hasAttribute = function (n) { return own(this.attrs, n); };
  El.prototype._kids = function () {
    return this.childNodes.filter(function (c) { return c.nodeType === 1; });
  };
  function walk(el, fn) {
    for (var i = 0; i < el.childNodes.length; i++) {
      var c = el.childNodes[i];
      if (c.nodeType === 1) { fn(c); walk(c, fn); }
    }
  }
  Object.defineProperty(El.prototype, "children", {
    get: function () { return this._kids(); }});
  Object.defineProperty(El.prototype, "id", {
    get: function () { return this.getAttribute("id") || ""; }});
  Object.defineProperty(El.prototype, "className", {
    get: function () { return this.getAttribute("class") || ""; }});
  Object.defineProperty(El.prototype, "hidden", {
    get: function () { return this.hasAttribute("hidden"); },
    set: function (v) { if (v) this.setAttribute("hidden", "");
                        else this.removeAttribute("hidden"); }});
  Object.defineProperty(El.prototype, "disabled", {
    get: function () { return this.hasAttribute("disabled"); },
    set: function (v) { if (v) this.setAttribute("disabled", "");
                        else this.removeAttribute("disabled"); }});
  Object.defineProperty(El.prototype, "textContent", {
    get: function () {
      var out = "";
      (function text(el) {
        for (var i = 0; i < el.childNodes.length; i++) {
          var c = el.childNodes[i];
          out += c.nodeType === 3 ? c.data : (text(c), "");
        }
      })(this);
      return out;
    },
    set: function (v) { this.childNodes = [new Text(String(v), this)]; }});
  Object.defineProperty(El.prototype, "options", {
    get: function () {
      if (this.localName !== "select") return undefined;
      var out = [];
      walk(this, function (c) { if (c.localName === "option") out.push(c); });
      return out;
    }});
  Object.defineProperty(El.prototype, "value", {
    get: function () {
      if (this.localName === "option")
        return own(this.attrs, "value") ? this.attrs.value
          : this.textContent.replace(/\s+/g, " ").replace(/^ | $/g, "");
      if (this.localName === "select") {
        var o = this.options, pick = null;
        for (var i = 0; i < o.length; i++) if (o[i].selected) { pick = o[i]; break; }
        if (!pick && !this.hasAttribute("multiple") && o.length) pick = o[0];
        return pick ? pick.value : "";
      }
      if (own(this, "_value")) return this._value;
      throw new Error("MiniDOM: no value on <" + this.localName + ">");
    },
    set: function (v) {
      if (this.localName === "select") {
        var o = this.options, hit = -1;
        for (var i = 0; i < o.length; i++)
          if (hit < 0 && o[i].value === String(v)) hit = i;
        if (hit < 0)
          throw new Error("MiniDOM: <select> has no option " + JSON.stringify(v));
        for (i = 0; i < o.length; i++) o[i].selected = i === hit;
        return;
      }
      this._value = String(v);
    }});

  // ---- selectors: compound parts joined by " " or ">", comma lists
  function parse(sel) {
    var alts = [], seq = [], comp = null, comb = null, i = 0, m;
    function need() {
      if (!comp) { comp = {tag: null, ids: [], cls: [], attrs: [], pseudo: []};
                   seq.push({c: comp, comb: comb}); comb = null; }
      return comp;
    }
    while (i < sel.length) {
      var rest = sel.slice(i), ch = sel.charAt(i);
      if ((m = /^\s*([>,])\s*/.exec(rest))) {
        if (m[1] === ",") { if (seq.length) alts.push(seq); seq = []; comb = null; }
        else comb = ">";
        comp = null; i += m[0].length;
      } else if ((m = /^\s+/.exec(rest))) {
        if (seq.length) comb = " ";
        comp = null; i += m[0].length;
      } else if (!comp && (m = /^(\*|[a-zA-Z][\w-]*)/.exec(rest))) {
        var c = need(); if (m[1] !== "*") c.tag = m[1].toLowerCase();
        i += m[0].length;
      } else if (ch === "#" && (m = /^#([\w-]+)/.exec(rest))) {
        need().ids.push(m[1]); i += m[0].length;
      } else if (ch === "." && (m = /^\.([\w-]+)/.exec(rest))) {
        need().cls.push(m[1]); i += m[0].length;
      } else if (ch === "[" && (m = /^\[\s*([\w:.-]+)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s"']+)))?\s*\]/.exec(rest))) {
        var v = m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : m[4];
        need().attrs.push({name: m[1], val: v}); i += m[0].length;
      } else if (ch === ":" && (m = /^:(checked|first-child|last-child|disabled)(?![\w-])/.exec(rest))) {
        need().pseudo.push(m[1]); i += m[0].length;
      } else {
        throw new Error("MiniDOM: cannot read selector " + JSON.stringify(sel)
                        + " at " + JSON.stringify(rest));
      }
    }
    if (seq.length) alts.push(seq);
    return alts;
  }
  function compound(el, c) {
    if (el.nodeType !== 1) return false;
    if (c.tag && el.localName !== c.tag) return false;
    for (var i = 0; i < c.ids.length; i++) if (el.id !== c.ids[i]) return false;
    var cls = " " + el.className.replace(/\s+/g, " ") + " ";
    for (i = 0; i < c.cls.length; i++)
      if (cls.indexOf(" " + c.cls[i] + " ") < 0) return false;
    for (i = 0; i < c.attrs.length; i++) {
      var a = c.attrs[i];
      if (!el.hasAttribute(a.name)) return false;
      if (a.val !== undefined && el.getAttribute(a.name) !== a.val) return false;
    }
    for (i = 0; i < c.pseudo.length; i++) {
      var p = c.pseudo[i], sib = el.parentNode ? el.parentNode._kids() : [el];
      if (p === "checked" && !(el.localName === "option" ? el.selected : el.checked === true)) return false;
      if (p === "disabled" && !el.disabled) return false;
      if (p === "first-child" && sib[0] !== el) return false;
      if (p === "last-child" && sib[sib.length - 1] !== el) return false;
    }
    return true;
  }
  function matchSeq(el, seq, k) {
    if (!compound(el, seq[k].c)) return false;
    if (k === 0) return true;
    var p = el.parentNode;
    if (seq[k].comb === ">") return !!p && p.nodeType === 1 && matchSeq(p, seq, k - 1);
    for (; p && p.nodeType === 1; p = p.parentNode)
      if (matchSeq(p, seq, k - 1)) return true;
    return false;
  }
  function matches(el, alts) {
    for (var i = 0; i < alts.length; i++)
      if (matchSeq(el, alts[i], alts[i].length - 1)) return true;
    return false;
  }
  El.prototype.querySelectorAll = function (sel) {
    var alts = parse(sel), out = [];
    walk(this, function (c) { if (matches(c, alts)) out.push(c); });
    return out;
  };
  El.prototype.querySelector = function (sel) {
    return this.querySelectorAll(sel)[0] || null; };
  El.prototype.matches = function (sel) { return matches(this, parse(sel)); };

  // ---- events: listeners on the target, then each ancestor
  El.prototype.addEventListener = function (t, fn) {
    (this.listeners[t] = this.listeners[t] || []).push(fn); };
  El.prototype.removeEventListener = function (t, fn) {
    var l = this.listeners[t] || [], i = l.indexOf(fn);
    if (i >= 0) l.splice(i, 1); };
  El.prototype.dispatchEvent = function (ev) {
    ev.target = ev.target || this;
    for (var n = this; n; n = ev.bubbles === false ? null : n.parentNode) {
      ev.currentTarget = n;
      var l = (n.listeners[ev.type] || []).slice();
      for (var i = 0; i < l.length; i++) l[i].call(n, ev);
    }
    return true;
  };
  El.prototype.fire = function (type) {
    return this.dispatchEvent({type: type, bubbles: true}); };

  function load(spec) {
    var doc = new El(spec, null, null);
    doc.ownerDocument = doc;
    walk(doc, function (c) { c.ownerDocument = doc; });
    doc.readyState = "complete";
    doc.getElementById = function (id) {
      var hit = null;
      walk(doc, function (c) { if (!hit && c.id === id) hit = c; });
      return hit;
    };
    return doc;
  }
  return {load: load, parse: parse};
})();

var TIMERS = [];
var setTimeout = function (fn) { TIMERS.push(fn); return TIMERS.length; };
var clearTimeout = function (id) { if (id) TIMERS[id - 1] = null; };
function flush() {
  for (var i = 0; i < TIMERS.length; i++) {
    var fn = TIMERS[i];
    TIMERS[i] = null;
    if (fn) fn();
  }
  TIMERS = [];
}
"""


def run(tmp: Path, html: str, scripts: list, body: str,
        prelude: str = ""):
    """Run the served page's `scripts` (paths, in the page's order)
    against `html` loaded as `document`, after `prelude`; return what
    `body` (a function body) returns, through JSON."""
    tmp.mkdir(parents=True, exist_ok=True)
    head = (MINIDOM_JS + "\nvar document = MiniDOM.load("
            + json.dumps(tree(html)) + ");\n" + prelude + "\n")
    tail = ("print(JSON.stringify((function () {\n" + body
            + "\n})()));\n")
    if JSC.is_file():
        a, b = tmp / "page-head.js", tmp / "page-tail.js"
        a.write_text(head, encoding="utf-8")
        b.write_text(tail, encoding="utf-8")
        cmd = [str(JSC), str(a), *map(str, scripts), str(b)]
    else:
        both = tmp / "page.js"
        both.write_text("var print = function (s) { console.log(s); };\n"
                        + head + "\n".join(Path(f).read_text(encoding="utf-8")
                                           for f in scripts) + "\n" + tail,
                        encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, (out.stderr or out.stdout)[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])
