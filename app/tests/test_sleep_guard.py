"""The sleep guard wrapped around long background runs.

The helper must spawn `caffeinate -i -w <this pid>` on macOS, set
SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) on Windows,
decline politely elsewhere, and swallow every failure: a forecast or an
overnight retrospective must never depend on the guard.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ui.server import (_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED,   # noqa: E402
                           _sleep_guard, _windows_sleep_guard)


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


# ----------------------------------------------------------- Windows branch

class _StubKernel32:
    """Records SetThreadExecutionState calls and answers like the real API:
    the previous flags (nonzero) on success, 0 on failure."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def SetThreadExecutionState(self, flags):
        self.calls.append(flags)
        return 0 if self.fail else 0x80000000


def test_windows_guard_sets_then_clears_the_execution_state():
    k32 = _StubKernel32()
    guard = _windows_sleep_guard(kernel32=k32)
    assert guard is not None
    assert k32.calls == [_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED]
    # the caller ends the guard with terminate(): ES_CONTINUOUS alone clears
    guard.terminate()
    assert k32.calls[-1] == _ES_CONTINUOUS


def test_windows_guard_declines_when_the_call_fails():
    assert _windows_sleep_guard(kernel32=_StubKernel32(fail=True)) is None


def test_windows_guard_swallows_exceptions():
    class _Broken:
        def SetThreadExecutionState(self, flags):
            raise OSError("no kernel32 here")

    assert _windows_sleep_guard(kernel32=_Broken()) is None


def test_guard_dispatches_to_the_windows_impl(monkeypatch):
    import app.ui.server as server

    sentinel = object()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(server, "_windows_sleep_guard", lambda: sentinel)
    assert _sleep_guard() is sentinel
