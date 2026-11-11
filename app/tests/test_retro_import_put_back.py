"""A Replace's old run, set aside while the new one goes in: the review of
#105 at 1ce301ed (the sixth pass) and the independent check beside it.

  F1. A Replace that started with nothing at the run's name never asked
      whether the folder is protected: a tree another import landed there
      meanwhile was set aside and deleted inside a protected folder. The
      second look asks again, in #104's words.
  F2. The sweep deleted a dead Replace's set-aside run, the only copy,
      before the new bundle was known good: killed between its two
      renames and retried with a damaged bundle, the retro root held no
      run at all. With nothing at the name the newest whole one now goes
      back under it, and the import says so; a set-aside run is deleted
      only once a whole import is at the name, never on age alone. Ctrl-C
      between the two renames puts it back at once, and a put-back that
      fails says where the run is.
  F3. A rename-in that failed because something was at the name deleted
      the old run, taking that something for another import's whole tree.
      The old run is dropped only for this bundle's whole import (its
      imported.json with this bundle's sha256); otherwise it stays aside
      and the refusal names the folder. Nothing at the name is deleted.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from test_retro_archive import SEASON                      # noqa: E402
from test_retro_import_directory_and_swap import (         # noqa: E402
    W3, WEEKS, _beside, _bundle, _changed, _ended_pid, _files, _killed_at)

LATER = 2 * rb.STALE_TEMP_S


@pytest.fixture
def run(tmp_path):
    """A bundle imported once (the run a Replace replaces) and the tree
    one import of it alone makes (the reference). The keys
    test_retro_import_directory_and_swap's Replace helper reads."""
    bundle = _bundle(tmp_path)
    m = rb.inspect_bundle(bundle)
    ref = rb.import_bundle(bundle, tmp_path / "reference").root
    rr = tmp_path / "retro"
    rr.mkdir()
    first = rb.import_bundle(bundle, rr)
    return {"tmp": tmp_path, "bundle": bundle, "stamp": m["stamp"],
            "rr": rr, "dst": first.root, "reference": _files(ref)}


def _set_aside(run, pid: int, tag: str = "0a0b0c0d") -> Path:
    """The run moved aside as a Replace does (a process `pid`'s), nothing
    left at its name."""
    dst = run["dst"]
    aside = dst.with_name(f"{dst.name}.replaced-{pid}-{tag}")
    os.rename(dst, aside)
    return aside


def _back_words(run, aside: Path) -> str:
    return (f"An earlier Replace stopped part way and left the run imported "
            f"as {run['stamp']} in {aside.name}; it is back under its own "
            "name now.")


def _already(run) -> str:
    return (f"{SEASON} from this bundle was already imported as "
            f"{run['stamp']}.")


def _stray(at: Path) -> dict:
    """What a season page's render can make at a run's name: one map card
    (the independent check's probe)."""
    p = at / "playback_cache" / "map_cards" / f"{WEEKS[3]}.json"
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    return _files(at)


# ------------------------------------------- F1. protected, second look

def test_a_tree_landing_in_a_protected_folder_during_a_replace_is_kept(
        tmp_path, monkeypatch):
    """The retro root is protected and nothing is at the run's name when a
    Replace starts; another process's import of the bundle lands its whole
    tree there while this one extracts. The Replace is refused in #104's
    words at the second look; that tree is neither set aside nor deleted,
    and this one's temp tree is gone."""
    bundle = _bundle(tmp_path)
    m = rb.inspect_bundle(bundle)
    theirs = rb.import_bundle(bundle, tmp_path / "theirs").root
    rr = tmp_path / "retro"
    rr.mkdir()
    dst = retro.archive_dir(rr, SEASON, m["stamp"])
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(rr))
    real, n = rb._extract_member, [0]

    def extract(z, name, d, *a):
        real(z, name, d, *a)
        n[0] += 1
        if n[0] == 1:
            shutil.copytree(theirs, dst)      # the other import's rename
    monkeypatch.setattr(rb, "_extract_member", extract)
    deleted, real_delete = [], retro.delete_tree

    def delete_tree(p):
        deleted.append(Path(p))
        real_delete(p)
    monkeypatch.setattr(retro, "delete_tree", delete_tree)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bundle, rr, replace=True)
    assert str(e.value) == (
        f"{SEASON} from this bundle is imported as {m['stamp']} in a "
        "protected folder, which the console never deletes; nothing was "
        "replaced.")
    assert deleted == []
    assert _files(dst) == _files(theirs)
    assert ((dst / rb.IMPORTED_MARK).read_bytes()
            == (theirs / rb.IMPORTED_MARK).read_bytes())
    assert _beside(rr) == []


# --------------------------------------- F2. put back, never deleted

def test_a_replace_killed_between_its_renames_then_a_damaged_bundle_keeps_the_run(  # noqa: E501
        run):
    """The review's case, with a real SIGKILL: the old run is aside, the
    name empty. A Replace with a damaged bundle then puts the old run back
    first, is refused as damaged, and says the run is back: the retro root
    holds the run, whole, and nothing beside it."""
    _killed_at(run, "rename")
    dst, rr = run["dst"], run["rr"]
    assert not (dst.exists() or dst.is_symlink())
    aside = rr / next(n for n in _beside(rr) if ".replaced-" in n)
    marker = (aside / rb.IMPORTED_MARK).read_bytes()
    bad = _changed(run["bundle"], f"weeks/{W3}/samples.json", "encrypted",
                   run["tmp"] / "bad.zip")
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bad, rr, replace=True)
    assert str(e.value) == (
        f"bad.zip: weeks/{W3}/samples.json could not be unpacked; the bundle "
        f"is damaged or altered. {_back_words(run, aside)}")
    assert _files(dst) == run["reference"]
    assert (dst / rb.IMPORTED_MARK).read_bytes() == marker
    assert retro.list_archive_dirs(rr, SEASON) == [dst]
    assert _beside(rr) == []


def test_a_set_aside_run_an_hour_old_goes_back_not_away(run):
    """A put-back that failed in a console that stays up: its process
    lives, and an hour on the sweep finds the run aside with nothing at its
    name. It is renamed back, not deleted."""
    aside = _set_aside(run, os.getpid())
    restored = []
    gone = rb._sweep_stale_temps(run["dst"], now=time.time() + LATER,
                                 restored=restored)
    assert gone == [] and restored == [aside]
    assert _files(run["dst"]) == run["reference"]
    assert _beside(run["rr"]) == []


def test_of_several_set_aside_runs_the_newest_goes_back(run):
    """Three stopped Replaces left three copies aside, nothing at the name:
    the newest goes back; the others, older copies of the same import, are
    leftovers once a whole import is at the name."""
    dst, pid = run["dst"], _ended_pid()
    copies = []
    for i, hours in enumerate((3, 1, 2)):
        a = dst.with_name(f"{dst.name}.replaced-{pid}-{i:08x}")
        shutil.copytree(dst, a)
        (a / "which.txt").write_text(str(i))
        when = time.time() - hours * 3600.0
        for p in [a, *a.rglob("*")]:
            os.utime(p, (when, when))
        copies.append(a)
    retro.delete_tree(dst)
    restored = []
    gone = rb._sweep_stale_temps(dst, restored=restored)
    assert restored == [copies[1]]
    assert (dst / "which.txt").read_text() == "1"
    assert sorted(gone) == [copies[0], copies[2]]
    assert _beside(run["rr"]) == []


@pytest.mark.parametrize("at_name", ["nothing", "something else"])
def test_a_set_aside_run_is_never_deleted_on_age_while_no_whole_import_is_there(  # noqa: E501
        run, at_name):
    """The age rule exempts a set-aside run while the name holds no whole
    import: nothing there (and this copy, its imported.json gone, is not
    whole enough to put back), or something that is not an import. Once an
    import is whole at the name, the next sweep removes it."""
    dst, rr = run["dst"], run["rr"]
    aside = _set_aside(run, os.getpid())
    if at_name == "nothing":
        (aside / rb.IMPORTED_MARK).unlink()
    else:
        _stray(dst)
    held = _files(aside)
    restored = []
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER,
                                 restored=restored) == []
    assert restored == [] and _files(aside) == held
    if at_name != "nothing":
        retro.delete_tree(dst)                 # the stray, cleared by hand
    r = rb.import_bundle(run["bundle"], rr)
    assert r.root == dst and _files(dst) == run["reference"]
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER) == [aside]
    assert _beside(rr) == []


def test_a_put_back_another_process_made_first_is_done_not_an_error(
        run, monkeypatch):
    """Two processes sweep at once (the import lock is per process): the
    other renames the run back first, and this one's rename finds nothing
    to move. That is done: the import is refused as already imported, no
    raw FileNotFoundError, nothing deleted."""
    dst = run["dst"]
    aside = _set_aside(run, _ended_pid())
    real = os.rename

    def rename(src, d, *a, **k):
        if Path(src) == aside and Path(d) == dst:
            real(src, d, *a, **k)              # the other process's sweep
            raise FileNotFoundError(2, "No such file or directory", str(src))
        return real(src, d, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], run["rr"])
    assert str(e.value) == _already(run)
    assert _files(dst) == run["reference"]
    assert _beside(run["rr"]) == []


def test_ctrl_c_between_the_two_renames_puts_the_old_run_back(
        run, monkeypatch):
    """Ctrl-C after the old run was set aside and before the new tree went
    in (the review's finding 2): the old run is back under its name at
    once, the new temp tree removed."""
    dst = run["dst"]
    marker = (dst / rb.IMPORTED_MARK).read_bytes()
    real = os.rename

    def rename(src, d, *a, **k):
        if ".importing-" in Path(src).name:
            raise KeyboardInterrupt
        return real(src, d, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(KeyboardInterrupt):
        rb.import_bundle(run["bundle"], run["rr"], replace=True)
    assert _files(dst) == run["reference"]
    assert (dst / rb.IMPORTED_MARK).read_bytes() == marker
    assert _beside(run["rr"]) == []


def test_a_put_back_that_fails_says_where_the_old_run_is(run, monkeypatch):
    """The new tree cannot go in and the old run cannot go back (two
    renames refused in a row): the refusal names the folder the old run is
    in, whole, instead of a raw error about the temp tree. An hour on, the
    sweep puts it back rather than deleting it."""
    dst, rr = run["dst"], run["rr"]
    real = os.rename

    def rename(src, d, *a, **k):
        if any(s in Path(src).name for s in (".importing-", ".replaced-")):
            raise PermissionError(13, "Permission denied", str(src))
        return real(src, d, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr, replace=True)
    left = _beside(rr)
    assert len(left) == 1 and ".replaced-" in left[0], left
    aside = rr / left[0]
    said = str(e.value)
    assert said.startswith(
        f"{SEASON} from this bundle could not be put in place "
        "(PermissionError: [Errno 13] Permission denied: "), said
    assert said.endswith(
        "), and the run it was to replace could not go back under its name "
        f"either; that run is kept in {aside}, and nothing was imported."), \
        said
    assert not (dst.exists() or dst.is_symlink())
    assert _files(aside) == run["reference"]
    monkeypatch.undo()
    restored = []
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER,
                                 restored=restored) == []
    assert restored == [aside]
    assert _files(dst) == run["reference"]


def test_in_a_protected_folder_the_run_goes_back_and_nothing_is_deleted(
        run, monkeypatch):
    """#104's rule holds: a killed Replace's leftovers in a protected
    folder. The old run is renamed back (nothing deleted); the dead temp
    tree beside it is left, and the import is refused in #104's words and
    says the run is back."""
    dst, rr = run["dst"], run["rr"]
    pid = _ended_pid()
    aside = _set_aside(run, pid)
    imp = dst.with_name(f"{dst.name}.importing-{pid}-1a1b1c1d")
    shutil.copytree(aside, imp)
    monkeypatch.setenv("FLUBNF_PROTECT_ROOTS", str(rr))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr)
    assert str(e.value) == (
        f"An earlier import of {SEASON} left {imp.name} in a protected "
        "folder, which the console never deletes; nothing was imported. "
        + _back_words(run, aside))
    assert _files(dst) == run["reference"]
    assert _beside(rr) == [imp.name]
    assert _files(imp) == run["reference"]


def test_a_delete_of_the_old_run_stopped_part_way_is_never_put_back(
        run, monkeypatch):
    """A Replace stopped part way through deleting the old run it set
    aside (the new run already whole at the name): that run's imported.json
    went first, so once the run is deleted from Storage, the next import
    does not put the part left back as a run; it lands from the bundle."""
    dst, rr = run["dst"], run["rr"]
    real = retro.delete_tree

    def stopped(p):
        if ".replaced-" in Path(p).name:
            shutil.rmtree(Path(p) / "weeks")
            raise KeyboardInterrupt
        return real(p)
    monkeypatch.setattr(retro, "delete_tree", stopped)
    with pytest.raises(KeyboardInterrupt):
        rb.import_bundle(run["bundle"], rr, replace=True)
    monkeypatch.undo()
    assert _files(dst) == run["reference"]
    part = rr / _beside(rr)[0]
    assert not (part / "weeks").exists()
    os.rename(part, dst.with_name(f"{dst.name}.replaced-{_ended_pid()}-"
                                  "0a0b0c0d"))       # its process ended
    retro.delete_tree(dst)                           # Storage's Delete
    r = rb.import_bundle(run["bundle"], rr)
    assert r.root == dst and _files(dst) == run["reference"]


def test_a_sweep_stopped_part_way_through_an_old_run_never_puts_it_back(
        run, monkeypatch):
    """The same for the sweep's own removal of a dead Replace's leftover:
    stopped part way, the part left is never put back as a run."""
    dst, rr = run["dst"], run["rr"]
    left = dst.with_name(f"{dst.name}.replaced-{_ended_pid()}-0a0b0c0d")
    shutil.copytree(dst, left)
    real = shutil.rmtree

    def stopped(p, *a, **k):
        if Path(p) == left:
            real(Path(p) / "weeks")
            raise KeyboardInterrupt
        return real(p, *a, **k)
    monkeypatch.setattr(shutil, "rmtree", stopped)
    with pytest.raises(KeyboardInterrupt):
        rb._sweep_stale_temps(dst)
    monkeypatch.undo()
    assert left.is_dir() and not (left / "weeks").exists()
    retro.delete_tree(dst)
    r = rb.import_bundle(run["bundle"], rr)
    assert r.root == dst and _files(dst) == run["reference"]


# ------------------------------------- F3. only a whole import stands

@pytest.mark.parametrize("what", ["map card", "another bundle's import"])
def test_something_else_at_the_name_keeps_the_old_run_aside(
        run, monkeypatch, what):
    """Right after the old run is set aside, something that is not this
    bundle's import appears at the name: a map card a page wrote (the
    independent check's probe), or an import whose imported.json names
    another bundle. The new tree cannot go in; the old run is kept aside,
    whole, and the refusal names its folder; what is at the name is left
    as it is. While the map card stays (no imported.json at the name), the
    sweep never deletes the old run, however old."""
    dst, rr = run["dst"], run["rr"]
    other = run["tmp"] / "other"
    if what == "another bundle's import":
        shutil.copytree(dst, other)
        info = json.loads((other / rb.IMPORTED_MARK).read_text())
        info["bundle_sha256"] = "0" * 64
        (other / rb.IMPORTED_MARK).write_text(json.dumps(info))
    real = rb._move_aside
    there = {}

    def move(d):
        a = real(d)
        if what == "map card":
            there.update(_stray(d))
        else:
            shutil.copytree(other, d)
            there.update(_files(d))
        return a
    monkeypatch.setattr(rb, "_move_aside", move)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr, replace=True)
    left = _beside(rr)
    assert len(left) == 1 and ".replaced-" in left[0], left
    aside = rr / left[0]
    assert str(e.value) == (
        f"{SEASON} from this bundle was not imported: something that is not "
        f"this bundle's import appeared at {dst} while it was imported, so "
        "the run it was to replace could not go back under its name; that "
        f"run is kept in {aside}.")
    assert _files(aside) == run["reference"]
    assert (aside / rb.IMPORTED_MARK).is_file()
    assert _files(dst) == there
    if what == "map card":
        assert rb._sweep_stale_temps(dst, now=time.time() + LATER) == []
        assert _files(aside) == run["reference"]


def test_a_run_put_back_then_kept_aside_is_not_said_to_be_back(
        run, monkeypatch):
    """A dead Replace's old run is put back by this Replace's sweep, set
    aside again, and then cannot go back (a map card at the name): the
    refusal names the folder it is kept in, and does not also say it is
    back under its name."""
    dst, rr = run["dst"], run["rr"]
    _set_aside(run, _ended_pid())
    real = rb._move_aside

    def move(d):
        a = real(d)
        _stray(d)
        return a
    monkeypatch.setattr(rb, "_move_aside", move)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr, replace=True)
    left = _beside(rr)
    assert len(left) == 1 and ".replaced-" in left[0], left
    assert str(e.value) == (
        f"{SEASON} from this bundle was not imported: something that is not "
        f"this bundle's import appeared at {dst} while it was imported, so "
        "the run it was to replace could not go back under its name; that "
        f"run is kept in {rr / left[0]}.")
    assert _files(rr / left[0]) == run["reference"]


@pytest.mark.parametrize("replace", [False, True])
def test_something_else_at_the_rename_is_named_not_called_an_import(
        tmp_path, monkeypatch, replace):
    """Nothing to set aside, and something that is not an import appears
    at the name just before the rename: the refusal says so, rather than
    "already imported" or "another import ... stands", and leaves it."""
    bundle = _bundle(tmp_path)
    m = rb.inspect_bundle(bundle)
    rr = tmp_path / "retro"
    rr.mkdir()
    dst = retro.archive_dir(rr, SEASON, m["stamp"])
    real = os.rename
    there = {}

    def rename(src, d, *a, **k):
        if ".importing-" in Path(src).name and Path(d) == dst:
            there.update(_stray(dst))
        return real(src, d, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bundle, rr, replace=replace)
    assert str(e.value) == (
        f"{SEASON} from this bundle was not imported: something that is not "
        f"this bundle's import appeared at {dst} while it was imported, and "
        "it was left as it is.")
    assert _files(dst) == there
    assert _beside(rr) == []
