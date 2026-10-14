"""FluBNF's own Perl for real, as a student with no Perl and no
administrator gets it: FluBNF.bat's Perl block run by cmd.exe with the
real download (conda-forge's Strawberry Perl repack), Windows' own
tar.exe, a real .venv Python, and a profile folder named with a space, an
apostrophe and parentheses. Then the perl it leaves must be the one the
console resolves, read its modules from where it was unpacked, and run
BNG2.pl, run_network included.

Only in the windows-own-perl CI job (FLUBNF_PERL_REAL=1, Windows, every
other Windows Perl hidden first). FLUBNF_PERL_LOCAL names the
%LOCALAPPDATA% to install under, so the job's next steps can use the same
Perl. tests/test_windows_launcher.py runs the same block with stand-ins on
every Windows run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

pytestmark = pytest.mark.skipif(
    os.name != "nt" or os.environ.get("FLUBNF_PERL_REAL") != "1",
    reason="FLUBNF_PERL_REAL=1 on Windows installs FluBNF's own Perl for real")

PACKAGE = "perl-5.32.1.1-2_h57928b3_strawberry.tar.bz2"


@pytest.fixture(scope="module")
def pc(tmp_path_factory):
    """A FluBNF folder as FluBNF.bat sees it when its Perl block runs: a
    real .venv, get_perl.py, and the Perl offer already made, so a failure
    here never reaches winget on the runner."""
    folder = tmp_path_factory.mktemp("flubnf")
    (folder / "scripts" / "windows").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "windows" / "get_perl.py",
                folder / "scripts" / "windows" / "get_perl.py")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                    str(folder / ".venv")], check=True)
    (folder / ".venv" / "perl-offer.txt").write_bytes(b'"not asked in CI"\r\n')
    local = Path(os.environ.get("FLUBNF_PERL_LOCAL")
                 or tmp_path_factory.mktemp("Jane O'Brien (Lab)") / "Local")
    local.mkdir(parents=True, exist_ok=True)
    return folder, local, local / "FluBNF" / "perl"


def _open(folder: Path, local: Path) -> tuple[subprocess.CompletedProcess, float]:
    """FluBNF.bat's Perl block, called as an open calls it."""
    bat = (REPO / "FluBNF.bat").read_bytes().replace(b"\r\n", b"\n").decode("ascii")
    sub = bat[bat.index("\n:perlblock\n") + 1:]
    text = ("@echo off\nsetlocal\ncall :perlblock\n"
            "echo PATH=[%PATH%]\necho PERL5LIB=[%PERL5LIB%]\necho REACHED\n"
            "exit /b 0\n\n" + sub)
    script = folder.parent / "perl-open.bat"
    script.write_bytes(text.replace("\n", "\r\n").encode("ascii"))
    env = {**os.environ, "LOCALAPPDATA": str(local), "PERL5LIB": r"C:\bogus"}
    t0 = time.monotonic()
    r = subprocess.run(["cmd", "/d", "/c", str(script)], cwd=folder, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, errors="replace", timeout=900, check=False)
    return r, time.monotonic() - t0


def _said(r) -> str:
    return f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def test_flubnf_bat_installs_its_own_perl_and_uses_it(pc):
    folder, local, root = pc
    r, took = _open(folder, local)
    print(f"first open: {took:.0f} s")
    assert "REACHED" in r.stdout, _said(r)
    assert "Perl for FluBNF is ready." in r.stdout, _said(r)
    assert (root / "flubnf-perl.ok").read_text().strip() == PACKAGE
    path = r.stdout.split("PATH=[", 1)[1].split("]", 1)[0]
    assert path.lower().startswith(str(root / "Library" / "bin").lower() + ";")
    assert "PERL5LIB=[]" in r.stdout, _said(r)

    # nothing relocated: @INC is computed from where perl532.dll sits
    perl = root / "Library" / "bin" / "perl.exe"
    inc = subprocess.run([str(perl), "-e", 'print qq{$_\\n} for @INC'],
                         capture_output=True, text=True, check=True,
                         env={**os.environ, "PERL5LIB": ""}).stdout.split()
    want = str(root).replace("\\", "/").lower()
    assert inc and all(d.replace("\\", "/").lower().startswith(want)
                       for d in inc), inc
    # the modules BNG2.pl and its Perl2 load
    mods = ("strict POSIX Storable IPC::Open3 IO::Select Math::Trig "
            "Class::Struct Data::Dumper List::Util Scalar::Util Getopt::Long "
            "FindBin File::Spec::Win32 Cwd File::Path").split()
    subprocess.run([str(perl), *[f"-M{m}" for m in mods], "-e", "1"], check=True)

    # the next open only checks it
    r, took = _open(folder, local)
    print(f"second open: {took:.1f} s")
    assert "installing Perl" not in r.stdout and took < 20, _said(r)


def test_the_console_resolves_it_and_bng2pl_runs_under_it(pc, monkeypatch,
                                                          tmp_path):
    folder, local, root = pc
    if not (root / "flubnf-perl.ok").is_file():
        pytest.skip("the install above failed")
    import bionetgen

    from app.core import sandbox as sb
    from flubnf import settings
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    perl = settings.resolve_perl()
    assert perl and Path(perl).resolve() == (root / "Library" / "bin"
                                             / "perl.exe").resolve(), perl
    # the SIR example's whole actions block: network, then simulate, which
    # runs Cygwin's run_network.exe
    cell = tmp_path / "Jane O'Brien (Lab)" / "cell"
    cell.mkdir(parents=True)
    shutil.copy(sb.EXAMPLES / "sir_example" / "model.bngl", cell / "m.bngl")
    monkeypatch.setattr(sb, "BNG", str(Path(bionetgen.__file__).parent
                                       / settings.bng_platform_dirs()[0]
                                       / "BNG2.pl"))
    sb._netgen(cell)
    assert (cell / "m.net").stat().st_size > 0
    assert (cell / "m_sir.gdat").stat().st_size > 0, "run_network did not run"
