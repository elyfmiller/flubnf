"""A model page takes a lock check left by an earlier page only while it
is fresh (the re-check of #93 at 099907c, finding 8;
app/core/engines/lwf.py lock_check_soon).

A page waits a few seconds for the public engine's lock check and, with
no answer yet, says nothing and leaves the check's slot. The next look
took that slot's answer however old it was: a venv repaired since then
still read as not matching the lock. P2-3 kept the startup warm from
leaving a slot; a page's own slot is now stamped when its answer comes
and dropped once lwf.CHECK_TTL_S old, as lock_check's own store is.

No real check runs: the engine_lock.py process is counted and answered.
"""
from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from app.core.engines import lwf


@pytest.fixture
def check(monkeypatch):
    """The public venv's Python here, nothing remembered, and the lock
    check's process answered by answer[0] ((returncode, line)) once
    `release` is set: (answer, release, the commands run)."""
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    monkeypatch.setattr(lwf, "_CHECK", {})
    monkeypatch.setattr(lwf, "_PENDING", {})
    answer = [(1, "! bngsim 0.14 is not the lock's 0.15")]
    release = threading.Event()
    ran = []

    def run(cmd, **kw):
        assert any(str(c).endswith("engine_lock.py") for c in cmd), cmd
        ran.append(list(cmd))
        release.wait(60)
        code, line = answer[0]
        return subprocess.CompletedProcess(cmd, code, line + "\n", "")
    monkeypatch.setattr(lwf.subprocess, "run", run)
    yield answer, release, ran
    release.set()
    _join()


def _join():
    for t in [t for t in threading.enumerate()
              if t.name == "flubnf-public-lock-check"]:
        t.join(30)
        assert not t.is_alive()


def _started(ran, n=1):
    """Wait until n checks have reached their process (on their thread)."""
    gate = threading.Event()
    for _ in range(3000):
        if len(ran) >= n:
            return
        gate.wait(0.01)
    raise AssertionError(f"{len(ran)} checks started, not {n}")


def _page_stops_waiting(release):
    """A page that gives up before the answer: its slot stays, and the
    answer lands in it afterwards."""
    assert lwf.lock_check_soon(0) is None
    release.set()
    _join()
    (slot,) = lwf._PENDING.values()
    assert slot["done"].is_set()
    return slot


def _age(seconds):
    """Every answer, the slot's and lock_check's store's, `seconds` older."""
    for slot in lwf._PENDING.values():
        slot["at"] = slot.get("at", lwf.time.time()) - seconds
    lwf._CHECK["at"] -= seconds


def test_a_slot_older_than_the_check_ttl_is_asked_again(check):
    answer, release, ran = check
    _page_stops_waiting(release)
    # the venv is repaired; the answer the first page left is past its time
    answer[0] = (0, "ok: matches")
    _age(lwf.CHECK_TTL_S + 1)
    got = lwf.lock_check_soon(30)
    assert got == (True, "ok: matches"), "the page took the old answer"
    assert len(ran) == 2
    assert lwf._PENDING == {}


def test_within_the_check_ttl_the_left_answer_is_taken(check):
    """The control: a fresh slot is the next page's answer, and no second
    check is started."""
    answer, release, ran = check
    _page_stops_waiting(release)
    answer[0] = (0, "ok: matches")
    _age(lwf.CHECK_TTL_S - 30)
    assert lwf.lock_check_soon(30) == (
        False, "bngsim 0.14 is not the lock's 0.15")
    assert len(ran) == 1
    assert lwf._PENDING == {}


def test_a_check_still_running_is_waited_for_not_restarted(check):
    """A slot whose answer has not come has no age: a page waits on it."""
    answer, release, ran = check
    assert lwf.lock_check_soon(0) is None
    (slot,) = lwf._PENDING.values()
    _started(ran)
    slot["at"] = slot.get("at", 0.0) - (lwf.CHECK_TTL_S + 1)  # no answer
    assert lwf.lock_check_soon(0) is None
    assert list(lwf._PENDING.values()) == [slot]
    release.set()
    assert lwf.lock_check_soon(30) == (
        False, "bngsim 0.14 is not the lock's 0.15")
    assert len(ran) == 1
