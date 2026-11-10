"""The public engine is the default everywhere a newcomer starts, and the
private engine runs only when FLUBNF_ENGINE=private names it (docs/ENGINE.md).

Read-only: these tests change no launcher and run none. They read each
launcher's text for its default route, and, with FLUBNF_ENGINE unset and no
install record, the words a newcomer sees when the engine is missing (the
fit preflight, doctor and Home's Setup card). Neither may send them to the
private engine's archive.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from flubnf import settings

REPO = Path(__file__).resolve().parents[1]

#: every script that installs, starts or switches the engine
LAUNCHERS = ("FluBNF.command", "SetupEngine.command", "setup_engine.sh",
             "setup.sh", "install.sh", "reinstall.sh", "FluBNF.bat",
             "setup.ps1", "FluBNF.app/Contents/MacOS/flubnf-launch")

#: words of the private engine's archive route, which a newcomer on the
#: default never needs
PRIVATE_ONLY = ("pybnf-pf-", "leave it unset", "fit_type = pf")


def _read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_no_launcher_says_the_private_engine_is_the_default():
    said = [f"{name}:{n}: {line.strip()}"
            for name in LAUNCHERS
            for n, line in enumerate(_read(name).splitlines(), 1)
            if re.search(r"opt-in until|stays the default", line, re.I)]
    assert said == []


def test_no_launcher_falls_back_to_private_when_nothing_is_set():
    for name in LAUNCHERS:
        src = _read(name)
        assert not re.search(r"FLUBNF_ENGINE:-\s*private", src), name
        assert not re.search(r'ENGINEROUTE=private"', src), name


@pytest.mark.parametrize("name, default", [
    ("FluBNF.command", '""|public) ROUTE=public ;;'),
    ("setup_engine.sh", '""|public) ROUTE=public ;;'),
    ("reinstall.sh", '[ -n "$ROUTE" ] || ROUTE=public'),
    ("install.sh", 'if [ -z "$ROUTE" ]; then\n  ROUTE=public'),
    ("setup.sh", 'if [ "$ROUTE" != private ]; then'),
    ("SetupEngine.command", 'if [ "$ROUTE" != private ]; then'),
    ("FluBNF.bat", 'set "ENGINEROUTE=public"\n'
                   'if defined FLUBNF_ENGINE set "ENGINEROUTE=%FLUBNF_ENGINE%"'),
    ("FluBNF.bat", 'if /I not "%ENGINEROUTE%"=="private" goto :publicengine'),
    ("setup.ps1", 'else { "public" }'),
])
def test_each_launcher_takes_the_public_route_unless_private_is_named(
        name, default):
    assert default in _read(name), f"{name} no longer defaults to public"


@pytest.fixture
def unset(monkeypatch, tmp_path):
    """No FLUBNF_ENGINE (the suite's conftest pins private), no install
    record, and no public engine venv."""
    monkeypatch.delenv("FLUBNF_ENGINE", raising=False)
    monkeypatch.setattr(settings, "_install_record_raw", lambda: None)
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC",
                       str(tmp_path / "no-venv" / "bin" / "python"))
    assert settings.engine_choice() == "public"
    assert settings.engine_source()[0] == "default"


def _newcomer_text(text: str, platform: str) -> None:
    step = ("open FluBNF.bat again" if platform == "win32"
            else "./setup_engine.sh --public")
    assert step in text, text
    for words in PRIVATE_ONLY:
        assert words not in text, (words, text)


@pytest.mark.parametrize("private_here", [False, True])
@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_the_missing_engine_message_names_the_public_install(
        unset, monkeypatch, platform, private_here):
    """The fit preflight's message (pf.engine_missing_message, the first
    reason sandbox.machine_problems gives) on the default."""
    from app.core.engines import pf
    monkeypatch.setattr(settings, "private_engine_installed",
                        lambda: private_here)
    _newcomer_text(pf.engine_missing_message(platform), platform)


def test_doctors_hint_names_the_public_install(unset, monkeypatch):
    from flubnf import doctor
    monkeypatch.setattr(settings, "private_engine_installed", lambda: False)
    res = doctor._check_engine_venv()
    assert res.name == "public engine venv"
    assert res.status is doctor.Status.WARN
    _newcomer_text(res.hint, sys.platform)


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_homes_setup_hint_names_the_public_install(unset, monkeypatch,
                                                   platform):
    from app.ui import templating
    monkeypatch.setattr(templating, "_platform", lambda: platform)
    _newcomer_text(str(templating._engine_setup_hint()), platform)
