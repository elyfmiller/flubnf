"""The offline engine bundle: one file, no GitHub account, no network.

Cloning the PyBNF fork is the ONE step of a FluBNF install that needs
credentials, because that repository is private. Everything else -- this
repo, the FluSight hub, BioNetGen, both venvs -- is public and automatic,
and the console runs without the engine anyway (analogue member only). Two
students and one PI have now lost time to that single clone: a collaborator
invitation that was never accepted, a GitHub Desktop login that terminal git
does not share, and a machine whose keychain had cached the wrong account.

`git bundle create pybnf.bundle feature/particle-filter` turns the private
repository into an ordinary 140 MB file, and

    git clone -b feature/particle-filter pybnf.bundle <destination>

produces a normal checkout from it with no network and no account at all.
So the fix for the whole authentication story is to hand a student one file
and have setup FIND it. These tests run the real setup_engine.sh against a
real (tiny) bundle and check that it does.

FLUBNF_ENGINE_CHECKOUT_ONLY=1 stops the script once the checkout exists,
which is the part under test; the venv build after it costs minutes and a
network this suite does not have.

setup_engine.sh is POSIX-only, so the executing tests skip on Windows, where
FluBNF.bat carries the twin of this search. The text checks run everywhere.
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

# A remote that cannot exist, so a run that reaches the network path fails
# instead of quietly succeeding: every executing test below asserts that the
# BUNDLE did the work, and a real clone of the real fork would hide that.
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
        # A double-clicked launcher gives git a real terminal, so a run that
        # reached the network path could stop at a password prompt and hang
        # this suite. It cannot get that far with NOWHERE as the remote, but
        # the belt goes with the braces.
        "GIT_TERMINAL_PROMPT": "0",
        "FLUBNF_PYBNF_REMOTE": NOWHERE,
        "FLUBNF_ENGINE_CHECKOUT_ONLY": "1",
        # The fallback path probes github.com for a PUBLIC repo, to tell "no
        # access" apart from "no network". That is one real network call
        # inside a unit suite, so bound it: on a machine with no route out,
        # git's own default would leave this test sitting for minutes.
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
    # and the remote it recorded is the fork, not the bundle file, which is
    # often on a stick that is about to be unplugged
    url = subprocess.run(["git", "-C", str(dest), "remote", "get-url", "origin"],
                         capture_output=True, text=True, check=True)
    assert url.stdout.strip() == NOWHERE


@posix_only
@pytest.mark.parametrize("where", ["repo", "beside", "Downloads", "Desktop",
                                   "Documents"])
def test_the_search_covers_the_places_a_student_puts_a_download(tmp_path, where):
    """Five folders, because a student saves a file where they save files.

    The script is copied into a temp tree so the "beside the FluBNF folder"
    and "in the FluBNF folder" cases can be exercised without dropping a
    140 MB file into the developer's own checkout.
    """
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
def test_no_bundle_prints_nothing_rather_than_a_guess(tmp_path):
    out = _run(SCRIPT, _home(tmp_path), args=("--print-bundle",))
    assert out.returncode == 0
    assert out.stdout.strip() == ""


@posix_only
def test_a_named_bundle_wins_and_a_missing_named_one_is_not_silent(tmp_path):
    """FLUBNF_PYBNF_BUNDLE is the escape hatch for a file kept somewhere
    else. Pointing it at a path that is not there is a typo, and a typo that
    silently falls back to the automatic search would leave the reader
    certain their file was used when it was not."""
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
    """On macOS ".bundle" is also a directory type -- plug-ins and
    frameworks ship that way -- and ~/Downloads is exactly where one turns
    up. The search must not offer a folder to `git clone`."""
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf-something.bundle").mkdir()

    out = _run(SCRIPT, home, args=("--print-bundle",))

    assert out.stdout.strip() == "", (
        "a DIRECTORY named *.bundle was offered as a git bundle")


@posix_only
def test_a_truncated_bundle_blames_the_file_and_falls_back(tmp_path):
    """The way this breaks in the field is a copy from a shared drive that
    did not finish, and git's words for it ("early EOF", "index-pack died")
    read as a broken installation rather than a broken file.

    MEASURED here on git 2.39.5, and the reason the message lives on the
    CLONE and not on the verify: `git bundle verify` ACCEPTS this file. It
    checks the header and the prerequisites, not the pack. A guard that
    trusted verify would hand a truncated bundle to clone and then report
    git's own low-level error.
    """
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
    # and it did not stop there: the GitHub route is still offered, which is
    # the whole reason the bundle is a shortcut rather than a requirement
    assert "fork access (needed to clone)" in out.stdout
    assert out.returncode == 1


@posix_only
def test_a_file_that_is_not_a_bundle_at_all_says_so(tmp_path):
    """A browser that saved an error page under the name pybnf.bundle. The
    remedy differs from the truncated case (a different file, not the same
    file again), so the two must not share a message."""
    home = _home(tmp_path)
    (home / "Downloads" / "pybnf.bundle").write_text(
        "<html><body>404 Not Found</body></html>\n")
    dest = tmp_path / "PyBNF-pf"

    out = _run(SCRIPT, home, dest=dest)

    assert "not a git bundle at all" in out.stdout, out.stdout
    assert not (dest / ".git").exists()
    assert "fork access (needed to clone)" in out.stdout


def test_the_bundle_is_tried_before_anything_that_needs_an_account():
    """Ordering is the feature. A file sitting beside you beats a network
    round trip that can end at a password prompt nobody can answer."""
    bundle_at = SRC.index('say "offline engine bundle"')
    access_at = SRC.index('say "fork access (needed to clone)"')
    assert bundle_at < access_at, (
        "setup_engine.sh probes GitHub before it looks for a local bundle")
    assert SRC.index("git bundle verify") < SRC.index("git ls-remote")


def test_the_no_bundle_path_says_where_it_looked():
    """A search that finds nothing and does not say where it searched is
    indistinguishable from a search that never ran."""
    # the message must name BOTH artifact shapes, because the tar.gz is the
    # one students are actually sent and an earlier wording named only the
    # bundle, telling a student with a slightly misnamed archive that only
    # bundles count
    assert "no engine file found. Looked for pybnf*.tar.gz and pybnf*.bundle in:" in SRC
    assert "engine_bundle_dirs | sed" in SRC, (
        "the folders searched are no longer printed, so a student cannot "
        "tell where to put the file")


def test_the_launchers_ask_the_script_rather_than_repeating_the_search():
    """One search, in one file. A second copy in a launcher is a second
    thing to keep in step, and the one that drifts is always the copy."""
    for name in ("FluBNF.command", "SetupEngine.command"):
        src = (REPO / name).read_text(encoding="utf-8")
        assert "--print-bundle" in src, (
            f"{name} does not ask setup_engine.sh where the bundle is")
        assert "*.bundle" not in src, (
            f"{name} has grown its own copy of the bundle search")


# ---------------------------------------------------------------------------
# The Windows twin. FluBNF.bat is never executed anywhere in this project's
# CI (the workflow says so in as many words), and the lab develops on macOS,
# so these are text checks -- but a mistyped label in a .bat is a silent jump
# to nowhere, and that much a text check CAN catch.
# ---------------------------------------------------------------------------

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
    """A `goto` to a label that does not exist ends the script silently, and
    on this path that means a console that never opens. Nothing in CI runs
    this file, so the typo would reach a student first."""
    labels, targets = _bat_labels_and_targets()
    missing = sorted({t for t in targets if t not in labels and t != "eof"})
    assert not missing, f"FluBNF.bat jumps to labels that do not exist: {missing}"


def _engine_section() -> str:
    """The text between the :launch LABEL and the :startconsole LABEL.

    Matched at the start of a line: `goto :launch` appears earlier in the
    file than the label it jumps to, and slicing from the jump would drag in
    the data section, which is entitled to ask its own bounded question.
    """
    import re
    start = re.search(r"^:launch\b", BAT, re.M)
    end = re.search(r"^:startconsole\b", BAT, re.M)
    assert start and end and start.start() < end.start(), (
        "FluBNF.bat no longer has the :launch ... :startconsole section the "
        "engine install lives in")
    return BAT[start.start():end.start()]


def test_every_windows_engine_path_ends_at_the_console():
    """The engine is optional by design: no branch of it may leave the user
    without a console, and none may stop UNATTENDED at a question. A
    double-clicked launcher has nobody watching it.

    The property is "cannot park", not "cannot ask": the data section's
    bounded question (20 s, a default, N one keystroke away) set the
    precedent, and the Perl offer (2026-09-01) extends it into the engine
    section. So a `choice` here is legal ONLY in the bounded form, carrying
    both a timeout (/t) and a default (/d); a bare `choice`, a `pause`, or
    an exit that skips the console remain forbidden."""
    engine = _engine_section()
    assert "pause" not in engine, "the engine section can stop at a prompt"
    for ln in engine.splitlines():
        # an INVOCATION starts the line with `choice`; `where choice` (the
        # availability probe) and comments mentioning it are not questions
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
    """Same folders as setup_engine.sh, so the instruction "put it in
    Downloads" is true on both platforms."""
    for needle in (r'"%~dp0pybnf*.bundle"',
                   r'"%~dp0..\pybnf*.bundle"',
                   r'"%USERPROFILE%\Downloads\pybnf*.bundle"',
                   r'"%USERPROFILE%\Desktop\pybnf*.bundle"',
                   r'"%USERPROFILE%\Documents\pybnf*.bundle"'):
        assert needle in BAT, f"FluBNF.bat no longer searches {needle}"
    assert 'git clone -b feature/particle-filter "%BUNDLE%" "%PYBNFDIR%"' in BAT
    assert 'git bundle verify "%BUNDLE%"' in BAT


def test_the_windows_launcher_never_calls_the_network_on_the_engine_path():
    """A probe of github.com here would cost a round trip on every launch of
    every machine that never gets the engine. setup.ps1 does that once, with
    a timeout and a diagnosis; the launcher does the credential-free half."""
    engine = _engine_section()
    assert "ls-remote" not in engine
    assert "git clone -b feature/particle-filter https" not in engine
    # the one github.com URL allowed here never opens a connection: it is
    # written into the new checkout's origin so a later pull says something
    # useful when the bundle file is gone
    for line in engine.splitlines():
        if "github.com" in line and not line.strip().startswith("rem"):
            assert line.strip().startswith("git -C"), line


def test_the_windows_launcher_resolves_the_fork_the_way_setup_does():
    """Three files decide where the checkout is: setup.ps1, this launcher,
    and flubnf/settings.py. If they disagree, one of them installs an engine
    the others cannot find."""
    order = [BAT.index(p) for p in (
        r"%USERPROFILE%\Documents\GitHub\PyBNF-pf",
        r"%LOCALAPPDATA%\FluBNF\PyBNF-pf",
        r"%USERPROFILE%\Documents\GitHub\PyBNF-Private",
        r"%LOCALAPPDATA%\FluBNF\PyBNF-Private")]
    assert order == sorted(order), (
        "FluBNF.bat no longer probes the four checkout locations in "
        "setup.ps1's order (PyBNF-pf before PyBNF-Private, and the old "
        "Documents default before the new one within each name)")
    # and setup.ps1 really does resolve PyBNF-pf before PyBNF-Private. Read
    # rather than asserted into existence: setup.ps1 belongs to the Windows
    # strand, and a test here that pins its exact wording would fail on a
    # refactor that changed nothing about the ORDER, which is the only thing
    # this file cares about.
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
    """The list is duplicated in three files, which is three chances to
    drift. Every published FluBNF number came from these pins; an engine
    built from a different set is not the engine that was validated."""
    assert pin in BAT, f"FluBNF.bat no longer installs {pin}"
    assert pin in SRC or pin.replace('"', "") in SRC, (
        f"setup_engine.sh no longer installs {pin}")


def test_the_retry_stamp_moves_when_a_bundle_appears():
    """FluBNF.command deliberately does not retry a failed engine setup on
    every open. The stamp must therefore include the bundle: a student whose
    first run failed for want of credentials is handed a file, drops it in
    Downloads, opens the app -- and the run that would now succeed must not
    be the one the stamp suppresses."""
    src = (REPO / "FluBNF.command").read_text(encoding="utf-8")
    fp = [l for l in src.splitlines() if l.strip().startswith("FP=")]
    assert len(fp) == 1, fp
    assert "BUNDLE" in fp[0], (
        "the attempt fingerprint ignores the bundle, so dropping one in "
        "Downloads does not earn a retry")


def test_the_retry_stamp_moves_when_a_BROKEN_bundle_is_replaced():
    """The stamp has to key on the bundle's CONTENT, not only its path.

    Review finding, 2026-08-31, reproduced before it was fixed. The failure
    setup_engine.sh names as the realistic one is a copy from a shared drive
    that did not finish, and the remedy it prints is "compare its size with
    the copy you were given and fetch it again". Fetching it again writes a
    good file over the bad one, under the same name, in the same folder, so a
    fingerprint made of the PATH alone does not move: the stamp suppressed
    exactly the retry the message had just asked for, and told the student to
    fix a failure they had already fixed. The size is enough to tell the two
    files apart and costs one `wc -c`.
    """
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
    """Four ways the engine arrives, none of which may reach the GitHub wall.

    Review finding, 2026-08-31, reproduced before it was fixed, in two
    halves that met in the middle:

    * `PYBNF` defaulted to `~/Documents/GitHub/PyBNF-pf` and nothing else.
      PyBNF-pf is the DEVELOPMENT HOST's name; every other machine gets
      PyBNF-Private, which is the repository's real name, what GitHub
      Desktop clones as, and the prefix scripts/cut_engine_archive.sh
      unpacks under. flubnf/settings.py and setup.ps1 both already knew
      that; this script did not, so a real checkout at PyBNF-Private was
      walked past and the run ended at the credentials advice.
    * the plain-copy branch accepts an unpacked archive with no .git, which
      is how docs/INSTALL-STUDENTS.md tells a student to install the
      engine -- but it was only reachable when FLUBNF_PYBNF pointed at the
      folder by hand, and nothing on the automatic path ever did.

    The engine needs an importable package, never git and never a
    particular folder name, so all four of these are installed engines.
    """
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
    """The launchers pick the checkout and hand it to setup_engine.sh, so a
    `.git` test there undoes the plain-copy support just as completely. Both
    files are shell, and the loop is small enough to check by running the
    real predicate against a real unpacked folder."""
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
