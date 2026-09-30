"""Bring the particle-filter engine checkout up to the production build.

FluBNF updates itself each time it opens (FluBNF.command, FluBNF.bat), but
the engine is a separate private checkout that nothing moved: a machine that
cloned it months ago kept that build, and the console's warning said so with
no way out but git by hand. update() is that way out. Both launchers run it
on every open (`flubnf engine-update`), and it is safe to run anywhere:

  * only a git checkout that is clean (no edits to tracked files), on the
    production branch, and behind the production commit moves;
  * it moves by fast-forward to exactly PRODUCTION_ENGINE_COMMIT, never past
    it and never by a reset, so nothing on disk is lost;
  * anything else (another branch, local edits, commits past production, an
    unpacked archive) is left as it is, and the reason is said: research
    runs may use other builds on purpose;
  * the network is used only when the commit is not on disk yet, with every
    prompt off and a time limit, so a machine without GitHub access opens as
    fast as before.

The last outcome is kept in app/state/engine_update.json, so the console's
build warning can say why the engine was left where it is (last_note).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from app.core import engine_build as _eb

#: where the last outcome is kept (app/state is gitignored)
STATE_FILE = Path(__file__).resolve().parents[1] / "state" / "engine_update.json"

#: a git call that reads the checkout; a fetch gets FETCH_TIMEOUT_S
GIT_TIMEOUT_S = 15.0
#: the one network call; a machine without access must not hold the launch
FETCH_TIMEOUT_S = 30.0

#: outcomes that leave the engine where it was, by choice or by necessity
LEFT = ("no-engine", "archive", "unreadable", "edited", "branch", "ahead",
        "diverged", "unreachable", "missing", "failed")


def _git_env() -> dict:
    """git with every prompt off: no terminal question, no credential
    window (Git Credential Manager answers from its cache or not at all),
    ssh in batch mode with a connect limit."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env.setdefault("GIT_SSH_COMMAND",
                   "ssh -o BatchMode=yes -o ConnectTimeout=10")
    return env


def _run(path: Path, *args: str, timeout: float = GIT_TIMEOUT_S):
    """(returncode, stdout, stderr) of `git -C path args`; (-1, "", why) when
    git is missing or runs past `timeout`. No console window on Windows."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "-c", "credential.interactive=false",
             *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, env=_git_env(), **kw)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"git did not answer within {timeout:g} s"
    except FileNotFoundError:
        return -1, "", "git is not installed or not on PATH"
    except Exception as e:                      # pragma: no cover
        return -1, "", f"{type(e).__name__}: {e}"


#: git's reason, one line (the build warning reads git's the same way)
_first_line = _eb.first_line


def _outcome(status: str, message: str, path, before: str = "",
             after: str = "") -> dict:
    return {"status": status, "message": message, "path": str(path or ""),
            "before": before, "after": after,
            "production": _eb.PRODUCTION_ENGINE_COMMIT,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def update(path=None, fetch: bool = True,
           fetch_timeout: float = FETCH_TIMEOUT_S) -> dict:
    """Move the engine checkout at `path` (settings.PYBNF by default) to the
    production build when that is safe, else leave it and say why.

    Returns {status, message, path, before, after, production, at}; status
    is "production" (already there), "updated", or one of LEFT. Never
    raises."""
    try:
        return _update(path, fetch, fetch_timeout)
    except Exception as e:                      # pragma: no cover
        return _outcome("failed", f"{type(e).__name__}: {e}", path)


def _update(path, fetch: bool, fetch_timeout: float) -> dict:
    if path is None:
        from flubnf import settings
        path = settings.PYBNF
    p = Path(path)
    want = _eb.PRODUCTION_ENGINE_COMMIT
    branch = _eb.PRODUCTION_ENGINE_BRANCH
    if not p.is_dir():
        return _outcome("no-engine", f"no engine at {p}", p)
    if not (p / ".git").exists():
        b = _eb.engine_build(p)
        if _eb.is_production(b):
            return _outcome("production", f"the production build {want}", p,
                            b["commit"], b["commit"])
        return _outcome(
            "archive",
            "an unpacked engine archive, which git cannot update: to "
            f"replace it, {_eb.archive_step()}", p, b.get("commit", ""))

    rc, head, err = _run(p, "rev-parse", "--verify", "HEAD")
    if rc != 0 or not head:
        return _outcome("unreadable",
                        "git cannot read this checkout: "
                        + (_first_line(err) or f"exit {rc}"), p)
    before = head[:8]
    rc, cur, _ = _run(p, "symbolic-ref", "--short", "-q", "HEAD")
    cur = cur if rc == 0 else ""
    rc, st, err = _run(p, "status", "--porcelain", "--untracked-files=no")
    if rc != 0:
        return _outcome("unreadable",
                        "git cannot read this checkout's status: "
                        + (_first_line(err) or f"exit {rc}"), p, before)

    rc, full, _ = _run(p, "rev-parse", "--verify", "--quiet",
                       f"{want}^{{commit}}")
    if rc == 0 and full and head == full and not st:
        return _outcome("production", f"the production build {want}", p,
                        before, before)
    if st:
        return _outcome(
            "edited",
            f"left at {before}: tracked files have local edits (git status "
            "in that folder lists them)", p, before)
    if cur != branch:
        on = f"the branch {cur}" if cur else "a detached HEAD"
        return _outcome(
            "branch",
            f"left at {before}: it is on {on}, not {branch}", p, before)

    if not (rc == 0 and full):
        if not fetch:
            return _outcome("missing",
                            f"the production build {want} is not on disk "
                            "yet (not fetched)", p, before)
        frc, _, ferr = _run(
            p, "fetch", "--quiet", "--no-tags", "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            timeout=fetch_timeout)
        if frc != 0:
            return _outcome(
                "unreachable",
                f"left at {before}: could not fetch {branch} from GitHub ("
                + (_first_line(ferr) or f"exit {frc}") + ")", p, before)
        rc, full, _ = _run(p, "rev-parse", "--verify", "--quiet",
                           f"{want}^{{commit}}")
        if rc != 0 or not full:
            return _outcome(
                "missing",
                f"left at {before}: {branch} on GitHub does not hold the "
                f"production build {want}", p, before)

    # behind (HEAD is an ancestor of production): the only case that moves
    rc, _, _ = _run(p, "merge-base", "--is-ancestor", "HEAD", full)
    if rc != 0:
        rc2, _, _ = _run(p, "merge-base", "--is-ancestor", full, "HEAD")
        if rc2 == 0:
            return _outcome(
                "ahead",
                f"left at {before}: it already holds the production build "
                f"{want} and has newer commits", p, before)
        return _outcome(
            "diverged",
            f"left at {before}: its history does not lead to the production "
            f"build {want}", p, before)
    rc, _, err = _run(p, "merge", "--ff-only", "--quiet", full)
    if rc != 0:
        return _outcome(
            "failed",
            f"left at {before}: git could not fast-forward ("
            + (_first_line(err) or f"exit {rc}") + ")", p, before)
    return _outcome("updated",
                    f"updated from {before} to the production build {want}",
                    p, before, full[:8])


def save(outcome: dict, state_file: Path | None = None) -> None:
    """Keep the outcome for the console (last_note). Never raises."""
    f = Path(state_file or STATE_FILE)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(outcome, indent=1), encoding="utf-8")
        os.replace(tmp, f)
    except Exception:
        pass


def load(state_file: Path | None = None) -> dict:
    """The last saved outcome, {} without one. Never raises."""
    try:
        d = json.loads(Path(state_file or STATE_FILE)
                       .read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def last_note(build: dict | None, state_file: Path | None = None) -> str:
    """Why the last open left this engine where it is, as a sentence for the
    build warning; "" when there is nothing to add (no outcome, another
    checkout or build than the one shown, or it moved). Only for a git
    checkout at the commit the update saw: for an unpacked archive or a
    folder git cannot read, the warning and its fix already say why, in
    this machine's words."""
    b = build or {}
    o = load(state_file)
    if not o or o.get("status") not in LEFT or b.get("source") != "git":
        return ""
    try:
        if Path(o.get("path") or "").resolve() != Path(b.get("path") or "")\
                .resolve():
            return ""
    except Exception:
        return ""
    if not o.get("before") or \
            str(b.get("commit") or "")[:8] != o["before"][:8]:
        return ""
    msg = str(o.get("message") or "").strip()
    return f"FluBNF tried to update it when it opened: {msg}." if msg else ""
