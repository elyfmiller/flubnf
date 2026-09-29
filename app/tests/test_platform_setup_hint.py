"""The setup instruction the console prints must be runnable on the machine
reading it: never the macOS-only SetupEngine.command alone on Windows, and
on Windows the route that needs no GitHub account (the lab's engine file in
Downloads, then FluBNF.bat), not setup.ps1, which only diagnoses.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

import flubnf.settings as fs                        # noqa: E402
from app.core import engine_build                   # noqa: E402
from app.ui import templating as ui_templating      # noqa: E402
from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)
TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"

MAC_ONLY = "SetupEngine.command"
WINDOWS_SCRIPT = "FluBNF.bat"


def test_engine_setup_hint_names_a_script_this_platform_can_run(monkeypatch):
    for platform, wanted, unwanted in (
        ("darwin", MAC_ONLY, WINDOWS_SCRIPT),
        ("win32", WINDOWS_SCRIPT, MAC_ONLY),
        ("linux", "setup_engine.sh", MAC_ONLY),
    ):
        monkeypatch.setattr(ui_templating, "_platform", lambda p=platform: p)
        hint = str(ui_templating._engine_setup_hint())
        assert wanted in hint, (platform, hint)
        assert unwanted not in hint, (platform, hint)
    # and it is markup, not escaped text: the <code> must survive rendering
    monkeypatch.setattr(ui_templating, "_platform", lambda: "darwin")
    assert "<code>" in str(ui_templating._engine_setup_hint())


def test_the_windows_hint_is_the_lab_file_and_needs_no_github_account(
        monkeypatch):
    monkeypatch.setattr(ui_templating, "_platform", lambda: "win32")
    hint = str(ui_templating._engine_setup_hint())
    assert (f"save the engine file from the lab (<code>"
            f"{engine_build.archive_name()}</code>) in your Downloads folder "
            "and open <code>FluBNF.bat</code> again") in hint
    assert "no GitHub account is needed" in hint
    assert "docs\\ENGINE.md" in hint
    # setup.ps1 reports what is missing and installs no engine; bash
    # scripts do not run there
    for gone in ("setup.ps1", "setup_engine.sh", "WINDOWS.md"):
        assert gone not in hint, gone


def test_no_console_page_names_a_mac_only_script_by_itself_on_windows(
        monkeypatch):
    """A page may name SetupEngine.command only beside the Windows equivalent
    (methods.html lists all three for the platform-neutral public site)."""
    monkeypatch.setattr(ui_templating, "_platform", lambda: "win32")
    for path in ("/", "/methods", "/retro"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        if MAC_ONLY in r.text:
            assert WINDOWS_SCRIPT in r.text, (
                f"{path} names {MAC_ONLY} to a Windows reader with no "
                f"Windows instruction anywhere on the page")


def test_home_and_retro_defer_to_the_platform_hint(monkeypatch):
    """The Setup card and retro warning are conditional (absent on a fully
    installed machine), so check the template sources directly."""
    for name in ("home.html", "retro.html"):
        src = (TEMPLATES / name).read_text(encoding="utf-8")
        assert MAC_ONLY not in src, (
            f"{name} hardcodes {MAC_ONLY}; use engine_setup_hint() instead")
        assert "engine_setup_hint()" in src, name


def _missing(*names):
    """settings.check()'s rows for the named components."""
    return [(n, f"/nowhere/{n}", f"{n}: not here") for n in names]


def test_home_offers_the_engine_install_only_when_the_engine_is_missing(
        monkeypatch):
    monkeypatch.setattr(ui_templating, "_platform", lambda: "win32")
    monkeypatch.setattr(fs, "check", lambda verbose=True: _missing(
        "FLUBNF_PY_ENGINE", "FLUBNF_PYBNF", "perl"))
    html = client.get("/").text
    assert "To add the particle-filter engine, save the engine file" in html
    # the engine is installed and only Perl is missing (a first Windows open
    # whose PATH predates the Strawberry Perl it just installed): the run
    # preflight's own Perl message, never "add the engine"
    monkeypatch.setattr(fs, "check", lambda verbose=True: _missing("perl"))
    html = client.get("/").text
    assert "To add the particle-filter engine" not in html
    assert "Perl was not found on PATH" in html
    assert "install Strawberry Perl" in html
    assert "1 not installed" in html
    # the hub alone is no engine matter either
    monkeypatch.setattr(fs, "check",
                        lambda verbose=True: _missing("FLUBNF_HUB"))
    html = client.get("/").text
    assert "To add the particle-filter engine" not in html
    assert "Perl was not found" not in html


def test_the_perl_message_on_home_follows_the_platform(monkeypatch):
    monkeypatch.setattr(fs, "check", lambda verbose=True: _missing("perl"))
    monkeypatch.setattr(ui_templating, "_platform", lambda: "darwin")
    html = client.get("/").text
    assert "perl ships with macOS" in html
    assert "Strawberry Perl" not in html


def test_methods_page_stays_platform_neutral_for_the_public_site():
    """app/core/site_build.py harvests methods.html into site/index.html, so
    a platform conditional there would publish the builder's platform."""
    src = (TEMPLATES / "methods.html").read_text(encoding="utf-8")
    assert "engine_setup_hint" not in src
    body = re.sub(r"\{#.*?#\}", "", src, flags=re.S)   # drop Jinja comments
    for name in (MAC_ONLY, "setup_engine.sh", WINDOWS_SCRIPT):
        assert name in body, name


def test_the_engine_venv_and_its_pin_are_credited_to_the_real_installers():
    """FluBNF.bat builds the engine venv on Windows (setup.ps1 only prints
    what is missing), and the bngsim pin is in every engine installer."""
    methods = client.get("/methods").text
    assert ("<code>setup_engine.sh</code> on\n  Linux, <code>FluBNF.bat</code> "
            "on Windows") in methods
    assert "<code>setup.ps1</code> on Windows" not in methods
    assert "bngsim 0.15.1 (pinned by every engine\n      installer)" in methods
    home = (TEMPLATES / "home.html").read_text(encoding="utf-8")
    assert "bngsim 0.15.1 (pinned by every engine installer)" in home
    assert "0.15.1 (setup_engine.sh)" not in home
    # each installer really pins it
    repo = Path(__file__).resolve().parents[2]
    for name in ("setup_engine.sh", "FluBNF.bat"):
        assert "bngsim==0.15.1" in (repo / name).read_text(encoding="utf-8")
