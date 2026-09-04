"""The Forecast form's two modes and its advanced group (2026-09-04).

Real-time and Vintage are two ways into ONE form: the same controls post
to the same route and build the same RunSpec, so the two cannot disagree
about what runs. The advanced group holds Season start (blank derives
August 1 of the forecast's season, RunSpec's rule), Weeks to drop and
Replicates. A typed season start is recorded verbatim in the spec, shown
in the run settings, and reproduced by a rerun; an impossible one is
refused out loud and the default used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

from app.core.runs import RunSpec, default_season_start, spec_settings  # noqa: E402
from app.ui import server as srv                         # noqa: E402

client = TestClient(srv.app)


@pytest.fixture(autouse=True)
def _release_engine():
    yield
    srv._status["running"] = None


def test_default_season_start_is_august_first_of_the_season():
    assert default_season_start("2098-01-04") == "2097-08-01"
    assert default_season_start("2098-08-01") == "2098-08-01"
    assert default_season_start("2098-07-31") == "2097-08-01"
    assert default_season_start("") == ""
    assert RunSpec(engine="all", forecast_date="2098-01-04").season_start == "2097-08-01"
    typed = RunSpec(engine="all", forecast_date="2098-01-04",
                    season_start="2097-10-01")
    assert typed.season_start == "2097-10-01"            # kept verbatim


def test_forecast_form_offers_two_modes_and_the_advanced_group():
    html = client.get("/forecast").text
    for needle in ('data-mode="realtime"', 'data-mode="vintage"',
                   'name="season_start"', '<details class="adv">',
                   'name="weeks_to_drop"', 'name="replicates"',
                   'name="engine"', 'id="season-line"'):
        assert needle in html, needle
    # engine stays in the main group; the two numeric fields moved under
    # Advanced, season start first
    adv = html.index('<details class="adv">')
    assert html.index('name="engine"') < adv
    assert adv < html.index('name="season_start"') < html.index(
        'name="weeks_to_drop"') < html.index('name="replicates"')
    assert "The anchor week is kept by" not in html          # the old paragraph


def _capture_run(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda spec: started.append(spec))
    return started


def test_run_records_a_typed_season_start_and_derives_a_blank_one(
        tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    r = client.post("/run", data={"forecast_date": "2098-01-04",
                                  "locations": ["Ohio"],
                                  "season_start": "2097-10-01"},
                    follow_redirects=False)
    assert r.status_code == 303
    srv._status["running"] = None
    client.post("/run", data={"forecast_date": "2098-01-04",
                              "locations": ["Ohio"], "season_start": ""},
                follow_redirects=False)
    assert started[0].season_start == "2097-10-01"
    assert started[1].season_start == "2097-08-01"
    assert srv._last_form["season_start"] == ""             # the form keeps blank


def test_run_refuses_a_season_start_that_is_not_before_the_week(
        tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    for bad in ("2098-02-01", "2096-01-01", "not-a-date"):
        srv._status["running"] = None
        client.post("/run", data={"forecast_date": "2098-01-04",
                                  "locations": ["Ohio"], "season_start": bad},
                    follow_redirects=False)
    assert [s.season_start for s in started] == ["2097-08-01"] * 3
    page = client.get("/forecast").text
    assert "using 2097-08-01" in page                      # the refusal is said


def test_run_settings_name_the_season_start():
    pairs = spec_settings(RunSpec(engine="all", forecast_date="2098-01-04",
                                  season_start="2097-10-01"))
    labels = [k for k, _ in pairs]
    assert labels[:2] == ["forecast date", "season start"]
    assert dict(pairs)["season start"] == "2097-10-01"
