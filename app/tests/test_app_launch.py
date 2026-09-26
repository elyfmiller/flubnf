"""Console launch survival (flubnf/cli.py): the single-instance pidfile
takeover, the free-port fallback, and the window load watchdog, all tested
headlessly. The takeover runs against real spawned processes (a marked fake
predecessor and an unmarked bystander); the watchdog runs against a fake
window that mimics the pywebview 6.2.1 semantics verified in cli.py
(events.loaded supports +=, load_url clears the loaded event)."""
import ctypes
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
    """A free (or held-and-listening) port with >= `headroom` ports above it:
    macOS ephemeral ports reach 65535, so re-roll until the upward fallback
    walk has room. The ceiling itself is tested separately."""
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
    proc = subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(60)", *extra])
    # until the child has exec'd, its command line is still the parent's
    # (no marker yet): a loaded machine can show that window, so wait it out
    import time
    t0 = time.time()
    while time.time() - t0 < 10 and extra and not all(
            m in cli._pid_cmdline(proc.pid) for m in extra):
        time.sleep(0.02)
    return proc


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
    # a marker built from this process's own command line, checked to match
    # first, so the only thing that can stop the signal is the self-guard
    own = cli._pid_cmdline(os.getpid())
    if not own:
        pytest.skip("cannot read this process's own command line here")
    mk = own.replace('"', " ").split()[0].replace("\\", "/").rsplit("/", 1)[-1]
    assert cli._cmdline_has_marker(own, (mk,)), (own, mk)
    assert cli._terminate_predecessor(pf, markers=(mk,)) is False
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
    # server NOT answering: a reload would only cancel a navigation in flight
    # (the cold-start reload storm), so wait out the budget untouched
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
        # LISTENING: connect succeeds before accept (the backlog holds it),
        # which lets the window open before the server finishes importing
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
# Both searches walk upward from `preferred`; bind() rejects a port above
# 65535 with OverflowError (a ValueError, not the OSError that means "try the
# next port"), so the walk must stop at ports that exist.

def _hold_the_top_port():
    """A live listener on 65535, so the search must decide at the ceiling.
    Skips if 65535 is already taken: a port we do not hold could be free and
    end the search before the boundary."""
    s = socket.socket()
    try:
        cli._set_port_reuse(s)          # the app's own option, so the hold
        s.bind(("127.0.0.1", MAX_PORT))  # is one the app's probe respects
        s.listen(1)
    except OSError:
        s.close()
        pytest.skip("port 65535 is not ours to hold on this machine")
    return s


def test_pick_port_stops_at_the_top_of_the_port_range():
    with _hold_the_top_port():
        # the only legal candidate is busy: hand the preferred port back and
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
    # 70000 is not a port: both searches take their all-busy branch without
    # asking the kernel
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
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native",
                        lambda pid: "")    # WMI fallback path
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    def fake_run(q, **kw):
        assert q[0] == "wmic"
        return types.SimpleNamespace(
            returncode=0,
            stdout="\n\nCommandLine=C:\\r\\.venv\\Scripts\\flubnf.exe app\n\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert (cli._pid_cmdline_windows(1)
            == "C:\\r\\.venv\\Scripts\\flubnf.exe app")


def test_windows_cmdline_falls_back_to_powershell(monkeypatch):
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native",
                        lambda pid: "")    # WMI fallback path
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    def fake_run(q, **kw):
        if q[0] == "wmic":                         # removed on new Win11
            raise FileNotFoundError("wmic not found")
        assert q[0] == "powershell"
        return types.SimpleNamespace(returncode=0, stdout="py.exe -m thing\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cli._pid_cmdline_windows(1) == "py.exe -m thing"


def test_windows_cmdline_empty_result_fails_safe(monkeypatch):
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native",
                        lambda pid: "")    # WMI fallback path
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    # "could not inspect" must come back as '' so the takeover never kills
    # a pid it could not positively identify
    monkeypatch.setattr(
        subprocess, "run",
        lambda q, **kw: types.SimpleNamespace(returncode=1, stdout=""))
    assert cli._pid_cmdline_windows(1) == ""


class _UStr(ctypes.Structure):
    """The UNICODE_STRING header, laid out as the platform lays it out."""
    _fields_ = [("Length", ctypes.c_ushort),
                ("MaximumLength", ctypes.c_ushort),
                ("Buffer", ctypes.c_void_p)]


class _StubNtdll:
    """Emulates NtQueryInformationProcess(ProcessCommandLineInformation):
    a sizing call with no buffer, then a filling call that writes the
    UNICODE_STRING header followed by the UTF-16-LE text, Buffer pointing
    just past the header, as Windows does."""

    def __init__(self, text="C:\\py\\python.exe -m flubnf app", status=0,
                 point_outside=False, size_override=None, fill_first=False):
        self.data = text.encode("utf-16-le")
        self.status = status
        self.point_outside = point_outside
        self.size_override = size_override
        self.fill_first = fill_first            # write a valid answer, THEN fail
        self.classes = []
        # a readable block OUTSIDE the returned buffer, so a missing bounds
        # check fails cleanly instead of reading unmapped memory
        self.elsewhere = ctypes.create_string_buffer(self.data, len(self.data))

    def NtQueryInformationProcess(self, handle, cls, buf, length, need_ref):
        self.classes.append(cls)
        total = ctypes.sizeof(_UStr) + len(self.data)
        if buf is None:
            need_ref._obj.value = (self.size_override
                                   if self.size_override is not None
                                   else total)
            return -1073741820                  # STATUS_INFO_LENGTH_MISMATCH
        if self.status and not self.fill_first:
            return self.status
        base = ctypes.addressof(buf)
        hdr = _UStr.from_buffer(buf)
        hdr.Length = hdr.MaximumLength = len(self.data)
        hdr.Buffer = (ctypes.addressof(self.elsewhere) if self.point_outside
                      else base + ctypes.sizeof(_UStr))
        ctypes.memmove(base + ctypes.sizeof(_UStr), self.data, len(self.data))
        return self.status


class _StubKernel32Open:
    def __init__(self, handle=77, exit_code=259):
        self.handle = handle
        self.exit_code = exit_code              # 259 is STILL_ACTIVE
        self.closed = []
        self.access = []

    def OpenProcess(self, access, inherit, pid):
        self.access.append(access)
        return self.handle

    def GetExitCodeProcess(self, handle, code_ref):
        code_ref._obj.value = self.exit_code
        return 1

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return 1


def test_windows_native_cmdline_reads_the_kernel_record():
    nt, k32 = _StubNtdll(), _StubKernel32Open()
    got = cli._pid_cmdline_windows_native(4242, ntdll=nt, kernel32=k32)
    assert got == "C:\\py\\python.exe -m flubnf app"
    assert nt.classes == [60, 60]               # ProcessCommandLineInformation
    assert k32.access == [0x1000]               # limited query access only
    assert k32.closed == [77]                   # handle released


def test_windows_native_cmdline_decodes_utf16_not_platform_wchar():
    text = "C:\\Users\\Z\u00e9lie\\flubnf.exe app \u6d4b\u8bd5"
    nt, k32 = _StubNtdll(text=text), _StubKernel32Open()
    assert cli._pid_cmdline_windows_native(1, ntdll=nt, kernel32=k32) == text


@pytest.mark.parametrize("nt,why", [
    (_StubNtdll(status=-1073741790), "access denied on the filling call"),
    (_StubNtdll(status=-2147483643, fill_first=True),
     "a full answer written but a failure status returned"),
    (_StubNtdll(point_outside=True), "Buffer outside the returned block"),
    (_StubNtdll(size_override=0), "sizing call reported nothing"),
    (_StubNtdll(size_override=(1 << 20) + 1), "absurd size"),
    (_StubNtdll(text=""), "empty command line"),
])
def test_windows_native_cmdline_fails_safe_to_empty(nt, why):
    k32 = _StubKernel32Open()
    assert cli._pid_cmdline_windows_native(1, ntdll=nt, kernel32=k32) == "", why
    assert k32.closed == [77], why              # handle released either way


def test_windows_native_cmdline_exited_process_is_empty():
    # an exited process stays openable while any handle to it is held; the
    # reader must not query it (psutil's rule), and must release the handle
    nt, k32 = _StubNtdll(), _StubKernel32Open(exit_code=0)
    assert cli._pid_cmdline_windows_native(1, ntdll=nt, kernel32=k32) == ""
    assert nt.classes == [] and k32.closed == [77]


def test_windows_native_cmdline_unopenable_process_is_empty():
    nt, k32 = _StubNtdll(), _StubKernel32Open(handle=0)
    assert cli._pid_cmdline_windows_native(1, ntdll=nt, kernel32=k32) == ""
    assert nt.classes == [] and k32.closed == []


def test_windows_native_cmdline_never_raises():
    class Boom:
        def OpenProcess(self, *a):
            raise OSError("boom")
    assert cli._pid_cmdline_windows_native(1, ntdll=_StubNtdll(),
                                           kernel32=Boom()) == ""


@pytest.mark.skipif(os.name == "nt", reason="asserts the non-Windows answer")
def test_windows_native_cmdline_without_windows_is_empty():
    # no ctypes.WinDLL off Windows: '' and no exception
    assert cli._pid_cmdline_windows_native(os.getpid()) == ""


def _record_wmi(monkeypatch):
    """subprocess.run that records each query and answers distinguishably.
    Recording rather than raising matters: the WMI loop swallows every
    exception, so a raising fake could never fail a test."""
    calls = []

    def fake_run(q, **kw):
        calls.append(q[0])
        return types.SimpleNamespace(returncode=0, stdout="from-wmi\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_windows_cmdline_prefers_native_and_spawns_nothing(monkeypatch):
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native",
                        lambda pid: f"native:{pid}")
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    calls = _record_wmi(monkeypatch)
    assert cli._pid_cmdline_windows(9) == "native:9"
    assert calls == []                          # no wmic, no PowerShell


def test_windows_cmdline_falls_back_to_wmi_for_a_live_process(monkeypatch):
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native", lambda pid: "")
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    calls = _record_wmi(monkeypatch)
    assert cli._pid_cmdline_windows(9) == "from-wmi"
    assert calls == ["wmic"]


def test_windows_cmdline_skips_wmi_for_a_dead_pid(monkeypatch):
    # a stale app.pid or runner entry must not pay a PowerShell start
    monkeypatch.setattr(cli, "_pid_cmdline_windows_native", lambda pid: "")
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: False)
    calls = _record_wmi(monkeypatch)
    assert cli._pid_cmdline_windows(9) == ""
    assert calls == []


@pytest.mark.skipif(os.name != "nt", reason="reads a real Windows process")
def test_windows_native_cmdline_on_a_real_process_is_fast():
    """The native read sees the marker quickly (WMI took >10 s on a cold
    Windows Server 2025 runner, defeating the takeover)."""
    import time
    proc = _spawn_sleeper(MARK)
    try:
        t0 = time.monotonic()
        cmd = cli._pid_cmdline_windows_native(proc.pid)
        took = time.monotonic() - t0
        assert MARK in cmd, cmd
        assert took < 2.0, took
    finally:
        proc.kill()
        proc.wait()
    # Popen still holds the handle, so the pid is not reused; the reader must
    # see the exit code and answer ''
    assert cli._pid_alive_windows(proc.pid) is False
    assert cli._pid_cmdline_windows_native(proc.pid) == ""


# ------------------------------------------------ entry-marker matching

# The server's real command line per platform. The Windows spelling is what
# pip's console-script launcher builds (derived from the binary below).
WINDOWS_APP = r'"C:\py\python.exe"  "C:\repo\.venv\Scripts\flubnf.exe" app'
WINDOWS_SPACE = (r'"C:\Program Files\Python312\python.exe"  '
                 r'"C:\Users\Jane Doe\flubnf\.venv\Scripts\flubnf.exe" window')
POSIX_APP = "/Users/x/flubnf/.venv/bin/python3 /Users/x/flubnf/.venv/bin/flubnf app"
POSIX_WINDOW = "/home/x/flubnf/.venv/bin/python /home/x/flubnf/.venv/bin/flubnf window --port 8711"
# macOS under FluBNF.app's host (scripts/macos/flubnf_host.c): ps shows the
# host's exec line, from the Dock (window) or from FluBNF.command (app)
MAC_HOST_DOCK = ("/Users/x/Documents/GitHub/flubnf/FluBNF.app/Contents/MacOS/FluBNF "
                 "/Users/x/Documents/GitHub/flubnf/.venv/bin/flubnf window")
MAC_HOST_TERMINAL = ("/Users/Jane Doe/flubnf/FluBNF.app/Contents/MacOS/FluBNF "
                     "/Users/Jane Doe/flubnf/.venv/bin/flubnf app")


@pytest.mark.parametrize("cmd", [WINDOWS_APP, WINDOWS_SPACE, POSIX_APP,
                                 POSIX_WINDOW, MAC_HOST_DOCK, MAC_HOST_TERMINAL,
                                 r"C:\repo\.venv\Scripts\flubnf.exe app",
                                 '"C:\\py\\python.exe" "C:\\r\\flubnf.exe"   app'])
def test_entry_markers_match_real_launch_spellings(cmd):
    assert cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd


@pytest.mark.parametrize("cmd", [
    "grep flubnf app.log",                       # a word, not the command
    "/usr/bin/notflubnf app",                     # a different program
    r'"C:\py\python.exe" "C:\r\flubnf.exe" apple',
    "flubnf-app",
    "python -m pytest app/tests",
    "/x/.venv/bin/flubnf doctor",                 # our program, not the app
    "",
])
def test_entry_markers_reject_lookalikes(cmd):
    assert not cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd


def test_the_old_substring_test_missed_the_windows_launch():
    """The bug this matcher fixes, pinned: a substring test never found an
    entry marker in the launcher's quoted command line."""
    assert not any(mk in WINDOWS_APP for mk in cli.APP_ENTRY_MARKERS)
    assert cli._cmdline_has_marker(WINDOWS_APP, cli.APP_ENTRY_MARKERS)


@pytest.mark.parametrize("cmd", [
    "/x/.venv/bin/python /x/.venv/bin/flubnf -v app",
    "/x/.venv/bin/python /x/.venv/bin/flubnf --verbose window --port 8711",
    r'"C:\py\python.exe"  "C:\r\Scripts\flubnf.exe" -v app',
])
def test_the_verbose_flag_may_precede_the_subcommand(cmd):
    assert cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd


@pytest.mark.parametrize("cmd", [
    "/x/bin/flubnf -v doctor",
    "/x/bin/flubnf -v",
    "/x/.venv/bin/flubnf doctor app",             # app is not the subcommand
    "/x/.venv/bin/flubnf -v fit --out window",
    r'"C:\py\python.exe"  "C:\r\flubnf.exe" doctor app',
    "grep flubnf -r app",                         # only the root switches skip
    "rg flubnf -uu app",
])
def test_the_subcommand_must_follow_the_program(cmd):
    assert not cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd


def test_empty_markers_match_nothing_and_do_not_disable_the_rest():
    assert not cli._cmdline_has_marker("/x/flubnf app", ("",))
    assert not cli._cmdline_has_marker("/x/flubnf app", ("   ",))
    assert cli._cmdline_has_marker("/x/flubnf app", ("", "flubnf app"))


def test_windows_file_names_match_without_case(monkeypatch):
    cmd = r'"C:\py\python.exe"  "C:\r\Scripts\FluBNF.EXE" app'
    monkeypatch.setattr(os, "name", "nt")
    assert cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS)
    monkeypatch.setattr(os, "name", "posix")          # case matters there
    assert not cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS)


def test_single_word_markers_match_a_whole_word():
    assert cli._cmdline_has_marker("python -c pass flubnf-test-entry",
                                   ("flubnf-test-entry",))
    assert not cli._cmdline_has_marker("python -c pass flubnf-test-entry-2",
                                       ("flubnf-test-entry",))


def test_takeover_signals_a_windows_launched_predecessor(tmp_path, monkeypatch):
    """The takeover itself reads the quoted Windows spelling, on any
    platform: the command-line read and the signal are faked, the
    decision is real."""
    killed = []
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: WINDOWS_APP)
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    pf = tmp_path / "app.pid"
    pf.write_text("424242")
    assert cli._terminate_predecessor(pf) is True
    assert killed == [424242]
    assert not pf.exists()


def test_takeover_never_signals_its_own_parent(tmp_path, monkeypatch):
    """On Windows the new console's launcher and venv redirector carry the
    entry shape too; a stale app.pid naming a recycled pid that is now one
    of them must not be signalled, or the relaunch kills itself."""
    killed = []
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: WINDOWS_APP)
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    pf = tmp_path / "app.pid"
    pf.write_text(str(os.getppid()))
    assert cli._terminate_predecessor(pf) is False
    assert killed == []
    assert not pf.exists()                         # the stale record goes


def test_takeover_never_signals_any_ancestor(tmp_path, monkeypatch):
    killed = []
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: WINDOWS_APP)
    monkeypatch.setattr(cli, "_ancestor_pids", lambda: {111, 222, 333})
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    pf = tmp_path / "app.pid"
    pf.write_text("222")                           # the launcher, say
    assert cli._terminate_predecessor(pf) is False
    assert killed == []


def test_ancestor_pids_of_this_process_hold_the_parent_not_self():
    anc = cli._ancestor_pids()
    assert os.getppid() in anc
    assert os.getpid() not in anc


def test_ancestor_walk_follows_the_chain_and_stops():
    chain = {10: 9, 9: 8, 8: 7, 7: 0}
    assert cli._ancestor_pids(10, parent_of=chain.get) == {9, 8, 7}
    loop = {10: 9, 9: 8, 8: 9}                     # stale Windows parents
    assert cli._ancestor_pids(10, parent_of=loop.get) == {9, 8}
    back = {10: 9, 9: 10}                          # back to the start
    assert cli._ancestor_pids(10, parent_of=back.get) == {9}
    deep = {n: n - 1 for n in range(1, 1000)}
    assert len(cli._ancestor_pids(999, parent_of=deep.get, limit=5)) == 5

    def boom(pid):
        raise OSError("gone")
    assert cli._ancestor_pids(10, parent_of=boom) == set()


class _StubToolhelp:
    """CreateToolhelp32Snapshot / Process32FirstW / Process32NextW."""

    def __init__(self, rows, snap=55):
        self.rows, self.snap, self.closed, self.i = rows, snap, [], 0

    def CreateToolhelp32Snapshot(self, flags, pid):
        assert flags == 0x2                        # TH32CS_SNAPPROCESS
        return self.snap

    def _fill(self, ref):
        if self.i >= len(self.rows):
            return 0
        e = ref._obj
        e.th32ProcessID, e.th32ParentProcessID = self.rows[self.i]
        self.i += 1
        return 1

    def Process32FirstW(self, snap, ref):
        self.i = 0
        return self._fill(ref)

    def Process32NextW(self, snap, ref):
        return self._fill(ref)

    def CloseHandle(self, h):
        self.closed.append(h)
        return 1


def test_windows_parent_map_reads_the_snapshot():
    k32 = _StubToolhelp([(4, 0), (500, 4), (612, 500)])
    assert cli._windows_parent_map(kernel32=k32) == {4: 0, 500: 4, 612: 500}
    assert k32.closed == [55]


def test_windows_parent_map_fails_to_empty():
    assert cli._windows_parent_map(kernel32=_StubToolhelp([], snap=0)) == {}

    class Boom:
        def CreateToolhelp32Snapshot(self, *a):
            raise OSError("boom")
    assert cli._windows_parent_map(kernel32=Boom()) == {}


@pytest.mark.skipif(os.name == "nt", reason="asserts the non-Windows answer")
def test_windows_parent_map_without_windows_is_empty():
    assert cli._windows_parent_map() == {}


def test_takeover_leaves_a_lookalike_alone(tmp_path, monkeypatch):
    killed = []
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: "grep flubnf app.log")
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    pf = tmp_path / "app.pid"
    pf.write_text("424242")
    assert cli._terminate_predecessor(pf) is False
    assert killed == []


def _launcher_formats():
    """The wide format strings in pip's vendored Windows console-script
    launcher that splice in the script path, or None when pip's vendored
    distlib or its launcher is not installed."""
    import re
    try:
        from pip._vendor import distlib
    except Exception:
        return None
    exe = Path(distlib.__file__).parent / "t64.exe"
    if not exe.is_file():
        return None
    data = exe.read_bytes()
    out = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){4,}", data):
        s = m.group().decode("utf-16-le")
        if s.count("%ls") == 4:
            out.append(s)
    return out


def test_markers_match_what_pips_windows_launcher_builds():
    """Build the server's command line from the format string inside pip's
    launcher binary (Python's % ignores the 'l' modifier) and match it."""
    fmts = _launcher_formats()
    if not fmts:
        pytest.skip("pip's vendored distlib launcher is not available")
    assert fmts == ['"%ls" %ls "%ls" %ls'], fmts
    for sub in ("app", "window"):
        cmd = fmts[0] % (r"C:\py\python.exe", "",
                         r"C:\repo\.venv\Scripts\flubnf.exe", sub)
        assert cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd
        assert not any(mk in cmd for mk in cli.APP_ENTRY_MARKERS), cmd


@pytest.mark.skipif(os.name != "nt",
                    reason="builds and runs a real Windows console-script launcher")
@pytest.mark.parametrize("interpreter", ["base", "venv"])
def test_takeover_recognises_a_real_windows_console_script_launch(tmp_path,
                                                                   interpreter):
    """End to end on Windows: a pip-built flubnf.exe started the way
    FluBNF.bat does; the takeover recognises and signals the Python process
    behind it, and the launcher exits 15 (FluBNF.bat's takeover code)."""
    import time
    scripts = pytest.importorskip("pip._vendor.distlib.scripts")
    (tmp_path / "flubnf_takeover_probe.py").write_text(
        "import os, time\n"
        "def main():\n"
        "    with open(os.environ['FLUBNF_PROBE_PIDOUT'], 'w') as f:\n"
        "        f.write(str(os.getpid()))\n"
        "    time.sleep(60)\n")
    bindir = tmp_path / "Scripts"
    bindir.mkdir()
    maker = scripts.ScriptMaker(None, str(bindir))
    maker.variants = {""}
    if interpreter == "venv":
        # production chain: flubnf.exe -> venv python.exe redirector -> base
        # interpreter; the server is that grandchild
        venv = tmp_path / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                        str(venv)], check=True, timeout=120)
        maker.executable = str(venv / "Scripts" / "python.exe")
    maker.make("flubnf = flubnf_takeover_probe:main")
    exe = bindir / "flubnf.exe"
    assert exe.is_file(), sorted(os.listdir(bindir))
    pidout = tmp_path / "server.pid"
    env = dict(os.environ, PYTHONPATH=str(tmp_path),
               FLUBNF_PROBE_PIDOUT=str(pidout))
    launcher = subprocess.Popen('cmd /d /c "Scripts\\flubnf" app',
                                cwd=str(tmp_path), env=env)
    pid = None
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if pidout.is_file() and pidout.read_text().strip():
                pid = int(pidout.read_text().strip())
                break
            assert launcher.poll() is None, "the launcher exited early"
            time.sleep(0.1)
        assert pid is not None, "the probe never recorded its pid"
        cmd = cli._pid_cmdline(pid)
        assert cli._cmdline_has_marker(cmd, cli.APP_ENTRY_MARKERS), cmd
        pf = tmp_path / "app.pid"
        pf.write_text(str(pid))
        assert cli._terminate_predecessor(pf) is True, cmd
        deadline = time.monotonic() + 10
        while cli._pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not cli._pid_alive(pid), "the server survived the takeover"
        assert launcher.wait(timeout=30) == 15, (
            "FluBNF.bat treats 15 as a takeover; the launcher chain returned "
            "something else")
    finally:
        if pid is not None and cli._pid_alive(pid):
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        if launcher.poll() is None:
            # launcher is cmd.exe: kill the whole tree
            subprocess.run(["taskkill", "/PID", str(launcher.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
            if launcher.poll() is None:
                launcher.kill()
        launcher.wait(timeout=10)


def test_pid_helpers_dispatch_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(cli, "_pid_cmdline_windows", lambda pid: f"win:{pid}")
    monkeypatch.setattr(cli, "_pid_alive_windows", lambda pid: True)
    assert cli._pid_cmdline(7) == "win:7"
    assert cli._pid_alive(7) is True


# ------------------------------------------------ window activation (macOS)

class _FakeNSWindow:
    def __init__(self):
        self.front = 0

    def isVisible(self):
        return True

    def makeKeyAndOrderFront_(self, sender):
        self.front += 1

    def orderFrontRegardless(self):
        pass


class _FakeNSApp:
    """NSApplication as macOS 14 treats a process Terminal launched: it
    becomes active only on the request numbered `grant_on` (None: never),
    the way cooperative activation can decline requests."""

    def __init__(self, grant_on=1, has_activate=True):
        self.grant_on = grant_on
        self.requests = 0
        self.modern = 0
        self.legacy = 0
        self.active = False
        self.win = _FakeNSWindow()
        self.has_activate = has_activate

    def setActivationPolicy_(self, p):
        pass

    def respondsToSelector_(self, sel):
        return sel == "activate" and self.has_activate

    def activate(self):
        self.modern += 1

    def activateIgnoringOtherApps_(self, flag):
        self.legacy += 1
        self.requests += 1
        if self.grant_on is not None and self.requests >= self.grant_on:
            self.active = True

    def windows(self):
        return [self.win]

    def isActive(self):
        return self.active

    def keyWindow(self):
        return self.win if self.active else None


def _fake_appkit(app):
    running = types.SimpleNamespace(activateWithOptions_=lambda o: True)
    return types.SimpleNamespace(
        NSApplication=types.SimpleNamespace(sharedApplication=lambda: app),
        NSRunningApplication=types.SimpleNamespace(
            currentApplication=lambda: running),
        NSApplicationActivationPolicyRegular=0,
        NSApplicationActivateAllWindows=1)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_activation_stops_at_the_first_granted_request(monkeypatch, tmp_path):
    trace = tmp_path / "trace.txt"
    monkeypatch.setenv("FLUBNF_STARTUP_TRACE", str(trace))
    app, clock = _FakeNSApp(grant_on=1), _Clock()
    ok = cli._bring_window_forward(_fake_appkit(app), lambda f: f(),
                                   sleep=clock.sleep, clock=clock)
    assert ok and app.requests == 1
    # the macOS 14 request is made, not only the deprecated one
    assert app.modern == 1 and app.win.front == 1
    assert "activation request 1 at +0.0s: active=True" in trace.read_text()


def test_activation_is_retried_until_macos_grants_it(monkeypatch, tmp_path):
    trace = tmp_path / "trace.txt"
    monkeypatch.setenv("FLUBNF_STARTUP_TRACE", str(trace))
    app, clock = _FakeNSApp(grant_on=4), _Clock()
    ok = cli._bring_window_forward(_fake_appkit(app), lambda f: f(),
                                   sleep=clock.sleep, clock=clock)
    assert ok and app.requests == 4
    assert clock.t == cli.ACTIVATE_DELAYS[3]
    text = trace.read_text()
    assert "activation request 3" in text and "active=False" in text
    assert "activation request 4 at +2.0s: active=True" in text


def test_a_declined_activation_is_watched_and_traced(monkeypatch, tmp_path):
    trace = tmp_path / "trace.txt"
    monkeypatch.setenv("FLUBNF_STARTUP_TRACE", str(trace))
    app, clock = _FakeNSApp(grant_on=None), _Clock()
    appkit = _fake_appkit(app)

    def sleep(s):
        clock.sleep(s)
        if clock.t >= 64.0:         # the user switches away and back
            app.active = True
    ok = cli._bring_window_forward(appkit, lambda f: f(),
                                   sleep=sleep, clock=clock)
    assert not ok
    assert app.requests == len(cli.ACTIVATE_DELAYS)
    text = trace.read_text()
    assert "macOS declined every activation request" in text
    assert "app became active at +64.0s (not by request)" in text


def test_activation_without_the_macos_14_call(monkeypatch, tmp_path):
    # an older macOS: NSApplication has no activate; the legacy call alone
    monkeypatch.delenv("FLUBNF_STARTUP_TRACE", raising=False)
    app, clock = _FakeNSApp(grant_on=1, has_activate=False), _Clock()
    assert cli._bring_window_forward(_fake_appkit(app), lambda f: f(),
                                     sleep=clock.sleep, clock=clock)
    assert app.modern == 0 and app.legacy == 1
