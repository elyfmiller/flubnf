"""Which particle-filter engine build this machine runs.

The engine is a checkout of the private PyBNF fork at flubnf.settings.PYBNF.
engine_build() names its branch and commit (from git, or from the VERSION
stamp an archive install carries), and whether tracked files have local
edits. is_production() compares it with the season's production build,
defined once here, and fix() says how to reach it with this machine's
launcher. archive_step() is the one wording for installing the engine from
its archive, shared by the run errors and doctor. Every function is cheap
to call wrong: none raises.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

#: the production engine for the 2026-27 season (docs/ORACLE-SIHRS.md,
#: "Engine line-up"); the commit decides, the branch is informative
PRODUCTION_ENGINE_COMMIT = "2fdadee0"
PRODUCTION_ENGINE_BRANCH = "feature/particle-filter"

#: per git call; a hung git (network filesystem, lock) must not hold a page
GIT_TIMEOUT_S = 3.0
#: git status alone: it refreshes the index first, which on a large checkout
#: with a cold cache or a virus scanner (Windows Defender) takes seconds, and
#: a status that did not answer counts as local edits
STATUS_TIMEOUT_S = 10.0

#: the reason when git itself cannot be started
NO_GIT = "git is not installed or not on PATH"


def _git(path: Path, *args: str,
         timeout: float = GIT_TIMEOUT_S) -> tuple[int, str, str]:
    """(returncode, stdout, stderr) of `git -C path args`; -1 with the reason
    in place of stderr when git is missing or does not answer in time. No
    console window on Windows."""
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(["git", "-C", str(path), *args],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, **kw)
        return (r.returncode, (r.stdout or "").strip(),
                (r.stderr or "").strip())
    except FileNotFoundError:
        return -1, "", NO_GIT
    except subprocess.TimeoutExpired:
        return -1, "", f"git did not answer within {timeout:g} s"
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {e}"


def first_line(text: str) -> str:
    """git's reason, one line: the first line that says something."""
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if ln and not ln.lower().startswith("hint:"):
            return ln[:200]
    return ""


def _safe_directory_line(err: str) -> str:
    """git's own `git config --global --add safe.directory <path>` from its
    "dubious ownership" refusal (a folder another account owns: an engine
    cloned from an elevated window, a USB or network drive); "" without
    one. It spells the path the way git accepts it."""
    for ln in (err or "").splitlines():
        ln = ln.strip()
        if ln.startswith("git config") and "safe.directory" in ln:
            return ln
    return ""


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


def _unreadable(out: dict, err: str, rc: int) -> dict:
    """The build of a checkout git would not read: git's reason, and its
    safe.directory command when it gave one."""
    out["source"] = "unreadable"
    out["error"] = first_line(err) or f"git exited with {rc}"
    cmd = _safe_directory_line(err)
    if cmd:
        out["safe_directory"] = cmd
    return out


def engine_build(path=None) -> dict:
    """The engine's build: {branch, commit (8 characters), dirty (tracked
    files edited), source ("git" | "archive" | "unreadable" | "unknown"),
    path}. A detached HEAD has branch "". A folder with .git that git will
    not read (git missing, "dubious ownership", no answer) is "unreadable"
    and adds error (git's reason) and, when git named one, safe_directory:
    never the VERSION stamp, which a checkout does not carry. Never raises;
    a folder that is neither checkout nor archive is "unknown"."""
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
        checkout = (p / ".git").exists()
    except Exception:
        return out
    if checkout:
        rc, top, err = _git(p, "rev-parse", "--show-toplevel")
        if rc != 0:
            return _unreadable(out, err, rc)
        rc, sha, err = _git(p, "rev-parse", "HEAD")
        if rc != 0 or not sha:
            return _unreadable(out, err, rc)
        same = False
        try:
            same = Path(top).resolve() == p.resolve()
        except Exception:
            pass
        if same:
            out["source"] = "git"
            out["commit"] = sha[:8]
            rc, br, _ = _git(p, "symbolic-ref", "--short", "-q", "HEAD")
            out["branch"] = br if rc == 0 else ""
            # asked twice before a status that did not answer is reported
            # as edited: never "production" on a check that did not run,
            # but one slow read is not enough to call it edited
            for _attempt in range(2):
                rc, st, _ = _git(p, "status", "--porcelain",
                                 "--untracked-files=no",
                                 timeout=STATUS_TIMEOUT_S)
                if rc == 0:
                    break
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
    """The one-line warning for a known non-production build, or for a
    checkout git could not read; "" otherwise."""
    b = build or {}
    if b.get("source") == "unreadable":
        where = b.get("path") or "the engine folder"
        why = str(b.get("error") or "no reason given")
        if why.lower().startswith("fatal: "):
            why = why[len("fatal: "):]
        return f"git could not read {where}: {why.rstrip('.')}."
    if not known(b) or is_production(b):
        return ""
    where = str(b.get("branch") or "a detached HEAD")
    s = (f"The engine is {where} at {b['commit']}, not the production build "
         f"{PRODUCTION_ENGINE_COMMIT} on {PRODUCTION_ENGINE_BRANCH}")
    if b.get("dirty"):
        s += ", and has local changes"
    return s + "."


def archive_name() -> str:
    """The production engine's archive, as the lab hands it out
    (scripts/cut_engine_archive.sh)."""
    return f"pybnf-pf-{PRODUCTION_ENGINE_COMMIT}.tar.gz"


def setup_step(platform: str | None = None) -> str:
    """This machine's engine installer, as a clause: FluBNF.bat on Windows
    (no bash there, and setup.ps1 only diagnoses), SetupEngine.command
    beside the script on macOS, the script elsewhere; the folder is named
    so no full stop lands on the command. `platform` is sys.platform by
    default; tests pass one."""
    plat = platform or sys.platform
    if plat == "win32":
        return "open FluBNF.bat again"
    if plat == "darwin":
        return ("double-click SetupEngine.command in the FluBNF folder (or "
                "run ./setup_engine.sh there)")
    return "run ./setup_engine.sh in the FluBNF folder"


def archive_step(platform: str | None = None) -> str:
    """How this machine installs the engine from its archive, or replaces
    an older unpacked one, as a clause to follow "To install it, ": the
    one wording the build warning, the run errors and doctor share."""
    return (f"save {archive_name()} in your Downloads folder and "
            f"{setup_step(platform)}")


def checkout_steps(path, dirty: bool = False,
                   platform: str | None = None) -> str:
    """How a git checkout of the engine reaches the production build, in
    sentences. The launchers fast-forward a clean checkout on the
    production branch on every open (engine_update), so the step by hand
    is to get it clean and onto that branch. A machine without access to
    the private fork (a checkout cloned from a bundle, whose origin
    FluBNF.bat points at GitHub) takes the archive instead. The path is
    quoted, as a Windows profile folder can hold a space, and named once:
    in a tip it is the longest word by far. No punctuation touches a
    command: a pasted "feature/particle-filter," names no branch."""
    stash = ("stash the local edits first (git stash in that folder), then "
             if dirty else "")
    return (f"FluBNF moves a clean checkout on {PRODUCTION_ENGINE_BRANCH} to "
            f"the production build each time it opens. To switch, {stash}run "
            f'git -C "{path}" checkout {PRODUCTION_ENGINE_BRANCH} and reopen '
            "FluBNF. Without access to the private fork (a checkout cloned "
            "from a bundle), rename the engine folder so FluBNF stops using "
            f"it, then {archive_step(platform)}.")


def _unreadable_fix(b: dict, platform: str | None) -> str:
    """What to do about a checkout git would not read, by git's reason."""
    plat = platform or sys.platform
    cmd = str(b.get("safe_directory") or "")
    if cmd:
        if plat == "win32":
            # git quotes a spaced path with single quotes, which cmd.exe
            # passes on as part of the path; double quotes work in cmd.exe
            # and PowerShell alike, and a Windows path cannot hold one
            head, sep, arg = cmd.partition("safe.directory ")
            if len(arg) > 1 and arg[0] == arg[-1] == "'" and '"' not in arg:
                cmd = f'{head}{sep}"{arg[1:-1]}"'
        return ("git reads a folder that another account owns only once it "
                f"is marked safe. To mark this one, run {cmd} and reopen "
                "FluBNF.")
    if b.get("error") == NO_GIT:
        if plat == "win32":
            return ("Install Git for Windows (https://git-scm.com/download/"
                    "win), then open FluBNF.bat again.")
        if plat == "darwin":
            return ("Install git (xcode-select --install in Terminal), then "
                    "reopen FluBNF.")
        return "Install git, then reopen FluBNF."
    path = str(b.get("path") or "<engine folder>")
    return (f'Run git -C "{path}" status to see why. If the checkout is '
            "damaged, rename the engine folder so FluBNF stops using it, "
            f"then {archive_step(platform)}.")


def fix(build: dict | None, platform: str | None = None) -> str:
    """How to switch to the production build, in plain words, for this
    machine's launcher (`platform`, sys.platform by default: Windows opens
    FluBNF.bat and has no setup_engine.sh)."""
    b = build or {}
    if b.get("source") == "unreadable":
        return _unreadable_fix(b, platform)
    if b.get("source") == "archive":
        return ("This engine was installed from an archive. To replace it, "
                f"{archive_step(platform)}.")
    path = str(b.get("path") or "<engine folder>")
    return (checkout_steps(path, bool(b.get("dirty")), platform)
            + " Research runs may use other builds on purpose.")


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
