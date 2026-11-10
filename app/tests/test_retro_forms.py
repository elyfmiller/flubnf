"""Retrospective forms and navigation (bug hunt 2026-10-25, G23).

  * The season page's Show in folder says why nothing opened: the reveal
    answers a script with its outcome, and the page shows a refusal under
    its buttons (a form post still goes back with the warning).
  * The Run form shows its choices again after a refusal or a run, and
    the Model settings panel opens on its own refusal.
  * A dataset replay's page leads back to that dataset's replays.
  * A replay that stopped early says how far it got, and its empty chart
    no longer promises forecasts "yet".
"""
import json
import subprocess
from datetime import date
from pathlib import Path

from app.core import custom_retro as CX
from app.ui import state as ui_state
from test_datasets_ui import client, isolated, stored        # noqa: F401
from test_dataset_engines import grouped_bytes                # noqa: E402
from test_retro_archive import OTHER, _roots                  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"
JSON = {"Accept": "application/json"}


# ----------------------------- RE-12 (WI-05): Show in folder says why not

def test_show_in_folder_answers_a_script_with_its_outcome(tmp_path,
                                                          monkeypatch):
    import app.core.runs as runs_mod
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    f = tmp_path / "retro" / "2098-99" / "r.html"
    f.parent.mkdir(parents=True)
    f.write_text("x")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: None)
    assert client.post("/output/reveal", data={"path": str(f)},
                       headers=JSON).json() == {"ok": True, "message": "",
                                                "detail": ""}
    assert client.post("/output/reveal", data={"path": "/etc/hosts"},
                       headers=JSON).json() == {
        "ok": False,
        "message": "Nothing opened: the file is not in app state any more.",
        "detail": "It may have been deleted or moved; Storage lists what is "
                  "on disk."}

    def no_file_manager(*a, **kw):
        raise OSError("xdg-open not found")
    monkeypatch.setattr(subprocess, "Popen", no_file_manager)
    got = client.post("/output/reveal", data={"path": str(f)},
                      headers=JSON).json()
    assert got["ok"] is False
    assert got["message"] == \
        "Nothing opened: no file manager could be started."
    assert got["detail"].endswith(f"The file is at {f.resolve()}.")
    # a form's post still goes back to its page with the warning
    r = client.post("/output/reveal", data={"path": str(f)},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "no file manager" in ui_state._status["flash"]
    # the season page asks for the outcome and says a refusal: its own
    # sentence as the alert's title, the detail under it
    js = (TEMPLATES / "retro_season.html").read_text(encoding="utf-8")
    js = js.split("fetch('/output/reveal'", 1)[1].split(".then(function()"
                                                        "{lock(false", 1)[0]
    assert "Accept:'application/json'" in js
    assert "e.title=d.message" in js and "fail(err.message,err.title)" in js


# ------------------------------- RE-13: the form keeps what was chosen

def _run_form() -> str:
    return client.get("/retro").text.split(
        'action="/retro/run"', 1)[1].split("</form>", 1)[0]


def test_the_run_form_shows_its_choices_again_after_a_refusal(tmp_path,
                                                              monkeypatch):
    _roots(tmp_path, monkeypatch)
    fields = {"season": OTHER, "locations": "custom", "national": "0",
              "engine": "analogue", "mode": "archive",
              "knob.groundhog.zero_anchor": "blend"}
    client.post("/retro/run", data=fields, follow_redirects=False)
    assert "no locations checked" in ui_state._status["flash"]
    form = _run_form()
    assert f"<option selected>{OTHER}</option>" in form
    assert '<option value="custom" selected>custom selection' in form
    assert 'id="retro-custom" style="display:none"' not in form
    assert '<option value="0" selected>states only' in form
    assert '<option value="analogue" selected>Groundhog only' in form
    assert '<option value="blend" selected>blend' in form
    # a refusal over the model settings opens their panel, once
    client.post("/retro/run", data={**fields, "locations": "panel6",
                                    "knob.groundhog.zero_anchor": "often"},
                follow_redirects=False)
    assert "model settings" in ui_state._status["flash"]
    assert 'open data-refused id="model-settings"' in _run_form()
    assert 'open data-refused' not in _run_form()


def test_a_refusal_keeps_the_particles_replicates_and_same_day_week(
        tmp_path, monkeypatch):
    """RE-13 for the older field names: the panel reads particles,
    replicates and drop_same_day from the remembered form, so the route
    must keep them, or the next Run replays at the defaults."""
    import re
    _roots(tmp_path, monkeypatch)
    client.post("/retro/run", data={
        "season": OTHER, "locations": "custom", "engine": "pf",
        "particles": "2000", "replicates": "5", "drop_same_day": "1",
        "knob.groundhog.zero_anchor": "blend"}, follow_redirects=False)
    # refused either way: no locations checked, or, on a machine without
    # the engine (CI), the Oracle preset's engine check comes first
    assert "Not started" in ui_state._status["flash"]
    form = _run_form()

    def value(name):
        m = re.search(r'<(?:input|select)[^>]*name="' + re.escape(name)
                      + r'"[^>]*>', form)
        assert m, name
        tag = m.group(0)
        if tag.startswith("<select"):
            sel = form[m.end():].split("</select>", 1)[0]
            return re.search(r'<option value="([^"]*)" selected', sel)[1]
        return re.search(r'value="([^"]*)"', tag)[1]
    # the panel posts these three under their older names (knobs.FIELD_OF)
    assert value("particles") == "2000"
    assert value("replicates") == "5"
    assert value("drop_same_day") == "1"


# ------------------------------------------ RE-24 and RE-25: a replay page

def test_a_stopped_replay_leads_back_and_says_how_far_it_got():
    ds = stored(grouped_bytes(groups=("Pediatric", "Adult"),
                              end=date(2023, 12, 2)), "Kids")
    out = CX.replay_dir(ds, CX.new_stamp(ds))
    CX.run(ds, ["2023-11-25", "2023-12-02"], ds.groups, out_dir=out)
    meta = json.loads((out / CX.META).read_text(encoding="utf-8"))
    meta.update(status="stopped", weeks_completed=1, total_weeks=2)
    (out / CX.META).write_text(json.dumps(meta), encoding="utf-8")
    page = " ".join(client.get(f"/retro/dataset/{ds.id}/{out.name}")
                    .text.split())
    assert "stopped after 1 of 2 weeks" in page
    assert f'<a href="/retro?dataset={ds.id}" id="rd-back">Back to the ' \
           f'replays</a>' in page
    assert "No forecasts stored yet" not in page
