"""install.sh's closing line says how to start the console on this system.

FluBNF.app and FluBNF.command are macOS's. On Linux and WSL2 the console
starts from its venv (`flubnf app`), which opens it in the browser when
there is no GTK or Qt for a window, so install.sh names that command there.

install.sh runs on a folder that is already a clone (nothing is cloned),
with setup.sh, setup_engine.sh and uname as stand-ins.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"), reason="install.sh is the POSIX route")


def _exe(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + text)
    path.chmod(0o755)


@pytest.mark.parametrize("system, route", [
    ("Darwin", None), ("Linux", None), ("Linux", "private")])
def test_the_closing_line_names_this_systems_launch(tmp_path, system, route):
    dest, home, stub = tmp_path / "flubnf", tmp_path / "home", tmp_path / "bin"
    (dest / ".git").mkdir(parents=True)
    home.mkdir()
    _exe(dest / "setup.sh", "exit 0\n")
    _exe(dest / "setup_engine.sh", "exit 0\n")
    _exe(stub / "uname", f'echo "{system}"\n')
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLUBNF_")}
    env.update({"HOME": str(home), "GIT_TERMINAL_PROMPT": "0",
                "FLUBNF_DIR": str(dest),
                "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
    if route:
        env["FLUBNF_ENGINE"] = route
    out = subprocess.run([BASH, str(REPO / "install.sh")], env=env,
                         stdin=subprocess.DEVNULL, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    done = [ln for ln in out.stdout.splitlines() if ln.startswith("Done.")]
    if system == "Darwin":
        assert done == [f'Done. Launch with:  open "{dest}/FluBNF.app"   '
                        "(or double-click FluBNF.command)"]
    else:
        assert done == [f'Done. Launch with:  "{dest}/.venv/bin/flubnf" app']
