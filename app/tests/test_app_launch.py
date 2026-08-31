"""Console launch survival (flubnf/cli.py): the single-instance pidfile
takeover, the free-port fallback, and the window load watchdog, all tested
headlessly. The takeover runs against real spawned processes (a marked fake
predecessor and an unmarked bystander); the watchdog runs against a fake
window that mimics the pywebview 6.2.1 semantics verified in cli.py
(events.loaded supports +=, load_url clears the loaded event)."""
import os
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import cli                                    # noqa: E402

MARK = "flubnf-test-entry"
MAX_PORT = 65535


def _free_port_with_headroom(headroom, listen=False):
    """A free (or, with listen=True, a held-and-listening) port that has
    at least `headroom` ports above it before the 65535 ceiling.

    The fallback tests seed themselves from an OS-assigned ephemeral port
    and then assert the search walks UPWARD from it. macOS hands out
    ephemeral ports in 49152-65535, so an unfiltered seed occasionally
    lands close enough to the top that the walk has nowhere legal to go
    and the assertion fails for a reason that has nothing to do with the
    behaviour under test. Re-rolling until the seed has room keeps those
    tests about fallback instead of about luck. The ceiling itself is
    covered deliberately by the tests further down."""
    for _ in range(200):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        if port + headroom <= MAX_PORT:
            if listen:
                s.listen(1)
                return s, port
            s.close()
            return None, port
        s.close()
    pytest.skip("no ephemeral port with headroom below the 65535 ceiling")


def _spawn_sleeper(*extra):
    return subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(60)", *extra])


# ------------------------------------------------- single-instance takeover

def test_takeover_terminates_marked_predecessor(tmp_path):
    proc = _spawn_sleeper(MARK)        # marker lands in the command line
    pf = tmp_path / "app.pid"
    pf.write_text(str(proc.pid))
    try:
        assert cli._terminate_predecessor(pf, markers=(MARK,)) is True
        assert proc.wait(timeout=10) != 0          # SIGTERM took it down
        assert not pf.exists()                     # stale record removed
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_takeover_leaves_unmarked_live_process_alone(tmp_path):
    # the pid is live but its command line lacks the entry marker: a
    # recycled pid must never get the predecessor treatment
    proc = _spawn_sleeper()
    pf = tmp_path / "app.pid"
    pf.write_text(str(proc.pid))
    try:
        assert cli._terminate_predecessor(pf, markers=(MARK,)) is False
        assert proc.poll() is None                 # untouched
        assert not pf.exists()                     # stale record removed
    finally:
        proc.kill()
        proc.wait()


def test_takeover_clears_dead_pid(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    pf = tmp_path / "app.pid"
    pf.write_text(str(proc.pid))
    assert cli._terminate_predecessor(pf, markers=(MARK,)) is False
    assert not pf.exists()


def test_takeover_never_signals_self(tmp_path):
    # a pidfile naming THIS process (a crashed cleanup, then a same-pid
    # relaunch path) must not lead to self-termination
    pf = tmp_path / "app.pid"
    pf.write_text(str(os.getpid()))
    assert cli._terminate_predecessor(pf, markers=("python",)) is False
    assert not pf.exists()


def test_takeover_survives_garbage_and_absent_pidfile(tmp_path):
    pf = tmp_path / "app.pid"
    pf.write_text("not-a-pid")
    assert cli._terminate_predecessor(pf) is False
    assert not pf.exists()
    assert cli._terminate_predecessor(tmp_path / "absent.pid") is False


def test_pidfile_written_and_cleaned_at_exit(tmp_path):
    pf = tmp_path / "app.pid"
    cleanup = cli._write_pidfile(pf)               # atexit runs this too
    assert pf.read_text() == str(os.getpid())
    cleanup()
    assert not pf.exists()
    cleanup()                                      # idempotent


def test_pidfile_cleanup_respects_a_new_owner(tmp_path):
    pf = tmp_path / "app.pid"
    cleanup = cli._write_pidfile(pf)
    pf.write_text("99999999")                      # a successor took over
    cleanup()
    assert pf.exists()                             # not ours: left alone


# ------------------------------------------------------- free-port fallback

def test_pick_port_prefers_the_preferred_port_when_free():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert cli._pick_port(free, tries=10) == free


def test_pick_port_falls_back_past_a_live_listener():
    holder, busy = _free_port_with_headroom(10, listen=True)
    with holder:
        got = cli._pick_port(busy, tries=10)
        assert got != busy
        assert busy < got < busy + 10
        # and the fallback port really is bindable
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", got))


def test_pick_port_returns_preferred_when_all_busy():
    socks = []
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            base = s.getsockname()[1]
            for p in range(base + 1, base + 3):
                try:
                    ns = socket.socket()
                    ns.bind(("127.0.0.1", p))
                    ns.listen(1)
                    socks.append(ns)
                except OSError:
                    socks.append(None)
            if any(x is None for x in socks):
                return                             # neighbor ports taken
            assert cli._pick_port(base, tries=3) == base
    finally:
        for ns in socks:
            if ns is not None:
                ns.close()


# --------------------------------------------------------- load watchdog

class _FakeLoaded:
    """pywebview 6.2.1 events.loaded, as verified in cli.py: += appends a
    handler fired from set(); is_set reflects the underlying event."""

    def __init__(self, initially_set=False):
        self._set = initially_set
        self._handlers = []

    def __iadd__(self, f):
        self._handlers.append(f)
        return self

    def is_set(self):
        return self._set

    def fire(self):
        self._set = True
        for f in list(self._handlers):
            f()


class _FakeWindow:
    """load_url clears the loaded event (the verified 6.2.1 behavior) and,
    when configured, succeeds on the nth call."""

    def __init__(self, loads_on_call=None, initially_set=False):
        self.events = types.SimpleNamespace(
            loaded=_FakeLoaded(initially_set))
        self.load_url_calls = []
        self.load_html_calls = []
        self._loads_on_call = loads_on_call

    def load_url(self, url):
        self.load_url_calls.append(url)
        self.events.loaded._set = False
        if (self._loads_on_call is not None
                and len(self.load_url_calls) >= self._loads_on_call):
            self.events.loaded.fire()

    def load_html(self, html):
        self.load_html_calls.append(html)


def test_watchdog_quiet_when_page_already_loaded():
    w = _FakeWindow(initially_set=True)
    assert cli._window_watchdog(w, "http://x", wait=0.05,
                                probe=lambda: True) == "loaded"
    assert w.load_url_calls == []
    assert w.load_html_calls == []


def test_watchdog_reloads_a_dead_window_once():
    # server answering, page dead: the one case a reload fixes
    w = _FakeWindow(loads_on_call=1)
    assert cli._window_watchdog(w, "http://x", wait=0.05,
                                probe=lambda: True) == "recovered"
    assert w.load_url_calls == ["http://x"]
    assert w.load_html_calls == []


def test_watchdog_never_reloads_while_server_is_down():
    # server NOT answering: a reload could only cache another refused page
    # and cancel a navigation in flight (the cold-start reload storm), so
    # the watchdog waits out its budget without touching the window
    w = _FakeWindow(loads_on_call=None)
    assert cli._window_watchdog(w, "http://x", wait=0.05,
                                probe=lambda: False) == "failed"
    assert w.load_url_calls == []
    assert len(w.load_html_calls) == 1


def test_watchdog_recovers_without_reload_when_page_lands_late():
    # server down, no reloads allowed, but the pending navigation completes
    # during the budget: recovered, window untouched
    import threading
    w = _FakeWindow(loads_on_call=None)
    threading.Timer(0.08, w.events.loaded.fire).start()
    assert cli._window_watchdog(w, "http://x", wait=0.06, retries=5,
                                probe=lambda: False) == "recovered"
    assert w.load_url_calls == []
    assert w.load_html_calls == []


def test_watchdog_shows_failure_page_after_all_retries():
    w = _FakeWindow(loads_on_call=None)
    assert cli._window_watchdog(w, "http://x", wait=0.05,
                                probe=lambda: True) == "failed"
    assert len(w.load_url_calls) == 3              # 3 retries, then give up
    assert len(w.load_html_calls) == 1
    assert "did not start" in w.load_html_calls[0]
    assert "relaunch" in w.load_html_calls[0]


def test_watchdog_catches_load_event_fired_between_attach_and_wait():
    # loaded fired before the handler attached: is_set covers the race
    w = _FakeWindow()
    w.events.loaded._set = True
    assert cli._window_watchdog(w, "http://x", wait=0.05,
                                probe=lambda: True) == "loaded"
    assert w.load_url_calls == []


def test_default_probe_is_false_for_a_dead_server():
    # nothing listens on this closed port: the real probe must say "down"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert cli._server_answering(f"http://127.0.0.1:{port}",
                                 timeout=0.3) is False


# ------------------------------------------------- held app socket

def test_bind_app_socket_holds_the_preferred_port():
    sock, port = cli._bind_app_socket(0)     # 0 = any free port
    try:
        assert sock is not None
        # the socket is LISTENING: a client connect succeeds even though
        # nothing has called accept yet (the backlog holds it, which is
        # what lets the window open before the server finishes importing)
        with socket.create_connection(("127.0.0.1", port), 1.0):
            pass
    finally:
        if sock is not None:
            sock.close()


def test_bind_app_socket_falls_back_past_a_live_listener():
    holder, base = _free_port_with_headroom(10, listen=True)
    with holder:
        sock, port = cli._bind_app_socket(base, tries=10)
        try:
            assert port != base
        finally:
            if sock is not None:
                sock.close()


# ------------------------------------------- the 65535 ceiling
# Both searches walk upward from `preferred`, and bind() rejects a port
# above 65535 with OverflowError, which is a ValueError and so escapes the
# `except OSError` that means "try the next port". These pin the walk to
# ports that can actually exist. Before the fix each one raised
# OverflowError out of the call instead of returning.

def _hold_the_top_port():
    """A live listener on 65535, so the search cannot take that port and
    must decide what to do at the ceiling. Skips rather than guesses when
    the machine already has 65535 spoken for: without a listener of our
    own we cannot tell a genuinely busy top port from a free one, and a
    free one would let the search succeed on its first probe and never
    reach the boundary this test exists to exercise."""
    s = socket.socket()
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", MAX_PORT))
        s.listen(1)
    except OSError:
        s.close()
        pytest.skip("port 65535 is not ours to hold on this machine")
    return s


def test_pick_port_stops_at_the_top_of_the_port_range():
    with _hold_the_top_port():
        # every legal candidate (there is exactly one, 65535) is busy, so
        # the all-busy contract applies: hand the preferred port back and
        # let uvicorn report the conflict
        assert cli._pick_port(MAX_PORT, tries=10) == MAX_PORT


def test_bind_app_socket_stops_at_the_top_of_the_port_range():
    with _hold_the_top_port():
        sock, port = cli._bind_app_socket(MAX_PORT, tries=10)
        try:
            assert sock is None
            assert port == MAX_PORT
        finally:
            if sock is not None:
                sock.close()


def test_port_search_declines_an_out_of_range_preferred_port():
    # no socket needed: 70000 is not a port, so there is nothing legal to
    # probe and both searches must fall through to their all-busy branch
    # rather than asking the kernel to bind a number it will reject
    assert cli._pick_port(70000, tries=3) == 70000
    sock, port = cli._bind_app_socket(70000, tries=3)
    try:
        assert sock is None
        assert port == 70000
    finally:
        if sock is not None:
            sock.close()


# ------------------------------------- Windows liveness + cmdline shims
# The Windows branches run on every platform through injected stubs, so
# the macOS suite exercises them without a Windows box.

class _StubKernel32:
    """Emulates the OpenProcess / GetExitCodeProcess / CloseHandle trio."""

    def __init__(self, open_result=1234, exit_code=259, last_error=0):
        self.open_result = open_result
        self.exit_code = exit_code
        self.last_error = last_error
        self.closed = []

    def OpenProcess(self, access, inherit, pid):
        return self.open_result

    def GetLastError(self):
        return self.last_error

    def GetExitCodeProcess(self, handle, code_ref):
        code_ref._obj.value = self.exit_code
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


def test_windows_alive_for_a_running_process():
    k32 = _StubKernel32(exit_code=259)             # STILL_ACTIVE
    assert cli._pid_alive_windows(4242, kernel32=k32) is True
    assert k32.closed == [1234]                    # handle released


def test_windows_dead_for_an_exited_process():
    k32 = _StubKernel32(exit_code=0)
    assert cli._pid_alive_windows(4242, kernel32=k32) is False
    assert k32.closed == [1234]


def test_windows_dead_when_no_such_process():
    k32 = _StubKernel32(open_result=0, last_error=87)
    assert cli._pid_alive_windows(4242, kernel32=k32) is False


def test_windows_access_denied_means_alive_but_not_ours():
    # the pid exists under another account: alive (so no pidfile reuse),
    # and the empty cmdline downstream keeps the takeover's hands off it
    k32 = _StubKernel32(open_result=0, last_error=5)
    assert cli._pid_alive_windows(4242, kernel32=k32) is True


def test_windows_cmdline_parses_the_wmic_list_format(monkeypatch):
    def fake_run(q, **kw):
        assert q[0] == "wmic"
        return types.SimpleNamespace(
            returncode=0,
            stdout="\n\nCommandLine=C:\\r\\.venv\\Scripts\\flubnf.exe app\n\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert (cli._pid_cmdline_windows(1)
            == "C:\\r\\.venv\\Scripts\\flubnf.exe app")


def test_windows_cmdline_falls_back_to_powershell(monkeypatch):
    def fake_run(q, **kw):
        if q[0] == "wmic":                         # removed on new Win11
            raise FileNotFoundError("wmic not found")
        assert q[0] == "powershell"
        return types.SimpleNamespace(returncode=0, stdout="py.exe -m thing\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli._pid_cmdline_windows(1) == "py.exe -m thing"


def test_windows_cmdline_empty_result_fails_safe(monkeypatch):
    # "could not inspect" must come back as '' so the takeover never kills
    # a pid it could not positively identify
    monkeypatch.setattr(
        subprocess, "run",
        lambda q, **kw: types.SimpleNamespace(returncode=1, stdout=""))
    assert cli._pid_cmdline_windows(1) == ""


def test_entry_markers_match_the_windows_exe_spelling():
    cmd = r"C:\repo\.venv\Scripts\flubnf.exe app"
    assert any(mk in cmd for mk in cli.APP_ENTRY_MARKERS)


def test_pid_helpers_dispatch_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(cli, "_pid_cmdline_windows", lambda pid: f"win:{pid}")
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    assert cli._pid_cmdline(7) == "win:7"
    assert cli._pid_alive(7) is True
