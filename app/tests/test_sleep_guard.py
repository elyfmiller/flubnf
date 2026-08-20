"""The caffeinate sleep guard wrapped around long background runs.

The helper must spawn `caffeinate -i -w <this pid>` on macOS, decline
politely elsewhere, and swallow every spawn failure: a forecast or an
overnight retrospective must never depend on the guard.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.server import _sleep_guard              # noqa: E402


class _StubProc:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


def test_guard_spawns_caffeinate_on_macos(monkeypatch):
    calls = {}

    def fake_popen(cmd, **kw):
        calls["cmd"] = cmd
        calls["kw"] = kw
        return _StubProc()

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    p = _sleep_guard()
    assert isinstance(p, _StubProc)
    assert calls["cmd"] == ["caffeinate", "-i", "-w", str(os.getpid())]
    # a chatty guard would pollute the console's stdout/stderr
    assert calls["kw"]["stdout"] is subprocess.DEVNULL
    assert calls["kw"]["stderr"] is subprocess.DEVNULL
    # the caller ends the guard with terminate(); the stub records it
    p.terminate()
    assert p.terminated


def test_guard_declines_off_macos(monkeypatch):
    def fail_popen(*a, **kw):                       # must not be reached
        raise AssertionError("Popen called off macOS")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "Popen", fail_popen)
    assert _sleep_guard() is None


def test_guard_swallows_spawn_failure(monkeypatch):
    def broken_popen(*a, **kw):
        raise OSError("caffeinate not found")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", broken_popen)
    assert _sleep_guard() is None
