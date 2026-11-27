"""The Forecasts card's chart on the Forecast tab (hub and dataset runs,
one script in forecast.html): the models together or one alone, the 50%,
80% and 95% ranges, the hover's whole counts, the labelled y axis, US
first, and Save figure.

  * The 95% range is read from the run's own files, since results.json
    keeps 10% to 90%: a hub run's weekly-report bundle (its "All
    locations" grid, the model's own forecast) and a dataset run's export
    files (forecast_aids.wide_levels, widen_fans).
  * Together ("Both"), each model draws its median and its 95% range (its
    80% where the run kept no 95%), and the legend's title says what the
    shading holds. One model alone draws all three ranges, each named in
    the legend by its share.
  * The hover gives the week, the median and the 50% and 95% ranges in
    whole counts; the y axis says what is counted.
  * The location list starts with the national series.
  * Save figure writes a PNG with the location, the data's date, the
    models and the legend in it.

The page's own script runs under node against a stub page."""
from __future__ import annotations

import csv
import json
import re
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.core.runs as runs_mod
from app.core import horizons as hz
from app.core import report_grid, report_v2
from app.core.runs import RunSpec
from app.ui import forecast_aids as FA
from app.ui import shared as ui_shared

import test_fan_zero_anchor_start as ZS                         # noqa: E402
from test_dataset_engines import grouped_bytes                  # noqa: E402
from test_datasets_ui import client, isolated, upload           # noqa: F401

FD = "2026-10-17"
#: the four target weeks of a run made on FD (stored horizons 1..4)
TIMES = [(date.fromisoformat(FD) + timedelta(days=7 * h)).isoformat()
         for h in (1, 2, 3, 4)]
OBS = {"Ohio": [["2026-10-03", 120.0], ["2026-10-10", 150.0],
                [FD, 180.0]],
       "US": [["2026-10-03", 9000.0], ["2026-10-10", 10500.0],
              [FD, 12000.0]],
       "Utah": [["2026-10-03", 20.0], ["2026-10-10", 24.0], [FD, 30.0]]}
MEMBERS = ("pf", "analogue")


def _five(base: float, h: int) -> dict:
    """A stored horizon's five levels, fractional as results.json keeps
    them."""
    m = base * (1 + 0.1 * h)
    return {"0.1": m * .6 + .4, "0.25": m * .8 + .3, "0.5": m + .2,
            "0.75": m * 1.25 + .1, "0.9": m * 1.6 + .45}


def _models() -> dict:
    return {m: {loc: {str(h): _five(obs[-1][1] * (1.2 if m == "pf" else 1),
                                    h) for h in (1, 2, 3, 4)}
                for loc, obs in OBS.items()} for m in MEMBERS}


def _grid(models: dict) -> dict:
    """The bundle's grid (report_grid.grid_data's shape): per panel and
    model, [2.5%, 25%, 50%, 75%, 97.5%] by target week, whole numbers; US
    keyed "US" under the title "United States"."""
    panels = []
    for loc in OBS:
        ms = {}
        for m in MEMBERS:
            q = []
            for h in (1, 2, 3, 4):
                f = models[m][loc][str(h)]
                q.append([float(round(f["0.1"] * .7)), round(f["0.25"]),
                          round(f["0.5"]), round(f["0.75"]),
                          float(round(f["0.9"] * 1.5))])
            ms[m] = {"times": TIMES, "q": q}
        panels.append({"key": "US" if loc == "US" else loc[:2].upper(),
                       "name": "United States" if loc == "US" else loc,
                       "models": ms})
    return {"asof": FD, "times": TIMES, "panels": panels}


def _hub_run(grid: bool = True) -> tuple[str, dict]:
    """A stored hub run of both members on FD (and its bundle's grid);
    (run id, its stored models)."""
    models = _models()
    spec = RunSpec(engine="all", forecast_date=FD, locations=list(OBS))
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    wr = runs_mod.APP_STATE / "workroots" / rid
    wr.mkdir(parents=True)
    (wr / "results.json").write_text(json.dumps({
        "spec": spec.to_json(), "forecast_date": FD, "observed": OBS,
        hz.CONVENTION_KEY: hz.STORED, "models": models}), encoding="utf-8")
    if grid:
        (wr / report_v2.BUNDLE_NAME).write_text(json.dumps({
            "version": 8, "asof": FD, "grid": _grid(models)}),
            encoding="utf-8")
    led.close_run(rid, "ok", {})
    ui_shared._invalidate_scans()
    return rid, models


def _page(path: str = "/forecast") -> str:
    r = client.get(path)
    assert r.status_code == 200
    return r.text


def _const(page: str, name: str):
    m = re.search(rf"^\s*const {name}\s*=\s*(.*?);\s*(//.*)?$", page, re.M)
    assert m, name
    return json.loads(m.group(1))


# ----------------------------------------------- the 95% range, the data


def test_a_hub_runs_95_range_comes_from_its_reports_grid():
    rid, models = _hub_run()
    wide = FA.wide_levels(runs_mod.APP_STATE / "workroots" / rid)
    # the national panel ("United States", keyed US) meets results' "US"
    assert set(wide["pf"]) == set(OBS)
    fanq = FA.widen_fans(models, wide, FD)
    grid = {p["name"]: p for p in _grid(models)["panels"]}
    for m in MEMBERS:
        for loc in OBS:
            panel = grid["United States" if loc == "US" else loc]
            for h in (1, 2, 3, 4):
                q, row = fanq[m][loc][str(h)], panel["models"][m]["q"][h - 1]
                # stored horizon h is the target week FD + 7h
                assert panel["models"][m]["times"][h - 1] == TIMES[h - 1]
                assert q["0.025"] == min(row[0], q["0.1"])
                assert q["0.975"] == max(row[4], q["0.9"])
                assert q["0.025"] <= q["0.1"] < q["0.9"] <= q["0.975"]
                # the five stored levels are untouched
                for k, v in models[m][loc][str(h)].items():
                    assert q[k] == v
    # the page carries them
    page = _page()
    assert _const(page, "FANQ")["pf"]["US"]["1"]["0.975"] == \
        fanq["pf"]["US"]["1"]["0.975"]


def test_the_95_range_stays_outside_the_80_range():
    fanq = {"pf": {"Ohio": {"1": {"0.1": 10.0, "0.5": 20.0, "0.9": 30.0},
                            "2": {"0.1": 10.0, "0.5": 20.0, "0.9": 30.0}}}}
    wide = {"pf": {"Ohio": {TIMES[0]: {"0.025": 11.0, "0.975": 29.0}}}}
    got = FA.widen_fans(fanq, wide, FD)["pf"]["Ohio"]
    # rounding in the bundle can cross the 80% range: held at its edges
    assert (got["1"]["0.025"], got["1"]["0.975"]) == (10.0, 30.0)
    # a horizon the files do not cover keeps its levels only
    assert "0.025" not in got["2"] and got["2"] == fanq["pf"]["Ohio"]["2"]


def test_without_the_files_the_fans_keep_their_five_levels():
    rid, models = _hub_run(grid=False)
    assert FA.wide_levels(runs_mod.APP_STATE / "workroots" / rid) == {}
    assert FA.wide_levels("") == {}
    assert FA.widen_fans(models, {}, FD) == models
    fanq = _const(_page(), "FANQ")
    assert "0.025" not in fanq["pf"]["Ohio"]["1"]


def _dataset_run():
    """A real Groundhog run on an uploaded dataset's newest week; the
    dataset."""
    from app.core import datasets as D
    r = upload(grouped_bytes(pop=False), "Clinics")
    assert r.status_code == 303, r.text[:500]
    ds = D.get(r.headers["location"].split("source=")[1].split("#")[0])
    client.post("/run/dataset", data={
        "dataset": ds.id, "forecast_date": ds.forecast_dates()[-1],
        "locations": "all", "engine": "analogue"})
    row = runs_mod.Ledger().rows(1)[0]
    assert row["status"] == "ok", row
    return ds, row["run_id"]


def test_a_dataset_runs_95_range_comes_from_its_export_files():
    from app.core import custom_run as CR
    ds, rid = _dataset_run()
    wr = runs_mod.APP_STATE / "workroots" / rid
    files = list((wr / CR.EXPORT_DIR).glob("*/*.csv"))
    assert len(files) == 1
    keys = {str(k): n for n, k in CR.source_keys(ds).items()}
    want = {}
    with open(files[0], newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            lv = f"{float(r['output_type_id']):g}"
            if lv in FA.WIDE:
                want[(keys.get(r[CR.key_col(ds)], r[CR.key_col(ds)]),
                      r["target_end_date"], lv)] = float(r["value"])
    page = _page(f"/forecast?source={ds.id}")
    fanq = _const(page, "FANQ")
    fd = _const(page, "FCDATE")
    member = next(iter(fanq))
    seen = 0
    for loc, hs in fanq[member].items():
        for h, q in hs.items():
            t = (date.fromisoformat(fd)
                 + timedelta(days=7 * int(h))).isoformat()
            for lv in FA.WIDE:
                assert q[lv] == pytest.approx(want[(loc, t, lv)]), (loc, h)
                seen += 1
            assert q["0.025"] <= q["0.1"] <= q["0.9"] <= q["0.975"]
    assert seen == 2 * sum(len(hs) for hs in fanq[member].values()) > 0
    # the y axis: the file's value column is plainly "value"
    fanc = _const(page, "FANC")
    assert fanc["label"] == FA.DATASET_VALUE_LABEL == "Weekly value"
    assert fanc["kind"] == "count" and fanc["dataset"] == "Clinics"
    # the dataset's national group first when it names one
    assert fanc["first"] == (ds.national_group or "")


# ------------------------------------------- the axis and the first location


class _DS:
    def __init__(self, value_col=None):
        self.meta = {"columns": {"value": value_col} if value_col else {}}


def test_the_y_axis_says_what_is_counted():
    assert FA.HUB_VALUE_LABEL == "Weekly flu hospital admissions"
    # the run's recorded target (a hub-style file's) wins
    assert FA.dataset_value_label(_DS("admissions"), {"dataset": {
        "target": "wk inc covid hosp"}}) == "wk inc covid hosp"
    # "custom" is the run's word for no target: the file's value column
    assert FA.dataset_value_label(_DS("flu_pos_samples"), {"dataset": {
        "target": "custom"}}) == "Weekly flu pos samples"
    assert FA.dataset_value_label(_DS("admissions")) == "Weekly admissions"
    for col in ("value", "Observation", None):
        assert FA.dataset_value_label(_DS(col)) == "Weekly value", col
    assert FA.dataset_value_label(None) == "Weekly value"


def test_the_national_series_is_listed_first():
    fanq = {"pf": {"Alabama": {}, "Ohio": {}, "US": {}}}
    c = FA.fan_chart(fanq, label=FA.HUB_VALUE_LABEL, first_label="US (x)")
    assert (c["first"], c["first_label"]) == ("US", "US (x)")
    # drawn in the weekly report's order (the first sits under the rest)
    assert c["order"] == list(report_grid.MODELS)
    # a dataset: its national group, when the run forecast it
    c = FA.fan_chart({"pf": {"A": {}, "All": {}}}, label="x", kind="rate",
                     national="All")
    assert (c["first"], c["first_label"], c["kind"]) == ("All", "All", "rate")
    assert FA.fan_chart({"pf": {"A": {}}}, label="x",
                        national="All")["first"] == ""
    assert FA.fan_chart({"pf": {"A": {}}}, label="x")["first"] == ""


# ------------------------------------------------- the page's script, node

pytestmark_node = pytest.mark.skipif(not ZS.NODE, reason="no node to run "
                                     "the page's script")

# a page with every element the script reaches for; the chart calls, their
# layouts and the saved image recorded
STUB = r"""
var calls = [], els = {}, saved = [], clicked = [];
function mk(id){
  var e = {id: id, tag: '', hidden: id === 'fanx-modal', innerHTML: '',
    textContent: '', value: '', dataset: {}, selectedIndex: 0,
    children: [], attrs: {}, options: [], style: {}, disabled: false,
    firstElementChild: null, onclick: null, onchange: null};
  e.classList = {toggle: function(){}, add: function(){},
                 remove: function(){}, contains: function(){ return false; }};
  e.appendChild = function(c){ e.children.push(c);
    e.firstElementChild = e.firstElementChild || c; return c; };
  e.setAttribute = function(k, v){ e.attrs[k] = v; };
  e.getAttribute = function(k){ return e.attrs[k]; };
  e.addEventListener = function(){};
  e.querySelector = function(){ return mk('q'); };
  e.querySelectorAll = function(){ return e.children; };
  e.remove = function(){ e.removed = true; }; e.focus = function(){};
  e.click = function(){ clicked.push({href: e.href, download: e.download}); };
  e.content = {cloneNode: function(){ return mk('fragment'); }};
  return e;
}
var document = {documentElement: {}, activeElement: null, body: mk('body'),
  getElementById: function(id){ return els[id] || (els[id] = mk(id)); },
  createElement: function(tag){ var e = mk(''); e.tag = tag; return e; },
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
var FluCharts = {
  react: function(el, traces, layout){
    el.data = traces; el.layout = layout;
    calls.push({id: el && el.id, traces: traces, layout: layout}); },
  applyLayout: function(l){ return l; }};
var Plotly = {toImage: function(fig, opts){
  saved.push({fig: JSON.parse(JSON.stringify(fig)), opts: opts});
  return Promise.resolve('data:image/png;base64,AAAA'); }};
"""

# the drawn chart, view by view, at the location PICK
DRIVE = r"""
function chart(){
  var c = calls.filter(function(c){ return c.id === 'fanplot'; }).pop();
  return {
    title: c.layout.title.text, ytitle: c.layout.yaxis.title.text,
    note: (c.layout.legend.title || {}).text || '',
    medians: c.traces.filter(function(t){ return t.meta === 'median'; })
      .map(function(t){ return {name: t.name, group: t.legendgroup,
                                x: t.x, tip: t.customdata}; }),
    bands: c.traces.filter(function(t){ return t.fill === 'tonexty'; })
      .map(function(t){ return {name: t.name, legend: t.showlegend,
                                group: t.legendgroup, y: t.y}; }),
    observed: c.traces[0].customdata};
}
(async function(){
  var out = {first: null, views: {}};
  await new Promise(function(r){ setTimeout(r, 0); });
  var seg = els['fan-view'];
  out.buttons = seg.children.map(function(b){
    return [b.dataset.m, b.textContent, b.attrs['aria-pressed']]; });
  out.first = FLOCS[0];
  out.option = els['fan-loc'].children.map(function(o){
    return o.textContent; })[0];
  FIDX = FLOCS.indexOf(PICK); await drawFan();
  out.views.both = chart();
  // a model's button: that model alone, the location kept
  for (var i = 1; i < seg.children.length; i++){
    seg.children[i].onclick();
    await new Promise(function(r){ setTimeout(r, 0); });
    out.views[FMODEL] = chart();
    out.views[FMODEL].loc = FLOCS[FIDX];
    out.views[FMODEL].pressed = seg.children.map(function(b){
      return b.attrs['aria-pressed']; });
  }
  // Save figure, from the view that is on
  seg.children[0].onclick();
  await new Promise(function(r){ setTimeout(r, 0); });
  await els['fan-save'].onclick();
  out.saved = saved.map(function(s){ return {
    title: s.fig.layout.title.text, sub: s.fig.layout.title.subtitle.text,
    note: (s.fig.layout.legend.title || {}).text || '',
    names: s.fig.data.map(function(t){ return t.name; }),
    width: s.opts.width, height: s.opts.height, scale: s.opts.scale,
    format: s.opts.format}; });
  out.clicked = clicked;
  out.disabled = els['fan-save'].disabled;
  console.log(JSON.stringify(out));
})();
"""


def _drive(tmp_path, page: str, pick: str) -> dict:
    drv = tmp_path / "drive.js"
    drv.write_text(STUB + ZS._fan_script(page) + "\nvar PICK = "
                   + json.dumps(pick) + ";\n" + DRIVE, encoding="utf-8")
    out = subprocess.run([ZS.NODE, str(drv)], capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytestmark_node
def test_both_models_together_then_one_with_all_three_ranges(tmp_path):
    rid, models = _hub_run()
    page = _page()
    names = _const(page, "MNAMES")
    got = _drive(tmp_path, page, "Ohio")
    # the switch: every model together first, then each alone; on load,
    # together
    assert got["buttons"] == [["", "Both", "true"]] + [
        [m, names[m], "false"] for m in MEMBERS]
    # the national series first, under the Data card's name for it
    assert got["first"] == "US" and got["option"] == "US (national)"
    both = got["views"]["both"]
    assert both["title"] == "Ohio"
    assert both["ytitle"] == "Weekly flu hospital admissions"
    # each model: its median line, named, and its 95% range in its group
    assert sorted(m["name"] for m in both["medians"]) == sorted(
        names[m] + " median" for m in MEMBERS)
    assert sorted(b["group"] for b in both["bands"]) == sorted(MEMBERS)
    assert not any(b["legend"] for b in both["bands"])
    assert both["note"] == "Shaded: 95% of each model's forecasts fall here"
    fanq = _const(page, "FANQ")
    for b in both["bands"]:
        # the lower edge: the starting week, then 2.5% at each horizon
        assert b["y"][1:] == [fanq[b["group"]]["Ohio"][str(h)]["0.025"]
                              for h in (1, 2, 3, 4)]
    # one model alone: its 50%, 80% and 95% ranges, each named
    for m in MEMBERS:
        one = got["views"][m]
        assert one["loc"] == "Ohio"
        assert one["pressed"] == ["false"] + [
            "true" if x == m else "false" for x in MEMBERS]
        assert [x["name"] for x in one["medians"]] == [names[m] + " median"]
        assert [(b["name"], b["legend"]) for b in one["bands"]] == [
            ("95% of forecasts fall here", True),
            ("80% of forecasts fall here", True),
            ("50% of forecasts fall here", True)]
        assert one["note"] == ""


@pytestmark_node
def test_the_hover_gives_the_week_median_and_ranges_in_whole_counts(
        tmp_path):
    _hub_run()
    page = _page()
    names = _const(page, "MNAMES")
    fanq = _const(page, "FANQ")
    got = _drive(tmp_path, page, "US")
    med = next(m for m in got["views"]["pf"]["medians"])
    q = fanq["pf"]["US"]["2"]

    def whole(v):
        return f"{round(v):,}"
    # the line starts from the last week observed, then the four weeks
    assert med["tip"][0] == (f"<b>{names['pf']}</b> starts from week "
                             "ending Oct 17, 2026<br>observed 12,000")
    assert med["tip"][2] == (
        f"<b>{names['pf']}</b> · week ending Oct 31, 2026"
        f"<br>median {whole(q['0.5'])}"
        f"<br>50% range {whole(q['0.25'])} to {whole(q['0.75'])}"
        f"<br>95% range {whole(q['0.025'])} to {whole(q['0.975'])}")
    assert "." not in med["tip"][2].replace("Oct", "")    # no fractions
    assert got["views"]["both"]["observed"][-1] == (
        "observed · week ending Oct 17, 2026<br>12,000")


@pytestmark_node
def test_without_a_95_range_the_overlay_draws_the_80(tmp_path):
    _hub_run(grid=False)
    got = _drive(tmp_path, _page(), "Ohio")
    both = got["views"]["both"]
    assert both["note"] == "Shaded: 80% of each model's forecasts fall here"
    assert "<br>80% range " in both["medians"][0]["tip"][1]
    one = got["views"]["pf"]
    assert [b["name"] for b in one["bands"]] == [
        "80% of forecasts fall here", "50% of forecasts fall here"]


@pytestmark_node
def test_save_figure_writes_the_location_date_models_and_legend(tmp_path):
    _hub_run()
    page = _page()
    assert ('id="fan-save">' in page and "Save figure</button>" in page)
    names = _const(page, "MNAMES")
    got = _drive(tmp_path, page, "Ohio")
    assert len(got["saved"]) == 1
    s = got["saved"][0]
    assert s["title"] == "Ohio"
    assert s["sub"] == (f"Data as of {FD} · "
                        + " and ".join(names[m] for m in MEMBERS))
    assert s["note"] == "Shaded: 95% of each model's forecasts fall here"
    assert {names[m] + " median" for m in MEMBERS} <= set(s["names"])
    assert (s["format"], s["width"], s["height"], s["scale"]) == (
        "png", 1200, 760, 2)
    assert got["clicked"] == [{
        "href": "data:image/png;base64,AAAA",
        "download": f"flubnf_forecast_Ohio_{FD}_models.png"}]
    assert got["disabled"] is False


def test_the_card_uses_the_kits_switch_and_keeps_the_flusight_lines():
    t = (Path(__file__).resolve().parents[1] / "ui" / "templates"
         / "forecast.html").read_text(encoding="utf-8")
    card = t.split('<template id="fc-fan-tpl">', 1)[1].split("</template>")[0]
    assert ('<div class="uk-seg" role="group" aria-label="models shown" '
            'id="fan-view"></div>') in card
    assert 'class="seg"' not in card and "mbtn" not in t
    # the FluSight comparators still drawn on the hub chart
    assert "if(SHOWOFF) traces.push(...offTraces(loc, xs, ox, oy));" in t
