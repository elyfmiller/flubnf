"""setup.sh stops when the console cannot be installed, and a re-run
repairs a venv that runs neither pip nor the console.

Ubuntu and WSL2 ship python3.12 without its venv module's pip
(python3.12-venv is its own package). `python3.12 -m venv .venv` then makes
the folder, says ensurepip is missing and exits 1. setup.sh used to go on,
end with "console still runs" and exit 0, and a re-run skipped the
half-made .venv. Now:

- a venv that cannot be made is exit 1, and where apt-get exists and venv
  says its module or ensurepip is missing, the message names the package
  for setup.sh's own Python (python3.X-venv);
- a failing install of FluBNF itself is exit 1, unless an earlier install
  is there (an offline re-run keeps it);
- a failing BioNetGen install stays a warning, as in setup.ps1: the
  console runs without it;
- a .venv that runs neither pip nor the console is moved to
  .venv.broken-<stamp>, never deleted, and made again (one the console
  runs from is kept: tests/test_setup_sh_venv_cases.py).

Each run is a copy of setup.sh alone in tmp_path, with a stand-in
python3.12 (and pip) first on PATH, FLUBNF_NO_DATA=1, and HOME and
FLUBNF_HUB in tmp_path: nothing is installed or fetched, and the
checkout's .venv and .flubnf.env are never touched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="setup.sh is the POSIX route")

# Ubuntu's message, without the package name: setup.sh must say it
ENSUREPIP = ("The virtual environment was not created successfully because "
             "ensurepip is not available.")

PYTHON = """#!/bin/sh
# python3.12 as setup.sh uses it: the version test, -V, the version number,
# no pip module (as on Ubuntu), and -m venv as {ctl}/venv says: "pipless"
# makes the folder and fails, as Ubuntu does; "ok" makes a venv
case "$1" in
  -V) echo "Python 3.12.3"; exit 0 ;;
  -c) case "$2" in *print*) echo 3.12 ;; esac; exit 0 ;;
  -m)
    case "$2" in
      pip) echo "No module named pip" >&2; exit 1 ;;
      venv)
        mkdir -p "$3/bin"
        if [ "$(cat "{ctl}/venv")" = ok ]; then
          cp "{ctl}/venv-python" "$3/bin/python"
          cp "{ctl}/venv-pip" "$3/bin/pip"
          exit 0
        fi
        ln -s "$0" "$3/bin/python"
        echo "{ensurepip}" >&2
        exit 1 ;;
    esac ;;
esac
exit 0
"""

VENV_PYTHON = """#!/bin/sh
# the venv's Python: pip runs, and flubnf.settings.check() finds nothing missing
exit 0
"""

VENV_PIP = """#!/bin/sh
# the venv's pip: logs each install; the package install makes .venv/bin/flubnf
echo "$*" >> "{ctl}/pip.log"
case "$*" in
  *" -e "*)
    rc="$(cat "{ctl}/pip-rc")"
    if [ "$rc" = 0 ]; then
      printf '#!/bin/sh\\nexit 0\\n' > "$(dirname "$0")/flubnf"
      chmod +x "$(dirname "$0")/flubnf"
    fi
    exit "$rc" ;;
  *" bionetgen") exit "$(cat "{ctl}/bng-rc")" ;;
esac
exit 0
"""


def _exe(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


class Setup:
    """setup.sh in a folder of its own, with its stand-ins."""

    def __init__(self, tmp_path: Path, *, apt: bool = True):
        self.tmp = tmp_path
        self.repo = tmp_path / "flubnf"
        self.repo.mkdir()
        shutil.copy(REPO / "setup.sh", self.repo / "setup.sh")
        self.ctl = tmp_path / "ctl"
        self.ctl.mkdir()
        fill = {"ctl": self.ctl, "ensurepip": ENSUREPIP}
        _exe(self.ctl / "venv-python", VENV_PYTHON)
        _exe(self.ctl / "venv-pip", VENV_PIP.format(**fill))
        self.bin = tmp_path / "bin"
        _exe(self.bin / "python3.12", PYTHON.format(**fill))
        if apt:
            _exe(self.bin / "apt-get", "#!/bin/sh\nexit 0\n")
        (tmp_path / "home").mkdir()
        self.set(venv="ok", pip=0, bng=0)

    def set(self, *, venv: str | None = None, pip: int | None = None,
            bng: int | None = None) -> None:
        for name, value in (("venv", venv), ("pip-rc", pip), ("bng-rc", bng)):
            if value is not None:
                (self.ctl / name).write_text(f"{value}\n")

    def run(self, path: str | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FLUBNF_", "PIP_", "PYTHON"))}
        env.update({"HOME": str(self.tmp / "home"),
                    "FLUBNF_HUB": str(self.tmp / "hub"),
                    "FLUBNF_NO_DATA": "1", "GIT_TERMINAL_PROMPT": "0",
                    "PATH": f"{self.bin}{os.pathsep}"
                            f"{path or os.environ['PATH']}"})
        return subprocess.run([BASH, str(self.repo / "setup.sh")], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=120)

    @property
    def pip_calls(self) -> list:
        log = self.ctl / "pip.log"
        return log.read_text().splitlines() if log.exists() else []

    def broken(self) -> list:
        return sorted(self.repo.glob(".venv.broken-*"))


def _said(out: subprocess.CompletedProcess) -> str:
    return out.stdout + out.stderr


def test_a_venv_that_cannot_be_made_stops_setup_and_names_the_package(tmp_path):
    s = Setup(tmp_path)
    s.set(venv="pipless")
    out = s.run()
    assert out.returncode == 1, _said(out)
    assert ENSUREPIP in out.stderr
    assert "sudo apt install python3.12-venv" in out.stdout, _said(out)
    assert "then run ./setup.sh again." in out.stdout
    assert "console still runs" not in _said(out)
    assert "you are ready" not in _said(out)
    assert s.pip_calls == []                       # it stopped right there
    assert not (s.repo / ".flubnf.env").exists()


def test_without_apt_get_it_names_no_apt_package(tmp_path):
    system = "/usr/bin:/bin"
    if any(Path(d, "apt-get").exists() for d in system.split(":")):
        pytest.skip("this machine has apt-get on the system path")
    s = Setup(tmp_path, apt=False)
    s.set(venv="pipless")
    out = s.run(path=system)
    assert out.returncode == 1, _said(out)
    assert "apt install" not in out.stdout
    assert "anaconda.com/download), then run ./setup.sh again." in out.stdout


def test_a_failing_package_install_stops_setup(tmp_path):
    s = Setup(tmp_path)
    s.set(pip=1)
    out = s.run()
    assert out.returncode == 1, _said(out)
    assert "FluBNF did not install into .venv" in out.stdout
    assert "console still runs" not in _said(out)
    assert "you are ready" not in _said(out)
    assert len(s.pip_calls) == 1                   # BioNetGen not tried
    assert not (s.repo / ".flubnf.env").exists()


def test_a_failing_bionetgen_install_is_a_warning(tmp_path):
    s = Setup(tmp_path)
    s.set(bng=1)
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert "BioNetGen (BNG2.pl) did not install (see above)" in out.stdout
    assert "runs; fits need it." in out.stdout
    assert (s.repo / ".flubnf.env").is_file()
    assert "you are ready: .venv/bin/flubnf app" in out.stdout


def test_a_fixed_rerun_sets_the_broken_venv_aside_and_makes_it_again(tmp_path):
    s = Setup(tmp_path)
    s.set(venv="pipless")
    assert s.run().returncode == 1
    assert (s.repo / ".venv" / "bin" / "python").is_symlink()   # half made
    s.set(venv="ok")                       # python3.12-venv installed
    out = s.run()
    assert out.returncode == 0, _said(out)
    broken = s.broken()
    assert len(broken) == 1, broken
    assert (broken[0] / "bin" / "python").is_symlink()   # kept, not deleted
    assert f"it is kept as {broken[0].name} and made again" in out.stdout
    assert (s.repo / ".venv" / "bin" / "flubnf").is_file()
    assert "flubnf installed editable" in out.stdout
    assert "you are ready: .venv/bin/flubnf app" in out.stdout


def test_a_working_venv_is_kept_and_an_offline_rerun_goes_on(tmp_path):
    s = Setup(tmp_path)
    first = s.run()
    assert first.returncode == 0, _said(first)
    venv_python = (s.repo / ".venv" / "bin" / "python").read_bytes()
    s.set(pip=1, bng=1)                    # offline now
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert s.broken() == []
    assert (s.repo / ".venv" / "bin" / "python").read_bytes() == venv_python
    assert "FluBNF's packages did not update (see above; offline?)" in out.stdout
    assert "runs with what is installed." in out.stdout
    assert "BioNetGen (BNG2.pl) did not install" in out.stdout
    assert (s.repo / ".flubnf.env").is_file()
    assert len(s.pip_calls) == 4           # two installs, each run


def test_git_ignores_a_venv_set_aside():
    """A student's `git add -A` never commits a set-aside venv."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "--no-index", "-q",
         ".venv.broken-20261109-120000/bin/python"],
        capture_output=True, text=True)
    if out.returncode == 128:
        pytest.skip(f"no git work tree here: {out.stderr.strip()}")
    assert out.returncode == 0, ".gitignore does not cover .venv.broken-*/"
