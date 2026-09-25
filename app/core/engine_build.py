"""Which particle-filter engine build this machine runs.

The engine is a checkout of the private PyBNF fork at flubnf.settings.PYBNF.
engine_build() names its branch and commit (from git, or from the VERSION
stamp an archive install carries), and whether tracked files have local
edits. is_production() compares it with the season's production build,
defined once here. Every function is cheap to call wrong: none raises.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

#: the production engine for the 2026-27 season (docs/ORACLE-SIHRS.md,
#: "Engine line-up"); the commit decides, the branch is informative
PRODUCTION_ENGINE_COMMIT = "2fdadee0"
PRODUCTION_ENGINE_BRANCH = "feature/particle-filter"

#: per git call; a hung git (network filesystem, lock) must not hold a page
GIT_TIMEOUT_S = 3.0


def _git(path: Path, *args: str) -> tuple[int, str]:
    """(returncode, stdout) of `git -C path args`; (-1, "") on any error."""
    try:
        r = subprocess.run(["git", "-C", str(path), *args],
                           capture_output=True, text=True,
                           timeout=GIT_TIMEOUT_S)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return -1, ""


def _from_version_file(path: Path) -> dict | None:
    """{branch, commit} from an archive's VERSION stamp, whose first line
    is "<ref> <sha>" (scripts/cut_engine_archive.sh); None without one."""
    vf = path / "VERSION"
    try:
        first = vf.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except Exception:
        return None
    parts = first.split()
    if not parts:
        return None
    if len(parts) == 1:
        return {"branch": "", "commit": parts[0][:8]}
    return {"branch": parts[0], "commit": parts[1][:8]}


def engine_build(path=None) -> dict:
    """The engine's build: {branch, commit (8 characters), dirty (tracked
    files edited), source ("git" | "archive" | "unknown"), path}. A detached
    HEAD has branch "". Never raises; an unreadable engine is "unknown"."""
    if path is None:
        try:
            from flubnf import settings
            path = settings.PYBNF
        except Exception:
            path = ""
    p = Path(path) if path else Path("")
    out = {"branch": "", "commit": "", "dirty": False, "source": "unknown",
           "path": str(p) if path else ""}
    try:
        if not path or not p.is_dir():
            return out
    except Exception:
        return out
    if (p / ".git").exists():
        rc, top = _git(p, "rev-parse", "--show-toplevel")
        rc2, sha = _git(p, "rev-parse", "HEAD")
        same = False
        try:
            same = rc == 0 and Path(top).resolve() == p.resolve()
        except Exception:
            pass
        if same and rc2 == 0 and sha:
            out["source"] = "git"
            out["commit"] = sha[:8]
            rc, br = _git(p, "symbolic-ref", "--short", "-q", "HEAD")
            out["branch"] = br if rc == 0 else ""
            rc, st = _git(p, "status", "--porcelain", "--untracked-files=no")
            # an unreadable status is reported as edited: never "production"
            # on a check that did not run
            out["dirty"] = bool(st) if rc == 0 else True
            return out
    stamp = _from_version_file(p)
    if stamp and stamp["commit"]:
        out.update(stamp)
        out["source"] = "archive"
    return out


def is_production(build: dict | None) -> bool:
    """True when the build is the production commit with no local edits
    (commit prefix match; the branch is informative only)."""
    b = build or {}
    c = str(b.get("commit") or "").lower()
    if not c or b.get("dirty"):
        return False
    n = min(len(c), len(PRODUCTION_ENGINE_COMMIT))
    return n >= 7 and c[:n] == PRODUCTION_ENGINE_COMMIT[:n].lower()


def known(build: dict | None) -> bool:
    """Whether a build names a commit at all (an engine was found)."""
    return bool((build or {}).get("commit"))


def label(build: dict | None) -> str:
    """"2fdadee0 (feature/particle-filter)", plus ", local changes" when
    edited; "" when unknown. A detached HEAD shows the commit alone."""
    b = build or {}
    if not known(b):
        return ""
    s = str(b["commit"])
    bits = [x for x in (str(b.get("branch") or ""),
                        "local changes" if b.get("dirty") else "") if x]
    return f"{s} ({', '.join(bits)})" if bits else s


def recorded_label(build) -> str:
    """A run's recorded build as its settings list names it: label(), plus
    ", not the production build" when it is not; "" when none recorded."""
    if not isinstance(build, dict) or not known(build):
        return ""
    lab = label(build)
    return lab if is_production(build) else lab + ", not the production build"


def warning(build: dict | None) -> str:
    """The one-line warning for a known non-production build; "" otherwise."""
    b = build or {}
    if not known(b) or is_production(b):
        return ""
    where = str(b.get("branch") or "a detached HEAD")
    s = (f"The engine is {where} at {b['commit']}, not the production build "
         f"{PRODUCTION_ENGINE_COMMIT} on {PRODUCTION_ENGINE_BRANCH}")
    if b.get("dirty"):
        s += ", and has local changes"
    return s + "."


def fix(build: dict | None) -> str:
    """How to switch to the production build, in plain words."""
    b = build or {}
    path = str(b.get("path") or "<engine folder>")
    if b.get("source") == "archive":
        return (f"This engine was installed from an archive. Save "
                f"pybnf-pf-{PRODUCTION_ENGINE_COMMIT}.tar.gz in Downloads and "
                "run ./setup_engine.sh to replace it.")
    # the path once: in a tip it is the longest word by far
    stash = ("stash the local edits first (git stash in that folder), then "
             if b.get("dirty") else "")
    return (f"To switch: {stash}git -C {path} checkout "
            f"{PRODUCTION_ENGINE_BRANCH}, then git pull there. Research runs "
            "may use other builds on purpose.")


def record(build: dict | None) -> dict:
    """The build as a run records it ({branch, commit, dirty, source}; no
    machine path); {} when unknown."""
    b = build or {}
    if not known(b):
        return {}
    return {"branch": str(b.get("branch") or ""), "commit": str(b["commit"]),
            "dirty": bool(b.get("dirty")),
            "source": str(b.get("source") or "unknown")}


def change(prior: dict | None, now: dict | None) -> str | None:
    """None when a resume over `now` keeps the recorded build (commit and
    edited state) or none was recorded; else the difference in plain words."""
    if not isinstance(prior, dict) or not known(prior):
        return None
    p, n = record(prior), record(now)
    if n and p["commit"][:8] == n["commit"][:8] and p["dirty"] == n["dirty"]:
        return None
    had = label(p)
    return (f"were fitted by engine {had}; this machine's engine is "
            f"{label(n) if n else 'not found'}")
