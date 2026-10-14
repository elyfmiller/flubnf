"""scripts/windows/get_perl.py, FluBNF's own Perl on Windows: the download
is refused unless it is the pinned package, and an unpack counts only when
every file the package lists is there. Runs everywhere, on a small package
built here; the real one is fetched only by the windows-own-perl CI job.
"""
from __future__ import annotations

import bz2
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "windows" / "get_perl.py"


def _module():
    spec = importlib.util.spec_from_file_location("get_perl", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FILES = {"Library/bin/perl.exe": b"MZ not really perl",
         "Library/lib/strict.pm": b"package strict;\n1;\n"}


def _package(tmp_path: Path) -> tuple[Path, bytes]:
    """A conda-style .tar.bz2 holding FILES and info/paths.json, and the
    plain tar it decompresses to."""
    manifest = {"paths": [{"_path": p, "size_in_bytes": len(b),
                           "sha256": hashlib.sha256(b).hexdigest()}
                          for p, b in FILES.items()], "paths_version": 1}
    members = dict(FILES)
    members["info/paths.json"] = json.dumps(manifest).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    plain = buf.getvalue()
    pkg = tmp_path / "pkg.tar.bz2"
    pkg.write_bytes(bz2.compress(plain))
    return pkg, plain


def _pinned_to(mod, pkg: Path, monkeypatch) -> None:
    data = pkg.read_bytes()
    monkeypatch.setattr(mod, "SIZE", len(data))
    monkeypatch.setattr(mod, "SHA256", hashlib.sha256(data).hexdigest())


class _Out:
    def __init__(self):
        self.buffer = io.BytesIO()


def _fetch(mod, monkeypatch, src) -> tuple[int, bytes]:
    out = _Out()
    monkeypatch.setattr(sys, "stdout", out)
    return mod.fetch(str(src)), out.buffer.getvalue()


def test_the_pinned_package_is_streamed_as_a_plain_tar(tmp_path, monkeypatch):
    mod = _module()
    pkg, plain = _package(tmp_path)
    _pinned_to(mod, pkg, monkeypatch)
    assert _fetch(mod, monkeypatch, pkg) == (0, plain)


@pytest.mark.parametrize("damage", ["short", "flipped", "longer"])
def test_anything_but_the_pinned_package_sends_nothing(tmp_path, monkeypatch,
                                                       damage):
    mod = _module()
    pkg, _ = _package(tmp_path)
    _pinned_to(mod, pkg, monkeypatch)
    data = pkg.read_bytes()
    data = {"short": data[:-10],
            "flipped": data[:-1] + bytes([data[-1] ^ 1]),
            "longer": data + b"\0"}[damage]
    pkg.write_bytes(data)
    assert _fetch(mod, monkeypatch, pkg) == (1, b"")


def test_a_download_that_fails_sends_nothing(monkeypatch):
    mod = _module()

    def offline(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(mod.urllib.request, "urlopen", offline)
    monkeypatch.delenv("FLUBNF_PERL_FROM", raising=False)
    out = _Out()
    monkeypatch.setattr(sys, "stdout", out)
    assert mod.fetch() == 1 and out.buffer.getvalue() == b""


def test_a_local_copy_can_stand_in_for_the_download(tmp_path, monkeypatch):
    mod = _module()
    pkg, plain = _package(tmp_path)
    _pinned_to(mod, pkg, monkeypatch)
    monkeypatch.setenv("FLUBNF_PERL_FROM", str(pkg))
    monkeypatch.setattr(mod.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("downloaded"))
    out = _Out()
    monkeypatch.setattr(sys, "stdout", out)
    assert mod.fetch() == 0 and out.buffer.getvalue() == plain


def _unpacked(tmp_path: Path) -> Path:
    _, plain = _package(tmp_path)
    root = tmp_path / "perl"
    root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(plain)) as t:
        t.extractall(root, filter="data") if hasattr(tarfile, "data_filter") \
            else t.extractall(root)
    return root


def test_a_complete_unpack_verifies(tmp_path):
    assert _module().verify(str(_unpacked(tmp_path))) == 0


@pytest.mark.parametrize("damage", ["missing", "emptied", "same-size",
                                    "no-manifest"])
def test_a_partial_unpack_does_not_verify(tmp_path, damage):
    root = _unpacked(tmp_path)
    strict = root / "Library" / "lib" / "strict.pm"
    if damage == "missing":
        strict.unlink()
    elif damage == "emptied":
        strict.write_bytes(b"")
    elif damage == "same-size":
        strict.write_bytes(strict.read_bytes().upper())
    else:
        (root / "info" / "paths.json").unlink()
    assert _module().verify(str(root)) == 1


def test_the_script_runs_as_the_launcher_runs_it(tmp_path):
    """-I, as FluBNF.bat starts it: standard library only, nothing from the
    current folder, and a bad --from exits 1 with nothing on stdout."""
    bad = tmp_path / "x.tar.bz2"
    bad.write_bytes(b"not the package")
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "fetch", "--from",
                        str(bad)], capture_output=True, cwd=tmp_path,
                       check=False)
    assert r.returncode == 1 and r.stdout == b""
    assert b"not the one FluBNF pins" in r.stderr
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "bogus"],
                       capture_output=True, check=False)
    assert r.returncode == 2


def test_the_launcher_and_the_script_pin_the_same_package():
    mod = _module()
    assert mod.URL.endswith("/" + mod.PACKAGE)
    bat = (REPO / "FluBNF.bat").read_text(encoding="ascii")
    assert re.findall(r'set "PERLPKG=([^"]+)"', bat) == [mod.PACKAGE]
    py = (REPO / "flubnf" / "settings.py").read_text(encoding="utf-8")
    assert f'"{mod.PACKAGE}"' in py
