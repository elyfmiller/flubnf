"""`flubnf app` in the browser (flubnf/cli.py app_serve).

On Linux, pywebview installs as plain Python whose GTK and Qt backends are
extras FluBNF does not request, and a setup.sh venv cannot see the system's
python3-gi: `import webview` works and the window then fails. So the
command checks for gi or qtpy first, and without either opens the console
in the browser. The browser route prints its address before the server
starts, for a terminal with no browser to open (SSH, WSL2, a headless
machine).

Every side effect is a stand-in: no predecessor is signalled, no pidfile is
written, uvicorn never starts and no browser opens. The port is one this
test holds, so the route's readiness wait ends at once.
"""
import socket
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import cli                                    # noqa: E402

LINE = "FluBNF console: http://localhost:{port}  (Ctrl-C stops it)"
NO_TOOLKIT = ("No GTK or Qt for a native window here: opening the console "
              "in your browser.")


def _find_spec(*present):
    """importlib.util.find_spec as a machine answers it where, of gi and
    qtpy, only `present` can be imported."""
    import importlib.util
    real = importlib.util.find_spec

    def find_spec(name, *a, **k):
        if name in ("gi", "qtpy"):
            return types.SimpleNamespace(name=name) if name in present else None
        return real(name, *a, **k)
    return find_spec


# ------------------------------------------------------- the toolkit probe

@pytest.mark.parametrize("platform", ["darwin", "win32", "cygwin"])
def test_macos_and_windows_bring_their_own_toolkit(monkeypatch, platform):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", _find_spec())
    assert cli._no_window_toolkit(platform) is False


@pytest.mark.parametrize("present, expected", [
    ((), True),                 # a setup.sh venv on Ubuntu or WSL2
    (("gi",), False),           # GTK's bindings
    (("qtpy",), False),         # Qt's
    (("gi", "qtpy"), False),
])
def test_linux_needs_gtk_or_qt_bindings(monkeypatch, present, expected):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", _find_spec(*present))
    assert cli._no_window_toolkit("linux") is expected


def test_a_probe_that_raises_counts_as_absent(monkeypatch):
    """find_spec raises ValueError for a module whose __spec__ is None."""
    import importlib.util

    def find_spec(name, *a, **k):
        raise ValueError(f"{name}.__spec__ is None")
    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    assert cli._no_window_toolkit("linux") is True


# ------------------------------------------------------- the browser route

@pytest.fixture
def browser_route(monkeypatch, capsys):
    """app_serve with every side effect replaced. Returns what happened:
    the output before uvicorn.run, uvicorn.run's arguments, the URL the
    browser was sent to and whether app_window ran."""
    import uvicorn
    import webbrowser

    for var in ("FLUBNF_BOOT_STATUS", "FLUBNF_STARTUP_TRACE",
                "FLUBNF_HOST_FALLBACK"):
        monkeypatch.delenv(var, raising=False)
    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    held.listen(4)                  # the readiness wait connects at once
    port = held.getsockname()[1]
    seen = {"window": False, "opened": None}
    opened = threading.Event()

    def open_(url, *a, **k):
        seen["opened"] = url
        opened.set()
        return True

    def run(app, **kwargs):
        seen["printed"] = capsys.readouterr().out   # before the server
        seen["run"] = (app, kwargs)
        # the route's thread opens the browser once the port answers: wait
        # for it here, so nothing of it outlives the test
        assert opened.wait(10), "the browser was never opened"

    def window(port=8710):
        seen["window"] = True

    monkeypatch.setattr(uvicorn, "run", run)
    monkeypatch.setattr(webbrowser, "open", open_)
    for name, stand_in in {
            "_trace": lambda msg: None,
            "_windows_mshtml_only": lambda: False,
            "_terminate_predecessor": lambda *a, **k: False,
            "_write_pidfile": lambda *a, **k: (lambda: None),
            "_pick_port": lambda preferred=8710, tries=10: port,
            "_boot_started": lambda: None,
            "app_window": window}.items():
        monkeypatch.setattr(cli, name, stand_in)
    yield types.SimpleNamespace(port=port, seen=seen)
    held.close()


def _linux_probe(monkeypatch, *present):
    """The real probe as Linux answers it, where of gi and qtpy only
    `present` can be imported (sys.platform itself is left alone: patching
    it changes what modules imported meanwhile define)."""
    import importlib.util
    probe = cli._no_window_toolkit
    monkeypatch.setattr(importlib.util, "find_spec", _find_spec(*present))
    monkeypatch.setattr(cli, "_no_window_toolkit",
                        lambda platform=None: probe("linux"))


def test_linux_without_gtk_or_qt_opens_the_browser_and_prints_the_address(
        monkeypatch, browser_route):
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    _linux_probe(monkeypatch)
    cli.app_serve(port=8710)
    seen, url = browser_route.seen, f"http://localhost:{browser_route.port}"
    assert seen["window"] is False
    assert NO_TOOLKIT in seen["printed"]
    assert LINE.format(port=browser_route.port) in seen["printed"]
    assert seen["printed"].index(NO_TOOLKIT) < seen["printed"].index(url)
    assert seen["opened"] == url
    app, kwargs = seen["run"]
    assert app == "app.ui.server:app"
    assert kwargs["port"] == browser_route.port
    assert kwargs["host"] == "127.0.0.1"


def test_macos_without_pywebview_prints_the_same_address(
        monkeypatch, browser_route):
    """No pywebview at all (`import webview` fails): the same route and the
    same line, and nothing about GTK or Qt."""
    monkeypatch.setitem(sys.modules, "webview", None)   # ImportError
    monkeypatch.setattr(cli, "_no_window_toolkit", lambda platform=None: False)
    cli.app_serve(port=8710)
    seen = browser_route.seen
    assert seen["window"] is False
    assert seen["printed"].splitlines() == [
        LINE.format(port=browser_route.port)]
    assert seen["opened"] == f"http://localhost:{browser_route.port}"


def test_linux_with_gtk_keeps_the_native_window(monkeypatch, browser_route):
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    _linux_probe(monkeypatch, "gi")
    cli.app_serve(port=8710)
    seen = browser_route.seen
    assert seen["window"] is True
    assert "run" not in seen and seen["opened"] is None
