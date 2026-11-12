"""Storage's Reclaim leaves a tree a delete, a move or an import's Replace
holds alone (the seventh pass's checks of the bundle and of the cards).

Reclaim's skips never asked retro_prep's removal mark, so it compressed
samples (and pruned weeks) in a tree Storage's Delete was removing (the
delete then failed half way, "Directory not empty"), and in the old run
a Replace was replacing: the plain samples.json it then unlinked could be
the new run's, which lost that week's samples while the import said it
was done. Now:

  * the survey and the perform step skip every tree the mark holds, by
    the same rule, so their counts agree;
  * the perform step looks again before each week's prune and each file's
    compress, under the lock the mark is taken under (the reviewer's
    ruling), so a mark can never come between the look and the work: a
    tree marked after the survey is not touched, and a delete or a Replace
    that arrives during a compress waits for that one file, then has the
    tree to itself.
"""
import os
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import reclaim, retro                          # noqa: E402
from app.core import replay_bundle as rb                     # noqa: E402
from app.core import retro_store                             # noqa: E402
from app.ui import retro_prep as RP                          # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from test_reclaim import (SEASON, W1, _mk_week, _snapshot,   # noqa: E402
                          routed, world)                     # noqa: F401
from test_retro_import_directory_and_swap import (           # noqa: E402
    WEEKS, _bundle, _files)

TREE = "2095-96"
TREE_WEEKS = ["2096-01-03", "2096-01-10", "2096-01-17"]


class _Log(list):
    """The console's log (_status["log"]) for one test: a list as the
    console's, which also keeps (message, kind, detail) of each notice
    shared._flash gives, read from that call itself. Several route
    modules import _flash, so patching Storage's copy breaks
    test_ui_layout's one-home rule; nothing is patched here, and each
    route's own _flash is the one that runs."""

    def __init__(self, lines, said: list):
        super().__init__(lines)
        self.said = said

    def append(self, line):
        caller = sys._getframe(1)
        if caller.f_code is ui_shared._flash.__code__:
            at = caller.f_locals
            self.said.append((at["msg"], at["kind"], at["detail"]))
        super().append(line)


@pytest.fixture
def flashes(monkeypatch):
    """Every flash Storage's routes give, in order: (message, kind,
    detail). Two requests at once both flash; the page keeps one."""
    said = []
    monkeypatch.setitem(ui_state._status, "log",
                        _Log(ui_state._status["log"], said))
    return said


def _confirm() -> str:
    return TestClient(srv.app).get("/api/storage/reclaim").json()["confirm"]


def _reclaim(confirm: str):
    return TestClient(srv.app).post("/storage/reclaim",
                                    data={"confirm": confirm},
                                    follow_redirects=False)


class Paused:
    """Reclaim held inside one compress in `tree`: os.replace, the first
    time it places `gz` (that week's samples.json.gz), waits there until
    let go. Once let go, reclaim's next look into `tree` waits (outside
    the lock) until the mark is taken, so the delete or Replace that was
    waiting has marked the tree by then; what it yields is kept in
    `looks`, and `looked` is set. The remover's own step after its mark
    calls remover() first, which waits for that look, so the mark is
    still held when reclaim looks. Every compress in `tree` is recorded
    with whether the mark held the tree at that moment."""

    def __init__(self, monkeypatch, tree: Path, gz: Path):
        self.at, self.go = threading.Event(), threading.Event()
        self.looked = threading.Event()
        self.compressed, self.looks = [], []
        real_replace, real_held = os.replace, reclaim._held
        real_compress = retro.compress_samples_file

        def replace(src, d, *a, **k):
            r = real_replace(src, d, *a, **k)
            if Path(d) == gz and not self.at.is_set():
                self.at.set()
                if not self.go.wait(30):
                    raise TimeoutError("the test never let the compress go")
            return r

        @contextmanager
        def held(hold, root):
            if not (Path(root) == tree and self.go.is_set()):
                with real_held(hold, root) as free:
                    yield free
                return
            end = time.monotonic() + 10
            while not RP._being_removed(tree) and time.monotonic() < end:
                time.sleep(0.005)
            with real_held(hold, root) as free:
                self.looks.append(free)
                self.looked.set()
                yield free

        def compress(fp):
            if Path(fp).is_relative_to(tree):
                self.compressed.append((Path(fp).parent.name,
                                        RP._being_removed(tree)))
            return real_compress(fp)
        monkeypatch.setattr(os, "replace", replace)
        monkeypatch.setattr(reclaim, "_held", held)
        monkeypatch.setattr(retro, "compress_samples_file", compress)

    def remover(self) -> None:
        if not self.looked.wait(15):
            raise TimeoutError("reclaim never looked at the tree again")


def _thread(fn):
    out = {}

    def run():
        try:
            out["r"] = fn()
        except BaseException as e:            # noqa: BLE001
            out["e"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, out


# ----------------------------------------------- marked before the survey

def test_a_marked_tree_is_left_out_of_the_survey_and_the_perform_step(
        routed, flashes):
    """The cards check's case: inside the mark (a delete under way), the
    reclaim report leaves the tree out, the perform step's own survey
    agrees with it (no "the storage panel changed"), and the tree keeps
    every byte while the others are reclaimed."""
    rr = routed["retro_root"]
    root = rr / SEASON
    before = _snapshot(root)
    weeks, runs, files = map(int, _confirm().split("/"))
    with RP._removing(root) as busy:
        assert busy == ""
        confirm = _confirm()
        # the tree's two completed weeks and its one plain samples file
        assert confirm == f"{weeks - 2}/{runs}/{files - 1}"
        r = _reclaim(confirm)
    assert r.status_code == 303
    assert flashes[-1][0].startswith("Reclaimed"), flashes
    assert _snapshot(root) == before
    arch = rr / f"{SEASON}__archived_20980204T101500Z"
    assert (arch / "weeks" / W1 / "samples.json.gz").is_file()
    # the mark lifted, the tree's own two weeks and one file are left
    assert _confirm() == "2/0/1"


# ------------------------------------------------- marked after the survey

def test_a_tree_marked_after_the_survey_is_not_touched(routed, flashes,
                                                       monkeypatch):
    """The mark comes after the perform step's own survey and skips (a
    delete clicked meanwhile), before any work: the look before each week
    and each file finds it, and the tree keeps every byte."""
    rr = routed["retro_root"]
    root = rr / SEASON
    before = _snapshot(root)
    confirm = _confirm()
    real = reclaim.execute
    held = ExitStack()

    def execute(*a, **k):
        assert held.enter_context(RP._removing(root)) == ""
        return real(*a, **k)
    monkeypatch.setattr(reclaim, "execute", execute)
    try:
        r = _reclaim(confirm)
    finally:
        held.close()
    assert r.status_code == 303
    assert flashes[-1][0].startswith("Reclaimed"), flashes
    assert _snapshot(root) == before


# ------------------------------------------- a delete during a compress

def test_a_delete_arriving_during_a_compress_waits_for_that_file(
        routed, flashes, monkeypatch):
    """Storage's Delete clicked while Reclaim compresses a file in that
    tree: the delete cannot mark the tree until that file is done (it
    waits, briefly), then Reclaim leaves the rest of the tree alone and
    the delete removes it whole: never "Directory not empty"."""
    rr = routed["retro_root"]
    tree = rr / TREE
    for w in TREE_WEEKS:
        _mk_week(tree, w, with_intermediates=False)
    first = tree / "weeks" / TREE_WEEKS[0]
    pause = Paused(monkeypatch, tree, first / retro_store.SAMPLES_GZ)
    real_delete = retro.delete_tree

    def delete_tree(p):
        if Path(p) == tree:
            pause.remover()
        return real_delete(p)
    monkeypatch.setattr(retro, "delete_tree", delete_tree)
    confirm = _confirm()
    rt, rout = _thread(lambda: _reclaim(confirm))
    try:
        assert pause.at.wait(30), "the compress did not begin"
        dt, dout = _thread(lambda: TestClient(srv.app).post(
            "/storage/delete", data={"kind": "retro-season", "ident": TREE,
                                     "confirm": TREE},
            follow_redirects=False))
        dt.join(0.5)
        assert dt.is_alive(), "the delete did not wait for the compress"
        assert not RP._being_removed(tree)
        assert sorted(p.name for p in (tree / "weeks").iterdir()) == \
            TREE_WEEKS
    finally:
        pause.go.set()
        rt.join(30)
    dt.join(30)
    assert not rt.is_alive() and not dt.is_alive()
    assert "e" not in rout and "e" not in dout, (rout, dout)
    deleted = [f for f in flashes if "retrospective season" in f[0]]
    assert len(deleted) == 1 and deleted[0][0].startswith(
        f"Deleted the retrospective season {TREE}: "), flashes
    assert deleted[0][1] == "ok"
    assert not (tree.exists() or tree.is_symlink())
    reclaimed = [f for f in flashes if f[0].startswith("Reclaimed")]
    assert len(reclaimed) == 1, flashes
    # the file under way when the delete came, and none once it marked:
    # the next look found the mark
    assert pause.compressed == [(TREE_WEEKS[0], False)]
    assert pause.looks == [False]
    assert not RP._REMOVING


# ------------------------------------------- a Replace during a compress

def test_a_replace_arriving_during_a_compress_keeps_every_weeks_samples(
        routed, flashes, monkeypatch):
    """The bundle check's race: Reclaim compresses a week of an imported
    run while an import's Replace of it (the console's, with the mark)
    arrives. The Replace waits for that file before it marks the run;
    Reclaim then leaves the run alone, and the new run holds every week's
    samples, byte for byte the bundle's."""
    rr = routed["retro_root"]
    bundle = _bundle(routed["tmp"])
    ref = _files(rb.import_bundle(bundle, routed["tmp"] / "reference").root)
    dst = rb.import_bundle(bundle, rr).root
    pause = Paused(monkeypatch, dst,
                   dst / "weeks" / WEEKS[0] / retro_store.SAMPLES_GZ)
    real_temp = rb._temp_tree

    def temp_tree(d):
        pause.remover()                   # the Replace has its mark by now
        return real_temp(d)
    monkeypatch.setattr(rb, "_temp_tree", temp_tree)
    confirm = _confirm()
    rt, rout = _thread(lambda: _reclaim(confirm))
    try:
        assert pause.at.wait(30), "the compress did not begin"
        it, iout = _thread(lambda: rb.import_bundle(
            bundle, rr, replace=True, removing=RP._removing))
        it.join(0.5)
        assert it.is_alive(), "the Replace did not wait for the compress"
        assert not RP._being_removed(dst)
        assert not [p for p in rr.iterdir() if ".importing-" in p.name]
    finally:
        pause.go.set()
        rt.join(30)
    it.join(30)
    assert not rt.is_alive() and not it.is_alive()
    assert "e" not in rout and "e" not in iout, (rout, iout)
    assert iout["r"].root == dst
    for w in WEEKS:
        assert retro.samples_file(dst / "weeks" / w) is not None, w
    assert _files(dst) == ref
    # the old run's first week, under way when the Replace came; none
    # while the Replace held the run
    assert pause.compressed == [(WEEKS[0], False)]
    assert pause.looks == [False]
    assert not RP._REMOVING
