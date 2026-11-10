"""Two gaps the removal mark (retro_prep._removing) left (the review of
#105 at 9c16dd6c, "What the builders left open").

  * Storage's Delete looked at the season's status before it marked the
    tree. A Resume claimed in that gap was let through, and its worker
    started on a tree a confirmed delete was removing. The status is now
    looked at again under _engine_lock once the tree is marked, the lock
    a Run claims a season under after refusing a marked tree: of the two,
    one comes first and the other refuses in words.
  * The mark did not refuse a second remover: two deletes of one tree at
    once (a double click, another tab) both went ahead, and the loser said
    "Could not delete" though the tree was gone. A second remover is now
    refused in words ("already being deleted or replaced"), nothing
    removed by it, and the first goes through whole.

The races are made deterministic as in test_retro_removal_import_resume:
the first delete pauses part way; the claim is posted in the gap.
"""
import shutil
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from app.ui import retro_prep as RP                        # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons       # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402
from app.ui.routes import storage as ui_storage            # noqa: E402
from test_retro_archive import (SEASON, STAMP, _roots,     # noqa: E402
                                _season_tree)

client = TestClient(srv.app)

SIX = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
       "California"]
RESUME = {"season": SEASON, "engine": "pf", "mode": "resume",
          "locations": "panel6", "national": "0"}


@pytest.fixture
def world(tmp_path, monkeypatch, pf_engine_ready):
    """A retro root (test_retro_archive's); finalize jobs and map cards
    stubbed, the season worker recorded instead of started. Status stores
    restored after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    ui_state._status.update({"running": None, "flash": "",
                             "flash_detail": ""})
    RP._results_jobs.clear()
    ui_shared._invalidate_scans()
    launched = []
    monkeypatch.setattr(retro, "finalize_season",
                        lambda *a, **k: {"total": 0.0})
    monkeypatch.setattr(RP, "_week_map_cards", lambda root, wk: {})
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append(a[0]))
    yield {"rr": rr, "tmp": tmp_path, "launched": launched}
    for job in list(RP._results_jobs.values()):
        job["done"].wait(10)
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


def _clear_flash() -> None:
    for k in ("flash", "flash_kind", "flash_detail"):
        ui_state._status.pop(k, None)


def _live_tree(rr: Path) -> Path:
    """The live season, stopped part way: a Resume claims it."""
    root = _season_tree(rr, SEASON)
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "scope": "panel6",
                                         "locations": SIX}})
    return root


def _paused_delete(monkeypatch):
    """retro.delete_tree that removes the scores and caches first, then
    waits on `go` before it removes the rest; only the first delete waits,
    a second one runs through: (paused, go, calls)."""
    paused, go, calls = threading.Event(), threading.Event(), []

    def delete_tree(p):
        p = Path(p)
        calls.append(p)
        (p / "scores.json").unlink(missing_ok=True)
        shutil.rmtree(p / "playback_cache", ignore_errors=True)
        if paused.is_set():
            shutil.rmtree(p)
            return
        paused.set()
        if not go.wait(20):
            raise TimeoutError("the test never let the delete go on")
        shutil.rmtree(p)
    monkeypatch.setattr(retro, "delete_tree", delete_tree)
    return paused, go, calls


# ----------------------- a Resume claimed between Storage's two looks


@pytest.mark.parametrize("kind", ["retro-season", "retro-archive"])
def test_a_resume_claimed_after_storages_first_look_stops_the_delete(
        world, monkeypatch, kind):
    """Storage's checks pass (the season is stopped); a Resume from a
    second tab is claimed before the tree is marked. The delete refuses in
    the replaying words, nothing removed; the Resume's worker has its
    tree. (An archived run's Delete refuses while its season replays, so
    it is held to the same second look.)"""
    rr = world["rr"]
    root = _live_tree(rr)
    if kind == "retro-season":
        target, ident = root, SEASON
        words = (f"Not deleted: {SEASON} is replaying (status: running); "
                 "stop it first.")
    else:
        target = _season_tree(rr / "aside", SEASON)
        target = target.rename(retro.archive_dir(rr, SEASON, STAMP))
        shutil.rmtree(rr / "aside")
        ident = target.name
        words = (f"Not deleted: {SEASON} is replaying; stop it before "
                 "deleting its archived runs.")
    first_look = ui_storage._storage_target
    resumed = []

    def storage_target(k, i):
        out = first_look(k, i)
        # the gap: past the first look, before the mark
        resumed.append(TestClient(srv.app).post(
            "/retro/run", data=RESUME, follow_redirects=False))
        return out
    monkeypatch.setattr(ui_storage, "_storage_target", storage_target)
    deleted = []
    monkeypatch.setattr(retro, "delete_tree",
                        lambda p: (deleted.append(Path(p)),
                                   shutil.rmtree(p)))

    _clear_flash()
    r = client.post("/storage/delete",
                    data={"kind": kind, "ident": ident, "confirm": ident},
                    follow_redirects=False)
    assert r.status_code == 303
    assert resumed and resumed[0].status_code == 303
    assert world["launched"] == [SEASON], "the Resume was not claimed"
    assert ui_retro_seasons._retro_status.get(SEASON) == "running"
    assert deleted == [], "the delete went ahead with a Resume claimed"
    assert (target / "weeks").is_dir() and (root / "weeks").is_dir()
    assert _flash() == words, _flash()
    assert ui_state._status.get("flash_kind") == "warn"
    assert not RP._REMOVING


def test_storages_status_is_looked_at_under_engine_lock(world, monkeypatch):
    """The second look and the mark happen while Storage holds
    _engine_lock (the lock a Run's check and claim are under)."""
    _live_tree(world["rr"])
    seen = []
    real = ui_storage._replaying_why

    def replaying_why(kind, ident):
        seen.append((ui_state._engine_lock.locked(),
                     RP._being_removed(world["rr"] / SEASON)))
        return real(kind, ident)
    monkeypatch.setattr(ui_storage, "_replaying_why", replaying_why)
    monkeypatch.setattr(retro, "delete_tree", lambda p: shutil.rmtree(p))
    r = client.post("/storage/delete",
                    data={"kind": "retro-season", "ident": SEASON,
                          "confirm": SEASON}, follow_redirects=False)
    assert r.status_code == 303
    # the first look (no lock, no mark), then the second (both)
    assert seen == [(False, False), (True, True)], seen
    assert f"Deleted the retrospective season {SEASON}" in _flash()


# ------------------------------------------- two deletes of one tree at once


def _tree(world, which: str):
    """(tree, first delete, second delete, the second's refusal) for a
    pair of deletes of one tree."""
    rr = world["rr"]
    if which == "storage-twice":
        root = _season_tree(rr, SEASON)
        post = ("/storage/delete", {"kind": "retro-season", "ident": SEASON,
                                    "confirm": SEASON})
        return root, post, post, (f"Not deleted: {SEASON} is already being "
                                  "deleted or replaced.")
    _season_tree(rr, SEASON)
    arch = retro.archive_run(rr, SEASON, stamp=STAMP)
    storage = ("/storage/delete", {"kind": "retro-archive",
                                   "ident": arch.name,
                                   "confirm": arch.name})
    own = (f"/retro/{SEASON}/archive/{STAMP}/delete", {"confirm": SEASON})
    if which == "archive-twice":
        return arch, own, own, (
            f"Not deleted: the archived {SEASON} run from "
            f"{retro.stamp_human(STAMP)} is already being deleted or "
            "replaced.")
    if which == "archive-then-storage":
        return arch, own, storage, (f"Not deleted: {arch.name} is already "
                                    "being deleted or replaced.")
    return arch, storage, own, (
        f"Not deleted: the archived {SEASON} run from "
        f"{retro.stamp_human(STAMP)} is already being deleted or replaced.")


@pytest.mark.parametrize("which", ["storage-twice", "archive-twice",
                                   "archive-then-storage",
                                   "storage-then-archive"])
def test_a_second_delete_of_one_tree_is_refused_in_words(
        world, monkeypatch, which):
    root, (url1, form1), (url2, form2), words = _tree(world, which)
    paused, go, calls = _paused_delete(monkeypatch)
    out = {}

    def first():
        out["r"] = TestClient(srv.app).post(url1, data=form1,
                                            follow_redirects=False)
    _clear_flash()
    t = threading.Thread(target=first, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the first delete did not begin"
        assert (root / "weeks").is_dir()
        r = client.post(url2, data=form2, follow_redirects=False)
        seen = _flash()
        kind = ui_state._status.get("flash_kind")
        detail = ui_state._status.get("flash_detail") or ""
        weeks_left = (root / "weeks").is_dir()
        _clear_flash()
    finally:
        go.set()
        t.join(30)
    assert r.status_code == 303
    assert seen == words, seen
    assert kind == "warn"
    assert detail == "Nothing else changed."
    assert weeks_left, "the second delete removed the tree"
    assert calls == [root], "the second delete went ahead"
    # the first went through, whole, and says so
    assert out["r"].status_code == 303
    assert not root.exists()
    assert _flash().startswith("Deleted"), _flash()
    assert "Could not delete" not in _flash()
    assert not RP._REMOVING


def test_a_replace_import_during_a_delete_of_its_run_is_refused(
        world, monkeypatch):
    """A Replace import of a bundle whose archived run Storage is deleting
    is refused in words, nothing extracted; the delete goes through."""
    src = world["tmp"] / "elsewhere"
    src.mkdir()
    bundle = rb.export_season(_season_tree(src, SEASON), SEASON,
                              world["tmp"] / "out")
    stamp = rb.inspect_bundle(bundle)["stamp"]
    dst = rb.import_bundle(bundle, world["rr"]).root
    paused, go, calls = _paused_delete(monkeypatch)
    out = {}

    def delete():
        out["r"] = TestClient(srv.app).post(
            "/storage/delete", data={"kind": "retro-archive",
                                     "ident": dst.name, "confirm": dst.name},
            follow_redirects=False)
    _clear_flash()
    t = threading.Thread(target=delete, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the delete did not begin"
        r = client.post("/retro/import",
                        data={"path": str(bundle), "replace": "1"},
                        follow_redirects=False)
        seen = _flash()
        extracted = list(world["rr"].glob("*.importing*"))
        _clear_flash()
    finally:
        go.set()
        t.join(30)
    assert r.headers["location"] == "/retro"
    assert seen == (f"Not imported: {SEASON} from this bundle is imported "
                    f"as {stamp}, and that run is already being deleted or "
                    "replaced; "
                    "nothing was replaced. Import it again once the delete "
                    "is done."), seen
    assert extracted == []
    assert calls == [dst]
    assert not dst.exists()
    assert _flash().startswith(f"Deleted the archived retrospective run "
                               f"{dst.name}"), _flash()
    assert not RP._REMOVING


def test_the_mark_refuses_a_second_holder_by_any_name(world):
    """The module's side: while one block holds a tree, a second (under
    its name, or the same folder named another way) gets the words; the
    first's mark is untouched by the second's leaving."""
    root = _season_tree(world["rr"], SEASON)
    other = root.parent / ".." / root.parent.name / SEASON
    with RP._removing(root) as first:
        assert first == ""
        with RP._removing(root) as second:
            assert second == RP._ALREADY_REMOVING == \
                "already being deleted or replaced"
        with RP._removing(other) as third:
            assert third == "already being deleted or replaced"
        assert RP._being_removed(root)          # still held by the first
    assert not RP._REMOVING
    with RP._removing(root) as again:
        assert again == ""                      # free once the first is done
