"""Where a Groundhog fan starts when the newest week reads 0 (FC-14).

A zero-anchor row is a reported week, not a set-aside one, so
missing.aside_weeks leaves it out. No zero-anchor rule anchors on that 0,
so the fan is never drawn from it (the Model lane's rule, 2026-11-10):

  * Extend starts the fan from the newest positive week, as after a
    set-aside week.
  * Level, Blend and the Poisson fallbacks start at the first horizon,
    with no line from the observed series.

A real Groundhog run on a dataset (the dataset Forecast page draws its fan
with forecast.html's own script), then that page's script under node,
against a stub page, location by location."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

import app.core.runs as runs_mod
from app.core import missing as MS
from app.ui import datasets_ui as DU

from test_dataset_engines import grouped_bytes                  # noqa: E402
from test_datasets_ui import client, isolated, upload           # noqa: F401

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="no node to run the "
                                                 "page's script")

#: one zero (Extend carries the week before), three zeros (more than
#: missing.MAX_CARRY: Extend's Poisson fallback), none (a plain fan)
ONE, THREE, PLAIN = "Adult", "Pediatric", "Elderly"


def _csv() -> bytes:
    """Three groups of the seasonal wave; the newest week of ONE and the
    newest three of THREE read 0."""
    lines = grouped_bytes(groups=(THREE, ONE, PLAIN),
                          pop=False).decode().splitlines()
    head, rows = lines[0], [ln.split(",") for ln in lines[1:]]
    dates = sorted({r[0] for r in rows},
                   key=lambda s: date(2000 + int(s.split("/")[2]),
                                      int(s.split("/")[0]),
                                      int(s.split("/")[1])))
    for r in rows:
        if (r[1] == ONE and r[0] == dates[-1]) or (
                r[1] == THREE and r[0] in dates[-3:]):
            r[2] = "0"
    return ("\n".join([head] + [",".join(r) for r in rows]) + "\n").encode()


def _stored():
    from app.core import datasets as D
    r = upload(_csv(), "Zeros")
    assert r.status_code == 303, r.text[:500]
    return D.get(r.headers["location"].split("source=")[1].split("#")[0])


def _run(ds, rule: str) -> dict:
    """A real Groundhog run on the dataset's newest week under `rule`;
    its ledger row's outcome."""
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": ds.forecast_dates()[-1],
        "locations": "all", "engine": "analogue",
        "knob.groundhog.zero_anchor": rule})
    row = runs_mod.Ledger().rows(1)[0]
    assert row["status"] == "ok", row
    return json.loads(row["outcome"])


def _fan_script(page: str) -> str:
    bodies = [b for b in re.findall(r"<script>(.*?)</script>", page, re.S)
              if "async function drawFan()" in b]
    assert len(bodies) == 1
    return bodies[0]


# a page with every element the script reaches for: each one a plain
# object, the chart calls recorded
STUB = r"""
var calls = [], els = {};
function mk(id){
  var e = {id: id, hidden: id === 'fanx-modal', innerHTML: '',
    textContent: '', value: '', dataset: {}, selectedIndex: 0,
    children: [], attrs: {}, options: [], style: {},
    firstElementChild: null, onclick: null, onchange: null};
  e.classList = {toggle: function(){}, add: function(){},
                 remove: function(){}, contains: function(){ return false; }};
  e.appendChild = function(c){ e.children.push(c);
    e.firstElementChild = e.firstElementChild || c; return c; };
  e.setAttribute = function(k, v){ e.attrs[k] = v; };
  e.addEventListener = function(){};
  e.querySelector = function(){ return mk('q'); };
  e.querySelectorAll = function(){ return []; };
  e.remove = function(){}; e.focus = function(){};
  e.content = {cloneNode: function(){ return mk('fragment'); }};
  return e;
}
var document = {documentElement: {}, activeElement: null,
  getElementById: function(id){ return els[id] || (els[id] = mk(id)); },
  createElement: function(){ return mk(''); },
  querySelector: function(){ return mk('q'); },
  querySelectorAll: function(){ return []; },
  contains: function(){ return true; }};
function getComputedStyle(){
  return {getPropertyValue: function(){ return '#123456'; },
          fontSize: '16px'};
}
function matchMedia(){ return {matches: false}; }
var innerHeight = 900;
function addEventListener(){}
function fetch(){ return Promise.resolve({json: function(){
  return Promise.resolve({}); }}); }
var FluCharts = {react: function(el, traces){
  calls.push({id: el && el.id, traces: traces}); }};
"""

# each (member, location): the median trace's first point and length
DRIVE = r"""
(async function(){
  var out = {};
  for (var i = 0; i < PAIRS.length; i++){
    var m = PAIRS[i][0], loc = PAIRS[i][1];
    FMODEL = m; FIDX = Object.keys(FANQ[m]).indexOf(loc);
    await drawFan();
    var c = calls.filter(function(c){ return c.id === 'fanplot'; }).pop();
    var med = c.traces.filter(function(t){ return t.name === 'median'; })[0];
    out[m + '|' + loc] = {x: med.x[0], y: med.y[0], n: med.x.length,
                          h: Object.keys(FANQ[m][loc]).length};
  }
  console.log(JSON.stringify(out));
})();
"""


def _starts(tmp_path, page: str, pairs) -> dict:
    drv = tmp_path / "drive.js"
    drv.write_text(STUB + _fan_script(page) + "\nvar PAIRS = "
                   + json.dumps(pairs) + ";\n" + DRIVE, encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _weeks(ds, n: int) -> list[str]:
    """The dataset's newest n weeks, oldest first."""
    return [str(w)[:10] for w in ds.weeks()[-n:]]


def _first_horizon(ds) -> str:
    return (date.fromisoformat(_weeks(ds, 1)[0])
            + timedelta(days=7)).isoformat()


def _zero_rules(outcome) -> dict:
    return {r["location"]: r["rule"]
            for r in outcome["data_flags"]["analogue"]
            if r["rule"].startswith(MS.ZERO_ANCHOR_NOTE)}


def test_extend_starts_from_the_newest_positive_week(tmp_path):
    ds = _stored()
    outcome = _run(ds, "extend")
    assert _zero_rules(outcome) == {ONE: "zero-anchor extend",
                                    THREE: "zero-anchor extend"}
    # the rows stay out of the set-aside weeks (missing.py, unchanged)
    assert MS.aside_weeks(outcome) == {}
    page = client.get(f"/forecast?source={ds.id}").text
    got = _starts(tmp_path, page, [["analogue", g]
                                   for g in (ONE, THREE, PLAIN)])
    newest, before = _weeks(ds, 2)[::-1]
    series = {g: dict(zip(*[[str(d)[:10] for d in ds.series(g)["dates"]],
                            ds.series(g)["values"]]))
              for g in (ONE, PLAIN)}
    # one zero: from the week Extend carried, never from the 0
    one = got[f"analogue|{ONE}"]
    assert (one["x"], one["y"]) == (before, series[ONE][before])
    assert one["y"] > 0 and one["n"] == one["h"] + 1
    # three zeros, Extend's Poisson fallback: the first horizon, no line
    three = got[f"analogue|{THREE}"]
    assert three["x"] == _first_horizon(ds) and three["n"] == three["h"]
    # a plain fan still starts from the newest week
    plain = got[f"analogue|{PLAIN}"]
    assert (plain["x"], plain["y"]) == (newest, series[PLAIN][newest])


@pytest.mark.parametrize("rule", ["level", "blend"])
def test_level_and_blend_start_at_the_first_horizon(tmp_path, rule):
    ds = _stored()
    outcome = _run(ds, rule)
    assert _zero_rules(outcome)[ONE] == f"zero-anchor {rule}"
    page = client.get(f"/forecast?source={ds.id}").text
    got = _starts(tmp_path, page, [["analogue", g] for g in (ONE, THREE)])
    for g in (ONE, THREE):
        fan = got[f"analogue|{g}"]
        assert fan["x"] == _first_horizon(ds), (rule, g, fan)
        assert fan["n"] == fan["h"], (rule, g, fan)       # no connector


def test_the_hub_forecast_tab_draws_its_fans_by_the_same_rule(tmp_path):
    """The hub's Forecast tab runs the same script: its drawn run's row
    (forecast_aids.fan_run) carries the flags."""
    from pathlib import Path
    from app.core import horizons as hz
    from app.core.runs import RunSpec
    from app.ui import shared as ui_shared
    fd, qs = "2026-10-17", {"0.1": 4.0, "0.5": 8.0, "0.9": 16.0}
    obs = {"Ohio": [["2026-10-03", 12.0], ["2026-10-10", 9.0], [fd, 0.0]],
           "Utah": [["2026-10-03", 4.0], ["2026-10-10", 2.0], [fd, 0.0]],
           "Iowa": [["2026-10-03", 30.0], ["2026-10-10", 35.0], [fd, 41.0]]}
    spec = RunSpec(engine="analogue", forecast_date=fd, locations=list(obs),
                   extra={"knobs": {MS.ZERO_ANCHOR_KEY: "level"}})
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    wr = runs_mod.APP_STATE / "workroots" / rid
    wr.mkdir(parents=True)
    (wr / "results.json").write_text(json.dumps({
        "spec": spec.to_json(), "forecast_date": fd, "observed": obs,
        hz.CONVENTION_KEY: hz.STORED,
        "models": {"analogue": {loc: {str(h): qs for h in (1, 2, 3, 4)}
                                for loc in obs}}}), encoding="utf-8")
    led.close_run(rid, "ok", {"data_flags": {"pf": [], "analogue": [
        {"location": "Ohio", "week": fd, "value": 0.0,
         "rule": "zero-anchor extend"},
        {"location": "Utah", "week": fd, "value": 0.0,
         "rule": "zero-anchor level"}]}})
    ui_shared._invalidate_scans()
    page = client.get("/forecast").text
    assert 'id="fc-fan-run">' in page and rid in page
    got = _starts(tmp_path, page, [["analogue", g]
                                   for g in ("Ohio", "Utah", "Iowa")])
    assert (got["analogue|Ohio"]["x"], got["analogue|Ohio"]["y"]) == \
        ("2026-10-10", 9.0)
    assert got["analogue|Utah"]["x"] == "2026-10-24"
    assert got["analogue|Utah"]["n"] == 4
    assert (got["analogue|Iowa"]["x"], got["analogue|Iowa"]["y"]) == \
        (fd, 41.0)


def test_without_the_runs_flags_a_groundhog_fan_never_starts_at_0(
        tmp_path, monkeypatch):
    """The drawn run's ledger row is not on the page (a page lists five
    rows): a Groundhog fan from a week of 0 came from a zero-anchor rule,
    which one unknown, so it starts at the first horizon. The particle
    filter keeps its 0 (no zero-anchor rule is its own)."""
    ds = _stored()
    _run(ds, "extend")
    monkeypatch.setattr(DU, "_ledger_for", lambda *a, **k: [])
    real = DU.latest_results_for

    def with_pf(ds_id):
        rid, res = real(ds_id)
        res["models"]["pf"] = res["models"]["analogue"]
        return rid, res
    monkeypatch.setattr(DU, "latest_results_for", with_pf)
    page = client.get(f"/forecast?source={ds.id}").text
    got = _starts(tmp_path, page, [["analogue", ONE], ["pf", ONE],
                                   ["analogue", PLAIN]])
    newest = _weeks(ds, 1)[0]
    gh = got[f"analogue|{ONE}"]
    assert gh["x"] == _first_horizon(ds) and gh["n"] == gh["h"]
    pf = got[f"pf|{ONE}"]
    assert (pf["x"], pf["y"]) == (newest, 0)
    assert got[f"analogue|{PLAIN}"]["x"] == newest
