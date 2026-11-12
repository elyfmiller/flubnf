"""setup.sh keeps every venv the console runs from, and says how to run
it again in words the user can type.

- A venv without pip (one uv made, or `venv --without-pip`) that the
  console runs from is kept, online or off: setting it aside offline left
  no console at all. A venv that runs neither pip nor the console is set
  aside and made again, as before.
- When making the venv again fails, the one set aside comes back: a run
  that fails leaves no new .venv.broken-<stamp>.
- The apt hint is for a missing venv module or ensurepip only; a full disk
  gets "once the problem above is fixed", not a package to install.
- A venv in the Windows layout (Scripts/, as setup.ps1 and a Windows
  Python under Git Bash make it) is used where it is. Its stand-ins carry
  Windows' own names, python.exe, pip.exe and flubnf.exe, and no
  extension-less ones (review 3 of #93, re-check R6): setup.sh names the
  .exe itself, so the test does not lean on Git Bash finding it.
- After the one-line install (install.sh), the user's shell is not in the
  install folder: setup.sh says to paste the install line again.
- A sparse hub clone that holds auxiliary-data/ but not its archive is
  widened, so doctor's "Run ./setup.sh" does what it says; doctor's hint
  also gives git's own command, which works on any system.

Each run is a copy of setup.sh alone in tmp_path with stand-ins first on
PATH, FLUBNF_NO_DATA=1 (or a local hub clone in tmp_path), and HOME in
tmp_path: nothing is installed or fetched.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="setup.sh is the POSIX route")

# Ubuntu's message, wrapped as Ubuntu wraps it
ENSUREPIP = ("The virtual environment was not created successfully because "
             "ensurepip is not\navailable.  On Debian/Ubuntu systems, you "
             "need to install the python3-venv\npackage using the following "
             "command.")
DISK_FULL = "[Errno 28] No space left on device: 'lib'"

# python3.12 as setup.sh uses it. -m venv does as {ctl}/venv says: "ok" and
# "win" make a working venv (bin/, or Scripts/ with python.exe and pip.exe,
# as a Windows Python does);
# "pipless" makes the folder and fails as Ubuntu does; "full" makes part of
# the folder and fails as on a full disk.
PYTHON = r"""#!/bin/sh
case "$1" in
  -V) echo "Python 3.12.3"; exit 0 ;;
  -c) case "$2" in *print*) echo 3.12 ;; esac; exit 0 ;;
  -m)
    case "$2" in
      pip) echo "No module named pip" >&2; exit 1 ;;
      venv)
        mode="$(cat "{ctl}/venv")"
        case "$mode" in
          ok|win)
            d=bin; x=""; [ "$mode" = win ] && { d=Scripts; x=.exe; }
            mkdir -p "$3/$d"
            cp "{ctl}/venv-python" "$3/$d/python$x"
            cp "{ctl}/venv-pip" "$3/$d/pip$x"
            exit 0 ;;
          full)
            mkdir -p "$3/bin"
            echo "Error: {disk_full}" >&2
            exit 1 ;;
        esac
        mkdir -p "$3/bin"
        ln -s "$0" "$3/bin/python"
        printf '%s\n' "{ensurepip}" >&2
        exit 1 ;;
    esac ;;
esac
exit 0
"""

# the venv's Python: pip runs, and flubnf.settings.check() finds nothing
VENV_PYTHON = "#!/bin/sh\nexit 0\n"

# a venv's Python without the pip module (uv's venvs)
NOPIP_PYTHON = r"""#!/bin/sh
[ "$1" = -m ] && [ "$2" = pip ] && { echo "No module named pip" >&2; exit 1; }
exit 0
"""

# the venv's pip: logs each install as `<its folder>: <args>`; the package
# install makes the console beside it (flubnf.exe in Scripts/, as on Windows)
VENV_PIP = r"""#!/bin/sh
here="$(basename "$(dirname "$0")")"
echo "$here: $*" >> "{ctl}/pip.log"
case "$*" in
  *" -e "*)
    rc="$(cat "{ctl}/pip-rc")"
    if [ "$rc" = 0 ]; then
      x=""; [ "$here" = Scripts ] && x=.exe
      printf '#!/bin/sh\nexit 0\n' > "$(dirname "$0")/flubnf$x"
      chmod +x "$(dirname "$0")/flubnf$x"
    fi
    exit "$rc" ;;
  *" bionetgen") exit "$(cat "{ctl}/bng-rc")" ;;
esac
exit 0
"""

CONSOLE = "#!/bin/sh\n# the console: it runs\nexit 0\n"

#: what a Windows venv's programs end in: Scripts/ holds python.exe,
#: pip.exe and flubnf.exe, never a file named python (re-check R6)
WIN_EXE = ".exe"


def _windows_names_only(scripts: Path) -> bool:
    """Scripts/ as a Windows venv has it: the .exe names, none without."""
    names = {p.name for p in scripts.iterdir()}
    return ({"python.exe", "flubnf.exe"} <= names
            and not names & {"python", "pip", "flubnf"})


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
        fill = {"ctl": self.ctl, "ensurepip": ENSUREPIP,
                "disk_full": DISK_FULL}
        _exe(self.ctl / "venv-python", VENV_PYTHON)
        _exe(self.ctl / "venv-pip", VENV_PIP.replace("{ctl}", str(self.ctl)))
        py = PYTHON
        for k, v in fill.items():
            py = py.replace("{" + k + "}", str(v))
        self.bin = tmp_path / "bin"
        _exe(self.bin / "python3.12", py)
        if apt:
            _exe(self.bin / "apt-get", "#!/bin/sh\nexit 0\n")
        (tmp_path / "home").mkdir()
        self.hub = tmp_path / "hub"
        self.set(venv="ok", pip=0, bng=0)

    def set(self, *, venv=None, pip=None, bng=None) -> None:
        for name, value in (("venv", venv), ("pip-rc", pip), ("bng-rc", bng)):
            if value is not None:
                (self.ctl / name).write_text(f"{value}\n")

    def venv(self, layout: str = "bin", *, python: str = NOPIP_PYTHON,
             pip: bool = False, console: bool = True) -> Path:
        """A .venv made beforehand, as uv or setup.ps1 would leave it: in
        Scripts/, Windows' names (python.exe, pip.exe, flubnf.exe) only."""
        d = self.repo / ".venv" / layout
        x = WIN_EXE if layout == "Scripts" else ""
        _exe(d / f"python{x}", python)
        if pip:
            shutil.copy(self.ctl / "venv-pip", d / f"pip{x}")
        if console:
            _exe(d / f"flubnf{x}", CONSOLE)
        (self.repo / ".venv" / "pyvenv.cfg").write_text("home = /nowhere\n")
        return d

    def run(self, path: str | None = None, **extra) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FLUBNF_", "PIP_", "PYTHON", "GIT_"))}
        env.update({"HOME": str(self.tmp / "home"),
                    "FLUBNF_HUB": str(self.hub),
                    "FLUBNF_NO_DATA": "1", "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CEILING_DIRECTORIES": str(self.tmp),
                    "PATH": f"{self.bin}{os.pathsep}"
                            f"{path or os.environ['PATH']}"})
        env.update(extra)
        return subprocess.run([BASH, str(self.repo / "setup.sh")], env=env,
                              cwd=self.tmp, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)

    @property
    def pip_calls(self) -> list:
        log = self.ctl / "pip.log"
        return log.read_text().splitlines() if log.exists() else []

    def broken(self) -> list:
        return sorted(self.repo.glob(".venv.broken-*"))


def _said(out: subprocess.CompletedProcess) -> str:
    return out.stdout + out.stderr


# --- a venv without pip ---------------------------------------------------
@pytest.mark.parametrize("online", [False, True])
def test_a_venv_without_pip_that_the_console_runs_from_is_kept(tmp_path, online):
    """uv's venv, FluBNF installed and working: kept where it is, offline
    too (origin/dev kept it; a venv set aside offline left no console)."""
    s = Setup(tmp_path)
    s.set(pip=0 if online else 1, bng=0 if online else 1)
    bin_ = s.venv()
    console = (bin_ / "flubnf").read_bytes()
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert s.broken() == []
    assert (bin_ / "flubnf").read_bytes() == console
    assert not (bin_ / "pip").exists()          # nothing made over it
    assert s.pip_calls == []
    assert "the venv in .venv has no pip (a venv made by uv, say)" in out.stdout
    assert "The console runs with what is" in out.stdout
    assert f'"{bin_ / "python"}" -m ensurepip, then run ./setup.sh again.' \
        in out.stdout
    assert "made again" not in out.stdout
    assert (s.repo / ".flubnf.env").is_file()
    assert "you are ready: .venv/bin/flubnf app" in out.stdout


def test_a_venv_that_runs_neither_pip_nor_the_console_is_set_aside(tmp_path):
    s = Setup(tmp_path)
    s.venv(console=False)                       # uv venv, nothing installed
    out = s.run()
    assert out.returncode == 0, _said(out)
    broken = s.broken()
    assert len(broken) == 1, broken
    assert (broken[0] / "bin" / "python").is_file()          # kept
    assert ("the venv in .venv runs neither pip nor the console: it is kept "
            f"as {broken[0].name} and made again") in out.stdout
    assert (s.repo / ".venv" / "bin" / "flubnf").is_file()
    assert "flubnf installed editable" in out.stdout


def test_a_venv_whose_console_does_not_run_is_set_aside(tmp_path):
    """A console script that is there but fails (its Python removed, say)
    is no console."""
    s = Setup(tmp_path)
    bin_ = s.venv()
    _exe(bin_ / "flubnf", "#!/bin/sh\nexit 127\n")
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert len(s.broken()) == 1
    assert "flubnf installed editable" in out.stdout


def test_a_venv_with_pip_as_a_module_only_installs_through_it(tmp_path):
    """ensurepip by hand gives pip3, not pip: setup goes through -m pip."""
    s = Setup(tmp_path)
    s.venv(python=VENV_PYTHON.replace(
        "exit 0", f'echo "python: $*" >> "{s.ctl}/pip.log"; exit 0'))
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert s.broken() == []
    calls = [c for c in s.pip_calls if " install " in c]
    assert calls[0].startswith("python: -m pip install -q -e "), calls
    assert calls[1] == "python: -m pip install -q bionetgen", calls


# --- a venv that cannot be made -------------------------------------------
def test_a_failed_remake_puts_the_old_venv_back(tmp_path):
    """Each failed try used to leave one more .venv.broken-<stamp>."""
    s = Setup(tmp_path)
    s.venv(console=False)
    (s.repo / ".venv" / "mine.txt").write_text("the old venv\n")
    s.set(venv="full")
    for _ in range(2):
        out = s.run()
        assert out.returncode == 1, _said(out)
        assert s.broken() == []
        assert (s.repo / ".venv" / "mine.txt").read_text() == "the old venv\n"
        assert "The old venv is back in .venv." in out.stdout
    s.set(venv="ok")                            # space freed
    out = s.run()
    assert out.returncode == 0, _said(out)
    broken = s.broken()
    assert len(broken) == 1, broken
    assert (broken[0] / "mine.txt").is_file()


def test_a_full_disk_gets_no_apt_hint(tmp_path):
    s = Setup(tmp_path)                         # apt-get is there
    s.set(venv="full")
    out = s.run()
    assert out.returncode == 1, _said(out)
    assert DISK_FULL in out.stderr              # what venv said, shown
    assert "apt install" not in out.stdout
    assert "Anaconda" not in out.stdout
    assert "Run ./setup.sh again once the problem above is fixed." in out.stdout
    assert s.pip_calls == []


def test_ubuntus_wrapped_ensurepip_message_still_gets_the_apt_hint(tmp_path):
    s = Setup(tmp_path)
    s.set(venv="pipless")
    out = s.run()
    assert out.returncode == 1, _said(out)
    assert "ensurepip is not\navailable." in out.stderr
    assert "sudo apt install python3.12-venv" in out.stdout
    assert "then run ./setup.sh again." in out.stdout


# --- the Windows layout ---------------------------------------------------
def test_a_windows_layout_venv_is_used_where_it_is(tmp_path):
    """setup.ps1's venv under Git Bash: Scripts/, no bin/python."""
    s = Setup(tmp_path)
    scripts = s.venv("Scripts", python=VENV_PYTHON, pip=True)
    out = s.run()
    assert out.returncode == 0, _said(out)
    assert s.broken() == []
    assert not (s.repo / ".venv" / "bin").exists()
    assert [c.split(":")[0] for c in s.pip_calls] == ["Scripts", "Scripts"]
    assert (scripts / "flubnf.exe").is_file()
    assert _windows_names_only(scripts)
    assert "you are ready: .venv/Scripts/flubnf app" in out.stdout


def test_a_venv_made_in_the_windows_layout_is_used(tmp_path):
    """A Windows Python makes Scripts/ under Git Bash, here too."""
    s = Setup(tmp_path)
    s.set(venv="win")
    out = s.run()
    assert out.returncode == 0, _said(out)
    scripts = s.repo / ".venv" / "Scripts"
    assert (scripts / "flubnf.exe").is_file()
    assert _windows_names_only(scripts)
    assert s.broken() == []
    assert "flubnf installed editable" in out.stdout
    assert "you are ready: .venv/Scripts/flubnf app" in out.stdout


# --- run it again ---------------------------------------------------------
@pytest.mark.parametrize("venv, pip, expect", [
    ("pipless", 0, "then paste the install line again."),
    ("full", 0, "Paste the install line again once the problem above is fixed."),
    ("ok", 1, "needs it: paste the install line again once the problem"),
])
def test_after_the_one_line_install_the_way_back_is_the_install_line(
        tmp_path, venv, pip, expect):
    """install.sh runs setup.sh in the install folder while the user's shell
    stays where it was: "./setup.sh" would not run as typed there."""
    s = Setup(tmp_path)
    s.set(venv=venv, pip=pip)
    out = s.run(FLUBNF_SETUP_FROM="install")
    assert out.returncode == 1, _said(out)
    assert expect in out.stdout, out.stdout
    assert "./setup.sh" not in out.stdout


def test_a_bionetgen_failure_after_the_install_names_the_install_line(tmp_path):
    s = Setup(tmp_path)
    s.set(bng=1)
    out = s.run(FLUBNF_SETUP_FROM="install")
    assert out.returncode == 0, _said(out)
    assert "Paste the install line again to retry." in out.stdout


def test_every_run_again_line_goes_through_the_one_wording():
    """No message of setup.sh names ./setup.sh by itself."""
    src = (REPO / "setup.sh").read_text(encoding="utf-8")
    named = [ln.strip() for ln in src.splitlines()
             if re.search(r"(re)?run (\./)?setup\.sh", ln, re.I)]
    assert named == ['again="run ./setup.sh again"; Again="Run ./setup.sh again"'], named


def test_install_sh_tells_setup_sh_where_it_came_from(tmp_path):
    dest, home, stub = tmp_path / "flubnf", tmp_path / "home", tmp_path / "bin"
    (dest / ".git").mkdir(parents=True)
    home.mkdir()
    _exe(dest / "setup.sh",
         f'#!/bin/sh\necho "$FLUBNF_SETUP_FROM" > "{tmp_path}/from"\nexit 1\n')
    _exe(dest / "setup_engine.sh", "#!/bin/sh\nexit 0\n")
    _exe(stub / "uname", '#!/bin/sh\necho Linux\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLUBNF_")}
    env.update({"HOME": str(home), "GIT_TERMINAL_PROMPT": "0",
                "FLUBNF_DIR": str(dest),
                "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
    out = subprocess.run([BASH, str(REPO / "install.sh")], env=env,
                         cwd=tmp_path, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 1, _said(out)        # it stops with setup.sh
    assert (tmp_path / "from").read_text() == "install\n"
    assert "Done." not in out.stdout


# --- the hub's archive ----------------------------------------------------
#: the test's own folder (sparse_hub sets it): git never looks above it
#: for a repository, so a command that misses the scratch clone fails
#: instead of reaching a checkout around the test folders
_CEILING: list = []


def _git(*args, cwd=None):
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null",
         *args], cwd=cwd, capture_output=True, text=True, timeout=60,
        env={**{k: v for k, v in os.environ.items()
                if not k.startswith("GIT_")},
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
             "GIT_CEILING_DIRECTORIES": _CEILING[-1]})
    assert out.returncode == 0, (args, out.stdout, out.stderr)
    return out


@pytest.fixture
def sparse_hub(tmp_path):
    """A local hub and a sparse clone of it whose cone holds auxiliary-data/
    (locations.csv and one other folder) but not target-data-archive/."""
    if shutil.which("git") is None:
        pytest.skip("no git")
    _CEILING[:] = [str(tmp_path)]
    up = tmp_path / "upstream"
    for rel in ("auxiliary-data/locations.csv",
                "auxiliary-data/other/x.csv",
                "auxiliary-data/target-data-archive/"
                "target-hospital-admissions_2025-01-11.csv",
                "target-data/target-hospital-admissions.csv",
                "model-output/FluSight-baseline/a.csv",
                "model-output/FluSight-ensemble/a.csv"):
        (up / rel).parent.mkdir(parents=True, exist_ok=True)
        (up / rel).write_text("x\n")
    _git("init", "-q", str(up))
    _git("add", "-A", cwd=up)
    _git("commit", "-q", "-m", "hub", cwd=up)
    hub = tmp_path / "hub"
    _git("clone", "-q", "--sparse", str(up), str(hub))
    _git("sparse-checkout", "set", "target-data", "auxiliary-data/other",
         "model-output/FluSight-baseline", "model-output/FluSight-ensemble",
         cwd=hub)
    assert (hub / "auxiliary-data").is_dir()
    assert not (hub / "auxiliary-data" / "target-data-archive").exists()
    return hub


def test_setup_widens_a_clone_that_lacks_only_the_archive(tmp_path, sparse_hub):
    """doctor fails this clone and names ./setup.sh, which used to look at
    the top folders only and widen nothing."""
    s = Setup(tmp_path)
    assert s.hub == sparse_hub
    out = s.run(FLUBNF_NO_DATA="0")
    assert out.returncode == 0, _said(out)
    assert ("this clone does not contain: auxiliary-data/target-data-archive"
            in out.stdout), out.stdout
    assert "sparse checkout widened to the directories the app reads" in out.stdout
    assert (sparse_hub / "auxiliary-data" / "target-data-archive").is_dir()
    assert (sparse_hub / "auxiliary-data" / "other" / "x.csv").is_file()


def test_doctors_hint_carries_a_step_that_widens_the_clone(sparse_hub, monkeypatch):
    """The hint's git command, run as printed, gets past the FAIL."""
    import shlex

    from flubnf import doctor, settings
    monkeypatch.setattr(settings, "HUB", sparse_hub)
    res = doctor._check_hub("win32")
    assert res.status is doctor.Status.FAIL
    assert "Run setup.ps1:" in res.hint and "FLUBNF_HUB" in res.hint
    # the exact command, alone on its line: nothing a paste could carry along
    cmd = f'git -C "{sparse_hub}" sparse-checkout add auxiliary-data target-data'
    m = re.search(r"^ *(git -C .*)$", res.hint, re.M)
    assert m and m.group(1) == cmd, res.hint
    _git(*shlex.split(m.group(1))[1:])
    assert doctor._check_hub("win32").status is doctor.Status.OK
