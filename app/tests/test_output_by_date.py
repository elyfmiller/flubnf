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
         tag="x", spec="") -> Path:
    """A closed ledger row and its workroot with a file per model dir."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date=asof,
                               locations=["Ohio"]), Path("pending"), {})
    w = root / "workroots" / rid
    ref = O._reference_date(asof)
    res = {"forecast_date": asof, "spec": spec, "tag": tag}
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
    # the newest date is a card (Show in folder per file); the earlier
    # ones are lines with a download per file
    assert html.count("Show in folder") == 2
    assert html.count('class="out-line"') == 2
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


def test_a_newer_run_on_a_few_states_does_not_replace_the_whole_set(root):
    whole = _run(root, "2098-01-03", [OR, GH], tag="whole")
    _run(root, "2098-01-03", [GH], tag="ohio",
         spec=json.dumps({"locations": ["Ohio"]}))
    (d,) = O.forecast_dates()[0]
    by = {f["model"]: f for f in d["files"]}
    assert by[GH]["run_id"] == whole.name and by[OR]["run_id"] == whole.name


def test_runs_started_in_the_same_second_show_the_one_opened_last(root):
    """A run id carries only its start second; its random suffix says
    nothing of order. Of two complete runs started in one second, the card
    shows the one the ledger opened last, the run the report button
    (shared._latest_results) and the archive hold, not the one whose
    suffix sorts last."""
    import time
    first, second = "20981001T100424-ffffff", "20981001T100424-000000"
    led = Ledger()
    now = time.time()
    for k, rid in enumerate((first, second)):
        w = root / "workroots" / rid
        for m in (OR, GH):
            d = w / "submission" / m
            d.mkdir(parents=True)
            (d / f"{O._reference_date('2098-01-03')}-{m}.csv").write_text(rid)
        (w / "results.json").write_text(json.dumps(
            {"forecast_date": "2098-01-03", "spec": ""}))
        led._db.execute(
            "INSERT INTO runs (run_id, created_utc, spec_json, workroot, "
            "status, outcome_json) VALUES (?,?,?,?,?,?)",
            (rid, now + 0.5 * k, "{}", str(w), "ok", "{}"))
    led._db.commit()
    ui_shared._invalidate_scans()
    assert ui_shared._latest_results()[0] == second
    (d,) = O.forecast_dates()[0]
    assert [f["run_id"] for f in d["files"]] == [second, second]


def test_with_no_complete_run_the_newest_file_shows_marked_incomplete(root):
    _run(root, "2098-01-03", [GH], status="stopped")
    late = _run(root, "2098-01-03", [GH], status="partial")
    (d,) = O.forecast_dates()[0]
    (f,) = d["files"]
    assert f["run_id"] == late.name and not f["complete"]
    html = client.get("/output").text
    # the run link carries a warn badge (its tip: why the file shows)
    after = html.split(f'href="/runs/{late.name}"', 1)[1][:1200]
    assert "uk-badge--warn" in after
    assert '<span class="uk-badge-t">incomplete</span>' in after


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
    # one group per run: the dataset's name over its as-of
    assert ">Clinic admissions</h3>" in block and "as of 2098-01-10" in block
    assert "2098-01-17-FluBNF-Groundhog.csv" in block


def test_a_file_that_fails_the_hub_checks_says_so(root):
    _run(root, "2098-01-03", [GH], tag="not,a,hub,file")
    (d,) = O.forecast_dates()[0]
    (f,) = d["files"]
    assert not f["check"]["ok"] and f["check"]["text"].startswith("Fails ")
    html = client.get("/output").text
    # an error badge, in a word and an icon; its tip lists the problems
    from markupsafe import escape
    assert 'uk-badge--error' in html
    assert '<span class="uk-badge-t">Fails ' in html
    assert str(escape(f["check"]["text"].split(": ", 1)[1])) in html


def test_research_runs_and_retired_names_are_not_listed(root):
    w = _run(root, "2098-01-03", ["NAU-Ensemble"])
    res = json.loads((w / "results.json").read_text())
    r = _run(root, "2098-01-10", [GH])
    (r / "results.json").write_text(json.dumps(
        {"forecast_date": "2098-01-10", "spec": "", "research": True}))
    assert O.forecast_dates() == ([], [])
    assert res["forecast_date"] == "2098-01-03"
    assert (w / "submission" / "NAU-Ensemble").is_dir()     # kept on disk


def test_each_date_card_names_its_hub_window_in_a_badge(root):
    """The window is a badge after the card's title (a state in a word and
    an icon); its sentence and the hub's rule are the badge's tip."""
    import datetime as dt
    due = O._date_status("2026-10-10", today=dt.date(2026, 10, 6))
    assert due["state"] == "due"
    assert due["text"] == "Due Wed 2026-10-07, 11 PM ET."
    assert due["badge"] == ("warn", "Due Wed 2026-10-07, 11 PM ET")
    soon = O._date_status("2026-10-10", today=dt.date(2026, 10, 1))
    assert soon["badge"] == ("pending",
                             "Due Sun 2026-10-04 to Wed 2026-10-07, 11 PM ET")
    # the close in UTC for the page to name in the reader's clock
    # (11 PM EDT on Wed 2026-10-07 is 03:00 UTC on the Thursday)
    assert due["deadline"] == soon["deadline"] == "2026-10-08T03:00:00Z"
    shut = O._date_status("2026-10-10", today=dt.date(2026, 10, 8))
    assert shut["badge"] == ("neutral", "Window closed")
    assert shut["text"] == "The window closed Wed 2026-10-07."
    assert O._date_status("2026-07-11")["badge"] == ("neutral",
                                                     "Not a FluSight round")
    _run(root, "2098-01-03", [GH])
    card = client.get("/output").text.split('id="fc-2098-01-03"', 1)[1]
    assert '<span class="uk-badge-t">Not a FluSight round</span>' in card
    tip = card.split('id="tip-out-win-1"', 1)[1].split("</span>", 1)[0]
    assert ("2098-01-10 is not a FluSight round, so its files are a "
            "record.") in tip


def test_a_seasons_older_dates_sit_behind_one_fold(root):
    """The newest date is a card and the next three are lines; older ones
    are in one closed fold whose summary counts them and names their span,
    every file still offered for download."""
    for asof in ("2098-01-03", "2098-01-10", "2098-01-17", "2098-01-24",
                 "2098-01-31"):
        _run(root, asof, [GH])
    html = client.get("/output").text
    head, fold = html.split('<details class="out-older" id="out-older">', 1)
    assert head.count('class="card out-day"') == 1
    assert head.count('class="out-line"') == 3
    assert 'id="fc-2098-01-03"' in fold and 'id="fc-2098-01-03"' not in head
    assert "1 earlier forecast date<" in fold
    assert "2098-01-10 to 2098-01-10" in fold
    assert html.count("/output/download?path=") == 5


def test_each_files_coverage_fold_has_its_own_handle(root):
    """Two files missing a location: two folds, "1 of 2 locations" and
    "1 missing" each, their ids (and so their tips' ids) distinct."""
    import re
    _run(root, "2098-01-03", [OR, GH], tag="location\n39\n",
         spec=json.dumps({"locations": ["Ohio", "Utah"]}))
    html = client.get("/output").text
    ids = re.findall(r'<details class="uk-fold" id="(cov-[0-9a-f]+)"', html)
    assert len(ids) == 2 and len(set(ids)) == 2
    assert html.count("1 of 2 locations") == 2
    assert html.count('<span class="uk-badge-t">1 missing</span>') == 2
    assert "<b>Utah</b>: no forecast was recorded for it" in html


def test_refusals_and_missing_reports_are_console_pages(root):
    """A bad date, a report that is not there or a refused download is a
    page of the console (the Output tab: one line and the way back), with
    the status code it always had."""
    r = client.get("/output/report?date=nope")
    assert r.status_code == 400 and 'role="alert"' in r.text
    assert "Invalid date. Expected YYYY-MM-DD." in r.text
    assert 'aria-current="page">Output</a>' in r.text
    r = client.get("/output/report/download?date=nope")
    assert r.status_code == 400 and 'role="alert"' in r.text
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200
    assert "No archived report for 2098-01-03" in r.text
    r = client.get("/output/report")
    assert r.status_code == 200 and "No report yet" in r.text
    assert 'href="/forecast"' in r.text and "Run the models first." in r.text
    r = client.get("/output/report/download")
    assert r.status_code == 404 and "No report to download" in r.text
    r = client.get("/output/download", params={"path": "/etc/hosts"})
    assert r.status_code == 404 and "File not found in app state" in r.text
    assert 'href="/output"' in r.text                    # the way back
