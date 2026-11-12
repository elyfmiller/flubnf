"""The steps doctor, setup.sh and install.sh print can be pasted as printed.

- doctor's git step for a sparse hub clone stands alone on its last line:
  pasted with the sentence's comma, git added a folder "target-data," and
  left target-data absent.
- doctor gives that git step only for a hub folder with its own .git. For a
  folder that is there but is not a clone, git -C would walk up to any
  repository around it; doctor and setup.sh say plainly that the folder is
  not a clone, and setup.sh no longer tries a clone into it and reports
  "data fetch failed (offline?)".
- After the piped install the user's shell is not in the install folder:
  each setup_engine.sh step install.sh prints names that folder, and its
  closing line names the venv folder setup.sh used (bin or Scripts).
- setup.sh quotes the venv path it asks to be moved or deleted.

Every git command here runs in a repository the test made in tmp_path,
with GIT_CEILING_DIRECTORIES set there. setup.sh and install.sh run as
copies or with stand-ins (git, mv, uname, setup.sh, setup_engine.sh):
nothing is installed or fetched.
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

from flubnf import doctor, settings

REPO = Path(__file__).resolve().parents[1]
BASH = "/bin/bash" if sys.platform == "darwin" else "bash"
POSIX = pytest.mark.skipif(sys.platform.startswith("win"),
                           reason="setup.sh and install.sh are the POSIX route")
# a folder name a pasted path must survive
ODD = "it's a folder"
STEP = "it makes or widens the sparse clone, about 150 MB."


def _exe(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + text)
    path.chmod(0o755)
    return path


def _git_env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CEILING_DIRECTORIES": str(tmp_path),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0"})
    return env


def _git(tmp_path: Path, *args, cwd=None) -> subprocess.CompletedProcess:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "init.defaultBranch=main", "-c", "core.hooksPath=/dev/null",
         *args], cwd=cwd, env=_git_env(tmp_path), capture_output=True,
        text=True, timeout=60)
    assert out.returncode == 0, (args, out.stdout, out.stderr)
    return out


@pytest.fixture
def lean_hub(tmp_path):
    """A sparse clone of a local hub whose cone holds the comparators only:
    no target-data, no auxiliary-data."""
    if shutil.which("git") is None:
        pytest.skip("no git")
    up = tmp_path / "upstream"
    for rel in ("auxiliary-data/locations.csv",
                "auxiliary-data/target-data-archive/"
                "target-hospital-admissions_2025-01-11.csv",
                "target-data/target-hospital-admissions.csv",
                "model-output/FluSight-baseline/a.csv",
                "model-output/FluSight-ensemble/a.csv"):
        (up / rel).parent.mkdir(parents=True, exist_ok=True)
        (up / rel).write_text("x\n")
    _git(tmp_path, "init", "-q", str(up))
    _git(tmp_path, "add", "-A", cwd=up)
    _git(tmp_path, "commit", "-q", "-m", "hub", cwd=up)
    hub = tmp_path / ODD / "hub"
    hub.parent.mkdir()
    _git(tmp_path, "clone", "-q", "--sparse", str(up), str(hub))
    _git(tmp_path, "sparse-checkout", "set", "model-output/FluSight-baseline",
         "model-output/FluSight-ensemble", cwd=hub)
    assert not (hub / "target-data").exists()
    return hub


# --- doctor: the git step, alone on its line (R2) --------------------------
@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_doctors_git_step_is_the_exact_command_alone_on_the_last_line(
        lean_hub, monkeypatch, platform):
    monkeypatch.setattr(settings, "HUB", lean_hub)
    res = doctor._check_hub(platform)
    assert res.status is doctor.Status.FAIL
    cmd = f'git -C "{lean_hub}" sparse-checkout add auxiliary-data target-data'
    lines = res.hint.splitlines()
    assert lines[-1].strip() == cmd, res.hint
    assert [ln for ln in lines if "sparse-checkout" in ln] == [lines[-1]]
    assert "FLUBNF_HUB" in res.hint and STEP in res.hint


def test_the_git_line_pasted_whole_gets_past_the_fail(tmp_path, lean_hub,
                                                     monkeypatch):
    """Whoever copies the line from "git" to its end runs the right command
    (with the old wording that added "target-data," and more)."""
    monkeypatch.setattr(settings, "HUB", lean_hub)
    line = next(ln for ln in doctor._check_hub("darwin").hint.splitlines()
                if "sparse-checkout" in ln)
    pasted = line[line.index("git -C"):]
    _git(tmp_path, *shlex.split(pasted)[1:])
    listed = _git(tmp_path, "sparse-checkout", "list", cwd=lean_hub).stdout
    assert not any(e.endswith(",") for e in listed.split()), listed
    assert doctor._check_hub("darwin").status is not doctor.Status.FAIL


# --- doctor: a hub folder that is not a clone (R3) -------------------------
@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_a_full_folder_that_is_not_a_clone_gets_no_git_step(
        tmp_path, monkeypatch, platform):
    """git -C on it would walk up to any repository the folder sits in."""
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / "notes.txt").write_text("left here\n")
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub(platform)
    assert res.status is doctor.Status.FAIL
    assert "auxiliary-data/target-data-archive" in res.detail
    assert "git -C" not in res.hint and "sparse-checkout" not in res.hint
    assert res.hint.startswith("The folder is there but is not a git clone, "
                               "so setup cannot fetch the data into it. Move "
                               "or rename it first. Run "), res.hint
    assert STEP in res.hint and "FLUBNF_HUB" in res.hint


@pytest.mark.parametrize("platform, not_a_clone", [
    ("darwin", False), ("linux", False), ("win32", True)])
def test_an_empty_folder_gets_the_setup_step(tmp_path, monkeypatch, platform,
                                             not_a_clone):
    """setup.sh clones into an empty folder; setup.ps1 clones into none."""
    hub = tmp_path / "hub"
    hub.mkdir()
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub(platform)
    assert res.status is doctor.Status.FAIL
    assert "git -C" not in res.hint
    assert ("is not a git clone" in res.hint) is not_a_clone
    assert res.hint.endswith(f"{STEP} Or set FLUBNF_HUB to an existing clone.")


# --- setup.sh: a hub folder that is not a clone (R3) -----------------------
def _setup(tmp_path: Path, hub: Path, *, mv_fails: bool = False,
           venv_ok: bool = True, **extra) -> tuple:
    """setup.sh alone in a folder whose name holds a space and an
    apostrophe, with a venv already there and stand-ins first on PATH: a git
    that logs and fails, a python3.12, and an mv that fails if asked."""
    repo = tmp_path / ODD / "flubnf"
    repo.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "setup.sh", repo / "setup.sh")
    ctl, bin_, home = tmp_path / "ctl", tmp_path / "bin", tmp_path / "home"
    ctl.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    _exe(bin_ / "python3.12",
         'case "$1" in -V) echo "Python 3.12.3" ;; esac\nexit 0\n')
    _exe(bin_ / "git", f'echo "$*" >> "{ctl}/git.log"\nexit 1\n')
    if mv_fails:
        _exe(bin_ / "mv", "exit 1\n")
    vb = repo / ".venv" / "bin"
    if venv_ok:
        _exe(vb / "python", "exit 0\n")
        _exe(vb / "pip", "exit 0\n")
        _exe(vb / "flubnf", "exit 0\n")
    else:                                   # runs neither pip nor a console
        _exe(vb / "python", "exit 1\n")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("FLUBNF_", "PIP_", "PYTHON", "GIT_"))}
    env.update({"HOME": str(home), "FLUBNF_HUB": str(hub),
                "FLUBNF_NO_DATA": "0", "GIT_TERMINAL_PROMPT": "0",
                "GIT_CEILING_DIRECTORIES": str(tmp_path),
                "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}"})
    env.update(extra)
    out = subprocess.run([BASH, str(repo / "setup.sh")], env=env,
                         cwd=tmp_path, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=120)
    log = ctl / "git.log"
    return out, (log.read_text().splitlines() if log.exists() else []), repo


@POSIX
@pytest.mark.parametrize("source, again", [
    (None, "then run ./setup.sh again."),
    ("install", "then paste the install line again.")])
def test_setup_says_a_full_folder_is_not_a_clone(tmp_path, source, again):
    hub = tmp_path / "hub"
    (hub / "target-data").mkdir(parents=True)
    (hub / "notes.txt").write_text("left here\n")
    extra = {"FLUBNF_SETUP_FROM": source} if source else {}
    out, git_calls, _ = _setup(tmp_path, hub, **extra)
    assert out.returncode == 0, out.stdout + out.stderr
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)
    said = " ".join(ln.strip().lstrip("!").strip()
                    for ln in plain.splitlines())
    assert (f'"{hub}" is there but is not a git clone, so no data was fetched '
            "into it. Move or rename it (or set FLUBNF_HUB to an existing "
            f"clone), {again}") in said, out.stdout
    assert "data fetch failed" not in out.stdout
    assert not [c for c in git_calls if c.startswith("clone")], git_calls
    assert sorted(p.name for p in hub.iterdir()) == ["notes.txt", "target-data"]


@POSIX
def test_setup_still_clones_into_an_empty_folder(tmp_path):
    hub = tmp_path / "hub"
    hub.mkdir()
    out, git_calls, _ = _setup(tmp_path, hub)
    assert out.returncode == 0, out.stdout + out.stderr
    assert [c for c in git_calls if c.startswith("clone ")], git_calls
    assert "is not a git clone" not in out.stdout


# --- setup.sh: the venv path it asks to be moved (R4) ----------------------
@POSIX
def test_setup_quotes_the_venv_it_asks_to_be_moved_or_deleted(tmp_path):
    out, _, repo = _setup(tmp_path, tmp_path / "hub", mv_fails=True,
                          venv_ok=False, FLUBNF_NO_DATA="1")
    assert out.returncode == 1, out.stdout + out.stderr
    m = re.search(r"Move or delete (.+?) and then run \./setup\.sh again\.",
                  out.stdout)
    assert m, out.stdout
    assert shlex.split(m.group(1)) == [str(repo / ".venv")], m.group(1)


# --- install.sh: steps that name the install folder (R4) -------------------
def _install(tmp_path: Path, *, system: str, route: str, engine_rc: int,
             layout: tuple = ()) -> tuple:
    """install.sh on a copy already there (nothing is cloned) in a folder
    whose name holds a space and an apostrophe, run from another folder,
    as a piped install is."""
    dest = tmp_path / ODD / "flubnf"
    (dest / ".git").mkdir(parents=True)
    for d in layout:
        (dest / ".venv" / d).mkdir(parents=True)
    ctl, stub, home = tmp_path / "ctl", tmp_path / "bin", tmp_path / "home"
    ctl.mkdir()
    home.mkdir()
    (ctl / "rc").write_text(f"{engine_rc}\n")
    _exe(dest / "setup.sh", "exit 0\n")
    _exe(dest / "setup_engine.sh",
         f'echo "$PWD $*" >> "{ctl}/calls"\nexit "$(cat "{ctl}/rc")"\n')
    _exe(stub / "uname", f'echo "{system}"\n')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLUBNF_")}
    env.update({"HOME": str(home), "GIT_TERMINAL_PROMPT": "0",
                "GIT_CEILING_DIRECTORIES": str(tmp_path),
                "FLUBNF_DIR": str(dest), "FLUBNF_ENGINE": route,
                "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}"})
    out = subprocess.run([BASH, str(REPO / "install.sh")], env=env,
                         cwd=elsewhere, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=60)
    return out, dest, ctl, elsewhere, env


@POSIX
@pytest.mark.parametrize("system", ["Darwin", "Linux"])
@pytest.mark.parametrize("route, engine_rc, flags", [
    ("public", 1, ["--public"]),
    ("private", 1, ["--private"]),
    ("private", 0, ["--private", "--public"])])
def test_each_setup_engine_step_names_the_install_folder(
        tmp_path, system, route, engine_rc, flags):
    out, dest, ctl, elsewhere, env = _install(
        tmp_path, system=system, route=route, engine_rc=engine_rc)
    assert out.returncode == 0, out.stdout + out.stderr
    named = [ln for ln in out.stdout.splitlines() if "setup_engine.sh" in ln]
    want = [f'cd "{dest}" && ./setup_engine.sh {f}' for f in flags]
    assert [ln.strip() for ln in named] == want, out.stdout
    # each runs as printed, from the folder the install line was pasted in
    (ctl / "rc").write_text("0\n")
    (ctl / "calls").unlink()
    for ln in named:
        ran = subprocess.run([BASH, "-c", ln.strip()], env=env, cwd=elsewhere,
                             capture_output=True, text=True, timeout=60)
        assert ran.returncode == 0, ran.stdout + ran.stderr
    assert (ctl / "calls").read_text().splitlines() == [
        f"{dest} {f}" for f in flags]


@POSIX
@pytest.mark.parametrize("layout, folder", [
    (("Scripts",), "Scripts"), (("bin", "Scripts"), "bin"), ((), "bin")])
def test_the_closing_line_names_the_venv_folder_setup_used(tmp_path, layout,
                                                           folder):
    """setup.sh uses Scripts in a venv a Windows Python made (Git Bash)."""
    out, dest, *_ = _install(tmp_path, system="Linux", route="public",
                             engine_rc=0, layout=layout)
    assert out.returncode == 0, out.stdout + out.stderr
    done = [ln for ln in out.stdout.splitlines() if ln.startswith("Done.")]
    assert done == [f'Done. Launch with:  "{dest}/.venv/{folder}/flubnf" app']
