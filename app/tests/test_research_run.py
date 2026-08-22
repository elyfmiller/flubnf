"""Research runs, separated from the flagship flows.

The two-strain engine failed its full-grid ensemble gate, so its run
control lives ONLY on the pf2s model view, clearly badged; it posts the
members=3 selection the /run path already accepts (now with a particles
knob); everything it starts is tagged research on every surface the run
appears on; and the flagship Forecast page keeps no third-member option.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core.runs import Ledger, RunSpec, is_research  # noqa: E402
from app.ui import server as srv                     # noqa: E402

client = TestClient(srv.app)


@pytest.fixture(autouse=True)
def _isolated_status():
    status_before = dict(srv._status)
    form_before = dict(srv._last_form)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._last_form.clear(); srv._last_form.update(form_before)
    srv._invalidate_scans()


# ------------------------------------------------------------- the control

def test_pf2s_view_carries_the_badged_research_form():
    html = client.get("/model/pf2s").text
    assert 'id="research-run"' in html
    joined = " ".join(html.split())
    assert "Research run" in joined
    assert "research · not the shipped forecast" in joined
    # its own form: date, locations, particles, posting the accepted path
    assert 'action="/run"' in html
    assert 'name="forecast_date"' in html
    assert 'id="rr-locs"' in html and 'name="locations"' in html
    assert 'name="particles"' in html
    assert 'name="members" value="3"' in html
    # guarded by the same busy rules as every control that books the engine
    form = html.split('id="research-run"', 1)[1]
    assert 'data-guard="console-run"' in form
    # honest copy: the shipped forecast is not changed by this
    assert "unchanged" in joined


def test_research_form_appears_only_on_the_pf2s_view():
    for page in ("/models", "/model/analogue", "/model/ensemble",
                 "/forecast", "/", "/runs", "/methods"):
        assert 'id="research-run"' not in client.get(page).text, page


def test_flagship_forecast_page_offers_no_third_member():
    html = client.get("/forecast").text
    assert 'name="members"' not in html
    assert "Research run" not in html


# ------------------------------------------------------------ the run path

def _capture_run(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda spec: started.append(spec))
    return started


def test_run_accepts_the_research_selection(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    r = client.post("/run", data={"forecast_date": "2098-01-04",
                                  "locations": ["Ohio"], "members": "3",
                                  "particles": "20000", "engine": "all"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert len(started) == 1
    spec = started[0]
    assert spec.extra == {"members": 3}
    assert spec.particles == 20_000
    assert is_research(spec)


def test_particles_defaults_and_clamps(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    client.post("/run", data={"forecast_date": "2098-01-04",
                              "locations": ["Ohio"]},
                follow_redirects=False)
    srv._status["running"] = None                    # release for the next
    client.post("/run", data={"forecast_date": "2098-01-04",
                              "locations": ["Ohio"],
                              "particles": "999999"},
                follow_redirects=False)
    assert started[0].particles == 10_000            # flagship default
    assert not is_research(started[0])               # and NOT research
    assert started[1].particles == 100_000           # clamped


# ----------------------------------------------------------------- the tag

def test_is_research_reads_any_spec_shape():
    spec = RunSpec(engine="all", forecast_date="2098-01-04",
                   extra={"members": 3})
    assert is_research(spec)
    assert is_research(spec.to_json())
    assert is_research({"extra": {"variant": "2strain"}})
    assert not is_research(RunSpec(engine="all", forecast_date="2098-01-04"))
    assert not is_research("not json")
    assert not is_research(None)


def test_label_carries_the_tag_and_badge_pages_can_drop_it():
    spec = RunSpec(engine="all", forecast_date="2098-01-04",
                   extra={"members": 3}).to_json()
    tagged = srv._run_label("20980104T120000-abcdef", spec)
    assert tagged.endswith("· research")
    plain = srv._run_label("20980104T120000-abcdef", spec, tag=False)
    assert "research" not in plain
    normal = RunSpec(engine="all", forecast_date="2098-01-04").to_json()
    assert "research" not in srv._run_label("20980104T120000-abcdef", normal)


def test_ledger_and_run_page_wear_the_research_badge(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rrid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-04",
                                extra={"members": 3}), Path("pending"), {})
    led.close_run(rrid, "ok", {})
    nrid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-10"),
                        Path("pending"), {})
    led.close_run(nrid, "ok", {})
    srv._invalidate_scans()
    html = client.get("/runs").text
    rrow = html.split(f'href="/runs/{rrid}"', 1)[1].split("</tr>", 1)[0]
    nrow = html.split(f'href="/runs/{nrid}"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="pill">research</span>' in rrow
    assert "research" not in nrow
    # the badge follows the run onto its own page
    rpage = client.get(f"/runs/{rrid}").text
    assert '<span class="pill">research</span>' in rpage
    assert "research" not in client.get(f"/runs/{nrid}").text.split(
        "<h1>", 1)[1].split("</h1>", 1)[0]


def test_rerun_reproduces_a_research_runs_particles(tmp_path, monkeypatch):
    """The re-run path reposts the recorded spec verbatim, particles
    included, so a research run's knob survives the shortcut."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-04",
                               locations=["Ohio", "US"], particles=20_000,
                               extra={"members": 3}), Path("pending"), {})
    led.close_run(rid, "stopped", {})
    started = _capture_run(monkeypatch, tmp_path)
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert len(started) == 1
    assert started[0].particles == 20_000
    assert started[0].extra == {"members": 3}
