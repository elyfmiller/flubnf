"""Deleting or moving a season tree while its week maps are warmed
(review 3 of #93, finding 4).

After a finalize, the warm (app/ui/retro_prep.py _warm_map_cards) writes
each week's map cards into playback_cache/map_cards, one week a second or
so. A delete that has removed playback_cache and is still walking weeks/
would then find the folder made again and fail on the tree itself: "Could
not delete ... the existing results are intact", with every week gone and
a stub left. So every path that removes or moves a tree stops the warm
first and waits for it to leave the week in hand (retro_prep._stop_warm):
Start's discard and archive, an archived run's Delete, and Storage's
Delete. A warm that does not leave in time refuses the request, nothing
removed; and a stopped warm checks again just before it writes.

The race is the file system's: shutil.rmtree lists a folder once, in the
order the file system gives. _rmtree_cache_first below is that walk on a
file system that lists playback_cache before weeks.
"""
import os
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
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from test_retro_archive import (SEASON, STAMP, _roots,     # noqa: E402
                                _season_tree)

client = TestClient(srv.app)

#: how long one week's samples take to read in the warm here
WEEK_S = 0.5
DISCARD = {"season": SEASON, "mode": "discard", "confirm": SEASON,
           "knob.groundhog.zero_anchor": "abstain"}


def _rmtree_cache_first(p) -> None:
    """retro.delete_tree on a file system that lists playback_cache first:
    one listing, playback_cache removed, then the rest of the walk (long
    enough for the warm's week in hand to end), the folder itself last."""
    p = Path(p)
    if p.is_symlink():
        p.unlink()
        return
    entries = sorted(p.iterdir(), key=lambda q: q.name != "playback_cache")
    for q in entries:
        if q.is_dir() and not q.is_symlink():
            shutil.rmtree(q)
        else:
            q.unlink()
        if q.name == "playback_cache":
            time.sleep(2 * WEEK_S)
    os.rmdir(p)


@pytest.fixture
def world(tmp_path, monkeypatch, pf_engine_ready):
    """A retro root (test_retro_archive's), the season worker stubbed, a
    week's samples read in WEEK_S, deletes walking as _rmtree_cache_first
    does; every warm started here stopped and joined after."""
    rr = _roots(tmp_path, monkeypatch)
    status = dict(ui_state._status)
    ui_state._status.update({"running": None, "flash": ""})
    RP._results_jobs.clear()
    ui_shared._invalidate_scans()
    reading = threading.Event()

    def slow(fp):
        reading.set()
        time.sleep(WEEK_S)
        return {"asof": Path(fp).parent.name, "pf": {}}
    monkeypatch.setattr(retro, "read_samples", slow)
    monkeypatch.setattr(retro, "week_member_quantiles", lambda r, wk: {})
    monkeypatch.setattr(RP, "_last_reported_before", lambda wk, n2f: {})
    monkeypatch.setattr(retro, "delete_tree", _rmtree_cache_first)
    threads = []
    yield {"rr": rr, "reading": reading, "threads": threads}
    RP._results_jobs.clear()          # any warm left stops at its next week
    for t in threads:
        t.join(10)
    ui_state._status.clear()
    ui_state._status.update(status)
    ui_shared._invalidate_scans()


def _warm(world, root: Path) -> dict:
    """A finished results job for `root`, its warm started and on its
    first week."""
    job = {"phase": "done", "t0": time.time(), "done": threading.Event(),
           "error": "", "seconds": 1.0, "season": SEASON, "inputs": None,
           "warm": threading.Event()}
    job["done"].set()
    RP._results_jobs[str(root)] = job
    world["reading"].clear()
    t = threading.Thread(target=RP._warm_map_cards, args=(root, SEASON, job),
                         daemon=True)
    t.start()
    world["threads"].append(t)
    assert world["reading"].wait(5), "the warm did not start"
    return job


def _flash() -> str:
    return ui_state._status.get("flash") or ""


# ------------------------------------------------------------ the deletes

def test_discard_stops_the_warm_and_removes_the_whole_tree(world):
    root = _season_tree(world["rr"], SEASON)
    job = _warm(world, root)
    r = client.post("/retro/run", data=DISCARD, follow_redirects=False)
    assert r.status_code == 303
    assert "Discarded" in _flash(), _flash()
    assert not root.exists()                    # no stub left behind
    assert job["warm"].is_set()


def test_storage_delete_stops_the_warm_and_removes_the_whole_tree(world):
    root = _season_tree(world["rr"], SEASON)
    job = _warm(world, root)
    r = client.post("/storage/delete", data={
        "kind": "retro-season", "ident": SEASON, "confirm": SEASON},
        follow_redirects=False)
    assert r.status_code == 303
    assert "Deleted the retrospective season" in _flash(), _flash()
    assert not root.exists()
    assert job["warm"].is_set()


@pytest.mark.parametrize("route", ["retro", "storage"])
def test_an_archived_runs_delete_stops_its_warm(world, route):
    """An archived run warms too, once a results page opens it."""
    _season_tree(world["rr"], SEASON)
    arch = retro.archive_run(world["rr"], SEASON, stamp=STAMP)
    job = _warm(world, arch)
    if route == "retro":
        client.post(f"/retro/{SEASON}/archive/{STAMP}/delete",
                    data={"confirm": SEASON}, follow_redirects=False)
        assert "Deleted the archived" in _flash(), _flash()
    else:
        client.post("/storage/delete", data={
            "kind": "retro-archive", "ident": arch.name,
            "confirm": arch.name}, follow_redirects=False)
        assert "Deleted the archived retrospective run" in _flash(), _flash()
    assert not arch.exists()
    assert job["warm"].is_set()


def test_archive_moves_the_tree_once_the_warm_has_stopped(world,
                                                          monkeypatch):
    """Start's archive moves the tree: never under a warm still writing
    into it (on Windows an open samples file can fail the move)."""
    root = _season_tree(world["rr"], SEASON)
    job = _warm(world, root)
    real, seen = retro.archive_run, []

    def archive_run(*a, **k):
        seen.append(job["warm"].is_set())
        return real(*a, **k)
    monkeypatch.setattr(retro, "archive_run", archive_run)
    client.post("/retro/run", data={
        "season": SEASON, "mode": "archive",
        "knob.groundhog.zero_anchor": "abstain"}, follow_redirects=False)
    assert seen == [True], _flash()
    assert "Archived" in _flash() and not root.exists()


def test_a_warm_still_on_its_week_refuses_and_removes_nothing(world,
                                                              monkeypatch):
    monkeypatch.setattr(RP, "_WARM_STOP_WAIT_S", 0.05)
    root = _season_tree(world["rr"], SEASON)
    weeks = sorted(p.name for p in (root / "weeks").iterdir())
    _warm(world, root)
    client.post("/retro/run", data=DISCARD, follow_redirects=False)
    assert "week maps are still being prepared" in _flash(), _flash()
    assert "Nothing was deleted" in (ui_state._status.get("flash_detail")
                                     or "")
    assert sorted(p.name for p in (root / "weeks").iterdir()) == weeks
    ui_state._status["flash"] = ""
    client.post("/storage/delete", data={
        "kind": "retro-season", "ident": SEASON, "confirm": SEASON},
        follow_redirects=False)
    assert "week maps of 2098-99 are still being prepared" in _flash()
    assert sorted(p.name for p in (root / "weeks").iterdir()) == weeks


# ------------------------------------------------------------- the warm

def test_a_stopped_warm_writes_no_card_and_begins_no_week(world):
    """Stopped while it works out a week: that week's card is not
    written, and no other week is begun."""
    root = _season_tree(world["rr"], SEASON)
    job = _warm(world, root)
    assert RP._stop_warm(root)
    assert job["warm"].is_set()
    assert not (root / "playback_cache" / "map_cards").exists()


def test_stopping_with_no_warm_or_a_finalize_still_running(world,
                                                           tmp_path):
    """No job: nothing to wait for. A finalize still running is not waited
    for, and its warm does not start."""
    root = _season_tree(world["rr"], SEASON)
    assert RP._stop_warm(root) and RP._stop_warm(tmp_path / "nowhere")
    job = {"phase": "scoring", "done": threading.Event(), "error": "",
           "season": SEASON, "inputs": None, "warm": threading.Event()}
    RP._results_jobs[str(root)] = job
    t0 = time.monotonic()
    assert RP._stop_warm(root)
    assert time.monotonic() - t0 < 1.0
    world["reading"].clear()
    job["done"].set()
    RP._warm_map_cards(root, SEASON, job)       # as the job's thread would
    assert job["warm"].is_set() and not world["reading"].is_set()
    # a record from before the warm existed
    RP._results_jobs[str(root)] = {"done": threading.Event(), "warm": None}
    assert RP._stop_warm(root)
