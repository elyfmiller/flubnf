"""The native window's comfort features: the Dock name, page zoom (pinch,
Cmd +/-/0, the Display menu's Zoom row), the shell filling wide windows,
and the slow-request log used to chase UI stutter."""
import json
import shutil
import subprocess
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
    assert api.can_zoom() is False


def test_the_windows_window_says_it_cannot_zoom(monkeypatch):
    """WebView2's window has a bridge but no zoom behind it: can_zoom() says
    so, and zoom() leaves the level alone (the page then hides the row and
    leaves Ctrl +/- to the system)."""
    api = cli._WindowApi()
    api._window = object()
    monkeypatch.setattr(sys, "platform", "win32")
    assert api.can_zoom() is False
    assert api.zoom(1) == 1.0 and api.zoom(1) == 1.0
    assert api.set_zoom(1.5) == 1.0
    monkeypatch.setattr(sys, "platform", "darwin")
    assert api.can_zoom() is True


NODE = shutil.which("node")


def _zoom_script() -> str:
    """base.html's page-zoom script, as the page carries it."""
    html = client.get("/methods").text
    start = html.index("(function(){\n  var can=false;")
    end = html.index("addEventListener('pywebviewready',ready);})();", start)
    return html[start:end + len("addEventListener('pywebviewready',ready);})();")]


def _run_zoom(tmp_path, can: bool) -> dict:
    """The zoom script against a stub page and bridge whose can_zoom() says
    `can`: whether the row shows and whether Ctrl+= is taken from the
    system."""
    drv = tmp_path / "zoom.js"
    drv.write_text(
        "var rows=[{hidden:true},{hidden:true}], calls=[], on={};\n"
        "var label={textContent:''};\n"
        "var document={querySelector:function(){return label;},\n"
        "  querySelectorAll:function(s){return s==='.zoomrow'?rows:[];}};\n"
        "var localStorage={getItem:function(){return null;},"
        "setItem:function(){}};\n"
        "function addEventListener(t,f){on[t]=f;}\n"
        "var window={pywebview:{api:{\n"
        f"  can_zoom:function(){{return Promise.resolve({str(can).lower()});}},\n"
        "  zoom:function(n){calls.push(n);return Promise.resolve(1.1);},\n"
        "  set_zoom:function(z){return Promise.resolve(z);}}}};\n"
        + _zoom_script() + "\n"
        "setTimeout(function(){\n"
        "  var e={metaKey:false,ctrlKey:true,altKey:false,key:'=',\n"
        "         prevented:false,preventDefault:function(){this.prevented=true;}};\n"
        "  on.keydown(e);\n"
        "  setTimeout(function(){console.log(JSON.stringify({\n"
        "    shown:rows.map(function(r){return !r.hidden;}),\n"
        "    prevented:e.prevented, calls:calls}));},0);},0);\n",
        encoding="utf-8")
    out = subprocess.run([NODE, str(drv)], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not NODE, reason="no node to run the page's script")
def test_the_zoom_row_and_keys_are_live_only_where_the_bridge_can_zoom(
        tmp_path):
    # Windows: the row stays hidden, and Ctrl+= reaches the system
    assert _run_zoom(tmp_path, can=False) == {
        "shown": [False, False], "prevented": False, "calls": []}
    # macOS: the row shows, and Cmd/Ctrl+= zooms through the bridge
    assert _run_zoom(tmp_path, can=True) == {
        "shown": [True, True], "prevented": True, "calls": [1]}


# ------------------------------------------------ when the server never answers

def test_the_server_failed_page_says_where_the_error_is_on_this_system():
    win = cli._server_fail_page("win32")
    assert "The console server did not start" in win
    assert ("If it happens again, look at the FluBNF.bat window for the "
            "error") in win
    assert ("<code>.venv\\Scripts\\flubnf app</code> in a Command Prompt in "
            "the FluBNF folder") in win
    assert "Terminal" not in win and ".venv/bin" not in win
    mac = cli._server_fail_page("darwin")
    assert "Terminal (<code>.venv/bin/flubnf app</code>)" in mac
    assert cli._SERVER_FAIL_PAGE == cli._server_fail_page()


def test_the_pywebview_hint_names_this_systems_pip():
    assert cli._pip_hint("pywebview", "win32") == \
        ".venv\\Scripts\\pip install pywebview"
    assert cli._pip_hint("pywebview", "darwin") == \
        ".venv/bin/pip install pywebview"


def test_the_window_is_created_zoomable_with_the_bridge():
    j = CLI_SRC.index("webview.create_window(APP_NAME")
    call = CLI_SRC[j:CLI_SRC.index("api._window = window", j)]
    assert "zoomable=True" in call and "js_api=api" in call
    assert "_allow_pinch_zoom, window" in CLI_SRC


def test_the_display_menu_zoom_row_waits_for_the_window_bridge():
    html = client.get("/methods").text
    assert 'class="zoompick zoomrow" role="group" aria-label="Page zoom" hidden' in html
    assert "addEventListener('pywebviewready',ready)" in html
    assert "a.can_zoom().then(" in html
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
