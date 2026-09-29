"""The engine checkout follows the production build: both launchers run
`flubnf engine-update` on every open, which fast-forwards a clean checkout
on the production branch to exactly the production commit and leaves every
other checkout where it is, saying why. Real git repositories in temporary
folders; the "GitHub" remote is a bare repository beside them."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.core import engine_build as EB
from app.core import engine_update as EU

REPO = Path(__file__).resolve().parents[2]
BRANCH = "feature/particle-filter"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _commit(repo: Path, name: str, text: str) -> str:
    (repo / "pybnf" / name).write_text(text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def forge(tmp_path, monkeypatch):
    """A bare "GitHub" fork with three commits on the production branch:
    old, prod (the production build) and newer; a working copy `work` that
    pushes them. Returns (bare, work, {old, prod, newer})."""
    work = tmp_path / "upstream"
    (work / "pybnf").mkdir(parents=True)
    _git(work, "init", "-q", "-b", BRANCH)
    shas = {"old": _commit(work, "pf.py", "v = 1\n")}
    bare = tmp_path / "fork.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "origin", BRANCH)
    shas["prod"] = _commit(work, "pf.py", "v = 2\n")
    shas["newer"] = _commit(work, "pf.py", "v = 3\n")
    monkeypatch.setattr(EB, "PRODUCTION_ENGINE_COMMIT", shas["prod"][:8])
    monkeypatch.setattr(EB, "PRODUCTION_ENGINE_BRANCH", BRANCH)
    monkeypatch.setattr(EU, "STATE_FILE", tmp_path / "state" / "eu.json")
    return bare, work, shas


def _publish(work: Path, sha: str) -> None:
    _git(work, "push", "-q", "origin", f"{sha}:refs/heads/{BRANCH}")


def _clone(bare: Path, dest: Path, at: str | None = None) -> Path:
    subprocess.run(["git", "clone", "-q", "-b", BRANCH, str(bare), str(dest)],
                   check=True)
    if at:
        _git(dest, "reset", "-q", "--hard", at)
    return dest


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


# ------------------------------------------------------------- what moves
def test_an_old_clean_checkout_is_fetched_and_moved_to_production(
        forge, tmp_path):
    bare, work, shas = forge
    eng = _clone(bare, tmp_path / "PyBNF-pf")          # holds only "old"
    _publish(work, shas["newer"])                      # GitHub moved on
    out = EU.update(eng)
    assert out["status"] == "updated", out
    # exactly the production commit, never past it
    assert _head(eng) == shas["prod"]
    assert _git(eng, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert out["before"] == shas["old"][:8] and out["after"] == shas["prod"][:8]
    assert EB.is_production(EB.engine_build(eng))
    # a second open has nothing to do
    assert EU.update(eng)["status"] == "production"


def test_a_commit_already_on_disk_needs_no_network(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    _git(eng, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    out = EU.update(eng)
    assert out["status"] == "updated" and _head(eng) == shas["prod"]


def test_without_network_the_checkout_stays_and_says_why(forge, tmp_path):
    bare, work, shas = forge
    eng = _clone(bare, tmp_path / "PyBNF-pf")
    _publish(work, shas["newer"])
    _git(eng, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    out = EU.update(eng)
    assert out["status"] == "unreachable", out
    assert _head(eng) == shas["old"]
    assert out["message"].startswith(f"left at {shas['old'][:8]}: could not "
                                     f"fetch {BRANCH} from GitHub (")


def test_no_fetch_leaves_a_missing_commit_alone(forge, tmp_path):
    bare, work, shas = forge
    eng = _clone(bare, tmp_path / "PyBNF-pf")
    _publish(work, shas["newer"])
    out = EU.update(eng, fetch=False)
    assert out["status"] == "missing" and _head(eng) == shas["old"]


def test_a_branch_on_github_without_the_production_commit(forge, tmp_path):
    bare, _, shas = forge
    eng = _clone(bare, tmp_path / "PyBNF-pf")          # GitHub holds "old"
    out = EU.update(eng)
    assert out["status"] == "missing" and _head(eng) == shas["old"]
    assert "does not hold the production build" in out["message"]


# ------------------------------------------------------- what is left alone
def test_local_edits_are_never_touched(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    (eng / "pybnf" / "pf.py").write_text("v = 'mine'\n")
    out = EU.update(eng)
    assert out["status"] == "edited" and _head(eng) == shas["old"]
    assert (eng / "pybnf" / "pf.py").read_text() == "v = 'mine'\n"


def test_untracked_files_do_not_count_as_edits(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    (eng / "notes.txt").write_text("scratch\n")
    assert EU.update(eng)["status"] == "updated"
    assert (eng / "notes.txt").read_text() == "scratch\n"


def test_another_branch_is_a_research_build_and_stays(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    _git(eng, "checkout", "-q", "-b", "feature/bngsim")
    out = EU.update(eng)
    assert out["status"] == "branch" and _head(eng) == shas["old"]
    assert "on the branch feature/bngsim, not feature/particle-filter" \
        in out["message"]


def test_a_detached_head_stays(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf")
    _git(eng, "checkout", "-q", "--detach", shas["old"])
    out = EU.update(eng)
    assert out["status"] == "branch" and "a detached HEAD" in out["message"]
    assert _head(eng) == shas["old"]


def test_a_checkout_past_production_is_never_moved_back(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf")          # at "newer"
    out = EU.update(eng)
    assert out["status"] == "ahead" and _head(eng) == shas["newer"]


def test_local_commits_off_the_line_stay(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    mine = _commit(eng, "mine.py", "x = 1\n")
    out = EU.update(eng)
    assert out["status"] == "diverged" and _head(eng) == mine


def test_an_untracked_file_in_the_way_fails_without_harm(forge, tmp_path,
                                                         monkeypatch):
    bare, work, shas = forge
    _git(work, "checkout", "-q", shas["prod"])
    prod2 = _commit(work, "added.py", "y = 1\n")       # adds a file
    _git(work, "checkout", "-q", BRANCH)
    _publish(work, prod2)
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    (eng / "pybnf" / "added.py").write_text("my own\n")
    monkeypatch.setattr(EB, "PRODUCTION_ENGINE_COMMIT", prod2[:8])
    out = EU.update(eng)
    assert out["status"] == "failed", out
    assert _head(eng) == shas["old"]
    assert (eng / "pybnf" / "added.py").read_text() == "my own\n"


def test_an_unpacked_archive_and_no_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(EB, "PRODUCTION_ENGINE_COMMIT", "2fdadee0")
    d = tmp_path / "PyBNF-Private"
    (d / "pybnf").mkdir(parents=True)
    (d / "VERSION").write_text(f"{BRANCH} 1234abcd\n")
    out = EU.update(d)
    assert out["status"] == "archive"
    assert "pybnf-pf-2fdadee0.tar.gz" in out["message"]
    (d / "VERSION").write_text(f"{BRANCH} 2fdadee0\n")
    assert EU.update(d)["status"] == "production"
    assert EU.update(tmp_path / "nowhere")["status"] == "no-engine"


def test_a_checkout_git_cannot_read_is_named(tmp_path):
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)                   # not a repository
    out = EU.update(d)
    assert out["status"] == "unreadable"
    assert out["message"].startswith("git cannot read this checkout: ")


# ------------------------------------------------ the reason, where it shows
def test_the_reason_reaches_the_build_warning(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    _git(eng, "checkout", "-q", "-b", "feature/bngsim")
    EU.save(EU.update(eng))
    b = EB.engine_build(eng)
    note = EU.last_note(b)
    assert note == ("FluBNF tried to update it when it opened: left at "
                    f"{shas['old'][:8]}: it is on the branch feature/bngsim, "
                    "not feature/particle-filter.")
    # another checkout, or the same one at another commit: nothing to add
    assert EU.last_note(dict(b, path=str(tmp_path / "other"))) == ""
    assert EU.last_note(dict(b, commit="deadbeef")) == ""


def test_an_update_that_worked_adds_nothing(forge, tmp_path):
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    EU.save(EU.update(eng))
    assert EU.load()["status"] == "updated"
    assert EU.last_note(EB.engine_build(eng)) == ""


def test_the_console_warning_carries_the_reason(forge, tmp_path, monkeypatch):
    from app.ui import versions as V
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    (eng / "pybnf" / "pf.py").write_text("v = 'mine'\n")
    EU.save(EU.update(eng))
    saved = dict(V.ENGINE_BUILD)
    try:
        V.ENGINE_BUILD.clear()
        V.ENGINE_BUILD.update(EB.engine_build(eng))
        view = V.engine_build_view()
    finally:
        V.ENGINE_BUILD.clear()
        V.ENGINE_BUILD.update(saved)
    assert view["fix"].startswith(
        "FluBNF tried to update it when it opened: left at "
        f"{shas['old'][:8]}: tracked files have local edits")
    assert "git stash" in view["fix"]


def test_the_command_prints_the_outcome_and_saves_it(forge, tmp_path):
    from flubnf.cli import app
    bare, work, shas = forge
    _publish(work, shas["newer"])
    eng = _clone(bare, tmp_path / "PyBNF-pf", at=shas["old"])
    r = CliRunner().invoke(app, ["engine-update", "--path", str(eng)])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == (f"engine: updated from {shas['old'][:8]} to "
                                f"the production build {shas['prod'][:8]}")
    assert EU.load()["status"] == "updated"
    # quiet when there is nothing to say
    r = CliRunner().invoke(app, ["engine-update", "--quiet", "--path",
                                 str(eng)])
    assert r.exit_code == 0 and r.output == ""


def test_the_command_never_fails_a_launch(forge, tmp_path):
    from flubnf.cli import app
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)
    r = CliRunner().invoke(app, ["engine-update", "--quiet", "--path",
                                 str(d)])
    assert r.exit_code == 0
    assert r.output.startswith("  engine: git cannot read this checkout")


# ------------------------------------------------------------ the launchers
def test_both_launchers_run_it_on_every_open():
    bat = (REPO / "FluBNF.bat").read_text(encoding="ascii")
    lines = bat.splitlines()
    call = ('".venv\\Scripts\\flubnf.exe" engine-update --quiet --path '
            '"%PYBNFDIR%"')
    assert call in lines
    # after the checkout is chosen, before the import probe checks it
    assert lines.index(":pybnfresolved") < lines.index(call) \
        < lines.index(":engineupdated") \
        < next(i for i, ln in enumerate(lines) if "from pybnf.pf import" in ln)
    block = lines[lines.index(":pybnfresolved"):lines.index(":engineupdated")]
    assert 'if /I "%FLUBNF_UPDATE%"=="off" goto :engineupdated' in block
    assert 'if not exist "%PYBNFDIR%\\.git" goto :engineupdated' in block

    cmd = (REPO / "FluBNF.command").read_text(encoding="utf-8")
    at = cmd.index(".venv/bin/flubnf engine-update --quiet || true")
    assert cmd.rindex('"${FLUBNF_UPDATE:-}" != "off"', 0, at) > \
        cmd.index('PF engine not installed yet')
    # before a prepare-only open returns, so the Dock app gets it too
    assert at < cmd.index('if [ -n "$PREPARE" ]; then')


# ------------------------------------------------------------ the fix text
def test_the_fix_names_this_machines_launcher():
    arch = {"branch": BRANCH, "commit": "1234abcd", "dirty": False,
            "source": "archive", "path": "C:\\x"}
    assert "FluBNF.bat" in EB.fix(arch, platform="win32")
    assert "setup_engine.sh" not in EB.fix(arch, platform="win32")
    assert "./setup_engine.sh" in EB.fix(arch, platform="darwin")
    git = dict(arch, source="git",
               path="C:\\Users\\Ely Miller\\AppData\\Local\\FluBNF\\PyBNF-pf")
    text = EB.fix(git, platform="win32")
    # quoted: a profile folder can hold a space
    assert ('git -C "C:\\Users\\Ely Miller\\AppData\\Local\\FluBNF\\PyBNF-pf"'
            f" checkout {BRANCH}") in text
    assert text.startswith(f"FluBNF moves a clean checkout on {BRANCH} to "
                           "this build each time it opens.")
