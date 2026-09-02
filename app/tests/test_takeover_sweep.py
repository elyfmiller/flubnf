"""The console takeover sweeps orphaned PF runner groups (flubnf/cli.py).

The runners are plain Popen children supervised from daemon threads: a
takeover or window close kills the server without any supervisor's finally
block, the fits keep running unowned, and once the heartbeat goes stale a
resumed run fits the same cells concurrently. Each runner therefore leads
its own process group, is recorded in a registry beside app.pid, and the
relaunch sweeps the recorded groups after signalling the server. Same
safety rule as the pidfile takeover: a pid whose live command line no
longer names its recorded runner script is never signalled, because a
recycled pid must never get the treatment.

Like test_app_launch.py, these tests run against real spawned processes: a
marked fake runner leading its own group (with a child, so the GROUP
signal is what is proven) and an unmarked bystander.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flubnf import cli                                    # noqa: E402

MARKER = "pf_runner_0.py"

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="the sweep's group signalling is POSIX "
    "(killpg); Windows goes through taskkill /T, which needs a real "
    "Windows box")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _spawn_group(tmp_path, marked=True):
    """A process leading its own group, with one child in that group. The
    marker rides in argv so the recorded runner script matches (or, for
    the bystander, does not match) the live command line."""
    pidfile = tmp_path / f"child_{marked}.pid"
    code = ("import subprocess, sys, time\n"
            "g = subprocess.Popen([sys.executable, '-c',"
            " 'import time; time.sleep(120)'])\n"
            f"open({str(pidfile)!r}, 'w').write(str(g.pid))\n"
            "time.sleep(120)\n")
    argv = [sys.executable, "-c", code] + ([MARKER] if marked else [])
    p = subprocess.Popen(argv, start_new_session=True)
    deadline = time.time() + 10
    while time.time() < deadline and not pidfile.is_file():
        time.sleep(0.05)
    child = int(pidfile.read_text())
    return p, child


def _registry(tmp_path, *pids, runner=f"/w/{MARKER}"):
    reg = tmp_path / "pf_runners.json"
    reg.write_text(json.dumps({str(p): {"pgid": p, "runner": runner}
                               for p in pids}))
    return reg


def _reap(proc, *pids):
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    except Exception:
        pass
    for p in pids:
        try:
            os.kill(p, 9)
        except OSError:
            pass


def test_sweep_terminates_the_recorded_group_child_included(tmp_path):
    proc, child = _spawn_group(tmp_path)
    reg = _registry(tmp_path, proc.pid)
    try:
        assert cli._sweep_runner_groups(reg, wait=1.0) == 1
        assert proc.wait(10) != 0              # the leader was signalled
        deadline = time.time() + 10
        while time.time() < deadline and _alive(child):
            time.sleep(0.1)
        assert not _alive(child)               # the GROUP took the child too
        assert not reg.exists()                # the registry is cleared
    finally:
        _reap(proc, child)


def test_sweep_leaves_a_recycled_pid_alone(tmp_path):
    """The registry entry is stale and its pid now belongs to a process
    whose command line never mentions the runner script: untouched."""
    proc, child = _spawn_group(tmp_path, marked=False)
    reg = _registry(tmp_path, proc.pid)
    try:
        assert cli._sweep_runner_groups(reg, wait=0.2) == 0
        assert proc.poll() is None             # alive and untouched
        assert _alive(child)
        assert not reg.exists()                # the stale record still clears
    finally:
        _reap(proc, child)


def test_sweep_survives_garbage_dead_pids_and_an_absent_registry(tmp_path):
    assert cli._sweep_runner_groups(tmp_path / "absent.json") == 0
    reg = tmp_path / "pf_runners.json"
    reg.write_text("not json")
    assert cli._sweep_runner_groups(reg) == 0
    assert not reg.exists()
    # a dead pid: recorded, but its command line is gone
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    reg2 = _registry(tmp_path, gone.pid)
    assert cli._sweep_runner_groups(reg2) == 0
    assert not reg2.exists()


def test_default_takeover_sweeps_the_default_registry(tmp_path, monkeypatch):
    """The production call is _terminate_predecessor() with no arguments,
    and it must sweep even when no pidfile exists: a clean server exit
    removes app.pid while a window close still orphans the runners."""
    monkeypatch.setattr(cli, "APP_PID_FILE", tmp_path / "app.pid")
    monkeypatch.setattr(cli, "PF_RUNNER_PIDS_FILE",
                        tmp_path / "pf_runners.json")
    proc, child = _spawn_group(tmp_path)
    _registry(tmp_path, proc.pid)
    try:
        assert cli._terminate_predecessor(wait=1.0) is False   # no pidfile
        assert proc.wait(10) != 0
        deadline = time.time() + 10
        while time.time() < deadline and _alive(child):
            time.sleep(0.1)
        assert not _alive(child)
        assert not (tmp_path / "pf_runners.json").exists()
    finally:
        _reap(proc, child)


def test_an_injected_pidfile_sweeps_nothing(tmp_path, monkeypatch):
    """A caller probing a private pidfile (every takeover test does) must
    not reclaim the real console's fits: without an explicit registry the
    sweep does not run at all."""
    monkeypatch.setattr(cli, "PF_RUNNER_PIDS_FILE",
                        tmp_path / "pf_runners.json")
    proc, child = _spawn_group(tmp_path)
    reg = _registry(tmp_path, proc.pid)
    try:
        assert cli._terminate_predecessor(tmp_path / "other.pid") is False
        assert proc.poll() is None             # untouched
        assert reg.is_file()                   # and still recorded
    finally:
        _reap(proc, child)
