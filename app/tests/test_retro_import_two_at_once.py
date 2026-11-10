"""Two imports of one bundle at once (the review of #105 at 9c16dd6c,
finding 1).

The Import form has no double-submit guard and its route runs in the
thread pool, so a double click posts the same bundle twice, the two
imports overlapping. Both extracted into one shared <dst>.importing folder,
deleted on entry: the second deleted the first's half made tree and
finished; the first made the folder again with only its remaining files,
deleted the second's whole tree (even without Replace) and renamed its
partial one into place. Both said "Imported"; the archived run lacked
run_meta.json.

The fix (app/core/replay_bundle.py import_bundle): one lock per
destination around the import, so the second waits for the first and is
then refused in words ("already imported") without Replace; and a second
look at the destination just before the rename, so a tree that appeared
meanwhile is never deleted without Replace.

The overlap is made deterministic: the first import pauses after its
first member until the test lets it go on.
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from app.ui import retro_prep as RP                        # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from test_retro_archive import SEASON, _roots, _season_tree  # noqa: E402

client = TestClient(srv.app)

#: how long the test lets the second import run on its own: an unguarded
#: one finishes in well under this, a guarded one is still waiting
ALONE_S = 1.5


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A retro root (test_retro_archive's), a bundle made on "another
    machine", and the tree one import of it alone makes (the reference)."""
    status = dict(ui_state._status)
    rr = _roots(tmp_path, monkeypatch)
    ui_state._status.update({"running": None, "flash": "",
                             "flash_detail": ""})
    ui_shared._invalidate_scans()
    src = tmp_path / "elsewhere"
    src.mkdir()
    bundle = rb.export_season(_season_tree(src, SEASON), SEASON,
                              tmp_path / "out")
    stamp = rb.inspect_bundle(bundle)["stamp"]
    ref = rb.import_bundle(bundle, tmp_path / "reference").root
    yield {"rr": rr, "bundle": bundle, "stamp": stamp,
           "dst": retro.archive_dir(rr, SEASON, stamp),
           "reference": _files(ref)}
    ui_state._status.clear()
    ui_state._status.update(status)
    ui_shared._invalidate_scans()


def _files(root: Path) -> dict:
    """Every file under an imported tree but its marker (which carries the
    moment of import), with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(Path(root).rglob("*"))
            if p.is_file() and p.name != rb.IMPORTED_MARK}


def _pause_first(monkeypatch):
    """_extract_member that holds the first import to call it after its
    first member until `go`: (paused, go)."""
    real = rb._extract_member
    first, paused, go = [], threading.Event(), threading.Event()

    def extract(z, name, dst, *a):
        me = threading.get_ident()
        if not first:
            first.append(me)
        real(z, name, dst, *a)
        if me == first[0] and not paused.is_set():
            paused.set()
            if not go.wait(20):
                raise TimeoutError("the test never let the import go on")
    monkeypatch.setattr(rb, "_extract_member", extract)
    return paused, go


def _two_at_once(world, monkeypatch, call):
    """Run `call` twice, the second while the first is paused part way
    through its extraction; (first's outcome, second's outcome, whether the
    second was still waiting when the first went on)."""
    paused, go = _pause_first(monkeypatch)
    out = {}

    def run(who):
        try:
            out[who] = call()
        except Exception as e:          # noqa: BLE001 - the outcome itself
            out[who] = e
    a = threading.Thread(target=run, args=("a",), daemon=True)
    a.start()
    try:
        assert paused.wait(20), "the first import did not begin"
        b = threading.Thread(target=run, args=("b",), daemon=True)
        b.start()
        b.join(ALONE_S)
        waiting = b.is_alive()
    finally:
        go.set()
    a.join(30)
    b.join(30)
    assert not a.is_alive() and not b.is_alive()
    return out["a"], out["b"], waiting


def test_two_imports_of_one_bundle_at_once_give_one_whole_tree(
        world, monkeypatch):
    """Replace off, as on a double click: the second waits for the first,
    then is refused in words; the archived run is whole."""
    first, second, waiting = _two_at_once(
        world, monkeypatch,
        lambda: rb.import_bundle(world["bundle"], world["rr"]))
    dst = world["dst"]
    assert _files(dst) == world["reference"], \
        "the archived run lacks files: " + ", ".join(
            sorted(set(world["reference"]) - set(_files(dst))))
    assert (dst / "run_meta.json").is_file()
    assert isinstance(first, rb.ImportResult), first
    assert isinstance(second, rb.BundleError), \
        f"both imports said they imported: {second!r}"
    assert str(second) == (f"{SEASON} from this bundle was already imported "
                           f"as {world['stamp']}.")
    assert waiting, "the second import ran alongside the first"
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert not list(world["rr"].glob("*.importing"))


def test_two_replace_imports_at_once_give_one_whole_tree(world, monkeypatch):
    """Replace on, the run already imported: the two run one after the
    other (each replaces whole), never into one temp tree."""
    rb.import_bundle(world["bundle"], world["rr"])
    first, second, waiting = _two_at_once(
        world, monkeypatch,
        lambda: rb.import_bundle(world["bundle"], world["rr"], replace=True,
                                 removing=RP._removing))
    assert isinstance(first, rb.ImportResult), first
    assert isinstance(second, rb.ImportResult), second
    assert waiting, "the second import ran alongside the first"
    assert _files(world["dst"]) == world["reference"]
    assert not list(world["rr"].glob("*.importing"))
    assert not RP._REMOVING


def test_a_tree_that_appears_meanwhile_is_not_deleted_without_replace(
        world, monkeypatch):
    """The second look: a tree under the destination's name that appeared
    while this import extracted (another process's import) is left as it
    is and the import refused in words, its temp tree removed."""
    dst = world["dst"]
    paused, go = _pause_first(monkeypatch)
    out = {}

    def run():
        try:
            out["r"] = rb.import_bundle(world["bundle"], world["rr"])
        except Exception as e:          # noqa: BLE001 - the outcome itself
            out["r"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the import did not begin"
        dst.mkdir()
        (dst / "theirs.txt").write_text("another import's tree")
    finally:
        go.set()
    t.join(30)
    assert isinstance(out["r"], rb.BundleError), out["r"]
    assert str(out["r"]) == (f"{SEASON} from this bundle was already "
                             f"imported as {world['stamp']}.")
    assert sorted(p.name for p in dst.iterdir()) == ["theirs.txt"]
    assert not list(world["rr"].glob("*.importing"))


def test_a_double_click_on_import_says_imported_once(world, monkeypatch):
    """Through the route: two posts of one path at once. One says
    Imported, the other that the bundle was already imported; the run
    opens whole."""
    paused, go = _pause_first(monkeypatch)
    out = {}

    def post(who):
        out[who] = TestClient(srv.app).post(
            "/retro/import", data={"path": str(world["bundle"])},
            follow_redirects=False)
    a = threading.Thread(target=post, args=("a",), daemon=True)
    a.start()
    try:
        assert paused.wait(20), "the first import did not begin"
        b = threading.Thread(target=post, args=("b",), daemon=True)
        b.start()
        b.join(ALONE_S)
    finally:
        go.set()
    a.join(30)
    b.join(30)
    flash = ui_state._status.get("flash") or ""
    page = f"/retro/{SEASON}?archive={world['stamp']}"
    assert sorted(r.headers["location"] for r in out.values()) == \
        ["/retro", page], flash
    assert flash.count(f"Imported {SEASON} (2 weeks).") == 1, flash
    assert (f"Not imported: {SEASON} from this bundle was already imported "
            f"as {world['stamp']}.") in flash
    assert _files(world["dst"]) == world["reference"]
