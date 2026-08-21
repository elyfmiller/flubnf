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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import cli                                    # noqa: E402

MARK = "flubnf-test-entry"


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
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        busy = s.getsockname()[1]
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
    assert cli._window_watchdog(w, "http://x", wait=0.05) == "loaded"
    assert w.load_url_calls == []
    assert w.load_html_calls == []


def test_watchdog_reloads_a_dead_window_once():
    w = _FakeWindow(loads_on_call=1)
    assert cli._window_watchdog(w, "http://x", wait=0.05) == "recovered"
    assert w.load_url_calls == ["http://x"]
    assert w.load_html_calls == []


def test_watchdog_shows_failure_page_after_all_retries():
    w = _FakeWindow(loads_on_call=None)
    assert cli._window_watchdog(w, "http://x", wait=0.05) == "failed"
    assert len(w.load_url_calls) == 3              # 3 retries, then give up
    assert len(w.load_html_calls) == 1
    assert "did not start" in w.load_html_calls[0]
    assert "relaunch" in w.load_html_calls[0]


def test_watchdog_catches_load_event_fired_between_attach_and_wait():
    # loaded fired before the handler attached: is_set covers the race
    w = _FakeWindow()
    w.events.loaded._set = True
    assert cli._window_watchdog(w, "http://x", wait=0.05) == "loaded"
    assert w.load_url_calls == []
