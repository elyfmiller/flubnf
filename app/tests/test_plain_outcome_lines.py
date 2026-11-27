"""Plain outcome lines first, operator detail in a closed, labelled fold
(review findings B7 and B8, compromise C3).

  * the Data tab's FluSight hub card says what a check found in plain
    words: "No new flu data since Nov 21: you are up to date" when the
    hub has no new week, whatever the clone's commit count, and "New flu
    data: the week ending Nov 28 is ready to update" when it has one.
    Check for new data comes first; Update data is the primary button
    only when there is new data. The commit count, origin and the check's
    own words sit in a closed "Hub clone details" fold under the line;
  * the kit's fold (tips.fold) is closed unless the page asks, labelled
    with what it holds, and with `remember` keeps each reader's open or
    closed choice in the browser (localStorage "fold:<id>"); it works
    without storage and without script. Its script and the hub card's
    are run here on the served page (JavaScriptCore, or node as on CI);
  * the same fold holds other operator detail: Home's component versions
    (the engine's commit) and the run page's software versions.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import data as data_mod                    # noqa: E402
from app.core import runs as runs_mod                    # noqa: E402
from app.core.runs import Ledger, RunSpec                # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui.routes import data as D                      # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_pull_hub import _freshness_git, hub            # noqa: E402,F401
from test_ui_kit import render                           # noqa: E402

client = TestClient(srv.app)
F = data_mod.Freshness
TIPS_JS = Path(__file__).resolve().parents[1] / "ui" / "static" / "tips.js"
needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

UP_TO_DATE = "No new flu data since Nov 21: you are up to date"
NEW_WEEK = "New flu data: the week ending Nov 28 is ready to update"


def _behind(n=46, week="2026-11-21", **kw):
    """A check that found the clone n commits behind origin and no new
    week in the hub's file (the review's case: 46 commits, no new data)."""
    return F(week, week, n, False,
             f"{n} commits behind origin, no new week of data",
             local_live=week, remote_live=week, **kw)


# ----------------------------------------------------------- the words

@pytest.mark.parametrize("f, missing, want", [
    # commits alone, or none at all: no new week, up to date
    (_behind(), (), ("ok", False, UP_TO_DATE)),
    (F("2026-11-21", "2026-11-21", 0, True, "up to date with origin",
       local_live="2026-11-21", remote_live="2026-11-21"), (),
     ("ok", False, UP_TO_DATE)),
    # the hub's file holds newer weeks: one, two, three, or a first pull
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-11-28"), (), ("info", True, NEW_WEEK)),
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-12-05"), (),
     ("info", True, "New flu data: the weeks ending Nov 28 and Dec 5 are "
                    "ready to update")),
    (F(None, None, 3, False, "x", local_live="2026-11-21",
       remote_live="2026-12-12"), (),
     ("info", True, "New flu data: the weeks ending Nov 28 to Dec 12 are "
                    "ready to update")),
    (F(None, None, 3, False, "x", local_live=None,
       remote_live="2026-11-28"), (),
     ("info", True, "New flu data: weeks through Nov 28 are ready to "
                    "update")),
    # across the new year
    (F(None, None, 1, False, "x", local_live="2026-12-26",
       remote_live="2027-01-02"), (),
     ("info", True, "New flu data: the week ending Jan 2 is ready to "
                    "update")),
    # a newer archived week (the live file level)
    (F("2026-11-14", "2026-11-21", 2, False, "x", local_live="2026-11-21",
       remote_live="2026-11-21"), (),
     ("info", True, "New flu data: the archived week ending Nov 21 is "
                    "ready to update")),
    # the file on disk is not the hub's
    (_behind(0, tree_stale=True), (),
     ("info", True, "Your copy of the flu data differs from the hub's: "
                    "Update data replaces it")),
    # commits whose file could not be read: no claim either way
    (F(None, None, 3, False, "x", local_live="2026-11-21"), (),
     ("info", True, "The hub has changed since your last update: Update "
                    "data brings the changes in")),
    # no new week, but the comparators a pull adds are missing
    (_behind(), ["baseline", "ensemble"],
     ("info", True, "No new flu data since Nov 21, but the hub's baseline "
                    "and ensemble forecasts are missing: Update data adds "
                    "them")),
    # offline: what to do, never git's words
    (F(None, None, None, False, "fetch failed: fatal: unable to access"), (),
     ("warn", False, "Could not reach the FluSight hub: check the internet "
                     "connection and try again")),
])
def test_the_outcome_in_plain_words(f, missing, want):
    o = D._hub_outcome(f, missing)
    assert (o["state"], o["new"], o["text"]) == want
    for word in ("commit", "origin", "clone", "vintage", "upstream"):
        assert word not in o["text"].lower(), word


def test_no_outcome_before_a_check_or_without_a_hub_folder():
    assert D._hub_outcome(None) is None
    assert D._hub_outcome(F(None, None, None, False, "")) is None
    assert D._hub_outcome(F(None, None, None, False,
                            "no hub clone: there is no hub folder")) is None


def test_commits_alone_are_a_quiet_fact_in_the_fold():
    assert _behind(46).pill() == ("neutral", "46 commits behind")
    assert _behind(1).pill() == ("neutral", "1 commit behind")
    # a file on disk that is not origin's still asks for a look
    assert _behind(3, tree_stale=True).pill() == ("warn", "stale files")
    assert D._new_data(_behind(46)) is False


def test_the_checks_own_words_count_commits_properly(hub, monkeypatch):  # noqa: F811
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-07-04")
    _freshness_git(hub, monkeypatch, behind="46")
    f = data_mod.check_freshness()
    assert f.detail == "46 commits behind origin, no new week of data"
    assert D._hub_outcome(f)["text"] == ("No new flu data since Jul 4: you "
                                         "are up to date")
    _freshness_git(hub, monkeypatch, behind="1")
    assert data_mod.check_freshness().detail == \
        "1 commit behind origin, no new week of data"
    # origin's file unreadable: the count alone, no claim about weeks
    _freshness_git(hub, monkeypatch, behind="2", remote_csv="")
    assert data_mod.check_freshness().detail == "2 commits behind origin"


# ------------------------------------------------------- the hub card

def _card(monkeypatch, f) -> str:
    """The Data page as a plain (no-script) Check for new data answers
    with `f`, cut to the FluSight hub card."""
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week",
                        lambda: getattr(f, "local_live", None) or "2026-11-21")
    if f is not None:
        monkeypatch.setattr(data_mod, "check_freshness", lambda: f)
        html = client.post("/freshness").text
    else:
        html = client.get("/data").text
    return html.split('class="card hubcard"', 1)[1] \
        .split('<div class="card dt-archive">', 1)[0]


def _fold(card: str) -> str:
    return card.split('id="hub-clone-fold"', 1)[1].split("</details>", 1)[0]


def _visible(html: str) -> str:
    """Text outside scripts and tags."""
    html = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_no_new_week_says_up_to_date_and_keeps_update_data_quiet(
        hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, _behind())
    # the outcome in plain words, an ok line (the status line speaks it,
    # so the line has no role of its own)
    line = card.split('id="hub-outcome"', 1)[1].split("</div></div>", 1)[0]
    assert '<div class="uk-alert uk-alert--ok" id="hub-outcome-line">' in line
    assert f'<span class="uk-alert-text">{UP_TO_DATE}</span>' in line
    assert "role=" not in line
    # Check for new data first and the primary; Update data quiet
    assert card.index('id="hub-check"') < card.index('id="hub-pull"')
    assert 'class="gold" id="hub-check"' in card
    assert 'class="quiet" id="hub-pull"' in card
    # then the outcome, then the closed fold labelled with what it holds
    assert card.index('id="hub-pull"') < card.index('id="hub-outcome"') \
        < card.index('id="hub-clone-fold"')
    assert ('<details class="uk-fold" id="hub-clone-fold" data-remember>'
            '<summary><span class="uk-fold-sum">Hub clone details</span>'
            '</summary>') in card
    # the commit count and origin live in the fold, and nowhere else on
    # the card
    fold = _fold(card)
    assert ('<span class="uk-badge uk-badge--neutral" id="hub-pill" '
            'data-state="neutral">') in fold
    assert '<span class="uk-badge-t">46 commits behind</span>' in fold
    assert ('<p class="hint" id="hub-detail">46 commits behind origin, no '
            'new week of data</p>') in fold
    outside = _visible(card.replace(card.split('<details class="uk-fold" '
                                               'id="hub-clone-fold"', 1)[1]
                                    .split("</details>", 1)[0], ""))
    for word in ("commit", "origin"):
        assert word not in outside.lower(), word
    # no warning mark for commits
    assert "uk-badge--warn" not in card and "uk-alert--warn" not in card


def test_a_new_week_makes_update_data_the_primary(hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, F(None, None, 3, False, "x",
                                local_live="2026-11-21",
                                remote_live="2026-11-28"))
    assert '<div class="uk-alert uk-alert--info" id="hub-outcome-line">' in card
    assert f'<span class="uk-alert-text">{NEW_WEEK}</span>' in card
    # the check still comes first; the pull is now the primary
    assert card.index('id="hub-check"') < card.index('id="hub-pull"')
    assert 'class="quiet" id="hub-check"' in card
    assert 'class="gold" id="hub-pull"' in card


def test_before_a_check_no_outcome_and_the_fold_says_not_checked(
        hub, monkeypatch):  # noqa: F811
    card = _card(monkeypatch, None)
    assert '<div id="hub-outcome"></div>' in card
    assert '<span class="uk-badge-t">not checked</span>' in _fold(card)
    assert '<p class="hint" id="hub-detail" hidden></p>' in _fold(card)
    assert 'class="gold" id="hub-check"' in card


def test_the_json_answer_carries_the_outcome(hub, monkeypatch):  # noqa: F811
    monkeypatch.setattr(data_mod, "check_freshness", lambda: _behind())
    r = client.post("/freshness", headers={"Accept": "application/json"})
    assert r.json() == {
        "ok": True, "fresh": False, "pill": "neutral",
        "words": "46 commits behind",
        "detail": "46 commits behind origin, no new week of data",
        "new_data": False,
        "outcome": {"state": "ok", "new": False, "text": UP_TO_DATE}}


# ------------------------------------------------- the kit's fold macro

def test_the_fold_remembers_only_when_asked_and_named():
    # a fold that remembers: data-remember after the page's own state
    html = render('{% call t.fold("Hub clone details", id="x", remember=True) %}'
                  "b{% endcall %}")
    assert html.startswith('<details class="uk-fold" id="x" data-remember>'
                           '<summary><span class="uk-fold-sum">Hub clone '
                           'details</span></summary>')
    assert render('{% call t.fold("a", id="x", open=True, remember=True) %}'
                  "b{% endcall %}").startswith(
        '<details class="uk-fold" id="x" open data-remember><summary>')
    # nothing to key it by: no memory
    assert "data-remember" not in render(
        '{% call t.fold("a", remember=True) %}b{% endcall %}')
    # every other fold is drawn as before: closed unless asked, no memory
    assert render('{% call t.fold("a", id="y") %}b{% endcall %}').startswith(
        '<details class="uk-fold" id="y"><summary>')


# ------------------------------------------ the fold's memory, as served

#: the page's browser, as far as tips.js and the hub card's script reach:
#: `window` with listeners and a storage that logs its writes (or throws),
#: `location`, a details element's `open` (its toggle event queued, as a
#: browser queues it, and only on a change), a button's className
_PRELUDE = r"""
var LS = %(ls)s, WRITES = [], DENY = %(deny)s;
var window = {L: {}, addEventListener: function (t, f) {
  (this.L[t] = this.L[t] || []).push(f); }};
Object.defineProperty(window, 'localStorage', {get: function () {
  if (DENY) throw new Error('SecurityError: storage is off');
  return {getItem: function (k) {
            return Object.prototype.hasOwnProperty.call(LS, k) ? LS[k] : null; },
          setItem: function (k, v) { WRITES.push([k, String(v)]);
                                     LS[k] = String(v); }};
}});
var location = {hash: %(hash)s, reload: function () { location.reloaded = true; }};
document.documentElement = document.querySelector('html');
document.querySelectorAll('details').forEach(function (d) {
  Object.defineProperty(d, 'open', {
    get: function () { return this.hasAttribute('open'); },
    set: function (v) {
      var was = this.hasAttribute('open'), self = this;
      if (v) this.setAttribute('open', ''); else this.removeAttribute('open');
      if (!!v !== was) setTimeout(function () {
        self.dispatchEvent({type: 'toggle', bubbles: false}); });
    }});
});
document.querySelectorAll('button').forEach(function (b) {
  Object.defineProperty(b, 'className', {
    get: function () { return this.getAttribute('class') || ''; },
    set: function (v) { this.setAttribute('class', v); }});
});
"""


def _prelude(ls=None, deny=False, hash_="") -> str:
    return _PRELUDE % {"ls": json.dumps(ls or {}), "deny": json.dumps(deny),
                       "hash": json.dumps(hash_)}


def _data_page(monkeypatch) -> str:
    monkeypatch.setattr(data_mod, "vintages", lambda: [])
    monkeypatch.setattr(data_mod, "live_newest_week", lambda: "2026-11-21")
    return client.get("/data").text


_STATE = """
flush();
var d = document.getElementById('hub-clone-fold');
return {open: d.open, writes: WRITES, ls: LS};
"""


@needs_js
def test_a_fold_with_nothing_kept_stays_closed_and_writes_nothing(
        hub, monkeypatch, tmp_path):  # noqa: F811
    out = SD.run(tmp_path, _data_page(monkeypatch), [TIPS_JS], _STATE,
                 prelude=_prelude())
    assert out == {"open": False, "writes": [], "ls": {}}


@needs_js
def test_a_fold_left_open_opens_again_and_the_readers_choice_is_kept(
        hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    # left open last time: open again, and opening it is not a new write
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "1"}))
    assert out == {"open": True, "writes": [],
                   "ls": {"fold:hub-clone-fold": "1"}}
    # the reader closes it, then opens it: each choice kept under its id
    out = SD.run(tmp_path, page, [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold');
      d.open = false; flush();
      var closed = LS['fold:hub-clone-fold'];
      d.open = true; flush();
      return [closed, LS['fold:hub-clone-fold'], WRITES.length];
    """, prelude=_prelude({"fold:hub-clone-fold": "1"}))
    assert out == ["0", "1", 2]
    # kept closed: the page's closed fold stays closed
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "0"}))
    assert out["open"] is False


@needs_js
def test_without_storage_the_fold_still_opens_and_closes(
        hub, monkeypatch, tmp_path):  # noqa: F811
    out = SD.run(tmp_path, _data_page(monkeypatch), [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold'), was = d.open;
      d.open = true; flush();
      return [was, d.open, WRITES.length];
    """, prelude=_prelude(deny=True))
    assert out == [False, True, 0]


@needs_js
def test_a_fold_the_page_asks_open_stays_open(hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch).replace(
        'id="hub-clone-fold" data-remember>',
        'id="hub-clone-fold" open data-remember>')
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude({"fold:hub-clone-fold": "0"}))
    assert out["open"] is True and out["writes"] == []


@needs_js
def test_a_link_into_a_closed_fold_opens_it_without_counting_as_a_choice(
        hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    # on load: the address points at the badge inside the fold
    out = SD.run(tmp_path, page, [TIPS_JS], _STATE,
                 prelude=_prelude(hash_="#hub-pill"))
    assert out == {"open": True, "writes": [], "ls": {}}
    # on a hash change after load
    out = SD.run(tmp_path, page, [TIPS_JS], """
      flush();
      var d = document.getElementById('hub-clone-fold'), was = d.open;
      location.hash = '#hub-detail';
      (window.L.hashchange || []).forEach(function (f) { f({}); });
      flush();
      return [was, d.open, WRITES.length];
    """, prelude=_prelude())
    assert out == [False, True, 0]


# --------------------------------------- the hub card's script, as served

def _hub_script(page: str, tmp_path: Path) -> Path:
    """The Data page's inline script for the hub card's two buttons, as
    a file the harness runs after tips.js."""
    src = next(c.split("</script>", 1)[0] for c in page.split("<script>")
               if ".hubacts form" in c.split("</script>", 1)[0])
    p = tmp_path / "hub-card.js"
    p.write_text(src, encoding="utf-8")
    return p


_CHECK = r"""
var ANSWERS = %s, asked = [];
window.fetch = function (url, opts) {
  asked.push([url, opts.method, opts.headers.Accept]);
  var a = ANSWERS.shift();
  function done(v) { return {then: function (f) { return done(f(v)); },
                             'catch': function () { return this; }}; }
  return done({json: function () { return a; }});
};
var fetch = window.fetch;
"""

_PRESS = r"""
flush();
var out = [];
for (var i = 0; i < 2; i++) {
  var ev = {type: 'submit', bubbles: true, defaultPrevented: false,
            preventDefault: function () { this.defaultPrevented = true; }};
  document.getElementById('hub-check').parentNode.dispatchEvent(ev);
  var pill = document.getElementById('hub-pill');
  out.push({outcome: document.getElementById('hub-outcome').innerHTML,
            status: document.getElementById('hub-status').textContent,
            pill: [pill.getAttribute('data-state'), pill.innerHTML],
            detail: [document.getElementById('hub-detail').textContent,
                     document.getElementById('hub-detail').hidden],
            check: document.getElementById('hub-check').className,
            pull: document.getElementById('hub-pull').className,
            busy: document.getElementById('hub-check').disabled,
            error: document.getElementById('hub-error').innerHTML || ''});
}
return {asked: asked, out: out};
"""


@needs_js
def test_the_cards_script_shows_each_checks_outcome(hub, monkeypatch, tmp_path):  # noqa: F811
    page = _data_page(monkeypatch)
    answers = []
    for f in (_behind(), F(None, None, 3, False, "new data upstream",
                           local_live="2026-11-21", remote_live="2026-11-28")):
        monkeypatch.setattr(data_mod, "check_freshness", lambda f=f: f)
        answers.append(client.post(
            "/freshness", headers={"Accept": "application/json"}).json())
    got = SD.run(tmp_path, page, [TIPS_JS, _hub_script(page, tmp_path)],
                 _PRESS, prelude=_prelude() + _CHECK % json.dumps(answers))
    assert got["asked"] == [["/freshness", "POST", "application/json"]] * 2
    same, new = got["out"]
    # no new week: the ok line, spoken by the status line; the count in
    # the fold as a quiet fact; Check for new data stays the primary
    assert 'class="uk-alert uk-alert--ok"' in same["outcome"]
    assert f'<span class="uk-alert-text">{UP_TO_DATE}</span>' in same["outcome"]
    assert "role=" not in same["outcome"]
    assert same["status"] == UP_TO_DATE
    assert same["pill"][0] == "neutral" and "46 commits behind" in same["pill"][1]
    assert same["detail"] == ["46 commits behind origin, no new week of data",
                              False]
    assert (same["check"], same["pull"], same["busy"]) == ("gold", "quiet", False)
    assert same["error"] == ""
    # a new week: the info line, and Update data becomes the primary
    assert 'class="uk-alert uk-alert--info"' in new["outcome"]
    assert f'<span class="uk-alert-text">{NEW_WEEK}</span>' in new["outcome"]
    assert new["status"] == NEW_WEEK
    assert (new["check"], new["pull"]) == ("quiet", "gold")


def test_the_cards_busy_words_are_plain():
    src = (Path(__file__).resolve().parents[1] / "ui" / "templates"
           / "data.html").read_text(encoding="utf-8")
    assert ("busy(true,pull?'Updating the flu data':'Checking the FluSight "
            "hub for new data');") in src
    assert "Checking origin" not in src and "Pulling the hub clone" not in src


# ------------------------------------- operator detail on other pages

def test_home_keeps_component_versions_in_a_fold(monkeypatch):
    html = client.get("/").text
    card = html.split('<div class="card hm-setup">', 1)[1]
    # the outcome (the heading's badge) first, outside the fold
    assert card.index('id="hm-setup-state"') < card.index('id="hm-versions-fold"')
    assert ('<details class="uk-fold hm-versions-fold" id="hm-versions-fold" '
            'data-remember><summary><span class="uk-fold-sum">Component '
            'versions</span></summary>') in card
    fold = card.split('id="hm-versions-fold"', 1)[1].split("</details>", 1)[0]
    assert 'aria-label="Component versions"' in fold


def _run_page(tmp_path, monkeypatch, build) -> str:
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {"pybnf": "1.8.1", "pybnf_build": build})
    led.close_run(rid, "ok", {})
    return client.get(f"/runs/{rid}").text


def test_the_run_page_keeps_software_versions_in_a_fold(tmp_path, monkeypatch):
    from app.core import engine_build as EB
    prod = {"branch": EB.PRODUCTION_ENGINE_BRANCH,
            "commit": EB.PRODUCTION_ENGINE_COMMIT[:8], "dirty": False,
            "source": "git"}
    page = _run_page(tmp_path, monkeypatch, prod)
    rec = page.split('class="card runrec"', 1)[1]
    assert ('<details class="uk-fold" id="run-versions" data-remember>'
            '<summary><span class="uk-fold-sum">Software versions</span>'
            '</summary>') in rec
    fold = rec.split('id="run-versions"', 1)[1].split("</details>", 1)[0]
    assert "<dt>pybnf</dt><dd>1.8.1</dd>" in fold
    assert "<dt>PyBNF build</dt>" in fold
    assert "Produced by" not in page
    # another build than production says so on the fold's own line
    other = {"branch": "main", "commit": "deadbeef", "dirty": False,
             "source": "git"}
    page = _run_page(tmp_path / "other", monkeypatch, other)
    summary = page.split('id="run-versions"', 1)[1].split("</summary>", 1)[0]
    assert '<span class="uk-fold-sum">Software versions</span>' in summary
    assert 'id="run-versions-warn"' in summary
    assert '<span class="uk-badge-t">not the production build</span>' in summary
