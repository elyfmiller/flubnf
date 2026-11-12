"""Home on a first run (P6 home-and-tabs: findings F34, F39, F43 and F77
of the 2026-11-09 usability review), tested on the page the server
renders, its markup parsed (served_dom.tree) and its own script run
(served_dom.run), never on template text.

  * With no forecast to map, Start here comes before the map, and its
    steps say where this computer stands: Data done "through <newest
    week>", Forecast current, with "Groundhog only on this computer" when
    the engine is absent (not when it is broken: the Setup line says
    that), Output to do. The cold paint, with no stored run, already
    puts the card there, its steps plain until the reload reads the
    data. Ely's weekly view keeps the map first and the steps plain.
  * Start here's extras: the Sandbox, relabelled, and one way into your
    own data, the Forecast tab's Your data.
  * A "Setup incomplete." line under the hero names what is not
    installed and links to the Setup card. While a cold launch still
    probes versions it names what check() found, and the Setup badge's
    recount keeps it in step.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import flubnf.settings as fs
from app.core import data as core_data
from app.core import runs as runs_mod
from app.ui import pipeline, shared
from app.ui import server as srv
from app.ui import state as ui_state
from app.ui import templating
from app.ui import versions as V
from app.ui.routes import home as H

import served_dom as SD                               # noqa: E402
from test_outlook_toggle import _latest                # noqa: E402

client = TestClient(srv.app)
needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

ENGINE = H.ENGINE_NAME
INSTALLED = {"pybnf": "1.0", "bngsim": "0.15.1", "bionetgen": "2.9",
             "perl": "5.38", "fastapi": "0.1", "plotly": "7.0"}
HUB_GONE = ("FLUBNF_HUB", "/x/auxiliary-data",
            "FluSight hub clone (truth vintages, locations)")
WEEK = "2026-10-31"


# ------------------------------------------------------------- the page

def _walk(node, out):
    """Every element under `node`, in document order."""
    for k in node["kids"]:
        if isinstance(k, dict):
            out.append(k)
            _walk(k, out)
    return out


class Page:
    """The served page as elements in document order."""

    def __init__(self, html: str):
        self.html = html
        self.els = _walk(SD.tree(html), [])

    def find(self, pred, under=None):
        els = _walk(under, []) if under is not None else self.els
        return [e for e in els if pred(e)]

    def one(self, pred, under=None):
        hits = self.find(pred, under)
        assert len(hits) == 1, len(hits)
        return hits[0]

    def at(self, el) -> int:
        return next(i for i, e in enumerate(self.els) if e is el)

    def by_id(self, i):
        return self.one(lambda e: e["attrs"].get("id") == i)

    def card(self, name):
        return self.one(lambda e: name in _cls(e) and "card" in _cls(e))


def _cls(e):
    return e["attrs"].get("class", "").split()


def _text(e) -> str:
    out = []

    def go(n):
        for k in n["kids"]:
            if isinstance(k, str):
                out.append(k)
            else:
                go(k)
    go(e)
    return " ".join("".join(out).split())


def _steps(p: Page):
    """Start here's steps: (label, its link, state, aria-current, caption,
    any "?" or button inside)."""
    ol = p.one(lambda e: e["tag"] == "ol"
               and e["attrs"].get("aria-label") == "Start here")
    out = []
    for li in [k for k in ol["kids"] if isinstance(k, dict)]:
        state = next(c[len("uk-step--"):] for c in _cls(li)
                     if c.startswith("uk-step--"))
        label = p.one(lambda e: "uk-step-label" in _cls(e), li)
        a = p.one(lambda e: e["tag"] == "a", label)
        meta = p.find(lambda e: "uk-step-meta" in _cls(e), li)
        marks = p.find(lambda e: e["tag"] == "button"
                       or "tipbtn" in _cls(e) or "uk-tt" in _cls(e), li)
        out.append((_text(label), a["attrs"]["href"], state,
                    li["attrs"].get("aria-current"),
                    _text(meta[0]) if meta else "", bool(marks)))
    return out


def _get(path="/") -> Page:
    r = client.get(path)
    assert r.status_code == 200, r.text[:300]
    return Page(r.text)


class _Data:
    """state.data_mod with Home's newest-week call counted (and its
    answer set); every other name is the data module's own."""

    def __init__(self, week):
        self.week, self.calls = week, 0

    def __getattr__(self, name):
        return getattr(core_data, name)

    def newest_week(self):
        self.calls += 1
        if isinstance(self.week, Exception):
            raise self.week
        return self.week


class _ColdStart:
    """state._WARM_DONE on a cold launch: the warm pass has not landed,
    and the route's wait for it returns at once."""

    def is_set(self):
        return False

    def wait(self, timeout=None):
        return False


@pytest.fixture
def empty(tmp_path, monkeypatch):
    """An empty state folder (no run), the warm pass done, the hub's
    newest week WEEK, the engine absent."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    shared._invalidate_scans()
    data = _Data(WEEK)
    monkeypatch.setattr(ui_state, "data_mod", data)
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: "absent")
    yield data
    shared._invalidate_scans()


# ---------------------------------------------- F34, F39: first run

def test_a_first_run_puts_start_here_before_the_map(empty):
    p = _get()
    start, outlook = p.card("hm-start"), p.card("hm-outlook")
    assert p.at(start) < p.at(outlook)
    # the record keeps its own row, alone in its grid (home.css spans it)
    grid = p.one(lambda e: "homeperf" in _cls(e))
    assert [_cls(k) for k in grid["kids"] if isinstance(k, dict)] == \
        [["card", "hm-perf"]]
    # the map still says there is no forecast, with its one action
    assert p.by_id("hm-nofc")
    assert _steps(p) == [
        ("Data", "/data", "done", None, f"through {WEEK}", False),
        ("Forecast", "/forecast", "current", "step",
         "Groundhog only on this computer", False),
        ("Output", "/output", "todo", None, "", False)]
    assert empty.calls == 1


@pytest.mark.parametrize("engine,caption", [
    ("absent", "Groundhog only on this computer"),
    # a broken install refuses a run with every model rather than running
    # the Groundhog alone: the Setup line names it, the step says nothing
    ("broken", ""),
    ("ready", "")])
def test_the_forecast_step_says_groundhog_only_when_the_engine_is_absent(
        empty, monkeypatch, engine, caption):
    monkeypatch.setattr(pipeline, "_pf_engine_state", lambda: engine)
    forecast = _steps(_get())[1]
    assert forecast[:4] == ("Forecast", "/forecast", "current", "step")
    assert forecast[4] == caption


@pytest.mark.parametrize("week, why", [
    (None, "The hub folder {hub} holds no weeks of data. Move or rename the "
     "folder, then run ./setup.sh and relaunch the console: setup fetches "
     "a fresh clone."),
    (OSError("no hub data"), "The hub data could not be read: no hub data. "
     "If it stays so, move or rename the folder, then run ./setup.sh and "
     "relaunch the console: setup fetches a fresh clone.")])
def test_without_data_the_data_step_is_current(empty, monkeypatch, week,
                                               why):
    """Data is the step to take, and its caption says why (review of #93
    at d160002b, finding 1: the reason was worked out and never shown) and
    what to do (review of #93 at 3120298e, finding 4)."""
    monkeypatch.setattr(templating, "_platform", lambda: "linux")
    empty.week = week
    steps = _steps(_get())
    assert [s[2:5] for s in steps] == [
        ("current", "step", why.format(hub=core_data.HUB)),
        ("todo", None, "Groundhog only on this computer"),
        ("todo", None, "")]


def test_without_the_hub_the_data_step_is_current(empty, monkeypatch,
                                                   tmp_path, hub_check_real):
    """No FluSight hub clone: a run is refused, whatever week the shipped
    snapshots hold, so Data is the step to take, and the line under the
    hero names the data."""
    monkeypatch.setattr(ui_state, "data_mod", core_data)
    monkeypatch.setattr(core_data, "HUB", tmp_path / "nohub")
    monkeypatch.setattr(core_data, "newest_week", lambda: WEEK)
    for k, v in INSTALLED.items():
        monkeypatch.setitem(V.VERSIONS, k, v)
    monkeypatch.setattr(templating, "_platform", lambda: "linux")
    p = _get()
    assert [s[2:5] for s in _steps(p)] == [
        ("current", "step", f"There is no hub folder at {tmp_path / 'nohub'}. "
         "To fetch the data, run ./setup.sh and relaunch the console."),
        ("todo", None, "Groundhog only on this computer"),
        ("todo", None, "")]
    assert "FluSight data" in _line(p)[1]


def test_the_cold_paint_puts_start_here_where_the_reload_will(empty,
                                                             monkeypatch):
    """outlook_pending paints the silhouette and reloads once the map is
    ready. With no stored run that page has no forecast, so Start here is
    already before the map, its steps plain, and the cold paint never
    reads the data (the import it exists to avoid)."""
    monkeypatch.setattr(ui_state, "_WARM_DONE", _ColdStart())
    monkeypatch.setattr(H, "_outlook_ready", lambda: False)
    p = _get()
    assert p.by_id("hm-prep")                         # the preparing card
    start, outlook = p.card("hm-start"), p.card("hm-outlook")
    assert p.at(start) < p.at(outlook)
    grid = p.one(lambda e: "homeperf" in _cls(e))
    assert start not in _walk(grid, [])
    assert [s[2:5] for s in _steps(p)] == [("todo", None, "")] * 3
    assert empty.calls == 0


def test_the_weekly_view_keeps_the_map_first(empty, tmp_path, monkeypatch):
    """With a stored run, Home is as before: the map, then the record and
    Start here side by side, the steps plain."""
    _latest(tmp_path, monkeypatch)
    p = _get()
    assert "2098-01-03" in _text(p.one(lambda e: e.get("tag") == "h2"
                                       and e["attrs"].get("id") == "h-hm-map"))
    start, outlook = p.card("hm-start"), p.card("hm-outlook")
    assert p.at(outlook) < p.at(start)
    grid = p.one(lambda e: "homeperf" in _cls(e))
    assert [_cls(k) for k in grid["kids"] if isinstance(k, dict)] == \
        [["card", "hm-perf"], ["card", "hm-start"]]
    assert _steps(p) == [("Data", "/data", "todo", None, "", False),
                         ("Forecast", "/forecast", "todo", None, "", False),
                         ("Output", "/output", "todo", None, "", False)]
    assert empty.calls == 0


# ---------------------------------------------------- F77: the way in

@pytest.mark.parametrize("weekly", [False, True])
def test_start_here_offers_the_sandbox_and_your_own_data(
        empty, tmp_path, monkeypatch, weekly):
    if weekly:
        _latest(tmp_path, monkeypatch)
    p = _get()
    more = p.one(lambda e: "hm-start-more" in _cls(e))
    links = [(a["attrs"]["href"], _text(a))
             for a in p.find(lambda e: e["tag"] == "a", more)]
    assert links == [
        ("/retro", "Replay a past season"),
        ("/sandbox", "Sandbox: write and fit your own model"),
        ("/forecast?tab=own", "Your data: forecast a weekly series")]
    # the link lands on the Forecast tab's Your data (the upload box, or
    # the first stored dataset)
    own = client.get(links[2][0])
    assert own.status_code == 200
    tab = Page(own.text).one(lambda e: e["tag"] == "a"
                             and e["attrs"].get("href") == "/forecast?tab=own"
                             and "aria-current" in e["attrs"])
    assert _text(tab) == "Your data"


# ------------------------------------------- F43: what this computer lacks

def _home(monkeypatch, missing, versions):
    monkeypatch.setattr(fs, "check", lambda verbose=True: missing)
    monkeypatch.setattr(H, "_engine_known", lambda: False)
    for k, v in versions.items():
        monkeypatch.setitem(V.VERSIONS, k, v)
    return _get()


def _line(p: Page):
    """The line under the hero: (shown, its words, its action's links as
    (target, text))."""
    el = p.by_id("hm-gaps-top")
    words = p.one(lambda e: "uk-alert-text" in _cls(e), el)
    action = p.one(lambda e: "uk-alert-action" in _cls(e), el)
    return ("hidden" not in el["attrs"], _text(words),
            [(a["attrs"]["href"], _text(a))
             for a in p.find(lambda e: e["tag"] == "a", action)])


@pytest.mark.parametrize("weekly", [False, True])
def test_a_missing_component_is_said_under_the_hero(
        empty, tmp_path, monkeypatch, weekly):
    """The suite's FluSight hub is a missing folder, and its machine has
    no engine: the line names both, before Start here and the map, and
    its link is a real one to the Setup card's heading."""
    if weekly:
        _latest(tmp_path, monkeypatch)
    for k, v in INSTALLED.items():
        monkeypatch.setitem(V.VERSIONS, k, v)
    missing = fs.check(verbose=False)
    assert {m[0] for m in missing} >= {"FLUBNF_HUB"}
    names = H._setup_gaps(missing, V.VERSIONS, H._engine_known())
    p = _get()
    line = p.by_id("hm-gaps-top")
    assert p.at(line) < p.at(p.card("hm-outlook"))
    assert p.at(line) < p.at(p.card("hm-start"))
    assert _line(p) == (True, f"Setup incomplete. {len(names)} not "
                        f"installed: {', '.join(names)}.",
                        [("#h-hm-setup", "Setup")])
    assert "FluSight data" in names
    # the link's target is the Setup card's heading, whose badge counts
    # the same names
    assert p.by_id("h-hm-setup")["tag"] == "h2"
    assert _text(p.by_id("hm-missing")) == f"{len(names)} not installed"
    # present from the first paint, not news: no live role, no "?"
    assert "role" not in line["attrs"]
    assert not p.find(lambda e: e["tag"] == "button" or "tipbtn" in _cls(e),
                      line)


def test_nothing_missing_says_nothing(empty, monkeypatch):
    p = _home(monkeypatch, [], INSTALLED)
    assert not p.find(lambda e: e["attrs"].get("id") == "hm-gaps-top")
    assert p.by_id("hm-installed")


def test_a_version_read_as_not_installed_counts_as_the_badge_does(
        empty, monkeypatch):
    p = _home(monkeypatch, [], dict(INSTALLED, plotly="not installed"))
    assert _line(p)[:2] == (True, "Setup incomplete. 1 not installed: "
                            "Plotly.")


def test_a_cold_launch_names_what_the_check_found(empty, monkeypatch):
    """Versions still probing: the line names check()'s components, and
    is there hidden when the check found none, for the recount to show."""
    pending = {k: V.VERSION_PENDING for k in INSTALLED}
    p = _home(monkeypatch, [HUB_GONE], pending)
    assert p.by_id("hm-checking")                    # the badge waits
    assert _line(p) == (True, "Setup incomplete. 1 not installed: "
                        "FluSight data.", [("#h-hm-setup", "Setup")])
    p = _home(monkeypatch, [], pending)
    assert _line(p)[0] is False


# The Setup badge's recount on the page as served: base.html's version
# poll writes each value into its data-vkey span, and the recount (an
# observer on the versions box) draws the badge again and keeps the line
# under the hero with it. STUBS stand in for the browser's observer and
# the kit's FluBNFUI (its markup is the badge's, not the line's).

STUBS = """
var OBS = [];
globalThis.window = globalThis;
globalThis.MutationObserver = function (cb) {
  OBS.push(cb); this.observe = function () {}; };
globalThis.FluBNFUI = {badge: function (k, w) { return w; },
                       tip: function () { return ""; }};
"""

PROBE = """
function land(vals) {
  var s = document.querySelectorAll('[data-vkey]');
  for (var i = 0; i < s.length; i++) {
    var k = s[i].getAttribute('data-vkey');
    if (k in vals) s[i].textContent = vals[k];
  }
  for (var j = 0; j < OBS.length; j++) OBS[j]([]);
}
function line() {
  var el = document.getElementById('hm-gaps-top');
  return [!el.hidden, el.querySelector('[data-gaps-words]').textContent];
}
"""


def _recount(tmp_path, html, body):
    script = next(s for s in re.findall(r"<script>(.*?)</script>", html, re.S)
                  if "function recount()" in s)
    f = tmp_path / "home-recount.js"
    f.write_text(script, encoding="utf-8")
    return SD.run(tmp_path / "js", html, [f], PROBE + body, prelude=STUBS)


@needs_js
def test_the_recount_keeps_the_line_with_the_badge(tmp_path, empty,
                                                   monkeypatch):
    pending = {k: V.VERSION_PENDING for k in INSTALLED}
    html = _home(monkeypatch, [], pending).html
    got = _recount(tmp_path, html, """
      var out = [line()];
      land({pybnf: "1.0", bngsim: "0.15.1", bionetgen: "2.9", perl: "5.38",
            fastapi: "0.1", plotly: "not installed"});
      out.push(line());
      land({plotly: "7.0"});
      out.push(line());
      return [OBS.length].concat(out);""")
    assert got == [1, [False, "0 not installed: ."],
                   [True, "1 not installed: Plotly."],
                   [False, "0 not installed: ."]]


@needs_js
def test_the_recount_keeps_what_the_check_found(tmp_path, empty,
                                                monkeypatch):
    pending = {k: V.VERSION_PENDING for k in INSTALLED}
    html = _home(monkeypatch, [HUB_GONE], pending).html
    got = _recount(tmp_path, html, """
      var out = [line()];
      land({pybnf: "resolving…"});                     // still probing
      out.push(line());
      land({pybnf: "not installed", bngsim: "not installed",
            bionetgen: "2.9", perl: "5.38", fastapi: "0.1", plotly: "7.0"});
      out.push(line());
      return out;""")
    assert got == [[True, "1 not installed: FluSight data."],
                   [True, "1 not installed: FluSight data."],
                   [True, f"2 not installed: FluSight data, {ENGINE}."]]
