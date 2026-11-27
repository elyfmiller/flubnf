"""The Forecast tab's display-only aids (app/ui/forecast_aids.py): the
date's round row, the next round, the failed run's reason, the run the
fans draw, the location presets, the last form kept across a restart and
the form against the last run."""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

import served_dom as SD                             # noqa: E402
from app.ui import forecast_aids as FA              # noqa: E402
from app.ui import state as ui_state                # noqa: E402
from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)
TEMPLATE = (Path(__file__).resolve().parents[1] / "ui" / "templates"
            / "forecast.html").read_text(encoding="utf-8")
STATES = ["Alabama", "New York", "Ohio"]


def test_week_info_names_the_reference_date_and_window():
    w = FA.week_info("2026-10-03", today=date(2026, 10, 5))
    assert w["reference"] == "2026-10-10" and w["state"] == "due"
    assert w["badge"][0] == "warn" and "2026-10-07" in w["badge"][1]
    r = FA.week_info("2026-09-26", today=date(2026, 10, 5))
    assert r["reference"] == "2026-10-03"
    assert r["badge"] == ["neutral", "Not a FluSight round"]
    assert FA.week_info("soon") == {}
    got = client.get("/api/forecast/week-info?week=2026-09-26").json()
    assert got["reference"] == "2026-10-03"


def test_next_round_names_the_data_it_needs():
    nr = FA.next_round("2026-09-26", today=date(2026, 10, 5))
    assert nr == {"round": "2026-10-10", "needs": "2026-10-03",
                  "expected": "Wed Oct 7", "expected_past": False}
    # the default's own round is open: nothing to say
    assert FA.next_round("2026-10-03", today=date(2026, 10, 5)) is None


def test_error_head_is_the_first_clause_in_plain_plurals():
    e = ("prepare failed for all 53 location(s) (first: FAIL: prepare: "
         "netgen failed for Alabama: BioNetGen 2.9.2\n)")
    assert FA.error_head(e) == "Prepare failed for all 53 locations"
    assert FA.error_head("1 location(s) failed\nmore") == "1 location failed"
    assert FA.error_head("") == ""


def _row(rid, status="ok", locs=None, outcome=None):
    spec = {"engine": "all", "forecast_date": "2026-09-26",
            "locations": locs or STATES + ["US"], "replicates": 3,
            "particles": 10000}
    return {"run_id": rid, "status": status, "spec": json.dumps(spec),
            "outcome": json.dumps(outcome or {})}


def test_presets_read_the_latest_runs_pick_and_failures():
    rows = [_row("20261005T182531-ecda8f", "partial", ["Ohio", "New York"],
                 {"pf_failures": {"New_York_r0": "FAIL", "New_York_r1": "FAIL"}})]
    p = FA.presets(rows, STATES, "US (national)")
    assert p == {"last": ["Ohio", "New York"], "failed": ["New York"]}
    # a run that failed before any fit: every location it asked for
    rows = [_row("20261005T182531-ecda8f", "error", None,
                 {"error": "prepare failed for all 4 location(s) (first: x)"})]
    p = FA.presets(rows, STATES, "US (national)")
    assert p["failed"] == STATES + ["US (national)"]
    assert FA.presets([], STATES, "US (national)") == {"last": [], "failed": []}


def test_fan_run_badges_an_earlier_run_and_says_why():
    """M4: the badge said "The newest run left no forecasts to draw" even
    when the newest run had written them (its settings were modified).
    The badge now says why in its own words, and a modified run drawn is
    badged as such."""
    drawn = "20261005T182151-a7caef"
    rows = [_row("20261005T182531-ecda8f", "error"), _row(drawn)]
    fr = FA.fan_run(rows, drawn)
    assert fr["earlier"] == "earlier run · newest failed"
    assert fr["label"].startswith("2026-09-26 · 10-05 18:21")
    assert fr["modified"] is False
    assert FA.fan_run(rows[1:], drawn)["earlier"] == ""
    for status, why in (("stopped", "stopped"), ("running", "still running"),
                        ("interrupted", "interrupted"),
                        ("ok", "has no forecasts")):
        rows[0]["status"] = status
        assert FA.fan_run(rows, drawn)["earlier"] == f"earlier run · newest {why}"
    # the newest is a research run (never drawn on the Forecast tab)
    rows[0]["spec"] = json.dumps({"extra": {"members": 3}})
    assert FA.fan_run(rows, drawn)["earlier"] == "earlier run · newest is research"
    # a run with modified settings drawn: badged
    mod = dict(_row(drawn), spec=json.dumps(
        {"engine": "all", "forecast_date": "2026-09-26",
         "extra": {"knobs": {"oracle.w": 0.25}}}))
    assert FA.fan_run([mod], drawn) == {
        "run_id": drawn, "label": FA.fan_run([mod], drawn)["label"],
        "modified": True, "earlier": ""}
    assert FA.fan_run(rows, None) is None


def test_last_run_values_as_the_form_holds_them():
    lr = FA.last_run_values([_row("20261005T182151-a7caef")])
    assert lr["engine"] == "all"
    assert lr["locations"] == ["Alabama", "New York", "Ohio", "US"]
    assert lr["knobs"]["pf.particles"] == "10000"
    assert "run.season_start" not in lr["knobs"]
    assert "hub_names" not in lr                # a shipped run: no question
    assert FA.last_run_values([]) is None


def test_last_run_values_say_how_a_modified_runs_files_were_named():
    """After a modified run the override box starts unticked, so the Run
    row's 'Same as last run' must weigh the file names too: the last
    run's hub_names against the box (forecast.html)."""
    from app.core import knobs as K

    def row(override=""):
        r = _row("20261005T182151-a7caef")
        spec = json.loads(r["spec"])
        spec["extra"] = K.write_extra({"oracle.w": 0.25}, {}, override=override)
        r["spec"] = json.dumps(spec)
        return r
    assert FA.last_run_values([row("weekly decision")])["hub_names"] is True
    assert FA.last_run_values([row()])["hub_names"] is False
    src = (Path(FA.__file__).parent / "templates" / "forecast.html").read_text()
    assert "tick.checked !== LAST.hub_names) diff.push('File names')" in src
    # a difference is no fault: it is said in quiet words, as "Same as
    # last run" is, in the one slot beside Run models
    assert "FluBNFUI.setBadge(badge, 'neutral', 'Differs: '" in src
    assert "FluBNFUI.setBadge(badge, 'ok', 'Same as last run')" in src
    assert "setBadge(badge, 'warn'" not in src


def test_the_last_form_survives_a_restart_without_its_date(monkeypatch, tmp_path):
    from app.core import runs as _runs
    monkeypatch.setattr(_runs, "APP_STATE", tmp_path)
    form = {"forecast_date": "2026-09-26", "locations": ["Ohio"],
            "engine": "pf", "replicates": 5, "data_choices": {"x": {}},
            "ms_refused": False, "knobs": {"pf.jitter": "0.2"}}
    FA.save_last_form(form)
    kept = json.loads((tmp_path / FA.LAST_FORM_NAME).read_text())
    assert kept == {"locations": ["Ohio"], "engine": "pf", "replicates": 5,
                    "knobs": {"pf.jitter": "0.2"}}
    # written by this process: never restored (already in memory)
    monkeypatch.setitem(FA._restored, "done", False)
    mem = {}
    assert FA.restore_last_form(mem, lambda: "2026-10-03") is False
    # written by an earlier process: restored once, dated the default
    old = time.time() - 3600
    os.utime(tmp_path / FA.LAST_FORM_NAME, (old, old))
    monkeypatch.setattr(FA, "_STARTED", time.time())
    monkeypatch.setitem(FA._restored, "done", False)
    assert FA.restore_last_form(mem, lambda: "2026-10-03") is True
    assert mem["forecast_date"] == "2026-10-03" and mem["engine"] == "pf"
    assert FA.restore_last_form({}, lambda: "2026-10-03") is False   # once


def test_the_page_carries_the_aids():
    # presets and the filter post nothing: no name on them
    assert '<option value="all">All 53</option>' in TEMPLATE
    assert 'id="fc-locfilter"' in TEMPLATE
    filt = TEMPLATE.split('id="fc-locfilter"')[1].split(">")[0]
    assert "name=" not in filt
    pick = TEMPLATE.split('class="fc-presets"')[1].split("</div>")[0]
    assert '<select id="fc-preset" aria-label="Location presets">' in pick
    assert "name=" not in pick
    # one select: the three fixed picks, the remembered ones when there
    # are any (the failed one counted in parentheses, as "States only
    # (52)" beside it), and Custom, which the script shows for any other
    # pick and which cannot be chosen
    for opt in ('<option value="states">States only (52)</option>',
                '<option value="us">US only</option>',
                '>Last pick</option>',
                '>Failed last run ({{ pre.failed | length }})</option>',
                '<option value="custom" disabled hidden>Custom</option>'):
        assert opt in pick, opt
    assert "if (o.value === 'custom') o.hidden = !!hit;" in TEMPLATE
    assert ("if (o.selected && o.value !== 'custom') apply(o);"
            in TEMPLATE)
    # the expanded view's arrows are named; the card's arrows page by key
    assert 'id="fanx-prev" aria-label="previous location"' in TEMPLATE
    assert 'id="fanx-next" aria-label="next location"' in TEMPLATE
    assert "e.key==='ArrowLeft'" in TEMPLATE
    # the re-run is quiet beside the form's Run models
    assert '<button class="quiet" data-guard="console-run">Run again' in TEMPLATE
    html = client.get("/forecast").text
    assert 'id="fc-datestats"' in html and 'id="fc-locfilter"' in html


#: what the location script needs beyond the small DOM: a window, a class
#: list, and global listeners (the list's fade measures nothing here)
_LOC_STUBS = """
globalThis.window = globalThis;
globalThis.addEventListener = function () {};
Object.defineProperty(Object.getPrototypeOf(document), 'classList', {
  get: function () {
    var el = this;
    function list() { return (el.getAttribute('class') || '').split(/\\s+/)
                               .filter(Boolean); }
    return {contains: function (c) { return list().indexOf(c) >= 0; },
            toggle: function (c, on) {
              var l = list().filter(function (x) { return x !== c; });
              if (on === undefined ? list().indexOf(c) < 0 : on) l.push(c);
              el.setAttribute('class', l.join(' '));
            }};
  }});
"""


@pytest.mark.skipif(not SD.HAVE_JS, reason="no JavaScript engine")
def test_the_preset_select_sets_the_list_and_shows_the_pick(tmp_path):
    """The four preset chips became one select (review 2026-11-27, B21):
    choosing a preset sets the boxes as the chip did, and the select shows
    the pick's preset, or Custom for any other pick. Run on the served
    page's own markup and script."""
    ui_state._last_form.clear()
    html = client.get("/forecast").text
    script = next(x for x in re.findall(r"<script>(.*?)</script>", html, re.S)
                  if "// the location checklist." in x)
    f = tmp_path / "locations.js"
    f.write_text(script, encoding="utf-8")
    got = SD.run(tmp_path / "js", html, [f], """
      var sel = document.getElementById('fc-preset');
      function state() {
        var custom = sel.options.filter(function (o) {
          return o.value === 'custom'; })[0];
        return [sel.options.filter(function (o) { return o.selected; })
                   .map(function (o) { return o.value; }).join(),
                custom.hidden,
                document.getElementById('lcount').textContent,
                document.getElementById('ck-all').checked,
                document.getElementById('ck-us').checked,
                document.querySelectorAll('.ck-one:checked').length];
      }
      function choose(v) {
        sel.options.forEach(function (o) { o.selected = o.value === v; });
        sel.fire('change');
      }
      var out = [state()];
      choose('states'); out.push(state());
      choose('us'); out.push(state());
      var ohio = document.querySelectorAll('.ck-one').filter(function (c) {
        return c.value === 'Ohio'; })[0];
      ohio.checked = true; ohio.fire('change'); out.push(state());
      choose('all'); out.push(state());
      return out;""", prelude=_LOC_STUBS)
    assert got == [
        ["all", True, "all 53", True, True, 52],
        ["states", True, "52 selected", False, False, 52],
        ["us", True, "US only", False, True, 0],
        ["custom", False, "1 + US selected", False, True, 1],
        ["all", True, "all 53", True, True, 52],
    ]
