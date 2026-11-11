"""Three S3s from the review of #105 at cee2fb5f (findings 2 to 4, and
the note on the Run form).

  * A bundle damaged inside a compressed member gave a 500 page: the
    extraction let zipfile.BadZipFile and zlib.error through, as
    inspect_bundle does not. Both are now refused in words as a damaged
    bundle, nothing written; a damaged manifest member too.
  * A delete refused because an import's Replace holds the archived run
    said the run "is already being deleted". It says "is already being
    deleted or replaced"; the Run form's discard and archive never put
    that answer into their "still being prepared" sentence.
  * Two uploads in one millisecond shared incoming-<pid>-<ms>.zip; the
    second's clean-up deleted the first's file. The name now carries a
    random part.
"""
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

import app.core.runs as runs_mod                           # noqa: E402
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

W3 = "2098-01-17"
WEEKS = ["2098-01-03", "2098-01-10", W3]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A retro root (test_retro_archive's), the exports folder under this
    test's state, and a bundle of three weeks made on "another machine"
    whose samples are real deflate streams. Status stores restored
    after."""
    status = dict(ui_state._status)
    rstatus = dict(ui_retro_seasons._retro_status)
    claims = dict(ui_retro_seasons._retro_claim_at)
    rr = _roots(tmp_path, monkeypatch)
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    ui_state._status.update({"running": None, "flash": "",
                             "flash_detail": ""})
    ui_shared._invalidate_scans()
    src = tmp_path / "elsewhere"
    src.mkdir()
    root = _season_tree(src, SEASON, weeks=WEEKS)
    for w in WEEKS:
        (root / "weeks" / w / "samples.json").write_text(json.dumps(
            {"asof": w, "pf": {"Ohio": {str(h): [float(i * h % 89)
                                                 for i in range(300)]
                                        for h in range(5)}}}))
    bundle = rb.export_season(root, SEASON, tmp_path / "out")
    yield {"tmp": tmp_path, "rr": rr, "bundle": bundle,
           "stamp": rb.inspect_bundle(bundle)["stamp"]}
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


# ---------------------------------- a member damaged inside (finding 2)

def _damaged(bundle: Path, member: str, out: Path) -> Path:
    """A copy of `bundle` with one byte flipped half way into `member`'s
    compressed bytes (its manifest entry, sizes and the zip's directory
    untouched)."""
    import zipfile
    data = bytearray(bundle.read_bytes())
    with zipfile.ZipFile(bundle) as z:
        info = z.getinfo(member)
    assert info.compress_type == zipfile.ZIP_DEFLATED
    assert info.compress_size > 200
    ho = info.header_offset
    start = (ho + 30 + int.from_bytes(data[ho + 26:ho + 28], "little")
             + int.from_bytes(data[ho + 28:ho + 30], "little"))
    data[start + info.compress_size // 2] ^= 0xFF
    out.write_bytes(bytes(data))
    return out


def _nothing_written(rr: Path) -> None:
    assert [p.name for p in rr.iterdir()] == [], \
        sorted(p.name for p in rr.iterdir())


def test_a_bundle_damaged_inside_a_member_is_refused_in_words(world):
    member = f"weeks/{W3}/samples.json"
    bad = _damaged(world["bundle"], member, world["tmp"] / "bad.zip")
    rb.inspect_bundle(bad)                 # its table of contents is sound
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bad, world["rr"], name="mine.flubnf-replay.zip")
    assert str(e.value) == (f"mine.flubnf-replay.zip: {member} could not "
                            "be unpacked; the bundle is damaged or altered.")
    _nothing_written(world["rr"])


def test_the_import_form_refuses_a_damaged_member_without_a_500(world):
    """Through the route, by path and by upload: a refusal in words and
    the index, never a 500 page; nothing written, the upload's copy
    removed."""
    member = f"weeks/{W3}/samples.json"
    bad = _damaged(world["bundle"], member, world["tmp"] / "bad.zip")
    _clear_flash()
    r = client.post("/retro/import", data={"path": str(bad)},
                    follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert r.headers["location"] == "/retro"
    assert _flash() == (f"Not imported: bad.zip: {member} could not be "
                        "unpacked; the bundle is damaged or altered.")
    assert ui_state._status.get("flash_kind") == "warn"
    _clear_flash()
    with open(bad, "rb") as f:
        r = client.post("/retro/import",
                        files={"file": ("theirs.flubnf-replay.zip", f,
                                        "application/zip")},
                        follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert _flash() == ("Not imported: theirs.flubnf-replay.zip: "
                        f"{member} could not be unpacked; the bundle is "
                        "damaged or altered.")
    _nothing_written(world["rr"])
    assert not list((runs_mod.APP_STATE / "exports").glob("incoming-*"))


def test_a_damaged_manifest_member_is_refused_in_words(world):
    bad = _damaged(world["bundle"], rb.MANIFEST, world["tmp"] / "bad.zip")
    with pytest.raises(rb.BundleError) as e:
        rb.inspect_bundle(bad)
    assert str(e.value) == ("bad.zip: manifest.json could not be unpacked; "
                            "the bundle is damaged or altered.")
    _clear_flash()
    r = client.post("/retro/import", data={"path": str(bad)},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/retro"
    assert _flash() == ("Not imported: bad.zip: manifest.json could not be "
                        "unpacked; the bundle is damaged or altered.")
    _nothing_written(world["rr"])


def _without(bundle: Path, member: str) -> None:
    """`bundle` written again in place without `member` (the file changed
    on disk: another copy saved over it)."""
    import zipfile
    tmp = bundle.with_name(bundle.name + ".part")
    with zipfile.ZipFile(bundle) as z, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as w:
        for i in z.infolist():
            if i.filename != member:
                w.writestr(i, z.read(i.filename))
    tmp.replace(bundle)


@pytest.mark.parametrize("via", ["import", "route", "terminal"])
def test_a_member_gone_since_the_inspection_is_refused_in_words(
        world, monkeypatch, via):
    """The seventh pass's finding 4: the bundle file changes between the
    inspection and the import, and one member is no longer in it. The
    import's z.getinfo raised a raw KeyError, which neither the import
    form nor `flubnf retro import` catches (they catch BundleError and
    OSError). It is refused as a damaged bundle, in the same words, and
    nothing is left under the retro root."""
    from typer.testing import CliRunner
    from flubnf.cli import app as cli_app
    member = f"weeks/{W3}/samples.json"
    bundle, rr = world["bundle"], world["rr"]
    real = rb.inspect_bundle

    def inspect(path, name=""):
        m = real(path, name)
        _without(Path(path), member)
        return m
    monkeypatch.setattr(rb, "inspect_bundle", inspect)
    said = (f"{bundle.name}: {member} could not be unpacked; the bundle is "
            "damaged or altered.")
    if via == "import":
        with pytest.raises(rb.BundleError) as e:
            rb.import_bundle(bundle, rr)
        assert str(e.value) == said
    elif via == "route":
        _clear_flash()
        r = client.post("/retro/import", data={"path": str(bundle)},
                        follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/retro"
        assert _flash() == f"Not imported: {said}"
    else:
        res = CliRunner().invoke(cli_app, ["retro", "import", str(bundle),
                                           "--root", str(rr)])
        assert res.exit_code == 2, res.output
        assert f"refused: {said}" in res.output, res.output
    _nothing_written(rr)


# ------------------------- a delete during an import's Replace (finding 3)

def _replace_held(world, monkeypatch):
    """A Replace import of the bundle, its run already imported, held part
    way through its extraction (the tree marked): (thread, paused, go,
    outcome, the archived run)."""
    dst = rb.import_bundle(world["bundle"], world["rr"]).root
    real = rb._extract_member
    paused, go = threading.Event(), threading.Event()

    def extract(z, name, d, *a):
        real(z, name, d, *a)
        if not paused.is_set():
            paused.set()
            if not go.wait(20):
                raise TimeoutError("the test never let the import go on")
    monkeypatch.setattr(rb, "_extract_member", extract)
    out = {}

    def run():
        try:
            out["r"] = rb.import_bundle(world["bundle"], world["rr"],
                                        replace=True, removing=RP._removing)
        except Exception as e:          # noqa: BLE001 - the outcome itself
            out["r"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert paused.wait(20), "the Replace did not begin"
    return t, go, out, dst


@pytest.mark.parametrize("where", ["storage", "archive"])
def test_a_delete_during_a_replace_says_deleted_or_replaced(
        world, monkeypatch, where):
    t, go, out, dst = _replace_held(world, monkeypatch)
    try:
        assert RP._being_removed(dst)
        _clear_flash()
        if where == "storage":
            r = client.post("/storage/delete",
                            data={"kind": "retro-archive", "ident": dst.name,
                                  "confirm": dst.name},
                            follow_redirects=False)
            want = (f"Not deleted: {dst.name} is already being deleted or "
                    "replaced.")
        else:
            r = client.post(f"/retro/{SEASON}/archive/{world['stamp']}"
                            "/delete", data={"confirm": SEASON},
                            follow_redirects=False)
            want = (f"Not deleted: the {SEASON} run "
                    f"{rb.imported_label(dst)} is already being deleted or "
                    "replaced.")
        seen = _flash()
        detail = ui_state._status.get("flash_detail")
    finally:
        go.set()
        t.join(30)
    assert r.status_code == 303
    assert seen == want, seen
    assert detail == "Nothing else changed."
    # the Replace went through, whole
    assert isinstance(out["r"], rb.ImportResult), out["r"]
    assert (dst / rb.IMPORTED_MARK).is_file()
    assert sorted(p.name for p in (dst / "weeks").iterdir()) == WEEKS
    assert not RP._REMOVING


def _live_tree(rr: Path) -> Path:
    root = _season_tree(rr, SEASON)
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "scope": "panel6",
                                         "locations": [
                                             "Alaska", "New York",
                                             "Wyoming", "Pennsylvania",
                                             "Vermont", "California"]}})
    return root


@pytest.mark.parametrize("mode", ["discard", "archive"])
def test_the_run_form_never_garbles_the_answer_of_a_held_tree(
        world, monkeypatch, pf_engine_ready, mode):
    """The Run form's discard or archive finds the season held by another
    remover at its mark (the look before it said no: the gap between the
    two, forced): it says so in its own sentence, not "the 2098-99
    already being deleted are still being prepared"; nothing deleted,
    moved or started."""
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append(a[0]))
    monkeypatch.setattr(RP, "_being_removed", lambda root: False)
    root = _live_tree(world["rr"])
    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    form = {"season": SEASON, "engine": "pf", "mode": mode,
            "locations": "panel6", "national": "0", "confirm": SEASON,
            "knob.groundhog.zero_anchor": "abstain"}
    _clear_flash()
    with RP._removing(root) as first:
        assert first == ""
        r = client.post("/retro/run", data=form, follow_redirects=False)
    assert r.status_code == 303
    assert _flash() == f"Not started: the {SEASON} results are being deleted."
    assert ui_state._status.get("flash_detail") == (
        "Nothing was started. Start the replay again once the delete is "
        "done.")
    assert launched == []
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before
    assert not RP._REMOVING


# ------------------------------------------- uploads in one millisecond

def _pinned_clock(monkeypatch):
    """The clock stopped for the Import route alone (a call to time.time()
    made from retro_import itself); everyone else's runs on."""
    real, at = time.time, time.time()

    def clock():
        if sys._getframe(1).f_code is ui_retro.retro_import.__code__:
            return at
        return real()
    monkeypatch.setattr(time, "time", clock)


def test_two_uploads_in_one_millisecond_get_their_own_files(
        world, monkeypatch):
    _pinned_clock(monkeypatch)
    real = ui_retro._import_replay_file
    names = []

    def imp(src, replace, name=""):
        names.append(Path(src).name)
        return real(src, replace, name)
    monkeypatch.setattr(ui_retro, "_import_replay_file", imp)
    for _ in range(2):
        with open(world["bundle"], "rb") as f:
            client.post("/retro/import",
                        files={"file": (world["bundle"].name, f,
                                        "application/zip")},
                        follow_redirects=False)
    assert len(names) == 2 and all(n.startswith("incoming-") for n in names)
    assert names[0] != names[1], names


def test_an_upload_keeps_its_file_while_a_second_one_finishes(
        world, monkeypatch):
    """The first upload is saved and about to be imported when a second,
    in the same millisecond, is saved, imported and cleaned up: the
    first's file is still its own, whole, and it is refused only because
    the bundle was imported (before: "no such file", naming nothing it
    knew)."""
    _pinned_clock(monkeypatch)
    real = ui_retro._import_replay_file
    want = hashlib.sha256(world["bundle"].read_bytes()).hexdigest()
    paused, go = threading.Event(), threading.Event()
    seen = {}

    def imp(src, replace, name=""):
        first = not paused.is_set()
        if first:
            paused.set()
            if not go.wait(20):
                raise TimeoutError("the test never let the upload go on")
            seen["intact"] = (Path(src).is_file() and hashlib.sha256(
                Path(src).read_bytes()).hexdigest() == want)
        out = real(src, replace, name)
        seen["first" if first else "second"] = out
        return out
    monkeypatch.setattr(ui_retro, "_import_replay_file", imp)

    def upload():
        with open(world["bundle"], "rb") as f:
            TestClient(srv.app).post(
                "/retro/import", files={"file": ("a.flubnf-replay.zip", f,
                                                 "application/zip")},
                follow_redirects=False)
    t = threading.Thread(target=upload, daemon=True)
    t.start()
    try:
        assert paused.wait(20), "the first upload did not begin"
        with open(world["bundle"], "rb") as f:
            client.post("/retro/import",
                        files={"file": ("b.flubnf-replay.zip", f,
                                        "application/zip")},
                        follow_redirects=False)
    finally:
        go.set()
        t.join(30)
    assert seen["second"][0][0].startswith(f"Imported {SEASON} (3 weeks).")
    assert seen["intact"], "the second upload's clean-up took the first's file"
    assert seen["first"][0] == (
        f"Not imported: {SEASON} from this bundle was already imported as "
        f"{world['stamp']}.", "warn", ""), seen["first"]
    assert not list((runs_mod.APP_STATE / "exports").glob("incoming-*"))
