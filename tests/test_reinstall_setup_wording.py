"""After the one-line reinstall, setup.sh's run-again lines name the folder.

reinstall.sh is run as `curl ... | bash`: it runs setup.sh in the new copy
while the user's shell stays where it was, so "./setup.sh" would not run as
typed. Pasting the reinstall line again is no way back either: it sets the
new copy aside too, or finds it current and does nothing (a failed
BioNetGen install or data fetch leaves a copy that reads as current). So
reinstall.sh says where it came from (FLUBNF_SETUP_FROM=reinstall), as
install.sh does, and setup.sh's run-again lines then give the command with
the folder in it: cd "<the copy>" && ./setup.sh.

setup.sh runs with the stand-ins of tests/test_setup_sh_venv_cases.py;
reinstall.sh against a local bare origin whose setup.sh records what it was
told.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_setup_sh_venv_cases import Setup, _said

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="setup.sh and reinstall.sh are the POSIX route")


def _commands(out: str) -> list[list[str]]:
    """Each `cd "<folder>" && ./setup.sh` the output gives, split as a shell
    would."""
    return [shlex.split(m.group(0))
            for m in re.finditer(r'cd "[^"]+" && \./setup\.sh', out)]


# --- setup.sh's words -----------------------------------------------------
@pytest.mark.parametrize("venv, pip, bng, rc, expect", [
    ("full", 0, 0, 1, "Run {cmd} again once the problem above is fixed."),
    ("ok", 1, 0, 1, "needs it: run {cmd} again once the problem"),
    ("ok", 0, 1, 0, "Run {cmd} again to retry."),
], ids=["venv-not-made", "flubnf-not-installed", "bionetgen"])
def test_after_the_reinstall_the_way_back_names_the_folder(
        tmp_path, venv, pip, bng, rc, expect):
    s = Setup(tmp_path)
    s.set(venv=venv, pip=pip, bng=bng)
    out = s.run(FLUBNF_SETUP_FROM="reinstall")
    assert out.returncode == rc, _said(out)
    cmd = f'cd "{s.repo}" && ./setup.sh'
    assert expect.format(cmd=cmd) in out.stdout, out.stdout
    # typed in a Terminal opened anywhere, it runs this copy's setup.sh
    assert _commands(out.stdout) == [["cd", str(s.repo), "&&", "./setup.sh"]], \
        out.stdout
    assert not re.search(r"[Rr]un \./setup\.sh", out.stdout), out.stdout
    assert "install line" not in out.stdout and "reinstall line" not in out.stdout


def test_the_reinstall_wording_is_its_own_and_the_others_stand(tmp_path):
    """The plain run and install.sh's keep their words."""
    s = Setup(tmp_path)
    s.set(venv="full")
    plain = s.run()
    assert "Run ./setup.sh again once the problem above is fixed." in plain.stdout
    assert not _commands(plain.stdout)
    install = s.run(FLUBNF_SETUP_FROM="install")
    assert ("Paste the install line again once the problem above is fixed."
            in install.stdout)
    assert not _commands(install.stdout)


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
