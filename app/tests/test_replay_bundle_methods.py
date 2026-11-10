"""A compression method no FluBNF bundle uses is refused in words (the
review of #105 at 1ce301ed, finding 5).

export_season deflates every member, as every build has; stored is plain
zip. One changed byte in the table of contents can name another method:
bzip2 (12) read deflated bytes and gave "Could not import: OSError:
Invalid data stream." for a member and for the manifest. Any method but
stored and deflated is now refused from the member's entry, when the
bundle is inspected and again on import, in the words a member that
cannot be unpacked gets.
"""
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import replay_bundle as rb                   # noqa: E402
from test_retro_archive import SEASON                      # noqa: E402
from test_retro_import_directory_and_swap import (         # noqa: E402,F401
    W3, WEEKS, _directory_entry, _flash, _nothing_written, client, world)

SAMPLE = f"weeks/{W3}/samples.json"


def _method(bundle: Path, member: str, method: int, out: Path) -> Path:
    """A copy of `bundle` whose table of contents names `method` for
    `member` (its bytes, and the manifest's hashes, untouched)."""
    data = bytearray(bundle.read_bytes())
    off = _directory_entry(data, member)
    assert int.from_bytes(data[off + 10:off + 12], "little") == \
        zipfile.ZIP_DEFLATED
    data[off + 10:off + 12] = method.to_bytes(2, "little")
    out.write_bytes(bytes(data))
    return out


def _words(member: str) -> str:
    return (f"bad.zip: {member} could not be unpacked; the bundle is damaged "
            "or altered.")


def test_every_member_an_export_writes_is_deflated(world):
    with zipfile.ZipFile(world["bundle"]) as z:
        assert {i.compress_type for i in z.infolist()} == \
            {zipfile.ZIP_DEFLATED}


@pytest.mark.parametrize("member", [rb.MANIFEST, SAMPLE])
@pytest.mark.parametrize("method", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA,
                                    93, 99])
def test_a_method_no_bundle_uses_is_refused_in_words(world, member, method):
    """bzip2 above all (it gave a raw OSError); LZMA, zstd (93) and an
    AES entry (99) too, by one rule. Inspected or imported: the same
    sentence, nothing written."""
    bad = _method(world["bundle"], member, method, world["tmp"] / "bad.zip")
    for call in (lambda: rb.inspect_bundle(bad),
                 lambda: rb.import_bundle(bad, world["rr"]),
                 lambda: rb.import_bundle(bad, world["rr"], replace=True)):
        with pytest.raises(rb.BundleError) as e:
            call()
        assert str(e.value) == _words(member)
    _nothing_written(world["rr"])


def test_the_import_asks_again_of_the_file_it_opens(world, monkeypatch):
    """The file is changed between the inspection and the extraction (the
    inspection here reads the good bundle): the member's method is asked
    again of the file the import opens."""
    bad = _method(world["bundle"], SAMPLE, zipfile.ZIP_BZIP2,
                  world["tmp"] / "bad.zip")
    real = rb.inspect_bundle
    monkeypatch.setattr(rb, "inspect_bundle",
                        lambda p, name="": real(world["bundle"], name))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bad, world["rr"])
    assert str(e.value) == _words(SAMPLE)
    _nothing_written(world["rr"])


def test_a_stored_bundle_still_imports(world):
    """Stored is plain zip and is read as before: the same members,
    uncompressed, import whole."""
    plain = world["tmp"] / "stored.zip"
    with zipfile.ZipFile(world["bundle"]) as src, \
            zipfile.ZipFile(plain, "w", zipfile.ZIP_STORED) as out:
        for i in src.infolist():
            out.writestr(i.filename, src.read(i.filename))
    assert rb.inspect_bundle(plain)["weeks"] == WEEKS
    r = rb.import_bundle(plain, world["rr"])
    assert r.season == SEASON and r.weeks == WEEKS


@pytest.mark.parametrize("member", [rb.MANIFEST, SAMPLE])
def test_the_import_form_and_the_terminal_say_it_in_words(world, member):
    """A bzip2 entry through the route (a refusal, never "Could not
    import: OSError") and `flubnf retro import` (exit 2, no traceback)."""
    from app.ui import state as ui_state
    from flubnf.cli import app as cli_app
    bad = _method(world["bundle"], member, zipfile.ZIP_BZIP2,
                  world["tmp"] / "bad.zip")
    r = client.post("/retro/import", data={"path": str(bad)},
                    follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert _flash() == f"Not imported: {_words(member)}"
    assert ui_state._status.get("flash_kind") == "warn"
    res = CliRunner().invoke(cli_app, ["retro", "import", str(bad),
                                       "--root", str(world["rr"])])
    assert res.exit_code == 2, res.output
    assert f"refused: {_words(member)}" in res.output, res.output
    assert "Traceback" not in res.output
    _nothing_written(world["rr"])
