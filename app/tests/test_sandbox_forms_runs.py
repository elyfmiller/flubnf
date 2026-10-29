"""The Sandbox's forms and runs say and keep what they should: an upload
over the limit never costs the editor's text, Load data names the weeks it
loaded and calls no future week missing, two datasets of one name are told
apart, every run of a model is counted and reachable, the New model form
suggests free names and comes back as posted after a refusal, an Oracle
start fits one season, and the one-run-at-a-time refusals claim no engine
a Groundhog-only run does not use. Hub-free and engine-free
(conftest.sandbox_root)."""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                      # noqa: E402
import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.core import sandbox_data as sbd                 # noqa: E402
from app.ui import server as srv                         # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui.routes import sandbox as rs                  # noqa: E402

client = TestClient(srv.app)
STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"


@pytest.fixture
def box(sandbox_root):
    return sandbox_root


def _runs(n, model="kinetics_example"):
    for i in range(n):
        d = sb.RUNS / f"2099010{i // 10}-0000{i % 10:02d}_{model}"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps(
            {"model": model, "status": "stopped", "particles": 500,
             "started_utc": "2099-01-01T00:00:00Z"}))


# -------------------------------------------- SB-02: an upload over the limit

def test_an_upload_over_the_limit_is_refused_before_the_editor_text_goes(box):
    sb.add_example("kinetics_example")
    html = client.get("/sandbox?model=kinetics_example").text
    assert f'data-max-bytes="{sb.UPLOAD_MAX_BYTES}"' in html
    js = (STATIC / "sandbox.js").read_text(encoding="utf-8")
    # the page refuses it before it leaves, keeping the unsaved edits
    assert "f.size > max" in js and "e.preventDefault();" in js
    # a body the server reads none of says the editor's text went unread too
    big = b"x" * (32 * 1024 * 1024)            # past the read cap too
    client.post("/sandbox/models/kinetics_example/upload-data",
                files={"csv": ("big.csv", big, "text/csv")},
                data={"model_bngl": "# MY EDIT"}, follow_redirects=False)
    page = client.get("/sandbox?model=kinetics_example").text
    assert ("nothing was read past it or stored, and unsaved edits in the "
            "editor were not saved.") in page


# ------------------------------------------- SB-03: the weeks loaded, no future

def test_load_data_counts_no_week_past_the_sources_newest_as_missing(
        monkeypatch):
    from app.core import data as data_mod, scoring
    weeks = {"2026-09-26": 5.0, "2026-10-03": 6.0, "2026-10-10": 7.0}
    monkeypatch.setattr(data_mod, "vintage_series", lambda d, loc: {
        "dates": list(weeks), "values": list(weeks.values())})
    # the vintage of 2026-10-10 cannot hold 2026-10-17: not missing
    v = sbd.series_for("New York", "2026-09-26", "2026-10-17",
                       asof="2026-10-10")
    assert v["dates"] == list(weeks) and v["dropped"] == 0
    # settled truth: no week past the newest any location has is missing,
    # but a location short of that newest week is
    ts = pd.Timestamp
    truth = {("36", ts(d)): x for d, x in weeks.items()}
    truth[("04", ts("2026-10-17"))] = 9.0
    monkeypatch.setattr(scoring, "load_truth", lambda: (
        truth, {"New York": "36", "Arizona": "04"}))
    assert sbd.series_for("New York", "2026-09-26",
                          "2026-12-31")["dropped"] == 1
    # a week the source does hold is still missing
    del weeks["2026-10-03"]
    v = sbd.series_for("New York", "2026-09-26", "2026-10-17",
                       asof="2026-10-10")
    assert v["dropped"] == 1


def test_load_data_names_the_weeks_it_loaded_not_the_range_asked_for():
    ui_state._status.pop("flash", None)
    rs._sandbox_fill_flash({"asof": "2026-10-10", "rows": 3,
                            "location": "New York", "start": "2026-09-26",
                            "end": "2026-10-17", "dropped": 0,
                            "dates": ["2026-09-26", "2026-10-03",
                                      "2026-10-10"]})
    assert ("3 weeks of New York, 2026-09-26 to 2026-10-10."
            in ui_state._status["flash"])


# ------------------------------------------ SB-06: two datasets of one name

def test_two_datasets_of_one_name_are_told_apart_by_their_weeks(monkeypatch):
    from app.core import datasets

    def ds(i, first, last):
        return types.SimpleNamespace(
            id=f"cases-{i}", name="cases", kind="count", pf_eligible=False,
            meta={"groups": [{"name": "cases", "first": first,
                              "last": last}]})
    monkeypatch.setattr(datasets, "list_datasets", lambda: [
        ds(1, "2024-01-06", "2024-06-29"), ds(2, "2025-01-04", "2025-03-29"),
        types.SimpleNamespace(id="flu-3", name="flu", kind="count",
                              pf_eligible=False, meta={"groups": []})])
    labels = [d["label"] for d in sbd.dataset_choices()]
    assert labels == ["cases (2024-01-06 to 2024-06-29)",
                      "cases (2025-01-04 to 2025-03-29)", "flu"]


# --------------------------------------------- SB-08: every run is counted

def test_a_model_with_27_runs_counts_and_lists_all_27(box):
    sb.add_example("kinetics_example")
    _runs(27)
    html = client.get("/sandbox?model=kinetics_example").text
    assert ">27 runs<" in html
    assert 'data-sb-delete="kinetics_example and its 27 runs"' in html
    # the oldest run is reachable from the list
    assert "/sandbox?run=20990100-000000_kinetics_example&amp;model=" in html


# ------------------------------- SB-09 and SB-17: the New model form's names

def test_the_new_model_form_suggests_names_no_model_has(box):
    sb.add_example("kinetics_example")
    html = client.get("/sandbox").text
    form = html.split('<form method="post" action="/sandbox/new"', 1)[1]
    assert 'data-taken="kinetics_example"' in form.split(">", 1)[0]
    # a copy start names its copy (it blanked the field)
    assert ('value="copy:kinetics_example" data-note="A copy of '
            'kinetics_example, with its data and priors." '
            'data-name="kinetics_example_copy_1"') in form
    js = (STATIC / "sandbox.js").read_text(encoding="utf-8")
    assert "s = free(suggestName(loc.value, date.value));" in js


def test_a_refused_new_model_comes_back_as_it_was_posted(box):
    sb.add_example("kinetics_example")
    client.post("/sandbox/new", data={
        "name": "kinetics_example", "start": "skeleton",
        "season_start": "2026-08-01"}, follow_redirects=False)
    html = client.get("/sandbox").text
    assert "already exists" in html
    name = html.split('id="sbnew-name"', 1)[1].split(">", 1)[0]
    assert 'value="kinetics_example" data-kept' in name
    assert ('<option value="skeleton" data-note="The smallest runnable '
            'model') in html
    assert 'data-name="skeleton_1" selected>Blank skeleton' in html
    assert 'name="season_start" type="date" value="2026-08-01"' in html
    # one-shot: the next visit is the plain form
    assert "data-kept" not in client.get("/sandbox").text


# ------------------------------------ SB-11: an Oracle start fits one season

def test_an_oracle_start_refuses_a_season_start_over_a_year_back(box):
    with pytest.raises(sb.SandboxError, match="more than a year before the "
                       "forecast date 2026-10-17; the Oracle SIHRS fits one "
                       r"season \(production starts 2026-08-01\)"):
        sb.from_shipped("ora", "Arizona", "2026-10-17",
                        season_start="2025-08-01")


# ------------------------- SB-12: one run at a time, said without an engine

def test_the_one_run_refusals_claim_no_engine_a_groundhog_run_does_not_use(box):
    ui_state._sandbox_status["running"] = "20990101-000000_mine"
    try:
        ui_state._status.pop("flash", None)
        client.post("/run", data={"forecast_date": "2099-01-02",
                                  "locations": "Alabama",
                                  "engine": "analogue"},
                    follow_redirects=False)
        flash = ui_state._status["flash"]
        assert ("Not started: a sandbox fit is running (20990101-000000_mine); "
                "one run at a time.") in flash
        assert "holds the engine" not in flash
    finally:
        ui_state._sandbox_status["running"] = None
    ui_state._status["running"] = "console"
    try:
        assert rs._sandbox_busy_reason() == "a console run is in progress"
    finally:
        ui_state._status["running"] = None
