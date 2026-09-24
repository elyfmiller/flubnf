"""The offline engine bundle: install the private PyBNF fork with no GitHub
account or network.

`git bundle create pybnf.bundle feature/particle-filter` makes the fork one
file; setup_engine.sh must FIND it (repo, beside it, Downloads, Desktop,
Documents) and clone from it. FLUBNF_ENGINE_CHECKOUT_ONLY=1 stops after the
checkout (the venv build needs minutes and a network). Executing tests are
POSIX-only; FluBNF.bat, the Windows twin, is checked as text everywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "setup_engine.sh"
SRC = SCRIPT.read_text(encoding="utf-8")

posix_only = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="setup_engine.sh is the POSIX setup; FluBNF.bat is its twin")

# A remote that cannot exist: a run that reaches the network path fails, so
# every executing test proves the BUNDLE did the work.
NOWHERE = "/nonexistent/PyBNF-Private.git"


def _make_bundle(tmp_path: Path) -> Path:
    """A real git bundle of a real branch, a few hundred bytes of it."""
    src = tmp_path / "fork"
    src.mkdir()
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", *a], cwd=src, check=True, capture_output=True)
    run("init", "-q", "-b", "main", ".")
    (src / "README").write_text("stand-in for the fork\n")
    run("add", "README")
    run("-c", "user.email=t@example.invalid", "-c", "user.name=t",
        "commit", "-qm", "init")
    run("checkout", "-q", "-b", "feature/particle-filter")
    (src / "pf.py").write_text("class ParticleFilter: pass\n")
    run("add", "pf.py")
    run("-c", "user.email=t@example.invalid", "-c", "user.name=t",
        "commit", "-qm", "pf")
    bundle = tmp_path / "made" / "pybnf.bundle"
    bundle.parent.mkdir()
    run("bundle", "create", str(bundle), "feature/particle-filter")
    return bundle


def _run(script: Path, home: Path, *, dest: Path | None = None,
         args: tuple[str, ...] = (), **env_extra) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "HOME": str(home),
        # never hang on a password prompt
        "GIT_TERMINAL_PROMPT": "0",
        "FLUBNF_PYBNF_REMOTE": NOWHERE,
        "FLUBNF_ENGINE_CHECKOUT_ONLY": "1",
        # the fallback probes github.com once; bound it so a machine with no
        # route out does not stall for minutes
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "http.lowSpeedLimit",
        "GIT_CONFIG_VALUE_0": "1000",
        "GIT_CONFIG_KEY_1": "http.lowSpeedTime",
        "GIT_CONFIG_VALUE_1": "5",
    }
    for k in ("FLUBNF_PYBNF", "FLUBNF_PYBNF_BUNDLE"):
        env.pop(k, None)
    if dest is not None:
        env["FLUBNF_PYBNF"] = str(dest)
    env.update({k: str(v) for k, v in env_extra.items()})
    return subprocess.run([str(script), *args], capture_output=True, text=True,
                          timeout=180, env=env)


def _home(tmp_path: Path) -> Path:
    """A fake profile with the folders a download lands in."""
    home = tmp_path / "home"
    for d in ("Downloads", "Desktop", "Documents"):
        (home / d).mkdir(parents=True)
    return home


@posix_only
def test_a_bundle_in_downloads_installs_the_fork_with_no_credentials(tmp_path):
    """The whole point: the file is in Downloads, so nobody logs in."""
    bundle = _make_bundle(tmp_path)
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf.bundle").write_bytes(bundle.read_bytes())
    dest = tmp_path / "PyBNF-pf"

    out = _run(SCRIPT, home, dest=dest)

    assert out.returncode == 0, out.stdout + out.stderr
    assert (dest / ".git").is_dir(), out.stdout + out.stderr
    branch = subprocess.run(["git", "-C", str(dest), "branch", "--show-current"],
                            capture_output=True, text=True, check=True)
    assert branch.stdout.strip() == "feature/particle-filter"
    # the recorded remote is the fork, not the (often removable) bundle file
    url = subprocess.run(["git", "-C", str(dest), "remote", "get-url", "origin"],
                         capture_output=True, text=True, check=True)
    assert url.stdout.strip() == NOWHERE


@posix_only
@pytest.mark.parametrize("where", ["repo", "beside", "Downloads", "Desktop",
                                   "Documents"])
def test_the_search_covers_the_places_a_student_puts_a_download(tmp_path, where):
    """Five folders, because a student saves a file where they save files.
    The script is copied into a temp tree for the repo/beside cases."""
    bundle = _make_bundle(tmp_path)
    home = _home(tmp_path)
    tree = tmp_path / "GitHub" / "flubnf"
    tree.mkdir(parents=True)
    script = tree / "setup_engine.sh"
    script.write_bytes(SCRIPT.read_bytes())
    script.chmod(0o755)
    target = {"repo": tree,
              "beside": tree.parent,
              "Downloads": home / "Downloads",
              "Desktop": home / "Desktop",
              "Documents": home / "Documents"}[where]
    (target / "pybnf.bundle").write_bytes(bundle.read_bytes())

    out = _run(script, home, args=("--print-bundle",))

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(target / "pybnf.bundle"), (
        f"a bundle in {where} was not found; the printed answer was "
        f"{out.stdout.strip()!r}")


@posix_only
def test_print_bundle_prints_the_path_and_nothing_else(tmp_path):
    """FluBNF.command reads this in a command substitution, so a stray
    heading or a warning on stdout would become part of a filename."""
    bundle = _make_bundle(tmp_path)
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf.bundle").write_bytes(bundle.read_bytes())

    out = _run(SCRIPT, home, args=("--print-bundle",))

    assert out.stdout.splitlines() == [str(home / "Downloads" / "pybnf.bundle")]


@posix_only
def test_print_bundle_needs_no_engine_python(tmp_path):
    """--print-bundle must answer before the Python 3.11/3.12 probe: on a
    machine with neither, the probe's warnings (or a `conda create`) would
    otherwise land in the launchers' command substitution as the path."""
    import shutil

    bundle = _make_bundle(tmp_path)
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf.bundle").write_bytes(bundle.read_bytes())
    # PATH: bash, dirname, a python3 that is not 3.11/3.12, and a conda that
    # records being asked (only reached where no absolute-path candidate
    # exists; the stdout check holds everywhere).
    shim = tmp_path / "bin"
    shim.mkdir()
    for tool in ("bash", "dirname"):
        (shim / tool).symlink_to(shutil.which(tool))
    marker = tmp_path / "conda-was-called"
    (shim / "python3").write_text("#!/bin/sh\nexit 1\n")
    (shim / "conda").write_text(f"#!/bin/sh\n: > '{marker}'\nexit 1\n")
    for tool in ("python3", "conda"):
        (shim / tool).chmod(0o755)

    out = _run(SCRIPT, home, args=("--print-bundle",), PATH=str(shim))

    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.splitlines() == [str(home / "Downloads" / "pybnf.bundle")]
    assert not marker.exists(), "--print-bundle ran the conda fallback"


@posix_only
def test_no_bundle_prints_nothing_rather_than_a_guess(tmp_path):
    out = _run(SCRIPT, _home(tmp_path), args=("--print-bundle",))
    assert out.returncode == 0
    assert out.stdout.strip() == ""


@posix_only
def test_a_named_bundle_wins_and_a_missing_named_one_is_not_silent(tmp_path):
    """FLUBNF_PYBNF_BUNDLE wins; a missing named file falls back to the search
    but says so, so a typo does not read as success."""
    bundle = _make_bundle(tmp_path)
    home = _home(tmp_path)
    kept = tmp_path / "shared drive" / "engine.bundle"
    kept.parent.mkdir()
    kept.write_bytes(bundle.read_bytes())

    named = _run(SCRIPT, home, args=("--print-bundle",),
                 FLUBNF_PYBNF_BUNDLE=kept)
    assert named.stdout.strip() == str(kept)

    # a typo, with a perfectly good bundle in Downloads to fall back to
    (home / "Downloads" / "pybnf.bundle").write_bytes(bundle.read_bytes())
    typo = _run(SCRIPT, home, args=("--print-bundle",),
                FLUBNF_PYBNF_BUNDLE=tmp_path / "no-such.bundle")
    assert typo.stdout.strip() == str(home / "Downloads" / "pybnf.bundle")
    assert "no-such.bundle" in typo.stderr, (
        "a FLUBNF_PYBNF_BUNDLE that does not exist was ignored without a "
        "word, so a typo reads as success")


@posix_only
def test_a_directory_named_bundle_is_not_taken_for_one(tmp_path):
    """On macOS ".bundle" is also a directory type; never offer a folder to
    `git clone`."""
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf-something.bundle").mkdir()

    out = _run(SCRIPT, home, args=("--print-bundle",))

    assert out.stdout.strip() == "", (
        "a DIRECTORY named *.bundle was offered as a git bundle")


@posix_only
def test_a_truncated_bundle_blames_the_file_and_falls_back(tmp_path):
    """A half-copied bundle: the message blames the file and the run falls
    back. The message lives on the CLONE because `git bundle verify` accepts
    a truncated pack (it checks the header only)."""
    whole = _make_bundle(tmp_path).read_bytes()
    home = _home(tmp_path)
    bad = home / "Downloads" / "pybnf.bundle"
    bad.write_bytes(whole[:len(whole) // 2])
    dest = tmp_path / "PyBNF-pf"

    verify = subprocess.run(["git", "bundle", "verify", str(bad)],
                            capture_output=True, text=True)
    assert verify.returncode == 0, (
        "git bundle verify now rejects a truncated bundle; if that holds on "
        "every git in the lab, the clone-side message could move back to it")

    out = _run(SCRIPT, home, dest=dest)

    assert not (dest / ".git").exists(), "a corrupt bundle produced a checkout"
    assert "the clone from that bundle FAILED" in out.stdout, out.stdout
    assert "early EOF" in out.stdout, (
        "the message no longer quotes the words git actually prints, which "
        "are the words a student will search for")
    # the GitHub route is still offered: the bundle is a shortcut, not a
    # requirement
    assert "fork access (needed to clone)" in out.stdout
    assert out.returncode == 1


@posix_only
def test_a_file_that_is_not_a_bundle_at_all_says_so(tmp_path):
    """An error page saved as pybnf.bundle gets its own message (the remedy
    differs from the truncated case)."""
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf.bundle").write_text(
        "<html><body>404 Not Found</body></html>\n")
    dest = tmp_path / "PyBNF-pf"

    out = _run(SCRIPT, home, dest=dest)

    assert "not a git bundle at all" in out.stdout, out.stdout
    assert not (dest / ".git").exists()
    assert "fork access (needed to clone)" in out.stdout


def test_the_bundle_is_tried_before_anything_that_needs_an_account():
    """The local bundle is tried before any network probe that could end at a
    password prompt."""
    bundle_at = SRC.index('say "offline engine bundle"')
    access_at = SRC.index('say "fork access (needed to clone)"')
    assert bundle_at < access_at, (
        "setup_engine.sh probes GitHub before it looks for a local bundle")
    assert SRC.index("git bundle verify") < SRC.index("git ls-remote")


def test_the_no_bundle_path_says_where_it_looked():
    """The no-bundle message says where it looked and names both artifact
    shapes (tar.gz is what students are sent)."""
    assert "no engine file found. Looked for pybnf*.tar.gz and pybnf*.bundle in:" in SRC
    assert "engine_bundle_dirs | sed" in SRC, (
        "the folders searched are no longer printed, so a student cannot "
        "tell where to put the file")


def test_the_launchers_ask_the_script_rather_than_repeating_the_search():
    """The launchers ask setup_engine.sh (--print-bundle) instead of keeping
    their own copy of the search."""
    for name in ("FluBNF.command", "SetupEngine.command"):
        src = (REPO / name).read_text(encoding="utf-8")
        assert "--print-bundle" in src, (
            f"{name} does not ask setup_engine.sh where the bundle is")
        assert "*.bundle" not in src, (
            f"{name} has grown its own copy of the bundle search")


# --- FluBNF.bat (never executed in CI): text checks; a mistyped label is a
# silent jump to nowhere, which a text check can catch ---

BAT = (REPO / "FluBNF.bat").read_text(encoding="utf-8")


def _bat_labels_and_targets():
    labels, targets = set(), []
    for line in BAT.splitlines():
        s = line.strip()
        if s.startswith(":") and not s.startswith("::"):
            labels.add(s[1:].split()[0].lower())
        low = s.lower()
        for kw in ("goto :", "call :"):
            at = low.find(kw)
            while at != -1:
                targets.append(low[at + len(kw):].split()[0].split(">")[0])
                at = low.find(kw, at + 1)
    return labels, targets


def test_every_jump_in_the_windows_launcher_lands_somewhere():
    """A goto to a missing label ends the script silently (no console)."""
    labels, targets = _bat_labels_and_targets()
    missing = sorted({t for t in targets if t not in labels and t != "eof"})
    assert not missing, f"FluBNF.bat jumps to labels that do not exist: {missing}"


def _engine_section() -> str:
    """The text between the :launch and :startconsole LABELS (matched at line
    start: `goto :launch` appears earlier than the label)."""
    import re
    start = re.search(r"^:launch\b", BAT, re.M)
    end = re.search(r"^:startconsole\b", BAT, re.M)
    assert start and end and start.start() < end.start(), (
        "FluBNF.bat no longer has the :launch ... :startconsole section the "
        "engine install lives in")
    return BAT[start.start():end.start()]


def test_every_windows_engine_path_ends_at_the_console():
    """No engine branch may leave the user without a console or park
    unattended: a `choice` is legal only bounded (/t and /d); no pause, no
    exit."""
    engine = _engine_section()
    assert "pause" not in engine, "the engine section can stop at a prompt"
    for ln in engine.splitlines():
        # an invocation starts the line; `where choice` and comments do not
        if ln.lstrip().lower().startswith("choice"):
            assert "/t " in ln and "/d " in ln, (
                "an engine-section choice must be bounded (needs /t and /d): "
                + ln.strip())
    assert "exit /b" not in engine, (
        "the engine section can exit without opening the console")
    for label in ("enginefailed", "engineskipped", "enginebadbundle",
                  "enginebadclone", "enginenogit"):
        assert f":{label}" in engine, label


def test_the_windows_launcher_searches_the_same_five_places(tmp_path):
    """Same five folders as setup_engine.sh."""
    for needle in (r'"%~dp0pybnf*.bundle"',
                   r'"%~dp0..\pybnf*.bundle"',
                   r'"%USERPROFILE%\Downloads\pybnf*.bundle"',
                   r'"%USERPROFILE%\Desktop\pybnf*.bundle"',
                   r'"%USERPROFILE%\Documents\pybnf*.bundle"'):
        assert needle in BAT, f"FluBNF.bat no longer searches {needle}"
    assert 'git clone -b feature/particle-filter "%BUNDLE%" "%PYBNFDIR%"' in BAT
    assert 'git bundle verify "%BUNDLE%"' in BAT


def test_the_windows_launcher_probes_onedrive_known_folder_move():
    """OneDrive Known Folder Move relocates Desktop/Documents/Downloads, so
    both engine-file shapes get %OneDrive% probes, each guarded with `if
    defined` (an undefined %OneDrive% would match a drive-root \\Downloads).
    setup_engine.sh needs no twin: KFM is Windows-only."""
    for folder in ("Downloads", "Desktop", "Documents"):
        for shape in ("bundle", "tar.gz"):
            needle = ('if defined OneDrive for %%F in '
                      f'("%OneDrive%\\{folder}\\pybnf*.{shape}")')
            assert needle in BAT, (
                f"FluBNF.bat does not probe OneDrive {folder} for *.{shape}")
    assert 'for %%F in ("%OneDrive%' not in BAT.replace(
        'if defined OneDrive for %%F in ("%OneDrive%', ""), (
        "an %OneDrive% probe in FluBNF.bat is missing its `if defined` "
        "guard, so an undefined variable becomes a drive-root wildcard")


def test_the_windows_launcher_never_calls_the_network_on_the_engine_path():
    """No github.com probe on the engine path (it would cost a round trip on
    every launch); setup.ps1 does that once."""
    engine = _engine_section()
    assert "ls-remote" not in engine
    assert "git clone -b feature/particle-filter https" not in engine
    # the one allowed github.com URL is written into the checkout's origin,
    # never contacted
    for line in engine.splitlines():
        if "github.com" in line and not line.strip().startswith("rem"):
            assert line.strip().startswith("git -C"), line


def test_the_windows_launcher_resolves_the_fork_the_way_setup_does():
    """setup.ps1, FluBNF.bat and flubnf/settings.py must agree on where the
    checkout is."""
    order = [BAT.index(p) for p in (
        r"%USERPROFILE%\Documents\GitHub\PyBNF-pf",
        r"%LOCALAPPDATA%\FluBNF\PyBNF-pf",
        r"%USERPROFILE%\Documents\GitHub\PyBNF-Private",
        r"%LOCALAPPDATA%\FluBNF\PyBNF-Private")]
    assert order == sorted(order), (
        "FluBNF.bat no longer probes the four checkout locations in "
        "setup.ps1's order (PyBNF-pf before PyBNF-Private, and the old "
        "Documents default before the new one within each name)")
    # setup.ps1's order is checked only when its phrasing is found, so a
    # rewording there does not fail this test
    ps1 = (REPO / "setup.ps1").read_text(encoding="utf-8")
    pf_at = ps1.find('Resolve-Checkout $env:FLUBNF_PYBNF "PyBNF-pf"')
    private_at = ps1.find('Resolve-Checkout $null "PyBNF-Private"')
    if pf_at >= 0 and private_at >= 0:
        assert pf_at < private_at, (
            "setup.ps1 now prefers PyBNF-Private over PyBNF-pf; FluBNF.bat "
            "above still prefers PyBNF-pf, and the two must agree")


@pytest.mark.parametrize("pin", ['"numpy<2"', '"bngsim==0.15.1"',
                                 '"dask==2022.12.1"',
                                 '"distributed==2022.12.1"', "libroadrunner",
                                 "python-libsbml", "--no-deps"])
def test_the_windows_engine_installs_the_same_pinned_set(pin):
    """The engine pins are duplicated across launchers; they must match."""
    assert pin in BAT, f"FluBNF.bat no longer installs {pin}"
    assert pin in SRC or pin.replace('"', "") in SRC, (
        f"setup_engine.sh no longer installs {pin}")


def test_the_retry_stamp_moves_when_a_bundle_appears():
    """The launcher does not retry a failed engine setup on every open, so the
    stamp must include the bundle: dropping one in Downloads earns a retry."""
    src = (REPO / "FluBNF.command").read_text(encoding="utf-8")
    fp = [l for l in src.splitlines() if l.strip().startswith("FP=")]
    assert len(fp) == 1, fp
    assert "BUNDLE" in fp[0], (
        "the attempt fingerprint ignores the bundle, so dropping one in "
        "Downloads does not earn a retry")


def test_the_windows_retry_stamp_moves_when_the_launcher_is_updated():
    """The Windows fingerprint covers the installer code (%BATFP%, %PS1FP%),
    not just its inputs, so pulling a launcher fix retries exactly once."""
    src = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
    fp = [l for l in src.splitlines()
          if l.strip().startswith('set "ENGINEFP=')]
    assert len(fp) == 1, fp
    for component in ("%BUNDLE%", "%BATFP%", "%PS1FP%"):
        assert component in fp[0], (
            f"the Windows attempt fingerprint lost {component}: a pulled "
            "launcher fix would no longer earn a retry")
    # and the components must actually be derived from the two files
    assert 'for %%F in ("%~f0") do set "BATFP=' in src
    assert 'if exist setup.ps1 for %%F in (setup.ps1) do set "PS1FP=' in src


def test_the_retry_stamp_moves_when_a_BROKEN_bundle_is_replaced():
    """The stamp keys on bundle SIZE as well as path: re-fetching a truncated
    pybnf.bundle under the same name must earn the retry the error message
    asks for (wc -c: stat flags differ between macOS and Linux)."""
    src = (REPO / "FluBNF.command").read_text(encoding="utf-8")
    fp = [l for l in src.splitlines() if l.strip().startswith("FP=")][0]
    assert "BUNDLESZ" in fp, (
        "the attempt fingerprint is the bundle's path only, so replacing a "
        "truncated pybnf.bundle with a whole one under the same name does "
        "not earn the retry the error message promises")
    assert "wc -c" in src, (
        "the bundle size is measured with something other than wc -c; stat's "
        "flags differ between macOS and Linux")
    bat = (REPO / "FluBNF.bat").read_text(encoding="utf-8")
    assert "%%~zF" in bat and "%BUNDLESZ%" in bat, (
        "FluBNF.bat's fingerprint does not include the bundle size, so the "
        "Windows twin still suppresses the retry")


@posix_only
@pytest.mark.parametrize("kind", ["git", "unpacked"])
@pytest.mark.parametrize("name", ["PyBNF-pf", "PyBNF-Private"])
def test_an_engine_already_on_disk_is_never_sent_to_authenticate(
        tmp_path, kind, name):
    """An engine already on disk (git checkout or unpacked archive, named
    PyBNF-pf or PyBNF-Private) is used, never sent to authenticate: the
    engine needs an importable package, not git or a particular folder name."""
    home = _home(tmp_path)
    root = home / "Documents" / "GitHub"
    root.mkdir(parents=True)
    dest = root / name
    if kind == "git":
        bundle = _make_bundle(tmp_path)
        subprocess.run(["git", "clone", "-q", "-b", "feature/particle-filter",
                        str(bundle), str(dest)], check=True,
                       capture_output=True)
    else:
        (dest / "pybnf").mkdir(parents=True)
        (dest / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
        (dest / "setup.py").write_text("setup()\n")

    out = _run(SCRIPT, home)  # no FLUBNF_PYBNF: the automatic path

    assert out.returncode == 0, out.stdout + out.stderr
    assert "fork access (needed to clone)" not in out.stdout, (
        f"an engine already on disk ({kind} {name}) was sent to authenticate "
        f"to GitHub anyway")
    assert str(dest) in out.stdout, out.stdout


@posix_only
def test_the_launchers_accept_an_unpacked_copy_too(tmp_path):
    """The launchers' checkout predicate accepts an unpacked copy (no .git)."""
    dest = tmp_path / "PyBNF-Private"
    (dest / "pybnf").mkdir(parents=True)
    (dest / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
    (dest / "setup.py").write_text("setup()\n")
    predicate = (
        f'c={dest!s}; '
        'if [ -d "$c/.git" ] || { [ -f "$c/pybnf/pf.py" ] && '
        '[ -f "$c/setup.py" ]; }; then echo yes; fi')
    assert subprocess.run(["sh", "-c", predicate], capture_output=True,
                          text=True).stdout.strip() == "yes"
    for launcher in ("FluBNF.command", "SetupEngine.command"):
        src = (REPO / launcher).read_text(encoding="utf-8")
        assert '[ -f "$c/pybnf/pf.py" ]' in src, (
            f"{launcher} still requires a .git directory, so the unpacked "
            f"engine archive students are sent is treated as no engine")


def test_a_present_engine_file_always_earns_a_retry_despite_the_stamp():
    """The stamp suppresses only the doomed attempt (no bundle AND no
    checkout); with either present the launcher retries regardless."""
    src = (REPO / "FluBNF.command").read_text(encoding="utf-8")
    assert '[ -z "$BUNDLE$CHECKOUT" ] &&' in src, (
        "the stamp guard no longer requires an empty bundle-and-checkout, so "
        "a transient failure with the engine file present again suppresses "
        "the retry that would succeed")
    # and the recovery it points at is a double-click, not a Terminal command
    assert "double-click SetupEngine.command" in src
    assert "./setup_engine.sh\n" not in src.replace(
        "in Terminal", "")  # no lingering "run ./setup_engine.sh in Terminal"
    assert "setup_engine.sh in Terminal" not in src


@posix_only
def test_the_newest_archive_wins_when_an_old_one_is_still_in_downloads(tmp_path):
    """Newest archive by mtime wins (the hex sha in the name makes glob order
    random, which once installed a weeks-stale engine); more than one is
    reported on stderr, never stdout, which the launchers read as a path."""
    import os
    import time

    home = _home(tmp_path)
    old = home / "Downloads" / "pybnf-pf-3320d1f0.tar.gz"
    new = home / "Downloads" / "pybnf-pf-8b28edf4.tar.gz"
    for f in (old, new):
        f.write_bytes(b"not a real archive, the search never opens it")
    stale = time.time() - 9 * 24 * 3600
    os.utime(old, (stale, stale))          # the alphabetically first is older

    out = _run(SCRIPT, home, args=("--print-bundle",))

    assert out.stdout.splitlines() == [str(new)], (
        "the newest archive must win; the glob's alphabetical order picked "
        "the stale one and shipped a three week old engine")
    assert "using the newest" in out.stderr
    assert "3320d1f0" not in out.stdout


def _fake_archive(tmp_path: Path, stamp: str, name: str) -> Path:
    """An engine archive of the shape cut_engine_archive.sh produces: one top
    level folder holding pybnf/pf.py, setup.py and a VERSION stamp."""
    import tarfile
    root = tmp_path / f"src-{stamp.split()[-1]}" / "PyBNF-Private"
    (root / "pybnf").mkdir(parents=True)
    (root / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
    (root / "pybnf" / "__init__.py").write_text("")
    (root / "setup.py").write_text("from setuptools import setup; setup()\n")
    (root / "VERSION").write_text(stamp + "\n")
    arc = tmp_path / name
    with tarfile.open(arc, "w:gz") as t:
        t.add(root, arcname="PyBNF-Private")
    return arc


@posix_only
def test_a_newer_archive_replaces_a_stale_unpacked_engine(tmp_path):
    """A newer archive in Downloads replaces a stale unpacked copy, which is
    moved aside, not deleted."""
    home = _home(tmp_path)
    dest = tmp_path / "PyBNF-pf"
    old = _fake_archive(tmp_path, "feature/particle-filter 3320d1f0",
                        "pybnf-pf-3320d1f0.tar.gz")
    import tarfile
    with tarfile.open(old) as t:                    # the stale copy, on disk
        t.extractall(tmp_path / "unpacked")
    (tmp_path / "unpacked" / "PyBNF-Private").rename(dest)
    # the mtime guard reads install time: installed weeks before the download
    import os
    import time
    was = time.time() - 9 * 24 * 3600
    for f in (dest / "VERSION", dest):
        os.utime(f, (was, was))
    new = _fake_archive(tmp_path, "pf/pre-pr 8b28edf4", "pybnf-pf-8b28edf4.tar.gz")
    (home / "Downloads" / new.name).write_bytes(new.read_bytes())

    out = _run(SCRIPT, home, dest=dest)

    assert (dest / "VERSION").read_text().strip() == "pf/pre-pr 8b28edf4", (
        out.stdout + out.stderr)
    assert list(dest.parent.glob("PyBNF-pf.replaced-*")), "the old copy was destroyed"


@posix_only
def test_an_old_archive_left_in_downloads_cannot_downgrade_the_engine(tmp_path):
    """A stale archive left in Downloads must never replace a current engine."""
    import os
    import time

    home = _home(tmp_path)
    dest = tmp_path / "PyBNF-pf"
    current = _fake_archive(tmp_path, "pf/pre-pr 8b28edf4", "cur.tar.gz")
    import tarfile
    with tarfile.open(current) as t:
        t.extractall(tmp_path / "unpacked")
    (tmp_path / "unpacked" / "PyBNF-Private").rename(dest)
    stale = _fake_archive(tmp_path, "feature/particle-filter 3320d1f0",
                          "pybnf-pf-3320d1f0.tar.gz")
    landed = home / "Downloads" / stale.name
    landed.write_bytes(stale.read_bytes())
    was = time.time() - 9 * 24 * 3600            # downloaded before the install
    os.utime(landed, (was, was))

    out = _run(SCRIPT, home, dest=dest)

    assert (dest / "VERSION").read_text().strip() == "pf/pre-pr 8b28edf4", (
        "an older archive downgraded the engine\n" + out.stdout + out.stderr)


# A GNU tar stand-in: GNU tar does not glob member names without --wildcards
# (which bsdtar rejects), so the stamp read must not use a glob. A bsdtar-only
# suite cannot see the difference.
_GNU_TAR = """#!/bin/sh
for a in "$@"; do
  case "$a" in
    -*) ;;
    *[*?]*)
      echo "tar: $a: Not found in archive" >&2
      echo "tar: Exiting with failure status due to previous errors" >&2
      exit 2 ;;
  esac
done
exec {real} "$@"
"""


@posix_only
def test_a_stale_copy_is_replaced_under_gnu_tar_too(tmp_path):
    """The stale-copy replacement also works under GNU tar."""
    import os
    import shutil
    import tarfile
    import time

    real = shutil.which("tar")
    assert real, "no tar on PATH"
    shim = tmp_path / "gnu-tar-bin"
    shim.mkdir()
    (shim / "tar").write_text(_GNU_TAR.format(real=real))
    (shim / "tar").chmod(0o755)

    home = _home(tmp_path)
    dest = tmp_path / "PyBNF-pf"
    old = _fake_archive(tmp_path, "feature/particle-filter 3320d1f0",
                        "pybnf-pf-3320d1f0.tar.gz")
    with tarfile.open(old) as t:
        t.extractall(tmp_path / "unpacked")
    (tmp_path / "unpacked" / "PyBNF-Private").rename(dest)
    was = time.time() - 9 * 24 * 3600
    for f in (dest / "VERSION", dest):
        os.utime(f, (was, was))
    new = _fake_archive(tmp_path, "pf/pre-pr 8b28edf4", "pybnf-pf-8b28edf4.tar.gz")
    (home / "Downloads" / new.name).write_bytes(new.read_bytes())

    out = _run(SCRIPT, home, dest=dest,
               PATH=f"{shim}:{os.environ.get('PATH', '')}")

    assert (dest / "VERSION").read_text().strip() == "pf/pre-pr 8b28edf4", (
        "the stale engine survived a tar that does not glob member names\n"
        + out.stdout + out.stderr)


def test_the_windows_launcher_picks_the_newest_archive_and_replaces_a_stale_copy():
    """FluBNF.bat mirrors setup_engine.sh: every pybnf*.tar.gz search goes
    through :newerarchive (newest wins, not glob order), and an unpacked copy
    that already exists is sent to the stale check instead of being kept."""
    bat = BAT.replace("\r\n", "\n")
    archive_loops = [ln for ln in bat.split("\n")
                     if "pybnf*.tar.gz" in ln and ln.lstrip().startswith(("for ", "if defined OneDrive for "))]
    assert len(archive_loops) == 8
    assert all('do call :newerarchive "%%~fF"' in ln for ln in archive_loops)
    assert "if not defined ARCHIVE set" not in bat
    assert "\n:newerarchive\n" in bat and "\n:archivestale\n" in bat
    assert 'goto :archivestale' in bat
    # the old copy is renamed aside, never deleted
    stale = bat.split("\n:archivestale\n", 1)[1].split("\n:archivedone\n", 1)[0]
    assert 'ren "%PYBNFDIR%" "%KEPT%"' in stale
    # a working engine still reaches the console after the archive check
    assert "\n:archivedone\nif defined ENGINEOK goto :startconsole\n" in bat
