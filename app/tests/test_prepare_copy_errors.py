"""prepare() when copying replicate 0's BNG2.pl files fails (review 3,
finding 6; app/core/engines/pf.py _cell_files and _copy_added).

A later replicate whose files equal replicate 0's gets copies of what
BNG2.pl added there. Before the copy, BNG2.pl ran in every replicate's
folder and nothing read replicate 0's. So an OSError while reading the
replicate's own files, or while copying (a virus scanner holding the fresh
.gdat, a full disk, replicate 0's folder gone), must fall through to
BNG2.pl for that replicate, as before, and never fail the location: the
cells, the files in them and the failures recorded are what BNG2.pl in
every cell gives. When BNG2.pl then fails too, the location fails as it
did before, never on a half-copied m.net.

The hub, the cases and the BNG2.pl stub are test_prepare_golden.py's and
test_prepare_dedupe.py's; the reference is prepare with the copy turned
off.
"""
import errno
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402
from app.tests.test_prepare_dedupe import _bng, _spec3, _tree  # noqa: E402
from app.tests.test_prepare_golden import _env, _paths, normalize  # noqa: E402

HELD = "Vermont_r1"                     # the replicate whose copy fails


def _held(path) -> OSError:
    return PermissionError(errno.EACCES,
                           "The process cannot access the file because it "
                           "is being used by another process", str(path))


def _fail_copy(mp, which: str):
    """Make one step of copying into HELD fail: `which` is "first" (the
    first file copied), "gdat" (the .gdat), "m.net" (m.net's copy, after
    some bytes of it were written) or "rename" (m.net's last rename)."""
    real_copy, real_replace = shutil.copy2, os.replace
    state = {"copies": 0}

    def copy2(src, dst, *a, **kw):
        dst = Path(dst)
        if dst.parent.name == HELD:
            state["copies"] += 1
            if which == "first" and state["copies"] == 1:
                raise _held(src)
            if which == "gdat" and Path(src).suffix == ".gdat":
                raise _held(src)
            if which == "m.net" and Path(src).name == "m.net":
                dst.write_bytes(Path(src).read_bytes()[:5])  # half written
                raise OSError(errno.ENOSPC, "No space left on device",
                              str(dst))
        return real_copy(src, dst, *a, **kw)

    def replace(src, dst, *a, **kw):
        if which == "rename" and Path(dst).parent.name == HELD:
            raise _held(dst)
        return real_replace(src, dst, *a, **kw)

    mp.setattr(pf.shutil, "copy2", copy2)
    mp.setattr(pf.os, "replace", replace)


def _reference(env, mp, tmp_path):
    """prepare with the copy turned off: BNG2.pl in every cell."""
    calls = []
    _bng(mp, calls)
    mp.setattr(pf, "_netgen_added", lambda d, before: None)
    old = (tmp_path / "old").resolve()
    cells = pf.prepare(_spec3(env), old)
    return old, cells, calls


def _same_as_bng2pl_everywhere(env, new, cells_new, old, cells_old):
    assert _tree(new, env) == _tree(old, env)
    assert (normalize(json.dumps(cells_new), _paths(new, env))
            == normalize(json.dumps(cells_old), _paths(old, env)))
    assert pf.read_prepare_failures(new) == {}
    assert not [p for p in new.rglob("*") if pf._COPY_PART in p.name]


@pytest.mark.parametrize("which", ["first", "gdat", "m.net", "rename"])
def test_a_copy_that_fails_runs_bng2pl_for_that_replicate(which, monkeypatch,
                                                          tmp_path):
    """The location keeps its three cells; BNG2.pl runs for the replicate
    whose copy failed, and only for it; every file is what BNG2.pl in
    every cell writes."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        old, cells_old, _ = _reference(env, m, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    _fail_copy(monkeypatch, which)
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert len(cells) == 6
    assert calls == ["Vermont_r0", HELD, "New_York_r0"]
    _same_as_bng2pl_everywhere(env, new, cells, old, cells_old)


def test_a_replicate_whose_own_files_cannot_be_read_runs_bng2pl(monkeypatch,
                                                                tmp_path):
    """Reading the replicate's own inputs to compare them is new: an
    OSError there runs BNG2.pl, as before, and fails nothing."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        old, cells_old, _ = _reference(env, m, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    real = Path.read_bytes

    def read_bytes(self):
        if self.parent.name == "Vermont_r2" and self.suffix == ".exp":
            raise _held(self)
        return real(self)
    monkeypatch.setattr(pf.Path, "read_bytes", read_bytes)
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert len(cells) == 6
    assert calls == ["Vermont_r0", "Vermont_r2", "New_York_r0"]
    monkeypatch.setattr(pf.Path, "read_bytes", real)
    _same_as_bng2pl_everywhere(env, new, cells, old, cells_old)


def test_replicate_0s_folder_unreadable_after_bng2pl_runs_it_everywhere(
        monkeypatch, tmp_path):
    """An OSError reading replicate 0's folder after its BNG2.pl: nothing
    is copied for that location, BNG2.pl runs in every replicate."""
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    real = pf._cell_files
    seen = []

    def iterdir_fails_second_time(d):
        seen.append(d.name)
        if d.name == "Vermont_r0" and seen.count("Vermont_r0") == 2:
            real_iterdir = Path.iterdir

            def iterdir(self):
                if self == d:
                    raise _held(self)
                return real_iterdir(self)
            with monkeypatch.context() as m:
                m.setattr(pf.Path, "iterdir", iterdir)
                return real(d)
        return real(d)
    monkeypatch.setattr(pf, "_cell_files", iterdir_fails_second_time)
    cells = pf.prepare(_spec3(env), (tmp_path / "new").resolve())
    assert len(cells) == 6
    assert calls == ["Vermont_r0", "Vermont_r1", "Vermont_r2", "New_York_r0"]
    assert pf.read_prepare_failures((tmp_path / "new").resolve()) == {}


def test_a_failed_copy_then_a_failed_bng2pl_fails_the_location_as_before(
        monkeypatch, tmp_path):
    """m.net's copy stops half written and BNG2.pl then refuses that
    replicate: the half-written m.net is gone, so the location fails with
    BNG2.pl's own message, as BNG2.pl in every cell gives."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        calls_old = []
        _bng(m, calls_old, fail_for=(HELD,))
        m.setattr(pf, "_netgen_added", lambda d, before: None)
        old = (tmp_path / "old").resolve()
        cells_old = pf.prepare(_spec3(env), old)
    calls = []
    _bng(monkeypatch, calls, fail_for=(HELD,))
    _fail_copy(monkeypatch, "m.net")
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert [c["key"] for c in cells] == [c["key"] for c in cells_old] == [
        "New_York_r0", "New_York_r1", "New_York_r2"]
    assert calls == ["Vermont_r0", HELD, "New_York_r0"]
    got, want = (pf.read_prepare_failures(new),
                 pf.read_prepare_failures(old))
    assert set(got) == set(want) == {"Vermont"}
    assert got["Vermont"] == want["Vermont"]
    assert got["Vermont"].startswith(
        "FAIL: prepare: netgen failed for Vermont: ")
    assert not (new / HELD / "m.net").exists()


def test_a_half_copied_m_net_that_cannot_be_removed_never_passes_for_bng2pls(
        monkeypatch, tmp_path):
    """m.net's copy stops half written and the half copy cannot be
    removed either (the scanner still holds it): m.net was never under its
    own name, so a BNG2.pl that then refuses is still seen to fail."""
    env = _env(monkeypatch, tmp_path)
    calls = []
    _bng(monkeypatch, calls, fail_for=(HELD,))
    _fail_copy(monkeypatch, "m.net")
    real = Path.unlink

    def unlink(self, *a, **kw):
        if self.parent.name == HELD:
            raise _held(self)
        return real(self, *a, **kw)
    monkeypatch.setattr(pf.Path, "unlink", unlink)
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert [c["key"] for c in cells] == ["New_York_r0", "New_York_r1",
                                         "New_York_r2"]
    assert pf.read_prepare_failures(new)["Vermont"].startswith(
        "FAIL: prepare: netgen failed for Vermont: ")
    assert not (new / HELD / "m.net").exists()
