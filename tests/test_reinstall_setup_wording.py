"""After the one-line reinstall, setup.sh's run-again line names the folder.

reinstall.sh is run as `curl ... | bash`: it runs setup.sh in the new copy
while the user's shell stays where it was, so "setup.sh" would not run as
typed. Pasting the reinstall line again is no way back either: it sets the
new copy aside too, or finds it current and does nothing (a failed data
fetch leaves a copy that reads as current). So reinstall.sh says where it
came from (FLUBNF_SETUP_FROM=reinstall), and setup.sh's run-again line then
gives the command with the folder in it: cd "<the copy>" && ./setup.sh.

setup.sh runs in a copy of its own with stand-ins for Python, the venv's
pip and python, the app host build and git, whose clone of the hub fails
(the run-again line's case); reinstall.sh against a local bare origin whose
setup.sh records what it was told. Nothing is installed or fetched.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="setup.sh and reinstall.sh are the POSIX route")


def _said(out: subprocess.CompletedProcess) -> str:
    return out.stdout + out.stderr


def _commands(out: str) -> list[list[str]]:
    """Each `cd "<folder>" && ./setup.sh` the output gives, split as a shell
    would."""
    return [shlex.split(m.group(0))
            for m in re.finditer(r'cd "[^"]+" && \./setup\.sh', out)]


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


class Setup:
    """setup.sh in a copy of its own (a folder with a space in its name),
    run with stand-ins on a PATH of their own plus /usr/bin and /bin."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.repo = tmp / "new copy" / "flubnf"
        self.repo.mkdir(parents=True)
        shutil.copy2(REPO / "setup.sh", self.repo / "setup.sh")
        self.calls = tmp / "calls"
        log = f'echo "$0 $*" >> "{self.calls}"\n'
        bin_ = tmp / "stand-ins"
        # a Python 3.12 for the version checks; `-V` names it
        _stub(bin_ / "python3.12", log + '[ "$1" = -V ] && echo "Python 3.12.8"\nexit 0\n')
        # git: the hub clone fails, as it does offline
        _stub(bin_ / "git", log + "exit 128\n")
        # the venv is there: its pip installs, its python passes doctor,
        # its console is installed (setup.sh stops without one)
        _stub(self.repo / ".venv" / "bin" / "pip", log + "exit 0\n")
        _stub(self.repo / ".venv" / "bin" / "python", log + "exit 0\n")
        _stub(self.repo / ".venv" / "bin" / "flubnf", log + "exit 0\n")
        _stub(self.repo / "scripts" / "macos" / "build_app_host.sh", log + "exit 0\n")
        self.home = tmp / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FLUBNF_")}
        self.env.update({
            "HOME": str(self.home), "PATH": f"{bin_}:/usr/bin:/bin",
            "FLUBNF_HUB": str(tmp / "hub"),
            "FLUBNF_ENGINE_VENV": str(self.home / ".venvs" / "flubnf-engine"),
            "FLUBNF_PYBNF": str(self.home / "GitHub" / "PyBNF-pf")})

    def run(self, **env: str) -> subprocess.CompletedProcess:
        out = subprocess.run(
            [BASH, str(self.repo / "setup.sh")], env={**self.env, **env},
            cwd=self.tmp, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=60)
        # the stand-ins ran: the hub clone was tried, and failed
        assert "git clone" in self.calls.read_text(), _said(out)
        return out


# --- setup.sh's words -----------------------------------------------------
def test_after_the_reinstall_the_way_back_names_the_folder(tmp_path):
    s = Setup(tmp_path)
    out = s.run(FLUBNF_SETUP_FROM="reinstall")
    assert out.returncode == 0, _said(out)
    cmd = f'cd "{s.repo}" && ./setup.sh'
    assert (f"data fetch failed (offline?) -- run {cmd} again when connected"
            in out.stdout), out.stdout
    # typed in a Terminal opened anywhere, it runs this copy's setup.sh
    assert _commands(out.stdout) == [["cd", str(s.repo), "&&", "./setup.sh"]], \
        out.stdout
    assert "rerun setup.sh" not in out.stdout, out.stdout
    assert "install line" not in out.stdout and "reinstall line" not in out.stdout


@pytest.mark.parametrize("env, again", [
    ({}, "run ./setup.sh again"),
    ({"FLUBNF_SETUP_FROM": "install"}, "paste the install line again")])
def test_the_reinstall_wording_is_its_own_and_the_plain_run_stands(
        tmp_path, env, again):
    """Run by hand, in its folder, setup.sh keeps its words, and run from
    the one-line install, the install line's."""
    s = Setup(tmp_path)
    plain = s.run(**env)
    assert plain.returncode == 0, _said(plain)
    assert (f"data fetch failed (offline?) -- {again} when connected"
            in plain.stdout), plain.stdout
    assert not _commands(plain.stdout), plain.stdout


# --- reinstall.sh tells setup.sh ------------------------------------------
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="reinstall.sh refuses to run as root")
def test_reinstall_sh_tells_setup_sh_where_it_came_from(tmp_path):
    """Run on a machine with no FluBNF yet, against a local origin whose
    setup.sh writes down FLUBNF_SETUP_FROM and fails: reinstall.sh stops
    there and leaves the new copy."""
    src = tmp_path / "src"
    src.mkdir()
    env_git = {**os.environ, **GIT_ENV}
    git = lambda *a, cwd=src: subprocess.run(  # noqa: E731
        ["git", *a], cwd=cwd, env=env_git, check=True, capture_output=True)
    git("init", "-q", "-b", "main", ".")
    told = tmp_path / "told"
    (src / "setup.sh").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "${{FLUBNF_SETUP_FROM:-}}" > "{told}"\nexit 1\n')
    (src / "setup_engine.sh").write_text(
        f'#!/bin/sh\necho engine >> "{tmp_path}/engine"\nexit 0\n')
    for name in ("setup.sh", "setup_engine.sh"):
        (src / name).chmod(0o755)
    git("add", ".")
    git("commit", "-qm", "stand-in")
    origin = tmp_path / "origin.git"
    git("clone", "-q", "--bare", str(src), str(origin), cwd=tmp_path)

    home = tmp_path / "home"
    home.mkdir()
    stand = tmp_path / "stand-ins"            # a Python 3.12 for the checks
    stand.mkdir()
    py = stand / "python3.12"
    py.write_text('#!/bin/sh\n[ "$1" = -V ] && echo "Python 3.12.8"\nexit 0\n')
    py.chmod(0o755)
    dest = home / "GitHub" / "flubnf"
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLUBNF_")}
    env.update({"HOME": str(home), "FLUBNF_REPO": str(origin),
                "FLUBNF_DIR": str(dest),
                "FLUBNF_REINSTALL_YES": "1", "FLUBNF_REINSTALL_NO_OPEN": "1",
                "FLUBNF_REINSTALL_IGNORE_RUNNING": "1",
                "GIT_TERMINAL_PROMPT": "0", **GIT_ENV,
                "PATH": f"{stand}{os.pathsep}{os.environ['PATH']}"})
    out = subprocess.run([BASH, str(REPO / "reinstall.sh")], env=env,
                         cwd=tmp_path, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 1, _said(out)          # it stops with setup.sh
    assert told.read_text() == "reinstall\n", _said(out)
    assert "setup.sh did not finish" in out.stdout, out.stdout
    assert not (tmp_path / "engine").exists()       # nothing after it ran
    assert (dest / "setup.sh").is_file()            # the new copy stays
