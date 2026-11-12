"""A results page opened while its season tree is deleted or moved
(ux-review3 report, "Left for Ely" item 6).

The race: Storage's Delete (or an archived run's Delete, or Start's
discard or archive) removes or moves the tree. A results page opened while
the removal walks the tree finds the scores gone (stale caches) and starts
a new finalize job, which scores into the half removed tree: the delete
can then fail on files made again under it, or leave a stub of caches
behind.

The fix (app/ui/retro_prep.py _removing): every such delete or move marks
the tree before it removes anything, under the lock the finalize jobs
start under, and lifts the mark when it is done. No finalize job starts on
a marked tree, nor on one no longer on disk (_ensure_results_job refuses
in words, and records nothing); the results page says the run is being
deleted. A delete or a move also refuses while a finalize is running on
the tree, nothing removed.

The race is made deterministic here: the delete removes the scores and
the caches first, as a file system that lists them first would, then
waits for the test to open the results page before it removes the rest.
"""
import shutil
import sys
import threading
import time
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
BEING_DELETED = "the run is being deleted or moved"


@pytest.fixture
def world(tmp_path, monkeypatch, pf_engine_ready):
    """A retro root (test_retro_archive's) with the season worker stubbed;
    every finalize job's scoring recorded instead of run, and its map cards
    not made. Status stores restored after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    ui_state._status.update({"running": None, "flash": ""})
    RP._results_jobs.clear()
    ui_shared._invalidate_scans()
    finalized = []

    def finalize_season(root, season, phase_cb=None, force=False):
        finalized.append(Path(root))
        return {"total": 0.0}
    monkeypatch.setattr(retro, "finalize_season", finalize_season)
    monkeypatch.setattr(RP, "_week_map_cards", lambda root, wk: {})
    yield {"rr": rr, "finalized": finalized}
    RP._results_jobs.clear()
    ui_state._status.clear()
    ui_state._status.update(status)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(rstatus)
    ui_retro_seasons._retro_claim_at.clear()
    ui_retro_seasons._retro_claim_at.update(claims)
    ui_shared._invalidate_scans()


def _flash() -> str:
    return ui_state._status.get("flash") or ""


def _paused_delete(monkeypatch):
    """retro.delete_tree that removes the scores and the caches first,
    then waits on `go` before it removes the rest: (paused, go)."""
    paused, go = threading.Event(), threading.Event()

    def delete_tree(p):
        p = Path(p)
        (p / "scores.json").unlink()
        shutil.rmtree(p / "playback_cache")
        paused.set()
        if not go.wait(20):
            raise TimeoutError("the test never let the delete go on")
        shutil.rmtree(p)
    monkeypatch.setattr(retro, "delete_tree", delete_tree)
    return paused, go


def _tree(world, which: str):
    """(tree, its results page, the delete request) for one delete path."""
    rr = world["rr"]
    root = _season_tree(rr, SEASON)
    if which == "storage":
        return (root, f"/retro/{SEASON}",
                ("/storage/delete", {"kind": "retro-season", "ident": SEASON,
                                     "confirm": SEASON}))
    if which == "discard":
        return root, f"/retro/{SEASON}", ("/retro/run", DISCARD)
    if which == "start-archive":
        return root, f"/retro/{SEASON}", ("/retro/run", ARCHIVE)
    arch = retro.archive_run(rr, SEASON, stamp=STAMP)
    page = f"/retro/{SEASON}?archive={STAMP}"
    if which == "archive-delete":
        return (arch, page, (f"/retro/{SEASON}/archive/{STAMP}/delete",
                             {"confirm": SEASON}))
    return (arch, page, ("/storage/delete", {
        "kind": "retro-archive", "ident": arch.name, "confirm": arch.name}))


# ------------------------------------------------------------- the race

@pytest.mark.parametrize("which", ["storage", "discard", "archive-delete",
                                   "storage-archive"])
def test_a_results_page_opened_during_a_delete_starts_no_finalize(
        world, monkeypatch, which):
    root, page, (url, form) = _tree(world, which)
    paused, go = _paused_delete(monkeypatch)
    deleter = TestClient(srv.app)
    out = {}

    def delete():
        out["r"] = deleter.post(url, data=form, follow_redirects=False)
    t = threading.Thread(target=delete, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the delete did not begin"
        # the half removed tree: weeks left, the scores and caches gone
        assert (root / "weeks").is_dir()
        assert not (root / "scores.json").exists()
        r = client.get(page, follow_redirects=False)
        seen = _flash()
        job = RP._results_jobs.get(str(root))
        if job is not None:
            job["done"].wait(10)          # a job started (the bug): let it end
    finally:
        go.set()
        t.join(30)
    assert world["finalized"] == [], \
        "a finalize started on the half removed tree"
    assert job is None
    assert r.status_code == 303, r.status_code
    assert BEING_DELETED in seen, seen
    # the delete went through, whole
    assert out["r"].status_code == 303
    assert not root.exists()
    assert ("Deleted" in _flash() or "Discarded" in _flash()), _flash()
    assert not RP._REMOVING            # the mark is lifted


# ------------------------------------------------------ the finalize job

def test_no_finalize_starts_on_a_marked_tree(world):
    root = _season_tree(world["rr"], SEASON)
    with RP._removing(root) as busy:
        assert busy == ""
        job = RP._ensure_results_job(root, SEASON)
        assert job["done"].is_set() and job["refused"]
        assert job["error"] == ("the run is being deleted or moved; its "
                                "results are not prepared")
        # the same folder named another way is marked too
        other = root.parent / ".." / root.parent.name / SEASON
        assert RP._ensure_results_job(other, SEASON)["refused"]
        assert world["finalized"] == []
        assert str(root) not in RP._results_jobs     # nothing recorded
    # the mark lifted: the next visit's job runs as before
    assert not RP._REMOVING
    job = RP._ensure_results_job(root, SEASON)
    assert job["done"].wait(10) and not job["error"]
    assert world["finalized"] == [root]


def test_no_finalize_starts_on_a_tree_no_longer_on_disk(world):
    root = _season_tree(world["rr"], SEASON)
    shutil.rmtree(root)
    job = RP._ensure_results_job(root, SEASON)
    assert job["done"].is_set() and job["refused"]
    assert job["error"] == ("the run is no longer on disk; its results are "
                            "not prepared")
    assert world["finalized"] == []
    assert not root.exists()           # nothing made again


def test_a_running_finalize_is_joined_not_refused(world):
    """A job already running when a delete marks the tree is joined (it
    started nothing new); the delete itself refuses (below)."""
    root = _season_tree(world["rr"], SEASON)
    running = {"phase": "scoring cells", "t0": time.time(),
               "done": threading.Event(), "error": "", "season": SEASON,
               "inputs": None}
    RP._results_jobs[str(root)] = running
    with RP._removing(root) as busy:
        assert busy == "results"
        assert RP._ensure_results_job(root, SEASON) is running
    assert not RP._REMOVING


# ------------------------------------- a delete while a finalize runs

@pytest.mark.parametrize("which", ["storage", "discard", "start-archive",
                                   "archive-delete"])
def test_a_delete_refuses_while_a_finalize_runs(world, which):
    root, _page, (url, form) = _tree(world, which)
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    RP._results_jobs[str(root)] = {
        "phase": "scoring cells", "t0": time.time(),
        "done": threading.Event(), "error": "", "season": SEASON,
        "inputs": None}
    r = client.post(url, data=form, follow_redirects=False)
    assert r.status_code == 303
    what = {"storage": f"Not deleted: the results of {SEASON} are still",
            "discard": f"Not started: the {SEASON} results are still",
            "start-archive": f"Not started: the {SEASON} results are still",
            "archive-delete": "Not deleted: the results of the archived "
                              f"{SEASON} run from"}[which]
    assert what in _flash(), _flash()
    assert "being prepared" in _flash()
    assert sorted(str(p.relative_to(root))
                  for p in root.rglob("*")) == files       # nothing removed
    assert not RP._REMOVING
    if which in ("discard", "start-archive"):
        nothing = ("Nothing was deleted" if which == "discard"
                   else "Nothing was archived")
        assert nothing in (ui_state._status.get("flash_detail") or "")
        assert ui_retro_seasons._retro_status.get(SEASON) != "running"
        if which == "start-archive":
            assert not list(root.parent.glob(f"{SEASON}__archived_*"))
