"""A copy that fails and cannot be removed either (review 3 of #93,
re-check R7; app/core/engines/pf.py _copy_added and _drop_copies).

A later replicate whose files equal replicate 0's gets copies of what
BNG2.pl added there, m.net last through a part file. When a copy fails
and removing it fails too (the scanner still holds the file), what it
left stayed in the replicate's folder: m.net.netgen-part, or a whole copy
under one of BNG2.pl's own names. BNG2.pl then ran beside it, and the run
folder kept one file a BNG2.pl-everywhere run never writes. prepare now
removes it again before BNG2.pl runs, and the part file once more after.

The reference is prepare with the copy turned off (BNG2.pl in every
cell); the hub, the cases and the BNG2.pl stub are the other prepare
tests'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core.engines import pf                          # noqa: E402
from app.tests.test_prepare_copy_errors import (         # noqa: E402
    HELD, _fail_copy, _held, _same_as_bng2pl_everywhere)
from app.tests.test_prepare_dedupe import _bng, _spec3   # noqa: E402
from app.tests.test_prepare_golden import _env           # noqa: E402

PART = "m.net" + pf._COPY_PART
_REAL_UNLINK = Path.unlink


def _seen_at_bng2pl(mp, seen: dict):
    """Record each cell folder's file names as BNG2.pl starts in it (over
    whatever stub _bng put in place)."""
    inner = pf.subprocess.run

    def run(cmd, *a, **kw):
        if cmd and cmd[0] == "perl":
            cwd = Path(kw["cwd"])
            seen[cwd.name] = sorted(p.name for p in cwd.iterdir())
        return inner(cmd, *a, **kw)
    mp.setattr(pf.subprocess, "run", run)


def _held_unlink(mp, times: dict, only_part: bool = False):
    """Path.unlink on a file in HELD fails while the scanner holds it:
    the first `times[name]` tries for each name (default 1), the part
    file alone when `only_part`. A missing file is missing, as ever."""
    real = Path.unlink
    tries = {}

    def unlink(self, *a, **kw):
        if (self.parent.name == HELD and self.exists()
                and (self.name == PART or not only_part)):
            tries[self.name] = tries.get(self.name, 0) + 1
            if tries[self.name] <= times.get(self.name, 1):
                raise _held(self)
        return real(self, *a, **kw)
    mp.setattr(pf.Path, "unlink", unlink)
    return tries


def _reference(env, mp, tmp_path):
    """BNG2.pl in every cell, each folder as BNG2.pl found it."""
    calls, seen = [], {}
    _bng(mp, calls)
    _seen_at_bng2pl(mp, seen)
    mp.setattr(pf, "_netgen_added", lambda d, before: None)
    old = (tmp_path / "old").resolve()
    cells = pf.prepare(_spec3(env), old)
    return old, cells, seen


@pytest.mark.parametrize("which", ["m.net", "rename", "gdat"])
def test_bng2pl_runs_in_the_folder_it_always_ran_in(which, monkeypatch,
                                                    tmp_path):
    """The copy into HELD fails (m.net half written, m.net's rename, or
    the .gdat after the .cdat arrived) and the removal of what it made
    fails once: BNG2.pl then starts in a folder holding exactly what it
    held with BNG2.pl in every cell, and the run's files are that run's."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        old, cells_old, seen_old = _reference(env, m, tmp_path)
    calls, seen = [], {}
    _bng(monkeypatch, calls)
    _seen_at_bng2pl(monkeypatch, seen)
    _fail_copy(monkeypatch, which)
    tries = _held_unlink(monkeypatch, {})
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert calls == ["Vermont_r0", HELD, "New_York_r0"]
    assert tries                         # something was left, then removed
    assert seen[HELD] == seen_old[HELD]
    assert PART not in seen[HELD]
    _same_as_bng2pl_everywhere(env, new, cells, old, cells_old)


def test_a_part_file_held_past_bng2pl_is_removed_after_it(monkeypatch,
                                                          tmp_path):
    """The scanner holds the half-copied m.net's part file through both
    removals before BNG2.pl: BNG2.pl runs beside it (nothing reads it),
    and it is gone once BNG2.pl is done, so the run's files are a
    BNG2.pl-everywhere run's."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        old, cells_old, _seen = _reference(env, m, tmp_path)
    calls, seen = [], {}
    _bng(monkeypatch, calls)
    _seen_at_bng2pl(monkeypatch, seen)
    _fail_copy(monkeypatch, "m.net")
    tries = _held_unlink(monkeypatch, {PART: 2}, only_part=True)
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert PART in seen[HELD] and tries[PART] == 3
    _same_as_bng2pl_everywhere(env, new, cells, old, cells_old)


def test_a_part_file_never_released_leaves_the_fit_as_it_was(monkeypatch,
                                                             tmp_path):
    """Held for good: it stays (nothing reads it), and every cell, file
    and failure is otherwise a BNG2.pl-everywhere run's."""
    env = _env(monkeypatch, tmp_path)
    with monkeypatch.context() as m:
        old, cells_old, _seen = _reference(env, m, tmp_path)
    calls = []
    _bng(monkeypatch, calls)
    _fail_copy(monkeypatch, "m.net")
    _held_unlink(monkeypatch, {PART: 10 ** 6}, only_part=True)
    new = (tmp_path / "new").resolve()
    cells = pf.prepare(_spec3(env), new)
    assert (new / HELD / PART).is_file()
    assert calls == ["Vermont_r0", HELD, "New_York_r0"]
    _REAL_UNLINK(new / HELD / PART)              # the scanner lets go
    _same_as_bng2pl_everywhere(env, new, cells, old, cells_old)
