"""The Forecast tab's display-only aids (app/ui/forecast_aids.py): the
date's round row, the next round, the failed run's reason, the run the
fans draw, the location presets, the last form kept across a restart and
the form against the last run."""
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import forecast_aids as FA              # noqa: E402
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


def test_fan_run_badges_an_earlier_run():
    rows = [_row("20261005T182531-ecda8f", "error"),
            _row("20261005T182151-a7caef")]
    fr = FA.fan_run(rows, "20261005T182151-a7caef")
    assert fr["earlier"] is True and fr["label"].startswith("2026-09-26 · 10-05 18:21")
    assert FA.fan_run(rows[1:], "20261005T182151-a7caef")["earlier"] is False
    assert FA.fan_run(rows, None) is None


def test_last_run_values_as_the_form_holds_them():
    lr = FA.last_run_values([_row("20261005T182151-a7caef")])
    assert lr["engine"] == "all"
    assert lr["locations"] == ["Alabama", "New York", "Ohio", "US"]
    assert lr["knobs"]["pf.particles"] == "10000"
    assert "run.season_start" not in lr["knobs"]
    assert FA.last_run_values([]) is None


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
    assert 'data-preset="all"' in TEMPLATE and 'id="fc-locfilter"' in TEMPLATE
    filt = TEMPLATE.split('id="fc-locfilter"')[1].split(">")[0]
    assert "name=" not in filt
    chips = TEMPLATE.split('class="fc-presets"')[1].split("</div>")[0]
    assert "name=" not in chips
    # the expanded view's arrows are named; the card's arrows page by key
    assert 'id="fanx-prev" aria-label="previous location"' in TEMPLATE
    assert 'id="fanx-next" aria-label="next location"' in TEMPLATE
    assert "e.key==='ArrowLeft'" in TEMPLATE
    # the re-run is quiet beside the form's Run models
    assert '<button class="quiet" data-guard="console-run">Run again' in TEMPLATE
    html = client.get("/forecast").text
    assert 'id="fc-datestats"' in html and 'id="fc-locfilter"' in html
