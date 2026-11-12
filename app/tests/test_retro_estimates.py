"""The Retrospective Settings form before Start (UX package P10).

  * F53: the Oracle preset's option says what the replay costs, from the
    engine's cost model (app/core/estimates.py) over the picked season's
    weeks at the form's locations, Independent Runs, particles and width:
    "here" only on this computer's own record, only the weeks left when a
    resume would run them, nothing for a season with no hub weeks. The
    page's script (retro_progress.js FluBNFRetroCost, on estimate.js)
    redoes the words on every change, as the server words them.
  * F63: the 6-state panel is one constant, in the order the run record
    and every week's manifest keep, and its option names the states.
  * F46: a fresh install says so and links the measured record.
  * Nothing the form posts changes.
"""
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import estimates, replay_bundle, retro       # noqa: E402
from app.core.engines import pf                            # noqa: E402
from app.core.retro_settings import PANEL6                 # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402
from test_retro_archive import _season_tree                # noqa: E402

client = TestClient(srv.app)

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"
EST_JS, TICKER_JS = STATIC / "estimate.js", STATIC / "retro_progress.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")

SEASON, EMPTY = "2098-99", "2097-98"
START = "2098-08-01"
WEEKS = ["2098-10-03", "2098-10-10", "2098-10-17", "2098-10-24"]
OLD_PANEL = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
             "California"]
BASE = "Oracle SIHRS + Groundhog"
PF_OPT = re.compile(r'<option value="pf" data-base="Oracle SIHRS \+ '
                    r'Groundhog">([^<]*)</option>')


@pytest.fixture
def world(tmp_path, monkeypatch):
    """An empty retro root, two seasons (SEASON with four hub weeks, EMPTY
    with none), the worker stubbed to record what it was given, and the
    remembered form cleared."""
    rr = tmp_path / "retro"
    rr.mkdir()
    monkeypatch.setattr(RS, "RETRO_ROOT", rr)
    monkeypatch.setattr(RS, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON, EMPTY])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(WEEKS) if s == SEASON else [])
    started = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: started.append(list(a[1])))
    status, form = dict(RS._retro_status), dict(ui_retro._last_retro_form)
    RS._retro_status.clear()
    ui_retro._last_retro_form.clear()
    ui_shared._invalidate_scans()
    yield {"root": rr, "started": started}
    RS._retro_status.clear()
    RS._retro_status.update(status)
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update(form)
    ui_shared._invalidate_scans()


@pytest.fixture(params=["private", "public"])
def engine(request, monkeypatch):
    """Each engine set here, never taken from the shell or the install."""
    monkeypatch.setenv("FLUBNF_ENGINE", request.param)
    return request.param


def _page(**form) -> str:
    """/retro with `form` as the remembered Settings form."""
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update(form)
    ui_shared._invalidate_scans()
    return client.get("/retro").text


def _pf(html: str) -> str:
    return PF_OPT.search(html).group(1)


def _text(words: str) -> str:
    return BASE + (f" ({words})" if words else "")


def _locs(scope: str, national: bool = True, picked: int = 0) -> int:
    n = {"panel6": 6, "all": len(ui_retro._retro_state_names())}.get(
        scope, picked)
    return n + 1 if n and national else n


def _oracle_record(root: Path, weeks: list, seconds: dict | None = None,
                   engine: str = "pf", width: int = 4,
                   status: str = "stopped") -> None:
    """A run record of the Oracle preset (or `engine`) over the panel with
    US, and `weeks` stored."""
    root.mkdir(parents=True, exist_ok=True)
    for w in weeks:
        wd = root / "weeks" / w
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "samples.json").write_text(json.dumps({"asof": w, "pf": {}}))
    meta = {"season": SEASON, "status": status, "total_weeks": len(WEEKS),
            "settings": {"season": SEASON, "engine": engine, "scope": "panel6",
                         "locations": OLD_PANEL + ["US"], "replicates": 3,
                         "particles": 10_000, "width": width}}
    if seconds is not None:
        meta["week_seconds"] = seconds
    retro.write_meta(root, meta)


# ------------------------------------------------------------- F63: panel

def test_the_panel_keeps_the_order_runs_record_and_names_its_states(world):
    """PANEL6 is the route's old literal, in its order (each week's manifest
    compares it with ==); the option sorts the abbreviations for reading."""
    assert list(PANEL6) == OLD_PANEL
    html = _page()
    assert ('<option value="panel6" data-n="6">6-state panel '
            "(AK, CA, NY, PA, VT, WY)</option>") in html
    assert "(fast)" not in html
    for national in ("0", "1"):
        r = client.post("/retro/run", data={
            "season": SEASON, "locations": "panel6", "national": national,
            "engine": "analogue", "knob.groundhog.zero_anchor": "abstain"},
            follow_redirects=False)
        assert r.status_code == 303
        RS._retro_status.clear()          # the stub never ends its claim
    us = ui_retro._retro_national_name()
    assert world["started"] == [OLD_PANEL, OLD_PANEL + [us]]


# ------------------------------------------- nothing the form posts changes

class _FormDOM(HTMLParser):
    """The Run form's controls, in order, with their attributes; selects
    with their options (attributes, text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.form, self.controls, self._in, self._opt = None, [], False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "rt-run-form":
            self.form, self._in = a, True
        elif not self._in:
            return
        elif tag == "input":
            self.controls.append(("input", a, None))
        elif tag == "select":
            self.controls.append(("select", a, []))
        elif tag == "option" and self.controls:
            self._opt = [a, ""]
            self.controls[-1][2].append(self._opt)

    def handle_data(self, data):
        if self._opt is not None:
            self._opt[1] += data

    def handle_endtag(self, tag):
        if tag == "option":
            self._opt = None
        elif tag == "form" and self._in:
            self._in = False


def _dom(html: str) -> _FormDOM:
    d = _FormDOM()
    d.feed(html.split("<main", 1)[1])
    return d


def _form_data(html: str) -> list:
    """What the browser posts for the form as rendered (FormData): every
    enabled named control; a checkbox when ticked; a select's selected
    option (else its first), whose value is its text when it has none."""
    out = []
    for kind, a, opts in _dom(html).controls:
        name = a.get("name")
        if not name or "disabled" in a:
            continue
        if kind == "input":
            if a.get("type") == "checkbox":
                if "checked" in a:
                    out.append((name, a.get("value", "on")))
            else:
                out.append((name, a.get("value", "")))
        elif opts:
            pick = next((o for o in opts if "selected" in o[0]), opts[0])
            out.append((name, pick[0].get("value", pick[1])))
    return out


def test_the_form_posts_exactly_what_it_did(world, pf_engine_ready):
    """The cost rides in attributes of the form and of two options with
    values of their own: for both presets and every scope, the posted
    fields are the remembered ones, the panel's, mode and confirm."""
    for scope in ("panel6", "all", "custom"):
        for preset in ("pf", "analogue"):
            form = {"season": SEASON, "locations": scope, "national": "1",
                    "width": "3", "engine": preset,
                    "custom_locations": ["Ohio", "Utah"],
                    "knobs": {"groundhog.zero_anchor": "blend"}}
            html = _page(**form)
            data = _form_data(html)
            kp = ui_retro._knob_panel("retro", dict(form))
            panel = {r["name"]: r["value"] for g in kp["groups"]
                     for r in g["rows"] if not r["later"]}
            rest = [(k, v) for k, v in data if k not in panel]
            # ticked boxes post under every scope (the server reads them
            # for the custom one only), as they always have
            assert rest == [
                ("season", SEASON), ("locations", scope),
                ("custom_locations", "Ohio"), ("custom_locations", "Utah"),
                ("national", "1"), ("width", "3"), ("engine", preset),
                ("knob.groundhog.zero_anchor", "blend"),
                ("mode", "resume"), ("confirm", "")], (scope, preset)
            assert dict((k, v) for k, v in data if k in panel) == panel
            # every option whose words change posts its own value
            for kind, a, opts in _dom(html).controls:
                for o in opts or ():
                    if o[1].startswith(("6-state panel", BASE)):
                        assert o[0]["value"] in ("panel6", "pf")


# ------------------------------------------------------ F53: the cost words

def test_the_oracle_option_prices_the_form(world, monkeypatch):
    """The figure follows the engine, the scope, US national, the width,
    particles and Independent Runs, as estimates prices them; the
    Groundhog's option keeps its words; no hub weeks or no locations, no
    figure."""
    texts = {}
    for eng in ("private", "public"):
        monkeypatch.setenv("FLUBNF_ENGINE", eng)
        for scope in ("panel6", "all"):
            got = _pf(_page(season=SEASON, locations=scope))
            want = RS._cost_words(WEEKS, START, _locs(scope) * 3, 10_000,
                                  pf.DEFAULT_SHARD_WIDTH)
            assert got == _text(want) and want.startswith("about ")
            assert "here" not in got and "left" not in got
            texts[eng, scope] = got
    assert texts["private", "panel6"] != texts["public", "panel6"]
    assert texts["private", "panel6"] != texts["private", "all"]
    # the public engine costs PUBLIC_COST_RATIO times the private one
    pub = estimates.run_seconds([14], 21, 10_000, 4, "public")
    assert pub == pytest.approx(pf.PUBLIC_COST_RATIO
                                * estimates.run_seconds([14], 21, 10_000, 4,
                                                        "private"))
    # each field the cost depends on
    form = dict(season=SEASON, locations="custom", national="0",
                custom_locations=["Ohio", "Utah", "Iowa"], width="2",
                particles="2000", replicates="1")
    assert _pf(_page(**form)) == _text(
        RS._cost_words(WEEKS, START, 3, 2000, 2))
    # the width as the run reads it: never above the cap, blank the default
    assert _pf(_page(season=SEASON, width="99")) == _text(
        RS._cost_words(WEEKS, START, 21, 10_000, pf.SHARD_WIDTH_CAP))
    assert _pf(_page(season=SEASON, width="")) == _text(
        RS._cost_words(WEEKS, START, 21, 10_000, pf.DEFAULT_SHARD_WIDTH))
    # no figure: a season with no hub weeks, a custom scope with none ticked
    assert _pf(_page(season=EMPTY)) == BASE
    assert _pf(_page(season=SEASON, locations="custom")) == BASE
    # the Groundhog's option is as it was
    assert re.search(r'<option value="analogue"( selected)?>Groundhog only '
                     r"\(minutes\)</option>", _page())


def test_a_resume_prices_the_weeks_it_would_run(world):
    """A live Oracle tree with weeks stored: only the weeks left; a
    Groundhog-only tree or a complete one: a full replay."""
    live = world["root"] / SEASON
    _oracle_record(live, WEEKS[:1])
    left = WEEKS[1:]
    got = _pf(_page(season=SEASON))
    assert got == _text(RS._cost_words(left, START, 21, 10_000,
                                       pf.DEFAULT_SHARD_WIDTH, left=3))
    assert got.endswith(", 3 weeks left)")
    full = _text(RS._cost_words(WEEKS, START, 21, 10_000,
                                pf.DEFAULT_SHARD_WIDTH))
    _oracle_record(live, WEEKS[:1], engine="analogue")
    assert _pf(_page(season=SEASON)) == full
    _oracle_record(live, WEEKS, status="done")
    assert _pf(_page(season=SEASON)) == full


def test_here_rests_on_this_computers_own_replays(world):
    """The pace is this computer's timed Oracle weeks over the model's
    figure for each (median), live or archived; an imported replay ran
    elsewhere and a Groundhog-only one has no fits, so neither counts.
    Without one the words say no "here"."""
    rr = world["root"]
    assert RS._own_cost_ratio() == (None, 0)
    # another season's archived run, timed here: 2x and 3x the model
    other = rr / f"2096-97{retro.ARCHIVE_SEP}20970101T000000Z"
    wk = ["2096-11-02", "2096-11-09"]
    model = [estimates.run_seconds([estimates.n_obs_for(w, "2096-08-01")],
                                   21, 10_000, 4, "private") for w in wk]
    _oracle_record(other, [], {wk[0]: 2 * model[0], wk[1]: 3 * model[1]})
    # an imported replay (much slower) and a Groundhog-only one: left out
    imp = rr / f"2095-96{retro.ARCHIVE_SEP}20960101T000000Z"
    _oracle_record(imp, [], {"2095-11-04": 1e6})
    (imp / replay_bundle.IMPORTED_MARK).write_text(
        json.dumps({"from": "vm", "imported_at": "2096-02-01"}))
    gh = rr / "2094-95"
    _oracle_record(gh, [], {"2094-11-05": 1e6}, engine="analogue")
    ui_shared._invalidate_scans()
    ratio, n = RS._own_cost_ratio()
    assert n == 2 and ratio == pytest.approx(2.5, abs=1e-3)
    got = _pf(_page(season=SEASON))
    assert got == _text(RS._cost_words(WEEKS, START, 21, 10_000,
                                       pf.DEFAULT_SHARD_WIDTH, ratio))
    assert " here)" in got
    # with a recorded pace both ends are the same figure
    assert " to " not in got


# ------------------------------------------- the page's script, as served

_DRIVER = r"""
function el(attrs, extra) {
  var o = {attrs: attrs || {}, getAttribute: function (n) {
    return Object.prototype.hasOwnProperty.call(this.attrs, n)
      ? this.attrs[n] : null; }};
  for (var k in extra) o[k] = extra[k];
  return o;
}
// the served form, as the page script sees it
function fakeForm(spec) {
  var handlers = {}, fields = {};
  Object.keys(spec.fields).forEach(function (n) {
    var f = spec.fields[n], opts = {};
    (f.options || []).forEach(function (o) {
      opts[o.attrs.value] = el(o.attrs, {textContent: o.text});
    });
    fields[n] = el(f.attrs, {value: f.value, opts: opts,
      querySelector: function (sel) {
        var m = /option\[value="([^"]+)"\]/.exec(sel);
        return (m && opts[m[1]]) || null; }});
  });
  var boxes = spec.boxes.map(function (b) { return el({}, {checked: b}); });
  return el(spec.attrs, {
    elements: {namedItem: function (n) { return fields[n] || null; }},
    querySelectorAll: function (sel) {
      return sel.indexOf("custom_locations") >= 0 ? boxes : []; },
    addEventListener: function (t, fn) {
      (handlers[t] = handlers[t] || []).push(fn); },
    fire: function (t) { (handlers[t] || []).forEach(function (fn) { fn(); }); },
    fields: fields, boxes: boxes});
}
var f = fakeForm(SPEC), out = [];
FluBNFRetroCost.bind(f);
out.push(f.fields.engine.opts.pf.textContent);
STEPS.forEach(function (s) {
  Object.keys(s.set || {}).forEach(function (n) { f.fields[n].value = s.set[n]; });
  if (s.boxes) s.boxes.forEach(function (b, i) { f.boxes[i].checked = b; });
  f.fire(s.event || "change");
  out.push(f.fields.engine.opts.pf.textContent);
});
return out;
"""


def _spec(html: str) -> dict:
    """The served Run form as the fake DOM's spec: its attributes, each
    named control's value and attributes (a select's value is its selected
    option's), the engine and scope selects' options, the state boxes."""
    d = _dom(html)
    fields, boxes = {}, []
    for kind, a, opts in d.controls:
        name = a.get("name")
        if name == "custom_locations":
            boxes.append("checked" in a)
            continue
        if not name or name in fields:
            continue
        if kind == "select":
            pick = next((o for o in opts if "selected" in o[0]), opts[0])
            fields[name] = {"attrs": a, "value": pick[0].get("value", pick[1]),
                            "options": [{"attrs": o[0], "text": o[1]}
                                        for o in opts if "value" in o[0]]}
        else:
            fields[name] = {"attrs": a, "value": a.get("value", "")}
    return {"attrs": d.form, "fields": fields, "boxes": boxes}


def _run_js(tmp_path, spec: dict, steps: list) -> list:
    drv = tmp_path / "driver.js"
    drv.write_text("var SPEC = %s, STEPS = %s;\nprint(JSON.stringify("
                   "(function(){%s})()));\n"
                   % (json.dumps(spec), json.dumps(steps), _DRIVER),
                   encoding="utf-8")
    files = [EST_JS, TICKER_JS, drv]
    if JSC.is_file():
        cmd = [str(JSC)] + [str(p) for p in files]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + "\n".join(p.read_text(encoding="utf-8")
                                    for p in files), encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_js
def test_the_page_script_words_every_change_as_the_server(world, engine,
                                                          tmp_path):
    """FluBNFRetroCost.bind on the served form: the option as served, then
    after each change (a select, a typed field, the panel's reset) the
    words the server gives that form."""
    html = _page(season=SEASON)
    spec = _spec(html)
    n_all = _locs("all")
    d = pf.DEFAULT_SHARD_WIDTH
    steps = [
        ({"set": {"locations": "all"}}, (WEEKS, n_all * 3, 10_000, d)),
        ({"set": {"width": "2"}}, (WEEKS, n_all * 3, 10_000, 2)),
        ({"set": {"particles": "2000"}, "event": "input"},
         (WEEKS, n_all * 3, 2000, 2)),
        ({"set": {"replicates": "", "national": "0"}},
         (WEEKS, (n_all - 1) * 3, 2000, 2)),
        ({"set": {"locations": "custom"}, "boxes": [True, False, True]},
         (WEEKS, 2 * 3, 2000, 2)),
        ({"set": {"national": "1"}}, (WEEKS, 3 * 3, 2000, 2)),
        ({"boxes": [False, False, False]}, None),
        ({"set": {"locations": "panel6", "width": "99"}},
         (WEEKS, 7 * 3, 2000, pf.SHARD_WIDTH_CAP)),
        ({"set": {"width": "abc"}}, (WEEKS, 7 * 3, 2000, d)),
        ({"set": {"particles": ""}, "event": "ms-reset"},
         (WEEKS, 7 * 3, 10_000, d)),
        ({"set": {"season": EMPTY}}, None),
    ]
    got = _run_js(tmp_path, spec, [s for s, _ in steps])
    assert got[0] == _pf(html)
    want = [_text(RS._cost_words(a[0], START, *a[1:])) if a else BASE
            for _, a in steps]
    assert got[1:] == want
    assert len(set(got)) > 6               # the words really moved


@needs_js
def test_the_page_script_says_here_and_the_weeks_left(world, tmp_path):
    """With this computer's pace recorded and a resume to run, the script
    words it as the server does."""
    _oracle_record(world["root"] / SEASON, WEEKS[:2],
                   {WEEKS[0]: 300.0, WEEKS[1]: 320.0})
    html = _page(season=SEASON)
    ratio, _n = RS._own_cost_ratio()
    assert ratio and "here, 2 weeks left)" in _pf(html)
    got = _run_js(tmp_path, _spec(html), [{"set": {"locations": "all"}}])
    assert got[0] == _pf(html)
    assert got[1] == _text(RS._cost_words(
        WEEKS[2:], START, _locs("all") * 3, 10_000, pf.DEFAULT_SHARD_WIDTH,
        ratio, left=2))


# ------------------------------------------------- F46: a fresh install

def _empty_state(html: str) -> bool:
    return 'id="rt-empty"' in html


def test_a_fresh_install_points_to_the_measured_record(world):
    html = _page()
    assert _empty_state(html)
    box = html.split('id="rt-empty"', 1)[1].split("</div></div>", 1)[0]
    assert "No replays on this computer yet" in box
    assert 'href="/methods#performance"' in box
    assert "See the measured record" in box
    # no tip: the page keeps its marks (test_fewer_marks.py)
    assert "tipbtn" not in box and "uk-tt-btn" not in box
    # the link lands on the measured record
    assert 'id="performance"' in client.get("/methods").text


def test_the_empty_state_goes_once_anything_is_here(world):
    """Results, a replay running with no week stored yet, or an archived
    or imported run alone: each says this computer has replays."""
    rr = world["root"]
    # a replay just started: running, nothing stored yet
    RS._retro_status[SEASON] = "running"
    assert not _empty_state(_page())
    RS._retro_status.clear()
    assert _empty_state(_page())
    # an imported run alone (it lands as an archived run of its season)
    _season_tree(rr, SEASON)
    dst = retro.archive_run(rr, SEASON, stamp="20980204T101500Z")
    (dst / replay_bundle.IMPORTED_MARK).write_text(
        json.dumps({"from": "vm", "imported_at": "2098-02-04"}))
    assert not (rr / SEASON).exists()
    assert not _empty_state(_page())
    # results in the live tree
    shutil.rmtree(dst)
    assert _empty_state(_page())
    _season_tree(rr, SEASON)
    assert not _empty_state(_page())
