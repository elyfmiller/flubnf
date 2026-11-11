"""Three S3s from the review of #105 at bc045672 (the fifth pass).

  1. One changed byte in the zip's table of contents (its central
     directory) gave a 500 page and a terminal traceback: the encrypted
     flag set raised RuntimeError, a compression method or flag zipfile
     does not read NotImplementedError, and a "zip version needed" it does
     not know NotImplementedError from the ZipFile constructor in
     inspect_bundle. Each is now refused in words as a damaged bundle,
     nothing written.
  2. A live import whose temp tree was swept (another machine's sweep, an
     import idle for an hour) met the missing files first in the pass
     that sets the quantiles' times, and said a raw FileNotFoundError.
     The "every member still there" check now comes first, with its
     sentence.
  3. A Replace killed while it deleted the old run left part of a run
     under the run's name, which the next plain import called "already
     imported", and the whole new tree under a temp name no page shows.
     The old tree is now renamed aside (<dst>.replaced-<pid>-<random>),
     the new one renamed in, and only then is the old one deleted; the
     sweep (which never deletes in a protected folder) removes an aside a
     dead process left, on a refused import too.

The kills are real: a Replace runs in a python of its own (cwd the
checkout), held at a chosen step by a flag file, and is ended with
SIGKILL there.
"""
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import app.core.runs as runs_mod                           # noqa: E402
from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from app.core.retro_store import ORACLE_NAME               # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons       # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402
from app.ui import state as ui_state                       # noqa: E402
from test_retro_archive import SEASON, _roots, _season_tree  # noqa: E402

client = TestClient(srv.app)

WEEKS = ["2098-01-03", "2098-01-10", "2098-01-17", "2098-01-24"]
W3 = WEEKS[2]


def _bundle(tmp: Path, oracle: bool = False) -> Path:
    """A bundle of four weeks made on "another machine": samples that are
    real deflate streams, each week's quantiles current (so they travel)
    and, with `oracle`, the first week's oracle.json."""
    src = tmp / "elsewhere"
    src.mkdir()
    root = _season_tree(src, SEASON, weeks=WEEKS)
    for w in WEEKS:
        wd = root / "weeks" / w
        (wd / "samples.json").write_text(json.dumps(
            {"asof": w, "pf": {"Ohio": {str(h): [float(i * h % 89)
                                                 for i in range(300)]
                                        for h in range(5)}}}))
        q = wd / retro.QUANTILES_NAME
        q.write_text(json.dumps({"asof": w, "q": [0.1, 0.5, 0.9]}))
        t = (wd / "samples.json").stat().st_mtime + 10
        os.utime(q, (t, t))
    if oracle:
        (root / "weeks" / WEEKS[0] / ORACLE_NAME).write_text(
            json.dumps({"step": "on"}))
    return rb.export_season(root, SEASON, tmp / "out")


def _files(root: Path) -> dict:
    """Every file under an imported tree but its marker (which carries the
    moment of import), with its bytes."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(Path(root).rglob("*"))
            if p.is_file() and p.name != rb.IMPORTED_MARK}


def _beside(rr: Path) -> list:
    """What lies under the retro root that is not a run: temp trees, the
    old trees a Replace set aside, and those it let go (renamed before they
    are deleted)."""
    return sorted(p.name for p in rr.iterdir()
                  if any(s in p.name
                         for s in (".importing", ".replaced", ".dropping")))


# ------------------------------- 1. a changed byte in the table of contents

def _directory_entry(data: bytes, member: str) -> int:
    """Where `member`'s record starts in the zip's central directory."""
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as z:
        off = z.start_dir
    while data[off:off + 4] == b"PK\x01\x02":
        n = int.from_bytes(data[off + 28:off + 30], "little")
        if bytes(data[off + 46:off + 46 + n]).decode() == member:
            return off
        off += (46 + n + int.from_bytes(data[off + 30:off + 32], "little")
                + int.from_bytes(data[off + 32:off + 34], "little"))
    raise KeyError(member)


def _changed(bundle: Path, member: str, how: str, out: Path) -> Path:
    """A copy of `bundle` with one byte of `member`'s central directory
    record changed: the encrypted flag set ("encrypted"), the compression
    method made one zipfile does not read ("method"), the strong-encryption
    flag set ("flag"), or the "zip version needed" made 25.5 ("version")."""
    data = bytearray(bundle.read_bytes())
    off = _directory_entry(data, member)
    if how == "encrypted":
        data[off + 8] |= 0x01
    elif how == "flag":
        data[off + 8] |= 0x40
    elif how == "method":
        assert data[off + 10] == zipfile.ZIP_DEFLATED
        data[off + 10] ^= 0xFF
    elif how == "version":
        data[off + 6] = 0xFF
    else:
        raise ValueError(how)
    out.write_bytes(bytes(data))
    return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A retro root (test_retro_archive's), the exports folder under this
    test's state, and a bundle of four weeks. Status stores restored
    after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    ui_state._status.update({"running": None, "flash": "",
                             "flash_detail": ""})
    ui_shared._invalidate_scans()
    bundle = _bundle(tmp_path)
    m = rb.inspect_bundle(bundle)
    yield {"tmp": tmp_path, "rr": rr, "bundle": bundle, "stamp": m["stamp"],
           "dst": retro.archive_dir(rr, SEASON, m["stamp"])}
    ui_state._status.clear()
    ui_state._status.update(status)
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(rstatus)
    ui_retro_seasons._retro_claim_at.clear()
    ui_retro_seasons._retro_claim_at.update(claims)
    ui_shared._invalidate_scans()


def _flash() -> str:
    return ui_state._status.get("flash") or ""


def _nothing_written(rr: Path) -> None:
    assert sorted(p.name for p in rr.iterdir()) == []


@pytest.mark.parametrize("how", ["encrypted", "method", "flag"])
def test_a_members_changed_directory_entry_is_refused_in_words(world, how):
    """The member's flag or compression method changed in the table of
    contents (its own bytes untouched): refused as a damaged bundle,
    nothing written, no temp tree left."""
    member = f"weeks/{W3}/samples.json"
    bad = _changed(world["bundle"], member, how, world["tmp"] / "bad.zip")
    words = (f"mine.flubnf-replay.zip: {member} could not be unpacked; the "
             "bundle is damaged or altered.")
    if how == "method":
        # a method no FluBNF bundle uses is refused from the member's
        # entry when the bundle is inspected, in the same words
        with pytest.raises(rb.BundleError) as e:
            rb.inspect_bundle(bad, "mine.flubnf-replay.zip")
        assert str(e.value) == words
    else:
        rb.inspect_bundle(bad)         # the manifest itself reads
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bad, world["rr"], name="mine.flubnf-replay.zip")
    assert str(e.value) == words
    _nothing_written(world["rr"])


@pytest.mark.parametrize("how", ["encrypted", "method", "flag"])
def test_the_manifests_changed_directory_entry_is_refused_in_words(
        world, how):
    bad = _changed(world["bundle"], rb.MANIFEST, how,
                   world["tmp"] / "bad.zip")
    for call in (lambda: rb.inspect_bundle(bad),
                 lambda: rb.import_bundle(bad, world["rr"])):
        with pytest.raises(rb.BundleError) as e:
            call()
        assert str(e.value) == ("bad.zip: manifest.json could not be "
                                "unpacked; the bundle is damaged or altered.")
    _nothing_written(world["rr"])


VERSION_WORDS = ("bad.zip: its table of contents asks for a zip feature "
                 "no FluBNF bundle uses; the bundle is damaged or altered.")


@pytest.mark.parametrize("member", [rb.MANIFEST, f"weeks/{W3}/samples.json"])
def test_a_zip_version_no_reader_knows_is_refused_by_the_constructor(
        world, member):
    """The ZipFile constructor itself refuses it (NotImplementedError,
    before any member is read): caught around the constructor."""
    bad = _changed(world["bundle"], member, "version",
                   world["tmp"] / "bad.zip")
    for call in (lambda: rb.inspect_bundle(bad),
                 lambda: rb.import_bundle(bad, world["rr"])):
        with pytest.raises(rb.BundleError) as e:
            call()
        assert str(e.value) == VERSION_WORDS
    _nothing_written(world["rr"])


@pytest.mark.parametrize("how,words", [
    ("encrypted", f"bad.zip: weeks/{W3}/samples.json could not be "
                  "unpacked; the bundle is damaged or altered."),
    ("method", f"bad.zip: weeks/{W3}/samples.json could not be unpacked; "
               "the bundle is damaged or altered."),
    ("version", VERSION_WORDS)])
def test_the_import_form_and_the_terminal_say_it_in_words(world, how, words):
    """Through the route (a refusal and the index, never a 500 page) and
    `flubnf retro import` (one line, exit 2, no traceback)."""
    from flubnf.cli import app as cli_app
    bad = _changed(world["bundle"], f"weeks/{W3}/samples.json", how,
                   world["tmp"] / "bad.zip")
    r = client.post("/retro/import", data={"path": str(bad)},
                    follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert r.headers["location"] == "/retro"
    assert _flash() == f"Not imported: {words}"
    assert ui_state._status.get("flash_kind") == "warn"
    res = CliRunner().invoke(cli_app, ["retro", "import", str(bad),
                                       "--root", str(world["rr"])])
    assert res.exit_code == 2, res.output
    assert f"refused: {words}" in res.output, res.output
    assert "Traceback" not in res.output
    _nothing_written(world["rr"])


def test_an_export_passes_over_an_earlier_bundle_it_cannot_open(world):
    """An earlier bundle of the season in the exports folder whose table
    of contents was altered: the export writes a new bundle beside it
    (the reuse check opened it with the same constructor and died)."""
    src = world["tmp"] / "elsewhere" / SEASON
    out = world["tmp"] / "out"
    bad = _changed(world["bundle"], rb.MANIFEST, "version",
                   out / world["bundle"].name)
    assert bad == world["bundle"]           # the earlier bundle, altered
    os.utime(bad, (time.time() + 60, time.time() + 60))   # newer than all
    p = rb.export_season(src, SEASON, out)
    assert p != bad and p.is_file()
    assert rb.inspect_bundle(p)["weeks"] == WEEKS


# ------------------------------- 2. a swept temp tree, quantiles carried

@pytest.mark.parametrize("oracle", [False, True])
def test_a_swept_temp_tree_is_refused_in_words_when_quantiles_travel(
        tmp_path, monkeypatch, oracle):
    """The import's own temp tree is swept part way (the sweep run with a
    clock over an hour on, as another machine's or a woken laptop's
    would): the members extracted after it recreate part of the tree.
    The refusal is the sentence written for it, not a raw
    FileNotFoundError from setting the quantiles' times."""
    bundle = _bundle(tmp_path, oracle=oracle)
    m = rb.inspect_bundle(bundle)
    assert any(f.endswith(retro.QUANTILES_NAME) for f in m["files"])
    rr = tmp_path / "retro"
    rr.mkdir()
    dst = retro.archive_dir(rr, SEASON, m["stamp"])
    real = rb._extract_member
    n = [0]

    def extract(z, name, d, *a):
        real(z, name, d, *a)
        n[0] += 1
        if n[0] == 4:
            gone = rb._sweep_stale_temps(
                dst, now=time.time() + 2 * rb.STALE_TEMP_S)
            assert len(gone) == 1 and ".importing-" in gone[0].name
    monkeypatch.setattr(rb, "_extract_member", extract)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bundle, rr)
    assert str(e.value) == (
        f"{SEASON} from this bundle: run_meta.json was removed from the "
        "import's temporary folder while it was imported; nothing was "
        "imported. Import it again.")
    assert sorted(p.name for p in rr.iterdir()) == []


# --------------------------------------- 3. a Replace killed part way

#: one Replace import, in its own process, held at `pause` (and, unless
#: let go, killed there by the test): "rename" just before its new tree is
#: renamed into place; "delete" as it starts deleting the old run;
#: "delete-half" once half the old run's files are deleted
CHILD = r'''
import json, os, shutil, sys, time
from pathlib import Path
a = json.loads(sys.argv[1])
sys.path.insert(0, a["repo"])
from app.core import replay_bundle as rb

def hold():
    Path(a["paused"]).write_text("paused")
    end = time.monotonic() + 60
    while not Path(a["go"]).exists():
        if time.monotonic() > end:
            raise TimeoutError("the test never ended this import")
        time.sleep(0.01)

real_rename = os.rename
def rename(src, dst, *rest, **kw):
    if (a["pause"] == "rename" and ".importing" in Path(src).name
            and Path(dst).name == a["dst_name"]):
        hold()
    return real_rename(src, dst, *rest, **kw)
os.rename = rename

real_rmtree = shutil.rmtree
def rmtree(p, *rest, **kw):
    name = Path(p).name
    if (a["pause"] in ("delete", "delete-half")
            and name.startswith(a["dst_name"]) and ".importing" not in name):
        if a["pause"] == "delete-half":
            files = sorted(q for q in Path(p).rglob("*") if q.is_file())
            assert len(files) > 6, files
            for q in files[:len(files) // 2]:
                q.unlink()
        hold()
    return real_rmtree(p, *rest, **kw)
shutil.rmtree = rmtree

r = rb.import_bundle(Path(a["bundle"]), Path(a["rr"]), replace=True)
print(json.dumps({"said": "imported", "weeks": len(r.weeks)}), flush=True)
'''


@pytest.fixture
def run(tmp_path):
    """A bundle imported once (the run a Replace replaces) and the tree
    one import of it alone makes (the reference)."""
    bundle = _bundle(tmp_path)
    m = rb.inspect_bundle(bundle)
    ref = rb.import_bundle(bundle, tmp_path / "reference").root
    rr = tmp_path / "retro"
    rr.mkdir()
    first = rb.import_bundle(bundle, rr)
    return {"tmp": tmp_path, "bundle": bundle, "stamp": m["stamp"],
            "rr": rr, "dst": first.root, "reference": _files(ref)}


class Replace:
    """One Replace import of the run's bundle in its own python, cwd the
    checkout."""

    def __init__(self, run, pause: str):
        t = run["tmp"]
        self.paused, self.go = t / "paused", t / "go"
        args = {"repo": str(REPO), "bundle": str(run["bundle"]),
                "rr": str(run["rr"]), "pause": pause,
                "paused": str(self.paused), "go": str(self.go),
                "dst_name": run["dst"].name}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("FLUBNF_ENGINE", None)
        self.p = subprocess.Popen(
            [sys.executable, "-c", CHILD, json.dumps(args)], cwd=str(REPO),
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)

    def held(self, limit: float = 60.0) -> None:
        end = time.monotonic() + limit
        while time.monotonic() < end:
            if self.paused.exists():
                return
            if self.p.poll() is not None:
                out, err = self.p.communicate()
                raise AssertionError(f"ended without holding:\n{out}\n{err}")
            time.sleep(0.01)
        raise AssertionError("the Replace neither held nor ended")

    def kill(self) -> None:
        self.p.kill()                       # SIGKILL: no clean-up runs
        self.p.communicate(timeout=30)

    def release(self) -> dict:
        self.go.write_text("go")
        out, err = self.p.communicate(timeout=60)
        lines = [ln for ln in out.splitlines() if ln.startswith("{")]
        assert lines, f"no outcome; stderr:\n{err}"
        return json.loads(lines[-1])


def _killed_at(run, pause: str) -> int:
    c = Replace(run, pause)
    try:
        c.held()
    finally:
        c.kill()
    return c.p.pid


@pytest.mark.parametrize("pause", ["delete", "delete-half"])
def test_a_replace_killed_while_deleting_the_old_run_leaves_the_run_whole(
        run, pause):
    """The review's case: killed half way through deleting the old run.
    The run's name holds the new tree, whole; the old one is aside, under
    a name no page lists; the next plain import says "already imported"
    truthfully and sweeps the dead process's aside. The old run was let go
    once the new one stood, so it was renamed .dropping- before its delete
    began, and goes whatever bundle is at the name."""
    pid = _killed_at(run, pause)
    dst, rr = run["dst"], run["rr"]
    assert _files(dst) == run["reference"], "part of a run at its name"
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert retro.list_archive_dirs(rr, SEASON) == [dst]
    left = _beside(rr)
    assert len(left) == 1 and left[0].startswith(
        f"{dst.name}.dropping-{pid}-"), left
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr)
    assert str(e.value) == (f"{SEASON} from this bundle was already "
                            f"imported as {run['stamp']}.")
    assert _beside(rr) == [], "the dead process's aside was left"
    assert _files(dst) == run["reference"]


def test_a_replace_killed_between_its_two_renames_leaves_whole_trees(run):
    """Killed after the old run was set aside and before the new one went
    in: no part of a run at the name (no run there), the old run whole
    aside, the new one whole in its temp tree. A plain import then puts
    the old run back under its name (the sixth pass's review, finding 1:
    it used to delete it before anything new was known good), is refused
    as already imported and says so, and sweeps the dead temp tree."""
    pid = _killed_at(run, "rename")
    dst, rr = run["dst"], run["rr"]
    assert not (dst.exists() or dst.is_symlink())
    assert retro.list_archive_dirs(rr, SEASON) == []
    left = _beside(rr)
    assert len(left) == 2, left
    imp = next(n for n in left if ".importing-" in n)
    aside = next(n for n in left if ".replaced-" in n)
    assert imp.startswith(f"{dst.name}.importing-{pid}-")
    assert aside.startswith(f"{dst.name}.replaced-{pid}-")
    assert _files(rr / aside) == run["reference"]
    assert (rr / aside / rb.IMPORTED_MARK).is_file()
    assert _files(rr / imp) == run["reference"]
    marker = (rr / aside / rb.IMPORTED_MARK).read_bytes()
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr)
    assert str(e.value) == (
        f"{SEASON} from this bundle was already imported as {run['stamp']}. "
        "An earlier Replace stopped part way and left the run imported as "
        f"{run['stamp']} in {aside}; it is back under its own name now.")
    assert _files(dst) == run["reference"]
    assert (dst / rb.IMPORTED_MARK).read_bytes() == marker   # the old run
    assert retro.list_archive_dirs(rr, SEASON) == [dst]
    assert _beside(rr) == []


def test_a_live_replaces_aside_is_left_by_another_imports_sweep(run):
    """The old run's files are hours old, but the aside a live Replace
    holds is touched as it is set aside: another import's sweep leaves it,
    and the Replace, let go, finishes whole and leaves nothing beside."""
    dst, rr = run["dst"], run["rr"]
    when = time.time() - 3 * 3600.0
    for p in [dst, *dst.rglob("*")]:
        os.utime(p, (when, when))
    c = Replace(run, "rename")
    try:
        c.held()
        aside = [n for n in _beside(rr) if ".replaced-" in n]
        assert len(aside) == 1, _beside(rr)
        assert rb._sweep_stale_temps(dst) == []
        assert (rr / aside[0] / "run_meta.json").is_file()
        said = c.release()
    finally:
        if c.p.poll() is None:
            c.kill()
    assert said == {"said": "imported", "weeks": len(WEEKS)}, said
    assert _files(dst) == run["reference"]
    assert _beside(rr) == []


def _ended_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"], cwd=str(REPO))
    p.wait(30)
    return p.pid


def _aside(run, suffix: str) -> Path:
    """An old run of the run's own bundle (its imported.json, as the run
    at the name has it) under a name beside the run."""
    t = run["dst"].with_name(run["dst"].name + suffix)
    (t / "weeks" / WEEKS[0]).mkdir(parents=True)
    (t / "weeks" / WEEKS[0] / "samples.json").write_text("{}")
    (t / "run_meta.json").write_text("{}")
    (t / rb.IMPORTED_MARK).write_bytes(
        (run["dst"] / rb.IMPORTED_MARK).read_bytes())
    return t


def test_the_sweep_knows_only_an_asides_own_name(run):
    """A dead process's aside goes; a live one's stays; names that only
    look like one stay, however old."""
    dead = _aside(run, f".replaced-{_ended_pid()}-0a0b0c0d")
    live = _aside(run, f".replaced-{os.getppid()}-1a1b1c1d")
    others = [_aside(run, s) for s in (".replaced", ".replaced-x",
                                       ".replacedz", ".replaced-12-x")]
    when = time.time() - 3 * 3600.0
    for t in others:
        for p in [t, *t.rglob("*")]:
            os.utime(p, (when, when))
    gone = rb._sweep_stale_temps(run["dst"])
    assert gone == [dead]
    assert live.is_dir() and all(t.is_dir() for t in others)


def test_a_dead_replaces_aside_in_a_protected_folder_is_never_deleted(
        run, monkeypatch):
    """#104's rule holds for an aside: inside a protected folder it is
    never deleted. A plain import is refused as already imported and
    leaves it; a Replace is refused in words, nothing replaced; without
    the protection the refused plain import sweeps it."""
    dead = _aside(run, f".replaced-{_ended_pid()}-0a0b0c0d")
    held = _files(dead)
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(dead))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], run["rr"])
    assert str(e.value) == (f"{SEASON} from this bundle was already "
                            f"imported as {run['stamp']}.")
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], run["rr"], replace=True)
    assert str(e.value) == (
        f"An earlier import of {SEASON} left {dead.name} in a protected "
        "folder, which the console never deletes; nothing was imported.")
    assert _files(dead) == held
    assert _files(run["dst"]) == run["reference"]
    assert _beside(run["rr"]) == [dead.name]
    monkeypatch.delenv("FLUBNF_PROTECT_ROOTS")
    with pytest.raises(rb.BundleError):
        rb.import_bundle(run["bundle"], run["rr"])
    assert _beside(run["rr"]) == []


def test_a_replace_whose_new_tree_cannot_go_in_puts_the_old_run_back(
        run, monkeypatch):
    """The rename of the new tree fails with nothing at the name (a disk
    that refuses it): the old run goes back under its name, whole, and the
    disk's error is raised as before; nothing is left beside."""
    real = os.rename

    def rename(src, dst, *a, **k):
        if ".importing-" in Path(src).name:
            raise PermissionError(13, "Permission denied", str(src))
        return real(src, dst, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(PermissionError):
        rb.import_bundle(run["bundle"], run["rr"], replace=True)
    assert _files(run["dst"]) == run["reference"]
    assert (run["dst"] / rb.IMPORTED_MARK).is_file()
    assert _beside(run["rr"]) == []
