"""The Output page lists the forecasts run so far, by forecast date,
newest first (app/ui/routes/output.forecast_dates, output.html).

  * one card per as-of date, headed by the hub's reference date;
  * per model, the file of the newest complete run for the date, else of
    the newest run that wrote one (archive_record.choose), with Download
    and Show in folder;
  * a modified-settings run's <model>-modified file sits under its date
    with a "modified settings" tag, never as the hub-named file;
  * own-data runs are listed apart ("Your data") with their exports;
  * nothing on the page reads as a submission workflow (no marks).
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

client = TestClient(srv.app)
GH, OR = "NAU_PyBNF-GroundHogCGR", "NAU_PyBNF-OracleSIHRS"


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _run(root, asof, dirs, status="ok", outcome=None, dataset=None,
         tag="x") -> Path:
    """A closed ledger row and its workroot with a file per model dir."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=asof,
                               locations=["Ohio"]), Path("pending"), {})
    w = root / "workroots" / rid
    ref = O._reference_date(asof)
    res = {"forecast_date": asof, "spec": "", "tag": tag}
    if dataset:
        res["dataset"] = {"id": "clinics-1", "name": dataset}
        d = w / "export" / "FluBNF-Groundhog"
        d.mkdir(parents=True)
        (d / f"{ref}-FluBNF-Groundhog.csv").write_text(tag)
    for m in dirs:
        d = w / "submission" / m
        d.mkdir(parents=True)
        (d / f"{ref}-{m}.csv").write_text(tag)
    w.mkdir(parents=True, exist_ok=True)
    (w / "results.json").write_text(json.dumps(res))
    led.set_workroot(rid, w)
    led.close_run(rid, status, outcome or {})
    ui_shared._invalidate_scans()        # as the pipeline does on close
    return w


def test_dates_are_listed_newest_first_one_card_each(root):
    a = _run(root, "2098-01-03", [GH])
    b = _run(root, "2098-01-17", [OR, GH])
    c = _run(root, "2098-01-10", [GH])
    dates, own = O.forecast_dates()
    assert [d["asof"] for d in dates] == ["2098-01-17", "2098-01-10",
                                          "2098-01-03"]
    assert [d["ref"] for d in dates] == ["2098-01-24", "2098-01-17",
                                         "2098-01-10"]
    assert [f["model"] for f in dates[0]["files"]] == [OR, GH]
    assert own == []
    html = client.get("/output").text
    assert html.index('id="fc-2098-01-17"') < html.index('id="fc-2098-01-10"') \
        < html.index('id="fc-2098-01-03"')
    assert "Forecast 2098-01-24" in html and "as of 2098-01-17" in html
    import re
    from urllib.parse import unquote
    offered = {unquote(m) for m in
               re.findall(r"/output/download\?path=([^\"'&>\s]+)", html)}
    assert offered == {str(p) for w in (a, b, c)
                       for p in w.glob("submission/*/*.csv")}
    assert html.count("Show in folder") == 4
    for gone in ("Mark as submitted", "Unmark", "Submitted</span>",
                 "Archived files", "holds an earlier run",
                 "No current submission files"):
        assert gone not in html


def test_a_rerun_shows_the_newest_complete_file_per_model(root):
    first = _run(root, "2098-01-03", [OR, GH], tag="first")
    # a newer run that dropped a location from the Oracle SIHRS file
    second = _run(root, "2098-01-03", [OR, GH], tag="second", outcome={
        "submission_dropped": {OR: {"Ohio": "no fit"}}})
    (d,) = O.forecast_dates()[0]
    by = {f["model"]: f for f in d["files"]}
    assert by[OR]["run_id"] == first.name and by[OR]["complete"]
    assert by[GH]["run_id"] == second.name
    # a newer complete run takes over
    third = _run(root, "2098-01-03", [OR], tag="third")
    (d,) = O.forecast_dates()[0]
    by = {f["model"]: f for f in d["files"]}
    assert by[OR]["run_id"] == third.name and by[GH]["run_id"] == second.name


def test_with_no_complete_run_the_newest_file_shows_marked_incomplete(root):
    _run(root, "2098-01-03", [GH], status="stopped")
    late = _run(root, "2098-01-03", [GH], status="partial")
    (d,) = O.forecast_dates()[0]
    (f,) = d["files"]
    assert f["run_id"] == late.name and not f["complete"]
    html = client.get("/output").text
    assert "(incomplete)</a>" in html


def test_a_modified_run_sits_under_its_date_with_a_tag(root):
    hub = _run(root, "2098-01-03", [GH])
    mod = _run(root, "2098-01-03", [GH + "-modified"])
    (d,) = O.forecast_dates()[0]
    assert [f["run_id"] for f in d["files"]] == [hub.name]
    (m,) = d["modified"]
    assert m["run_id"] == mod.name and m["modified"]
    assert m["name"].endswith(f"{GH}-modified.csv")
    html = client.get("/output").text
    card = html.split('id="fc-2098-01-03"', 1)[1]
    assert card.count("modified settings</span>") == 1
    tagged = card.split("modified settings</span>", 1)[1]
    assert f"{GH}-modified.csv" in tagged
    assert f"{GH}-modified.csv" not in card.split("modified settings</span>")[0]
    # a date with only a modified run lists it, never under the hub name
    only = _run(root, "2098-01-10", [OR + "-modified"])
    d2 = O.forecast_dates()[0][0]
    assert d2["files"] == [] and d2["modified"][0]["run_id"] == only.name


def test_own_data_runs_are_listed_apart_with_their_exports(root):
    _run(root, "2098-01-03", [GH])
    w = _run(root, "2098-01-10", [], dataset="Clinic admissions")
    dates, own = O.forecast_dates()
    assert [d["asof"] for d in dates] == ["2098-01-03"]     # not a hub date
    (r,) = own
    assert r["run_id"] == w.name and r["dataset"] == "Clinic admissions"
    (e,) = r["files"]
    assert e["model"] == "FluBNF-Groundhog"
    html = client.get("/output").text
    block = html.split('id="own-data"', 1)[1]
    assert "Your data" in html.split('id="own-data"', 1)[0][-200:] + block[:200]
    assert "Clinic admissions · as of 2098-01-10" in block
    assert "2098-01-17-FluBNF-Groundhog.csv" in block


def test_a_file_that_fails_the_hub_checks_says_so(root):
    _run(root, "2098-01-03", [GH], tag="not,a,hub,file")
    (d,) = O.forecast_dates()[0]
    (f,) = d["files"]
    assert not f["check"]["ok"] and f["check"]["text"].startswith("Fails ")
    html = client.get("/output").text
    assert '<span class="bad">Fails ' in html


def test_research_runs_and_retired_names_are_not_listed(root):
    w = _run(root, "2098-01-03", ["NAU-Ensemble"])
    res = json.loads((w / "results.json").read_text())
    r = _run(root, "2098-01-10", [GH])
    (r / "results.json").write_text(json.dumps(
        {"forecast_date": "2098-01-10", "spec": "", "research": True}))
    assert O.forecast_dates() == ([], [])
    assert res["forecast_date"] == "2098-01-03"
    assert (w / "submission" / "NAU-Ensemble").is_dir()     # kept on disk
