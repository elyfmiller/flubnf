"""Resume and re-run without re-entering parameters.

Retrospective: a season whose status is stopped or interrupted offers a
one-click Resume that POSTs /retro/run with mode=resume and the settings
its own run record holds (retro.resume_form_fields). Seasons that predate
the record get no button; the form path remains.

Console: a stopped or failed run's entry (the forecast page's latest-run
card and the run page) offers "Run again with these settings", which
re-submits the ledger row's stored spec through the same /run path as the
form. Worded honestly everywhere: console fits hold no checkpoint, so it
is a fresh run, never a resume.

Both shortcuts carry the same data-guard kind as the forms they shortcut,
and both are refused by the server-side busy cross-checks while another
run holds the engine.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

import app.core.runs as runs_mod                    # noqa: E402
from app.core import retro                          # noqa: E402
from app.core import ttlcache                       # noqa: E402
from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

SEASON = "2025-26"          # always in available_seasons (bounds fallback)
SATURDAY = "2025-12-06"     # a real Saturday: /run must not snap it


@pytest.fixture(autouse=True)
def _isolated_state():
    """Snapshot and restore every module-level store a run start mutates,
    so claims made by these tests never leak into other tests."""
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    claim_before = dict(srv._retro_claim_at)
    form_before = dict(srv._last_form)
    ttlcache.clear_all()
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)
    srv._retro_claim_at.clear(); srv._retro_claim_at.update(claim_before)
    srv._last_form.clear(); srv._last_form.update(form_before)
    ttlcache.clear_all()


# ------------------------------------------------- retro.resume_form_fields

SETTINGS = {"season": SEASON, "scope": "custom",
            "locations": ["Ohio", "Utah"], "particles": 4000,
            "replicates": 2, "width": 3, "engine": "pf"}


def test_resume_form_fields_reproduces_a_scoped_record():
    meta = {"season": "2024-25",
            "settings": {"season": "2024-25", "scope": "panel6",
                         "locations": ["Alaska", "New York"],
                         "particles": 10_000, "replicates": 3,
                         "width": 6, "engine": "pf"}}
    # national="0": this record's locations are states only, and a resume
    # must reproduce THAT scope. US national became a default-on scope on
    # 2026-08-26, so without the explicit answer a stopped 52-jurisdiction
    # replay would silently widen to 53 halfway through its season.
    assert retro.resume_form_fields(meta) == {
        "season": "2024-25", "mode": "resume", "locations": "panel6",
        "custom_locations": [], "particles": 10_000, "replicates": 3,
        "width": 6, "engine": "pf", "national": "0"}
    # the all scope passes through the same way
    meta["settings"]["scope"] = "all"
    assert retro.resume_form_fields(meta)["locations"] == "all"
    # a record whose own list names the national row resumes WITH it
    meta["settings"]["locations"] = ["Alaska", "New York", "US"]
    assert retro.resume_form_fields(meta)["national"] == "1"


def test_resume_form_fields_custom_and_unscoped_records_name_locations():
    # a custom scope resubmits its list verbatim
    f = retro.resume_form_fields({"settings": dict(SETTINGS)})
    assert f["locations"] == "custom"
    assert f["custom_locations"] == ["Ohio", "Utah"]
    assert f["mode"] == "resume"
    # a record with a location list but no scope (run_season's own fold-in)
    # resubmits the list as a custom selection: verbatim reproduction
    s = dict(SETTINGS); s.pop("scope")
    f2 = retro.resume_form_fields({"settings": s})
    assert f2["locations"] == "custom"
    assert f2["custom_locations"] == ["Ohio", "Utah"]


def test_resume_form_fields_absent_for_unrecorded_runs():
    assert retro.resume_form_fields({}) is None
    assert retro.resume_form_fields({"status": "stopped"}) is None
    assert retro.resume_form_fields({"settings": {}}) is None
    # a record with neither a scope nor a location list cannot be resubmitted
    assert retro.resume_form_fields(
        {"settings": {"season": SEASON, "particles": 4000}}) is None


# ------------------------------------------------- retro card resume button

def _season_card(**over):
    base = {"name": "2098-99", "total": 30, "done": 3, "seal": False,
            "rel": None, "settings": [("season", "2098-99")], "archives": [],
            "status": "stopped", "running": False, "paused": False,
            "active": False, "elapsed_s": None, "mean_s": None,
            "weeks_measured": 0, "eta_s": None, "finished_utc": None,
            "scored": False, "resume_fields": None}
    base.update(over)
    return base


def _render_retro(seasons):
    return srv.templates.env.get_template("retro.html").render(
        active="Retrospective", seasons=seasons, state_names=["Ohio"],
        engine_ok=True)


def test_stopped_season_card_offers_resume_with_recorded_settings():
    rf = {"season": "2098-99", "mode": "resume", "locations": "custom",
          "custom_locations": ["Ohio", "Utah"], "particles": 4000,
          "replicates": 2, "width": 3, "engine": "pf"}
    html = _render_retro([_season_card(resume_fields=rf)])
    assert '<form method="post" action="/retro/run" class="resume-run">' in html
    seg = html.split('class="resume-run"')[1].split("</form>")[0]
    assert 'name="mode" value="resume"' in seg
    assert 'name="season" value="2098-99"' in seg
    assert 'name="particles" value="4000"' in seg
    assert 'name="replicates" value="2"' in seg
    assert 'name="width" value="3"' in seg
    assert 'name="engine" value="pf"' in seg
    assert seg.count('name="custom_locations"') == 2
    # the same guard kind as the form it shortcuts, and honest copy
    assert 'data-guard="retro-run"' in seg
    assert ">Resume</button>" in seg
    assert "Resumes with the recorded settings" in html


def test_season_without_recorded_settings_gets_no_resume_button():
    html = _render_retro([_season_card(resume_fields=None)])
    assert 'class="resume-run"' not in html
    # no guarded Resume control on the card (the base template's start-over
    # modal carries its own Resume choice, which is not a card button)
    assert 'data-guard="retro-run">Resume' not in html
    # the form path remains
    assert 'action="/retro/run"' in html


def test_paused_card_keeps_its_own_resume_and_no_shortcut_form():
    html = _render_retro([_season_card(status="paused", running=False,
                                       paused=True, active=True)])
    # the live-worker resume (clears the PAUSE flag) is untouched
    assert 'action="/retro/2098-99/resume"' in html
    assert 'class="resume-run"' not in html


def test_retro_index_wires_resume_for_stopped_and_interrupted(tmp_path,
                                                              monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": dict(SETTINGS), "total_weeks": 30})
    ttlcache.clear_all()
    html = client.get("/retro").text
    assert 'class="resume-run"' in html
    assert f'name="season" value="{SEASON}"' in html
    assert 'name="particles" value="4000"' in html
    # a dead worker's record (stale heartbeat) reads interrupted and offers
    # the same one-click resume
    retro.write_meta(root, {"season": SEASON, "status": "running",
                            "heartbeat_utc": time.time() - 10_000,
                            "settings": dict(SETTINGS), "total_weeks": 30})
    ttlcache.clear_all()
    html = client.get("/retro").text
    assert "interrupted" in html
    assert 'class="resume-run"' in html
    # without recorded settings the button is absent and the form remains
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "total_weeks": 30})
    ttlcache.clear_all()
    html = client.get("/retro").text
    assert 'class="resume-run"' not in html
    assert 'action="/retro/run"' in html


# -------------------------------------------- retro resume POST, end to end

def test_retro_resume_post_launches_with_the_recorded_settings(tmp_path,
                                                               monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": dict(SETTINGS), "total_weeks": 30})
    wk = root / "weeks" / "2025-11-01"
    wk.mkdir(parents=True)
    (wk / "samples.json").write_text("{}")
    launched = []
    monkeypatch.setattr(srv, "_retro_bg",
                        lambda *a: launched.append(a))
    fields = retro.resume_form_fields(retro.read_meta(root))
    r = client.post("/retro/run", data=fields, follow_redirects=False)
    assert r.status_code == 303
    # the worker receives exactly the recorded settings, and the record's
    # scope and engine ride along for the resumed run's own record
    # the recorded list was states only, so the resume runs states only:
    # national="0" rides in the resume fields for exactly this reason
    assert launched == [(SEASON, ["Ohio", "Utah"], 3, 2, 4000,
                         {"scope": "custom", "engine": "pf",
                          "national": False})]
    # mode=resume: the completed week was neither archived nor discarded
    assert (wk / "samples.json").is_file()
    assert srv._retro_status[SEASON] == "running"


def test_retro_resume_post_refused_over_a_console_run(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": dict(SETTINGS), "total_weeks": 30})
    launched = []
    monkeypatch.setattr(srv, "_retro_bg", lambda *a: launched.append(a))
    srv._retro_status.clear()
    srv._status.update({"running": "all:20990101T000000-abc",
                        "run_label": "2099-01-02 · 3 state(s) + US"})
    fields = retro.resume_form_fields(retro.read_meta(root))
    r = client.post("/retro/run", data=fields, follow_redirects=False)
    assert r.status_code == 303
    assert launched == []
    assert SEASON not in srv._retro_status
    assert "console run holds the engine" in srv._status.get("flash", "")


# ----------------------------------------------------- console run again

def _ledger_row(tmp_path, monkeypatch, spec, status="stopped"):
    """A tmp ledger holding one closed run with `spec`; returns run_id."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})
    led.close_run(rid, status, {})
    return rid


def test_rerun_reposts_the_stored_spec_verbatim(tmp_path, monkeypatch):
    spec = runs_mod.RunSpec(engine="all", forecast_date=SATURDAY,
                            locations=["Ohio", "US"], weeks_to_drop=1,
                            replicates=2)
    rid = _ledger_row(tmp_path, monkeypatch, spec)
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda s: started.append(s))
    srv._status.update({"running": None})
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert len(started) == 1
    # verbatim: the run that starts carries exactly the recorded spec
    assert started[0].to_json() == spec.to_json()


def test_rerun_refused_when_settings_were_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)   # empty ledger
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda s: started.append(s))
    r = client.post("/runs/20980101T000000-abcdef/rerun",
                    follow_redirects=False)
    assert r.status_code == 303
    assert started == []
    assert srv._status.get("running") is None
    assert "were not recorded" in srv._status.get("flash", "")


def test_rerun_refuses_a_spec_the_form_path_cannot_reproduce(tmp_path,
                                                             monkeypatch):
    # a row with a non-default jitter must refuse rather than silently run
    # with the console defaults. (Particles, once the example here, became
    # reproducible when the research run control gained its particles
    # field; test_research_run covers that path re-running verbatim.)
    spec = runs_mod.RunSpec(engine="pf", forecast_date=SATURDAY,
                            locations=["Ohio", "US"], jitter=0.55)
    rid = _ledger_row(tmp_path, monkeypatch, spec)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda s: started.append(s))
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert started == []
    assert srv._status.get("running") is None
    flash = srv._status.get("flash", "")
    assert "cannot be reproduced" in flash and "jitter" in flash


def test_rerun_refused_while_a_retrospective_replays(tmp_path, monkeypatch):
    spec = runs_mod.RunSpec(engine="all", forecast_date=SATURDAY,
                            locations=["Ohio", "US"])
    rid = _ledger_row(tmp_path, monkeypatch, spec)
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda s: started.append(s))
    srv._status.update({"running": None})
    srv._retro_status["2097-98"] = "running"
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert started == []
    assert srv._status.get("running") is None
    assert "retrospective replay holds the engine" in srv._status.get(
        "flash", "")


def test_rerun_refused_while_a_console_run_is_fitting(tmp_path, monkeypatch):
    spec = runs_mod.RunSpec(engine="all", forecast_date=SATURDAY,
                            locations=["Ohio", "US"])
    rid = _ledger_row(tmp_path, monkeypatch, spec, status="error")
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(srv, "_run_all", lambda s: started.append(s))
    srv._retro_status.clear()
    srv._status.update({"running": "all:20990101T000000-abc"})
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303
    assert started == []
    assert srv._status["running"] == "all:20990101T000000-abc"  # untouched


# ------------------------------------------------ console card and run page

def _render_forecast(row):
    return srv.templates.env.get_template("forecast.html").render(
        active="Forecast", engines=srv.ENGINES, status={"running": None},
        ledger=[row], all_locs=["Ohio"], locations_error="",
        form={"forecast_date": SATURDAY, "locations": ["all"],
              "engine": "all", "weeks_to_drop": 0, "weeks_to_nowcast": 0,
              "replicates": 3, "members": 2},
        elapsed0=None, series_json="{}", fanq_json="{}",
        model_names_json="{}", run_obs_json="{}", fc_date="")


def test_a_completed_run_with_fit_failures_is_partial_not_failed():
    """MEASURED 2026-09-01, the first real Windows full grid: 159 fits, 4
    failures, 2 submissions, report built -- and the run badge said
    "failed". A run whose pipeline completed and whose record exists is
    "partial" when some fits failed; the chips carry the count. The pill
    warns rather than condemns, and the rerun offer stays. "failed" and
    "error" remain reserved for runs that died."""
    server = (Path(__file__).resolve().parents[2]
              / "app" / "ui" / "server.py").read_text(encoding="utf-8")
    assert '"partial" if fails else "ok"' in server, (
        "close_run went back to branding a completed run failed for "
        "per-cell fit failures")
    assert '"failed" if fails' not in server
    row = {"run_id": "20980101T000000-abcdef", "label": "L",
           "status": "partial", "chips": "PF 159 fits", "has_report": True,
           "spec": "{}", "elapsed_s": None}
    html = _render_forecast(row)
    assert "pill warn" in html, "the partial pill should warn, not condemn"
    assert f'action="/runs/{row["run_id"]}/rerun"' in html, (
        "a partial run must still offer the rerun")


def test_latest_run_card_offers_rerun_for_stopped_and_failed_only():
    row = {"run_id": "20980101T000000-abcdef", "label": "L",
           "status": "stopped", "chips": "", "has_report": False,
           "spec": "{}", "elapsed_s": None}
    html = _render_forecast(row)
    assert f'action="/runs/{row["run_id"]}/rerun"' in html
    assert 'data-guard="console-run">Run again with these settings' in html
    # the honest wording: a re-run, never a resume
    assert "hold no checkpoint" in html
    assert "does not resume" in html
    for ok_status in ("ok", "running"):
        html = _render_forecast(dict(row, status=ok_status))
        assert "/rerun" not in html
    # a row without a recorded spec gets no shortcut
    html = _render_forecast(dict(row, spec=""))
    assert "/rerun" not in html


def test_run_page_offers_rerun_and_corrects_interrupted(tmp_path,
                                                        monkeypatch):
    spec = runs_mod.RunSpec(engine="all", forecast_date=SATURDAY,
                            locations=["Ohio", "US"])
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = runs_mod.Ledger()
    rid = led.open_run(spec, Path("pending"), {})   # stays 'running' in the DB
    srv._status.update({"running": None})
    html = client.get(f"/runs/{rid}").text
    # the ledger says running, no worker is alive: the page says interrupted
    assert "interrupted" in html
    assert f'action="/runs/{rid}/rerun"' in html
    assert 'data-guard="console-run">Run again with these settings' in html
    assert "hold no checkpoint" in html
    # a completed run offers nothing
    led.close_run(rid, "ok", {})
    html = client.get(f"/runs/{rid}").text
    assert "/rerun" not in html
