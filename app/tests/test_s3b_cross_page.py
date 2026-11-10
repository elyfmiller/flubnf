"""Across pages, the review of #97 (bug hunt G35), second S3 pass.

  * UI-12: with storage blocked (reading `localStorage` throws) or full
    (a write throws), a theme picked in the Display menu stays checked and
    a change of the system's scheme does not override it; with storage
    working the pick is stored as before (the page's own script under
    node).
  * UI-12: the shell's scripts run with both storages throwing on access,
    not only on a call, and every storage use in the console's templates
    and scripts sits inside a try block, whichever page it is on.
  * UI-14: the fact Home's record line sends the reader to Methods for
    (the FluSight Ensemble column's cells) is on Methods; the explainers
    trimmed in this pass stay short.

The one-"i" count with every fold opened, Retrospective beside Forecast,
is test_fewer_marks'; "All 53 locations reported" is
test_newest_reported's.
"""
import json
import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui import server as srv                               # noqa: E402

client = TestClient(srv.app)
NODE = shutil.which("node")
UI = Path(__file__).resolve().parents[1] / "ui"
needs_node = pytest.mark.skipif(not NODE, reason="no node to run the page's scripts")


# ------------------------------------------------ the shell's script, a harness

def _shell(html: str) -> tuple:
    """The first-paint script, and the shell's script from the external
    links handler through the zoom row (scroll memory, theme picker, the
    two switches, text size, zoom), as a page carries them."""
    boot = html.split("// before first paint", 1)[1]
    boot = boot[boot.index("(function(){"):]
    boot = boot[:boot.index("})();") + len("})();")]
    first = "// external links open in a new window"
    main = first + html.split(first, 1)[1].split("// slow-page report", 1)[0]
    return boot, main


#: the page's scripts in a vm context of their own: storage that works
#: ("ok"), whose writes throw ("write", a full or read-only store), or
#: whose very name throws when read ("access", Safari with site data
#: blocked); a stand-in Display menu; steps that click, pick and change
#: the system's scheme. Prints a snapshot after the start and each step.
_RUNNER = r"""
const vm = require('vm');
const job = JSON.parse(require('fs').readFileSync(0, 'utf8'));
function Store() {
  const m = {};
  return {m: m,
    getItem: k => (k in m ? m[k] : null),
    setItem: (k, v) => { if (job.mode === 'write') throw new Error('QuotaExceededError'); m[k] = String(v); },
    removeItem: k => { if (job.mode === 'write') throw new Error('QuotaExceededError'); delete m[k]; }};
}
const local = Store(), session = Store();
function El() { this.a = {}; this.dataset = {}; this.style = {}; this.l = {};
  this.checked = false; this.hidden = false; this.disabled = false;
  this.textContent = ''; this.value = ''; }
El.prototype.setAttribute = function (k, v) { this.a[k] = String(v); };
El.prototype.getAttribute = function (k) { return k in this.a ? this.a[k] : null; };
El.prototype.removeAttribute = function (k) { delete this.a[k]; };
El.prototype.addEventListener = function (t, f) { (this.l[t] = this.l[t] || []).push(f); };
El.prototype.fire = function (t) { (this.l[t] || []).forEach(f => f({type: t, target: this})); };
El.prototype.focus = function () {};
const de = new El();
const themes = job.themes.map(id => { const e = new El(); e.dataset.th = id; return e; });
const sys = new El(), now = new El(), zoomLabel = new El();
const ax = ['contrast', 'vision'].map(k => { const e = new El(); e.dataset.ax = k; return e; });
const fs = new El(), fsOut = new El(), fsReset = new El();
const steps = [-1, 1].map(n => { const e = new El(); e.dataset.fsStep = String(n); return e; });
let dark = job.dark;
const scheme = {get matches() { return dark; }, l: [],
  addEventListener(t, f) { this.l.push(f); }};
const win = {}, errors = [];
const ctx = {
  document: {documentElement: de, activeElement: null,
    querySelectorAll(s) {
      if (s.indexOf('input[data-th]') >= 0) return themes;
      if (s.indexOf('data-ax') >= 0) return ax;
      if (s.indexOf('data-fs-step') >= 0) return steps;
      return []; },
    querySelector(s) {
      if (s.indexOf('input[data-sys]') >= 0) return sys;
      if (s === '.dm-sys-now') return now;
      if (s.indexOf('dm-zoom-v') >= 0) return zoomLabel;
      return null; },
    getElementById(id) {
      return {'dm-fs': fs, 'dm-fs-out': fsOut, 'dm-fs-reset': fsReset}[id] || null; }},
  matchMedia(q) {
    if (q.indexOf('prefers-color-scheme') >= 0) return scheme;
    return {matches: q.indexOf('more') >= 0 && job.more, addEventListener() {}}; },
  Event: function (t) { this.type = t; },
  dispatchEvent() {}, setTimeout(f) { f(); return 0; }, clearTimeout() {},
  requestAnimationFrame() {}, scrollTo() {}, scrollY: 40,
  location: {pathname: '/methods', hash: '', protocol: 'http:', host: 'testserver'},
  navigator: {platform: 'MacIntel'}, Promise: Promise};
ctx.window = ctx;
ctx.addEventListener = (t, f) => { (win[t] = win[t] || []).push(f); };
if (job.mode !== 'access') { ctx.localStorage = local; ctx.sessionStorage = session; }
vm.createContext(ctx);
// blocked: the name itself throws when read, on the context's own global
if (job.mode === 'access')
  vm.runInContext("['localStorage', 'sessionStorage'].forEach(function (k) {" +
    " Object.defineProperty(globalThis, k, {get: function () {" +
    " throw new Error('SecurityError: ' + k); }}); });", ctx);
const out = [];
function snap(label) {
  out.push({label: label, theme: de.getAttribute('data-theme'),
    contrast: de.getAttribute('data-contrast'),
    picked: themes.filter(b => b.checked).map(b => b.dataset.th),
    system: sys.checked, size: de.style.fontSize || null,
    zoom: zoomLabel.textContent || null,
    stored: Object.assign({}, local.m), kept: Object.assign({}, session.m),
    errors: errors.splice(0)});
}
function run(f) { try { f(); } catch (e) { errors.push(String(e)); } }
(async function () {
  for (const src of job.scripts) run(() => vm.runInContext(src, ctx));
  snap('start');
  for (const s of job.steps) {
    run(() => {
      if (s.do === 'pick') {
        const b = themes.find(t => t.dataset.th === s.th);
        themes.forEach(t => { t.checked = false; }); sys.checked = false;
        b.checked = true; b.fire('change');
      } else if (s.do === 'system') {
        themes.forEach(t => { t.checked = false; });
        sys.checked = true; sys.fire('change');
      } else if (s.do === 'scheme') {
        dark = s.dark; scheme.l.forEach(f => f({matches: dark}));
      } else if (s.do === 'contrast') {
        ax[0].onclick();
      } else if (s.do === 'bigger') {
        steps[1].onclick();
      } else if (s.do === 'unload' || s.do === 'load') {
        (win[s.do === 'unload' ? 'beforeunload' : 'load'] || []).forEach(f => f({}));
      } else if (s.do === 'zoom') {
        ctx.pywebview = {api: {can_zoom: () => Promise.resolve(true),
          set_zoom: z => Promise.resolve(z), zoom: n => Promise.resolve(1.1)}};
        (win.pywebviewready || []).forEach(f => f({}));
      }
    });
    await new Promise(r => setImmediate(r));
    snap(s.label || s.do);
  }
  process.stdout.write(JSON.stringify(out));
})();
"""

THEMES = ["light", "dark"]


def _run(scripts, steps, mode, dark=True, more=False, themes=None) -> list:
    job = json.dumps({"scripts": scripts, "steps": steps, "mode": mode,
                      "dark": dark, "more": more,
                      "themes": themes or THEMES})
    out = subprocess.run([NODE, "-e", _RUNNER], input=job, text=True,
                         capture_output=True, timeout=60, encoding="utf-8")
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def _picker(html: str) -> str:
    """The theme picker's script alone."""
    s = html.split("// theme picker:", 1)[1].split("// accessibility modes:", 1)[0]
    return s[s.index("(function(){"):]


def _theme_ids(html: str) -> list:
    return re.findall(r'<input type="radio" name="dm-theme" value="([\w-]+)" '
                      r'data-th="\1"', html)


# ------------------------------------------- UI-12: the pick with no storage

PICK_STEPS = [{"do": "pick", "th": "light"},
              {"do": "scheme", "dark": False, "label": "system light"},
              {"do": "scheme", "dark": True, "label": "system dark"},
              {"do": "system"},
              {"do": "scheme", "dark": False, "label": "system light again"}]


@needs_node
@pytest.mark.parametrize("mode", ["access", "write", "ok"])
def test_a_picked_theme_stays_checked_and_holds_whatever_storage_does(mode):
    html = client.get("/methods").text
    boot, _ = _shell(html)
    ids = _theme_ids(html)
    assert len(ids) == 8 and "light" in ids and "dark" in ids
    got = _run([boot, _picker(html)], PICK_STEPS, mode, themes=ids)
    at = {s["label"]: s for s in got}
    for s in got:
        assert s["errors"] == [], (mode, s)
    # the system is dark: the page follows it, Match system checked
    assert (at["start"]["theme"], at["start"]["picked"],
            at["start"]["system"]) == ("dark", [], True)
    # Light picked: applied and checked, Match system not
    for label in ("pick", "system light", "system dark"):
        assert (at[label]["theme"], at[label]["picked"],
                at[label]["system"]) == ("light", ["light"], False), (mode, label)
    # Match system again: the page follows the system from then on
    assert (at["system"]["theme"], at["system"]["picked"],
            at["system"]["system"]) == ("dark", [], True)
    assert (at["system light again"]["theme"],
            at["system light again"]["system"]) == ("light", True)
    # working storage keeps the pick, and Match system clears it
    if mode == "ok":
        assert at["pick"]["stored"] == {"theme": "light"}
        assert at["system"]["stored"] == {}
    else:
        assert at["pick"]["stored"] == {}


# ----------------------- UI-12: the shell with storage that throws on access

@needs_node
def test_the_shell_runs_with_storage_that_throws_when_named():
    """Reading `localStorage` or `sessionStorage` itself throws (not only
    a call on it): the first paint follows the system, every control
    still works and says so, and no script stops."""
    html = client.get("/methods").text
    boot, main = _shell(html)
    steps = [{"do": "unload"}, {"do": "load"},
             {"do": "pick", "th": "light"},
             {"do": "scheme", "dark": False, "label": "system light"},
             {"do": "contrast"}, {"do": "bigger"}, {"do": "zoom"}]
    got = _run([boot, main], steps, "access", dark=True, more=True,
               themes=_theme_ids(html))
    at = {s["label"]: s for s in got}
    assert [e for s in got for e in s["errors"]] == []
    assert (at["start"]["theme"], at["start"]["contrast"],
            at["start"]["size"]) == ("dark", "high", "100%")
    assert (at["system light"]["theme"], at["system light"]["picked"]) == \
        ("light", ["light"])
    assert at["contrast"]["contrast"] is None
    assert at["bigger"]["size"] == "105%"
    assert at["zoom"]["zoom"] == "100%"


# ------------------- UI-12: every storage use on the console, inside a try

_JINJA = re.compile(r"\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}", re.S)


def _code(js: str) -> str:
    """`js` with its comments, strings and regular expressions blanked
    (same length, newlines kept), so braces and names are code only."""
    out, i, n = list(js), 0, len(js)
    last = ""                         # the last code character seen

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "
    while i < n:
        c = js[i]
        if js.startswith("//", i):
            j = js.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif js.startswith("/*", i):
            j = js.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c in "'\"`":
            j = i + 1
            while j < n and js[j] != c:
                j += 2 if js[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
            last = c
        elif c == "/" and (last in "(,=:[!&|?{};+-*%<>~^" or last == ""
                           or re.search(r"\b(return|typeof|case)\s*$",
                                        js[max(0, i - 12):i])):
            j, cls = i + 1, False
            while j < n and (cls or js[j] != "/") and js[j] != "\n":
                if js[j] == "\\":
                    j += 1
                elif js[j] == "[":
                    cls = True
                elif js[j] == "]":
                    cls = False
                j += 1
            blank(i + 1, j)
            i = j + 1
            last = "/"
        else:
            if not c.isspace():
                last = c
            i += 1
    return "".join(out)


def unguarded(js: str) -> list:
    """The lines of `js` that name localStorage or sessionStorage outside
    every try block."""
    code = _code(js)
    spans = []
    for m in re.finditer(r"\btry\s*\{", code):
        depth, j = 0, m.end() - 1
        while j < len(code):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        spans.append((m.end(), j))
    bad = []
    for m in re.finditer(r"\b(?:local|session)Storage\b", code):
        if not any(a <= m.start() < b for a, b in spans):
            line = js.count("\n", 0, m.start())
            bad.append(js.splitlines()[line].strip())
    return bad


def _console_scripts():
    """(where, script) for every inline script in the console's templates
    and every script it serves (the vendored chart library aside)."""
    for p in sorted((UI / "templates").glob("*.html")):
        text = _JINJA.sub("0", p.read_text(encoding="utf-8"))
        for k, body in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                            text, re.S)):
            yield f"{p.name} script {k + 1}", body
    for p in sorted((UI / "static").rglob("*.js")):
        if not p.name.endswith(".min.js"):
            yield p.name, p.read_text(encoding="utf-8")


def test_every_storage_use_on_the_console_is_inside_a_try():
    seen = 0
    for where, js in _console_scripts():
        assert unguarded(js) == [], where
        seen += len(re.findall(r"\b(?:local|session)Storage\b", _code(js)))
    # the shell, Forecast, Output, Storage, the season page, the player,
    # the Model settings panel and the Sandbox all keep something
    assert seen >= 30


def test_the_scan_finds_an_unguarded_use():
    """The scan itself: an unguarded read, write or name is found, one in a
    string, a comment or a regular expression is not, and a try's block
    ends at its own closing brace."""
    assert unguarded("var a=localStorage.getItem('x');") == [
        "var a=localStorage.getItem('x');"]
    assert unguarded("try{var a=localStorage.getItem('x');}catch(e){}") == []
    assert unguarded("try{a();}catch(e){}\nsessionStorage.setItem('k','{');") == [
        "sessionStorage.setItem('k','{');"]
    assert unguarded("try{if(x){y();}\nlocalStorage.x=1;}catch(e){}") == []
    assert unguarded("var s='localStorage'; // localStorage\n"
                     "/* sessionStorage */ var r=/localStorage}/;") == []
    # forecast.html's guard, model_settings.js's and player.js's, as written
    assert unguarded("try { initial = localStorage.getItem('fcmode') || "
                     "initial; } catch (e) {}") == []
    assert unguarded("function readScale(){\n  try{\n    return "
                     "localStorage.getItem(K) === 'log' ? 'log' : 'natural';"
                     "\n  }catch(e){ return 'natural'; }\n}") == []


# --------------------------------------------- UI-14: the Ensemble's cells

def test_the_ensembles_cells_are_on_the_consoles_methods_only():
    from app.core import site_build
    said = "Home's FluSight Ensemble column is scored on 15,460 cells"
    methods = " ".join(unescape(client.get("/methods").text).split())
    fold = methods.split('id="mt-perf-cells"', 1)[1].split("</details>", 1)[0]
    assert said in fold
    # the public site drops the performance card, and with it the sentence
    # about a page it does not have
    site = " ".join(unescape(site_build.harvest_methods({})).split())
    assert "Home's FluSight Ensemble" not in site


# ---------------------------------------- UI-14: the explainers stay short

def _tip_text(html: str, tid: str) -> str:
    """The words of the toggletip `tid`'s panel."""
    pop = html.split(f'id="{tid}"', 1)[1].split(">", 1)[1]
    depth = 1
    for m in re.finditer(r"<(/?)span\b[^>]*>", pop):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            pop = pop[:m.start()]
            break
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", pop)).split())


def test_the_trimmed_explainers_stay_short():
    """Retrospective's and the Forecast tab's are shorter than the Methods
    note the bug gave as its example (448 characters), Output's lost the
    sentence the page shows itself (which dates get a card)."""
    retro = _tip_text(client.get("/retro").text, "tt-rt-page")
    fc = _tip_text(client.get("/forecast").text, "tt-fc-settings")
    out = _tip_text(client.get("/output").text, "tt-out-files")
    assert len(retro) < 448 and len(fc) < 448, (len(retro), len(fc))
    assert len(out) < 520 and "get a card" not in out, len(out)
    # what they keep: the rules, the file, the deadline
    assert "from its last completed week with the recorded settings" in retro
    assert ".flubnf-replay.zip" in retro and "read only" in retro
    assert "any other day anchors on the latest archived week before it" in fc
    assert "US is fitted and scored apart" in fc
    assert "until 11 PM Eastern" in out and "you upload them yourself" in out
    for t in (retro, fc, out):
        assert "–" not in t and "—" not in t
