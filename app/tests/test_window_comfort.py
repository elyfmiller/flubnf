"""The native window's comfort features: the Dock name, page zoom (pinch,
Cmd +/-/0, the Display menu's Zoom row), the shell filling wide windows,
and the slow-request log used to chase UI stutter."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                         # noqa: E402
from fastapi.testclient import TestClient             # noqa: E402

from app.ui import perflog                            # noqa: E402
from app.ui import server as srv                      # noqa: E402
from flubnf import cli                                # noqa: E402

client = TestClient(srv.app)
ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = (ROOT / "flubnf" / "cli.py").read_text()
NAU = (ROOT / "app" / "ui" / "static" / "nau.css").read_text()


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "logs" / "slow_requests.log"
    monkeypatch.setattr(perflog, "log_path", lambda: p)
    return p


# ------------------------------------------------------------- Dock name

def test_the_window_names_its_process_before_the_window_exists():
    i = CLI_SRC.index("_name_mac_process()\n")
    assert i < CLI_SRC.index("webview.create_window(")
    assert cli.APP_NAME == "FluBNF"


def test_naming_is_a_no_op_off_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cli._name_mac_process() is False


# ------------------------------------------------------------------ zoom

def test_zoom_steps_like_a_browser():
    assert cli._zoom_step(1.0, 1) == 1.1
    assert cli._zoom_step(1.0, -1) == 0.9
    assert cli._zoom_step(1.75, 0) == 1.0
    assert cli._zoom_step(cli.ZOOM_STEPS[-1], 1) == cli.ZOOM_STEPS[-1]
    assert cli._zoom_step(cli.ZOOM_STEPS[0], -1) == cli.ZOOM_STEPS[0]
    assert cli._zoom_step(1.05, 1) == 1.1       # off-grid snaps to the next


def test_the_zoom_bridge_never_raises_without_a_window():
    api = cli._WindowApi()
    assert api.zoom(1) == 1.0                    # no window: level unchanged
    assert api.set_zoom("junk") == 1.0


def test_the_window_is_created_zoomable_with_the_bridge():
    j = CLI_SRC.index("webview.create_window(APP_NAME")
    call = CLI_SRC[j:CLI_SRC.index("api._window = window", j)]
    assert "zoomable=True" in call and "js_api=api" in call
    assert "_allow_pinch_zoom, window" in CLI_SRC


def test_the_display_menu_zoom_row_waits_for_the_window_bridge():
    html = client.get("/methods").text
    assert 'class="zoompick zoomrow" role="group" aria-label="Page zoom" hidden' in html
    assert "addEventListener('pywebviewready',ready)" in html
    assert ".zoomrow[hidden]{display:none}" in NAU


# ----------------------------------------------------------------- width

def test_the_shell_fills_wide_windows_and_the_map_keeps_to_the_screen():
    assert "main{max-width:2560px;" in NAU
    assert ".usmap-wrap{max-width:min(100%,calc((100vh - 9rem) * 975 / 610))" in NAU
    from app.core import usmap
    assert 'class="usmap-wrap"' in usmap._shell("m", "", "#000", "#fff")


# ------------------------------------------------------ slow-request log

def test_fast_requests_are_not_logged_but_carry_server_timing(log):
    r = client.get("/api/busy")
    assert r.headers["Server-Timing"].startswith("app;dur=")
    assert not log.exists()


def test_a_slow_request_is_logged_with_the_load(log, monkeypatch):
    monkeypatch.setattr(perflog, "SLOW_MS", 0.0)
    client.get("/api/busy")
    line = log.read_text().splitlines()[-1]
    assert "server" in line and "GET /api/busy" in line and "load " in line


def test_a_slow_page_report_is_logged_and_junk_is_dropped(log):
    r = client.post("/api/perf", json={"path": "/retro", "total": 1500,
                                       "server": 40, "scripts": 900})
    assert r.status_code == 204
    assert "page" in log.read_text() and "/retro  server 40 ms scripts 900 ms" in log.read_text()
    n = len(log.read_text().splitlines())
    for bad in ({"path": "/x", "total": 10}, {"path": "x", "total": 5000},
                {"total": "nope"}, {}):
        assert client.post("/api/perf", json=bad).status_code == 204
    assert len(log.read_text().splitlines()) == n


def test_the_log_rolls_over(log, monkeypatch):
    monkeypatch.setattr(perflog, "MAX_BYTES", 100)
    for _ in range(10):
        perflog.write("server", 500, "GET /x")
    assert log.with_suffix(".log.1").exists()
    assert log.stat().st_size < 400
