"""reinstall.sh: the one-line clean reinstall for a stale lab machine.

It quits the console, sets aside the FluBNF folder, engine venv and unpacked
engine, sweeps other engine archives out of setup's search folders (newest-
by-mtime would pick a PR review package), installs fresh and opens the app.
The real script runs against a fake HOME and stops before the clone
(FLUBNF_REINSTALL_NO_INSTALL=1; the install is setup.sh's).

Pinned: checks run BEFORE anything changes; the right archive is kept and
everything else moved, not deleted; the old launcher is disabled; a current
machine is left alone, a stale one is not; a failed clone restores the old
install. On macOS the tests use /bin/bash 3.2, as lab Macs do.
"""
from __future__ import annotations

import io
import os
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "reinstall.sh"
SRC = SCRIPT.read_text(encoding="utf-8")
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
LINE = "curl -sL https://raw.githubusercontent.com/elyfmiller/flubnf/main/reinstall.sh | bash"

posix_only = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="reinstall.sh is the macOS and Linux route; Windows has its own steps")

# reinstall.sh refuses to run as root (it stops before any check under test)
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="reinstall.sh refuses to run as root")

GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _bare_origin(tmp_path: Path) -> tuple[Path, Path]:
    """A local stand-in for GitHub (a bare repo) and the working clone it was
    made from, so the reachability check and the already-current comparison
    work with no network, and the origin can be moved ahead."""
    src = tmp_path / "src"
    src.mkdir()
    env = {**os.environ, **GIT_ENV}
    run = lambda *a, cwd=src: subprocess.run(  # noqa: E731
        ["git", *a], cwd=cwd, env=env, check=True, capture_output=True)
    run("init", "-q", "-b", "main", ".")
    (src / "README").write_text("stand-in\n")
    run("add", "README")
    run("commit", "-qm", "init")
    origin = tmp_path / "origin.git"
    run("clone", "-q", "--bare", str(src), str(origin), cwd=tmp_path)
    return origin, src


def _tar(path: Path, members: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tar:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _engine_archive(path: Path, stamp: str = "feature/particle-filter 2fdadee0",
                    cut: str = "2026-09-23") -> Path:
    """The shape scripts/cut_engine_archive.sh writes: one top folder with
    pybnf/pf.py, setup.py and a VERSION whose second line dates the cut."""
    return _tar(path, {"PyBNF-Private/pybnf/pf.py": "x\n",
                       "PyBNF-Private/setup.py": "x\n",
                       "PyBNF-Private/VERSION": f"{stamp}\ncut {cut} from origin\n"})


def _review_package(path: Path) -> Path:
    """The PR agent's review package: same name pattern, pybnf/pf.py one
    level too deep, no setup.py beside it. Not installable."""
    return _tar(path, {"pybnf-pf-2171c226/tree/pybnf/pf.py": "x\n",
                       "pybnf-pf-2171c226/tree/setup.py": "x\n",
                       "pybnf-pf-2171c226/README.txt": "x\n"})


def _home_with_old_install(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    for d in ("Downloads", "Desktop", "Documents/GitHub/flubnf/app/state",
              ".venvs/flubnf-engine", "Documents/GitHub/PyBNF-Private"):
        (home / d).mkdir(parents=True)
    for name in ("FluBNF.command", "SetupEngine.command"):
        launcher = home / "Documents/GitHub/flubnf" / name
        launcher.write_text("#!/bin/bash\n")
        launcher.chmod(0o755)
    (home / "Documents/GitHub/flubnf/app/state/ledger.txt").write_text("runs\n")
    return home


def _run(home: Path, origin: Path, *, no_install: bool = True,
         **env_extra) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLUBNF_")}
    env.update({
        "HOME": str(home),
        "FLUBNF_REPO": str(origin),
        "FLUBNF_REINSTALL_YES": "1",
        "FLUBNF_REINSTALL_NO_OPEN": "1",
        # a developer's own console may be running; that check is about lab
        # machines
        "FLUBNF_REINSTALL_IGNORE_RUNNING": "1",
        "GIT_TERMINAL_PROMPT": "0",
        **GIT_ENV,
    })
    if no_install:
        env["FLUBNF_REINSTALL_NO_INSTALL"] = "1"
    env.update({k: str(v) for k, v in env_extra.items()})
    return subprocess.run([BASH, str(SCRIPT)], env=env, text=True,
                          capture_output=True, timeout=180)


def test_the_documented_line_is_the_same_everywhere():
    """README, the student guide and the script header show one line,
    spelled like install.sh's."""
    assert LINE in SRC
    assert LINE in (REPO / "README.md").read_text(encoding="utf-8")
    assert LINE in (REPO / "docs" / "INSTALL-STUDENTS.md").read_text(encoding="utf-8")
    assert LINE.replace("reinstall.sh", "install.sh") in (REPO / "install.sh").read_text(encoding="utf-8")
    assert "FLUBNF_REINSTALL_FORCE" in SRC and "FLUBNF_REINSTALL_NO_INSTALL" in SRC


def test_the_whole_file_is_parsed_before_any_of_it_runs():
    """curl | bash runs the file as it arrives, so the body is a function
    called on the last line: a truncated download is a syntax error, never
    half a reinstall."""
    body = SRC.rstrip().splitlines()
    assert body[-1] == 'main "$@"'
    assert "\nmain() {\n" in SRC
    cut = SRC[: SRC.index('say "installing FluBNF')]
    check = subprocess.run([BASH, "-n"], input=cut, text=True, capture_output=True)
    assert check.returncode != 0, "a truncated download parsed cleanly"


@posix_only
@not_root
def test_no_engine_file_means_nothing_is_touched(tmp_path):
    """The archive is checked before anything is renamed."""
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    out = _run(home, origin)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "no engine file found" in out.stdout
    assert "Nothing on this machine was changed" in out.stdout
    assert (home / "Documents/GitHub/flubnf").is_dir()
    assert (home / ".venvs/flubnf-engine").is_dir()


@posix_only
@not_root
def test_sets_the_old_install_aside_and_keeps_only_the_real_archive(tmp_path):
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    good = _engine_archive(home / "Downloads/pybnf-pf-2fdadee0.tar.gz")
    dup = _engine_archive(home / "Downloads/pybnf-pf-2fdadee0 (1).tar.gz")
    older = _engine_archive(home / "Desktop/pybnf-pf-3320d1f0.tar.gz",
                            "feature/particle-filter 3320d1f0", "2026-08-27")
    review = _review_package(home / "Downloads/pybnf-pf-2171c226.tar.gz")
    junk = home / "Documents/pybnfpf8b28edf4.tar.gz"
    junk.write_bytes(b"not even a tarball")
    bundle = home / "Downloads/pybnf.bundle"
    bundle.write_bytes(b"a git bundle, once")
    notes = home / "Documents/pybnf-notes.txt"           # the reader's own file
    notes.write_text("mine\n")
    # the review package is the NEWEST file (the trap); the duplicate is an
    # older save of the same archive
    now = time.time()
    os.utime(good, (now - 300, now - 300))
    os.utime(dup, (now - 400, now - 400))
    os.utime(older, (now - 900, now - 900))
    os.utime(review, (now, now))

    out = _run(home, origin)

    assert out.returncode == 0, out.stdout + out.stderr
    assert "engine file: " + str(good) in out.stdout
    assert "its version stamp: feature/particle-filter 2fdadee0" in out.stdout
    # the old install is renamed with a stamp, never deleted, runs included
    olds = sorted(p.name for p in (home / "Documents/GitHub").iterdir())
    assert not (home / "Documents/GitHub/flubnf").exists()
    assert any(n.startswith("flubnf-old-") for n in olds), olds
    assert any(n.startswith("PyBNF-Private-old-") for n in olds), olds
    assert not (home / ".venvs/flubnf-engine").exists()
    assert any(p.name.startswith("flubnf-engine-old-") for p in (home / ".venvs").iterdir())
    old_clone = next((home / "Documents/GitHub").glob("flubnf-old-*"))
    assert (old_clone / "app/state/ledger.txt").read_text() == "runs\n"
    assert "set aside: " + str(home / "Documents/GitHub/flubnf") in out.stdout
    assert str(old_clone) in out.stdout, "the reader is not told the new name"
    # the renamed launchers cannot be double-clicked into taking over
    for name in ("FluBNF.command", "SetupEngine.command"):
        assert not (old_clone / name).stat().st_mode & stat.S_IXUSR
    # the archive that matters stays; every other ENGINE file is moved, and
    # the reader's own file is not touched
    assert good.exists()
    keep = home / "Downloads/old-engine-files"
    moved = sorted(p.name for p in keep.iterdir())
    assert moved == sorted([dup.name, older.name, review.name, junk.name, bundle.name]), moved
    assert notes.exists()
    assert "delete " + str(keep) in out.stdout


@posix_only
@not_root
def test_a_name_already_swept_is_kept_under_a_distinct_name(tmp_path):
    """macOS mv -n exits 0 when it skips, so a repeat download must be kept
    under a distinct name, or it stays and wins setup's search."""
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    _engine_archive(home / "Downloads/pybnf-pf-2fdadee0.tar.gz")
    keep = home / "Downloads/old-engine-files"
    keep.mkdir()
    (keep / "pybnf-pf-2171c226.tar.gz").write_bytes(b"swept last time")
    review = _review_package(home / "Downloads/pybnf-pf-2171c226.tar.gz")
    out = _run(home, origin)
    assert out.returncode == 0, out.stdout + out.stderr
    assert not review.exists(), "the newer review package was left where setup looks"
    assert len(list(keep.glob("*pybnf-pf-2171c226.tar.gz"))) == 2


@posix_only
@not_root
def test_the_newest_valid_archive_wins_not_the_newest_file(tmp_path):
    """Two real archives: the newer one is installed even when a review
    package is newer still."""
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    old = _engine_archive(home / "Downloads/pybnf-pf-3320d1f0.tar.gz", "x 3320d1f0", "2026-08-27")
    new = _engine_archive(home / "Desktop/pybnf-pf-2fdadee0.tar.gz", "x 2fdadee0")
    review = _review_package(home / "Downloads/pybnf-pf-2171c226.tar.gz")
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now - 50, now - 50))
    os.utime(review, (now, now))
    out = _run(home, origin)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "engine file: " + str(new) in out.stdout
    assert new.exists() and not old.exists() and not review.exists()


@posix_only
@not_root
def test_an_archive_under_the_flubnf_parent_is_not_its_own_competitor(tmp_path):
    """FLUBNF_DIR under ~/Documents lists that folder twice in the search;
    the chosen archive must not be swept aside on the second pass."""
    origin, _ = _bare_origin(tmp_path)
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Documents/flubnf").mkdir(parents=True)
    good = _engine_archive(home / "Documents/pybnf-pf-2fdadee0.tar.gz")
    out = _run(home, origin, FLUBNF_DIR=str(home / "Documents/flubnf") + "/")
    assert out.returncode == 0, out.stdout + out.stderr
    assert good.exists()
    assert list((home / "Documents").glob("flubnf-old-*")), "a trailing slash broke the rename"


def _current_install(tmp_path: Path, origin: Path, stamp: str = "feature/particle-filter 2fdadee0") -> Path:
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    dest = home / "Documents/GitHub/flubnf"
    subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True,
                   capture_output=True)
    for stub in (dest / ".venv/bin/flubnf", dest / ".venv/bin/python",
                 home / ".venvs/flubnf-engine/bin/python"):
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("#!/bin/sh\n")       # runs, and answers every -c with success
        stub.chmod(0o755)
    pybnf = home / "Documents/GitHub/PyBNF-Private"
    pybnf.mkdir()
    (pybnf / "VERSION").write_text(f"{stamp}\ncut 2026-09-23 from origin\n")
    (dest / ".flubnf.env").write_text(
        f'export FLUBNF_PY_ENGINE="{home}/.venvs/flubnf-engine/bin/python"\n'
        f'export FLUBNF_PYBNF="{pybnf}"\n')
    _engine_archive(home / "Downloads/pybnf-pf-2fdadee0.tar.gz")
    return home


@posix_only
@not_root
def test_a_machine_that_is_already_current_is_left_alone(tmp_path):
    """Pasting the line twice must not set a good install aside."""
    origin, _ = _bare_origin(tmp_path)
    home = _current_install(tmp_path, origin)
    dest = home / "Documents/GitHub/flubnf"

    out = _run(home, origin)

    assert out.returncode == 0, out.stdout + out.stderr
    assert "already current" in out.stdout
    assert "FLUBNF_REINSTALL_FORCE=1 bash" in out.stdout, "no line to paste when it is broken anyway"
    assert dest.is_dir() and (dest / ".git").is_dir()
    assert not list((home / "Documents/GitHub").glob("flubnf-old-*"))

    forced = _run(home, origin, FLUBNF_REINSTALL_FORCE="1")
    assert forced.returncode == 0, forced.stdout + forced.stderr
    assert "already current" not in forced.stdout
    assert list((home / "Documents/GitHub").glob("flubnf-old-*"))


@posix_only
@not_root
def test_a_current_console_with_a_stale_engine_is_reinstalled(tmp_path):
    """A fast-forwarded console whose engine venv already existed (so the new
    archive was never installed) is reinstalled."""
    origin, _ = _bare_origin(tmp_path)
    home = _current_install(tmp_path, origin, stamp="pf/pre-pr 8b28edf4")
    (home / "Documents/GitHub/PyBNF-Private/VERSION").write_text(
        "pf/pre-pr 8b28edf4\ncut 2026-09-08 from origin\n")
    out = _run(home, origin)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "already current" not in out.stdout
    assert list((home / "Documents/GitHub").glob("flubnf-old-*"))


@posix_only
@not_root
def test_a_console_behind_origin_is_reinstalled(tmp_path):
    origin, src = _bare_origin(tmp_path)
    home = _current_install(tmp_path, origin)
    env = {**os.environ, **GIT_ENV}
    (src / "README").write_text("v2\n")
    subprocess.run(["git", "commit", "-qam", "v2"], cwd=src, env=env, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", str(origin), "main"], cwd=src, env=env, check=True, capture_output=True)
    out = _run(home, origin)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "already current" not in out.stdout
    assert list((home / "Documents/GitHub").glob("flubnf-old-*"))


@posix_only
@not_root
def test_an_older_archive_does_not_silently_downgrade(tmp_path):
    origin, _ = _bare_origin(tmp_path)
    home = _current_install(tmp_path, origin)
    (home / "Downloads/pybnf-pf-2fdadee0.tar.gz").unlink()
    _engine_archive(home / "Downloads/pybnf-pf-3320d1f0.tar.gz",
                    "feature/particle-filter 3320d1f0", "2026-08-27")
    out = _run(home, origin)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "OLDER than the engine already installed" in out.stdout
    assert "Nothing on this machine was changed" in out.stdout
    assert (home / "Documents/GitHub/flubnf").is_dir()


@posix_only
@not_root
def test_a_developer_shell_or_checkout_is_refused(tmp_path):
    """Exported FLUBNF_* settings or an engine checkout with uncommitted work
    are refused."""
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    _engine_archive(home / "Downloads/pybnf-pf-2fdadee0.tar.gz")

    out = _run(home, origin, FLUBNF_PYBNF="/somewhere/else")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "FLUBNF_PYBNF=/somewhere/else" in out.stdout
    assert "Nothing on this machine was changed" in out.stdout

    fork = home / "Documents/GitHub/PyBNF-Private"
    env = {**os.environ, **GIT_ENV}
    git = lambda *a: subprocess.run(["git", *a], cwd=fork, env=env, check=True,  # noqa: E731
                                    capture_output=True)
    git("init", "-q", "-b", "main", ".")
    (fork / "pf.py").write_text("committed\n")
    git("add", "pf.py")
    git("commit", "-qm", "pf")
    (fork / "pf.py").write_text("edited and not committed\n")   # tracked, modified
    out = _run(home, origin)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "uncommitted or unpushed work" in out.stdout
    assert fork.is_dir()


@posix_only
@not_root
def test_a_failed_clone_puts_the_old_install_back(tmp_path):
    """A failed clone after the rename: the exit trap moves the old copies
    back and re-enables their launcher."""
    origin, _ = _bare_origin(tmp_path)
    home = _home_with_old_install(tmp_path)
    _engine_archive(home / "Downloads/pybnf-pf-2fdadee0.tar.gz")
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the parent folder should be\n")
    dest = blocker / "flubnf"                  # mkdir -p and git clone must fail here

    out = _run(home, origin, no_install=False, FLUBNF_DIR=str(dest))

    assert out.returncode == 1, out.stdout + out.stderr
    assert "put back: " + str(home / ".venvs/flubnf-engine") in out.stdout
    assert (home / ".venvs/flubnf-engine").is_dir()
    assert not list((home / ".venvs").glob("flubnf-engine-old-*"))
    assert "Your previous FluBNF is as it was" in out.stdout
