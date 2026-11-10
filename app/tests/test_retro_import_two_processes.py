"""Two PROCESSES importing one bundle at once (the review of #105 at
cee2fb5f, finding 1).

The lock that makes two imports of one bundle run one after the other is
per process. A terminal `flubnf retro import` and the console's Import
form, the second starting while the first was past half way, both
extracted into one shared <dst>.importing, deleted on entry: the first
said "Imported (8 weeks)" with 4 of the 8 weeks in the tree, or
run_meta.json was missing, or both died.

The fix (app/core/replay_bundle.py): every call extracts into a temp tree
of its own (<dst>.importing-<pid>-<random>); the sweep on entry removes
only leftovers (a process no longer alive, or nothing written for an
hour), never another live call's; a temp tree is renamed into place only
with every member at its size; and of two that reach the rename at once
one stands and the other is refused in words.

Each import here runs in a python of its own (cwd the checkout, this
checkout's code), held at a chosen point by flag files, so the overlaps
are the reviewer's, made deterministic.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from test_retro_archive import SEASON, _season_tree        # noqa: E402

#: eight completed weeks, as in the review
WEEKS = [f"2098-{m:02d}-{d:02d}" for m, d in
         ((1, 3), (1, 10), (1, 17), (1, 24), (1, 31), (2, 7), (2, 14),
          (2, 21))]

#: one import, in its own process: holds after its `pause_after`-th member
#: (or just before the rename into place, with "rename") until `go`
#: exists, having made `paused`; prints what it said as one JSON line
CHILD = r'''
import json, os, sys, time
from pathlib import Path
a = json.loads(sys.argv[1])
sys.path.insert(0, a["repo"])
from app.core import replay_bundle as rb

def hold():
    Path(a["paused"]).write_text("paused")
    end = time.monotonic() + 60
    while not Path(a["go"]).exists():
        if time.monotonic() > end:
            raise TimeoutError("the test never let the import go on")
        time.sleep(0.01)

real_extract, n = rb._extract_member, [0]
def extract(z, name, dst, *rest):
    real_extract(z, name, dst, *rest)
    n[0] += 1
    if a["pause"] == n[0]:
        hold()
rb._extract_member = extract

real_rename = os.rename
def rename(src, dst, *rest, **kw):
    if (a["pause"] == "rename" and ".importing" in Path(src).name
            and Path(dst).name == a["dst_name"]):
        hold()
    return real_rename(src, dst, *rest, **kw)
os.rename = rename

try:
    r = rb.import_bundle(Path(a["bundle"]), Path(a["rr"]),
                         replace=a["replace"])
    out = {"said": "imported", "weeks": len(r.weeks)}
except rb.BundleError as e:
    out = {"said": "refused", "why": str(e)}
except BaseException as e:
    out = {"said": "died", "why": f"{type(e).__name__}: {e}"}
print(json.dumps(out), flush=True)
'''


def _files(root: Path) -> dict:
    """Every file under an imported tree but its marker (which carries the
    moment of import), with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(Path(root).rglob("*"))
            if p.is_file() and p.name != rb.IMPORTED_MARK}


@pytest.fixture
def world(tmp_path):
    """A bundle of eight weeks made on "another machine", an empty retro
    root, and the tree one import of it alone makes (the reference)."""
    src = tmp_path / "elsewhere"
    src.mkdir()
    root = _season_tree(src, SEASON, weeks=WEEKS)
    # samples of some size, so a member is a real deflate stream
    for w in WEEKS:
        (root / "weeks" / w / "samples.json").write_text(json.dumps(
            {"asof": w, "pf": {"Ohio": {str(h): [float(i * h % 97)
                                                 for i in range(400)]
                                        for h in range(5)}}}))
    bundle = rb.export_season(root, SEASON, tmp_path / "out")
    m = rb.inspect_bundle(bundle)
    ref = rb.import_bundle(bundle, tmp_path / "reference").root
    rr = tmp_path / "retro"
    rr.mkdir()
    return {"tmp": tmp_path, "bundle": bundle, "stamp": m["stamp"],
            "members": len(m["files"]), "rr": rr,
            "dst": retro.archive_dir(rr, SEASON, m["stamp"]),
            "reference": _files(ref)}


class Child:
    """One import in its own python, cwd the checkout."""

    def __init__(self, world, who: str, pause, replace: bool = False):
        t = world["tmp"]
        self.paused, self.go = t / f"paused-{who}", t / f"go-{who}"
        args = {"repo": str(REPO), "bundle": str(world["bundle"]),
                "rr": str(world["rr"]), "replace": replace,
                "pause": pause, "paused": str(self.paused),
                "go": str(self.go), "dst_name": world["dst"].name}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("FLUBNF_ENGINE", None)
        self.p = subprocess.Popen(
            [sys.executable, "-c", CHILD, json.dumps(args)], cwd=str(REPO),
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)

    def wait_paused(self, limit: float = 60.0) -> bool:
        """Until it holds (True) or has ended without holding (False)."""
        end = time.monotonic() + limit
        while time.monotonic() < end:
            if self.paused.exists():
                return True
            if self.p.poll() is not None:
                return False
            time.sleep(0.01)
        raise AssertionError("the import neither held nor ended")

    def release(self) -> None:
        self.go.write_text("go")

    def said(self, limit: float = 60.0) -> dict:
        out, err = self.p.communicate(timeout=limit)
        lines = [ln for ln in out.splitlines() if ln.startswith("{")]
        assert lines, f"no outcome; stderr:\n{err}"
        return json.loads(lines[-1])


def _kill(*children):
    for c in children:
        if c.p.poll() is None:
            c.release()
            try:
                c.p.wait(10)
            except subprocess.TimeoutExpired:
                c.p.kill()


def _temps(world) -> list:
    return sorted(p.name for p in world["rr"].iterdir()
                  if ".importing" in p.name)


def _no_partial_tree(world):
    dst = world["dst"]
    assert dst.is_dir(), "nothing was imported"
    missing = sorted(set(world["reference"]) - set(_files(dst)))
    assert not missing, "the archived run lacks " + ", ".join(missing)
    assert _files(dst) == world["reference"]
    assert (dst / "run_meta.json").is_file()
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert _temps(world) == [], "a temp tree was left behind"


def test_a_second_process_starting_past_half_way_leaves_the_tree_whole(
        world):
    """The review's case: the first import is past half way when a second
    process starts on the same bundle; the second is part way when the
    first goes on and finishes. One says Imported, the other is refused
    in words, and the archived run holds every week."""
    assert world["members"] == 10                # run_meta, 8 weeks, scores
    a = Child(world, "a", pause=6)
    b = None
    try:
        assert a.wait_paused(), a.said()
        b = Child(world, "b", pause=2)
        assert b.wait_paused(), b.said()
        a.release()
        first = a.said()
        b.release()
        second = b.said()
    finally:
        _kill(a, *([b] if b else []))
    assert first == {"said": "imported", "weeks": 8}, first
    assert second == {"said": "refused",
                      "why": f"{SEASON} from this bundle was already "
                             f"imported as {world['stamp']}."}, second
    _no_partial_tree(world)


def test_two_processes_at_the_rename_at_once_one_stands(world):
    """Both have looked at the name (nothing there) and are about to
    rename their whole trees into place: one stands, the other is refused
    in words; neither dies, no temp tree is left."""
    a = Child(world, "a", pause="rename")
    b = None
    try:
        assert a.wait_paused(), a.said()
        b = Child(world, "b", pause="rename")
        assert b.wait_paused(), b.said()
        a.release()
        b.release()
        out = [a.said(), b.said()]
    finally:
        _kill(a, *([b] if b else []))
    assert sorted(o["said"] for o in out) == ["imported", "refused"], out
    refused = next(o for o in out if o["said"] == "refused")
    assert refused["why"] == (f"{SEASON} from this bundle was already "
                              f"imported as {world['stamp']}."), refused
    _no_partial_tree(world)


def test_two_replace_imports_in_two_processes_leave_one_whole_tree(world):
    """Replace on, the run already imported: the first is past half way
    when the second starts. Each replaces whole in turn; the run is whole
    and both say Imported."""
    rb.import_bundle(world["bundle"], world["rr"])
    a = Child(world, "a", pause=6, replace=True)
    b = None
    try:
        assert a.wait_paused(), a.said()
        b = Child(world, "b", pause=2, replace=True)
        assert b.wait_paused(), b.said()
        a.release()
        first = a.said()
        b.release()
        second = b.said()
    finally:
        _kill(a, *([b] if b else []))
    assert first == {"said": "imported", "weeks": 8}, first
    assert second == {"said": "imported", "weeks": 8}, second
    _no_partial_tree(world)


def test_two_replace_imports_at_the_rename_at_once_one_stands(world):
    """Replace on: the first has deleted the old run and is about to
    rename its tree into place when the second gets there too. One
    stands; the other says so in words; the run is whole."""
    rb.import_bundle(world["bundle"], world["rr"])
    a = Child(world, "a", pause="rename", replace=True)
    b = None
    try:
        assert a.wait_paused(), a.said()
        b = Child(world, "b", pause="rename", replace=True)
        assert b.wait_paused(), b.said()
        a.release()
        b.release()
        out = [a.said(), b.said()]
    finally:
        _kill(a, *([b] if b else []))
    assert sorted(o["said"] for o in out) == ["imported", "refused"], out
    refused = next(o for o in out if o["said"] == "refused")
    assert refused["why"] == (
        f"{SEASON} from this bundle was imported as {world['stamp']} by "
        "another import that finished at the same moment; that one "
        "stands."), refused
    _no_partial_tree(world)


# ------------------------------------------------------- the stale sweep

def _ended_pid() -> int:
    """The pid of a python that has ended."""
    p = subprocess.Popen([sys.executable, "-c", "pass"], cwd=str(REPO))
    p.wait(30)
    return p.pid


def _leftover(world, suffix: str, age_s: float = 0.0) -> Path:
    t = world["dst"].with_name(world["dst"].name + suffix)
    (t / "weeks" / WEEKS[0]).mkdir(parents=True)
    (t / "weeks" / WEEKS[0] / "samples.json").write_text("{}")
    (t / "run_meta.json").write_text("{}")
    if age_s:
        when = time.time() - age_s
        for p in [t, *t.rglob("*")]:
            os.utime(p, (when, when))
    return t


def test_the_sweep_removes_only_leftovers(world):
    """On entry an import removes the temp trees earlier imports left: a
    process that has ended, or nothing written for over an hour (an older
    build's <dst>.importing included). A live process's tree that is
    being written is left as it is."""
    hours = 3 * 3600.0
    dead = _leftover(world, f".importing-{_ended_pid()}-0a0b0c0d")
    # a live process: this test's parent
    live = _leftover(world, f".importing-{os.getppid()}-1a1b1c1d")
    stale = _leftover(world, f".importing-{os.getppid()}-2a2b2c2d",
                      age_s=hours)
    old_fresh = _leftover(world, ".importing")       # an older build's
    # names that are not an import's temp tree, however old
    others = [_leftover(world, s, age_s=hours)
              for s in (".importing-x", ".importing.bak", ".importingz")]
    rb.import_bundle(world["bundle"], world["rr"])
    assert not dead.exists(), "a dead process's temp tree was left"
    assert not stale.exists(), "a temp tree untouched for hours was left"
    assert live.is_dir() and (live / "run_meta.json").is_file(), \
        "another live import's temp tree was swept"
    assert old_fresh.is_dir()                        # still recent
    assert all(p.is_dir() for p in others)
    assert _files(world["dst"]) == world["reference"]


def test_an_older_builds_shared_temp_tree_goes_once_an_hour_old(world):
    assert rb.STALE_TEMP_S == 3600.0
    old = _leftover(world, ".importing", age_s=3 * 3600.0)
    rb.import_bundle(world["bundle"], world["rr"])
    assert not old.exists()
    assert _temps(world) == []


def test_a_live_import_is_never_swept_by_a_second_one(world):
    """A second process's import starts while the first is part way: the
    first's temp tree is still there, whole so far, when the second is
    done (before, the second deleted it on entry)."""
    a = Child(world, "a", pause=3)
    try:
        assert a.wait_paused(), a.said()
        before = _temps(world)
        assert len(before) == 1 and before[0].startswith(
            world["dst"].name + ".importing-"), before
        tmp_a = world["rr"] / before[0]
        have = sorted(str(p.relative_to(tmp_a))
                      for p in tmp_a.rglob("*") if p.is_file())
        assert len(have) == 3, have
        r = rb.import_bundle(world["bundle"], world["rr"])
        assert r.weeks == WEEKS
        assert sorted(str(p.relative_to(tmp_a))
                      for p in tmp_a.rglob("*") if p.is_file()) == have, \
            "the second import touched the first's temp tree"
        a.release()
        first = a.said()
    finally:
        _kill(a)
    assert first == {"said": "refused",
                     "why": f"{SEASON} from this bundle was already "
                            f"imported as {world['stamp']}."}, first
    _no_partial_tree(world)


def test_a_temp_tree_that_loses_a_member_never_goes_into_place(
        world, monkeypatch):
    """Whatever removes part of an import's temp tree while it is written
    (a sweep run by a clock gone wrong, a hand), the tree is never renamed
    into place with files missing: refused in words, nothing imported."""
    real = rb._extract_member
    seen = []

    def extract(z, name, dst, *a):
        real(z, name, dst, *a)
        seen.append(dst)
        if len(seen) == 4:
            seen[0].unlink()           # the first member, gone
    monkeypatch.setattr(rb, "_extract_member", extract)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(world["bundle"], world["rr"])
    assert str(e.value) == (
        f"{SEASON} from this bundle: run_meta.json was removed from the "
        "import's temporary folder while it was imported; nothing was "
        "imported. Import it again.")
    assert not world["dst"].exists()
    assert _temps(world) == []


# ------------------------------------------------------------- the CLI

def test_the_cli_says_a_disk_error_in_one_line(world, monkeypatch):
    """`flubnf retro import` into a folder the disk refuses: one line and
    exit 1, no traceback (it caught BundleError only)."""
    from typer.testing import CliRunner
    from flubnf.cli import app as cli_app

    def refuse(*a, **k):
        raise PermissionError(13, "Permission denied", str(world["rr"]))
    monkeypatch.setattr(rb, "import_bundle", refuse)
    res = CliRunner().invoke(cli_app, ["retro", "import",
                                       str(world["bundle"]), "--root",
                                       str(world["rr"])])
    assert res.exit_code == 1, res.output
    assert res.exception is None or isinstance(res.exception, SystemExit), \
        repr(res.exception)
    assert ("could not import: PermissionError: [Errno 13] Permission "
            f"denied: '{world['rr']}'") in res.output, res.output
    assert "Traceback" not in res.output
