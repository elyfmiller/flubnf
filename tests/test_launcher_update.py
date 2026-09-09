"""The launcher's self-update block, exercised on real clones.

The block used to be two lines and one message, "offline or local changes,
running as-is", which names two causes with opposite remedies and does not
say which one happened. A PI's laptop can sit on a month old console that
way while the engine beside it is current, and nothing on screen says so.
These tests pin the four outcomes apart.

The block is sliced out of FluBNF.command rather than reimplemented, so a
test cannot pass against a launcher that no longer contains it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "FluBNF.command"
START = "# Stay current (lab-share mode)."
END = "# Dependency refresh policy"

posix_only = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="FluBNF.command is the macOS and Linux launcher; Windows has the .bat")


def _update_block() -> str:
    text = LAUNCHER.read_text()
    assert START in text and END in text, (
        "the self-update block moved or was renamed in FluBNF.command; this "
        "test slices it out by those two comments")
    body = text.split(START, 1)[1].split(END, 1)[0]
    return "set -u\n" + START + body


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, text=True,
                          capture_output=True, check=True)


def _origin_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin one commit ahead of a clone, both on main."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "-c", "init.defaultBranch=main", "init", "-q", ".")
    (work / "app.py").write_text("v1\n")
    _git(work, "add", "app.py")
    _git(work, "commit", "-qm", "v1")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(origin))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    (work / "app.py").write_text("v2\n")            # origin moves ahead
    _git(work, "commit", "-qam", "v2")
    _git(work, "push", "-q", str(origin), "main")
    return origin, clone


def _run_block(clone: Path, **env_extra) -> subprocess.CompletedProcess:
    script = clone.parent / "update-block.sh"
    script.write_text(_update_block())
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    env.pop("FLUBNF_UPDATE", None)
    env.update({k: str(v) for k, v in env_extra.items()})
    return subprocess.run(["bash", str(script)], cwd=clone, env=env,
                          text=True, capture_output=True, timeout=120)


@posix_only
def test_a_clean_clone_fast_forwards(tmp_path):
    _, clone = _origin_and_clone(tmp_path)
    out = _run_block(clone)
    assert "up to date with origin" in out.stdout, out.stdout + out.stderr
    assert (clone / "app.py").read_text() == "v2\n"


@posix_only
def test_a_stray_edit_is_stashed_and_the_update_goes_through(tmp_path):
    """The lab case: someone saved over a tracked file by accident and the
    machine has been running an old console ever since. The edit is not this
    script's to destroy, so it goes to the stash and the update proceeds."""
    _, clone = _origin_and_clone(tmp_path)
    (clone / "app.py").write_text("someone edited this\n")

    out = _run_block(clone)

    assert (clone / "app.py").read_text() == "v2\n", (
        "the update did not go through\n" + out.stdout + out.stderr)
    assert "local edits are blocking the update" in out.stdout
    assert "app.py" in out.stdout, "the reader is not told which file"
    stashed = subprocess.run(["git", "stash", "list"], cwd=clone, text=True,
                             capture_output=True).stdout
    assert "FluBNF update" in stashed, "the edit was destroyed, not set aside"


@posix_only
def test_local_commits_are_never_discarded(tmp_path):
    """A clone with real work on it is not the launcher's to reset. It says
    so, names the count, prints the command, and changes nothing."""
    _, clone = _origin_and_clone(tmp_path)
    (clone / "mine.py").write_text("work in progress\n")
    _git(clone, "add", "mine.py")
    _git(clone, "commit", "-qm", "mine")
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()

    out = _run_block(clone)

    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == head, (
        "a local commit was discarded")
    assert "1 commit(s) origin does not" in out.stdout, out.stdout + out.stderr
    assert "reset --hard" in out.stdout, "no recovery command was offered"


@posix_only
def test_force_takes_origins_copy(tmp_path):
    """FLUBNF_UPDATE=force is the answer to 'just make this machine match the
    lab'. It is the one path that discards local commits, and only when it is
    asked for by name."""
    _, clone = _origin_and_clone(tmp_path)
    (clone / "mine.py").write_text("work in progress\n")
    _git(clone, "add", "mine.py")
    _git(clone, "commit", "-qm", "mine")

    out = _run_block(clone, FLUBNF_UPDATE="force")

    assert (clone / "app.py").read_text() == "v2\n", out.stdout + out.stderr
    assert not (clone / "mine.py").exists(), "force did not take origin's copy"
    assert "forced to" in out.stdout


@posix_only
def test_off_skips_the_update_entirely(tmp_path):
    _, clone = _origin_and_clone(tmp_path)
    out = _run_block(clone, FLUBNF_UPDATE="off")
    assert out.stdout.strip() == "", out.stdout
    assert (clone / "app.py").read_text() == "v1\n", "it updated anyway"


@posix_only
def test_an_unreachable_origin_says_offline_not_local_changes(tmp_path):
    """The other half of the old message. Offline and local changes have
    opposite remedies, so they cannot share one line."""
    _, clone = _origin_and_clone(tmp_path)
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    out = _run_block(clone)

    assert "offline" in out.stdout, out.stdout + out.stderr
    assert (clone / "app.py").read_text() == "v1\n"
