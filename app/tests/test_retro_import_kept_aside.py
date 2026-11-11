"""An old run a Replace set aside stays while the run's name holds another
bundle's import, and every import of the run says where it is (the
seventh pass's check, 2026-11-10 night, and the reviewer's ruling on it).

The pass before refused a Replace with "that run is kept in <aside>" when
another bundle's import (another sha256) stood at the name, and the next
import's sweep then deleted that aside: it counted the name as whole when
an imported.json was there at all. The sweep now deletes an old run set
aside only when the name holds a whole import of the SAME bundle as it
(both imported.json files name one bundle_sha256), and never on a value
missing or unreadable on either side. The cost is a leak the reviewer
accepted: a Replace with another file of the same season and stamp (a
bundle zipped again), stopped after its new run went in and before the
old one was deleted, leaves the old run aside for good, in no Storage
row. So every import of that season and stamp, plain or Replace, refused
or not, says in one sentence where it is and that it can be deleted by
hand once the run at the name is the one wanted. Nothing is deleted for
it.

An old run let go once the new one stood is renamed .dropping- before its
delete begins, so a delete stopped part way leaves a tree the sweep
removes by that name, whatever bundle is at the run's name.
"""
import json
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from app.core import replay_bundle as rb                   # noqa: E402
from app.core import retro                                 # noqa: E402
from test_retro_archive import SEASON                      # noqa: E402
from test_retro_import_directory_and_swap import (         # noqa: E402
    _beside, _bundle, _ended_pid, _files, _flash, client, world)  # noqa: F401
from test_retro_import_put_back import run                 # noqa: E402,F401
from app.ui import state as ui_state                       # noqa: E402

LATER = 2 * rb.STALE_TEMP_S
OTHER_SHA = "0" * 64


def _already(run) -> str:
    return (f"{SEASON} from this bundle was already imported as "
            f"{run['stamp']}.")


def _kept_words(stamp: str, asides: list) -> str:
    if len(asides) == 1:
        return (f"An earlier Replace set a run of {SEASON} aside in "
                f"{asides[0]}, and the console keeps it there: it can be "
                f"deleted by hand once the run imported as {stamp} is the "
                "one wanted.")
    where = ", ".join(str(p) for p in asides[:-1]) + f" and {asides[-1]}"
    return (f"Earlier Replaces set runs of {SEASON} aside in {where}, and "
            "the console keeps them there: they can be deleted by hand "
            f"once the run imported as {stamp} is the one wanted.")


def _note(words: str) -> str:
    """The same as an ImportResult's warning (a clause, as the others)."""
    return words[:1].lower() + words[1:].rstrip(".")


def _sha_at(root: Path) -> str:
    return json.loads((root / rb.IMPORTED_MARK).read_text())["bundle_sha256"]


def _of_another_bundle(src: Path, at: Path) -> Path:
    """A copy of the import at `src` whose imported.json names another
    bundle (another file of the same season and stamp)."""
    shutil.copytree(src, at)
    info = json.loads((at / rb.IMPORTED_MARK).read_text())
    info["bundle_sha256"] = OTHER_SHA
    (at / rb.IMPORTED_MARK).write_text(json.dumps(info))
    return at


def _ended(aside: Path) -> Path:
    """The aside as the process that set it aside, now ended, leaves it."""
    dead = aside.with_name(aside.name.replace(f"-{os.getpid()}-",
                                              f"-{_ended_pid()}-"))
    os.rename(aside, dead)
    return dead


def _zipped_again(bundle: Path, out_dir: Path) -> Path:
    """The same export zipped again: another file (another sha256), the
    same season, stamp and members. What a Replace is for."""
    out_dir.mkdir()
    out = out_dir / bundle.name
    with zipfile.ZipFile(bundle) as z, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
        for i in z.infolist():
            w.writestr(i.filename, z.read(i.filename),
                       compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
        w.comment = b"zipped again"
    return out


# ------------------------------------- the refusal's kept run stays kept

@pytest.mark.parametrize("ended", [True, False])
def test_a_run_a_refusal_says_is_kept_is_kept_and_named_again(
        run, monkeypatch, ended):
    """The check's case: a Replace sets the old run aside, another bundle's
    import lands at the name, and the Replace is refused with "that run is
    kept in <aside>". The user tries a plain import again, once the
    Replace's process has ended (a terminal's) or in the same console:
    refused as already imported, with one sentence naming the folder the
    run is kept in. It stays, whole, an hour on as well."""
    dst, rr = run["dst"], run["rr"]
    other = _of_another_bundle(dst, run["tmp"] / "other")
    real = rb._move_aside

    def move(d, *rest):
        a = real(d, *rest)
        shutil.copytree(other, d)
        return a
    monkeypatch.setattr(rb, "_move_aside", move)
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr, replace=True)
    monkeypatch.undo()
    left = _beside(rr)
    assert len(left) == 1 and ".replaced-" in left[0], left
    aside = rr / left[0]
    said = str(e.value)
    assert said.endswith(f"that run is kept in {aside}."), said
    assert said.count(str(aside)) == 1            # named once, as its own
    assert _files(aside) == run["reference"]
    if ended:
        aside = _ended(aside)
    with pytest.raises(rb.BundleError) as e2:
        rb.import_bundle(run["bundle"], rr)
    assert str(e2.value) == (_already(run) + " "
                             + _kept_words(run["stamp"], [aside]))
    assert _files(aside) == run["reference"]
    assert (aside / rb.IMPORTED_MARK).is_file()
    assert _sha_at(dst) == OTHER_SHA
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER) == []
    assert _files(aside) == run["reference"]
    assert _beside(rr) == [aside.name]


@pytest.mark.parametrize("where,how", [
    ("aside", "no imported.json"), ("aside", "no value"),
    ("aside", "unreadable"), ("aside", "not a string"),
    ("run", "no value"), ("run", "unreadable"), ("both", "no value")])
def test_a_bundle_value_missing_on_either_side_keeps_the_old_run(
        run, where, how):
    """The reviewer's ruling, point 1: the sweep never deletes an old run
    set aside on a missing value. An old run of the run's own bundle,
    left by a dead Replace an hour ago, stays when its imported.json, or
    the run's at the name, names no bundle or cannot be read (no two empty
    values count as one bundle); every import names it."""
    dst, rr = run["dst"], run["rr"]
    aside = dst.with_name(f"{dst.name}.replaced-{_ended_pid()}-0a0b0c0d")
    shutil.copytree(dst, aside)
    for root in {"aside": [aside], "run": [dst],
                 "both": [aside, dst]}[where]:
        mark = root / rb.IMPORTED_MARK
        if how == "no imported.json":
            mark.unlink()
        elif how == "unreadable":
            mark.write_text("{not json")
        else:
            info = json.loads(mark.read_text())
            if how == "no value":
                del info["bundle_sha256"]
            else:
                info["bundle_sha256"] = [info["bundle_sha256"]]
            mark.write_text(json.dumps(info))
    held = _files(aside)
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER) == []
    assert _files(aside) == held
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], rr)
    assert str(e.value) == _already(run) + " " + _kept_words(run["stamp"],
                                                             [aside])
    assert _files(aside) == held and _beside(rr) == [aside.name]


# ------------------------------------- the leak the ruling accepts, named

def test_a_replace_with_another_file_stopped_before_its_drop_is_named(
        run, monkeypatch):
    """A Replace's proper use: the same export zipped again, imported over
    the run. Stopped after its new run went in and before the old one was
    deleted (Ctrl-C there, a kill), the old run stays aside for good: the
    name holds another bundle's import. Every import of the run, plain or
    Replace, refused or not, says where it is; nothing deletes it. Once
    the name holds its own bundle's import again, the sweep removes it."""
    dst, rr = run["dst"], run["rr"]
    again = _zipped_again(run["bundle"], run["tmp"] / "again")
    m2 = rb.inspect_bundle(again)
    m1 = rb.inspect_bundle(run["bundle"])
    assert (m2["season"], m2["stamp"]) == (m1["season"], m1["stamp"])
    assert m2["bundle_sha256"] != m1["bundle_sha256"]

    def stopped(*a):
        raise KeyboardInterrupt
    monkeypatch.setattr(rb, "_drop_aside", stopped)
    with pytest.raises(KeyboardInterrupt):
        rb.import_bundle(again, rr, replace=True)
    monkeypatch.undo()
    assert _sha_at(dst) == m2["bundle_sha256"]
    assert _files(dst) == run["reference"]
    left = _beside(rr)
    assert len(left) == 1 and ".replaced-" in left[0], left
    aside = _ended(rr / left[0])
    assert _sha_at(aside) == m1["bundle_sha256"]
    words = _kept_words(run["stamp"], [aside])
    for bundle in (run["bundle"], again):
        with pytest.raises(rb.BundleError) as e:
            rb.import_bundle(bundle, rr)
        assert str(e.value) == _already(run) + " " + words
    r = rb.import_bundle(again, rr, replace=True)
    assert r.root == dst and _note(words) in r.warnings
    assert rb._sweep_stale_temps(dst, now=time.time() + LATER) == []
    assert _files(aside) == run["reference"]
    assert _sha_at(aside) == m1["bundle_sha256"]
    # its own bundle at the name again: no longer kept, and it goes
    r = rb.import_bundle(run["bundle"], rr, replace=True)
    assert _sha_at(dst) == m1["bundle_sha256"]
    assert not any("aside in" in w for w in r.warnings), r.warnings
    assert rb._sweep_stale_temps(dst) == [aside]
    assert _beside(rr) == []


def test_the_console_and_the_terminal_say_where_the_kept_run_is(world):
    """Through the import form (the refusal's flash, and a Replace's note)
    and `flubnf retro import` (refused: one line, exit 2; imported: a
    note line)."""
    from flubnf.cli import app as cli_app
    rr, dst = world["rr"], world["dst"]
    rb.import_bundle(world["bundle"], rr)
    aside = _of_another_bundle(
        dst, dst.with_name(f"{dst.name}.replaced-{_ended_pid()}-0a0b0c0d"))
    words = _kept_words(world["stamp"], [aside])
    already = (f"{SEASON} from this bundle was already imported as "
               f"{world['stamp']}.")
    r = client.post("/retro/import", data={"path": str(world["bundle"])},
                    follow_redirects=False)
    assert r.status_code == 303
    assert _flash() == f"Not imported: {already} {words}"
    r = client.post("/retro/import", data={"path": str(world["bundle"]),
                                           "replace": "1"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert ui_state._status.get("flash_kind") == "warn"
    detail = ui_state._status.get("flash_detail") or ""
    assert " Note: " in detail and detail.endswith(f"{_note(words)}."), \
        detail
    res = CliRunner().invoke(cli_app, ["retro", "import",
                                       str(world["bundle"]), "--root",
                                       str(rr)])
    assert res.exit_code == 2, res.output
    assert f"refused: {already} {words}" in res.output, res.output
    res = CliRunner().invoke(cli_app, ["retro", "import",
                                       str(world["bundle"]), "--root",
                                       str(rr), "--replace"])
    assert res.exit_code == 0, res.output
    assert f"  note: {_note(words)}" in res.output, res.output
    assert _files(aside) == _files(dst)
    assert _sha_at(aside) == OTHER_SHA


def test_only_an_old_run_no_replace_is_using_is_named(run):
    """A live Replace's aside (another process, written just now) is in
    use: not named until it is an hour old. This process's own earlier one
    is named (imports into one run take turns here), and the one an import
    sets aside itself is left to its own words. An old run of the bundle
    at the name is not kept, so not named."""
    dst = run["dst"]

    def at(pid: int, tag: str, other: bool = True) -> Path:
        a = dst.with_name(f"{dst.name}.replaced-{pid}-{tag}")
        if other:
            return _of_another_bundle(dst, a)
        shutil.copytree(dst, a)
        return a
    live = at(os.getppid(), "1a1b1c1d")
    mine = at(os.getpid(), "2a2b2c2d")
    dead = at(_ended_pid(), "3a3b3c3d")
    at(_ended_pid(), "4a4b4c4d", other=False)
    assert rb._asides_left(dst) == sorted([mine, dead])
    assert rb._asides_left(dst, but=[mine]) == [dead]
    assert rb._asides_left(dst, now=time.time() + LATER) == \
        sorted([live, mine, dead])
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(run["bundle"], run["rr"])
    assert str(e.value) == _already(run) + " " + _kept_words(
        run["stamp"], sorted([mine, dead]))
    assert live.is_dir() and mine.is_dir() and dead.is_dir()


# -------------------------------- an old run let go: .dropping-, then gone

def test_a_run_let_go_and_left_part_deleted_goes_whatever_is_at_the_name(
        run):
    """A dead Replace's delete of the old run it let go, stopped part way:
    the part left (its imported.json already gone) is under the .dropping-
    name, and the sweep removes it, though the name holds another bundle's
    import now."""
    dst, rr = run["dst"], run["rr"]
    part = dst.with_name(f"{dst.name}.dropping-{_ended_pid()}-0a0b0c0d")
    shutil.copytree(dst, part)
    (part / rb.IMPORTED_MARK).unlink()
    shutil.rmtree(part / "weeks")
    info = json.loads((dst / rb.IMPORTED_MARK).read_text())
    info["bundle_sha256"] = OTHER_SHA
    (dst / rb.IMPORTED_MARK).write_text(json.dumps(info))
    assert rb._sweep_stale_temps(dst) == [part]
    assert _beside(rr) == []
    assert _files(dst) == run["reference"]


def test_a_rename_the_disk_refuses_deletes_the_run_let_go_where_it_is(
        run, monkeypatch):
    """The old run, let go once the new one stood, cannot be renamed
    .dropping- (a disk that refuses it): it is deleted where it is, as
    before, and nothing is left beside."""
    dst, rr = run["dst"], run["rr"]
    real = os.rename

    def rename(src, d, *a, **k):
        if ".dropping-" in Path(d).name:
            raise PermissionError(13, "Permission denied", str(src))
        return real(src, d, *a, **k)
    monkeypatch.setattr(os, "rename", rename)
    r = rb.import_bundle(run["bundle"], rr, replace=True)
    assert r.root == dst and _files(dst) == run["reference"]
    assert _beside(rr) == []
    assert retro.list_archive_dirs(rr, SEASON) == [dst]
