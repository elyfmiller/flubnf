"""The reviewer's read of #105 at eeb7580b: the Forecast tab's follow-up.

  * FC-13: shown again after a run or a refusal, a "Both from the week
    before" chosen by hand stays when the run-wide rule goes off, and a
    choice the rule moved comes back, a hand-picked Blend as Blend. The
    form posts the same in both cases, so the box keeps what it last sent
    in the browser (never posted); without that record the recommendation
    stands in, as before (the box's own script under node).
  * FC-14: the page carries only member, location and rule from the drawn
    run's outcome (RZERO), not the outcome record.
  * FC-14: the FluSight ensemble and baseline lines start where they did
    before the Groundhog's zero-anchor start: from the week the hub
    reported, a 0 included; the Groundhog's own fan moves as the Model
    lane set out (the page's fan script under node).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import app.core.runs as runs_mod
from app.core import missing as MS

from test_datasets_ui import client, isolated                   # noqa: F401
from test_fan_zero_anchor_start import STUB, _fan_script

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(not NODE, reason="no node to run the "
                                                 "page's script")
UI = Path(__file__).resolve().parents[1] / "ui"
#: the Data issues box's template (its script is what runs under node)
BOX = UI / "templates" / "_data_issues.html"


def _node(tmp_path, text: str):
    f = tmp_path / "page.js"
    f.write_text(text, encoding="utf-8")
    got = subprocess.run([NODE, str(f)], capture_output=True, text=True,
                         timeout=60)
    assert got.returncode == 0, got.stderr[-800:]
    return json.loads(got.stdout.strip().splitlines()[-1])


# ------------------------------------------------ FC-13: the box, two pages

#: stand-ins for the box's elements. page() builds one Forecast page: its
#: selects as the server renders them (each holding the last form's value),
#: the box's week and data file, Model settings' "Newest weeks reading 0"
#: and the browser's storage, shared by the pages of one browser.
_HARNESS = r"""
var ALL = ['level', 'extend', 'blend', 'set_aside', 'omit'];
function Sel(fips, value, rec) {
  var check = {hidden: value !== rec};          // as the server renders it
  var on = {};
  var s = {name: 'gap.' + fips,
           options: ALL.map(function (v) {
             return {value: v, hidden: false, disabled: false}; }),
           dataset: {rules: 'data.trailing_zero', rec: rec, issue: 'zero'},
           _v: value, check: check, on: on,
           parentNode: {querySelector: function () { return check; }},
           addEventListener: function (t, f) { on[t] = f; }};
  Object.defineProperty(s, 'selectedIndex', {get: function () {
    for (var i = 0; i < s.options.length; i++)
      if (s.options[i].value === s._v) return i;
    return -1; }});
  Object.defineProperty(s, 'value', {
    get: function () { var i = s.selectedIndex; return i < 0 ? '' : s.options[i].value; },
    set: function (v) { s._v = v; }});
  return s;
}
function Store() {
  var d = {};
  return {getItem: function (k) { return k in d ? d[k] : null; },
          setItem: function (k, v) { d[k] = String(v); }, _d: d};
}
//: storage blocked: naming it works, every call throws
var BLOCKED = {getItem: function () { throw new Error('blocked'); },
               setItem: function () { throw new Error('blocked'); }};
function boot(document, localStorage) { SCRIPT }
function page(sels, knobValue, store, week, sha) {
  var knob = {value: knobValue, disabled: false};
  var panel = false, L = {}, D = [];
  var form = {
    querySelector: function (q) {
      return panel && q === '[name="knob.data.trailing_zero"]' ? knob : null; },
    addEventListener: function (t, f) { (L[t] = L[t] || []).push(f); }};
  var box = {dataset: {week: week || '2026-11-07'}, disabled: false,
    closest: function () { return form; },
    querySelectorAll: function (q) {
      if (q === 'select[data-rules]' || q === 'select[name^="gap."]') return sels;
      if (q === 'input[name="gap._sha"]') return [{value: sha || 'abc'}];
      return []; }};
  var document = {
    getElementById: function (id) { return id === 'data-issues' ? box : null; },
    addEventListener: function (t, f) { if (t === 'DOMContentLoaded') D.push(f); }};
  boot(document, store);
  panel = true;                 // the panel is in the page once it has loaded
  D.forEach(function (f) { f({type: 'DOMContentLoaded'}); });
  return {
    sels: sels, box: box,
    setting: function (v) {
      knob.value = v;
      L.change.forEach(function (f) { f({target: {name: 'knob.data.trailing_zero'}}); });
    },
    reset: function () {        // Reset to defaults, then its event
      knob.value = 'keep';
      L['ms-reset'].forEach(function (f) { f({type: 'ms-reset'}); });
    },
    pick: function (s, v) { s._v = v; s.on.change(); },
    // the form sent: what each select posts, with the setting's value
    submit: function () {
      (L.submit || []).forEach(function (f) { f({type: 'submit'}); });
      var out = {};
      sels.forEach(function (s) { out[s.name] = s.value; });
      out['knob.data.trailing_zero'] = knob.value;
      return out;
    }};
}
// the choice, whether its check shows, and whether it is the rule's
// choice (set aside under the rule, else the recommendation)
function state(p, s) {
  var on = s.dataset.ruled === '1';
  return [s.value, !s.check.hidden, s.value === (on ? 'set_aside' : s.dataset.rec)];
}
"""


def _box(tmp_path, steps: str):
    text = BOX.read_text(encoding="utf-8")
    script = text.split("<script>", 1)[1].split("</script>", 1)[0]
    return _node(tmp_path, _HARNESS.replace("SCRIPT", script)
                 + "var out = {};\n" + steps
                 + "\nconsole.log(JSON.stringify(out));\n")


@needs_node
def test_both_orders_post_the_same_form(tmp_path):
    """Why the box keeps a record: picked by hand and then the rule on, or
    moved there by the rule, Utah posts the same; only the page knew."""
    got = _box(tmp_path, """
var a = page([Sel('49', 'level', 'level')], 'keep', Store());
a.pick(a.sels[0], 'set_aside'); a.setting('missing');
var b = page([Sel('49', 'level', 'level')], 'keep', Store());
b.setting('missing');
out.hand = a.submit(); out.rule = b.submit();
""")
    assert got["hand"] == got["rule"] == {
        "gap.49": "set_aside", "knob.data.trailing_zero": "missing"}


@needs_node
def test_after_a_run_a_both_from_chosen_by_hand_stays(tmp_path):
    """The reviewer's sequence: Utah's recommendation is Level; with the
    rule off Utah is set to "Both from" by hand, the rule goes on, the form
    is sent. Shown again, the rule off (or Reset to defaults) leaves Utah
    on "Both from", with no check: it was not the rule's move."""
    got = _box(tmp_path, """
var store = Store();
var one = page([Sel('49', 'level', 'level')], 'keep', store);
one.pick(one.sels[0], 'set_aside'); one.setting('missing');
var sent = one.submit();
var two = page([Sel('49', sent['gap.49'], 'level')], 'missing', store);
out.shown = state(two, two.sels[0]);
two.setting('keep');
out.off = state(two, two.sels[0]);
var three = page([Sel('49', sent['gap.49'], 'level')], 'missing', store);
three.reset();
out.reset = state(three, three.sels[0]);
""")
    assert got == {"shown": ["set_aside", True, True],
                   "off": ["set_aside", False, False],
                   "reset": ["set_aside", False, False]}


@needs_node
def test_after_a_run_a_blend_the_rule_moved_comes_back_as_blend(tmp_path):
    """Blend chosen by hand, then the rule on (it moves Utah to "Both
    from"), then sent. Shown again, the rule off puts back Blend, not the
    recommendation; so does Reset to defaults."""
    got = _box(tmp_path, """
var store = Store();
var one = page([Sel('49', 'level', 'level')], 'keep', store);
one.pick(one.sels[0], 'blend'); one.setting('missing');
var sent = one.submit();
var two = page([Sel('49', sent['gap.49'], 'level')], 'missing', store);
two.setting('keep');
out.off = state(two, two.sels[0]);
two.setting('missing');
out.on_again = state(two, two.sels[0]);
two.setting('keep');
out.off_again = state(two, two.sels[0]);
var three = page([Sel('49', sent['gap.49'], 'level')], 'missing', store);
three.reset();
out.reset = state(three, three.sels[0]);
""")
    assert got == {"off": ["blend", False, False],
                   "on_again": ["set_aside", True, True],
                   "off_again": ["blend", False, False],
                   "reset": ["blend", False, False]}


@needs_node
def test_after_a_run_the_moves_of_one_form_come_back_state_by_state(
        tmp_path):
    """One form, three states under the rule: Utah moved from its
    recommendation, Ohio set to "Both from" by hand, Iowa left out by
    hand. Shown again with the rule off: Utah has Level back with its
    check, Ohio and Iowa keep their own choices."""
    got = _box(tmp_path, """
var store = Store();
var one = page([Sel('49', 'level', 'level'), Sel('39', 'extend', 'extend'),
                Sel('19', 'level', 'level')], 'keep', store);
one.pick(one.sels[1], 'set_aside');
one.setting('missing');
one.pick(one.sels[2], 'omit');
var sent = one.submit();
var two = page([Sel('49', sent['gap.49'], 'level'),
                Sel('39', sent['gap.39'], 'extend'),
                Sel('19', sent['gap.19'], 'level')], 'missing', store);
two.setting('keep');
out.utah = state(two, two.sels[0]);
out.ohio = state(two, two.sels[1]);
out.iowa = state(two, two.sels[2]);
""")
    assert got == {"utah": ["level", True, True],
                   "ohio": ["set_aside", False, False],
                   "iowa": ["omit", False, False]}


@needs_node
def test_a_record_of_another_form_or_none_falls_back_to_the_recommendation(
        tmp_path):
    """The record is used only by a page that shows the form it records:
    another week, another data file, or a select at another value, and the
    page does as it did without a record (the recommendation is the choice
    the rule moved). Storage blocked: the same, and nothing throws."""
    got = _box(tmp_path, """
function sentByHand(store) {
  var one = page([Sel('49', 'level', 'level')], 'keep', store);
  one.pick(one.sels[0], 'set_aside'); one.setting('missing');
  return one.submit();
}
function shownOff(store, week, sha, value) {
  var p = page([Sel('49', value || 'set_aside', 'level')], 'missing', store,
               week, sha);
  p.setting('keep');
  return state(p, p.sels[0]);
}
var s1 = Store(); sentByHand(s1);
out.week = shownOff(s1, '2026-11-14');
var s2 = Store(); sentByHand(s2);
out.sha = shownOff(s2, undefined, 'def');
var s3 = Store(); sentByHand(s3);
var p3 = page([Sel('49', 'set_aside', 'level'), Sel('39', 'omit', 'level')],
              'missing', s3);
p3.setting('keep');
out.other = state(p3, p3.sels[0]);
out.none = shownOff(Store());
sentByHand(BLOCKED);
out.blocked = shownOff(BLOCKED);
""")
    back = ["level", True, True]
    assert got == {"week": back, "sha": back, "other": back, "none": back,
                   "blocked": back}


@needs_node
def test_a_disabled_box_keeps_the_record_it_had(tmp_path):
    """A form sent with the box disabled (the date left the week) posts no
    choice and the server keeps the last ones; the record stays theirs."""
    got = _box(tmp_path, """
var store = Store();
var one = page([Sel('49', 'level', 'level')], 'keep', store);
one.pick(one.sels[0], 'set_aside'); one.setting('missing');
one.submit();
var kept = store._d['fc-di-sent'];
var two = page([Sel('49', 'set_aside', 'level')], 'missing', store);
two.box.disabled = true;
two.setting('keep');
two.submit();
out.same = store._d['fc-di-sent'] === kept;
var three = page([Sel('49', 'set_aside', 'level')], 'missing', store);
three.setting('keep');
out.off = state(three, three.sels[0]);
""")
    assert got == {"same": True, "off": ["set_aside", False, False]}


def test_the_record_is_never_a_posted_field():
    """The box posts gap.<fips> and gap._sha only: the record lives in the
    browser, inside a try (storage may be blocked)."""
    text = BOX.read_text(encoding="utf-8")
    markup, script = text.split("<script>", 1)
    names = set(re.findall(r'\bname="([^"{]*)"', markup))
    assert names == {"gap._sha"}, names
    assert len(re.findall(r'\bname="gap\.\{\{ r\.fips \}\}"', markup)) == 1
    assert "var KEY = 'fc-di-sent';" in script


# ---------------------------------------- FC-14: the hub's Forecast tab, a run

FD = "2026-10-17"
QS = {"0.025": 1.0, "0.1": 4.0, "0.25": 6.0, "0.5": 8.0, "0.75": 11.0,
      "0.9": 16.0, "0.975": 20.0}
#: Ohio and Utah read 0 in the newest week (Extend and Level); Iowa does
#: not; Idaho's newest week was set aside (a partial week)
OBS = {"Ohio": [["2026-10-03", 15.0], ["2026-10-10", 12.0], [FD, 0.0]],
       "Utah": [["2026-10-03", 4.0], ["2026-10-10", 2.0], [FD, 0.0]],
       "Iowa": [["2026-10-03", 30.0], ["2026-10-10", 35.0], [FD, 41.0]],
       "Idaho": [["2026-10-03", 7.0], ["2026-10-10", 9.0], [FD, 1.0]]}
#: a stand-in for what an outcome record carries besides the flags
LOCAL_PATH = "/Users/someone/flubnf/app/state/workroots/secret-notes"


def _hub_run(monkeypatch, official: bool) -> str:
    """A Groundhog run on the hub, stored with its ledger row; the hub's
    Forecast tab drawing it. The FluSight overlay's forecasts for its date
    when `official`."""
    from app.core import horizons as hz
    from app.core.runs import RunSpec
    from app.ui import shared as ui_shared
    from app.ui.routes import forecast as fc
    spec = RunSpec(engine="analogue", forecast_date=FD, locations=list(OBS),
                   extra={"knobs": {MS.ZERO_ANCHOR_KEY: "level"}})
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    wr = runs_mod.APP_STATE / "workroots" / rid
    wr.mkdir(parents=True)
    (wr / "results.json").write_text(json.dumps({
        "spec": spec.to_json(), "forecast_date": FD, "observed": OBS,
        hz.CONVENTION_KEY: hz.STORED,
        "models": {"analogue": {loc: {str(h): QS for h in (1, 2, 3, 4)}
                                for loc in OBS}}}), encoding="utf-8")
    led.close_run(rid, "ok", {
        "report": LOCAL_PATH + "/report.html",
        "notes": {"Ohio": "a note " + LOCAL_PATH},
        "data_flags": {"pf": [], "analogue": [
            {"location": "Ohio", "week": FD, "value": 0.0,
             "rule": "zero-anchor extend", "note": LOCAL_PATH},
            {"location": "Utah", "week": FD, "value": 0.0,
             "rule": "zero-anchor level"},
            {"location": "Idaho", "week": FD, "value": 1.0,
             "rule": "partial week"}]}})
    if official:
        over = {loc: {str(h): {"0.025": 2.0, "0.05": 3.0, "0.25": 5.0,
                               "0.5": 7.0 + h, "0.75": 9.0, "0.95": 12.0,
                               "0.975": 14.0} for h in (1, 2, 3, 4)}
                for loc in OBS}
        monkeypatch.setattr(fc, "_official_overlay", lambda d, locs: {
            "FluSight-ensemble": over, "FluSight-baseline": over}
            if d == FD else {})
    ui_shared._invalidate_scans()
    page = client.get("/forecast").text
    assert 'id="fc-fan-run">' in page and rid in page
    return page


def _rzero(page: str):
    m = re.search(r"^\s*const RZERO = (.*);\s*$", page, re.M)
    assert m, "no RZERO line"
    return m.group(1)


def test_the_page_carries_only_member_location_and_rule(monkeypatch):
    page = _hub_run(monkeypatch, official=False)
    line = _rzero(page)
    assert json.loads(line) == {"analogue": {"Ohio": "extend",
                                             "Utah": "level"}}
    for word in ("secret-notes", "report.html", "data_flags", "partial week",
                 "value", "week"):
        assert word not in line, word


def test_without_the_drawn_runs_row_the_page_says_null(monkeypatch):
    from app.ui import forecast_aids as fa
    _hub_run(monkeypatch, official=False)
    real = fa.page_aids

    def elsewhere(*a, **k):
        aids = dict(real(*a, **k))
        aids["fan_run"] = {**(aids.get("fan_run") or {}), "run_id": "x"}
        return aids
    monkeypatch.setattr(fa, "page_aids", elsewhere)
    assert _rzero(client.get("/forecast").text) == "null"


def test_the_rules_are_read_from_an_outcome_of_any_shape():
    from app.ui.routes.forecast import _fan_zero_rules as rules
    assert rules(None) == rules("") == rules("{") == rules("[]") == {}
    assert rules(json.dumps({"data_flags": {"analogue": [
        None, "x", {"rule": "zero-anchor blend"},
        {"location": "Utah", "rule": "zero-anchor blend"},
        {"location": "Iowa", "rule": "trailing zero"}]}})) == {
            "analogue": {"Utah": "blend"}}


# overlay and fan for each location: the median's first point, and the
# FluSight-ensemble's and -baseline's
DRIVE = r"""
(async function(){
  var out = {};
  for (var i = 0; i < PICK.length; i++){
    FMODEL = 'analogue'; FIDX = Object.keys(FANQ.analogue).indexOf(PICK[i]);
    await drawFan();
    var c = calls.filter(function(c){ return c.id === 'fanplot'; }).pop();
    var first = function(name){
      var t = c.traces.filter(function(t){ return t.name === name; })[0];
      return t ? [t.x[0], t.y[0], t.x.length] : null; };
    var named = function(m){ return MNAMES[m] || m; };
    out[PICK[i]] = {fan: first('median'), ens: first(named('FluSight-ensemble')),
                    base: first(named('FluSight-baseline'))};
  }
  console.log(JSON.stringify(out));
})();
"""


@needs_node
def test_the_flusight_lines_start_from_the_week_the_hub_reported(
        tmp_path, monkeypatch):
    """Ohio under Extend: the Groundhog's fan starts from the week before
    the 0, the FluSight ensemble and baseline from the 0 the hub reported,
    as before the fan's change. Utah under Level: the fan has no line from
    the observed series, the FluSight lines start from the 0. Iowa: both
    from the newest week. Idaho's set-aside week: both from the week
    before it, as before."""
    page = _hub_run(monkeypatch, official=True)
    got = _node(tmp_path, STUB + _fan_script(page) + "\nvar PICK = "
                + json.dumps(list(OBS)) + ";\n" + DRIVE)
    h1 = "2026-10-24"
    assert got["Ohio"]["fan"] == ["2026-10-10", 12.0, 5]
    assert got["Utah"]["fan"] == [h1, 8.0, 4]
    assert got["Iowa"]["fan"] == [FD, 41.0, 5]
    assert got["Idaho"]["fan"] == ["2026-10-10", 9.0, 5]
    for loc, start in (("Ohio", [FD, 0.0, 5]), ("Utah", [FD, 0.0, 5]),
                       ("Iowa", [FD, 41.0, 5]),
                       ("Idaho", ["2026-10-10", 9.0, 5])):
        assert got[loc]["ens"] == start, (loc, got[loc])
        assert got[loc]["base"] == start, (loc, got[loc])
