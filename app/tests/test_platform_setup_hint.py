"""The setup instruction the console prints must be runnable on the machine
reading it.

Field report, 2026-08-25: a Windows user opened the Retrospective page and was
told to run `SetupEngine.command`, a macOS double-click script that Windows
cannot open at all. Three templates hardcoded that filename with no platform
check. These tests fail if that ever comes back.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server                           # noqa: E402
from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)
TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"

MAC_ONLY = "SetupEngine.command"
WINDOWS_SCRIPT = "setup.ps1"


def test_engine_setup_hint_names_a_script_this_platform_can_run(monkeypatch):
    for platform, wanted, unwanted in (
        ("darwin", MAC_ONLY, WINDOWS_SCRIPT),
        ("win32", WINDOWS_SCRIPT, MAC_ONLY),
        ("linux", "setup_engine.sh", MAC_ONLY),
    ):
        monkeypatch.setattr(server, "_platform", lambda p=platform: p)
        hint = str(server._engine_setup_hint())
        assert wanted in hint, (platform, hint)
        assert unwanted not in hint, (platform, hint)
    # and it is markup, not escaped text: the <code> must survive rendering
    monkeypatch.setattr(server, "_platform", lambda: "darwin")
    assert "<code>" in str(server._engine_setup_hint())


def test_no_console_page_names_a_mac_only_script_by_itself_on_windows(
        monkeypatch):
    """The guard proper. A page may name SetupEngine.command only when it
    also names the Windows equivalent (methods.html lists all three, because
    it is harvested into the platform-neutral public site). A page that names
    the macOS script alone, on Windows, is the reported bug."""
    monkeypatch.setattr(server, "_platform", lambda: "win32")
    for path in ("/", "/methods", "/retro"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        if MAC_ONLY in r.text:
            assert WINDOWS_SCRIPT in r.text, (
                f"{path} names {MAC_ONLY} to a Windows reader with no "
                f"Windows instruction anywhere on the page")


def test_home_and_retro_defer_to_the_platform_hint(monkeypatch):
    """Rendering alone cannot prove it: the Setup card and the retro warning
    are both conditional, so on a fully installed machine neither string is
    emitted. Check the template sources directly."""
    for name in ("home.html", "retro.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        assert MAC_ONLY not in src, (
            f"{name} hardcodes {MAC_ONLY}; use engine_setup_hint() instead")
        assert "engine_setup_hint()" in src, name


def test_methods_page_stays_platform_neutral_for_the_public_site():
    """app/core/site_build.py harvests methods.html into site/index.html, so
    a platform conditional there would publish the builder's platform."""
    src = (TEMPLATES / "methods.html").read_text(encoding="utf-8")
    assert "engine_setup_hint" not in src
    body = re.sub(r"\{#.*?#\}", "", src, flags=re.S)   # drop Jinja comments
    for name in (MAC_ONLY, "setup_engine.sh", WINDOWS_SCRIPT):
        assert name in body, name
