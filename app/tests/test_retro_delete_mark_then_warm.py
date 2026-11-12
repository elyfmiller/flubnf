"""Every delete or move of a season tree takes the removal mark before it
stops the week maps' warm (the merge of the App final pass into the
usability work).

The two branches each guarded the same deletes: the App final pass marks
the tree (app/ui/retro_prep.py _removing), so no results page starts a
finalize on it while it is removed; the usability work stops the warm that
writes each week's map cards after a finalize (retro_prep._stop_warm), so
the delete does not meet files made again under it. Met in one merge, each
path runs them in one order: the protected-folder check, then the mark,
then the warm stopped, then the tree's size and weeks read, then the
delete. With the warm stopped before the mark, a results page opened in
between could start a finalize whose warm then writes into the tree being
removed. The mark is lifted on every exit, a refused warm stop included.

The paths: Start's discard and archive, an archived run's Delete, and
Storage's Delete of a season and of an archived run.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import retro                                 # noqa: E402
from app.ui import retro_prep as RP                        # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons       # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from test_retro_archive import (SEASON, STAMP, _roots,     # noqa: E402
                                _season_tree)

client = TestClient(srv.app)

DISCARD = {"season": SEASON, "mode": "discard", "confirm": SEASON,
           "knob.groundhog.zero_anchor": "abstain"}
ARCHIVE = {"season": SEASON, "mode": "archive",
           "knob.groundhog.zero_anchor": "abstain"}
PATHS = ["discard", "start-archive", "archive-delete", "storage",
         "storage-archive"]


@pytest.fixture
def world(tmp_path, monkeypatch, pf_engine_ready):
    """A retro root (test_retro_archive's), no replay or results job on
    it; status stores restored after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    ui_state._status.update({"running": None, "flash": ""})
    RP._results_jobs.clear()
    RP._REMOVING.clear()
    ui_shared._invalidate_scans()
    yield {"rr": rr}
    RP._results_jobs.clear()
    RP._REMOVING.clear()
    ui_state._status.clear()
    ui_state._status.update(status)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(rstatus)
    ui_retro_seasons._retro_claim_at.clear()
    ui_retro_seasons._retro_claim_at.update(claims)
    ui_shared._invalidate_scans()


def _tree(world, which: str):
    """(tree, the delete request) for one delete or move path."""
    rr = world["rr"]
    root = _season_tree(rr, SEASON)
    if which == "storage":
        return root, ("/storage/delete", {"kind": "retro-season",
                                          "ident": SEASON, "confirm": SEASON})
    if which == "discard":
        return root, ("/retro/run", DISCARD)
    if which == "start-archive":
        return root, ("/retro/run", ARCHIVE)
    arch = retro.archive_run(rr, SEASON, stamp=STAMP)
    if which == "archive-delete":
        return arch, (f"/retro/{SEASON}/archive/{STAMP}/delete",
                      {"confirm": SEASON})
    return arch, ("/storage/delete", {"kind": "retro-archive",
                                      "ident": arch.name,
                                      "confirm": arch.name})


def _record(monkeypatch, tree: Path, stopped: bool) -> list:
    """What happens to `tree`, in order: the warm stopped (with whether the
    mark was held then), its size or weeks read, the delete or the move."""
    log = []

    def stop_warm(root):
        log.append(("warm", RP._being_removed(tree)))
        return stopped
    monkeypatch.setattr(RP, "_stop_warm", stop_warm)
    for name in ("dir_size", "run_summary", "delete_tree", "archive_run"):
        real = getattr(retro, name)

        def spy(*a, _real=real, _name=name, **k):
            log.append((_name, RP._being_removed(tree)))
            return _real(*a, **k)
        monkeypatch.setattr(retro, name, spy)
    return log


@pytest.mark.parametrize("which", PATHS)
def test_the_mark_is_held_before_the_warm_is_stopped(world, monkeypatch,
                                                     which):
    tree, (url, form) = _tree(world, which)
    log = _record(monkeypatch, tree, stopped=True)
    r = client.post(url, data=form, follow_redirects=False)
    assert r.status_code == 303
    assert not tree.exists(), ui_state._status.get("flash")
    steps = [step for step, _ in log]
    assert steps[0] == "warm", log
    # each step on the tree, the warm's stop first, runs under the mark
    assert all(marked for _, marked in log), log
    # the size and the weeks are read once the warm has stopped, and the
    # tree goes last
    assert steps[-1] in ("delete_tree", "archive_run"), log
    assert not RP._being_removed(tree)          # lifted once it is done


@pytest.mark.parametrize("which", PATHS)
def test_a_warm_that_will_not_stop_refuses_and_lifts_the_mark(
        world, monkeypatch, which):
    tree, (url, form) = _tree(world, which)
    weeks = sorted(p.name for p in (tree / "weeks").iterdir())
    log = _record(monkeypatch, tree, stopped=False)
    client.post(url, data=form, follow_redirects=False)
    assert "week maps" in (ui_state._status.get("flash") or ""), \
        ui_state._status.get("flash")
    assert log == [("warm", True)], log         # nothing read or removed
    assert sorted(p.name for p in (tree / "weeks").iterdir()) == weeks
    assert not RP._being_removed(tree)
    # and the next delete is not refused as "already being deleted"
    monkeypatch.setattr(RP, "_stop_warm", lambda root: True)
    ui_state._status["flash"] = ""
    client.post(url, data=form, follow_redirects=False)
    assert not tree.exists(), ui_state._status.get("flash")


@pytest.mark.parametrize("which", PATHS)
def test_a_protected_tree_is_neither_marked_nor_its_warm_stopped(
        world, monkeypatch, which):
    tree, (url, form) = _tree(world, which)
    log = _record(monkeypatch, tree, stopped=True)
    marked = []
    real = RP._removing

    def removing(root):
        marked.append(Path(root))
        return real(root)
    monkeypatch.setattr(RP, "_removing", removing)
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(tree))
    client.post(url, data=form, follow_redirects=False)
    assert "protected" in (ui_state._status.get("flash") or ""), \
        ui_state._status.get("flash")
    assert tree.exists()
    assert log == [] and marked == [], (log, marked)
