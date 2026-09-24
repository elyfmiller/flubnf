"""Per-button run-interference guards and the report download: /api/busy,
the retro stop endpoint and between-weeks stop, the guard modal, the exact
set of guarded controls, the season-report download attribute, and the
Reveal-in-Finder fallback.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                       # noqa: E402
from fastapi.testclient import TestClient           # noqa: E402

from app.core import data as core_data              # noqa: E402
from app.ui import server as srv                    # noqa: E402
from app.ui import pipeline as ui_pipeline          # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import state as ui_state                # noqa: E402

client = TestClient(srv.app)

SEASON = "2098-99"


@pytest.fixture(autouse=True)
def _isolated_status():
    """Snapshot and restore the module-level status stores around each test
    so mocked busy states never leak between tests."""
    status_before = dict(ui_state._status)
    retro_before = dict(ui_retro_seasons._retro_status)
    stop_before = set(ui_retro_seasons._retro_stop)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_retro_seasons._retro_status.clear(); ui_retro_seasons._retro_status.update(retro_before)
    ui_retro_seasons._retro_stop.clear(); ui_retro_seasons._retro_stop.update(stop_before)


# ---------------------------------------------------------------- /api/busy

def test_busy_idle_shape():
    ui_state._status.update({"running": None, "phase": "", "run_label": ""})
    ui_retro_seasons._retro_status.clear()
    r = client.get("/api/busy")
    assert r.status_code == 200
    assert r.json() == {"console_run": None, "retro": {}, "phase": "",
                        "sandbox": None}


def test_busy_reports_console_run_and_phase():
    ui_state._status.update({"running": "all:20990101_000000",
                        "run_label": "2099-01-02 · 3 state(s) + US",
                        "phase": "materializing models (BNG network generation)"})
    b = client.get("/api/busy").json()
    assert b["console_run"] == "2099-01-02 · 3 state(s) + US"
    assert "materializing" in b["phase"]


def test_busy_console_label_falls_back_to_claim():
    ui_state._status.update({"running": "starting", "run_label": "", "phase": ""})
    assert client.get("/api/busy").json()["console_run"] == "starting"


def test_busy_lists_only_running_or_stopping_seasons():
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update({SEASON: "running", "2097-98": "done",
                                           "2096-97": "error: boom", "2095-96": "stopping"})
    b = client.get("/api/busy").json()
    assert b["retro"] == {SEASON: "running", "2095-96": "stopping"}


# --------------------------------------------------------------- retro stop

def test_retro_stop_flags_running_seasons_only():
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_stop.clear()
    ui_retro_seasons._retro_status.update({SEASON: "running", "2097-98": "done"})
    r = client.post("/retro/stop", follow_redirects=False)
    assert r.status_code == 303
    assert ui_retro_seasons._retro_status[SEASON] == "stopping"
    assert ui_retro_seasons._retro_status["2097-98"] == "done"
    assert ui_retro_seasons._retro_stop == {SEASON}


def test_retro_stop_idle_is_harmless():
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_stop.clear()
    r = client.post("/retro/stop", follow_redirects=False)
    assert r.status_code == 303
    assert ui_retro_seasons._retro_stop == set()


def test_retro_run_refused_while_stopping():
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status[SEASON] = "stopping"
    r = client.post("/retro/run", data={"season": SEASON},
                    follow_redirects=False)
    assert r.status_code == 303
    assert ui_retro_seasons._retro_status[SEASON] == "stopping"   # unchanged


def test_retro_bg_stops_between_weeks_and_keeps_weeks(monkeypatch, tmp_path):
    from app.core import retro
    monkeypatch.setattr(ui_pipeline, "_sleep_guard", lambda: None)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    seen = []

    def fake_run_season(root, season, locations, replicates=3,
                        particles=10_000, width=4, progress=None,
                        settings=None, engine="pf"):
        seen.append("week1")                 # first week lands on disk
        ui_retro_seasons._retro_stop.add(season)          # then a stop request arrives
        progress("2098-11-07")               # the between-weeks stop point
        raise AssertionError("worker must stop after the completed week")

    def no_score(*a, **k):
        raise AssertionError("a stopped run must not be scored")

    monkeypatch.setattr(retro, "run_season", fake_run_season)
    monkeypatch.setattr(retro, "score_season", no_score)
    srv._retro_bg(SEASON, ["Ohio"], width=1)
    assert seen == ["week1"]
    assert ui_retro_seasons._retro_status[SEASON] == "stopped"
    assert SEASON not in ui_retro_seasons._retro_stop     # flag consumed, replay resumable


# ------------------------------------------------------------- modal markup

def test_guard_modal_present_on_every_page():
    html = client.get("/data").text
    assert 'id="guard-modal"' in html
    assert "Stop run and proceed" in html
    assert 'id="guard-cancel"' in html
    # the resumability note the spec requires, verbatim themes
    assert "kept and resume" in html
    assert "restarts from scratch" in html
    assert "/api/busy" in html               # the guard actually checks


def test_guarded_attributes_on_exactly_the_classified_controls():
    import re

    def kinds(html):
        return set(re.findall(r'data-guard="([^"]+)"', html))

    # interfering actions carry only their own guard kind; resume/re-run
    # shortcuts carry the same kind as their form, so the set stays fixed
    fc = client.get("/forecast").text
    assert kinds(fc) == {"console-run"}
    assert 'data-guard="console-run">Run models' in fc

    rt = client.get("/retro").text
    assert kinds(rt) == {"retro-run"}
    assert 'data-guard="retro-run"' in rt

    dt = client.get("/data").text
    assert dt.count('data-guard="') == 1
    assert 'data-guard="data-pull">Update data' in dt
    # the safe freshness check stays friction-free
    assert 'data-guard' not in dt.split("Check for new data")[0].rsplit(
        "<form", 1)[-1]

    # the model pages' run buttons (incl. the pf2s research control) post to
    # /run and carry the same guard
    for page in ("/model/pf", "/model/analogue", "/models", "/model/pf2s"):
        mp = client.get(page).text
        assert mp.count('data-guard="') == 1, page
        assert 'data-guard="console-run"' in mp, page

    # safe pages: viewing and downloads; storage deletes use the confirm
    # shell and server-side checks, not a data-guard
    for page in ("/", "/output", "/runs", "/model/ensemble"):
        assert 'data-guard="' not in client.get(page).text, page


# ---------------------------------------- server-side busy cross-checks
# The client guard is a convenience: the server itself refuses a
# double-booking (second tab, stale page, script).

def test_post_run_refused_while_a_retrospective_replays(tmp_path,
                                                        monkeypatch):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(core_data, "vintage_path", lambda d: tmp_path)
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: started.append(spec))
    form_before = dict(ui_state._last_form)
    ui_retro_seasons._retro_status[SEASON] = "running"
    try:
        r = client.post("/run", data={"forecast_date": "2098-01-04",
                                      "locations": ["Ohio"]},
                        follow_redirects=False)
        assert r.status_code == 303
        assert ui_state._status.get("running") is None    # no claim was made
        assert started == []                         # no worker was launched
        flash = ui_state._status.get("flash", "")
        assert "retrospective replay holds the engine" in flash
        assert SEASON in flash
    finally:
        ui_state._last_form.clear()
        ui_state._last_form.update(form_before)


def test_post_retro_run_refused_over_a_console_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    ui_retro_seasons._retro_status.clear()
    ui_state._status.update({"running": "all:20990101T000000-abc",
                        "run_label": "2099-01-02 · 3 state(s) + US"})
    r = client.post("/retro/run", data={"season": SEASON},
                    follow_redirects=False)
    assert r.status_code == 303
    assert SEASON not in ui_retro_seasons._retro_status           # no season was claimed
    flash = ui_state._status.get("flash", "")
    assert "console run holds the engine" in flash
    assert "2099-01-02" in flash                     # names what holds it


def test_post_retro_run_refused_over_another_season(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    ui_retro_seasons._retro_status.clear()
    ui_state._status.update({"running": None})
    ui_retro_seasons._retro_status["2097-98"] = "running"
    r = client.post("/retro/run", data={"season": SEASON},
                    follow_redirects=False)
    assert r.status_code == 303
    assert SEASON not in ui_retro_seasons._retro_status
    assert ui_retro_seasons._retro_status["2097-98"] == "running"  # untouched
    flash = ui_state._status.get("flash", "")
    assert "Another season is already replaying" in flash
    assert "2097-98" in flash


def test_retro_run_button_clickable_while_running():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 3, "seal": False,
                  "running": True, "scored": False}])
    seg = html.split('data-guard="retro-run"')[1].split(">")[0]
    assert "disabled" not in seg     # the guard, not disabling, owns the flow
    # the auto-refresh is a script timer that yields to an open guard modal
    assert "GUARD_BUSY" in html
    assert 'http-equiv="refresh"' not in html


# ------------------------------------------- report download and reveal

def test_download_anchor_and_reveal_button():
    html = srv.templates.env.get_template("retro_season.html").render(
        active="Retrospective", season=SEASON, heads={"ensemble": 0.9},
        curve=[("2098-11-07", 0.95)], states=[],
        weeks=["2098-11-07"], week="2098-11-07",
        map_html="<div id='usmap-wrap'></div>", n_weeks=1, score_error="")
    # the anchor carries the download attribute (WKWebView download path)
    assert f'<a href="/retro/{SEASON}/report" download>' in html
    # the reveal fallback: fetch the built report's path, post it to the
    # existing reveal endpoint
    assert 'id="rev-report"' in html
    assert f'data-season="{SEASON}"' in html
    assert "/report_path'" in html
    assert "'/output/reveal'" in html
    assert "URLSearchParams({path:d.path})" in html


def test_report_path_endpoint_builds_and_returns_path(tmp_path, monkeypatch):
    from app.core import report_season
    calls = []

    def fake_build(root, season, archive="", build="", versions=None):
        calls.append((root, season))
        p = root / f"{season}-FluBNF-season-report.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("report")
        return p

    monkeypatch.setattr(report_season, "build_season_report", fake_build)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    r = client.get(f"/api/retro/{SEASON}/report_path")
    assert r.status_code == 200
    assert r.json() == {"path": str(tmp_path / SEASON /
                                    f"{SEASON}-FluBNF-season-report.html")}
    assert calls == [(tmp_path / SEASON, SEASON)]    # same builder, same root


def test_report_path_unknown_season_is_404(tmp_path, monkeypatch):
    from app.core import playback, report_season

    def raise_unknown(root, season, archive="", build="", versions=None):
        raise playback.UnknownWeek(f"no weeks for {season}")

    monkeypatch.setattr(report_season, "build_season_report", raise_unknown)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    r = client.get("/api/retro/2097-98/report_path")
    assert r.status_code == 404
    assert "2097-98" in r.text


def test_reveal_spawns_open_for_app_state_paths_only(tmp_path, monkeypatch):
    import app.core.runs as runs_mod
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    inside = tmp_path / "retro" / SEASON / "r.html"
    inside.parent.mkdir(parents=True)
    inside.write_text("x")
    spawned = []
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kw: spawned.append(args))
    r = client.post("/output/reveal", data={"path": str(inside)},
                    follow_redirects=False)
    assert r.status_code == 303
    # the reveal command is platform-dispatched; assert the branch for the
    # platform the suite is running on (CI runs this on Linux and Windows too)
    resolved = str(inside.resolve())
    expected = {
        "darwin": [["open", "-R", resolved]],
        "win32": [["explorer", f"/select,{inside.resolve()}"]],
    }.get(sys.platform, [["xdg-open", str(inside.resolve().parent)]])
    assert spawned == expected
    # a path outside the app state is refused without side effects
    spawned.clear()
    r = client.post("/output/reveal", data={"path": "/etc/hosts"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert spawned == []


def test_cli_enables_pywebview_downloads_before_window_creation():
    src = (Path(__file__).resolve().parents[2] / "flubnf" / "cli.py").read_text()
    i = src.index("webview.settings['ALLOW_DOWNLOADS'] = True")
    j = src.index("webview.create_window")
    assert i < j
