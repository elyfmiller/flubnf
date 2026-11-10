"""doctor and setup.sh take a hub folder for a clone when git does: when
`git -C <hub> rev-parse --show-toplevel` is the hub itself (the re-check
of #93 at 099907c, finding 5).

  * A hub whose .git is a file (a worktree or a submodule) is a clone:
    setup.sh widens it as it widens any clone. It used to fall to `git
    clone`, which fails on a folder that is there, and say "data fetch
    failed (offline?)".
  * A hub with an empty or broken .git folder is no clone: git -C there
    answers for any repository around the folder. doctor gives no git
    step for it and setup.sh says it is not a clone, as for any other
    folder that is there. Both used to take it for a clone, and setup.sh
    ran `git sparse-checkout add` in it.
  * With no git to ask, doctor counts a .git there, as before.

Every git command runs in repositories the test made in tmp_path, with
GIT_CEILING_DIRECTORIES there. setup.sh runs as a copy with stand-ins
first on PATH (a python3.12, the venv's tools, and a git that logs each
call and refuses `clone`): nothing is installed or fetched.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from flubnf import doctor, settings

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
POSIX = pytest.mark.skipif(sys.platform.startswith("win"),
                           reason="setup.sh is the POSIX route")
GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="no git")
NOT_A_CLONE = "is there but is not a git clone"


def _env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CEILING_DIRECTORIES": str(tmp_path),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0"})
    return env


def _git(tmp_path: Path, *args, cwd=None) -> str:
    out = subprocess.run(
        [GIT, "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null",
         "-c", "protocol.file.allow=always", *args],
        cwd=cwd, env=_env(tmp_path), capture_output=True, text=True,
        timeout=60)
    assert out.returncode == 0, (args, out.stdout, out.stderr)
    return out.stdout


def _repo(tmp_path: Path, name: str, files=("README.md",)) -> Path:
    r = tmp_path / name
    for rel in files:
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text("x\n")
    _git(tmp_path, "init", "-q", str(r))
    _git(tmp_path, "add", "-A", cwd=r)
    _git(tmp_path, "commit", "-q", "-m", "first", cwd=r)
    return r


def _worktree(tmp_path: Path) -> Path:
    """A hub that is a worktree of another clone: its .git is a file."""
    main = _repo(tmp_path, "main", ("README.md", "model-output/a/x.csv"))
    hub = tmp_path / "hub"
    _git(tmp_path, "worktree", "add", "-q", str(hub), cwd=main)
    assert (hub / ".git").is_file()
    return hub


def _submodule(tmp_path: Path) -> Path:
    """A hub that is a submodule of an outer clone: its .git is a file."""
    sub = _repo(tmp_path, "sub", ("README.md",))
    outer = _repo(tmp_path, "outer")
    _git(tmp_path, "submodule", "add", "-q", str(sub), "hub", cwd=outer)
    hub = outer / "hub"
    assert (hub / ".git").is_file()
    return hub


def _empty_git(tmp_path: Path) -> Path:
    """A folder with an empty .git folder, inside another clone."""
    outer = _repo(tmp_path, "outer")
    hub = outer / "hub"
    (hub / ".git").mkdir(parents=True)
    (hub / "notes.txt").write_text("left here\n")
    return hub


def _broken_git(tmp_path: Path) -> Path:
    """A folder whose .git folder is no repository, inside another clone."""
    outer = _repo(tmp_path, "outer")
    hub = outer / "hub"
    (hub / ".git").mkdir(parents=True)
    (hub / ".git" / "HEAD").write_text("not a ref\n")
    (hub / "notes.txt").write_text("left here\n")
    return hub


def _dangling_git_file(tmp_path: Path) -> Path:
    """A worktree whose main clone is gone: its .git file points nowhere."""
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / ".git").write_text(f"gitdir: {tmp_path / 'gone' / '.git'}\n")
    (hub / "notes.txt").write_text("left here\n")
    return hub


CLONES = {"worktree": _worktree, "submodule": _submodule}
NOT_CLONES = {"empty .git folder": _empty_git,
              "broken .git folder": _broken_git,
              "dangling .git file": _dangling_git_file}


# --- doctor -----------------------------------------------------------------
@pytest.fixture
def ceiling(tmp_path, monkeypatch):
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


@needs_git
@pytest.mark.parametrize("kind", list(CLONES))
def test_doctor_gives_a_worktree_or_submodule_hub_the_git_step(
        tmp_path, monkeypatch, ceiling, kind):
    hub = CLONES[kind](tmp_path)
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub("darwin")
    assert res.status is doctor.Status.FAIL
    assert res.hint.splitlines()[-1].strip() == (
        f'git -C "{hub}" sparse-checkout add auxiliary-data target-data')
    assert NOT_A_CLONE not in res.hint


@needs_git
@pytest.mark.parametrize("kind", list(NOT_CLONES))
@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_doctor_says_a_hub_with_no_working_git_is_not_a_clone(
        tmp_path, monkeypatch, ceiling, kind, platform):
    hub = NOT_CLONES[kind](tmp_path)
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub(platform)
    assert res.status is doctor.Status.FAIL
    assert "git -C" not in res.hint and "sparse-checkout" not in res.hint
    assert res.hint.startswith(f"The folder {NOT_A_CLONE}, so setup cannot "
                               "fetch the data into it. Move or rename it "
                               "first."), res.hint


@needs_git
def test_doctor_asks_git_about_the_hub_itself(tmp_path, monkeypatch, ceiling):
    """git's answer for a folder inside a clone is that clone's top level,
    never the folder's own: no git step for it."""
    hub = _empty_git(tmp_path)
    top = subprocess.run([GIT, "-C", str(hub), "rev-parse",
                          "--show-toplevel"], capture_output=True, text=True,
                         timeout=60)
    assert top.returncode == 0                     # git walks up to outer
    assert Path(top.stdout.strip()).samefile(hub.parent)
    assert doctor._is_clone(hub) is False
    assert doctor._is_clone(_worktree(tmp_path)) is True


def test_with_no_git_to_ask_a_dot_git_counts(tmp_path, monkeypatch):
    hub = tmp_path / "hub"
    (hub / ".git").mkdir(parents=True)

    def no_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(doctor.subprocess, "run", no_git)
    assert doctor._is_clone(hub) is True
    assert doctor._is_clone(tmp_path) is False     # no .git: never asked


# --- setup.sh ---------------------------------------------------------------
def _exe(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + text)
    path.chmod(0o755)
    return path


def _setup(tmp_path: Path, hub: Path) -> tuple:
    """setup.sh alone in a folder of its own, a venv already there, and
    stand-ins first on PATH: python3.12, and a git that logs each call
    and runs it with the real git, except `clone`, which fails."""
    repo = tmp_path / "flubnf"
    repo.mkdir()
    shutil.copy(REPO / "setup.sh", repo / "setup.sh")
    ctl, bin_, home = tmp_path / "ctl", tmp_path / "bin", tmp_path / "home"
    ctl.mkdir()
    home.mkdir()
    _exe(bin_ / "python3.12",
         'case "$1" in -V) echo "Python 3.12.3" ;; esac\nexit 0\n')
    _exe(bin_ / "git",
         f'echo "$*" >> "{ctl}/git.log"\n'
         'case "$1" in clone) exit 1 ;; esac\n'
         f'exec "{GIT}" "$@"\n')
    vb = repo / ".venv" / "bin"
    for tool in ("python", "pip", "flubnf"):
        _exe(vb / tool, "exit 0\n")
    env = {k: v for k, v in _env(tmp_path).items()
           if not k.startswith(("FLUBNF_", "PIP_", "PYTHON"))}
    env.update({"HOME": str(home), "FLUBNF_HUB": str(hub),
                "FLUBNF_NO_DATA": "0",
                "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}"})
    out = subprocess.run([BASH, str(repo / "setup.sh")], env=env,
                         cwd=tmp_path, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=180)
    log = ctl / "git.log"
    calls = log.read_text().splitlines() if log.exists() else []
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)
    return out, calls, plain


@POSIX
@needs_git
@pytest.mark.parametrize("kind", list(CLONES))
def test_setup_widens_a_worktree_or_submodule_hub(tmp_path, kind):
    hub = CLONES[kind](tmp_path)
    out, calls, said = _setup(tmp_path, hub)
    assert out.returncode == 0, out.stdout + out.stderr
    assert f"hub present: {hub}" in said, said
    assert [c for c in calls if c.startswith("sparse-checkout add ")], calls
    assert not [c for c in calls if c.startswith("clone")], calls
    assert "data fetch failed" not in said and NOT_A_CLONE not in said


@POSIX
@needs_git
@pytest.mark.parametrize("kind", list(NOT_CLONES))
def test_setup_says_a_hub_with_no_working_git_is_not_a_clone(tmp_path, kind):
    hub = NOT_CLONES[kind](tmp_path)
    before = sorted(p.name for p in hub.iterdir())
    out, calls, said = _setup(tmp_path, hub)
    assert out.returncode == 0, out.stdout + out.stderr
    flat = " ".join(ln.strip().lstrip("!").strip() for ln in said.splitlines())
    assert f'"{hub}" {NOT_A_CLONE}, so no data was fetched into it.' in flat, \
        said
    assert "hub present" not in said and "data fetch failed" not in said
    # nothing run in the clone around it, nothing cloned
    assert not [c for c in calls if "sparse-checkout" in c], calls
    assert not [c for c in calls if c.startswith("clone")], calls
    assert sorted(p.name for p in hub.iterdir()) == before


@POSIX
@needs_git
def test_setup_still_takes_an_ordinary_clone_for_one(tmp_path):
    up = _repo(tmp_path, "up", ("README.md", "model-output/a/x.csv"))
    hub = tmp_path / "hub"
    _git(tmp_path, "clone", "-q", "--sparse", str(up), str(hub))
    assert (hub / ".git").is_dir()
    out, calls, said = _setup(tmp_path, hub)
    assert out.returncode == 0, out.stdout + out.stderr
    assert f"hub present: {hub}" in said, said
    assert [c for c in calls if c.startswith("sparse-checkout add ")], calls
