"""The engine cache's registry lock, its warning, and its clear (review of
#93 at 3120298e, findings 1, 2 and 5).

  1. a registry lock the volume refuses (flock failing with ENOLCK or
     ENOTSUP, as on some network mounts) is gone ahead without at once;
     only a lock another process holds (EWOULDBLOCK, EAGAIN, or EACCES on
     Windows) is waited for. Each record and unrecord waited 5 s per
     registry: 10 s each;
  2. the cache warning is said on the error output before it is written
     to the state folder, so a state folder that takes no file still has
     it said (once in the process); and a launch whose environment names a
     folder of its own in BNGSIM_CODEGEN_CACHE_DIR says and keeps nothing,
     and leaves a warning kept from before for the launches that still use
     the state folder's cache (review of #93 at d5a7eb16, finding 4);
  5. reclaim.clear_codegen_cache keeps a protected cache folder and a
     linked one by itself, not only behind the route's own refusal.

Nothing here runs bngsim or changes a forecast, score or record.
"""
import errno
import json
import os
import shutil
import threading
import time
import types

import pytest

from app.core import reclaim
from app.core.engines import pf

from test_cache_and_runners import (                   # noqa: E402
    OWN, POSIX_USER, VAR, _blocked, _fill, client, state)

try:
    import fcntl
except ImportError:                     # Windows: msvcrt.locking instead
    fcntl = None
FLOCK = pytest.mark.skipif(fcntl is None, reason="flock is POSIX's")


@pytest.fixture(autouse=True)
def fresh_word(monkeypatch):
    """No word said yet in this process (pf._CODEGEN_SAID). raising=False:
    on a tree without it, each test fails for its own reason, not here
    (review of #93 at d5a7eb16, finding 3)."""
    monkeypatch.setattr(pf, "_CODEGEN_SAID", {}, raising=False)


def _runner(pid: int):
    return types.SimpleNamespace(pid=pid,
                                 args=["py", f"/w/pf_runner_{pid}.py"])


# ------------------------------------------- 1. a lock the volume refuses

def _flock_failing(monkeypatch, err: int, times: int | None = None) -> list:
    """flock's exclusive lock fails with `err` (every time, or the first
    `times` tries); unlocking is flock's own. The tries are counted."""
    real = fcntl.flock
    tries = []

    def flock(fd, op):
        if op & fcntl.LOCK_EX:
            tries.append(op)
            if times is None or len(tries) <= times:
                raise OSError(err, os.strerror(err))
        return real(fd, op)
    monkeypatch.setattr(fcntl, "flock", flock)
    return tries


@FLOCK
@pytest.mark.parametrize("err", [errno.ENOLCK, errno.EOPNOTSUPP],
                         ids=["ENOLCK", "EOPNOTSUPP"])
def test_a_volume_that_refuses_locks_is_gone_ahead_without_at_once(
        state, tmp_path, monkeypatch, err):
    reg = tmp_path / "pf_runners.json"
    tries = _flock_failing(monkeypatch, err)
    me = _runner(os.getpid())
    t0 = time.monotonic()
    pf.record_runner_pids([me], path=reg)
    recorded = time.monotonic() - t0
    assert set(json.loads(reg.read_text())) == {str(os.getpid())}
    assert set(json.loads(pf.codegen_holders_file().read_text())) == {
        str(os.getpid())}
    t0 = time.monotonic()
    pf.unrecord_runner_pids([me], path=reg)
    unrecorded = time.monotonic() - t0
    assert json.loads(reg.read_text()) == {}
    assert json.loads(pf.codegen_holders_file().read_text()) == {}
    # one try per registry (its own and the cache's holders), each way:
    # it waited out REGISTRY_LOCK_WAIT_S on each, about 10 s each way
    assert len(tries) == 4
    assert recorded < 1.0 and unrecorded < 1.0


@FLOCK
@pytest.mark.parametrize("err", [errno.EWOULDBLOCK, errno.EAGAIN,
                                 errno.EACCES],
                         ids=["EWOULDBLOCK", "EAGAIN", "EACCES"])
def test_a_lock_another_holds_is_still_waited_for(tmp_path, monkeypatch, err):
    fd = os.open(str(tmp_path / "r.json.lock"), os.O_RDWR | os.O_CREAT)
    try:
        tries = _flock_failing(monkeypatch, err, times=3)
        assert pf._lock_file(fd, 5.0) is True and len(tries) == 4
        pf._unlock_file(fd)
        tries = _flock_failing(monkeypatch, err)
        t0 = time.monotonic()
        assert pf._lock_file(fd, 0.3) is False
        assert time.monotonic() - t0 >= 0.3 and len(tries) > 3
    finally:
        os.close(fd)


@FLOCK
def test_a_lock_another_descriptor_holds_is_waited_for_then_had(tmp_path):
    """The real flock, no stand-in: held by another open file, waited for,
    and had once it is let go."""
    path = str(tmp_path / "r.json.lock")
    a = os.open(path, os.O_RDWR | os.O_CREAT)
    b = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        assert pf._lock_file(a, 1.0) is True
        t0 = time.monotonic()
        assert pf._lock_file(b, 0.3) is False
        assert time.monotonic() - t0 >= 0.3
        threading.Timer(0.2, pf._unlock_file, args=(a,)).start()
        assert pf._lock_file(b, 5.0) is True
    finally:
        os.close(a)
        os.close(b)


# ----------------------------------------- 2. said first, then written

def test_a_word_the_state_folder_cannot_keep_is_still_said_once(
        state, monkeypatch, capsys):
    _blocked(state)

    def cannot(path, reg):
        raise PermissionError(errno.EACCES, "Permission denied", str(path))
    monkeypatch.setattr(pf, "_write_registry", cannot)
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert VAR not in kw["env"]
    err = capsys.readouterr().err
    assert err.count("could not write the engine cache folder") == 1
    assert str(state["cache"]) in err and OWN in err
    # not kept, so not on Storage; said once however many runners start
    assert pf.codegen_cache_warning() == ""
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert capsys.readouterr().err == ""
    # fixed, then broken again: said again
    (state["root"] / "engine-cache").unlink()
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert kw["env"][VAR] == str(state["cache"])
    shutil.rmtree(state["root"] / "engine-cache")
    _blocked(state)
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert capsys.readouterr().err.count("could not write") == 1


@pytest.mark.skipif(not POSIX_USER, reason="POSIX permissions, not as root")
def test_a_read_only_state_folder_still_has_the_word_said(state, capsys):
    """The review's case: the state folder and the cache folder both
    read-only. Nothing reached the error output, and nothing Storage."""
    root = state["root"]
    root.chmod(0o555)
    try:
        kw = pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
        assert VAR not in kw["env"]
        err = capsys.readouterr().err
        assert err.count("could not write the engine cache folder") == 1
        assert "PermissionError" in err
        assert not (root / pf.CODEGEN_PROBLEM_NAME).exists()
    finally:
        root.chmod(0o755)


def test_a_folder_the_user_sets_leaves_the_word_kept_on_ours(
        state, tmp_path, capsys):
    """A runner given a folder of its own (the Sandbox passes its own
    environment): nothing said or kept for it, and the word kept on ours
    stays for this console's other launches, which still use ours."""
    block = _blocked(state)
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    kept = state["root"] / pf.CODEGEN_PROBLEM_NAME
    before = kept.read_bytes()
    assert 'id="st-ec-warn"' in client.get("/storage").text
    capsys.readouterr()
    theirs = tmp_path / "theirs" / "codegen"
    kw = pf.runner_popen_kwargs({}, _os_name="posix",
                                env={"PATH": "x", VAR: str(theirs)})
    assert kw["env"][VAR] == str(theirs) and not theirs.exists()
    assert capsys.readouterr().err == ""
    assert kept.read_bytes() == before
    assert "could not write" in pf.codegen_cache_warning()
    assert 'id="st-ec-warn"' in client.get("/storage").text
    # the next launch with ours, still blocked: kept, so not said again
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    assert capsys.readouterr().err == ""
    assert kept.read_bytes() == before
    assert block.is_file()                    # ours neither made nor fixed


def test_a_terminal_launch_with_its_own_folder_leaves_the_console_its_word(
        state, tmp_path, monkeypatch, capsys):
    """The review's case (#93 at d5a7eb16, finding 4), in one process: the
    console's cache folder cannot be written and Storage says so; a
    terminal replay on the same state folder, BNGSIM_CODEGEN_CACHE_DIR
    exported, starts a runner. The word is one per state folder: it stays,
    and the console, whose environment names no folder, still says it."""
    block = _blocked(state)
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    kept = state["root"] / pf.CODEGEN_PROBLEM_NAME
    before = kept.read_bytes()
    assert 'id="st-ec-warn"' in client.get("/storage").text
    capsys.readouterr()
    # the terminal: its own environment names a folder
    theirs = tmp_path / "theirs" / "codegen"
    monkeypatch.setenv(VAR, str(theirs))
    kw = pf.runner_popen_kwargs({}, _os_name="posix")
    assert kw["env"][VAR] == str(theirs) and not theirs.exists()
    assert capsys.readouterr().err == ""          # nothing said for it
    assert pf.codegen_cache_warning() == ""       # nor shown where it runs
    assert kept.read_bytes() == before            # kept as it was
    # the console: no folder of its own, so Storage still says it
    monkeypatch.delenv(VAR)
    assert "could not write" in pf.codegen_cache_warning()
    assert 'id="st-ec-warn"' in client.get("/storage").text
    assert block.is_file()


def test_storage_leaves_the_word_out_while_the_user_names_a_folder(
        state, tmp_path, monkeypatch):
    """Set before the console starts, no runner launched yet: the word kept
    from an earlier launch is not this console's runners'."""
    _blocked(state)
    pf.runner_popen_kwargs({}, _os_name="posix", env={"PATH": "x"})
    kept = state["root"] / pf.CODEGEN_PROBLEM_NAME
    assert kept.is_file()
    monkeypatch.setenv(VAR, str(tmp_path / "theirs"))
    assert pf.codegen_cache_warning() == ""
    assert 'id="st-ec-warn"' not in client.get("/storage").text
    monkeypatch.setenv(VAR, "  ")             # blank reads as unset
    assert "could not write" in pf.codegen_cache_warning()
    assert kept.is_file()


# ------------------------------- 5. clear_codegen_cache, without the route

@pytest.mark.parametrize("which", ["state", "cache"])
def test_clear_keeps_a_protected_cache_by_itself(state, monkeypatch, which):
    """Protected by the state folder, or by its own path: refused, every
    byte kept, nothing set aside (with the cache's own path protected, the
    folder set aside is outside it, and was deleted)."""
    b = _fill(state["cache"])
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS",
                       str(state["root"] if which == "state"
                           else state["cache"]))
    out = reclaim.clear_codegen_cache(registries=[])
    assert out == {"bytes": 0, "busy": False,
                   "refused": "the engine cache's folder is protected"}
    assert reclaim.codegen_cache_bytes() == b
    assert sorted(p.name for p in state["cache"].parent.iterdir()) == [
        "bngsim-codegen"]


@pytest.mark.skipif(os.name != "posix", reason="a symlink needs POSIX here")
def test_clear_leaves_a_linked_cache_where_it_is_by_itself(state, tmp_path):
    """A linked cache with a folder an earlier clear set aside: the folder
    set aside goes, the link and what it leads to stay."""
    elsewhere = tmp_path / "other-disk" / "codegen"
    kept = _fill(elsewhere, n=2)
    state["cache"].parent.mkdir(parents=True)
    state["cache"].symlink_to(elsewhere, target_is_directory=True)
    aside = state["cache"].with_name(
        f"bngsim-codegen{reclaim.CODEGEN_ASIDE}1-2")
    b = _fill(aside, n=1)
    out = reclaim.clear_codegen_cache(registries=[])
    assert out == {"bytes": b, "refused": "", "busy": False}
    assert state["cache"].is_symlink()
    assert os.path.realpath(state["cache"]) == os.path.realpath(elsewhere)
    assert sorted(p.name for p in state["cache"].parent.iterdir()) == [
        "bngsim-codegen"]
    assert sum(p.stat().st_size for p in elsewhere.iterdir()) == kept
