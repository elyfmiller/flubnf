"""The launcher's dependency refresh, for either kind of venv.

FluBNF.command refreshes the editable install when pyproject.toml differs
from the last good install's stamp. It ran `.venv/bin/pip`, which a venv
made by uv does not have, so every refresh there failed and said
"(offline?)". Pinned here:

- a venv uv made (its pyvenv.cfg says `uv = <version>`) is refreshed with
  `uv pip install --python .venv/bin/python` when uv is on PATH;
- any other venv with the venv's own `python -m pip`, never with uv;
- "(offline?)" only when pip's or uv's words are a network failure's;
  otherwise the cause is named in plain words (no pip, uv not found, a full
  disk, a file that could not be written, ...), with the installer's own
  output kept in view;
- the stamp moves only after a refresh that worked.

The block is sliced out of FluBNF.command, not reimplemented, and runs in a
folder of its own with stand-ins for the venv's python and for uv. PATH is
the stand-ins plus /usr/bin and /bin: nothing is installed or fetched.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "FluBNF.command"
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
START = "# Dependency refresh policy"
END = "if [ ! -x .venv/bin/flubnf ]; then\n  forget_reopen"

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="FluBNF.command is the macOS and Linux launcher; Windows has the .bat")

PYPROJECT = '[project]\nname = "flubnf"\nversion = "2"\n'
OLD_STAMP = '[project]\nname = "flubnf"\nversion = "1"\n'
UV_CFG = ("home = /opt/homebrew/opt/python@3.12/bin\nimplementation = CPython\n"
          "uv = 0.5.11\nversion_info = 3.12.8\n"
          "include-system-site-packages = false\n")
VENV_CFG = ("home = /opt/homebrew/opt/python@3.12/bin\n"
            "include-system-site-packages = false\nversion = 3.12.12\n")

# The venv's python: logs its arguments; `-m pip` fails as a pipless venv's
# does unless {ctl}/has-pip exists, and an install prints {ctl}/out to
# stderr and exits {ctl}/rc.
PYTHON = r"""#!/bin/sh
echo "python $*" >> "{ctl}/calls"
if [ "$1" = -m ] && [ "$2" = pip ]; then
  [ -f "{ctl}/has-pip" ] || { echo "$0: No module named pip" >&2; exit 1; }
  cat "{ctl}/out" >&2
  exit "$(cat "{ctl}/rc")"
fi
exit 0
"""
# uv: logs its arguments, prints {ctl}/out to stderr, exits {ctl}/rc
UV = r"""#!/bin/sh
echo "uv $*" >> "{ctl}/calls"
cat "{ctl}/out" >&2
exit "$(cat "{ctl}/rc")"
"""

# What pip prints offline (pip 24, -q keeps its warnings)
PIP_OFFLINE = (
    "WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, "
    "status=None)) after connection broken by 'NewConnectionError('<pip._vendor."
    "urllib3.connection.HTTPSConnection object at 0x104a3c0d0>: Failed to "
    "establish a new connection: [Errno 8] nodename nor servname provided, or "
    "not known')': /simple/setuptools/\n"
    "ERROR: Could not find a version that satisfies the requirement "
    "setuptools>=61 (from versions: none)\n"
    "ERROR: No matching distribution found for setuptools>=61\n")
PIP_TIMEOUT = (
    "WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, "
    "status=None)) after connection broken by 'ReadTimeoutError(\"HTTPSConnection"
    "Pool(host='pypi.org', port=443): Read timed out. (read timeout=15)\")': "
    "/simple/fastapi/\n"
    "ERROR: No matching distribution found for fastapi\n")
# What uv prints offline
UV_OFFLINE = (
    "error: Request failed after 3 retries\n"
    "  Caused by: Failed to fetch: `https://pypi.org/simple/setuptools/`\n"
    "  Caused by: error sending request for url (https://pypi.org/simple/setuptools/)\n"
    "  Caused by: client error (Connect)\n"
    "  Caused by: dns error: failed to lookup address information: nodename "
    "nor servname provided, or not known\n")
DISK_FULL = ("ERROR: Could not install packages due to an OSError: [Errno 28] "
             "No space left on device\n")
DENIED = ("ERROR: Could not install packages due to an OSError: [Errno 13] "
          "Permission denied: '/x/.venv/lib/python3.12/site-packages/fastapi'\n"
          "Check the permissions.\n")
OLD_PYTHON = ("ERROR: Package 'flubnf' requires a different Python: 3.10.14 "
              "not in '>=3.11'\n")
CONFLICT = ("ERROR: Cannot install flubnf because these package versions have "
            "conflicting dependencies.\n"
            "ERROR: ResolutionImpossible: for help visit "
            "https://pip.pypa.io/en/latest/topics/dependency-resolution/\n")
BUILD_FAILED = ("  error: subprocess-exited-with-error\n"
                "  × Getting requirements to build editable did not run "
                "successfully.\n"
                "  │ exit code: 1\n")


def _block() -> str:
    text = LAUNCHER.read_text(encoding="utf-8")
    assert START in text and END in text, (
        "the dependency refresh moved or was renamed in FluBNF.command; this "
        "test slices it out from its policy comment to the missing-launcher "
        "check")
    body = text.split(START, 1)[1].split(END, 1)[0]
    return ("set -u\n"
            'needs_terminal() { echo "· $1: handing over to Terminal"; }\n'
            "forget_reopen() { :; }\n" + START + body)


def _exe(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


class Copy:
    """A FluBNF folder whose pyproject.toml changed since its last install."""

    def __init__(self, tmp_path: Path, *, cfg: str, pip: bool = False,
                 uv: bool = False, rc: int = 0, out: str = ""):
        self.dir = tmp_path / "flubnf"
        self.ctl = tmp_path / "ctl"
        self.ctl.mkdir()
        (self.ctl / "rc").write_text(f"{rc}\n")
        (self.ctl / "out").write_text(out)
        if pip:
            (self.ctl / "has-pip").write_text("")
        venv = self.dir / ".venv"
        _exe(venv / "bin" / "python", PYTHON.replace("{ctl}", str(self.ctl)))
        _exe(venv / "bin" / "flubnf", "#!/bin/sh\nexit 0\n")
        (venv / "pyvenv.cfg").write_text(cfg)
        (venv / ".pyproject.stamp").write_text(OLD_STAMP)
        (self.dir / "pyproject.toml").write_text(PYPROJECT)
        self.bin = tmp_path / "stand-ins"
        self.bin.mkdir()
        if uv:
            _exe(self.bin / "uv", UV.replace("{ctl}", str(self.ctl)))
        (tmp_path / "refresh.sh").write_text(_block())
        self.script = tmp_path / "refresh.sh"

    def run(self) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("FLUBNF_", "PIP_", "UV_", "VIRTUAL_ENV"))}
        env.update({"HOME": str(self.dir.parent),
                    "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"})
        return subprocess.run([BASH, str(self.script)], cwd=self.dir, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=60)

    @property
    def calls(self) -> list[str]:
        log = self.ctl / "calls"
        return log.read_text().splitlines() if log.exists() else []

    def stamped(self) -> bool:
        return ((self.dir / ".venv" / ".pyproject.stamp").read_text()
                == PYPROJECT)


def _said(out: subprocess.CompletedProcess) -> str:
    return out.stdout + out.stderr


# --- which installer ---------------------------------------------------------
def test_a_venv_uv_made_is_refreshed_with_uv(tmp_path):
    """uv's venv has no pip: `.venv/bin/pip` failed there on every refresh."""
    c = Copy(tmp_path, cfg=UV_CFG, uv=True)
    out = c.run()
    assert out.returncode == 0, _said(out)
    uv = [ln for ln in c.calls if ln.startswith("uv ")]
    assert len(uv) == 1, c.calls
    args = shlex.split(uv[0])[1:]
    assert args[:2] == ["pip", "install"], args
    assert args[args.index("--python") + 1] == ".venv/bin/python", args
    assert args[args.index("-e") + 1] == ".[app,dev]", args
    assert not [ln for ln in c.calls if ln.startswith("python -m pip")], c.calls
    assert "failed" not in out.stdout, _said(out)
    assert c.stamped()


def test_a_venv_venv_made_is_refreshed_with_its_own_python_m_pip(tmp_path):
    """No pip script needed (a venv given pip by ensurepip has pip3 only),
    and never uv, even with uv on PATH."""
    c = Copy(tmp_path, cfg=VENV_CFG, pip=True, uv=True)
    out = c.run()
    assert out.returncode == 0, _said(out)
    assert c.calls == ["python -m pip install -q -e .[app,dev]"], c.calls
    assert "failed" not in out.stdout, _said(out)
    assert c.stamped()


# --- a venv that cannot be refreshed ---------------------------------------
def test_a_uv_venv_with_no_uv_found_says_so_not_offline(tmp_path):
    c = Copy(tmp_path, cfg=UV_CFG, uv=False)
    out = c.run()
    assert out.returncode == 0, _said(out)
    assert "offline" not in out.stdout, out.stdout
    assert ("· dependency refresh failed (the venv in .venv was made by uv "
            "and has no pip, and no uv command was found), running with what "
            "is installed") in out.stdout, out.stdout
    assert "Put uv on PATH" in out.stdout, out.stdout
    assert not c.stamped()


def test_a_venv_without_pip_says_so_and_how_to_give_it_pip(tmp_path):
    c = Copy(tmp_path, cfg=VENV_CFG, pip=False, uv=True)
    out = c.run()
    assert out.returncode == 0, _said(out)
    assert "offline" not in out.stdout, out.stdout
    assert ("· dependency refresh failed (the venv in .venv has no pip), "
            "running with what is installed") in out.stdout, out.stdout
    line = next(ln for ln in out.stdout.splitlines() if "ensurepip" in ln)
    cmd = shlex.split(line.split("To give it pip:", 1)[1].split(", then", 1)[0])
    # the whole path, as typed in a Terminal opened anywhere ($PWD can be the
    # physical path, /private/var on macOS, of tmp_path)
    assert Path(cmd[0]).resolve() == (c.dir / ".venv/bin/python").resolve(), line
    assert cmd[1:] == ["-m", "ensurepip"], line
    assert not [ln for ln in c.calls if ln.startswith("uv ")], c.calls
    assert not c.stamped()


# --- why a refresh failed --------------------------------------------------
@pytest.mark.parametrize("cfg, out", [
    (VENV_CFG, PIP_OFFLINE),
    (VENV_CFG, PIP_TIMEOUT),
    (UV_CFG, UV_OFFLINE),
], ids=["pip-no-host", "pip-timeout", "uv-dns"])
def test_a_network_failure_says_offline(tmp_path, cfg, out):
    c = Copy(tmp_path, cfg=cfg, pip=True, uv=True, rc=1, out=out)
    res = c.run()
    assert res.returncode == 0, _said(res)
    assert ("· dependency refresh failed (offline?), running with what is "
            "installed") in res.stdout, res.stdout
    assert out.splitlines()[-1] in res.stdout       # the installer's own words
    assert not c.stamped()


@pytest.mark.parametrize("cfg, out, cause", [
    (VENV_CFG, DISK_FULL, "the disk is full"),
    (VENV_CFG, DENIED, "a file could not be written: permission denied"),
    (VENV_CFG, OLD_PYTHON,
     "a package needs a different Python version than the venv's"),
    (VENV_CFG, CONFLICT, "the packages FluBNF needs conflict with each other"),
    (VENV_CFG, BUILD_FAILED, "pip stopped with the error above"),
    (UV_CFG, "error: Failed to build `flubnf @ file:///x`\n",
     "uv stopped with the error above"),
], ids=["disk-full", "denied", "python", "conflict", "pip-other", "uv-other"])
def test_any_other_failure_names_its_cause_not_offline(tmp_path, cfg, out,
                                                       cause):
    c = Copy(tmp_path, cfg=cfg, pip=True, uv=True, rc=1, out=out)
    res = c.run()
    assert res.returncode == 0, _said(res)
    assert "offline" not in res.stdout, res.stdout
    assert (f"· dependency refresh failed ({cause}), running with what is "
            "installed") in res.stdout, res.stdout
    assert out.splitlines()[0] in res.stdout        # the installer's own words
    assert not c.stamped()


def test_an_unchanged_pyproject_runs_no_installer(tmp_path):
    c = Copy(tmp_path, cfg=UV_CFG, uv=True)
    (c.dir / ".venv" / ".pyproject.stamp").write_text(PYPROJECT)
    out = c.run()
    assert out.returncode == 0, _said(out)
    assert c.calls == [] and out.stdout == "", _said(out)
