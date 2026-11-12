"""One changed byte in the zip's end record, in the offset of its table of
contents, is refused as a damaged bundle (the seventh pass's check).

Raising that offset (end record bytes 16-19) makes zipfile shift every
member's local header back by the same amount, before the start of the
file, and its seek there raised a raw OSError (EINVAL): the console said
"Could not import: OSError: [Errno 22] Invalid argument." as a disk
error, and the terminal exited 1. A member whose header would lie before
the start of the file is now refused in the words a member that cannot be
unpacked gets, inspected or imported. A real disk error still says so.
"""
import errno
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import replay_bundle as rb                   # noqa: E402
from test_retro_import_directory_and_swap import (         # noqa: E402,F401
    _flash, _nothing_written, client, world)

#: where the end record keeps the offset of the table of contents
CD_OFFSET = 16


def _end_record(bundle: Path) -> int:
    data = bundle.read_bytes()
    at = data.rfind(b"PK\x05\x06")
    assert at > 0
    return at


def _changed(bundle: Path, k: int, how: str, out: Path) -> tuple:
    """A copy of `bundle` with byte k of the offset changed `how`; and
    whether that raised the offset."""
    data = bytearray(bundle.read_bytes())
    at = _end_record(bundle) + CD_OFFSET + k
    old = data[at]
    new = {"+1": (old + 1) & 0xFF, "^ff": old ^ 0xFF, "0": 0,
           "|80": old | 0x80}[how]
    data[at] = new
    out.write_bytes(bytes(data))
    return out, new > old


def _words(member: str) -> str:
    return (f"bad.zip: {member} could not be unpacked; the bundle is damaged "
            "or altered.")


def _first(bundle: Path) -> str:
    """The member the table of contents lists first (its header at the
    start of the file)."""
    with zipfile.ZipFile(bundle) as z:
        first = z.infolist()[0]
    assert first.header_offset == 0
    return first.filename


@pytest.mark.parametrize("how", ["+1", "^ff", "0", "|80"])
@pytest.mark.parametrize("k", [0, 1, 2, 3])
def test_a_changed_offset_of_the_table_of_contents_is_refused_in_words(
        world, k, how):
    """Every one-byte change there is refused as a damaged bundle,
    inspected or imported, plain or Replace, nothing written; a raised
    offset in the words for the member listed first."""
    bad, raised = _changed(world["bundle"], k, how, world["tmp"] / "bad.zip")
    if bad.read_bytes() == world["bundle"].read_bytes():
        assert rb.inspect_bundle(bad)["season"]    # the byte as it was
        return
    for call in (lambda: rb.inspect_bundle(bad),
                 lambda: rb.import_bundle(bad, world["rr"]),
                 lambda: rb.import_bundle(bad, world["rr"], replace=True)):
        with pytest.raises(rb.BundleError) as e:
            call()
        if raised:
            assert str(e.value) == _words(_first(world["bundle"]))
    _nothing_written(world["rr"])


def test_the_import_asks_again_of_the_file_it_opens(world, monkeypatch):
    """The file is changed between the inspection and the extraction (the
    inspection here reads the good bundle): the member's header is asked
    of the file the import opens, before it is read."""
    bad, raised = _changed(world["bundle"], 3, "+1", world["tmp"] / "bad.zip")
    assert raised
    m = rb.inspect_bundle(world["bundle"])
    first = sorted(m["files"], key=lambda f: (f == "scores.json", f))[0]
    real = rb.inspect_bundle
    monkeypatch.setattr(rb, "inspect_bundle",
                        lambda p, name="": real(world["bundle"], name))
    with pytest.raises(rb.BundleError) as e:
        rb.import_bundle(bad, world["rr"])
    assert str(e.value) == _words(first)
    _nothing_written(world["rr"])


def test_the_import_form_and_the_terminal_say_it_in_words(world):
    """The check's case (end record byte 18 raised): through the route a
    refusal, never "Could not import: OSError", and `flubnf retro import`
    exits 2 with one line, no traceback."""
    from app.ui import state as ui_state
    from flubnf.cli import app as cli_app
    bad, raised = _changed(world["bundle"], 2, "+1", world["tmp"] / "bad.zip")
    assert raised
    words = _words(_first(world["bundle"]))
    r = client.post("/retro/import", data={"path": str(bad)},
                    follow_redirects=False)
    assert r.status_code == 303, r.status_code
    assert _flash() == f"Not imported: {words}"
    assert ui_state._status.get("flash_kind") == "warn"
    res = CliRunner().invoke(cli_app, ["retro", "import", str(bad),
                                       "--root", str(world["rr"])])
    assert res.exit_code == 2, res.output
    assert f"refused: {words}" in res.output, res.output
    assert "Traceback" not in res.output
    _nothing_written(world["rr"])


def test_a_real_disk_error_still_says_so(world, monkeypatch):
    """Only a header before the start of the file is refused as damage:
    an EINVAL the disk gives while a member is written stays the disk's
    error (the console's "Could not import", the terminal's exit 1)."""
    def extract(*a, **k):
        raise OSError(errno.EINVAL, "Invalid argument")
    monkeypatch.setattr(rb, "_extract_member", extract)
    with pytest.raises(OSError) as e:
        rb.import_bundle(world["bundle"], world["rr"])
    assert not isinstance(e.value, rb.BundleError)
    assert e.value.errno == errno.EINVAL
