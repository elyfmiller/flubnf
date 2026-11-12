"""Where the Models page's and a dataset run page's Groundhog fans start
when the newest week reads 0 (FC-14, the two fans 90ec3e99 left).

forecast.html's fan (test_fan_zero_anchor_start.py) reads each state's
zero-anchor rule from the drawn run's ledger row: Extend starts from the
newest positive week; Level, Blend and the Poisson fallbacks start at the
first horizon, with no line from the observed series. Without that row it
takes its fallback: a Groundhog fan that would start at a 0 came from a
zero-anchor rule, which one unknown, so it starts at the first horizon.

The model page (model.html) and a dataset run's page (_dataset_run.html)
carry no ledger row, and no value is added to their data, so their fans
take that fallback, by the same drawing rule:

  * a Groundhog fan never starts from a 0; it starts at the first
    horizon, with no connector (whatever the state's rule);
  * a week set aside keeps its start (the week before it, model.html);
  * the particle filter keeps its 0 (no zero-anchor rule is its own);
  * a fan from a positive week starts there, as before.

Each page's own script runs under node against a stub page."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import app.core.runs as runs_mod
from app.core import missing as MS
from app.ui import datasets_ui as DU
from app.ui import shared as ui_shared
from app.ui.templating import templates

import test_fan_zero_anchor_start as ZS                         # noqa: E402
from test_datasets_ui import client, isolated, upload           # noqa: F401

pytestmark = pytest.mark.skipif(not ZS.NODE, reason="no node to run the "
                                                    "page's script")


def _scripts(page: str, marker: str) -> str:
    bodies = [b for b in re.findall(r"<script>(.*?)</script>", page, re.S)
              if marker in b]
    assert len(bodies) == 1
    return bodies[0]


def _node(tmp_path, name: str, js: str) -> dict:
    drv = tmp_path / name
    drv.write_text(js, encoding="utf-8")
    out = subprocess.run([ZS.NODE, str(drv)], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------- the Models page (model.html)

FD = "2026-10-17"
FIRST = "2026-10-24"                         # the first horizon's week
QS = {"0.1": 4.0, "0.5": 8.0, "0.9": 16.0}
OBS = {
    # zero-anchor rules (the drawn run's flags; the page never reads them)
    "Ohio": [["2026-10-03", 12.0], ["2026-10-10", 9.0], [FD, 0.0]],
    "Utah": [["2026-10-03", 4.0], ["2026-10-10", 2.0], [FD, 0.0]],
    "Idaho": [["2026-10-03", 0.0], ["2026-10-10", 0.0], [FD, 0.0]],
    # set aside by both members: the fan starts from the week before
    "Kansas": [["2026-10-03", 20.0], ["2026-10-10", 25.0], [FD, 0.0]],
    # a plain fan
    "Iowa": [["2026-10-03", 30.0], ["2026-10-10", 35.0], [FD, 41.0]]}
ZERO = {"Ohio": "extend", "Utah": "level", "Idaho": "blend"}


def _hub_run() -> str:
    """A real-time hub run, both members, in the ledger and its workroot:
    the newest run the model pages draw. Its states' choices as the Data
    issues box records them, its flags as the engines write them."""
    from app.core import horizons as hz
    from app.core.runs import RunSpec
    states = {loc: {"issue": "zero", "reported": [[FD, 0.0]],
                    "choice": rule, "recommended": rule, "followed": True}
              for loc, rule in ZERO.items()}
    states["Kansas"] = {"issue": "zero", "reported": [[FD, 0.0]],
                        "choice": "set_aside", "from_week": "2026-10-10",
                        "recommended": "set_aside", "followed": True}
    spec = RunSpec(engine="all", forecast_date=FD, locations=list(OBS),
                   extra={MS.CHOICES_KEY: {"week": FD, "states": states}})
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    wr = runs_mod.APP_STATE / "workroots" / rid
    wr.mkdir(parents=True)
    (wr / "results.json").write_text(json.dumps({
        "spec": spec.to_json(), "forecast_date": FD, "observed": OBS,
        hz.CONVENTION_KEY: hz.STORED,
        "models": {m: {loc: {str(h): QS for h in (1, 2, 3, 4)}
                       for loc in OBS}
                   for m in ("pf", "analogue")}}), encoding="utf-8")
    aside = [{"location": "Kansas", "week": FD, "value": 0.0,
              "rule": MS.SET_ASIDE_RULE}]
    led.close_run(rid, "ok", {"data_flags": {
        "pf": list(aside),
        "analogue": aside + [
            {"location": loc, "week": FD, "value": 0.0,
             "rule": f"{MS.ZERO_ANCHOR_NOTE} {rule}"}
            for loc, rule in ZERO.items()]}})
    ui_shared._invalidate_scans()
    return rid


# each location: the median trace's first point and length
MODEL_DRIVE = r"""
(async function(){
  var out = {};
  for (var i = 0; i < PAIRS.length; i++){
    var loc = PAIRS[i];
    IDX = LOCS.indexOf(loc);
    await draw();
    var c = calls.filter(function(c){ return c.id === 'plot'; }).pop();
    var med = c.traces.filter(function(t){ return t.name === 'median'; })[0];
    out[loc] = {x: med.x[0], y: med.y[0], n: med.x.length,
                h: Object.keys(FANQ[loc]).length};
  }
  console.log(JSON.stringify(out));
})();
"""


def _model_starts(tmp_path, path: str) -> dict:
    page = client.get(path).text
    js = (ZS.STUB + _scripts(page, "async function draw()")
          + "\nvar PAIRS = " + json.dumps(list(OBS)) + ";\n" + MODEL_DRIVE)
    return _node(tmp_path, "model-" + path.strip("/").replace("/", "-")
                 + ".js", js)


def test_the_groundhogs_model_page_never_starts_a_fan_at_a_0(tmp_path):
    rid = _hub_run()
    assert ui_shared._latest_results()[0] == rid
    got = _model_starts(tmp_path, "/model/analogue")
    # Extend, Level and Blend (all zeros: its Poisson fallback) alike: the
    # first horizon, no line from the observed series
    for loc in ZERO:
        assert (got[loc]["x"], got[loc]["n"]) == (FIRST, got[loc]["h"]), \
            (loc, got[loc])
    # a week set aside: from the week before it, as before
    assert (got["Kansas"]["x"], got["Kansas"]["y"]) == ("2026-10-10", 25.0)
    assert got["Kansas"]["n"] == got["Kansas"]["h"] + 1
    # a plain fan still starts from the newest week
    assert (got["Iowa"]["x"], got["Iowa"]["y"]) == (FD, 41.0)
    assert got["Iowa"]["n"] == got["Iowa"]["h"] + 1


def test_the_oracle_sihrs_model_page_keeps_its_0(tmp_path):
    """The particle filter has no zero-anchor rule: its fan starts from
    the 0 it read, as before."""
    _hub_run()
    got = _model_starts(tmp_path, "/models")
    for loc in ZERO:
        assert (got[loc]["x"], got[loc]["y"]) == (FD, 0.0), (loc, got[loc])
        assert got[loc]["n"] == got[loc]["h"] + 1
    assert (got["Kansas"]["x"], got["Kansas"]["y"]) == ("2026-10-10", 25.0)
    assert (got["Iowa"]["x"], got["Iowa"]["y"]) == (FD, 41.0)


# ------------------------------- a dataset run's page (_dataset_run.html)

# a stub page for the run page's fan; setting innerHTML to '' empties an
# element, as the group list does when the member changes
DS_STUB = r"""
var calls = [], els = {};
function mk(tag){
  var e = {tag: tag, hidden: false, textContent: '', dataset: {},
    selectedIndex: 0, children: [], attrs: {}, onclick: null,
    onchange: null};
  Object.defineProperty(e, 'innerHTML', {get: function(){ return ''; },
    set: function(v){ if (v === '') e.children = []; }});
  e.appendChild = function(c){ e.children.push(c); return c; };
  e.querySelectorAll = function(){ return e.children; };
  e.setAttribute = function(k, v){ e.attrs[k] = v; };
  e.classList = {toggle: function(){}};
  return e;
}
var document = {documentElement: {},
  getElementById: function(id){ return els[id] || (els[id] = mk(id)); },
  createElement: mk};
function getComputedStyle(){
  return {getPropertyValue: function(){ return '#123456'; },
          fontSize: '16px'};
}
function matchMedia(){ return {matches: false}; }
function addEventListener(){}
var FluCharts = {react: function(id, traces, layout){
  calls.push({id: id, traces: traces, title: layout.title.text}); }};
"""

# every member, every group: the median trace's first point and length,
# keyed by the chart's title ("<group> · <member>")
DS_DRIVE = r"""
var out = {};
var buttons = els['dsf-models'].children;
for (var b = 0; b < buttons.length; b++){
  buttons[b].onclick();
  var n = els['dsf-loc'].children.length;
  for (var k = 0; k < n; k++){
    els['dsf-loc'].onchange.call({selectedIndex: k});
    var c = calls[calls.length - 1];
    var med = c.traces.filter(function(t){ return t.name === 'median'; })[0];
    out[c.title] = {x: med.x[0], y: med.y[0], n: med.x.length};
  }
}
console.log(JSON.stringify(out));
"""


def _ds_starts(tmp_path, page: str) -> dict:
    """{(member, group): first point, length and horizon count}."""
    js = _scripts(page, "FluCharts.react('dsf-plot'")
    F = json.loads(re.search(r"const F = (\{.*?\});\n", js).group(1))
    raw = _node(tmp_path, "dataset-run.js", DS_STUB + js + "\n" + DS_DRIVE)
    out = {}
    for m, by_loc in F["models"].items():
        for loc, qs in by_loc.items():
            if not qs:
                continue
            got = raw[f"{loc} · {F['names'].get(m, m)}"]
            out[(m, loc)] = {**got, "h": len(qs)}
    return out


@pytest.mark.parametrize("rule", ["extend", "level", "blend"])
def test_a_dataset_runs_groundhog_fan_never_starts_at_its_0(tmp_path, rule):
    """A real Groundhog run on a dataset under each rule, its run page:
    one zero (Extend carries the week before), three zeros (Extend's
    Poisson fallback) and a plain group."""
    ds = ZS._stored()
    outcome = ZS._run(ds, rule)
    assert ZS._zero_rules(outcome)[ZS.ONE] == f"zero-anchor {rule}"
    rid = runs_mod.Ledger().rows(1)[0]["run_id"]
    page = client.get(f"/runs/{rid}").text
    assert 'id="ds-fans"' in page
    got = _ds_starts(tmp_path, page)
    first, newest = ZS._first_horizon(ds), ZS._weeks(ds, 1)[0]
    for g in (ZS.ONE, ZS.THREE):
        fan = got[("analogue", g)]
        assert (fan["x"], fan["n"]) == (first, fan["h"]), (rule, g, fan)
    plain = got[("analogue", ZS.PLAIN)]
    values = dict(zip([str(d)[:10] for d in ds.series(ZS.PLAIN)["dates"]],
                      ds.series(ZS.PLAIN)["values"]))
    assert (plain["x"], plain["y"]) == (newest, values[newest])
    assert plain["n"] == plain["h"] + 1


def test_a_dataset_runs_particle_filter_keeps_its_0(tmp_path, monkeypatch):
    """Both members on one run page (run_page_extra's fans, as run.html
    includes them): the Groundhog's fan from a 0 takes the first horizon,
    the particle filter's starts from its 0, and a group read above 0
    starts from that week under both."""
    hq = {str(h): QS for h in range(4)}
    res = {"forecast_date": FD,
           "dataset": {"id": "no-such-dataset", "name": "Clinic counts",
                       "vintage_true": True},
           "horizon_convention": "canonical",
           "models": {m: {"Group A": hq, "Group B": hq}
                      for m in ("pf", "analogue")},
           "observed": {"Group A": [["2026-10-03", 6.0],
                                    ["2026-10-10", 3.0], [FD, 0.0]],
                        "Group B": [["2026-10-03", 10.0],
                                    ["2026-10-10", 12.0], [FD, 15.0]]}}
    monkeypatch.setattr(DU, "get_dataset", lambda _id: None)
    page = templates.env.from_string(
        '{% import "_tips.html" as tips %}{% include "_dataset_run.html" %}'
    ).render(**DU.run_page_extra(tmp_path, res))
    got = _ds_starts(tmp_path, page)
    gh = got[("analogue", "Group A")]
    assert (gh["x"], gh["n"]) == (FIRST, gh["h"]), gh
    pf = got[("pf", "Group A")]
    assert (pf["x"], pf["y"], pf["n"]) == (FD, 0.0, pf["h"] + 1), pf
    for m in ("pf", "analogue"):
        b = got[(m, "Group B")]
        assert (b["x"], b["y"], b["n"]) == (FD, 15.0, b["h"] + 1), (m, b)
