"""Two paths the removal mark (retro_prep._removing) did not cover (the
review of #105 at 8a1c12f7, items 1 and 2).

  * An import with Replace deletes the archived run it replaces. (a) A
    finalize running on that run (the page the first import landed on
    started it) had the tree deleted under it; (b) a results page opened
    while the Replace's delete walked the tree started a finalize on the
    half removed tree. The import now marks the tree for the whole
    Replace, so no finalize starts on it, and refuses in words, nothing
    replaced, while a finalize runs on it.
  * A Resume posted while Storage deletes the season was claimed, and its
    worker started on the tree being removed (a discard and start over
    deleted the tree a second time). Both are now refused in words under
    _engine_lock, before the tree is read or claimed.

The races are made deterministic as in test_retro_delete_finalize_race:
the delete pauses part way, and the finalize's scoring and the season
worker are stubbed.
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
from test_retro_archive import SEASON, _roots, _season_tree  # noqa: E402

client = TestClient(srv.app)

SIX = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
       "California"]
RESUME = {"season": SEASON, "engine": "pf", "mode": "resume",
          "locations": "panel6", "national": "0"}
DISCARD = {**RESUME, "mode": "discard", "confirm": SEASON,
           "knob.groundhog.zero_anchor": "abstain"}


@pytest.fixture
def world(tmp_path, monkeypatch, pf_engine_ready):
    """A retro root (test_retro_archive's); every finalize job's scoring
    recorded instead of run (held while `gate` is clear), its map cards
    not made, and the season worker recorded instead of started. Status
    stores restored after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    ui_state._status.update({"running": None, "flash": "",
                             "flash_detail": ""})
    RP._results_jobs.clear()
    ui_shared._invalidate_scans()
    finalized, launched = [], []
    gate = threading.Event()
    gate.set()

    def finalize_season(root, season, phase_cb=None, force=False):
        finalized.append(Path(root))
        if not gate.wait(20):
            raise TimeoutError("the test never let the finalize end")
        return {"total": 0.0}
    monkeypatch.setattr(retro, "finalize_season", finalize_season)
    monkeypatch.setattr(RP, "_week_map_cards", lambda root, wk: {})
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append(a[0]))
    yield {"rr": rr, "tmp": tmp_path, "finalized": finalized,
           "launched": launched, "gate": gate}
    gate.set()
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
    """Notices join until a page shows them: each step starts with none."""
    for k in ("flash", "flash_kind", "flash_detail"):
        ui_state._status.pop(k, None)


def _paused_delete(monkeypatch):
    """retro.delete_tree that removes the scores and the caches first,
    then waits on `go` before it removes the rest: (paused, go). Only the
    first delete waits; a second one (the bug) runs through."""
    paused, go = threading.Event(), threading.Event()

    def delete_tree(p):
        p = Path(p)
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
    return paused, go


def _imported(world, scores: bool = True):
    """A bundle made on "another machine" and imported here through the
    route: (bundle, its archived tree, its stamp)."""
    src = world["tmp"] / "elsewhere"
    src.mkdir(exist_ok=True)
    root = _season_tree(src, SEASON)
    if not scores:
        (root / "scores.json").unlink()
    p = rb.export_season(root, SEASON, world["tmp"] / "out")
    stamp = rb.inspect_bundle(p)["stamp"]
    r = client.post("/retro/import", data={"path": str(p)},
                    follow_redirects=False)
    assert r.headers["location"] == f"/retro/{SEASON}?archive={stamp}", \
        _flash()
    dst = retro.archive_dir(world["rr"], SEASON, stamp)
    assert dst.is_dir()
    return p, dst, stamp


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ---------------------------------- the import with Replace (review item 1)

def test_a_replace_refuses_while_a_finalize_runs_on_the_import(
        world, monkeypatch):
    """(a): a bundle with no scores lands on a page that starts a finalize;
    the same bundle imported again with Replace while it runs is refused,
    nothing replaced, and goes ahead once the finalize is done."""
    p, dst, stamp = _imported(world, scores=False)
    page = f"/retro/{SEASON}?archive={stamp}"
    monkeypatch.setattr(ui_retro, "_RESULTS_GRACE_S", 0.05)
    world["gate"].clear()                      # the finalize keeps running
    r = client.get(page, follow_redirects=False)
    assert r.status_code == 200
    job = RP._results_jobs.get(str(dst))
    assert job is not None and not job["done"].is_set()
    assert world["finalized"] == [dst]
    # what the running job has written so far
    (dst / "playback_cache").mkdir(exist_ok=True)
    (dst / "playback_cache" / "stats_cells.json").write_text('{"weeks":{}}')
    before = _snapshot(dst)

    _clear_flash()
    r = client.post("/retro/import", data={"path": str(p), "replace": "1"},
                    follow_redirects=False)
    assert r.headers["location"] == "/retro"
    assert _flash() == (
        f"Not imported: {SEASON} from this bundle is imported as {stamp}, "
        "and its results are still being prepared; nothing was replaced. "
        "Try again in a minute.")
    assert ui_state._status.get("flash_kind") == "warn"
    assert _snapshot(dst) == before                    # nothing removed
    assert not list(world["rr"].glob("*.importing*"))  # nothing extracted
    assert not RP._REMOVING                            # the mark is lifted

    # the finalize done, the Replace goes ahead
    world["gate"].set()
    assert job["done"].wait(10) and not job["error"]
    _clear_flash()
    r = client.post("/retro/import", data={"path": str(p), "replace": "1"},
                    follow_redirects=False)
    assert r.headers["location"] == page, _flash()
    assert _flash().startswith(f"Imported {SEASON} (2 weeks).")
    assert not (dst / "playback_cache").exists()       # the new tree
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert not RP._REMOVING


def test_a_results_page_opened_during_a_replace_starts_no_finalize(
        world, monkeypatch):
    """(b): while the Replace's delete walks the archived run, its results
    page finds the scores gone; it starts no finalize on the half removed
    tree and says why. The Replace then lands whole."""
    p, dst, stamp = _imported(world)
    page = f"/retro/{SEASON}?archive={stamp}"
    paused, go = _paused_delete(monkeypatch)
    importer = TestClient(srv.app)
    out = {}

    def replace():
        out["r"] = importer.post("/retro/import",
                                 data={"path": str(p), "replace": "1"},
                                 follow_redirects=False)
    _clear_flash()
    t = threading.Thread(target=replace, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the Replace's delete did not begin"
        assert (dst / "weeks").is_dir()
        assert not (dst / "scores.json").exists()
        r = client.get(page, follow_redirects=False)
        seen = _flash()
        job = RP._results_jobs.get(str(dst))
        if job is not None:
            job["done"].wait(10)          # a job started (the bug): let it end
    finally:
        go.set()
        t.join(30)
    assert world["finalized"] == [], \
        "a finalize started on the half removed tree"
    assert job is None
    assert r.status_code == 303, r.status_code
    assert "the run is being deleted or moved" in seen, seen
    # the Replace went through, whole
    assert out["r"].headers["location"] == page, _flash()
    assert f"Imported {SEASON} (2 weeks)." in _flash()
    assert (dst / "scores.json").is_file()
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert not RP._REMOVING


def test_import_bundle_holds_the_mark_only_for_a_replace(world):
    """The module's side: `removing` is entered with the archived tree's
    path for a Replace and held until the new tree is in place; a first
    import, or one without Replace, never enters it."""
    p, dst, stamp = _imported(world)
    entered = []

    class Mark:
        def __init__(self, root):
            self.root = root

        def __enter__(self):
            entered.append(("in", self.root, self.root.is_dir()))
            return ""

        def __exit__(self, *exc):
            entered.append(("out", self.root,
                            (self.root / rb.IMPORTED_MARK).is_file()))
            return False

    with pytest.raises(rb.BundleError, match="already imported"):
        rb.import_bundle(p, world["rr"], removing=Mark)
    rb.import_bundle(p, world["tmp"] / "fresh", replace=True,
                     removing=Mark)
    fresh = retro.archive_dir(world["tmp"] / "fresh", SEASON, stamp)
    # a Replace with nothing there to replace marks the name it will take
    assert entered == [("in", fresh, False), ("out", fresh, True)]
    entered.clear()
    rb.import_bundle(p, world["rr"], replace=True, removing=Mark)
    assert entered == [("in", dst, True), ("out", dst, True)]


# ------------------------- a Resume during Storage's delete (review item 2)

def _live_tree(rr: Path) -> Path:
    root = _season_tree(rr, SEASON)
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "scope": "panel6",
                                         "locations": SIX}})
    return root


@pytest.mark.parametrize("form", [RESUME, DISCARD], ids=["resume", "discard"])
def test_a_run_posted_during_storages_delete_is_refused(world, monkeypatch,
                                                        form):
    """Storage's Delete of the season is part way through; a Resume (or a
    discard and start over) from a second tab is refused in words, nothing
    claimed or deleted a second time, and the delete goes through whole."""
    rr = world["rr"]
    root = _live_tree(rr)
    # the form is one this tree takes: with no delete under way, it is
    # claimed and its worker starts
    client.post("/retro/run", data=form, follow_redirects=False)
    assert world["launched"] == [SEASON], _flash()
    world["launched"].clear()
    ui_retro_seasons._retro_status.pop(SEASON, None)
    ui_retro_seasons._retro_claim_at.pop(SEASON, None)
    if not root.exists():                       # the discard took it
        _live_tree(rr)

    _clear_flash()
    paused, go = _paused_delete(monkeypatch)
    deleter = TestClient(srv.app)
    out = {}

    def delete():
        out["r"] = deleter.post("/storage/delete",
                                data={"kind": "retro-season",
                                      "ident": SEASON, "confirm": SEASON},
                                follow_redirects=False)
    t = threading.Thread(target=delete, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the delete did not begin"
        assert (root / "weeks").is_dir()
        r = client.post("/retro/run", data=form, follow_redirects=False)
        seen = _flash()
        detail = ui_state._status.get("flash_detail") or ""
        claimed = ui_retro_seasons._retro_status.get(SEASON)
        weeks_left = (root / "weeks").is_dir()
    finally:
        go.set()
        t.join(30)
    assert world["launched"] == [], \
        f"a {form['mode']} started on the season being deleted"
    assert claimed != "running"
    assert weeks_left, "the season was deleted a second time"
    assert r.status_code == 303
    assert seen == f"Not started: the {SEASON} results are being deleted.", \
        seen
    assert detail == ("Nothing was started. Start the replay again once "
                      "the delete is done.")
    # the delete went through, whole
    assert out["r"].status_code == 303
    assert not root.exists()
    assert f"Deleted the retrospective season {SEASON}" in _flash(), _flash()
    assert not RP._REMOVING
