"""The native window must never open on MSHTML.

MEASURED 2026-09-01, Windows Sandbox: pywebview fell back to MSHTML (IE11)
for want of the WebView2 runtime, the console's JavaScript never ran, and a
silently dead location picker launched a full-grid, 3-replicate run from a
click meant to select one state. The guard: on Windows without WebView2,
both console entry points serve to the default browser instead.
"""
import contextlib
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from flubnf.cli import _windows_mshtml_only  # noqa: E402


def _fake_winreg(pv=None, raise_all=False):
    """A winreg stand-in: every probe raises, or every probe returns pv."""
    m = types.ModuleType("winreg")
    m.HKEY_LOCAL_MACHINE = object()
    m.HKEY_CURRENT_USER = object()

    @contextlib.contextmanager
    def open_key(hive, path):
        if raise_all:
            raise FileNotFoundError(path)
        yield "key"

    m.OpenKey = open_key
    m.QueryValueEx = lambda k, name: (pv, 1)
    return m


def test_not_windows_is_never_mshtml_only():
    assert sys.platform != "win32", "this suite does not run on Windows"
    assert _windows_mshtml_only() is False


def test_windows_without_webview2_is_mshtml_only(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(raise_all=True))
    assert _windows_mshtml_only() is True


def test_windows_with_webview2_gets_the_window(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(pv="140.0.7339.35"))
    assert _windows_mshtml_only() is False


def test_the_null_version_stamp_counts_as_missing(monkeypatch):
    # Microsoft documents pv == 0.0.0.0 as "not really installed"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(pv="0.0.0.0"))
    assert _windows_mshtml_only() is True


def test_both_entry_points_consult_the_guard():
    """Source pin: 'flubnf app' must check before preferring the window,
    and a direct 'flubnf window' must check before creating one."""
    src = (REPO / "flubnf" / "cli.py").read_text(encoding="utf-8")
    serve = src.split('@app.command("app")')[1].split('@app.command')[0]
    window = src.split('@app.command("window")')[1].split('@app.command')[0]
    assert "_windows_mshtml_only()" in serve, (
        "'flubnf app' would open the native window without checking the "
        "engine it renders on")
    assert "_windows_mshtml_only()" in window, (
        "'flubnf window' would create a window without checking the "
        "engine it renders on")
