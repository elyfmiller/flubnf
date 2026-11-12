"""The Sandbox's startup warm never waits, and leaves nothing a later look
takes however old (review 3 of #93, part 2: P2-3 and P2-5).

  * P2-5: sandbox.warm_probes returns while a probe it started is still
    running, on either engine. A wait with a time limit would return too,
    later, so every wait with a positive limit is made to last until its
    probe ends: a warm that waits then never returns while the probe is
    held, and the test sees it (no wall-clock bound to be flaky).
  * P2-3: on the public engine the warm's lock check fills only the
    timed store (lwf.lock_check, lwf.CHECK_TTL_S): no lwf.lock_check_soon
    slot is left for the first model page to take whatever its age, so a
    venv repaired since launch reads as repaired once the store is old.

No probe is real: test_sandbox_warm's fixtures count them.
"""
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import lwf                         # noqa: E402

from test_sandbox_warm import MODEL, client, probes      # noqa: E402,F401

#: Event.wait as written
REAL_WAIT = threading.Event.wait
#: how long a warm that does not wait may take to return here (a
#: computer stalled this long fails the test; a warm that waits never
#: returns within it while its probe is held)
RETURN_S = 20.0


@pytest.fixture
def patient(monkeypatch):
    """Every Event.wait with a positive time limit waits with none, so a
    wait for a held probe lasts until the probe is let go. wait(0), which
    only looks, is unchanged."""
    def wait(self, timeout=None):
        return REAL_WAIT(self, None if timeout is not None and timeout > 0
                         else timeout)
    monkeypatch.setattr(threading.Event, "wait", wait)


def _warm_returns() -> bool:
    """warm_probes on a thread: whether it returned within RETURN_S."""
    t = threading.Thread(target=sb.warm_probes, daemon=True,
                         name="test-warm")
    t.start()
    t.join(RETURN_S)
    return not t.is_alive()


def _join(prefix: str) -> None:
    for t in [t for t in threading.enumerate() if t.name.startswith(prefix)]:
        t.join(30)
        assert not t.is_alive(), t.name


def test_the_warm_returns_while_the_engine_import_probe_is_held(
        probes, patient, monkeypatch):
    release = threading.Event()
    counted = sb._probe_run

    def held(cmd, **kw):
        if cmd[1] == "-c":                      # the engine-import probe
            REAL_WAIT(release, 60)
        return counted(cmd, **kw)
    monkeypatch.setattr(sb, "_probe_run", held)
    try:
        returned = _warm_returns()
        (slot,) = sb._ENGINE_PROBES.values()
        running = not slot["done"].is_set()
    finally:
        release.set()
    _join("flubnf-engine-probe")
    assert returned, "the warm waited for the engine-import probe"
    assert running                              # it was still held
    # BNG2.pl's self-test ran on the warm's thread, the import probe after
    assert sorted(c[1] for c in probes) == sorted(["-c", sb.BNG])


def _public(monkeypatch, answers: list) -> list:
    """The public engine with its venv's Python here, its lock check's
    process counted (a list of argv) and answered by answers[0]
    ((returncode, line)), nothing remembered."""
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", sys.executable)
    monkeypatch.setattr(lwf, "_CHECK", {})
    monkeypatch.setattr(lwf, "_PENDING", {})
    checks = []

    def run(cmd, **kw):
        if any(str(c).endswith("engine_lock.py") for c in cmd):
            checks.append(list(cmd))
            code, line = answers[0]
            return subprocess.CompletedProcess(cmd, code, line + "\n", "")
        raise AssertionError(f"an unexpected process: {cmd}")
    monkeypatch.setattr(lwf.subprocess, "run", run)
    return checks


def test_the_warm_returns_while_the_lock_check_is_held(probes, patient,
                                                       monkeypatch):
    release = threading.Event()
    checks = _public(monkeypatch, [(0, "ok: matches")])
    answer = lwf.subprocess.run

    def held(cmd, **kw):
        REAL_WAIT(release, 60)
        return answer(cmd, **kw)
    monkeypatch.setattr(lwf.subprocess, "run", held)
    try:
        returned = _warm_returns()
        running = [t for t in threading.enumerate()
                   if t.name.startswith("flubnf-public-lock-check")
                   and t.is_alive()]
    finally:
        release.set()
    _join("flubnf-public-lock-check")
    assert returned, "the warm waited for the lock check"
    assert running and len(checks) == 1


def test_the_warm_leaves_no_lock_check_for_a_page_to_take_stale(
        probes, monkeypatch):
    # launched with the public venv not matching the lock
    answers = [(1, "! bngsim 0.14 is not the lock's 0.15")]
    checks = _public(monkeypatch, answers)
    sb.warm_probes()
    _join("flubnf-public-lock-check")
    assert len(checks) == 1
    assert lwf._PENDING == {}                   # no slot parked
    assert lwf._CHECK["result"][0] is False     # the timed store has it
    # repaired in place; the answer from launch is past its time
    answers[0] = (0, "ok: matches")
    lwf._CHECK["at"] -= lwf.CHECK_TTL_S + 1
    sb.add_example("kinetics_example")
    html = client.get(MODEL).text
    _join("flubnf-public-lock-check")
    assert 'id="sb-machine"' not in html, "the first page took the old answer"
    assert len(checks) == 2


def test_within_its_time_the_warms_answer_is_the_pages(probes, monkeypatch):
    """The control: a page within lwf.CHECK_TTL_S of the warm reads its
    answer and starts no check of its own."""
    answers = [(1, "! bngsim 0.14 is not the lock's 0.15")]
    checks = _public(monkeypatch, answers)
    sb.warm_probes()
    _join("flubnf-public-lock-check")
    sb.add_example("kinetics_example")
    html = client.get(MODEL).text
    _join("flubnf-public-lock-check")
    assert 'id="sb-machine"' in html and "does not match" in html
    assert len(checks) == 1
