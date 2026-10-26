"""The remembered form (state._last_form) and the Run row's "Same as last
run" (the 2026-10-25 bug hunt, G03).

  * a run pressed while a run holds the console is refused in words, and
    the form keeps what that run was given (FC-02, WI-01); the model
    pages' quick-run button is off meanwhile (MO-17);
  * a refused date keeps the user's other choices, the date moved to the
    week offered (FC-05);
  * the pick is kept as the Forecast checklist holds it: a model page's
    "Arizona, Ohio" ticks both (FC-07, MO-04), a re-run of the 53 by name
    is "all 53" (FC-09);
  * the Data issues choices survive a run that did not post the box
    (FC-12); a state left out there still counts as picked (FC-10);
  * a model page shows the remembered form after a restart (WI-12).
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import runs as runs_mod                        # noqa: E402
from app.ui import forecast_aids as FA                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from app.ui.routes.forecast import US_CHOICE                 # noqa: E402

from test_data_source import (W1, W2, W3, _capture, _hub,     # noqa: E402,F401
                              _isolated, client)

BW = "knob.groundhog.bandwidth"


def _post(data, referer="/forecast"):
    ui_state._status["running"] = None
    ui_state._status["flash"] = None
    return client.post("/run", data=data, follow_redirects=False,
                       headers={"referer": f"http://testserver{referer}"})


@pytest.fixture
def state(tmp_path, monkeypatch):
    """A hub whose archive skipped W2 (a holiday week), the runs captured,
    the remembered form written into tmp_path."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    started = _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W1, W3], [W1, W3], monkeypatch)
    ui_state._last_form.clear()
    return started


# ------------------------------------------------------------ a busy console

def test_a_run_pressed_during_a_run_is_refused_and_the_form_keeps_that_run(
        state):
    running = {"forecast_date": W3, "locations": ["all", US_CHOICE],
               "engine": "analogue", "knobs": {}}
    ui_state._last_form.update(running)
    ui_state._status["running"] = "20981018T120000-abcdef"
    ui_state._status["flash"] = None
    r = client.post("/run", data={"forecast_date": W1, "mode": "vintage",
                                  "locations": ["Ohio"], "engine": "analogue",
                                  BW: "4"},
                    headers={"referer": "http://testserver/forecast"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/forecast"
    assert state == []
    assert ui_state._status["flash"] == "Not run: a run is already in progress."
    assert ui_state._status.get("flash_kind") == "warn"
    assert ui_state._last_form == running


def test_the_quick_run_button_is_off_while_a_run_holds_the_engine():
    ui_state._status["running"] = "20981018T120000-abcdef"
    html = client.get("/model/analogue").text
    button = html.split('data-guard="console-run"')[1].split(">")[0]
    assert 'disabled aria-describedby="md-busy"' in button
    assert 'id="md-busy"' in html
    ui_state._status["running"] = None
    html = client.get("/model/analogue").text
    assert "disabled" not in html.split('data-guard="console-run"')[1].split(">")[0]


# ------------------------------------------------------------- a refused date

def test_a_refused_date_keeps_the_other_choices(state):
    r = _post({"forecast_date": W2, "mode": "vintage",
               "locations": [US_CHOICE], "engine": "analogue", BW: "5"})
    assert r.status_code == 303 and state == []
    assert f"Nearest earlier: {W1}" in ui_state._status["flash"]
    form = ui_state._last_form
    assert form["forecast_date"] == W1                 # the week offered
    assert form["locations"] == [US_CHOICE]
    assert form["engine"] == "analogue"
    assert form["knobs"]["groundhog.bandwidth"] == "5"
    page = " ".join(client.get("/forecast").text.split())
    assert '<option value="analogue" selected>' in page
    assert f'id="ck-us" name="locations" value="{US_CHOICE}" checked>' in page
    # a blank date keeps them too, and the last date
    _post({"forecast_date": "", "locations": ["Ohio"], "engine": "all"})
    assert ui_state._status["flash"] == "Not run: give a forecast date."
    assert form["forecast_date"] == W1 and form["locations"] == ["Ohio"]
    assert form["engine"] == "all"


# ----------------------------------------------------------------- the pick

def test_a_model_pages_typed_pick_ticks_the_forecast_checklist(state):
    _post({"forecast_date": W3, "locations": ["arizona, Ohio"],
           "engine": "analogue"}, referer="/model/analogue")
    assert ui_state._last_form["locations"] == ["Arizona", "Ohio"]
    # the kept file too, so the boxes tick after a restart
    assert FA.load_last_form()["locations"] == ["Arizona", "Ohio"]
    page = " ".join(client.get("/forecast").text.split())
    for name in ("Arizona", "Ohio"):
        assert f'name="locations" value="{name}" checked>' in page, name
    assert 'id="ck-all" value="all" name="locations" checked' not in page
    # and the model page shows it back as typed names
    html = client.get("/model/analogue").text
    assert 'id="mf-locs" name="locations" value="Arizona, Ohio"' in html


def test_a_rerun_of_the_53_by_name_is_all_53_on_the_form(state):
    from flubnf.settings import load_locations
    _l = load_locations()
    names = list(_l.location_name[(_l.location.str.len() == 2)
                                  & (_l.abbreviation != "US")])
    assert len(names) == 52
    _post({"forecast_date": W3, "locations": names + ["US"],
           "engine": "analogue"})
    assert len(state) == 1 and len(state[0].locations) == 53
    assert ui_state._last_form["locations"] == ["all", US_CHOICE]
    page = " ".join(client.get("/forecast").text.split())
    assert 'id="ck-all" value="all" name="locations" checked' in page
    # the model pages' Locations box reads it as "all", as typed there
    for page, box in (("/model/analogue", "mf-locs"), ("/model/pf2s", "rr-locs")):
        html = " ".join(client.get(page).text.split())
        assert f'id="{box}" name="locations" value="all"' in html, page
    # the 52 without US stay a pick of their own (States only)
    _post({"forecast_date": W3, "locations": names, "engine": "analogue"})
    assert ui_state._last_form["locations"] == names


# ---------------------------------------------------------- the Data issues box

def test_the_data_issues_choices_survive_a_run_that_did_not_post_the_box(
        state):
    kept = {W3: {"02": "omit"}}
    ui_state._last_form["data_choices"] = dict(kept)
    # a vintage run (the box's fieldset is off) and a model page's run
    _post({"forecast_date": W1, "mode": "vintage", "locations": ["Ohio"],
           "engine": "analogue"})
    _post({"forecast_date": W3, "locations": ["Ohio"], "engine": "analogue"},
          referer="/model/analogue")
    assert ui_state._last_form["data_choices"] == kept
    # a hand-made post carrying the box for an earlier week: still theirs
    _post({"forecast_date": W1, "mode": "vintage", "locations": ["Ohio"],
           "engine": "analogue", "gap._sha": "abc", "gap.02": "carry"})
    assert ui_state._last_form["data_choices"] == kept
    # the box posted for the newest week: its choices are that week's
    _post({"forecast_date": W3, "locations": ["Ohio"], "engine": "analogue",
           "gap._sha": "abc", "gap.02": "carry"})
    assert ui_state._last_form["data_choices"] == {W3: {"02": "carry"}}


def test_a_state_left_out_in_data_issues_still_counts_as_picked():
    from flubnf.settings import load_locations
    _l = load_locations()
    names = list(_l.location_name[(_l.location.str.len() == 2)
                                  & (_l.abbreviation != "US")])
    spec = {"engine": "analogue", "forecast_date": W3,
            "locations": [n for n in names if n != "Alaska"] + ["US"],
            "extra": {"mode": "realtime", "data_choices": {
                "week": W3, "source_sha256": "abc",
                "states": {"Alaska": {"choice": "omit"},
                           "Ohio": {"choice": "carry"}}}}}
    row = {"run_id": "20981018T120000-abcdef", "status": "ok",
           "spec": json.dumps(spec), "outcome": "{}"}
    assert FA.last_run_values([row])["locations"] == ["all"]


# ------------------------------------------------------------- after a restart

def test_a_model_page_after_a_restart_shows_the_remembered_form(
        tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    FA.save_last_form({"forecast_date": W3, "locations": ["Ohio", "Utah"],
                       "engine": "analogue"})
    old = time.time() - 3600
    os.utime(tmp_path / FA.LAST_FORM_NAME, (old, old))
    monkeypatch.setattr(FA, "_STARTED", time.time())
    monkeypatch.setitem(FA._restored, "done", False)
    ui_state._last_form.clear()
    html = client.get("/model/analogue").text
    assert 'id="mf-locs" name="locations" value="Ohio, Utah"' in html
