"""Which run a page shows (the 2026-10-25 bug hunt, G06).

  * Output's weekly report card keeps the newest run (app.md, 2026-10-01);
    when that is a newer run on a few states, the week's archived report
    (the whole-set run's, the one the date card shows) stays in the
    picker, now named for what it offers (OU-01, OU-11);
  * a vintage run of a past week never replaces the run made in that
    week, on Output or in the archive (OU-02);
  * a run's page and report come from the archive once Storage deleted
    its workroot, as Output's files do (OU-09);
  * Home, Models and Output's report pass over a run whose one model
    produced nothing (HM-05); the Models card names the run it shows
    (MO-06); Output's "i" and its live badge state the rules they follow
    (OU-08).
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                               # noqa: E402
from app.core import archive_record as AR                      # noqa: E402
from app.core.runs import Ledger, RunSpec                      # noqa: E402
from app.ui import pipeline as P                               # noqa: E402
from app.ui import server as srv                               # noqa: E402
from app.ui import shared as ui_shared                         # noqa: E402
from app.ui import state as ui_state                           # noqa: E402
from app.ui.routes import output as O                          # noqa: E402

from test_optional_outputs import pipeline_env                 # noqa: E402,F401
from test_oracle_step import ASOF, hubfiles                    # noqa: E402,F401

client = TestClient(srv.app)
GH = "NAU_PyBNF-GroundHogCGR"
DATE = "2098-01-03"
FAN = {"1": {"0.5": 10.0}}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    before = dict(ui_state._status)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    ui_state._status["running"] = None
    ui_state._status["workroot"] = None
    ui_shared._invalidate_scans()
    yield tmp_path
    ui_state._status.clear()
    ui_state._status.update(before)
    ui_shared._invalidate_scans()


def _all53():
    from flubnf.settings import load_locations
    return [n for n in load_locations().location_name if n != "US"] + ["US"]


def _run(root, tag, locations=("Ohio",), mode="realtime", engine="analogue",
         models=None, asof=DATE) -> str:
    """A closed run with a Groundhog file and a weekly report; its id."""
    import time
    time.sleep(1.05)                     # run ids sort by their start second
    spec = RunSpec(engine=engine, forecast_date=asof,
                   locations=list(locations), extra={"mode": mode})
    led = Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    w = root / "workroots" / rid
    d = w / "submission" / GH
    d.mkdir(parents=True)
    (d / f"{O._reference_date(asof)}-{GH}.csv").write_text(tag)
    (w / "report.html").write_text(f"<html><body>REPORT {tag}</body></html>")
    (w / "results.json").write_text(json.dumps(
        {"forecast_date": asof, "spec": json.dumps(asdict(spec)),
         "models": models if models is not None
         else {"analogue": {n: FAN for n in locations}}}))
    led.set_workroot(rid, w)
    led.close_run(rid, "ok", {})
    ui_shared._invalidate_scans()
    return rid


def _shown_file(asof=DATE) -> str:
    """The Groundhog file Output shows for a date, read back."""
    (d,) = [x for x in O.forecast_dates()[0] if x["asof"] == asof]
    (f,) = [f for f in d["files"] if f["model"] == GH]
    return Path(f["path"]).read_text()


# ------------------------------------------- the report card and its picker

def test_the_weeks_archived_report_stays_reachable_beside_a_newer_few_state_run(
        root):
    whole = _run(root, "whole", _all53())
    P._archive_run(root / "workroots" / whole, DATE)
    html = client.get("/output").text
    card = html.split('id="weekly-report"', 1)[1]
    assert f'href="/runs/{whole}/report"' in card
    assert f'<option value="{DATE}">' not in html     # the card offers it
    ohio = _run(root, "ohio")
    html = client.get("/output").text
    card = html.split('id="weekly-report"', 1)[1]
    # the card keeps the newest run; the date shows the whole-set file
    assert f'href="/runs/{ohio}/report"' in card
    assert _shown_file() == "whole"
    # and the week's archived report, the whole set's, is in the picker
    ref = O._reference_date(DATE)
    assert (f'<label for="archreport">Archived weeks</label>' in html)
    assert f'<option value="{DATE}">{ref} (as of {DATE})</option>' in html
    assert "Earlier weeks" not in html
    assert "REPORT whole" in client.get(f"/output/report?date={DATE}").text


# ------------------------------------------------- a vintage run of a past week

def test_a_vintage_run_of_a_past_week_never_replaces_the_run_made_in_that_week(
        root):
    week = _run(root, "in its week", _all53())
    P._archive_run(root / "workroots" / week, DATE)
    later = _run(root, "backtest", _all53(), mode="vintage")
    assert _shown_file() == "in its week"
    out = P._archive_run(root / "workroots" / later, DATE, realtime=False)
    assert out.startswith("kept: this run is a vintage run of a past week")
    assert AR.read_record(root / "archive" / DATE)["run_id"] == week
    # with no run made in that week, the vintage run is the date's
    other = "2098-01-10"
    only = _run(root, "only backtest", _all53(), mode="vintage", asof=other)
    assert _shown_file(other) == "only backtest"
    assert not P._archive_run(root / "workroots" / only, other,
                              realtime=False).startswith("kept")


def test_choose_takes_a_run_made_in_its_week_before_a_later_vintage_run():
    week = {"run_id": "20980103T100000-a", "complete": False, "full": False}
    vintage = {"run_id": "20980110T100000-b", "complete": True, "full": True,
               "realtime": False}
    assert AR.choose([week, vintage]) is week
    assert AR.choose([vintage]) is vintage
    assert AR.realtime_of(json.dumps({"extra": {"mode": "vintage"}})) is False
    assert AR.realtime_of(json.dumps({"extra": {"mode": "realtime"}}))
    assert AR.realtime_of("") and AR.realtime_of("{bad")  # an old record


def test_the_pipeline_hands_the_runs_mode_to_the_archive(pipeline_env,
                                                        monkeypatch):
    from app.ui.routes import forecast as F
    seen = []
    monkeypatch.setattr(P, "_archive_run", lambda w, d, **k: seen.append(
        k.get("realtime", True)) or "archived")
    for mode in ("realtime", "vintage"):
        P._run_all(RunSpec(engine="all", forecast_date=ASOF,
                           locations=pipeline_env["names"], replicates=1,
                           extra=F._run_extra(2, mode)))
    assert seen == [True, False]


# --------------------------------------------- a run whose workroot is gone

def test_a_runs_page_and_report_come_from_the_archive_once_its_workroot_is_gone(
        root):
    import shutil
    whole = _run(root, "whole", _all53())
    P._archive_run(root / "workroots" / whole, DATE)
    shutil.rmtree(root / "workroots" / whole)
    ui_shared._invalidate_scans()
    page = client.get(f"/runs/{whole}").text
    assert f"{O._reference_date(DATE)}-{GH}.csv" in page
    assert "No submission files" not in page
    assert f'href="/runs/{whole}/report"' in page
    r = client.get(f"/runs/{whole}/report")
    assert r.status_code == 200 and "REPORT whole" in r.text
    r = client.get(f"/runs/{whole}/report/download")
    assert r.status_code == 200 and "REPORT whole" in r.text
    # a run nothing holds any more still answers "no report"
    gone = _run(root, "gone")
    shutil.rmtree(root / "workroots" / gone)
    assert client.get(f"/runs/{gone}/report").status_code == 404


# ------------------------------------------ the shipped pages and the Models card

def test_a_run_whose_one_model_produced_nothing_never_replaces_the_shown_run(
        root):
    shown = _run(root, "two states", ("Arizona", "New York"))
    failed = _run(root, "oracle failed", engine="pf",
                  models={"pf": {}, "analogue": {"Ohio": FAN}})
    assert ui_shared._latest_results()[0] == shown
    assert ui_shared._latest_results(include_modified=True)[0] == shown
    # the Forecast tab shows the newest run, whatever it produced
    assert ui_shared._latest_results(include_modified=True,
                                     newest=True)[0] == failed


def test_a_run_that_wrote_either_member_or_has_no_models_table_is_shown(root):
    _run(root, "older")
    # a "Both" run without the filter wrote the Groundhog alone: that is a run
    both = _run(root, "groundhog alone", engine="all",
                models={"pf": {}, "analogue": {"Ohio": FAN}})
    assert ui_shared._latest_results()[0] == both
    # an Oracle-only run whose record predates the models table is never
    # skipped for it, nor one whose fits all failed on a record with no spec
    old = _run(root, "no tables", engine="pf", models={})
    assert ui_shared._latest_results()[0] == old
    bare = _run(root, "no spec", engine="pf", models={"pf": {}})
    w = root / "workroots" / bare / "results.json"
    rec = json.loads(w.read_text()); rec.pop("spec"); w.write_text(json.dumps(rec))
    ui_shared._invalidate_scans()
    assert ui_shared._latest_results()[0] == bare


def test_the_models_card_names_the_real_time_run_it_shows(root):
    week = _run(root, "in its week")
    _run(root, "backtest", mode="vintage", asof="2097-12-27")
    html = " ".join(client.get("/model/analogue").text.split())
    assert "Latest real-time run" in html
    assert f'href="/runs/{week}"' in html
    # the newer backtest shows on the Forecast tab: the card says so
    assert '<a href="/forecast">Newer run on the Forecast tab</a>' in html
    # with no real-time run, the newest run is plainly the latest
    import shutil
    shutil.rmtree(root / "workroots" / week)
    ui_shared._invalidate_scans()
    html = " ".join(client.get("/model/analogue").text.split())
    assert "Latest run" in html and "Latest real-time run" not in html
    assert "Newer run on the Forecast tab" not in html


# ------------------------------------------------------------ Output's words

def test_outputs_words_state_the_rules_it_follows(root):
    _run(root, "whole", _all53())
    html = " ".join(client.get("/output").text.split())
    assert "the newest run that finished complete" not in html
    assert ("from the newest complete run on all 53 locations, else the "
            "newest complete run, else the newest run that wrote one; a run "
            "made in the round's own week comes before a later vintage "
            "run") in html
    assert "The round open now is outlined" not in html
    # a run writing a date: the badge says so and promises nothing
    led = Ledger()
    rid = led.open_run(RunSpec(engine="analogue", forecast_date=DATE,
                               locations=["Ohio"]), Path("pending"), {})
    ui_state._status["running"] = f"run:{rid}"
    html = " ".join(client.get("/output").text.split())
    assert "newer run in progress" in html
    assert "A console run for this date is in progress." in html
    assert "this card shows its files" not in html
