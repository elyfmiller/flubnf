"""Runs when the particle-filter engine is missing (the 2026-10-25 bug
hunt, G05).

  * Oracle SIHRS only and the research run need the engine: refused up
    front, where they ran the Groundhog alone and ended "ok" with no file
    (FC-03, MO-05, WI-09); the model pages' buttons are off, saying why;
  * Both runs the Groundhog alone without it, as a machine without the
    engine always has: the form says so before the run, the Oracle-only
    choice is off, and the Running card shows a Groundhog-only run
    (FC-04);
  * the ledger's chip tells a Groundhog-only run from a missing engine
    (FC-17);
  * a season replay whose every week failed ends in error, not "complete"
    with no weeks (RE-02; the refusal itself is in test_retro_archive).
The suite's machine has no engine; `pf_engine_ready` gives it one.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro                                   # noqa: E402
from app.ui import pipeline as ui_pipeline                   # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402

from test_data_source import (W1, W2, W3, _capture, _hub,     # noqa: E402,F401
                              _isolated, client)

NO_ENGINE = ("Not run: the Oracle SIHRS needs the particle-filter engine, "
             "which is not installed on this machine. Choose Groundhog only.")


@pytest.fixture
def started(tmp_path, monkeypatch):
    out = _capture(monkeypatch, tmp_path)
    _hub(tmp_path / "hub", [W3], [W3], monkeypatch)
    return out


def _post(data, referer="/forecast"):
    ui_state._status.update({"running": None, "flash": None})
    return client.post("/run", data={"forecast_date": W3, "locations": ["Ohio"],
                                     **data},
                       headers={"referer": f"http://testserver{referer}"},
                       follow_redirects=False)


# --------------------------------------------------------------- the refusals

def test_oracle_sihrs_only_is_refused_without_the_engine(started, monkeypatch):
    r = _post({"engine": "pf"}, referer="/models")
    assert r.status_code == 303 and r.headers["location"] == "/models"
    assert started == [] and ui_state._status["flash"] == NO_ENGINE
    # a half-installed engine, in its own words
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "broken")
    _post({"engine": "pf"})
    assert started == []
    assert ui_state._status["flash"] == (
        "Not run: the Oracle SIHRS needs the particle-filter engine, whose "
        "install is incomplete. Choose Groundhog only.")


def test_a_research_run_is_refused_without_the_engine(started):
    _post({"engine": "all", "members": "3"}, referer="/model/pf2s")
    assert started == []
    assert ui_state._status["flash"] == (
        "Not run: the research run needs the particle-filter engine, which "
        "is not installed on this machine.")


def test_with_the_engine_they_run(started, pf_engine_ready):
    _post({"engine": "pf"})
    _post({"engine": "all", "members": "3"})
    assert [s.engine for s in started] == ["pf", "all"]


# ------------------------------------------- Both runs the Groundhog, and says so

def test_both_says_before_the_run_that_the_groundhog_runs_alone(started):
    page = " ".join(client.get("/forecast").text.split())
    assert ("Groundhog only: the particle-filter engine is not installed "
            "on this machine") in page
    assert '<option value="pf" disabled>Oracle SIHRS only</option>' in page
    assert 'id="fc-engine"' not in page          # no "Engine: Particle filter"
    # Both still runs (the Groundhog's file), its progress with no fits
    _post({"engine": "all"})
    assert [s.engine for s in started] == ["all"]
    assert ui_state._status["expected_total"] is None


def test_a_half_installed_engine_is_named_not_promised_as_groundhog_only(
        started, monkeypatch):
    """Both on a broken install fails at run time (the pipeline refuses to
    ship the Groundhog alone and hide the fault): the form names the
    install, never "Groundhog only"."""
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "broken")
    page = " ".join(client.get("/forecast").text.split())
    assert "Oracle SIHRS engine install incomplete" in page
    assert "Groundhog only: the particle-filter engine" not in page
    assert '<option value="pf" disabled>Oracle SIHRS only</option>' in page
    assert 'id="fc-engine"' not in page


def test_with_the_engine_the_form_is_as_before(started, pf_engine_ready):
    page = " ".join(client.get("/forecast").text.split())
    assert "Groundhog only: the particle-filter engine" not in page
    assert '<option value="pf" >Oracle SIHRS only</option>' in page
    assert 'id="fc-engine"' in page
    _post({"engine": "all"})
    assert ui_state._status["expected_total"] == 3   # 1 location x 3


def test_the_running_card_shows_a_groundhog_only_run(tmp_path, monkeypatch):
    import app.core.runs as runs_mod
    from app.core.engines import analogue as an_engine
    from app.core.runs import RunSpec
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(ui_pipeline, "_sleep_guard", lambda: None)
    seen = []
    monkeypatch.setattr(an_engine, "run", lambda spec: seen.append(
        dict(ui_state._status["settings"])) or {})
    ui_state._status.update({"running": "starting", "workroot": None})
    ui_pipeline._run_all(RunSpec(engine="all", forecast_date="2098-01-03",
                                 locations=["Ohio"]))
    (card,) = seen
    assert card["engine"] == "Groundhog only (no PF engine on this machine)"
    assert "particles" not in card and "replicates" not in card


# ------------------------------------------------------------ the model pages

def test_the_model_pages_say_why_the_oracle_cannot_run():
    ui_state._status["running"] = None
    html = " ".join(client.get("/model/pf").text.split())
    assert ("The Oracle SIHRS needs the particle-filter engine, which is not "
            "installed on this machine.") in html
    quick = html.split('action="/run"')[1].split("</form>")[0]
    assert 'disabled aria-describedby="md-busy">Run Oracle SIHRS only' in quick
    html = " ".join(client.get("/model/analogue").text.split())
    assert "particle-filter engine" not in html
    quick = html.split('action="/run"')[1].split("</form>")[0]
    assert "disabled" not in quick.split("<button", 1)[1].split(">")[0]
    html = " ".join(client.get("/model/pf2s").text.split())
    card = html.split('id="research-run"')[1]
    assert ("A research run needs the particle-filter engine, which is not "
            "installed on this machine.") in card
    assert ('data-guard="console-run" disabled aria-describedby="rr-busy">'
            'Start research run') in card


def test_with_the_engine_the_model_pages_run(pf_engine_ready):
    ui_state._status["running"] = None
    for page in ("/model/pf", "/model/pf2s"):
        html = " ".join(client.get(page).text.split())
        assert "needs the particle-filter engine" not in html, page
        assert 'aria-describedby="md-busy"' not in html
        assert 'aria-describedby="rr-busy"' not in html


# ------------------------------------------------------------------ the ledger

def test_the_ledger_chip_says_why_the_filter_did_not_run():
    def chips(outcome):
        return [i["text"] for i in ui_shared._outcome_items(
            json.dumps(outcome))]
    assert "Groundhog only" in chips({"pf_skipped": "analogue-only run"})
    assert "PF skipped" not in " ".join(
        chips({"pf_skipped": "analogue-only run"}))
    assert "PF skipped" in chips(
        {"pf_skipped": "engine venv not installed (Tier A)"})


# --------------------------------------------------------------- the replays

def test_a_season_whose_every_week_failed_ends_in_error_naming_the_first(
        tmp_path, monkeypatch):
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def boom(*a, **k):
        raise RuntimeError("the fork does not provide fit_type = pf")
    monkeypatch.setattr(retro, "run_week", boom)
    root = tmp_path / "2024-25"
    assert retro.run_season(root, "2024-25", ["Ohio"], width=1,
                            engine="analogue") == []
    meta = retro.read_meta(root)
    assert meta["status"] == f"error: {W1}: the fork does not provide fit_type = pf"
    assert meta["weeks_completed"] == 0
    assert (root / "failures.log").read_text(encoding="utf-8").count("\n") == 2
