"""A hub clone git refuses to read, and setup.ps1's clone test (review of
#93 at d160002b, findings 4 and 6).

  * Finding 6: a real clone that git will not read because another
    account owns it (git's "dubious ownership": a hub another account or
    an administrator made, or one on some external drives) was called
    "not a git clone" by doctor and setup.sh, with "Move or rename it
    first". Both now name the ownership problem, show git's line, and
    give git's own fix, `git config --global --add safe.directory`, for
    the hub folder itself; nothing is moved, cloned or widened. A folder
    inside another account's clone is still no clone of its own.
  * Finding 4: setup.ps1 took any hub with a .git for a clone (`Test-Path
    $HubGit`): a hub with an empty or broken .git folder was "hub present"
    and had `git pull` and `sparse-checkout add` run in it, where git
    answers for any repository around the folder, and doctor's words on
    Windows ("not a git clone ... Run setup.ps1") did not match. It now
    asks git by doctor's rule, and has the ownership case too. Nothing
    runs PowerShell on this Mac: setup.ps1 is read as text, as the other
    setup.ps1 tests read it.

git is made to refuse a repository by GIT_TEST_ASSUME_DIFFERENT_OWNER,
git's own switch for testing this check (its message is the one a hub
another account owns gets). Every git command runs in repositories the
test made in tmp_path, with GIT_CEILING_DIRECTORIES there.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from flubnf import doctor, settings
from tests.test_hub_clone_check import (BASH, GIT, NOT_A_CLONE, POSIX, REPO,
                                        _env, _exe, _git, _repo, _worktree,
                                        needs_git)

OWNER = "GIT_TEST_ASSUME_DIFFERENT_OWNER"
SAFE = "git config --global --add safe.directory"


def _clone(tmp_path: Path) -> Path:
    """A sparse clone that holds none of the data folders."""
    up = _repo(tmp_path, "up", ("README.md", "model-output/a/x.csv"))
    hub = tmp_path / "hub"
    _git(tmp_path, "clone", "-q", "--sparse", str(up), str(hub))
    assert (hub / ".git").is_dir()
    return hub


def _empty_git_in_clone(tmp_path: Path) -> Path:
    """A folder with an empty .git folder inside another clone."""
    outer = _repo(tmp_path, "outer")
    hub = outer / "hub"
    (hub / ".git").mkdir(parents=True)
    (hub / "notes.txt").write_text("left here\n")
    return hub


def _refusal(hub: Path) -> str:
    """git's own words for the hub with the switch on (the test of the
    test: git refuses it, and names the hub)."""
    env = {**os.environ, OWNER: "1"}
    r = subprocess.run([GIT, "-C", str(hub), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode != 0
    return r.stderr


@pytest.fixture
def ceiling(tmp_path, monkeypatch):
    for k in [k for k in os.environ if k.startswith("GIT_")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)


def _real(p: Path) -> str:
    return str(Path(os.path.realpath(p)))


# --- doctor -----------------------------------------------------------------
@needs_git
@pytest.mark.parametrize("platform, step", [("darwin", "./setup.sh"),
                                            ("win32", "setup.ps1")])
@pytest.mark.parametrize("make", [_clone, _worktree])
def test_doctor_names_the_ownership_and_gits_fix(tmp_path, monkeypatch,
                                                 ceiling, platform, step,
                                                 make):
    hub = make(tmp_path)
    assert "safe.directory" in _refusal(hub)
    monkeypatch.setenv(OWNER, "1")
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub(platform)
    assert res.status is doctor.Status.FAIL
    assert "lacks target-data" in res.detail
    assert NOT_A_CLONE not in res.hint and "Move or rename" not in res.hint
    first, last = res.hint.rsplit("\n", 1)
    assert first.startswith(
        "git will not read this clone (detected dubious ownership in "
        f"repository at '{_real(hub)}'): the folder is not owned by your "
        "account"), first
    assert f"then run {step}: it makes or widens the sparse clone" in first
    # git's own step, whole, alone on the last line
    assert last == f'    {SAFE} "{_real(hub)}"'
    assert "sparse-checkout" not in res.hint


@needs_git
def test_doctor_with_the_folder_marked_safe_gives_the_git_step(
        tmp_path, monkeypatch, ceiling):
    """git's fix works: with the hub marked safe it reads the clone, and
    doctor gives the clone its usual step."""
    hub = _clone(tmp_path)
    cfg = tmp_path / "gitconfig"
    cfg.write_text(f"[safe]\n\tdirectory = {_real(hub)}\n")
    monkeypatch.setenv(OWNER, "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub("darwin")
    assert res.hint.splitlines()[-1].strip() == (
        f'git -C "{hub}" sparse-checkout add auxiliary-data target-data')


@needs_git
def test_doctor_a_folder_inside_a_refused_clone_is_still_no_clone(
        tmp_path, monkeypatch, ceiling):
    """git refuses the clone around it, not the folder: no safe.directory
    step for a folder that is no clone of its own."""
    hub = _empty_git_in_clone(tmp_path)
    assert f"'{_real(hub.parent)}'" in _refusal(hub)
    monkeypatch.setenv(OWNER, "1")
    monkeypatch.setattr(settings, "HUB", hub)
    res = doctor._check_hub("darwin")
    assert res.hint.startswith(f"The folder {NOT_A_CLONE}"), res.hint
    assert "safe.directory" not in res.hint
    assert doctor._git_refuses_owner(hub) == ("", "")


def test_doctor_reads_gits_quoted_folder(tmp_path, monkeypatch):
    """git quotes a folder whose name needs it ('...', with '\\'' for an
    apostrophe); the folder is read back whole, and only for the hub."""
    hub = tmp_path / "a hub's folder"
    (hub / ".git").mkdir(parents=True)
    quoted = "'" + str(hub).replace("'", "'\\''") + "'"
    said = (f"fatal: detected dubious ownership in repository at '{hub}'\n"
            "To add an exception for this directory, call:\n\n"
            f"\t{SAFE} {quoted}\n")

    def git(*a, **k):
        return subprocess.CompletedProcess(a[0], 128, "", said)
    monkeypatch.setattr(doctor.subprocess, "run", git)
    assert doctor._git_refuses_owner(hub) == (
        f"detected dubious ownership in repository at '{hub}'", str(hub))
    assert doctor._git_refuses_owner(tmp_path) == ("", "")   # no .git


# --- setup.sh ---------------------------------------------------------------
def _setup(tmp_path: Path, hub: Path, **extra) -> tuple:
    """setup.sh alone in a folder of its own, a venv already there, and
    stand-ins first on PATH: python3.12, and a git that logs each call and
    runs it with the real git, except `clone`, which fails."""
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
    env.update(extra)
    out = subprocess.run([BASH, str(repo / "setup.sh")], env=env,
                         cwd=tmp_path, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=180)
    log = ctl / "git.log"
    calls = log.read_text().splitlines() if log.exists() else []
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out.stdout)
    return out, calls, plain


def _flat(said: str) -> str:
    return " ".join(ln.strip().lstrip("!").strip()
                    for ln in said.splitlines())


@POSIX
@needs_git
@pytest.mark.parametrize("make", [_clone, _worktree])
def test_setup_names_the_ownership_and_gits_fix(tmp_path, make):
    hub = make(tmp_path)
    before = sorted(p.name for p in hub.iterdir())
    out, calls, said = _setup(tmp_path, hub, **{OWNER: "1"})
    assert out.returncode == 0, out.stdout + out.stderr
    flat = _flat(said)
    assert (f'git will not read the clone at "{hub}": the folder is not '
            "owned by your account") in flat, said
    assert ("git said: detected dubious ownership in repository at "
            f"'{_real(hub)}'") in flat, said
    assert ("If you trust it, let git read it with this line, then run "
            "./setup.sh again:") in flat
    # git's own step, whole, on its own line
    assert [ln.strip().lstrip("!").strip() for ln in said.splitlines()
            if SAFE in ln] == [f'{SAFE} "{_real(hub)}"']
    assert NOT_A_CLONE not in said and "Move or rename" not in said
    assert "hub present" not in said and "data fetch failed" not in said
    # nothing widened, cloned or moved
    assert not [c for c in calls if "sparse-checkout" in c], calls
    assert not [c for c in calls if c.startswith(("clone", "pull"))], calls
    assert sorted(p.name for p in hub.iterdir()) == before


@POSIX
@needs_git
def test_setup_reads_gits_refusal_in_another_language(tmp_path):
    """git's words follow the locale; its fix line does not, and the
    folder git names is the hub's either way."""
    hub = _clone(tmp_path)
    de = {OWNER: "1", "LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8",
          "LANGUAGE": "de"}
    probe = subprocess.run([GIT, "-C", str(hub), "rev-parse",
                            "--show-toplevel"], capture_output=True,
                           text=True, env={**_env(tmp_path), **de},
                           timeout=60)
    first = probe.stderr.splitlines()[0]
    if first.startswith("fatal: "):
        pytest.skip("this git speaks no German")
    out, calls, said = _setup(tmp_path, hub, **de)
    assert out.returncode == 0, out.stdout + out.stderr
    assert f"git said: {first}" in _flat(said), said
    assert [ln.strip().lstrip("!").strip() for ln in said.splitlines()
            if SAFE in ln] == [f'{SAFE} "{_real(hub)}"']
    assert NOT_A_CLONE not in said


@POSIX
@needs_git
def test_setup_a_folder_inside_a_refused_clone_is_still_no_clone(tmp_path):
    hub = _empty_git_in_clone(tmp_path)
    out, calls, said = _setup(tmp_path, hub, **{OWNER: "1"})
    assert out.returncode == 0, out.stdout + out.stderr
    assert f'"{hub}" {NOT_A_CLONE}, so no data was fetched into it.' in \
        _flat(said), said
    assert "safe.directory" not in said
    assert not [c for c in calls if "sparse-checkout" in c], calls


# --- setup.ps1 (read as text) -----------------------------------------------
PS1 = (REPO / "setup.ps1").read_text(encoding="utf-8")


def _hub_block() -> str:
    """The hub section, from its heading to the next one."""
    start = PS1.index('Say "FluSight hub data"')
    return PS1[start:PS1.index("\nSay ", start + 1)]


def _function(name: str) -> str:
    m = re.search(r"^function " + re.escape(name) + r" \{\n(.*?)^\}\n",
                  PS1, re.M | re.S)
    assert m, f"setup.ps1 has no {name}"
    return m.group(1)


def test_setup_ps1_no_longer_takes_any_dot_git_for_a_clone():
    block = _hub_block()
    branches = re.findall(r"^(?:if|\} elseif) \((.*)\) \{$", block, re.M)
    assert branches[:3] == ['$env:FLUBNF_NO_DATA -eq "1"',
                            '$HubState -eq "clone"',
                            '$HubState -eq "refused"'], branches
    assert "Test-Path $HubGit" not in block.split("git clone")[0]
    assert "$HubState = Get-HubGitState $Hub" in block


def test_setup_ps1_asks_git_by_doctors_rule():
    """A .git (folder or file) is asked about; git's top level must be the
    folder itself (--show-cdup blank); without git, a .git counts."""
    fn = _function("Get-HubGitState")
    assert 'Test-Path -LiteralPath (Join-Path $Hub ".git")' in fn
    assert re.search(r'if \(-not \(Get-Command git [^)]*\)\) '
                     r'\{ return "clone" \}', fn)
    assert '@("-C", $Hub, "rev-parse", "--show-cdup")' in fn
    assert re.search(r'-join ""\)\.Trim\(\) -eq ""\) \{ return "clone" \}',
                     fn)
    assert 'return "none"' in fn


def test_setup_ps1_names_the_ownership_and_gits_fix():
    fn = _function("Get-HubGitState")
    # git's own fix, the folder read back (quotes, %(prefix)/), and only
    # for the hub itself
    assert '"git config*safe.directory*"' in fn
    assert ".Replace(\"'\\''\", \"'\")" in fn
    assert 'StartsWith("%(prefix)/")' in fn and "Substring(10)" in fn
    assert len("%(prefix)/") == 10
    assert "if ($a -ne $b) { return \"none\" }" in fn
    block = _hub_block()
    refused = block[block.index('$HubState -eq "refused"'):
                    block.index("} elseif (Test-Path $Hub)")]
    assert "git will not read the clone at $($Hub)" in refused
    assert "the folder is not owned by" in refused
    assert "$HubGitSaid" in refused
    assert ('"    git config --global --add safe.directory '
            '`"$HubSafeDir`""') in refused
    for word in ("Invoke-Captured", "Move", "Remove-Item", "pull"):
        assert word not in refused, word


def test_setup_ps1_is_ascii():
    """Windows PowerShell reads a script without a BOM as the ANSI code
    page: the new lines are ASCII, like the rest."""
    assert all(ord(c) < 128 for c in PS1)
