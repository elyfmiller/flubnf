"""Perl and BioNetGen's environment for every BNG2.pl run FluBNF starts:
flubnf/settings.py resolve_perl and bng_env; app/core/engines/pf.py
perl_path, bng_run_kwargs and bng_failure_text; the Perl row of
`flubnf doctor`.

On Windows the perl first on PATH can be one that cannot run BNG2.pl
(Git's Unix tools, MSYS2, Cygwin), a Strawberry Perl installed after the
console started is off its PATH, and a BNGPATH left by an earlier
BioNetGen or PyBNF install decides where BNG2.pl loads its own modules.
The Windows search runs here through its _platform seam, on fake perls:
shell scripts that print what a real one's $^O would. The BNG2.pl runs
use the real bundle of the installed bionetgen.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import contactmap as cm                    # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from flubnf import doctor, settings                      # noqa: E402

EXAMPLE = (Path(__file__).resolve().parents[2] / "flubnf"
           / "sandbox_examples" / "kinetics_example")
#: a BNGPATH an earlier BioNetGen install left, whose folder is gone
STALE = os.path.join(os.sep, "nonexistent", "BioNetGen-2.5.1")

#: the fake perls are shell scripts; Windows runs the real one instead
posix_only = pytest.mark.skipif(os.name == "nt",
                                reason="the fake perls are shell scripts")


@pytest.fixture
def search(monkeypatch, tmp_path):
    """A clean Windows search: nothing remembered, no registry Path, no
    Strawberry default folders, PATH holding only what a test puts there."""
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    monkeypatch.setattr(settings, "_registry_path_dirs", lambda: [])
    monkeypatch.delenv("SystemDrive", raising=False)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("BNGPATH", raising=False)
    # no FluBNF Perl unless a test unpacks one
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    return tmp_path


def _fake_perl(folder: Path, says: str, log: Path) -> Path:
    """A perl.exe that prints `says` for $^O and logs every start."""
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / "perl.exe"
    exe.write_text(f"#!/bin/sh\necho run >> '{log}'\nprintf '%s' '{says}'\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


@pytest.fixture
def real_bng(monkeypatch):
    """This platform's BNG2.pl from the installed bionetgen; skipped when
    there is none, or no perl that can run it. PATH is restored after (the
    Windows search puts the perl it finds first)."""
    try:
        import bionetgen
    except ImportError:
        pytest.skip("bionetgen is not installed")
    p = (Path(bionetgen.__file__).parent / settings.bng_platform_dirs()[0]
         / "BNG2.pl")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    if not p.is_file() or not settings.resolve_perl():
        pytest.skip("no BNG2.pl bundle for this platform, or no perl")
    return p


# ------------------------------------------------- resolve_perl, POSIX

def test_macos_and_linux_resolve_perl_as_before(monkeypatch):
    """shutil.which, no subprocess and no PATH change."""
    if os.name == "nt":
        pytest.skip("the POSIX branch")

    def no_run(*a, **k):
        raise AssertionError("POSIX resolution must not start a process")
    monkeypatch.setattr(settings, "_probe", no_run)
    before = os.environ.get("PATH")
    assert settings.resolve_perl() == shutil.which("perl")
    assert settings.resolve_perl("linux") == shutil.which("perl")
    assert os.environ.get("PATH") == before
    assert pf.perl_available() == (shutil.which("perl") is not None)


# ------------------------------------------------ resolve_perl, Windows

@posix_only
def test_a_unix_style_perl_first_on_path_is_passed_over(search, monkeypatch):
    """Git's usr\\bin first on PATH, Strawberry later: Strawberry wins, its
    folder goes first on this process's PATH, and each perl is asked once."""
    log = search / "starts.log"
    git = _fake_perl(search / "Git" / "usr" / "bin", "cygwin", log)
    straw = _fake_perl(search / "Strawberry" / "perl" / "bin", "MSWin32", log)
    monkeypatch.setenv("PATH", os.pathsep.join([str(git.parent),
                                                str(straw.parent)]))
    assert settings.resolve_perl("win32") == str(straw)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(straw.parent)
    assert log.read_text().count("run") == 2
    # again: found first now, nothing asked again, PATH not grown
    path_now = os.environ["PATH"]
    assert settings.resolve_perl("win32") == str(straw)
    assert log.read_text().count("run") == 2
    assert os.environ["PATH"] == path_now
    assert settings.perl_unusable() is None


@posix_only
def test_only_a_unix_style_perl_is_named_in_the_refusal(search, monkeypatch):
    log = search / "starts.log"
    git = _fake_perl(search / "Git" / "usr" / "bin", "cygwin", log)
    monkeypatch.setenv("PATH", str(git.parent))
    assert settings.resolve_perl("win32") is None
    assert settings.perl_unusable() == (str(git), "cygwin")
    msg = pf.perl_missing_message("win32")
    notice, tip = sb.split_reason(msg)
    assert notice == "The perl found here cannot run BNG2.pl."
    assert str(git) in tip and "cygwin" in tip
    assert "install Strawberry Perl" in tip and "no restart" in tip
    assert "open FluBNF.bat again" in tip and "no administrator" in tip
    # the routes FluBNF no longer offers once the engine is in
    assert "let FluBNF.bat offer" not in msg and "start the console again" not in msg
    # the setup table says the same, never "ready"
    monkeypatch.setattr(settings, "_windows", lambda: True)
    row = [m for m in settings.check(verbose=False) if m[0] == "perl"]
    assert row and str(git) in row[0][2]


@posix_only
def test_a_perl_that_will_not_start_is_not_counted(search, monkeypatch):
    folder = search / "broken"
    folder.mkdir()
    exe = folder / "perl.exe"
    exe.write_text("#!/bin/sh\nexit 3\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(folder))
    assert settings.resolve_perl("win32") is None
    assert settings.perl_unusable() == (str(exe), "")
    assert "did not start" in pf.perl_missing_message("win32")


@posix_only
def test_strawberry_off_path_is_found_in_its_default_folder(search,
                                                            monkeypatch):
    """Installed while the console ran: not on this process's PATH, found
    at %SystemDrive%\\Strawberry with no restart."""
    drive = search / "C"
    straw = _fake_perl(drive / "Strawberry" / "perl" / "bin", "MSWin32",
                       search / "starts.log")
    monkeypatch.setenv("SystemDrive", str(drive))
    assert settings.resolve_perl("win32") == str(straw)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(straw.parent)


@posix_only
def test_a_perl_on_the_registry_path_is_found(search, monkeypatch):
    """A Perl installed to another folder: the machine Path the registry
    holds now names it, this process's PATH does not."""
    perl = _fake_perl(search / "Perl64" / "bin", "MSWin32", search / "l")
    monkeypatch.setattr(settings, "_registry_path_dirs",
                        lambda: [str(search / "nowhere"), str(perl.parent)])
    assert settings.resolve_perl("win32") == str(perl)


@pytest.mark.skipif(os.name != "nt", reason="the real Windows search")
def test_windows_resolves_a_native_perl_even_after_gits_unix_tools(
        monkeypatch):
    """windows-latest has Strawberry Perl and Git's MSYS perl: with Git's
    usr\\bin first on PATH (as in Git Bash) the resolver still returns a
    perl whose $^O is MSWin32."""
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    git = (Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Git"
           / "usr" / "bin")
    monkeypatch.setenv("PATH", str(git) + os.pathsep
                       + os.environ.get("PATH", ""))
    perl = settings.resolve_perl()
    if perl is None:
        pytest.skip("no native perl on this machine")
    said = subprocess.run([perl, "-e", "print $^O"], capture_output=True,
                          text=True, timeout=60).stdout
    assert said == "MSWin32"
    assert not os.path.normcase(perl).startswith(os.path.normcase(str(git)))
    assert os.environ["PATH"].split(os.pathsep)[0] == os.path.dirname(perl)


def test_perl_available_asks_the_resolver(monkeypatch):
    monkeypatch.setattr(pf, "resolve_perl", lambda: None)
    assert not pf.perl_available()
    monkeypatch.setattr(pf, "resolve_perl", lambda: "/x/perl")
    assert pf.perl_available()


def test_the_windows_message_names_the_no_administrator_route_and_no_restart(
        monkeypatch):
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    msg = pf.perl_missing_message("win32")
    notice, tip = sb.split_reason(msg)
    assert notice == "Perl was not found on PATH."
    assert "install Strawberry Perl" in tip and "no restart" in tip
    assert "open FluBNF.bat again" in tip and "no administrator" in tip
    assert "let FluBNF.bat offer" not in msg and "start the console again" not in msg
    assert "ships with macOS" in pf.perl_missing_message("darwin")


# ------------------------------------------------------------- bng_env

def test_bng_env_pins_bngpath_to_the_folder_bng2pl_really_is_in(tmp_path,
                                                                 monkeypatch):
    bundle = tmp_path / "bionetgen" / "bng-linux"
    bundle.mkdir(parents=True)
    (bundle / "BNG2.pl").write_text("# stub\n")
    monkeypatch.setenv("BNGPATH", "C:\\BioNetGen-2.5.1")    # deleted since
    env = settings.bng_env(bundle / "BNG2.pl")
    assert env["BNGPATH"] == os.path.realpath(str(bundle))
    assert os.environ["BNGPATH"] == "C:\\BioNetGen-2.5.1"  # a copy
    # through a link: the folder BNG2.pl's own modules sit beside
    link = tmp_path / "linked.pl"
    try:
        link.symlink_to(bundle / "BNG2.pl")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    assert settings.bng_env(link)["BNGPATH"] == os.path.realpath(str(bundle))


def test_bng_env_without_bng2pl_changes_nothing_off_windows(tmp_path):
    if os.name == "nt":
        pytest.skip("the POSIX branch")
    assert settings.bng_env(tmp_path / "missing" / "BNG2.pl") is None
    assert settings.bng_env("BNG2.pl") is None


@posix_only
def test_on_windows_bng_env_puts_the_resolved_perl_first(search, monkeypatch):
    straw = _fake_perl(search / "Strawberry" / "perl" / "bin", "MSWin32",
                       search / "l")
    git = _fake_perl(search / "Git" / "usr" / "bin", "msys", search / "l")
    monkeypatch.setenv("PATH", os.pathsep.join([str(git.parent),
                                                str(straw.parent)]))
    monkeypatch.setattr(settings, "_windows", lambda: True)
    env = settings.bng_env(search / "missing" / "BNG2.pl")
    parts = env["PATH"].split(os.pathsep)
    assert parts[:2] == [str(straw.parent), str(git.parent)]
    assert "BNGPATH" not in env                # no BNG2.pl, nothing pinned


def test_an_apostrophe_folder_is_given_relative_on_windows(search,
                                                           monkeypatch):
    """C:\\Users\\O'Brien: Cygwin's run_network.exe reads the ' in its own
    unquoted path as a quote, so BNG2.pl gets BNGPATH relative to the
    folder it runs in."""
    home = search / "O'Brien"
    bundle = home / "flubnf" / "bng-win"
    bundle.mkdir(parents=True)
    (bundle / "BNG2.pl").write_text("# stub\n")
    work = home / "flubnf" / "sandbox" / "check"
    work.mkdir(parents=True)
    real = os.path.realpath(str(bundle))
    monkeypatch.setattr(settings, "_windows", lambda: False)
    assert settings.bng_env(bundle / "BNG2.pl", cwd=work)["BNGPATH"] == real
    monkeypatch.setattr(settings, "_windows", lambda: True)
    rel = settings.bng_env(bundle / "BNG2.pl", cwd=work)["BNGPATH"]
    assert rel == os.path.join("..", "..", "bng-win")
    assert os.path.realpath(os.path.join(str(work), rel)) == real
    # a run folder outside it would carry the ' again: keep the whole path
    elsewhere = search / "elsewhere"
    elsewhere.mkdir()
    assert settings.bng_env(bundle / "BNG2.pl",
                            cwd=elsewhere)["BNGPATH"] == real


def test_a_bngpath_outside_the_ansi_code_page_is_given_its_8dot3_form(
        search, monkeypatch):
    """Windows Perl builds %ENV in the ANSI code page, so BNG2.pl's `use lib
    catdir($ENV{BNGPATH}, 'Perl2')` read Łukasz 李 as ?ukasz ? and could not
    load its own modules: the self-test failed and told the student to
    reinstall BioNetGen, which changes nothing. The 8.3 form goes in
    instead; José fits the code page and keeps its name."""
    def folder(name: str) -> Path:
        bundle = search / name / "bng-win"
        bundle.mkdir(parents=True)
        (bundle / "BNG2.pl").write_text("# stub\n")
        return bundle

    lukasz, jose = folder("Łukasz 李"), folder("José")
    short = "C:\\Users\\UKASZ~1\\bng-win"
    asked = []

    def api(s, buf, n):
        asked.append(s)
        if buf is None:
            return len(short) + 1
        buf.value = short
        return len(short)

    win = {"_platform": "win32", "_codec": "cp1252"}
    real = os.path.realpath(str(lukasz))
    assert settings.bng_env(lukasz / "BNG2.pl", _api=api,
                            **win)["BNGPATH"] == short
    assert set(asked) == {real}         # the folder itself, never its name
    asked.clear()
    assert settings.bng_env(jose / "BNG2.pl", _api=api, **win)["BNGPATH"] \
        == os.path.realpath(str(jose))
    assert asked == []
    # no 8.3 name (the drive makes none): the long one stays pinned, since
    # the preflight refuses the folder, and a BNGPATH an earlier install
    # left never decides
    monkeypatch.setenv("BNGPATH", STALE)
    assert settings.bng_env(lukasz / "BNG2.pl", _api=lambda *a: 0,
                            **win)["BNGPATH"] == real
    # macOS and Linux read the environment as it is: unchanged there
    assert settings.bng_env(lukasz / "BNG2.pl", _platform="linux",
                            _api=api)["BNGPATH"] == real


# --------------------------------------------------- the runners' environment

def test_runners_get_bng_env_on_windows_and_what_they_are_given(tmp_path,
                                                                monkeypatch):
    stub = tmp_path / "bng" / "BNG2.pl"
    stub.parent.mkdir()
    stub.write_text("# stub\n")
    monkeypatch.setattr(settings, "BNG", stub)
    # production on macOS/Linux: inherited, as before
    assert "env" not in pf.runner_popen_kwargs({}, _os_name="posix")
    # Windows: pinned (retro's runners come through here too)
    nt = pf.runner_popen_kwargs({}, _os_name="nt")
    assert nt["env"]["BNGPATH"] == os.path.realpath(str(stub.parent))
    # the Sandbox passes its own, on every platform
    given = {"BNGPATH": "x"}
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env=given)
    assert kw["env"] is given


def test_execute_gives_the_runners_the_environment_it_is_handed(
        tmp_path, monkeypatch):
    """A runner (this interpreter and a stub pybnf) records the BNGPATH it
    sees: the one execute() was handed, not this process's."""
    pkg = tmp_path / "fake" / "pybnf"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "parse.py").write_text("def load_config(p):\n    return p\n")
    (pkg / "pf.py").write_text(
        "import os\n"
        "class ParticleFilter:\n"
        "    def __init__(self, cfg):\n"
        "        pass\n"
        "    def run(self, _):\n"
        "        with open('bngpath.txt', 'w') as fh:\n"
        "            fh.write(os.environ.get('BNGPATH', ''))\n")
    monkeypatch.setattr(pf, "PYBNF_PF", pkg.parent)
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    monkeypatch.setattr(pf, "_sleep", lambda _s: time.sleep(0.02))
    monkeypatch.setenv("BNGPATH", STALE)
    w = tmp_path / "wr"
    cell = w / "c0"
    cell.mkdir(parents=True)
    (cell / "pf.conf").write_text("")
    (w / "cells.json").write_text(json.dumps(
        [{"key": "c0", "dir": str(cell), "n_obs": 1, "particles": 10}]))
    pinned = os.path.join(str(tmp_path), "bng")
    status = pf.execute(w, width=1, env=dict(os.environ, BNGPATH=pinned))
    assert status == {"c0": "ok"}
    assert (cell / "bngpath.txt").read_text() == pinned


def test_a_sandbox_run_hands_the_engine_bng_env(sandbox_root, monkeypatch,
                                                tmp_path):
    stub = tmp_path / "bng" / "BNG2.pl"
    stub.parent.mkdir()
    stub.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(stub))
    monkeypatch.setenv("BNGPATH", STALE)
    sb.add_example("kinetics_example")
    w = sb.prepare("kinetics_example")
    seen = {}

    def fake_execute(workroot, width=None, timeout=None, env=None):
        seen["env"] = env
        return {"kinetics_example_r0": "ok"}
    monkeypatch.setattr(sb.pf_engine, "execute", fake_execute)
    sb.run(w)
    assert seen["env"]["BNGPATH"] == os.path.realpath(str(stub.parent))


# ------------------------------------------- BNG2.pl's output and its failure

def test_bng2pl_output_is_read_in_the_ansi_code_page_on_windows(monkeypatch):
    """Perl prints the paths it holds in the ANSI code page: under
    PYTHONUTF8=1 a strict UTF-8 read of é failed."""
    import locale
    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252",
                        raising=False)
    kw = pf.bng_run_kwargs(_os_name="nt")
    assert kw == {"encoding": "cp1252", "errors": "replace"}
    prog = ("import sys; sys.stdout.buffer.write("
            "b'full command: C:\\\\Users\\\\Jos\\xe9\\\\bin \\x81')")
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       **kw)
    assert r.stdout == "full command: C:\\Users\\José\\bin \ufffd"
    # macOS and Linux read as before; an env rides along only when given
    assert pf.bng_run_kwargs(_os_name="posix") == {"text": True}
    assert pf.bng_run_kwargs({"A": "1"}, _os_name="posix") == {
        "text": True, "env": {"A": "1"}}


def test_the_failure_text_leads_with_the_line_that_names_the_cause():
    inc = " ".join(f"C:/Strawberry/perl/lib{i}" for i in range(30))
    err = ("Can't locate BNGUtils.pm in @INC (you may need to install the "
           "BNGUtils module) (@INC entries checked: "
           f"C:\\BioNetGen-2.5.1/Perl2 "
           f"{inc}) at C:\\Users\\jdoe\\BNG2.pl line 50.\n"
           "BEGIN failed--compilation aborted at C:\\Users\\jdoe\\BNG2.pl "
           "line 50.\n")
    r = types.SimpleNamespace(stdout="", stderr=err, returncode=2)
    text = pf.bng_failure_text(r)
    first = text.splitlines()[0]
    assert first.startswith("Can't locate BNGUtils.pm")
    assert "C:\\BioNetGen-2.5.1/Perl2" in first          # the stale folder
    assert text.rstrip().endswith("BNG2.pl line 50.")
    assert "BEGIN failed" in text
    # stdout last, cut from its start; a None stream (Windows' reader
    # thread) is no TypeError; nothing at all says so
    r = types.SimpleNamespace(stdout="x" * 1000 + "Read 7 parameters",
                              stderr="ABORT: Molecule Q not defined\n")
    parts = pf.bng_failure_text(r, sep=" | ").split(" | ")
    assert parts[0] == "ABORT: Molecule Q not defined"
    assert parts[1].startswith("... ")
    assert parts[1].endswith("Read 7 parameters")
    assert len(parts[1]) == 4 + pf.BNG_OUT_TAIL
    assert pf.bng_failure_text(types.SimpleNamespace(stdout=None,
                                                     stderr=None)) == \
        "BNG2.pl printed nothing"


def test_the_reinstall_remedy_reinstalls_bionetgen_alone(monkeypatch):
    """--force-reinstall alone reinstalls every dependency too (numpy,
    pandas, about a hundred packages), and on Windows pip stops at "Access
    is denied" on a .pyd the open console has loaded. BNG2.pl's start needs
    only bionetgen's own files and Perl."""
    monkeypatch.delenv("FLUBNF_BNG", raising=False)
    for plat in ("win32", "linux"):
        msg = pf.bng_broken_message("Can't locate BNGUtils.pm", plat)
        assert (f"{sys.executable}\" -m pip" if plat == "win32"
                else f"{sys.executable} -m pip") in msg, msg
        assert "-m pip install --force-reinstall --no-deps bionetgen" in msg


def test_the_sandboxs_netgen_failure_keeps_perls_first_line(sandbox_root,
                                                            monkeypatch):
    """A run that dies before BioNetGen's banner is this computer's
    failure (test_sandbox_machine.py), said with Perl's first line."""
    sb.add_example("kinetics_example")
    head = ("Can't locate BNGUtils.pm in @INC (@INC entries checked: "
            "/gone/BioNetGen-2.5.1/Perl2 " + "/usr/share/perl5 " * 40 + ")")

    def dies(cmd, **kw):
        return types.SimpleNamespace(
            stdout="", returncode=2,
            stderr=head + "\nBEGIN failed--compilation aborted at line 50.\n")
    monkeypatch.setattr(sb.subprocess, "run", dies)
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    notice, tip = sb.split_reason(str(e.value))
    assert notice == ("BioNetGen's BNG2.pl does not start on this computer, "
                      "so no network can be generated and no fit can start.")
    assert "Perl said: Can't locate BNGUtils.pm" in tip
    assert "/gone/BioNetGen-2.5.1/Perl2" in tip
    # after the banner the model is at fault, in BNG2.pl's own words
    monkeypatch.setattr(sb.subprocess, "run", lambda cmd, **kw: (
        types.SimpleNamespace(stdout="BioNetGen version 2.9.3\n" + "x" * 900,
                              stderr="ABORT: Molecule Q not defined\n",
                              returncode=1)))
    with pytest.raises(sb.SandboxError) as e:
        sb.prepare("kinetics_example")
    notice, tip = sb.split_reason(str(e.value))
    assert notice == "BNG2.pl could not generate the network:"
    assert tip.startswith("ABORT: Molecule Q not defined")


# ------------------------------------------ the real BNG2.pl, stale BNGPATH

def test_a_stale_bngpath_no_longer_breaks_the_sandboxs_netgen(real_bng,
                                                             tmp_path,
                                                             monkeypatch):
    """At 7e8390a this died at compile time ("Can't locate BNGUtils.pm")
    and wrote no m.net."""
    monkeypatch.setattr(sb, "BNG", str(real_bng))
    monkeypatch.setenv("BNGPATH", STALE)
    cell = tmp_path / "cell"
    cell.mkdir()
    shutil.copy(EXAMPLE / "model.bngl", cell / "m.bngl")
    sb._netgen(cell)
    assert (cell / "m.net").is_file()


def test_a_stale_bngpath_no_longer_fails_check_as_a_model_problem(
        real_bng, tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "BNG", str(real_bng))
    monkeypatch.setattr(cm, "BNG", str(real_bng))
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "sandbox")
    monkeypatch.setattr(sb, "RUNS", tmp_path / "sandbox" / "runs")
    monkeypatch.setenv("BNGPATH", STALE)
    files = {n: (EXAMPLE / n).read_text() for n in sb.REQUIRED}
    r = sb.check(files, work=tmp_path / "check")
    assert r["facts"]["network"] == "generates", r["problems"]
    assert r["problems"] == []
    net = cm.network_from_bngl(files["model.bngl"], tmp_path / "views")
    assert "begin reactions" in net


def test_production_netgen_is_unchanged_but_its_failure_names_the_cause(
        real_bng, tmp_path, monkeypatch):
    """pf.prepare on macOS and Linux runs BNG2.pl as before, so a stale
    BNGPATH still fails there (the conf decision is Ely's); the record now
    says why instead of 'netgen failed for Ohio: '."""
    if os.name == "nt":
        pytest.skip("Windows pins BNGPATH in production too")
    _prepare_env(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "BNG", real_bng)
    monkeypatch.setenv("BNGPATH", STALE)
    with pytest.raises(RuntimeError) as e:
        pf.prepare(_spec(), tmp_path / "wr")
    msg = str(e.value)
    assert "netgen failed for Ohio: Can't locate BNGUtils.pm" in msg
    fails = (tmp_path / "wr" / pf.PREPARE_FAILURES_NAME).read_text()
    assert STALE in fails                     # within the 200 kept


def test_production_netgen_call_is_the_same_off_windows(tmp_path,
                                                        monkeypatch):
    """macOS and Linux: bare perl, text=True, the inherited environment.
    Windows: the same bare perl (resolve_perl put the native one first on
    PATH), the ANSI read and bng_env."""
    _prepare_env(monkeypatch, tmp_path)
    stub = tmp_path / "bng" / "BNG2.pl"
    stub.parent.mkdir()
    stub.write_text("# stub\n")
    monkeypatch.setattr(settings, "BNG", stub)
    monkeypatch.setattr(pf, "perl_available", lambda: True)
    calls, real = [], subprocess.run

    def netgen(cmd, **kw):
        if cmd[-1] != "m.bngl":
            return real(cmd, **kw)
        calls.append((cmd, kw))
        (Path(kw["cwd"]) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(pf.subprocess, "run", netgen)
    pf.prepare(_spec(), tmp_path / "wr")
    cmd, kw = calls[0]
    assert cmd == ["perl", stub, "m.bngl"]
    if os.name == "nt":
        assert kw["errors"] == "replace" and kw["env"]["BNGPATH"]
    else:
        assert set(kw) == {"capture_output", "cwd", "timeout", "text"}


class _State:
    def __init__(self):
        import numpy as np
        self.times = np.array([12, 13, 14])
        self.observed = np.array([4.0, 5.0, 6.0])
        self.n_obs = 3
        self.last_week_offset = 14
        self.i0 = 5e-3
        self.rhomult = 0.05


def _spec():
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": ["Ohio"], "replicates": 1,
        "particles": 100, "jitter": 0.15,
        "observable_mode": "integrated", "extra": None})()


def _prepare_env(monkeypatch, tmp_path):
    """pf.prepare up to its BNG2.pl call: the state, model and data stubbed
    (test_perl_preflight.py's stubs)."""
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None,
                         **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p
    monkeypatch.setattr(sf, "resolve_state", lambda loc, **kw: _State())
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp",
                        lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))


# ------------------------------------------------ paths Perl can read (W08)

def test_perl_path_keeps_a_readable_path_and_falls_back_to_8dot3():
    assert pf.perl_path("/home/José/x", _platform="linux") == "/home/José/x"
    # José fits the ANSI code page of an English Windows: unchanged
    jose = "C:\\Users\\José\\BNG2.pl"
    assert pf.perl_path(jose, _platform="win32", _codec="cp1252") == jose
    short = "C:\\Users\\UKASZ~1\\BNG2.pl"

    def api(s, buf, n):
        if buf is None:
            return len(short) + 1
        buf.value = short
        return len(short)
    lukasz = "C:\\Users\\Łukasz 李\\BNG2.pl"
    assert pf.perl_path(lukasz, _platform="win32", _api=api,
                        _codec="cp1252") == short
    # no short name (8.3 creation off), or one Perl still cannot read
    assert pf.perl_path(lukasz, _platform="win32", _api=lambda *a: 0,
                        _codec="cp1252") is None
    short = "C:\\Users\\ŁUKASZ~1\\BNG2.pl"
    assert pf.perl_path(lukasz, _platform="win32", _api=api,
                        _codec="cp1252") is None


def test_the_preflight_refuses_a_folder_perl_cannot_read(sandbox_root,
                                                         monkeypatch):
    monkeypatch.setattr(pf, "perl_path", lambda p: None)
    msg = sb.machine_problem()
    notice, tip = sb.split_reason(msg)
    assert notice == "Perl cannot read the name of the folder FluBNF is in."
    assert "C:\\Users\\Public\\FluBNF\\flubnf" in tip
    assert "open FluBNF.bat there" in tip
    sb.add_example("kinetics_example")
    with pytest.raises(sb.SandboxError):
        sb.prepare("kinetics_example")
    # Check: a machine problem, so the network is not run as the model's
    stub = sandbox_root / "BNG2.pl"
    stub.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(stub))
    r = sb.check(sb.read_model("kinetics_example"))
    assert r["facts"]["machine"] == notice
    assert r["facts"]["network"].startswith("not checked (Perl cannot read")
    assert r["problems"] == []


# ------------------------------------------------------------------ doctor

def test_doctor_reports_perl_as_the_preflight_finds_it(monkeypatch):
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    monkeypatch.setattr(pf, "resolve_perl", lambda: "/opt/perl/bin/perl")
    res = doctor._check_perl()
    assert res.status is doctor.Status.OK
    assert res.detail == "/opt/perl/bin/perl"
    monkeypatch.setattr(pf, "resolve_perl", lambda: None)
    # an engine is installed (conftest's stub fork): every fit is refused
    res = doctor._check_perl()
    assert res.status is doctor.Status.FAIL
    assert "not found on PATH" in res.detail
    assert res.hint == pf.perl_missing_message()
    # no engine: a WARN, since the console still runs, but the Sandbox's
    # Check runs BNG2.pl with no engine, so fits are not all that need it
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    res = doctor._check_perl()
    assert res.status is doctor.Status.WARN
    assert "fits and the Sandbox's Check need it" in res.detail
    # a perl found and passed over is named
    monkeypatch.setattr(settings, "_PERL", {
        "os": {}, "unusable": ("C:\\Git\\usr\\bin\\perl.exe", "msys")})
    assert "C:\\Git\\usr\\bin\\perl.exe is not a Windows perl" in \
        doctor._check_perl().detail
    names = [c.name for c in doctor.run_doctor().checks]
    assert names.index("Perl") == names.index("BNG2.pl") + 1


# ------------------------------------------------------ FluBNF's own Perl

def _own_perl(local: Path, log: Path, marker: str | None = None) -> Path:
    """FluBNF's own Perl as FluBNF.bat leaves it under `local`
    (%LOCALAPPDATA%): perl.exe in Library\\bin and the marker, written
    last, naming the package."""
    root = local / "FluBNF" / "perl"
    exe = _fake_perl(root / "Library" / "bin", "MSWin32", log)
    (root / "flubnf-perl.ok").write_bytes(
        ((marker or settings.OWN_PERL_PACKAGE) + "\r\n").encode("ascii"))
    return exe


def test_own_perl_counts_only_when_its_marker_names_the_pinned_package(
        search, monkeypatch):
    local = search / "local"
    assert settings.own_perl_dir() is None              # nothing unpacked
    exe = _own_perl(local, search / "log")
    assert settings.own_perl_dir() == str(exe.parent)
    # a marker from another package (an older pin) is not this Perl
    (exe.parents[2] / "flubnf-perl.ok").write_text("perl-5.20.3.1-2.tar.bz2\n")
    assert settings.own_perl_dir() is None
    # an unpack that stopped before the marker
    (exe.parents[2] / "flubnf-perl.ok").unlink()
    assert settings.own_perl_dir() is None
    # a marker with no perl.exe beside it
    _own_perl(local, search / "log")
    exe.unlink()
    assert settings.own_perl_dir() is None
    monkeypatch.delenv("LOCALAPPDATA")
    assert settings.own_perl_dir() is None


@posix_only
def test_the_console_runs_flubnfs_own_perl_first(search, monkeypatch):
    """FluBNF.bat puts its own Perl first on the window's PATH, and the
    console looks there first too, so a Strawberry Perl elsewhere on PATH
    does not make the two run different perls."""
    log = search / "log"
    other = _fake_perl(search / "Strawberry" / "perl" / "bin", "MSWin32", log)
    monkeypatch.setenv("PATH", str(other.parent))
    own = _own_perl(search / "local", log)

    assert settings.resolve_perl(_platform="win32") == str(own)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(own.parent)


@posix_only
def test_bng_env_drops_other_perls_settings_for_flubnfs_own(search, tmp_path,
                                                            monkeypatch):
    """PERL5LIB, PERLLIB and PERL5OPT would put another Perl's modules or
    options in front of FluBNF's own; a Strawberry user's are left alone."""
    own = _own_perl(search / "local", search / "log")
    monkeypatch.setattr(settings, "_windows", lambda: True)
    for var in ("PERL5LIB", "PERLLIB", "PERL5OPT"):
        monkeypatch.setenv(var, r"C:\old\lib")
    env = settings.bng_env(tmp_path / "no-bng" / "BNG2.pl")
    assert env["PATH"].split(os.pathsep)[0] == str(own.parent)
    for var in ("PERL5LIB", "PERLLIB", "PERL5OPT"):
        assert var not in env, var
        assert os.environ[var] == r"C:\old\lib"       # this process's kept

    (own.parents[2] / "flubnf-perl.ok").unlink()
    _fake_perl(search / "sp", "MSWin32", search / "log")
    monkeypatch.setenv("PATH", str(search / "sp"))
    monkeypatch.setattr(settings, "_PERL", {"os": {}, "unusable": None})
    env = settings.bng_env(tmp_path / "no-bng" / "BNG2.pl")
    assert env["PERL5LIB"] == r"C:\old\lib"


# ------------------------------------------- bngsim's code generation, Windows

def test_windows_runners_fit_without_bngsims_code_generation(monkeypatch):
    """On Windows every engine runner (Sandbox, Forecast, Retrospective)
    gets BNGSIM_NO_CODEGEN=1: no C compiler to install, and no gcc from
    another program compiling a library that then fails to load. macOS and
    Linux keep code generation."""
    given = {"PATH": "x", "BNGPATH": "y"}
    nt = pf.runner_popen_kwargs({}, _os_name="nt", env=given)
    assert nt["env"]["BNGSIM_NO_CODEGEN"] == "1"
    assert nt["env"]["BNGPATH"] == "y"
    assert "BNGSIM_NO_CODEGEN" not in given             # the caller's untouched
    # nothing to pin: still set, on this process's environment
    monkeypatch.setattr(pf, "bng_env", lambda *a, **k: None)
    monkeypatch.delenv("BNGSIM_NO_CODEGEN", raising=False)
    nt = pf.runner_popen_kwargs({}, _os_name="nt")
    assert nt["env"]["BNGSIM_NO_CODEGEN"] == "1"
    assert nt["env"]["PATH"] == os.environ.get("PATH")
    # a value someone set on purpose stays
    nt = pf.runner_popen_kwargs({}, _os_name="nt", env={"BNGSIM_NO_CODEGEN": "yes"})
    assert nt["env"]["BNGSIM_NO_CODEGEN"] == "yes"
    # macOS and Linux: as before
    assert "env" not in pf.runner_popen_kwargs({}, _os_name="posix")
    kw = pf.runner_popen_kwargs({}, _os_name="posix", env=given)
    assert kw["env"] is given and "BNGSIM_NO_CODEGEN" not in given
