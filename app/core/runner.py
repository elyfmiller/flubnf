"""SANDBOX: the runner on the students' Mac Studio (`flubnf runner`): one
supervisor per computer works the student experiment queue, one job at a
time, each in a fresh child process that points the Sandbox at one
student's folder for its whole life.

  ~/Students/                 STUDENTS, a preset (it may be a link Ely
                              made: resolved at each use)
    .runner/                  the runner's own folder: runner.json (the
                              supervisor's state, written by it alone),
                              runner.lock (one runner per computer),
                              pf_runners.json (the job's fits, for the
                              sweep), job.log (the child's output)
    <name>/sandbox/           a student's folder, today's Sandbox shape
      experiments/<id>/QUEUED a job: an empty flag, its mtime the time
                              queued (0 for a job requeued at a restart)

A computer has a runner exactly when STUDENTS/.runner exists. Elsewhere
every function here answers as if there were none (folder_of None,
read_state {}, busy_words "", storage no rows), at the cost of one
failed stat, so Ely's laptop and every console off the runner behave as
before.

A student's console queues (enqueue), dequeues or stops (stop), and
reads where its jobs stand (position, refusal, read_state); it reads no
other student's folder. The supervisor (serve) takes the queue first in,
first out; holds it while the install is not a clean main, the engine is
missing or a replay runs elsewhere on this computer; keeps FREE_FLOOR
free on the disk; kills a job at its limits (LIMITS); and tidies idle
folders (their unfinished weeks removed, their weeks made lean, their
summaries scored again). The child (job_main) refits an unfinished week
from its start, checks the folder before every week (check), and makes
each stored week lean (experiments.drop_samples).

A job names its folder by (name, id) only, never by a path, and nothing
in a student folder is trusted: check refuses a link, a pipe, a hard
link, a giant file or a strange entry anywhere on the way, with the
words MACHINE carries.

Module imports are the standard library's only: the core modules load
pandas, which a console's import must not, and fcntl, resource and
os.killpg are POSIX's, imported where they are used, so the module
imports on Windows (where serve refuses to start).
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import signal
import stat
import statistics
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

#: the students' clones, one folder each (~/Students/<name>): a preset
STUDENTS = Path.home() / "Students"
#: the runner's own folder in STUDENTS; its existing turns the runner's
#: branches on in any console (state_dir)
STATE_NAME = ".runner"
STATE_FILE = "runner.json"
LOCK_FILE = "runner.lock"
REGISTRY_FILE = "pf_runners.json"
LOG_FILE = "job.log"
#: runner.json's format: consoles of other versions read the file, and
#: one they do not know reads as no runner state
STATE_VERSION = 1
GiB, MiB = 2**30, 2**20
#: kept free on the disk that holds STUDENTS: at queueing, at dispatch and
#: while a job runs (swap and updates; a job's own needs are its peak)
FREE_FLOOR = 20 * GiB
#: the supervisor's clocks: a poll while idle, a watch while a job runs,
#: the folder and the disk measured, a heartbeat older than ALIVE_S reads
#: as a runner that is not running, an idle folder looked at again
POLL_S, WATCH_S, DISK_EVERY_S, ALIVE_S, TIDY_EVERY_S = 10.0, 5.0, 30.0, 60.0, 3600.0
#: how long a killed job's processes get after SIGTERM before SIGKILL
KILL_WAIT_S = 10.0
RECENT_MAX = 50
#: this computer's speed against pf.cell_seconds until a job of the size
#: has finished here (the shipped 2024-25 replay ran 1.91 at width 8),
#: then the median of its last K_RECENT jobs of that size
K_FIRST = 2.0
K_RECENT = 10
#: scoring's seconds at a segment end (a full scored in about 33 s)
SCORE_S = {"smoke": 2, "pilot": 10, "full": 40}
#: what a week keeps once lean: the sidecar per location and member,
#: oracle.json per location and the donor bank with the Oracle step on;
#: the folder's own files
QUANTILES_BYTES, ORACLE_BYTES, BANK_BYTES, FOLDER_BYTES = 2_500, 37_000, 250_000, 200_000
#: what a fit holds while its week is in flight: its cell tree, and the
#: week's samples before their drop
FIT_TREE_BYTES, FIT_SAMPLES_BYTES = 16 * MiB, 450_000
#: the largest file check reads in a student folder (a week's samples
#: excepted), and the largest experiment.json
FILE_MAX, SETTINGS_MAX = 64 * MiB, 4096


@dataclass(frozen=True)
class Limits:
    """One size's limits on the runner (limits caps the memory)."""
    seconds: float      # wall time from the child's start (a pause counts)
    memory: int         # RSS of the child and its descendants
    disk: int           # the experiment folder; also RLIMIT_FSIZE per file


#: by size: smoke 24x, pilot 11x and full 4x their first estimate at
#: width 16 in time, and 15x, 5.9x and 3.8x their peak on disk; the
#: memory has never been measured (every job records its peaks). A tidy
#: runs under the pilot's.
LIMITS = {"smoke": Limits(30 * 60, 4 * GiB, 512 * MiB),
          "pilot": Limits(2 * 3600, 16 * GiB, 1 * GiB),
          "full": Limits(16 * 3600, 32 * GiB, 10 * GiB)}

#: the job child's program: `-I` keeps the working folder and PYTHON*
#: variables out of its imports (app and flubnf import through the main
#: install's editable finder)
JOB_ENTRY = ("import sys; from app.core.runner import job_main; "
             "sys.exit(job_main(sys.argv[1:]))")

#: a week's folder name; a retro replay's week runner (retro.py
#: _launch_runners: a replay holds the queue, a Sandbox fit's
#: pf_runner_<n>.py never does); a season's name; Ely's repository
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RUNNER_PY_RE = re.compile(r"runner_\d+\.py")
_SEASON_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
_ORIGIN_RE = re.compile(r"[/:]elyfmiller/flubnf(\.git)?$")
#: the folders a week holds beside its cell trees (reclaim.CELL_DIR_RE):
#: retro.CELL_DONE_DIRNAME and oracle.BANK_DIRNAME, spelled here so the
#: module imports nothing of the engine
_WEEK_DIRS = ("cells_done", "oracle_bank")
#: the words of a job stopped from its page, which refits its week
_PAGE_STOP = ("Stopped from its page. Finished weeks are kept; Resume "
              "queues it again, and the week it was fitting starts over.")
#: the words of a job the runner's own stop ended (queued again first)
_RUNNER_STOP = "The runner stopped while it replayed; it was queued again."


def _now() -> float:
    return time.time()


#: set by SIGTERM or SIGINT while serve works the queue
_stopping = False


def _on_signal(signum, frame) -> None:
    """serve's SIGTERM and SIGINT: stop at the next watch or poll (a flag
    only: a handler that took a lock could wait on itself)."""
    global _stopping
    _stopping = True


def _sleep(seconds: float) -> None:
    """The supervisor's wait between polls and watches, ending within
    half a second of a stop (the tests replace it with their clock)."""
    end = time.monotonic() + seconds
    while not _stopping:
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(0.5, left))


def _utc(epoch) -> str:
    """Unix time as %Y-%m-%dT%H:%M:%SZ."""
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc
                                  ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(utc) -> float | None:
    """A %Y-%m-%dT%H:%M:%SZ time as Unix time, or None."""
    try:
        return datetime.strptime(str(utc), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _num(v) -> float:
    """A number read from runner.json, 0.0 for anything else."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def _say(text: str) -> None:
    """One line on the supervisor's stdout, one per event."""
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}", flush=True)


def _shown(x) -> str:
    """A value a person posted, quoted and cut short for the words."""
    s = repr(x)
    return s if len(s) <= 60 else s[:57] + "..."


def _h(n) -> str:
    from app.core.retro_archive import human_bytes
    return human_bytes(n)


def _ordinal(n: int) -> str:
    suffix = ("th" if 10 <= n % 100 <= 20
              else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))
    return f"{n}{suffix}"


def _students() -> Path:
    """STUDENTS resolved: a link Ely made is followed here, and only here."""
    return Path(os.path.realpath(STUDENTS))


def _in_students(p) -> bool:
    """Whether a path is, resolved, STUDENTS or inside it: a student's
    clone (folders() holding its name or not), never the main install."""
    students = _students()
    q = Path(os.path.realpath(p))
    return q == students or students in q.parents


def _is_dir(p) -> bool:
    """A folder itself, not a link to one (lstat)."""
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except OSError:
        return False


def _is_file(p) -> bool:
    """A regular file itself, not a link to one (lstat)."""
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)
    except OSError:
        return False


def _refuse(text: str):
    from app.core.problem_codes import Refusal, finding
    raise Refusal(finding("MACHINE", text))


def _said(e: Exception) -> str:
    """A refusal on one line, its code after it: the first problem's text
    for a Refusal, MACHINE for a resume the run record refuses."""
    from app.core.problem_codes import Refusal
    if isinstance(e, Refusal):
        found = [f for f in e.findings if f["tier"] == "problem"] or e.findings
        text, code = found[0]["text"], e.code
    else:
        text, code = str(e), "MACHINE"
    return f"{' '.join(str(text).split())} ({code})"


# ------------------------------------------------------------- the folders


def state_dir() -> Path:
    """The runner's folder, STUDENTS/.runner: a computer has a runner
    exactly when it exists (the first `flubnf runner` makes it)."""
    return STUDENTS / STATE_NAME


def folders() -> list[str]:
    """The students' folders, in name order: the children of STUDENTS
    that are folders themselves (not links), named as sandbox.NAME_RE
    allows (so .runner never is), with no other child of the same name
    ignoring case (both are left out), and holding a sandbox folder
    itself."""
    from app.core import sandbox as sb
    base = _students()
    try:
        names = os.listdir(base)
    except OSError:
        return []
    lower: dict = {}
    for n in names:
        lower[n.lower()] = lower.get(n.lower(), 0) + 1
    return sorted((n for n in names
                   if sb.NAME_RE.fullmatch(n) and lower[n.lower()] == 1
                   and _is_dir(base / n) and _is_dir(base / n / "sandbox")),
                  key=lambda n: (n.lower(), n))


def folder(name: str) -> Path | None:
    """A student's folder, STUDENTS/<name>/sandbox (resolved), or None
    for a name folders() does not hold."""
    if not isinstance(name, str) or name not in folders():
        return None
    return _students() / name / "sandbox"


def folder_of(sandbox: Path) -> str | None:
    """The student's name when this computer has a runner and `sandbox`
    is, resolved, STUDENTS/<name>/sandbox of a folder folders() holds:
    the console then queues. None elsewhere, at one failed stat on a
    computer without a runner."""
    if not state_dir().is_dir():
        return None
    try:
        p = Path(os.path.realpath(sandbox))
    except (OSError, TypeError, ValueError):
        return None
    if p.name != "sandbox" or p.parent.parent != _students():
        return None
    name = p.parent.name
    return name if name in folders() else None


def _folder_ok(p: Path, rel: str, name: str) -> bool:
    """Whether p is there: True for a folder itself whose real path is p;
    False when nothing is there; Refusal (MACHINE, naming rel) for a
    link, anything but a folder, or a path that leads elsewhere."""
    try:
        st = os.lstat(p)
    except FileNotFoundError:
        return False
    except OSError as e:
        _refuse(f"{rel} cannot be read ({e.strerror or e})")
    if stat.S_ISLNK(st.st_mode):
        _refuse(f"{rel} is a link, and the runner follows no link in a "
                "student folder")
    if not stat.S_ISDIR(st.st_mode):
        _refuse(f"{rel} is not a folder")
    if os.path.realpath(p) != str(p):
        _refuse(f"{rel} leads outside {name}'s folder")
    return True


def _walk(top: Path, rel: str, *, experiment: bool) -> None:
    """Refuse (MACHINE, naming the path) anything under top that the
    runner must not read or write through, links never followed: a link,
    pipe, socket or device; a file with another name (a hard link: an
    append would write into another folder's file); a file over FILE_MAX
    (a week's samples excepted). In an experiment's folder also an
    experiment.json over SETTINGS_MAX, a folder in weeks/ not named by a
    date, and inside a week a folder FluBNF does not write there or a
    Python file other than its runner scripts. Plain files such as
    Finder's .DS_Store are allowed everywhere."""
    from app.core import experiments as X
    from app.core import reclaim
    from app.core.retro_store import SAMPLES_GZ, SAMPLES_JSON

    def fail(e):
        if not isinstance(e, FileNotFoundError):
            raise e
    try:
        for dirpath, dirs, files in os.walk(top, onerror=fail):
            here = Path(dirpath).relative_to(top).parts
            for n in sorted(dirs + files):
                parts = here + (n,)
                shown = "/".join((rel,) + parts)
                try:
                    st = os.lstat(os.path.join(dirpath, n))
                except FileNotFoundError:
                    continue              # replaced meanwhile (a tmp file)
                mode = st.st_mode
                week = (experiment and parts[0] == "weeks")
                if stat.S_ISLNK(mode):
                    _refuse(f"{shown} is a link, and the runner follows no "
                            "link in a student folder")
                if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
                    what = "pipe" if stat.S_ISFIFO(mode) else "socket"
                    _refuse(f"{shown} is a {what}, and the runner reads no "
                            f"{what} in a student folder")
                if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
                    _refuse(f"{shown} is a device, and the runner reads no "
                            "device in a student folder")
                if stat.S_ISDIR(mode):
                    if week and len(parts) == 2 and not _DATE_RE.fullmatch(n):
                        _refuse(f"{shown} is not a week: a folder in weeks "
                                "is named by its date, such as 2024-12-28")
                    if (week and len(parts) == 3 and n not in _WEEK_DIRS
                            and not reclaim.CELL_DIR_RE.match(n)):
                        _refuse(f"{shown} is not a folder FluBNF writes in "
                                "a week (cells_done, oracle_bank or a fit's "
                                "<location>_r<n>)")
                    continue
                if not stat.S_ISREG(mode):
                    _refuse(f"{shown} is neither a file nor a folder")
                if st.st_nlink > 1:
                    _refuse(f"{shown} is a hard link (one file with "
                            f"{st.st_nlink} names), and the runner writes "
                            "into no file another folder may share")
                if experiment and parts == (X.SETTINGS,) and (
                        st.st_size > SETTINGS_MAX):
                    _refuse(f"{shown} is {_h(st.st_size)}, and an "
                            f"experiment.json is at most {_h(SETTINGS_MAX)}")
                samples = (week and len(parts) == 3
                           and n in (SAMPLES_JSON, SAMPLES_GZ))
                if st.st_size > FILE_MAX and not samples:
                    _refuse(f"{shown} is {_h(st.st_size)}, and the runner "
                            f"reads no file over {_h(FILE_MAX)} in a student "
                            "folder")
                if (week and len(parts) == 3 and n.endswith(".py")
                        and not _RUNNER_PY_RE.fullmatch(n)):
                    _refuse(f"{shown} is not a runner script FluBNF writes "
                            "(runner_<n>.py), and a week holds no other "
                            "Python file")
    except OSError as e:
        _refuse(f"{rel} cannot be read in full ({e.strerror or e})")


def _job_folder(name: str, eid: str) -> Path:
    """An experiment's folder named by (name, id), every folder on the way
    a folder itself inside the student's (check without the walk): what
    the runner's own writes need. Refusal (MACHINE) otherwise."""
    from app.core import experiments as X
    top = check(name)
    if not isinstance(eid, str) or not X._ID_RE.fullmatch(eid):
        _refuse(f"{_shown(eid)} is not an experiment's id")
    rel = f"experiments/{eid}"
    if not _folder_ok(top / "experiments" / eid, rel, name):
        _refuse(f"{rel} is not in {name}'s folder")
    return top / "experiments" / eid


def check(name: str, eid: str | None = None) -> Path:
    """The folder a job names, checked before the runner reads or writes
    through it: Refusal(MACHINE) in words naming the path relative to the
    student's folder, else the experiment's folder (the student's folder
    with no id).

    The name is one of folders(); the id one experiments._ID_RE allows (no
    separator, no dot). Every folder from STUDENTS down to experiments/<id>
    is a folder itself whose real path is where it stands. The walk of
    experiments/<id> refuses what _walk does; then its experiment.json
    must derive its name (experiments.find). The library version it
    names, when there is one, passes the same tests on its way and in its
    files, and the weeks its run record froze are dates."""
    from app.core import experiments as X
    from app.core import library
    from app.core.problem_codes import Refusal
    if not isinstance(name, str) or name not in folders():
        _refuse(f"there is no student folder {_shown(name)} on this computer")
    top = _students() / name / "sandbox"
    _folder_ok(top, "the sandbox folder", name)
    _folder_ok(top / "experiments", "experiments", name)
    if eid is None:
        return top
    f = _job_folder(name, eid)
    rel = f"experiments/{eid}"
    _walk(f, rel, experiment=True)
    if X.find(eid, under=top / "experiments") != f:
        _refuse(f"{rel}/{X.SETTINGS} does not name this experiment: its "
                "settings give another id, or cannot be read")
    try:
        mname, version = library.parse_ref(X.read(f / X.SETTINGS)["model"])
    except Refusal:
        mname, version = "", None
    if version is not None:
        lib = top / "library"
        on_way = (("library", lib), (f"library/{mname}", lib / mname),
                  (f"library/{mname}/{version}", lib / mname / str(version)))
        if all(_folder_ok(p, r, name) for r, p in on_way):
            _walk(lib / mname / str(version), f"library/{mname}/{version}",
                  experiment=False)
    st = X._meta(f).get("settings")
    if isinstance(st, dict) and "weeks" in st:
        weeks = st["weeks"]
        bad = ([w for w in weeks if not isinstance(w, str)
                or not _DATE_RE.fullmatch(w)]
               if isinstance(weeks, list) else [weeks])
        if bad:
            _refuse(f"{rel}/run_meta.json names a week that is not a date: "
                    f"{_shown(bad[0])}")
    return f


def _settings(folder: Path) -> dict | None:
    """The settings of an experiment's folder, read only when its
    experiment.json is a regular file of at most SETTINGS_MAX that
    derives the folder's name; None otherwise."""
    from app.core import experiments as X
    from app.core.problem_codes import Refusal
    p = Path(folder) / X.SETTINGS
    try:
        st = os.lstat(p)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > SETTINGS_MAX:
        return None
    try:
        s = X.read(p)
        return s if X.experiment_id(s) == Path(folder).name else None
    except Refusal:
        return None


def _record(folder: Path, *, follow: bool = False) -> dict:
    """A folder's run record, read only when run_meta.json is a regular
    file of at most FILE_MAX (lstat, or stat with follow for a tree of
    the runner's own install), and cached by its stat; {} otherwise."""
    from app.core import retro
    p = Path(folder) / retro.META_NAME
    try:
        st = os.stat(p) if follow else os.lstat(p)
    except OSError:
        return {}
    if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX:
        return {}
    key = (st.st_mtime_ns, st.st_size, st.st_ino)
    hit = _RECORDS.get(str(p))
    if hit is not None and hit[0] == key:
        return hit[1]
    meta = retro.read_meta(folder)
    if len(_RECORDS) > 4096:
        _RECORDS.clear()
    _RECORDS[str(p)] = (key, meta)
    return meta


#: run records read by _record: {path: (stat key, record)}
_RECORDS: dict = {}


def _status(folder: Path) -> dict | None:
    """experiments.status of a student's experiment that check has not
    looked at, read only when its run record is absent or a regular file
    of at most FILE_MAX (lstat): None for a link, a pipe or a giant file
    there (status would follow it or read it whole; check refuses it)."""
    from app.core import experiments as X
    from app.core import retro
    try:
        st = os.lstat(Path(folder) / retro.META_NAME)
    except FileNotFoundError:
        return X.status(folder)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX:
        return None
    return X.status(folder)


def _writable_record(folder: Path) -> bool:
    """Whether the runner may write a folder's run record now
    (retro.write_meta writes run_meta.json.tmp, then replaces the
    record): the record a regular file of at most FILE_MAX (lstat), and
    whatever stands at the tmp path (a link, a pipe, a hard link, a
    folder) removed first, so the write never opens it. False, nothing
    removed, for any other record."""
    from app.core import retro
    p = retro.meta_path(folder)
    try:
        st = os.lstat(p)
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX:
        return False
    tmp = p.with_suffix(".json.tmp")
    if os.path.lexists(tmp):
        if _is_dir(tmp):
            retro.delete_tree(tmp)
        else:
            os.unlink(tmp)
    return True


def limits(size: str) -> Limits:
    """The size's LIMITS, its memory capped at half this computer's RAM
    (os.sysconf SC_PHYS_PAGES * SC_PAGE_SIZE, where it can be read)."""
    lim = LIMITS[size]
    try:
        ram = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, ValueError, TypeError, OSError):
        ram = 0
    if ram > 0 and lim.memory > ram // 2:
        lim = replace(lim, memory=ram // 2)
    return lim


# --------------------------------------------------------------- the queue


def _ids(experiments: Path) -> list[str]:
    """The names in an experiments folder that are an experiment's id and
    a folder themselves, sorted; [] unless the folder is one itself."""
    from app.core import experiments as X
    if not _is_dir(experiments):
        return []
    try:
        names = os.listdir(experiments)
    except OSError:
        return []
    return sorted(n for n in names
                  if X._ID_RE.fullmatch(n) and _is_dir(experiments / n))


def queue() -> list[dict]:
    """Every job, in the order the runner takes them: {"folder", "id",
    "size" ("" when its settings cannot be read), "queued_utc"} of each
    experiment folder holding QUEUED as a regular file, sorted by the
    flag's mtime (0, a job requeued at a restart, first), then the
    student's folder and the id. Folders and the flag are looked at with
    lstat; nothing is followed."""
    from app.core import experiments as X
    base = _students()
    rows = []
    for name in folders():
        exp = base / name / "sandbox" / "experiments"
        for eid in _ids(exp):
            try:
                st = os.lstat(exp / eid / X.QUEUED)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            s = _settings(exp / eid)
            rows.append((st.st_mtime, name, eid, {
                "folder": name, "id": eid, "size": s["size"] if s else "",
                "queued_utc": _utc(st.st_mtime)}))
    rows.sort(key=lambda r: r[:3])
    return [r[3] for r in rows]


def read_state() -> dict:
    """runner.json as the supervisor wrote it, plus "alive" (its heartbeat
    at most ALIVE_S old and its pid a live process); {} when there is
    none, it cannot be read, or it is of a format_version this FluBNF
    does not read. "job" is a dict or None, "waiting" and "recent" lists."""
    p = state_dir() / STATE_FILE
    try:
        st = os.lstat(p)
        if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_MAX:
            return {}
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    v = obj.get("format_version") if isinstance(obj, dict) else None
    if type(v) is not int or v != STATE_VERSION:      # true is not 1
        return {}
    for k in ("waiting", "recent"):
        obj[k] = [x for x in obj.get(k) or () if isinstance(x, dict)] \
            if isinstance(obj.get(k), list) else []
    if not isinstance(obj.get("job"), dict):
        obj["job"] = None
    beat = _epoch(obj.get("heartbeat_utc"))
    obj["alive"] = bool(beat is not None and _now() - beat <= ALIVE_S
                        and _alive(obj.get("pid")))
    return obj


def _alive(pid) -> bool:
    """Whether a pid read from runner.json is a live process."""
    from flubnf.cli import _pid_alive
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    return pid > 0 and _pid_alive(pid)


def _named(entry, name: str, eid: str) -> bool:
    return (isinstance(entry, Mapping) and entry.get("folder") == name
            and entry.get("id") == eid)


def _estimate_of(folder: Path, recent: Sequence[Mapping]) -> dict:
    """estimate() for an experiment's folder: its settings, the weeks its
    run record froze (else the plan's), the weeks stored; {} when its
    settings cannot be read or the season's weeks cannot be worked out."""
    from app.core import experiments as X
    from app.core import retro
    s = _settings(folder)
    if s is None:
        return {}
    st = _record(folder).get("settings")
    weeks = (X._weeks(st) if isinstance(st, dict)
             and isinstance(st.get("weeks"), list) else None)
    try:
        if weeks is None:
            weeks = _plan_weeks(s)
        done = [w for w in weeks if retro.week_done(folder, w)]
        return estimate(s, weeks=weeks, done=done, recent=recent)
    except Exception:
        return {}


def _plan_weeks(s: Mapping) -> list[str]:
    """The weeks a plan would freeze for these settings (the hub's
    vintages and rounds), [] for a season not here."""
    from app.core import experiments as X
    from app.core import retro
    if s["season"] not in retro.available_seasons():
        return []
    return X.size_weeks(s["size"], retro.season_vintages(s["season"]),
                        retro.season_bounds(s["season"]), X._has_round)


def _position(state: Mapping, name: str, eid: str, folder: Path) -> dict:
    """The queued JSON of one job from runner.json: its place among the
    waiting (the back of the line when the supervisor has not seen it
    yet, its estimate then worked out here), the wait (the running job's
    eta and the seconds of every job ahead), its own figures, why it
    waits, and whether the runner is running."""
    waiting = list(state.get("waiting") or [])
    job = state.get("job") if isinstance(state.get("job"), Mapping) else None
    at = next((i for i, w in enumerate(waiting) if _named(w, name, eid)), None)
    if at is None:
        entry, at = _estimate_of(folder, state.get("recent") or ()), len(waiting)
    else:
        entry = waiting[at]
    wait = (_num(job.get("eta_s")) if job else 0.0) + sum(
        _num(w.get("seconds")) for w in waiting[:at])
    why = entry.get("why") or (f"waiting: {state['waiting_why']}"
                               if state.get("waiting_why") else "")
    return {"position": at + 1, "wait_s": round(wait, 1),
            "seconds": _num(entry.get("seconds")),
            "measured": bool(entry.get("measured")),
            "peak_bytes": int(_num(entry.get("peak_bytes"))),
            "keep_bytes": int(_num(entry.get("keep_bytes"))),
            "why": str(why), "runner": bool(state.get("alive"))}


def position(name: str, eid: str, *,
             state: Mapping | None = None) -> dict | None:
    """Where a queued job stands, as the experiment's JSON shows it:
    {"position" (1 is next), "wait_s", "seconds", "measured",
    "peak_bytes", "keep_bytes", "why" (" · "-ready: "waiting for disk:
    ..." or "waiting: ..."; "" when nothing holds it), "runner" (the
    runner is running)}. None unless QUEUED stands in its folder, and
    while a running runner's job names it (it is starting; the job of a
    runner that is not running starts nothing). Reads only that folder
    and runner.json (`state`, read_state()'s, when the caller read it
    once for many jobs)."""
    from app.core import experiments as X
    top = folder(name)
    if top is None or not isinstance(eid, str) or not X._ID_RE.fullmatch(eid):
        return None
    f = top / "experiments" / eid
    if not (_is_dir(top / "experiments") and _is_dir(f)
            and _is_file(f / X.QUEUED)):
        return None
    state = read_state() if state is None else state
    if state.get("alive") and _named(state.get("job"), name, eid):
        return None
    return _position(state, name, eid, f)


def refusal(name: str, eid: str, *, state: Mapping | None = None) -> str:
    """What the runner said when it last would not run this job: the text
    of runner.json's newest recent entry for it when that is a refusal
    newer than its experiment.json ("<words> (CODE)"); "" otherwise (a
    job queued again since has its settings written again). `state` is
    read_state()'s when the caller read it once for many jobs."""
    from app.core import experiments as X
    top = folder(name)
    if top is None or not isinstance(eid, str) or not X._ID_RE.fullmatch(eid):
        return ""
    try:
        mtime = os.lstat(top / "experiments" / eid / X.SETTINGS).st_mtime
    except OSError:
        return ""
    for r in (read_state() if state is None else state).get("recent") or ():
        if _named(r, name, eid) and r.get("kind", "run") == "run":
            when = _epoch(r.get("utc"))
            if (r.get("outcome") == "refused" and when is not None
                    and when >= math.floor(mtime)):
                return str(r.get("text") or "")
            return ""
    return ""


# ---------------------------------------------------------------- estimates


def _k(size: str, recent: Sequence[Mapping]) -> tuple[float, int]:
    """(k, n): the median k of this computer's last K_RECENT jobs of the
    size that ended done, stopped or at a limit with a week fitted, and
    how many there were; (K_FIRST, 0) before one has."""
    ks = []
    for r in recent or ():
        if (isinstance(r, Mapping) and r.get("size") == size
                and r.get("kind", "run") == "run"
                and r.get("outcome") in ("done", "stopped", "limit")
                and _num(r.get("weeks")) >= 1 and _num(r.get("k")) > 0):
            ks.append(_num(r["k"]))
            if len(ks) == K_RECENT:
                break
    return (statistics.median(ks), len(ks)) if ks else (K_FIRST, 0)


def _week_n(season: str, asof: str) -> int:
    """A week's observed weeks: (as-of minus the season's start) // 7 + 1."""
    from app.core import retro
    start = date.fromisoformat(retro.season_bounds(season)[0])
    return (date.fromisoformat(asof) - start).days // 7 + 1


def _week_cost(season: str, asof: str, fits: int, particles: int) -> float:
    """⌈F/W⌉·c(n_w): a week's predicted seconds at this computer's width
    (pf.DEFAULT_SHARD_WIDTH, the same in every process here) on the
    production machine."""
    from app.core.engines import pf
    width = max(1, int(pf.DEFAULT_SHARD_WIDTH))
    return (-(-int(fits) // width)
            * pf.cell_seconds({"n_obs": _week_n(season, asof),
                               "particles": particles}))


def estimate(settings: Mapping, *, weeks: Sequence[str] | None = None,
             done: Sequence[str] = (), recent: Sequence[Mapping] = ()) -> dict:
    """What a job costs here: {"weeks" (left to fit), "fits" (in all),
    "seconds", "measured" (k timed on this computer), "peak_bytes" (while
    it runs), "keep_bytes" (once its weeks are lean)}.

    Time is Σ k·⌈F/W⌉·c(n_w) over the weeks left plus SCORE_S, c being
    pf.cell_seconds and k this computer's ratio (_k over `recent`,
    runner.json's, else K_FIRST). Disk: keep = N_w·(L·(2,500 B·m + 37,000
    B·on) + 250,000 B·on) + 200,000 B, with m the members (3 with the
    Oracle step on, 2 off); peak = keep + F·16 MiB + F·450,000 B. `weeks`
    are the frozen or planned weeks (the hub's, worked out here when
    None), `done` those stored. Pure but for the hub's vintages."""
    from app.core import experiments as X
    s = X.read(settings)
    size = X.SIZES[s["size"]]
    if weeks is None:
        weeks = _plan_weeks(s)
    stored = set(done)
    left = [w for w in weeks if w not in stored]
    n_loc = (len(X._all_locations()) if size.locations == "all"
             else len(size.locations))
    fits = n_loc * size.replicates
    k, n = _k(s["size"], recent)
    seconds = sum(k * _week_cost(s["season"], w, fits, size.particles)
                  for w in left) + SCORE_S[s["size"]]
    on = 1 if s["oracle"] else 0
    keep = (len(left) * (n_loc * (QUANTILES_BYTES * (2 + on) + ORACLE_BYTES * on)
                         + BANK_BYTES * on) + FOLDER_BYTES)
    return {"weeks": len(left), "fits": len(left) * fits,
            "seconds": round(seconds, 1), "measured": n > 0,
            "peak_bytes": keep + fits * (FIT_TREE_BYTES + FIT_SAMPLES_BYTES),
            "keep_bytes": keep}


def _timed_words(size: str, recent: Sequence[Mapping]) -> str:
    """Where a time estimate comes from, in the queued notice's words."""
    n = _k(size, recent)[1]
    if not n:
        return f"a first estimate: no {size} has finished on this computer yet"
    return f"timed from {n} {size}{'s' if n != 1 else ''} on this computer"


def _free() -> int:
    """Bytes free on the disk that holds STUDENTS (0 when it cannot be
    read, which no floor passes)."""
    try:
        return int(shutil.disk_usage(_students()).free)
    except OSError:
        return 0


# --------------------------------------------- queueing, from a console


def enqueue(source: Path | Mapping) -> dict:
    """Queue an experiment on this computer's runner, from the student's
    own console (its sb.SANDBOX): experiment.json and an empty QUEUED
    written in its folder, nothing claimed, nothing run here. Nothing is
    written until every check passes; Refusal otherwise (the settings',
    the plan's, MACHINE for the folder, the runner and the disk).

    Already queued, replaying (its record under way, or a running
    runner's job; a tidy of it is not) and complete are answered in
    words. The plan reads the runner's
    retro root (runner.json) for the reference; without a runner.json
    the reference is checked when the runner starts it. The disk must
    keep FREE_FLOOR free after this job's peak and the keep of the job
    running and those ahead; the floor's Refusal has a second finding,
    the detail. Returns {"id", "state" ("queued", "already",
    "replaying", "complete"), "position", "wait_s", "estimate",
    "reference" ({"member", "root", "started_utc"} or None), "plan" (when
    queued: the plan as Start's JSON gives it, else None), "findings",
    "runner" (running), "free", "text", "detail", "kind"}."""
    from app.core import experiments as X
    from app.core import library, retro
    from app.core import sandbox as sb
    from app.core.problem_codes import Refusal, finding
    s = X.read(source)
    eid = X.experiment_id(s)
    name = folder_of(sb.SANDBOX)
    if name is None:
        _refuse("this computer has no runner" if not state_dir().is_dir()
                else "this computer's runner works the student folders in "
                f"{STUDENTS} only, and this Sandbox is not one of them")
    top = check(name)
    f = top / "experiments" / eid
    there = os.path.lexists(f)
    if there:
        check(name, eid)
    state = read_state()
    alive = bool(state.get("alive"))
    free = _free()
    out = {"id": eid, "position": None, "wait_s": None, "estimate": None,
           "reference": None, "plan": None, "findings": [], "runner": alive,
           "free": free, "detail": ""}
    st = X.status(f) if there else {}
    job = state.get("job") if isinstance(state.get("job"), Mapping) else {}
    if (st.get("status") in retro.ACTIVE_STATUSES or (
            alive and _named(job, name, eid) and job.get("kind") == "run")):
        return {**out, "state": "replaying", "kind": "info",
                "text": f"{eid} is replaying on the runner."}
    if _is_file(f / X.QUEUED):
        return _already(out, state, name, eid, f)
    if st.get("complete"):
        return {**out, "state": "complete", "kind": "info",
                "text": f"{eid} is complete: every week is stored, nothing "
                        "to fit."}
    rr = state.get("retro_root")
    known = isinstance(rr, str) and bool(rr)
    p = X.plan(s, retro_root=Path(rr) if known else state_dir() / "no-retro")
    found = [x for x in p["findings"] if known or x["code"] != "NO_REFERENCE"]
    rec = X._meta(f).get("settings") if there else None
    weeks = (X._weeks(rec) if isinstance(rec, dict)
             and isinstance(rec.get("weeks"), list) else p["weeks"])
    done = [w for w in weeks if retro.week_done(f, w)]
    recent = state.get("recent") or ()
    est = estimate(s, weeks=weeks, done=done, recent=recent)
    ahead = int(_num(job.get("keep_bytes")) + sum(
        _num(w.get("keep_bytes")) for w in state.get("waiting") or ()
        if not _named(w, name, eid)))
    left = free - ahead - est["peak_bytes"]
    if left < FREE_FLOOR:
        raise Refusal([
            finding("MACHINE", f"{eid} needs about {_h(est['peak_bytes'])} "
                    f"of disk while it runs, which would leave "
                    f"{_h(max(0, left))} free; FluBNF keeps "
                    f"{_h(FREE_FLOOR)} free on this disk"),
            finding("MACHINE", f"The experiments queued ahead of it keep "
                    f"{_h(ahead)}. Delete experiments you no longer need, "
                    "or ask Ely to free space.")])
    f.mkdir(parents=True, exist_ok=True)
    library.write_json(f / X.SETTINGS, json.loads(X.settings_text(s)))
    try:
        fd = os.open(f / X.QUEUED, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        return _already(out, read_state(), name, eid, f)
    os.close(fd)
    pos = _position(read_state(), name, eid, f)
    ref = p["reference"]
    plan = {k: p[k] for k in ("model", "model_fingerprint", "experiment",
                              "season", "size", "oracle", "locations",
                              "replicates", "particles")}
    plan["weeks"] = list(weeks)          # the frozen ones at a resume
    plan["reference"] = None if ref is None else {
        "member": ref["member"], "root": X._repo_path(ref["root"]),
        "started_utc": ref["started_utc"]}
    out.update(state="queued", position=pos["position"],
               wait_s=pos["wait_s"], estimate=est, findings=found, plan=plan,
               reference=None if ref is None else {
                   "member": ref["member"], "root": str(ref["root"]),
                   "started_utc": ref["started_utc"]})
    runs = sb.eta_words(est["seconds"], est["seconds"])
    detail = f"It runs {runs} once it starts ({_timed_words(s['size'], recent)})"
    if not alive:
        detail += "."
    elif pos["wait_s"] >= 60:
        detail += (f" and starts in "
                   f"{sb.eta_words(pos['wait_s'], pos['wait_s'])}.")
    else:
        detail += ". It starts within a minute."
    detail += (f" While it runs it needs about {_h(est['peak_bytes'])} of "
               f"disk and keeps about {_h(est['keep_bytes'])}.")
    if ref is not None:
        detail += (f" Compared with the shipped replay of {p['season']} ("
                   + ("the Oracle SIHRS" if ref["member"] == "pf"
                      else "the Liu-West filter alone")
                   + ") on the cells both score.")
    elif not known:
        detail += " The reference is checked when the runner starts it."
    for x in found:
        said = f"{x['text']} ({x['code']})."
        detail += " " + (said if x["code"] == "NO_REFERENCE"
                         else f"Worth a look: {said}")
    detail += (f" FluBNF keeps {_h(FREE_FLOOR)} free on this disk; "
               f"{_h(free)} is free now.")
    if alive:
        text = f"Queued {eid}: {_ordinal(pos['position'])} in line on the runner."
    else:
        text = (f"Queued {eid}; the runner is not running, so it waits "
                "until it is started.")
    out.update(text=text, detail=detail,
               kind="ok" if alive and ref is not None else "warn")
    return out


def _already(out: dict, state: Mapping, name: str, eid: str,
             f: Path) -> dict:
    """enqueue's answer for a job queued already."""
    pos = _position(state, name, eid, f)
    return {**out, "state": "already", "kind": "info",
            "position": pos["position"], "wait_s": pos["wait_s"],
            "text": f"{eid} is already queued: "
                    f"{_ordinal(pos['position'])} in line."}


def stop(name: str, eid: str) -> str:
    """Stop a student's job: "dequeued" when it waited (QUEUED removed;
    a child in its claim window then stops before any fit), "stopping"
    when it replays (retro.request_stop: the fits in flight drain,
    finished weeks are kept, the week under way is refitted next time),
    "" otherwise."""
    from app.core import experiments as X
    from app.core import retro
    top = folder(name)
    if top is None or not isinstance(eid, str) or not X._ID_RE.fullmatch(eid):
        return ""
    f = top / "experiments" / eid
    if not (_is_dir(top / "experiments") and _is_dir(f)):
        return ""
    if _is_file(f / X.QUEUED):
        try:
            os.unlink(f / X.QUEUED)
            return "dequeued"
        except FileNotFoundError:
            pass                          # claimed meanwhile: it replays
    if X.status(f)["status"] in retro.ACTIVE_STATUSES:
        retro.request_stop(f)
        return "stopping"
    return ""


def busy_words() -> str:
    """What the main console on the runner computer says when its own
    experiment Start must wait: "the runner on this computer is
    replaying alice's <id>" while a running runner replays; "" else."""
    state = read_state()
    job = state.get("job") if state.get("alive") else None
    if not isinstance(job, Mapping) or job.get("kind") != "run":
        return ""
    return (f"the runner on this computer is replaying {job.get('folder')}'s "
            f"{job.get('id')}")


def _local_time(epoch, fmt: str) -> str:
    try:
        return time.strftime(fmt, time.localtime(float(epoch)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def storage(size: Callable[[Path], int] | None = None) -> dict:
    """The Storage tab's Student experiments, on the runner computer's main
    console: {"rows", "runner" (its line's parts), "down" (not running),
    "why" (the words then)}; no rows, no parts without a runner here.

    Rows go by student folder in name order, newest first within each
    (a folder whose settings or run record cannot be read safely is left
    out, as check would refuse it):
    {"ident" (<name>/<id>), "folder" (the name), "id", "path", "status"
    (experiments.status), "queued" (position's dict or None), "refused"
    (refusal), "parts" (a queued job's time queued, time and disk),
    "size" (bytes, by `size`, retro.dir_size when None), "size_h",
    "busy" (it replays, or it is the runner's job: no Delete), "why"
    (the words then)}."""
    out = {"rows": [], "runner": [], "down": False, "why": ""}
    if not state_dir().is_dir():
        return out
    from app.core import experiments as X
    from app.core import retro
    from app.core import sandbox as sb
    measure = size or retro.dir_size
    state = read_state()
    alive = bool(state.get("alive"))
    job = state.get("job") if alive else None
    base = _students()
    for name in folders():
        exp = base / name / "sandbox" / "experiments"
        rows = []
        for eid in _ids(exp):
            f = exp / eid
            s = _settings(f)
            st = _status(f) if s is not None else None
            if st is None:
                continue
            ident = f"{name}/{eid}"
            busy = st["status"] in retro.ACTIVE_STATUSES or _named(job, name, eid)
            why = ""
            if busy:
                why = (f"the runner is tidying {ident} (its weeks made lean, "
                       "its summary scored); try again in a minute"
                       if isinstance(job, Mapping) and _named(job, name, eid)
                       and job.get("kind") == "tidy" else
                       f"{ident} is replaying on the runner; stop it from its "
                       f"page in {name}'s console first.")
            queued = (_position(state, name, eid, f)
                      if st["queued"] and not _named(job, name, eid) else None)
            parts = []
            if queued is not None:
                try:
                    t = os.lstat(f / X.QUEUED).st_mtime
                except OSError:
                    t = None
                parts = [("queued again" if t == 0 else
                          f"queued {_local_time(t, '%m-%d %H:%M')}"),
                         f"runs {sb.eta_words(queued['seconds'], queued['seconds'])}",
                         f"needs about {_h(queued['peak_bytes'])}"]
            n = int(measure(f) or 0)
            try:
                mtime = os.lstat(f / X.SETTINGS).st_mtime
            except OSError:
                mtime = 0.0
            rows.append(((st["started_utc"] or _utc(mtime)), {
                "ident": ident, "folder": name, "id": eid, "path": f,
                "settings": s, "status": st, "queued": queued,
                "refused": refusal(name, eid), "parts": parts, "size": n,
                "size_h": _h(n), "busy": busy, "why": why}))
        rows.sort(key=lambda r: r[0], reverse=True)
        out["rows"] += [r for _key, r in rows]
    now_job = state.get("job") if isinstance(state.get("job"), Mapping) else None
    if now_job:
        out["runner"].append(
            f"The runner: {'tidying' if now_job.get('kind') == 'tidy' else 'replaying'} "
            f"{now_job.get('folder')}/{now_job.get('id')} since "
            f"{_local_time(_epoch(now_job.get('started_utc')), '%H:%M')}")
    elif state.get("waiting_why"):
        out["runner"].append(f"The runner: waiting: {state['waiting_why']}")
    else:
        out["runner"].append("The runner: idle")
    if state.get("waiting"):
        out["runner"].append(f"{len(state['waiting'])} waiting")
    out["runner"].append(f"{_h(_free())} free · FluBNF keeps "
                         f"{_h(FREE_FLOOR)} free")
    if not alive:
        last = _local_time(_epoch(state.get("heartbeat_utc")), "%m-%d %H:%M")
        out["down"] = True
        out["why"] = ((f"Its last heartbeat was at {last}. " if last else "")
                      + "Queued experiments wait until it is started: in a "
                      "Terminal of this account, run "
                      f"{Path(sb.REPO) / '.venv' / 'bin' / 'flubnf'} runner.")
    return out


# ----------------------------------------------------------- the supervisor


def _git(*args: str) -> tuple[int, str]:
    """(exit code, stdout stripped) of one git call in the install
    (sb.REPO); (-1, "") when git cannot be run."""
    from app.core import sandbox as sb
    try:
        r = subprocess.run(["git", *args], cwd=sb.REPO, capture_output=True,
                           text=True, timeout=30)
    except Exception:
        return -1, ""
    return r.returncode, (r.stdout or "").strip()


def _head() -> str:
    """The install's HEAD commit, "" when it cannot be read (then the
    supervisor never re-executes)."""
    code, out = _git("rev-parse", "HEAD")
    return out if code == 0 and re.fullmatch(r"[0-9a-f]{40,64}", out) else ""


def _install_problem() -> str:
    """Why the runner's install may not start jobs, "" when it may: it
    must be a checkout of main, from elyfmiller/flubnf, with no edits to
    tracked files (the launcher's own test) and no commit that is not on
    origin/main. One git call a check; the first that fails is said."""
    code, branch = _git("symbolic-ref", "--short", "HEAD")
    if code != 0:
        code, _out = _git("rev-parse", "--git-dir")
        return ("the runner's install is not a git checkout of main"
                if code != 0 else
                "the runner's install is on a detached HEAD, not main")
    if branch != "main":
        return f"the runner's install is on {branch}, not main"
    code, url = _git("remote", "get-url", "origin")
    if code != 0 or not _ORIGIN_RE.search(url):
        url = re.sub(r"//[^/@]*@", "//", url)      # never a token in words
        return (f"the runner's install's origin is {url or 'not set'}, not "
                "elyfmiller/flubnf")
    # no optional lock: a status every poll never holds .git/index.lock
    # against Ely's own git pull
    code, edits = _git("--no-optional-locks", "status", "--porcelain",
                       "--untracked-files=no")
    if code != 0 or edits:
        return ("the runner's install has edits to tracked files; it runs "
                "main only as merged")
    code, ahead = _git("rev-list", "--count", "origin/main..HEAD")
    if code != 0 or not ahead.isdigit():
        return "the runner's install cannot be compared with origin/main"
    n = int(ahead)
    if n:
        return (f"the runner's install has {n} commit{'s' if n != 1 else ''} "
                f"that {'are' if n != 1 else 'is'} not on origin/main")
    return ""


def _engine_ready() -> bool:
    """The particle-filter engine is installed here (the console's test,
    pipeline._pf_engine_state, which lives in app.ui)."""
    from flubnf.settings import PY_ENGINE, PYBNF
    from app.core.engines import pf
    return PY_ENGINE.exists() and PYBNF.exists() and pf.engine_available()


def _ps(columns: str) -> list[str]:
    """`ps -Ao <columns>`'s lines; [] when ps cannot be read. A command
    line that is not UTF-8 is read with its bad bytes replaced, so one
    process never hides the others."""
    try:
        r = subprocess.run(["ps", "-Ao", columns], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=10)
    except Exception:
        return []
    return (r.stdout or "").splitlines() if r.returncode == 0 else []


def _tree(pid: int) -> tuple[list[int], int]:
    """(the descendants of pid, parents before children; the RSS in bytes
    of pid and all of them) from one ps read."""
    kids: dict = {}
    rss: dict = {}
    for line in _ps("pid=,ppid=,rss="):
        try:
            p, parent, r = (int(x) for x in line.split())
        except ValueError:
            continue                      # a header or a torn line
        kids.setdefault(parent, []).append(p)
        rss[p] = r
    out, frontier = [], [int(pid)]
    while frontier:
        nxt = []
        for q in frontier:
            for child in kids.get(q, ()):
                if child not in out and child != pid:
                    out.append(child)
                    nxt.append(child)
        frontier = nxt
    return out, 1024 * (rss.get(int(pid), 0) + sum(rss.get(c, 0) for c in out))


def _descendants(pid: int) -> list[int]:
    return _tree(pid)[0]


def _tree_rss(pid: int) -> int:
    """RSS of a process and its descendants, in bytes (ps reads KiB; macOS
    counts no compressed memory)."""
    return _tree(pid)[1]


def _signal(pid: int, sig) -> None:
    try:
        os.kill(int(pid), sig)
    except (OSError, ValueError):
        pass                              # gone, or not ours to signal


def _registry() -> Path:
    return state_dir() / REGISTRY_FILE


def _kill_tree(proc) -> None:
    """Kill a job child's whole tree: its descendants read first (a dead
    parent's children are reparented), SIGTERM to the child and each of
    them (as pf._signal_tree signals), the job's registry swept (each
    recorded fit's group, SIGKILL after KILL_WAIT_S), then SIGKILL to
    whatever outlived KILL_WAIT_S."""
    from flubnf import cli
    kill = getattr(signal, "SIGKILL", signal.SIGTERM)
    kids = _descendants(proc.pid)
    try:
        proc.terminate()
    except Exception:
        pass
    for pid in kids:
        _signal(pid, signal.SIGTERM)
    cli._sweep_runner_groups(_registry(), wait=KILL_WAIT_S)
    try:
        proc.wait(KILL_WAIT_S)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
    except Exception:
        pass
    for pid in kids:
        if cli._pid_alive(pid):
            _signal(pid, kill)


class _Orphan:
    """A job child a runner that died left behind, as much of Popen as
    _kill_tree needs."""

    def __init__(self, pid: int):
        self.pid = int(pid)

    def poll(self):
        from flubnf.cli import _pid_alive
        return None if _pid_alive(self.pid) else 0

    def terminate(self):
        _signal(self.pid, signal.SIGTERM)

    def kill(self):
        _signal(self.pid, getattr(signal, "SIGKILL", signal.SIGTERM))

    def wait(self, timeout=None):
        end = time.monotonic() + (timeout or 0.0)
        while self.poll() is None:
            if time.monotonic() >= end:
                raise subprocess.TimeoutExpired("job", timeout)
            time.sleep(0.1)
        return 0


def _replay_elsewhere() -> str:
    """Why the queue waits for a replay on this computer, "" when none
    runs: (a) a run record under way in the install's retro root
    (APP_STATE/retro/*), its own Sandbox's experiments, or any student's
    experiments (records read only when regular files under FILE_MAX,
    cached by stat), or (b) a live process running a retro week runner
    (runner_<n>.py, one ps read). Sandbox fits and console runs
    (pf_runner_<n>.py) never hold the queue."""
    from app.core import retro, runs
    from app.core import sandbox as sb
    places = []
    rr = runs.APP_STATE / "retro"
    try:
        names = sorted(os.listdir(rr))
    except OSError:
        names = []
    for n in names:
        if (rr / n).is_dir():             # the install's own trees
            places.append(((f"the shipped replay of {n}"
                            if _SEASON_RE.fullmatch(n) else f"the replay {n}"),
                           rr / n, True))
    for eid in _ids(sb.SANDBOX / "experiments"):
        places.append((f"the experiment {eid} on the main console",
                       sb.SANDBOX / "experiments" / eid, False))
    for name in folders():
        exp = _students() / name / "sandbox" / "experiments"
        for eid in _ids(exp):
            places.append((f"{name}'s {eid}", exp / eid, False))
    for what, p, follow in places:
        meta = _record(p, follow=follow)
        try:
            if meta and retro.effective_status(meta) in retro.ACTIVE_STATUSES:
                return f"a replay is running on this computer ({what})"
        except (TypeError, ValueError):
            continue                      # a damaged record runs nothing
    for line in _ps("pid=,command="):
        pid, _sp, cmd = line.strip().partition(" ")
        if any(_RUNNER_PY_RE.fullmatch(os.path.basename(t))
               for t in cmd.split()):
            return (f"a replay is running on this computer (its fits, "
                    f"pid {pid})")
    return ""


def _start_problem() -> str:
    """Why `flubnf runner` may not start here, "" when it may."""
    from app.core import sandbox as sb
    try:
        import fcntl  # noqa: F401
        posix = hasattr(os, "killpg")
    except ImportError:
        posix = False
    if _in_students(sb.REPO):
        return ("this is a student's clone; the runner runs from the main "
                "install only.")
    if not _students().is_dir():
        return (f"{STUDENTS} is missing: make it, and clone each student's "
                "fork into it (~/Students/<name>).")
    if not posix:
        return ("the runner needs flock and killpg, which this computer "
                "lacks; it runs on the students' Mac.")
    return ""


def _lock() -> int | None:
    """runner.lock held (flock, exclusive, not waiting): its descriptor,
    or None when another runner holds it. The kernel drops it when the
    process dies, and the descriptor closes at an exec (Python opens
    files close-on-exec), so a re-executed runner takes it again."""
    import fcntl
    fd = os.open(state_dir() / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def _supervisor() -> dict:
    """A new supervisor's state: what runner.json says (its pid and build,
    its retro root, why the queue waits, the job and the waiting) and
    what only it keeps (the estimates, the tidy rotation). recent and the
    job of a runner that died come from the runner.json it left."""
    from app.core import runs
    old = read_state()
    head = _head()
    return {"pid": os.getpid(), "head": head, "build": head[:7],
            "started_utc": _utc(_now()),
            "retro_root": str(runs.APP_STATE / "retro"), "waiting_why": "",
            "job": None, "waiting": [],
            "recent": list(old.get("recent") or [])[:RECENT_MAX],
            "recent_n": 0, "left": old.get("job"), "estimates": {}, "why": {},
            "tidy_at": {}, "tidy_due": set()}


def _write_state(sv: dict) -> None:
    """runner.json, atomically (beside, then replaced; whatever stood at
    the tmp path removed first, so a link there is never written
    through): the heartbeat now. A failed write is said on stdout and
    never stops the supervisor."""
    obj = {"format_version": STATE_VERSION, "pid": sv["pid"],
           "build": sv["build"], "started_utc": sv["started_utc"],
           "heartbeat_utc": _utc(_now()), "retro_root": sv["retro_root"],
           "waiting_why": sv["waiting_why"], "job": sv["job"],
           "waiting": sv["waiting"], "recent": sv["recent"][:RECENT_MAX]}
    p = state_dir() / STATE_FILE
    tmp = p.with_name(p.name + ".tmp")
    try:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        with open(tmp, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(obj, indent=1, sort_keys=True) + "\n")
        os.replace(tmp, p)
    except OSError as e:
        _say(f"runner.json not written: {e}")


def _recent(sv: dict, job: Mapping, outcome: str, text: str = "", *,
            seconds: float = 0.0, weeks: int = 0, k: float | None = None,
            rss_peak: int = 0, disk_peak: int = 0) -> None:
    """A recent entry, newest first, at most RECENT_MAX kept."""
    sv["recent"].insert(0, {
        "folder": job["folder"], "id": job["id"], "size": job.get("size", ""),
        "kind": job.get("kind", "run"), "utc": _utc(_now()),
        "outcome": outcome, "text": text, "seconds": round(seconds, 1),
        "weeks": int(weeks), "k": None if k is None else round(k, 3),
        "rss_peak": int(rss_peak), "disk_peak": int(disk_peak)})
    del sv["recent"][RECENT_MAX:]
    sv["recent_n"] = sv.get("recent_n", 0) + 1


def _waiting(sv: dict) -> list[dict]:
    """runner.json's waiting: queue() but the runner's job, each with its
    estimate (cached by its experiment.json's and run record's stat:
    settings and stat calls only, never the model) and why it waits."""
    from app.core import experiments as X
    out = []
    base = _students()
    for q in queue():
        key = (q["folder"], q["id"])
        if _named(sv["job"], *key):
            continue
        f = base / q["folder"] / "sandbox" / "experiments" / q["id"]
        stamp = []
        for n in (X.SETTINGS, "run_meta.json"):
            try:
                st = os.lstat(f / n)
                stamp.append((st.st_mtime_ns, st.st_size))
            except OSError:
                stamp.append(None)
        hit = sv["estimates"].get(key)
        if hit is None or hit[0] != (stamp, sv["recent_n"]):
            hit = ((stamp, sv["recent_n"]), _estimate_of(f, sv["recent"]))
            sv["estimates"][key] = hit
        est = hit[1]
        out.append({**q, "seconds": est.get("seconds", 0.0),
                    "measured": bool(est.get("measured")),
                    "peak_bytes": int(est.get("peak_bytes", 0)),
                    "keep_bytes": int(est.get("keep_bytes", 0)),
                    "why": sv["why"].get(key, "")})
    return out


def _reexec(sv: dict) -> None:
    """Start again on the install's new HEAD, between jobs only, so the
    supervisor and its children always run one build. Nothing when HEAD
    cannot be read."""
    head = _head()
    if not head or not sv["head"] or head == sv["head"]:
        return
    _say(f"the install moved to {head[:7]}: starting again on it")
    _write_state(sv)
    sys.stdout.flush()
    try:
        os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])
    except OSError as e:
        sv["head"] = head                 # go on as this build; never loop
        _say(f"not started again: {e}")


def _dispatch(sv: dict) -> None:
    """One poll while no job runs: runner.json written with the waiting
    and their estimates; a new HEAD re-executed; the queue held, with
    waiting_why, while the install is not a clean main, the engine is
    missing or a replay runs elsewhere; else the waiting taken in order,
    each checked (a refusal takes it out of the queue, in recent) and
    held for disk on its own (free − peak must keep FREE_FLOOR, so a
    smaller job can pass a full that does not fit), the first that
    passes run to its end. With nothing held and nothing run, one idle
    folder tidied (a tidy is a child too: a held queue starts none)."""
    from app.core.problem_codes import Refusal
    sv["waiting"] = _waiting(sv)
    _reexec(sv)
    why = (_install_problem()
           or ("" if _engine_ready() else
               "the particle-filter engine is not installed on the runner")
           or _replay_elsewhere())
    if why != sv["waiting_why"] and why:
        _say(f"waiting: {why}")
    sv["waiting_why"] = why
    _write_state(sv)
    if why:
        return
    for job in list(sv["waiting"]):
        key = (job["folder"], job["id"])
        try:
            f = check(*key)
        except Refusal as e:
            _refused(sv, job, _said(e))
            sv["waiting"].remove(job)
            continue
        free = _free()
        if free - job["peak_bytes"] < FREE_FLOOR:
            job["why"] = sv["why"][key] = (
                f"waiting for disk: it needs about {_h(job['peak_bytes'])}, "
                f"and leaving {_h(FREE_FLOOR)} free allows "
                f"{_h(max(0, free - FREE_FLOOR))} now")
            continue
        job["why"] = ""
        sv["why"].pop(key, None)
        _run(sv, {**job, "kind": "run"}, f)
        return
    _write_state(sv)
    _tidy(sv)


def _refused(sv: dict, job: Mapping, said: str) -> None:
    """A job check refuses at dispatch: out of the queue (its QUEUED
    removed, the folder a folder itself), in recent with the words."""
    from app.core import experiments as X
    try:
        f = _job_folder(job["folder"], job["id"])
        if _is_file(f / X.QUEUED):
            os.unlink(f / X.QUEUED)
    except Exception:
        pass
    _say(f"refused {job['folder']}/{job['id']}: {said}")
    _recent(sv, job, "refused", said)
    sv["why"].pop((job["folder"], job["id"]), None)


def _caffeinate(pid: int):
    """macOS: `caffeinate -i -w <pid>` keeps the computer awake while the
    child lives (pipeline._sleep_guard's pattern); None elsewhere."""
    if sys.platform != "darwin":
        return None
    try:
        return subprocess.Popen(["caffeinate", "-i", "-w", str(pid)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except Exception:
        return None


def _spawn(sv: dict, job: Mapping, f: Path) -> dict:
    """Start a job child (or a tidy child): runner.json's job written
    first, so a console's Delete sees it; then `<this python> -I -c
    JOB_ENTRY run <students> <name> <id> <size>` (tidy: `tidy <students>
    <name> <id>`) in its own session, in the runner's folder, with no
    PYTHON* variable (the engine runners it starts run without -I), its
    output in job.log (made anew: a link left there is removed, never
    written through); then caffeinate. What the watch needs."""
    from app.core import experiments as X
    lim = limits(job["size"] if job["kind"] == "run" else "pilot")
    now = _now()
    est = job.get("seconds") if job["kind"] == "run" else None
    sv["job"] = {"kind": job["kind"], "folder": job["folder"], "id": job["id"],
                 "size": job.get("size", ""), "pid": None,
                 "started_utc": _utc(now), "seconds": est, "eta_s": est,
                 "peak_bytes": int(job.get("peak_bytes", 0)),
                 "keep_bytes": int(job.get("keep_bytes", 0)),
                 "rss_bytes": 0, "disk_bytes": 0,
                 "limits": {"seconds": lim.seconds, "memory": lim.memory,
                            "disk": lim.disk}}
    sv["waiting"] = [w for w in sv["waiting"]
                     if not _named(w, job["folder"], job["id"])]
    _write_state(sv)
    meta = X._meta(f)
    argv = [job["kind"], str(_students()), job["folder"], job["id"]]
    if job["kind"] == "run":
        argv.append(job["size"])
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    if os.path.lexists(state_dir() / LOG_FILE):
        os.unlink(state_dir() / LOG_FILE)
    with open(state_dir() / LOG_FILE, "x", encoding="utf-8",
              newline="\n") as log:
        proc = subprocess.Popen([sys.executable, "-I", "-c", JOB_ENTRY, *argv],
                                cwd=str(state_dir()), env=env,
                                stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT,
                                start_new_session=True)
    sv["job"]["pid"] = proc.pid
    _write_state(sv)
    _say(f"{'started' if job['kind'] == 'run' else 'tidying'} "
         f"{job['folder']}/{job['id']}"
         + (f" ({job['size']}, pid {proc.pid})" if job["kind"] == "run"
            else f" (pid {proc.pid})"))
    return {"job": job, "folder": f, "proc": proc, "limits": lim, "t0": now,
            "caffeinate": _caffeinate(proc.pid), "rss_peak": 0,
            "disk_peak": 0, "next_disk": now, "next_beat": now + POLL_S,
            "why": "", "outcome": "", "requeue": False,
            "finished": meta.get("finished_utc"),
            "week_seconds": dict(meta.get("week_seconds") or {})}


def _run(sv: dict, job: Mapping, f: Path) -> None:
    """Run one job (or tidy) to its end: spawned, watched every WATCH_S,
    then recorded (_after). A job that cannot be started leaves the queue
    (so it cannot loop); one the watch fails on is killed and recorded
    like any other."""
    from app.core import experiments as X
    try:
        run = _spawn(sv, job, f)
    except Exception as e:
        sv["job"] = None
        _say(f"{job['folder']}/{job['id']} not started: {e}")
        if job["kind"] == "run":
            if _is_file(f / X.QUEUED):
                os.unlink(f / X.QUEUED)
            _recent(sv, job, "ended", f"The runner could not start it: {e}. "
                    "Resume queues it again.")
        _write_state(sv)
        return
    try:
        while not _watch(sv, run):
            _sleep(WATCH_S)
    except Exception as e:
        run["outcome"] = "ended"
        run["why"] = (f"The runner stopped it: it could not watch it ({e}). "
                      "Finished weeks are kept; Resume queues it again.")
        _say(f"{job['folder']}/{job['id']}: {run['why']}")
        _kill_tree(run["proc"])
    _after(sv, run)


def _limit_words(run: dict, now: float) -> str:
    """The words of the first limit the job is past, "" while none."""
    from app.core import retro
    from app.core import sandbox as sb
    lim, job = run["limits"], run["job"]
    size = job.get("size") if job["kind"] == "run" else "pilot"
    again = "Finished weeks are kept; Resume queues it again."
    if now - run["t0"] > lim.seconds:
        return (f"The runner stopped it at its time limit: a {size} "
                f"experiment may run {sb.clock(lim.seconds)} at a time. "
                f"{again}")
    rss = _tree_rss(run["proc"].pid)
    run["rss_peak"] = max(run["rss_peak"], rss)
    run["rss"] = rss
    if rss > lim.memory:
        return (f"The runner stopped it: its fits used {_h(rss)} of memory, "
                f"and a {size} experiment may use {_h(lim.memory)}. {again}")
    if now >= run["next_disk"]:
        run["next_disk"] = now + DISK_EVERY_S
        disk = retro.dir_size(run["folder"])
        run["disk_peak"] = max(run["disk_peak"], disk)
        run["disk"] = disk
        if disk > lim.disk:
            return (f"The runner stopped it: its folder reached {_h(disk)}, "
                    f"and a {size} experiment may hold {_h(lim.disk)}. "
                    f"{again}")
        if _free() < FREE_FLOOR:
            return (f"The runner stopped it: this disk fell below "
                    f"{_h(FREE_FLOOR)} free, which FluBNF keeps free. "
                    "Finished weeks are kept; Resume queues it again once "
                    "there is room.")
    return ""


def _watch(sv: dict, run: dict) -> bool:
    """One watch of a running job, True once it has ended: a stop of the
    supervisor kills it (to be queued again), a child the same signal
    ended (a logout's, a pkill's) included; PAUSE removed (the queue
    has no pause); wall time and the tree's RSS every watch, the folder
    and the free disk every DISK_EVERY_S, the job's tree killed at once
    at the first limit; the heartbeat, the eta and the waiting (jobs
    queued or taken out meanwhile) every POLL_S."""
    from app.core import retro
    proc, job = run["proc"], sv["job"]
    code = proc.poll()
    if _stopping and code != 0:
        run["requeue"] = True
        _say(f"stopping {job['folder']}/{job['id']}: the runner is stopping")
        if code is None:
            _kill_tree(proc)              # else _after's sweep finds its fits
        return True
    if code is not None:
        return True
    if job["kind"] == "run":
        try:
            retro.clear_pause(run["folder"])
        except OSError:
            pass
    now = _now()
    why = _limit_words(run, now)
    job["rss_bytes"] = int(run.get("rss", 0))
    job["disk_bytes"] = int(run.get("disk", 0))
    if why:
        run["why"], run["outcome"] = why, "limit"
        _kill_tree(proc)
        return True
    if now >= run["next_beat"]:
        run["next_beat"] = now + POLL_S
        if job["kind"] == "run":
            try:
                eta = (_status(run["folder"]) or {}).get("eta_s")
            except Exception:
                eta = None
            est = run["job"].get("seconds")
            job["eta_s"] = (round(eta, 1) if eta is not None else
                            None if est is None else
                            round(max(0.0, _num(est) - (now - run["t0"])), 1))
        try:
            sv["waiting"] = _waiting(sv)
        except Exception as e:            # the heartbeat goes on regardless
            _say(f"the waiting not read: {e}")
        _write_state(sv)
    return False


def _last_line() -> str:
    """job.log's last line that says anything ("" for none)."""
    try:
        with open(state_dir() / LOG_FILE, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    return next((x.strip() for x in reversed(lines) if x.strip()), "")


def _segment_k(meta: Mapping, before: Mapping) -> tuple[int, float | None]:
    """(weeks fitted in the segment, its k): Σ the new week_seconds over
    Σ ⌈F/W⌉·c(n_w) of those weeks, F the record's locations times
    replicates; k None with no week fitted."""
    st = meta.get("settings") if isinstance(meta.get("settings"), Mapping) else {}
    new = {w: _num(s) for w, s in (meta.get("week_seconds") or {}).items()
           if before.get(w) != s and isinstance(w, str)
           and _DATE_RE.fullmatch(w)}
    if not new:
        return 0, None
    try:
        season = str(meta.get("season") or st.get("season"))
        fits = len(st.get("locations") or ()) * int(st.get("replicates") or 0)
        den = sum(_week_cost(season, w, fits, int(st.get("particles") or 10_000))
                  for w in new)
    except (TypeError, ValueError):
        return len(new), None
    return len(new), (sum(new.values()) / den if den > 0 else None)


def _close(f: Path, why: str) -> None:
    """Close a run record whose worker is dead (killed or crashed; the
    supervisor is then its only writer): stopped, with why, its time
    stopping at its last heartbeat, finished now, its weeks counted.
    Nothing when the record is not a regular file (_writable_record)."""
    from app.core import retro
    with retro._META_LOCK:
        if not _writable_record(f):
            return
        m = retro.read_meta(f)
        if not m:
            return
        m["elapsed_s"] = retro.elapsed_now(m)
        m["segment_start_utc"] = None
        m["status"] = "stopped"
        m["stop_reason"] = str(why)
        m["finished_utc"] = retro._now()
        m["weeks_completed"] = retro._weeks_on_disk(f)
        retro.write_meta(f, m)


def _reset_unfinished(f: Path) -> int:
    """Remove every date-named entry of weeks/ that is not a stored week
    (retro.delete_tree: a link loses only itself), so no prepared cell
    outlives its segment and an unfinished week is fitted from its
    start. How many were removed."""
    from app.core import retro
    weeks = Path(f) / "weeks"
    if not _is_dir(weeks):
        return 0
    n = 0
    for name in sorted(os.listdir(weeks)):
        p = weeks / name
        if not _DATE_RE.fullmatch(name):
            continue
        if p.is_symlink() or (_is_dir(p) and not retro.week_done(f, name)):
            retro.delete_tree(p)
            n += 1
    return n


def _requeue(f: Path) -> None:
    """QUEUED set again with mtime 0: the job goes first (never through
    a link, never waiting on a pipe)."""
    from app.core import experiments as X
    try:
        fd = os.open(f / X.QUEUED, os.O_WRONLY | os.O_CREAT
                     | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0), 0o644)
        os.close(fd)
        os.utime(f / X.QUEUED, (0, 0))
    except OSError as e:
        _say(f"{f.name} not queued again: {e}")


def _settle(f: Path, why: str, *, live: bool, requeue: bool) -> None:
    """A job's folder after its child: the record closed with why when it
    still claims a live worker, unfinished weeks removed, STOP and PAUSE
    cleared, QUEUED removed (whatever stands there but a folder), and set
    again with mtime 0 when requeue (unless STOP stood)."""
    from app.core import experiments as X
    from app.core import retro
    stood = retro.stop_path(f).exists()
    if live:
        _close(f, _PAGE_STOP if requeue and stood else why)
    _reset_unfinished(f)
    retro.clear_flags(f)
    if os.path.lexists(f / X.QUEUED) and not _is_dir(f / X.QUEUED):
        os.unlink(f / X.QUEUED)
    if requeue and not stood:
        _requeue(f)


def _after(sv: dict, run: dict) -> None:
    """After a job's child ends: its registry swept (orphaned fits); its
    record closed when it still claims a live worker, a page Stop given
    its words, unfinished weeks removed, flags cleared, QUEUED removed (or
    set again with mtime 0 at a supervisor stop, unless STOP stands); a
    recent entry (outcome, words, seconds, weeks fitted, the segment's k,
    the peaks); the folder due for tidy. A tidy child leaves its folder
    looked at."""
    from app.core import retro
    from app.core.problem_codes import Refusal
    from flubnf import cli
    proc, job = run["proc"], run["job"]
    try:
        code = proc.wait()
    except Exception:
        code = -1
    caff = run.get("caffeinate")
    if caff is not None:
        try:
            if caff.poll() is None:
                caff.terminate()
            caff.wait(5)
        except Exception:
            pass
    cli._sweep_runner_groups(_registry())
    key = (job["folder"], job["id"])
    sv["job"] = None
    seconds = _now() - run["t0"]
    if job["kind"] == "tidy":
        _say(f"tidied {key[0]}/{key[1]} (exit code {code})"
             + (f": {run['why']}" if run["why"] else ""))
        sv["tidy_at"][key] = _now()
        _write_state(sv)
        return
    try:
        f = _job_folder(*key)
    except Refusal:
        f = None
    meta = _record(f) if f is not None else {}
    status = str(meta.get("status") or "")
    live = status in retro.ACTIVE_STATUSES
    last = _last_line()
    outcome, text = run["outcome"], run["why"]
    if run["requeue"]:
        stood = f is not None and retro.stop_path(f).exists()
        outcome, text = "stopped", _PAGE_STOP if stood else _RUNNER_STOP
    elif outcome:
        pass                              # a limit: its words
    elif code == 3:
        outcome, text = "refused", last
    elif code == 0 and last == "complete":
        outcome = "complete"
    elif code == 0 and status == "done":
        outcome = "done"
    elif code == 0 and status == "stopped":
        outcome, text = "stopped", str(meta.get("stop_reason") or _PAGE_STOP)
    elif code == 0 and status.startswith("error"):
        outcome, text = "ended", status.partition(":")[2].strip()
    elif code == 0:
        outcome = "done"
    else:
        outcome, text = "ended", (
            f"It ended unexpectedly (exit code {code}). Finished weeks are "
            "kept; Resume queues it again.")
    if f is not None:
        try:
            if (not live and status == "stopped"
                    and not meta.get("stop_reason")
                    and meta.get("finished_utc") != run["finished"]
                    and _writable_record(f)):
                retro._record_stop_reason(f, _PAGE_STOP)
            _settle(f, text or "It ended unexpectedly. Finished weeks are "
                    "kept; Resume queues it again.", live=live,
                    requeue=run["requeue"])
            meta = _record(f)
            run["disk_peak"] = max(run["disk_peak"], retro.dir_size(f))
        except Exception as e:
            _say(f"{key[0]}/{key[1]} not settled: {e}")
    weeks, k = _segment_k(meta, run["week_seconds"])
    _recent(sv, job, outcome, text, seconds=seconds, weeks=weeks, k=k,
            rss_peak=run["rss_peak"], disk_peak=run["disk_peak"])
    sv["tidy_due"].add(key)
    _say(f"{outcome} {key[0]}/{key[1]}: {weeks} week{'s' if weeks != 1 else ''}"
         f" in {round(seconds)} s" + (f": {text}" if text else ""))
    _write_state(sv)


def _recover(sv: dict) -> None:
    """At the start: a job a runner that died left behind. Its child, when
    it still lives (its pid's command line runs job_main), is killed with
    its tree; the registry is swept; a record that still claims a live
    worker is closed, its unfinished weeks removed, and the job queued
    again first unless STOP stands. No attempt is counted."""
    from app.core import retro
    from app.core.problem_codes import Refusal
    from flubnf import cli
    left = sv.pop("left", None)
    if not isinstance(left, Mapping):
        cli._sweep_runner_groups(_registry())
        return
    try:
        pid = int(left.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if (pid > 0 and cli._pid_alive(pid)
            and "app.core.runner import job_main" in cli._pid_cmdline(pid)):
        _say(f"killing the job a runner left: pid {pid}")
        _kill_tree(_Orphan(pid))
    cli._sweep_runner_groups(_registry())
    if left.get("kind") != "run" or not isinstance(left.get("folder"), str):
        return
    key = (left["folder"], str(left.get("id")))
    try:
        f = _job_folder(*key)
    except Refusal:
        return
    meta = _record(f)
    if str(meta.get("status") or "") not in retro.ACTIVE_STATUSES:
        _reset_unfinished(f)
        return
    words = "The runner restarted while it replayed; it was queued again."
    stood = retro.stop_path(f).exists()
    _settle(f, words, live=True, requeue=True)
    job = {"folder": key[0], "id": key[1], "size": left.get("size", ""),
           "kind": "run"}
    _recent(sv, job, "ended", _PAGE_STOP if stood else words)
    sv["tidy_due"].add(key)
    _say(f"recovered {key[0]}/{key[1]}"
         + ("" if stood else ": queued again first"))
    _write_state(sv)


# ------------------------------------------------------------------- tidy


def _tidy_needed(f: Path, retro_root: Path) -> bool:
    """Whether an idle folder needs a tidy: its summary no longer holds
    against the runner's retro root (experiments.stale, which keeps the
    shipped replay inside it), a stored week still holds its samples, or
    a week folder is unfinished. Stat calls and stale's reads."""
    from app.core import experiments as X
    from app.core import retro
    from app.core import retro_store as RS
    if X.stale(f, retro_root=retro_root):
        return True
    weeks = Path(f) / "weeks"
    if not _is_dir(weeks):
        return False
    for name in sorted(os.listdir(weeks)):
        if not _DATE_RE.fullmatch(name):
            continue
        if (RS.samples_file(weeks / name) is not None
                or not retro.week_done(f, name)):
            return True
    return False


def _tidy(sv: dict) -> None:
    """Look at one idle folder (not under way, not queued, not the
    runner's job): those whose job just ended first, then the rest in
    turn, each at most every TIDY_EVERY_S. A folder check refuses, or
    whose run record cannot be read safely (_status), is left as it is;
    one that needs it (_tidy_needed) gets a tidy child under the pilot's
    limits."""
    from app.core import experiments as X
    from app.core import retro
    from app.core.problem_codes import Refusal
    now = _now()
    base = _students()
    seen = []
    for name in folders():
        for eid in _ids(base / name / "sandbox" / "experiments"):
            seen.append((name, eid))
    due = [c for c in seen if c in sv["tidy_due"]]
    rest = [c for c in seen if c not in sv["tidy_due"]
            and now - sv["tidy_at"].get(c, -math.inf) >= TIDY_EVERY_S]
    for key in due + rest:
        f = base / key[0] / "sandbox" / "experiments" / key[1]
        if _named(sv["job"], *key) or _is_file(f / X.QUEUED):
            continue
        st = _status(f)
        if st is None or st["status"] in retro.ACTIVE_STATUSES:
            continue
        sv["tidy_due"].discard(key)
        sv["tidy_at"][key] = now
        try:
            f = check(*key)
        except Refusal as e:
            _say(f"not tidied {key[0]}/{key[1]}: {_said(e)}")
            return
        if _tidy_needed(f, Path(sv["retro_root"])):
            s = _settings(f) or {}
            _run(sv, {"kind": "tidy", "folder": key[0], "id": key[1],
                      "size": s.get("size", "")}, f)
        return


# --------------------------------------------------------------- serve


def serve() -> int:
    """`flubnf runner`: work this computer's student experiment queue, one
    job at a time, until SIGTERM or SIGINT; the exit code.

    Refused (1, in words on stderr) from a student's clone, with
    STUDENTS missing, without flock or killpg (Windows), and while
    another runner holds runner.lock. Otherwise it recovers what a runner
    that died left, then polls every POLL_S (_dispatch). A stop kills the
    running job's tree and queues it again first, writes runner.json and
    exits 0."""
    global _stopping
    why = _start_problem()
    if why:
        print(f"Not started: {why}", file=sys.stderr, flush=True)
        return 1
    state_dir().mkdir(exist_ok=True)
    fd = _lock()
    if fd is None:
        pid = read_state().get("pid")
        print("A runner already works this computer's queue"
              + (f" (pid {pid})." if pid else "."), file=sys.stderr, flush=True)
        return 1
    _stopping = False
    previous = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, _on_signal)
    except ValueError:
        pass                              # not the main thread
    try:
        sv = _supervisor()
        _say(f"runner {sv['pid']} on build {sv['build'] or 'unknown'}: "
             f"{_students()}")
        try:
            _recover(sv)
        except Exception:                 # said; the queue is worked anyway
            _say("the job a runner left not recovered:")
            traceback.print_exc(file=sys.stdout)
        while not _stopping:
            try:
                _dispatch(sv)
            except Exception:
                # one poll that fails (an unreadable folder, a full disk)
                # is said, and the next tries again
                _say("a poll failed:")
                traceback.print_exc(file=sys.stdout)
            if not _stopping:
                _sleep(POLL_S)
        sv["waiting"] = _waiting(sv)
        _write_state(sv)
        _say("runner stopped")
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        os.close(fd)
        _stopping = False
    return 0


# --------------------------------------------------------------- the child


@contextmanager
def _as_folder(name: str):
    """The child's Sandbox, one student's folder for its whole life:
    sb.SANDBOX, MODELS and RUNS from check(name), the fits' registry
    (pf.RUNNER_PIDS_FILE) in the runner's folder. Put back on exit (the
    tests run job_main in their own process)."""
    from app.core import sandbox as sb
    from app.core.engines import pf
    top = check(name)
    saved = (sb.SANDBOX, sb.MODELS, sb.RUNS, pf.RUNNER_PIDS_FILE)
    sb.SANDBOX, sb.MODELS, sb.RUNS = top, top / "models", top / "runs"
    pf.RUNNER_PIDS_FILE = state_dir() / REGISTRY_FILE
    try:
        yield top
    finally:
        sb.SANDBOX, sb.MODELS, sb.RUNS, pf.RUNNER_PIDS_FILE = saved


def _job_hooks(name: str, eid: str, f: Path):
    """(cancelled, after_week) for experiments.run in the child.

    cancelled(), before every week not yet stored: True once the
    supervisor is gone (the parent pid changed: it died without its stop,
    a closed Terminal or a crash), the job then queued again first unless
    STOP stands, as the supervisor's stop would have done (decided here:
    the child's end clears STOP); at its first call it
    claims the job by removing QUEUED, and a flag already gone (the
    student withdrew it) stops before anything is fitted; check() before
    every week, its refusal recorded as the stop's reason; and the week
    about to be fitted, when a folder of it stands, removed, so it is
    fitted from its start.

    after_week(asof), after every week, stored, skipped or failed: a
    stored week made lean (drop_samples), a failed one removed whole (its
    words are in failures.log). It only logs: a raising progress
    callback would end run_season.

    The stop's reason, QUEUED set again, a week's drop and its removal
    are written only while f is still the experiment's folder and its
    weeks/ a folder itself (ours): a folder on the way swapped for a link
    while a week fits is left alone, and the next week's check stops the
    job."""
    from app.core import experiments as X
    from app.core import retro
    from app.core.problem_codes import Refusal
    ppid = os.getppid()
    seen = {"claimed": False, "last": None}

    def upcoming() -> str:
        st = _record(f).get("settings")
        weeks = X._weeks(st) if isinstance(st, dict) else []
        if seen["last"] in weeks:
            weeks = weeks[weeks.index(seen["last"]) + 1:]
        return next((w for w in weeks if not retro.week_done(f, w)), "")

    def ours(weeks: bool = False) -> bool:
        try:
            if _job_folder(name, eid) != f:
                return False
        except Refusal as e:
            print(f"runner: {_said(e)}", file=sys.stderr, flush=True)
            return False
        return not weeks or _is_dir(f / "weeks")

    def recorded(why: str) -> None:
        with retro._META_LOCK:              # the heartbeat's writes wait
            if ours() and _writable_record(f):
                retro._record_stop_reason(f, why)

    def cancelled() -> bool:
        if os.getppid() != ppid:
            stood = retro.stop_path(f).exists()
            recorded(_PAGE_STOP if stood else _RUNNER_STOP)
            if not stood and ours():
                _requeue(f)
            return True
        if not seen["claimed"]:
            try:
                os.unlink(f / X.QUEUED)
            except OSError:               # gone: the student withdrew it
                return True
            seen["claimed"] = True
        asof = upcoming()
        try:
            check(name, eid)
        except Refusal as e:
            words = " ".join(str(e).split()).rstrip(".")
            recorded(f"The runner stopped it before {asof or 'its next week'}"
                     f": {words}. Finished weeks are kept.")
            return True
        wd = f / "weeks" / asof
        if asof and os.path.lexists(wd):
            retro.delete_tree(wd)
        return False

    def after_week(asof: str) -> None:
        seen["last"] = asof
        try:
            if not isinstance(asof, str) or not _DATE_RE.fullmatch(asof):
                return
            if not ours(weeks=True):
                print(f"runner: {asof} left as it is: experiments/{eid} "
                      "or its weeks folder is no longer a folder itself",
                      file=sys.stderr, flush=True)
                return
            if retro.week_done(f, asof):
                X.drop_samples(f, asof)
            else:
                wd = f / "weeks" / asof
                if os.path.lexists(wd):
                    retro.delete_tree(wd)
        except Exception as e:
            print(f"runner: {asof} not made lean: {e}", file=sys.stderr,
                  flush=True)
    return cancelled, after_week


def _tidy_main(f: Path, retro_root: Path) -> int:
    """The tidy child, after its check and reset: every stored week made
    lean, then the summary scored again when it no longer holds
    (flubnf_build None keeps the build that ran)."""
    from app.core import experiments as X
    from app.core import retro
    st = X._meta(f).get("settings")
    for w in (X._weeks(st) if isinstance(st, dict) else []):
        if retro.week_done(f, w):
            X.drop_samples(f, w)
    if X.stale(f, retro_root=retro_root):
        X.score(f, retro_root=retro_root, flubnf_build=None)
    return 0


def job_main(argv: Sequence[str]) -> int:
    """The job child (JOB_ENTRY): `run <students> <name> <id> <size>` or
    `tidy <students> <name> <id>`; the exit code: 0 when the run returned
    or stopped (SeasonStopped, EngineBuildChanged: the record says what
    happened) and for a complete experiment ("complete" printed), 3 for a
    refusal (its words the last line on stderr), 1 for anything else.

    First RLIMIT_FSIZE is set to the size's disk limit (a tidy: the
    pilot's), inherited by every process it starts; then STUDENTS is the
    supervisor's. The Sandbox is the student's folder (_as_folder); its
    unfinished weeks are removed before the folder is checked (check),
    so an unfinished week is fitted from its start; then the preflight
    against the install's retro root (APP_STATE/retro, as `flubnf retro`
    finds it), and experiments.run with _job_hooks. A tidy makes the
    stored weeks lean and scores again (_tidy_main). STOP and PAUSE are
    cleared at the end."""
    global STUDENTS
    import resource
    argv = list(argv)
    kind = argv[0] if argv else ""
    if not ((kind == "run" and len(argv) == 5 and argv[4] in LIMITS)
            or (kind == "tidy" and len(argv) == 4)):
        print(f"runner: not a job: {_shown(argv)}", file=sys.stderr, flush=True)
        return 1
    disk = LIMITS[argv[4] if kind == "run" else "pilot"].disk
    resource.setrlimit(resource.RLIMIT_FSIZE, (disk, disk))
    STUDENTS = Path(argv[1])
    name, eid = argv[2], argv[3]
    from app.core import experiments as X
    from app.core import retro, runs
    from app.core import sandbox as sb
    from app.core.problem_codes import Refusal
    f = None
    try:
        with _as_folder(name):
            try:
                f = _job_folder(name, eid)
                _reset_unfinished(f)
                f = check(name, eid)
                rr = runs.APP_STATE / "retro"
                if kind == "tidy":
                    return _tidy_main(f, rr)
                p = X.preflight(f / X.SETTINGS, retro_root=rr)
                if p["complete"]:
                    print("complete", flush=True)
                    return 0
                cancelled, after_week = _job_hooks(name, eid, f)
                X.run(f / X.SETTINGS, retro_root=rr,
                      flubnf_build=runs._git_sha(sb.REPO),
                      cancelled=cancelled, after_week=after_week)
                return 0
            finally:
                if f is not None and _is_dir(f):
                    retro.clear_flags(f)
    except (retro.SeasonStopped, retro.EngineBuildChanged):
        return 0
    except (Refusal, retro.ResumeMismatch) as e:
        print(_said(e), file=sys.stderr, flush=True)
        return 3
    except Exception:
        traceback.print_exc()
        return 1
