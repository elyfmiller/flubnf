"""The runner's supervisor (app/core/runner.py serve, one poll at a time):
one runner per computer; jobs only from a clean main; the engine read
as the console reads it, the one the install records or no start, and
named (its start line, runner.json, Storage's line); the job child
isolated (-I, its own session, no PYTHON*, caffeinate, runner.json's job
written first) and on the runner's engine; the heartbeat and the waiting
move while a job runs; a Stop from its page is said; the queue held for
replays, never for fits (a command line that is not UTF-8 hides none),
and for an engine older than the console; a job the disk cannot hold
waits while a smaller one runs; the time, memory, folder and free-space
limits kill the job's tree and record why (SIGKILL for what outlives
SIGTERM, each group a fit leads signalled whole); a crashed child is
recorded, not requeued; a restart or SIGTERM (^C too, its Terminal
closing unless under nohup, or one that ended the child as well) queues
the job again first unless STOP stands; the supervisor's writes never
open a pipe, a hard link or a link a student or anyone left; a new HEAD
re-executes between jobs only; refusals at dispatch and from the child
leave the queue with their words; PAUSE is cleared; recent records
seconds, k and the peaks; tidy runs only where a folder needs it and
never while the queue is held; and `flubnf runner` is listed and
refuses without STUDENTS or on Windows.

No process is started: subprocess.Popen, ps, git, the disk, the clock,
the signals (a process group's too), the sweep and os.execv are faked.
A fake child does on its start and at each poll what the test says
(writes its run record, ends with a code)."""
import errno
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import runs                                # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from flubnf import cli                                   # noqa: E402
from test_experiments import _stale_fork                 # noqa: E402
from test_runner_folders import (SMOKE, W0, W1, calendar,  # noqa: E402,F401
                                 experiment, stored, student, students)
from test_runner_queue import DEAD, _running, state      # noqa: E402

GiB, MiB = runner.GiB, runner.MiB
EID = "sihrs_2024-25_smoke_oracle"
#: the fake children's pids: no process has one (above every pid_max)
PID0 = 2_147_480_000
POSIX = pytest.mark.skipif(os.name == "nt",
                           reason="flock and killpg are POSIX's")
_INSTALL_PROBLEM = runner._install_problem
#: the real reader of the install's engine record (conftest: none)
_RECORDED_ENGINE = runner._recorded_engine
TERM = signal.SIGTERM


class Reexec(Exception):
    """os.execv faked: the supervisor would have started again."""


class Child:
    """A process the supervisor started (subprocess.Popen faked): its argv
    and keywords, runner.json as it stood at the spawn, and the world's
    start and act run at its start and at every poll."""

    def __init__(self, w, args, kw):
        self.w, self.args, self.kw = w, list(args), dict(kw)
        self.pid = PID0 + len(w.children)
        self.code = None
        self.polls = 0
        self.signals = []
        self.at_spawn = json.loads((runner.state_dir() / runner.STATE_FILE)
                                   .read_text(encoding="utf-8"))
        w.children.append(self)
        if w.start:
            w.start(self)

    @property
    def folder(self) -> Path:
        _kind, students, name, eid = self.args[4:8]
        return Path(students) / name / "sandbox" / "experiments" / eid

    def poll(self):
        if self.code is None:
            self.polls += 1
            if self.w.act:
                self.w.act(self)
        return self.code

    def wait(self, timeout=None):
        if self.code is None:
            raise subprocess.TimeoutExpired("job", timeout)
        return self.code

    def terminate(self):
        self.signals.append("TERM")
        self.code = -15 if self.code is None else self.code

    def kill(self):
        self.signals.append("KILL")
        self.code = -9 if self.code is None else self.code


class Caffeinate:
    def __init__(self, args):
        self.args = list(args)
        self.ended = False

    def poll(self):
        return 0 if self.ended else None

    def terminate(self):
        self.ended = True

    def wait(self, timeout=None):
        return 0


@pytest.fixture
def world(students, monkeypatch, tmp_path):
    """The supervisor's world faked: the clock (each wait moves it), git's
    HEAD (w.head), a clean main, the engine ready, ps (w.ps(columns)),
    the free disk (w.free()), the signals (a group's in w.groups, none
    led by a fake pid), the registry sweep, Popen (Child, Caffeinate)
    and os.execv; the install's state and Sandbox in tmp; alice and
    bob."""
    w = types.SimpleNamespace(
        clock=[1_800_000_000.0], children=[], caffs=[], swept=[],
        signals=[], groups=[], execs=[], head="a" * 40, start=None,
        act=None,
        ps=lambda columns: [], free=lambda: 500 * GiB, students=students)
    monkeypatch.setattr(runner, "_now", lambda: w.clock[0])
    monkeypatch.setattr(runner, "_sleep",
                        lambda s: w.clock.__setitem__(0, w.clock[0] + s))
    monkeypatch.setattr(runner, "_head", lambda: w.head)
    monkeypatch.setattr(runner, "_install_problem", lambda: "")
    monkeypatch.setattr(runner, "_engine_ready", lambda: True)
    monkeypatch.setattr(runner, "_ps", lambda columns: list(w.ps(columns)))
    monkeypatch.setattr(runner, "_free", lambda: w.free())
    monkeypatch.setattr(runner, "_signal",
                        lambda pid, sig: w.signals.append((pid, sig)))
    monkeypatch.setattr(runner, "_pgid", lambda pid: None)
    monkeypatch.setattr(runner, "_killpg",
                        lambda pgid, sig: w.groups.append((pgid, sig)))
    monkeypatch.setattr(cli, "_sweep_runner_groups",
                        lambda registry=None, wait=5.0:
                        w.swept.append(Path(registry)) or 0)

    def popen(args, **kw):
        if args[0] == "caffeinate":
            w.caffs.append(Caffeinate(args))
            return w.caffs[-1]
        return Child(w, args, kw)

    def no_run(*a, **k):
        raise AssertionError(f"a supervisor test ran {a}")
    monkeypatch.setattr(runner, "subprocess", types.SimpleNamespace(
        Popen=popen, run=no_run, DEVNULL=subprocess.DEVNULL,
        STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired))

    def execv(exe, argv):
        w.execs.append((exe, list(argv)))
        raise Reexec
    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(runs, "APP_STATE", tmp_path / "state")
    monkeypatch.setattr(sb, "SANDBOX", tmp_path / "main" / "sandbox")
    calendar(monkeypatch)
    w.alice, w.bob = student(students, "alice"), student(students, "bob")
    w.registry = runner.state_dir() / runner.REGISTRY_FILE
    return w


def claims(child) -> None:
    """What a job child does at its start: it claims QUEUED and opens its
    run record, a week stored before and the next under way (a tidy
    child does neither)."""
    if getattr(child, "args", ["run"] * 5)[4] != "run":
        return
    f = child.folder
    (f / X.QUEUED).unlink(missing_ok=True)
    now = time.time()
    retro.write_meta(f, {
        "status": "running", "pid": child.pid, "heartbeat_utc": now,
        "segment_start_utc": now - 30, "started_utc": now - 300,
        "elapsed_s": 270.0, "season": "2024-25",
        "week_seconds": {W0: 60.0},
        "settings": {"experiment": "e" * 64, "weeks": [W0, W1],
                     "locations": ["California", "Vermont"],
                     "replicates": 1, "particles": 10_000}})
    stored(f, W0)
    wd = f / "weeks" / W1
    (wd / "Vermont_r0").mkdir(parents=True, exist_ok=True)
    (wd / "cells.json").write_text("[]", encoding="utf-8")


def ends(child, code: int = 0, status: str = "done", **meta) -> None:
    """The child ends: its record finished (status), then its exit code."""
    m = retro.read_meta(child.folder)
    if m:
        retro.write_meta(child.folder, {**m, "status": status,
                                        "finished_utc": time.time(),
                                        "segment_start_utc": None, **meta})
    child.code = code


def _job(top: Path, settings=SMOKE, at: float | None = None) -> Path:
    f = experiment(top, settings, queued=True)
    if at is not None:
        os.utime(f / X.QUEUED, (at, at))
    return f


def _cleared(f: Path) -> bool:
    return not any((f / n).exists() for n in (X.QUEUED, retro.STOP_NAME,
                                              retro.PAUSE_NAME))


# ------------------------------------------------- starting, and the install


@POSIX
def test_one_runner_per_computer(world, capsys):
    fd = runner._lock()
    assert fd is not None
    try:
        assert runner._lock() is None
        state(world.students, pid=4242)
        assert runner.serve() == 1
        assert capsys.readouterr().err.strip() == (
            "A runner already works this computer's queue (pid 4242).")
        assert world.children == []
    finally:
        os.close(fd)
    again = runner._lock()                  # the kernel let it go
    assert again is not None
    os.close(again)


def test_the_runner_starts_jobs_only_from_a_clean_main(world, monkeypatch,
                                                       capsys):
    monkeypatch.setattr(runner, "_install_problem", _INSTALL_PROBLEM)
    sym, gitdir = ("symbolic-ref", "--short", "HEAD"), ("rev-parse",
                                                       "--git-dir")
    origin = ("remote", "get-url", "origin")
    # no optional lock: a poll's status never blocks Ely's git pull
    edits = ("--no-optional-locks", "status", "--porcelain",
             "--untracked-files=no")
    ahead = ("rev-list", "--count", "origin/main..HEAD")
    clean = {sym: (0, "main"), gitdir: (0, ".git"),
             origin: (0, "git@github.com:elyfmiller/flubnf.git"),
             edits: (0, ""), ahead: (0, "0")}
    _job(world.alice)
    world.act = ends
    sv = runner._supervisor()
    for change, words in (
            ({sym: (0, "dev")}, "the runner's install is on dev, not main"),
            ({sym: (128, "")},
             "the runner's install is on a detached HEAD, not main"),
            ({sym: (128, ""), gitdir: (128, "")},
             "the runner's install is not a git checkout of main"),
            ({origin: (0, "https://someone:t0ken@github.com/someone/"
                          "flubnf.git")},
             "the runner's install's origin is https://github.com/someone/"
             "flubnf.git, not elyfmiller/flubnf"),
            ({origin: (2, "")}, "the runner's install's origin is not set, "
             "not elyfmiller/flubnf"),
            ({edits: (0, " M app/core/runner.py")},
             "the runner's install has edits to tracked files; it runs main "
             "only as merged"),
            ({ahead: (0, "2")},
             "the runner's install has 2 commits that are not on "
             "origin/main"),
            ({ahead: (0, "1")},
             "the runner's install has 1 commit that is not on origin/main")):
        answers = {**clean, **change}
        monkeypatch.setattr(runner, "_git", lambda *a, _a=answers: _a[a])
        runner._dispatch(sv)
        assert runner.read_state()["waiting_why"] == words
        assert world.children == []
        assert runner.position("alice", EID)["why"] == f"waiting: {words}"
    for url in ("https://github.com/elyfmiller/flubnf",
                "git@github.com:elyfmiller/flubnf.git"):
        monkeypatch.setattr(runner, "_git", lambda *a, _u=url: {
            **clean, origin: (0, _u)}[a])
        assert runner._install_problem() == ""
    runner._dispatch(sv)
    assert len(world.children) == 1 and runner.read_state()["waiting_why"] == ""
    # an install inside STUDENTS: a student's clone, never a runner
    monkeypatch.setattr(sb, "REPO", world.students / "alice")
    assert runner.serve() == 1
    assert capsys.readouterr().err.strip() == (
        "Not started: this is a student's clone; the runner runs from the "
        "main install only.")


def test_the_child_is_isolated(world, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(world.students))
    monkeypatch.setenv("PYTHONSTARTUP", str(world.students / "x.py"))
    monkeypatch.setattr(sys, "platform", "darwin")
    _job(world.alice)
    world.act = ends
    runner._dispatch(runner._supervisor())
    [c] = world.children
    assert runner.JOB_ENTRY == ("import sys; from app.core.runner import "
                                "job_main; sys.exit(job_main(sys.argv[1:]))")
    assert c.args == [sys.executable, "-I", "-c", runner.JOB_ENTRY, "run",
                      str(world.students), "alice", EID, "smoke"]
    assert "nice" not in c.args
    assert c.kw["cwd"] == str(runner.state_dir())
    assert c.kw["start_new_session"] is True
    assert c.kw["stdin"] is subprocess.DEVNULL
    assert c.kw["stderr"] is subprocess.STDOUT
    assert Path(c.kw["stdout"].name) == runner.state_dir() / runner.LOG_FILE
    assert not [k for k in c.kw["env"] if k.startswith("PYTHON")]
    assert c.kw["env"]["PATH"] == os.environ["PATH"]
    assert [x.args for x in world.caffs] == [
        ["caffeinate", "-i", "-w", str(c.pid)]]
    assert world.caffs[0].ended
    # runner.json named the job before the child existed
    job = c.at_spawn["job"]
    lim = runner.limits("smoke")
    assert {k: job[k] for k in ("kind", "folder", "id", "size", "pid")} == {
        "kind": "run", "folder": "alice", "id": EID, "size": "smoke",
        "pid": None}
    assert job["limits"] == {"seconds": lim.seconds, "memory": lim.memory,
                             "disk": lim.disk}
    assert job["peak_bytes"] == 35_332_432 and job["keep_bytes"] == 878_000
    assert c.at_spawn["waiting"] == []


@pytest.mark.parametrize("installed", ["private", "public", "both", "none"])
@pytest.mark.parametrize("engine", ["private", "public"])
def test_the_runner_reads_the_engine_as_the_console_does(engine, installed,
                                                         tmp_path,
                                                         monkeypatch):
    # a drift guard: the queue waits for the engine exactly when the
    # console's up-front check (pipeline._pf_engine_state) says it is not
    # ready; on public its venv alone, the private venv and fork not needed
    from app.ui import pipeline
    from flubnf import settings
    fork = tmp_path / "fork"
    venv = tmp_path / "engine" / "bin" / "python"
    public = tmp_path / "public" / "bin" / "python"
    if installed in ("private", "both"):
        (fork / "pybnf").mkdir(parents=True)
        (fork / pf.PF_MODULE).write_text("# stub\n")
        venv.parent.mkdir(parents=True)
        venv.write_text("")
    if installed in ("public", "both"):
        public.parent.mkdir(parents=True)
        public.write_text("")
    monkeypatch.setattr(settings, "PY_ENGINE", venv)
    monkeypatch.setattr(settings, "PYBNF", fork)
    monkeypatch.setattr(pf, "PYBNF_PF", fork)
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(public))
    monkeypatch.setenv("FLUBNF_ENGINE", engine)
    ready = installed in (engine, "both")
    assert runner._engine_ready() is ready
    assert runner._engine_ready() == (pipeline._pf_engine_state() == "ready")


def test_the_engine_an_install_records(tmp_path, monkeypatch):
    from flubnf import settings
    monkeypatch.setattr(runner, "_recorded_engine", _RECORDED_ENGINE)
    monkeypatch.setattr(sb, "REPO", tmp_path)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    env = tmp_path / ".flubnf.env"
    assert runner._recorded_engine() is None
    for text, got in (
            # setup_engine.sh's lines; the last FLUBNF_ENGINE wins, read as
            # settings.engine_choice reads one
            ('export FLUBNF_PY_ENGINE_PUBLIC="/p/bin/python"\n', None),
            ('export FLUBNF_PY_ENGINE_PUBLIC="/p/bin/python"\n'
             "export FLUBNF_ENGINE=public\n", "public"),
            ('export FLUBNF_ENGINE="Public"\nexport FLUBNF_HUB=/h\n',
             "public"),
            ("export FLUBNF_ENGINE=public\nFLUBNF_ENGINE=private\n",
             "private"),
            ("export FLUBNF_ENGINE=public  # by hand\n", "public"),
            # by hand, as sh reads them: quotes first, then a blank or a ;
            ('export FLUBNF_ENGINE=" public"\n', "public"),
            ("export FLUBNF_ENGINE='public' # by hand\n", "public"),
            ("FLUBNF_ENGINE=public; export FLUBNF_ENGINE\n", "public"),
            # anything but exactly private is the public engine, the default
            ("export FLUBNF_ENGINE= public\n", "public"),
            ("export FLUBNF_ENGINE=public#x\n", "public"),
            ("# export FLUBNF_ENGINE=public\n", None),
            ("export FLUBNF_ENGINE_LOCK=/l\n", None),
            ("export FLUBNF_ENGINE=lwf\n", "public"),
            ('export FLUBNF_ENGINE="PRIVATE"\n', "private")):
        env.write_text(text, encoding="utf-8")
        assert runner._recorded_engine() == got, text
    env.write_text("export FLUBNF_ENGINE=public\n", encoding="utf-8")
    assert runner._engine_record_problem() == (
        "this install records FLUBNF_ENGINE=public (.flubnf.env) but this "
        "Terminal runs the private engine: run `. ./.flubnf.env` in the "
        "clone first")
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert runner._engine_record_problem() == ""
    # unset, settings reads the record itself: the two agree
    monkeypatch.delenv("FLUBNF_ENGINE")
    assert runner._engine_record_problem() == ""
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    env.unlink()
    env.mkdir()                                  # not a file: unreadable
    assert runner._recorded_engine() is None
    assert runner._engine_record_problem() == ""
    if hasattr(os, "mkfifo"):
        # a pipe, which FluBNF.command's [ -f ] skips: never waited on
        env.rmdir()
        os.mkfifo(env)

        def stuck(signum, frame):
            raise AssertionError("the record's reader waited on a pipe")
        old = signal.signal(signal.SIGALRM, stuck)
        signal.alarm(5)
        try:
            assert runner._recorded_engine() is None
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    # Windows: setup.ps1's and FluBNF.bat's lines, cmd's names in any case
    monkeypatch.setattr(settings, "_windows", lambda: True)
    cmd = tmp_path / ".flubnf.env.cmd"
    assert runner._recorded_engine() is None
    cmd.write_bytes(b'@echo off\r\nrem Written by setup.ps1\r\n'
                    b'set "FLUBNF_HUB=C:\\hub"\r\n'
                    b'set "FLUBNF_ENGINE=public"\r\n'
                    b'set "FLUBNF_PY_ENGINE_PUBLIC=C:\\p\\python.exe"\r\n')
    assert runner._recorded_engine() == "public"
    assert runner._engine_record_problem() == (
        "this install records FLUBNF_ENGINE=public (.flubnf.env.cmd) but "
        "this Terminal runs the private engine: run `call .flubnf.env.cmd` "
        "in the clone first")
    cmd.write_bytes(b'set "FLUBNF_ENGINE=public"\r\n'
                    b'SET flubnf_engine=private\r\n')
    assert runner._recorded_engine() == "private"


@POSIX
def test_a_terminal_without_the_installs_engine_is_not_started(
        world, monkeypatch, tmp_path, capsys):
    # the install records public (setup_engine.sh --public), this Terminal
    # never read the record: the job child would inherit the private
    # engine, so nothing starts
    from flubnf import settings
    monkeypatch.setattr(runner, "_recorded_engine", _RECORDED_ENGINE)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    install = tmp_path / "install"
    install.mkdir()
    (install / ".flubnf.env").write_text(
        'export FLUBNF_PY_ENGINE_PUBLIC="/p/bin/python"\n'
        "export FLUBNF_ENGINE=public\n", encoding="utf-8")
    monkeypatch.setattr(sb, "REPO", install)
    _job(world.alice)
    # a runner that started anyway stops after its first poll
    monkeypatch.setattr(runner, "_stopping", False)
    monkeypatch.setattr(runner, "_dispatch",
                        lambda sv: setattr(runner, "_stopping", True))
    assert os.environ["FLUBNF_ENGINE"] == "private"     # the suite's pin
    assert runner.serve() == 1
    assert capsys.readouterr().err.strip() == (
        "Not started: this install records FLUBNF_ENGINE=public "
        "(.flubnf.env) but this Terminal runs the private engine: run "
        "`. ./.flubnf.env` in the clone first.")
    assert world.children == []
    assert not (runner.state_dir() / runner.STATE_FILE).exists()
    # Storage's advice reads the record first, as a start must
    state(world.students, pid=DEAD)
    assert runner.storage(size=lambda p: 0)["why"].endswith(
        f"in a Terminal of this account, run cd {install} && . ./.flubnf.env "
        "&& .venv/bin/flubnf runner.")
    # one that read it starts
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert runner._start_problem() == ""


def _private_install(tmp_path, monkeypatch):
    """An install that records the private engine (setup_engine.sh
    --private), which both the runner's check and settings read."""
    from flubnf import settings
    monkeypatch.setattr(runner, "_recorded_engine", _RECORDED_ENGINE)
    monkeypatch.setattr(settings, "_windows", lambda: False)
    install = tmp_path / "install"
    install.mkdir()
    (install / ".flubnf.env").write_text(
        'export FLUBNF_PY_ENGINE="/e/bin/python"\n'
        "export FLUBNF_ENGINE=private\n", encoding="utf-8")
    monkeypatch.setattr(sb, "REPO", install)
    monkeypatch.setattr(settings, "INSTALL_ROOT", install)
    settings.forget_record()
    return install


def test_a_private_record_starts_from_a_terminal_that_names_no_engine(
        tmp_path, monkeypatch):
    from flubnf import settings
    _private_install(tmp_path, monkeypatch)
    monkeypatch.delenv("FLUBNF_ENGINE")
    assert settings.engine_choice() == "private"
    assert runner._engine_record_problem() == ""
    # one whose environment names the other engine is refused, as before
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    assert runner._engine_record_problem() == (
        "this install records FLUBNF_ENGINE=private (.flubnf.env) but this "
        "Terminal runs the public engine: run `. ./.flubnf.env` in the "
        "clone first")


@POSIX
@pytest.mark.parametrize("recorded", [{"engine": "private"}, {}],
                         ids=["private", "main-wrote-none"])
def test_a_reexec_onto_another_engine_stops_and_says_why(
        world, monkeypatch, capsys, recorded):
    # the runner ran the private engine (main's runner records none, and
    # ran only it); the update made this install's default the public one.
    # Its re-execution (the same pid) stops instead of refusing every job
    # begun on the private engine, and takes no lock. The public engine is
    # this install's by the default: nothing set, no record.
    from flubnf import settings
    monkeypatch.delenv("FLUBNF_ENGINE")
    settings.forget_record()
    assert settings.engine_source() == ("default", None)
    _job(world.alice)
    state(world.students, **recorded)
    before = (runner.state_dir() / runner.STATE_FILE).read_text()
    monkeypatch.setattr(runner, "_stopping", False)
    monkeypatch.setattr(runner, "_dispatch",
                        lambda sv: setattr(runner, "_stopping", True))
    assert runner.serve() == 1
    assert capsys.readouterr().err.strip() == (
        "Not started again: this runner ran the private engine and, after "
        "the update to aaaaaaa, this install runs the public one. Jobs begun "
        "on the private engine would be refused and leave the queue. To keep "
        "the private engine, run ./setup_engine.sh --private in the FluBNF "
        "folder; to go on with the public one, start the runner again.")
    assert world.children == []
    assert (runner.state_dir() / runner.STATE_FILE).read_text() == before
    # the same engine goes on
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    assert runner._engine_changed_on_reexec() == ""
    # a start by hand (another pid) goes on with the engine selected
    monkeypatch.delenv("FLUBNF_ENGINE")
    state(world.students, pid=DEAD, **recorded)
    assert runner._engine_changed_on_reexec() == ""
    assert runner.serve() == 0


@POSIX
def test_the_runner_names_its_engine_and_its_child_runs_it(world,
                                                           monkeypatch,
                                                           tmp_path,
                                                           capsys):
    # the public engine by the default (nothing set, no record): the child
    # is given it all the same, as runner.json names it (review #3)
    from flubnf import settings
    py = tmp_path / "public" / "bin" / "python"
    monkeypatch.delenv("FLUBNF_ENGINE")
    settings.forget_record()
    assert settings.engine_source() == ("default", None)
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", str(py))
    monkeypatch.setattr(pf, "engine_current", lambda: True)  # no venv probe
    monkeypatch.setattr(runner, "_stopping", False)
    _job(world.alice)
    world.act = ends
    dispatch = runner._dispatch

    def once(sv):
        dispatch(sv)
        runner._stopping = True
    monkeypatch.setattr(runner, "_dispatch", once)
    assert runner.serve() == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first.endswith(f" runner {os.getpid()} on build aaaaaaa (the "
                          f"public engine): {world.students}")
    [c] = world.children
    assert c.kw["env"]["FLUBNF_ENGINE"] == "public"
    assert c.kw["env"]["FLUBNF_PY_ENGINE_PUBLIC"] == str(py)
    assert c.at_spawn["engine"] == "public"
    assert runner.read_state()["engine"] == "public"
    assert runner.storage(size=lambda p: 0)["runner"][0] == (
        "The runner (the public engine): idle")
    # a runner.json of an older runner names none
    state(world.students)
    assert runner.storage(size=lambda p: 0)["runner"][0] == "The runner: idle"


def test_waits_for_replays_not_fits(world, tmp_path):
    lines = {}
    world.ps = lambda columns: lines.get(columns, [])
    world.act = ends
    sv = runner._supervisor()

    def waits(words: str) -> None:
        _job(world.alice)
        n = len(world.children)
        runner._dispatch(sv)
        assert runner.read_state()["waiting_why"] == words
        assert len(world.children) == n + bool(not words)

    lines["pid=,command="] = [
        "  123 /x/.venv/bin/python /x/app/state/retro/2024-25/weeks/"
        "2024-12-28/runner_0.py"]
    waits("a replay is running on this computer (its fits, pid 123)")
    lines["pid=,command="] = [
        "  124 /x/.venv/bin/python /x/sandbox/runs/20261101-000000_m/"
        "pf_runner_0.py", "  125 /x/.venv/bin/python -m pytest"]
    waits("")
    for root, what in (
            (world.bob / "experiments" / "beta-v1_2024-25_smoke",
             "bob's beta-v1_2024-25_smoke"),
            (runs.APP_STATE / "retro" / "2024-25",
             "the shipped replay of 2024-25"),
            (runs.APP_STATE / "retro" / "2024-25_custom",
             "the replay 2024-25_custom"),
            (sb.SANDBOX / "experiments" / "sihrs_2024-25_full_oracle",
             "the experiment sihrs_2024-25_full_oracle on the main console")):
        root.mkdir(parents=True)
        _running(root)
        waits(f"a replay is running on this computer ({what})")
        retro.write_meta(root, {"status": "done"})
        waits("")
    # a record that went quiet (its worker gone) holds nothing
    _running(world.bob / "experiments" / "beta-v1_2024-25_smoke")
    m = retro.read_meta(world.bob / "experiments" / "beta-v1_2024-25_smoke")
    retro.write_meta(world.bob / "experiments" / "beta-v1_2024-25_smoke",
                     {**m, "pid": PID0 - 1})
    waits("")


def test_an_engine_older_than_the_console_holds_the_queue(world,
                                                          monkeypatch,
                                                          tmp_path):
    # pf.prepare would refuse every week: the queue waits in its words,
    # and nothing is started or refused
    f = _job(world.alice)
    world.act = ends
    sv = runner._supervisor()
    current, stale = pf.PYBNF_PF, _stale_fork(tmp_path)
    monkeypatch.setattr(pf, "PYBNF_PF", stale)
    runner._dispatch(sv)
    words = pf.engine_stale_message()
    assert "does not accept pf_particles" in words
    r = runner.read_state()
    assert r["waiting_why"] == words
    assert world.children == [] and (f / X.QUEUED).is_file()
    assert r["recent"] == [] and runner.refusal("alice", EID) == ""
    assert runner.position("alice", EID)["why"] == f"waiting: {words}"
    # a probe that raises (a parser that is not UTF-8), or not installed
    # at all: the words as before, and runner.json still written
    gone = "the particle-filter engine is not installed on the runner"
    (stale / "pybnf" / "parse.py").write_bytes(b"\xff\xfe")
    runner._dispatch(sv)
    assert runner.read_state()["waiting_why"] == gone
    monkeypatch.setattr(runner, "_engine_ready", lambda: False)
    runner._dispatch(sv)
    assert runner.read_state()["waiting_why"] == gone
    assert world.children == [] and (f / X.QUEUED).is_file()
    # brought up to date: the job runs
    monkeypatch.setattr(runner, "_engine_ready", lambda: True)
    monkeypatch.setattr(pf, "PYBNF_PF", current)
    runner._dispatch(sv)
    assert len(world.children) == 1
    assert runner.read_state()["waiting_why"] == ""


def test_a_job_the_disk_cannot_hold_waits_and_a_smaller_one_runs(world):
    full = {**SMOKE, "size": "full"}
    _job(world.alice, full, at=100)
    _job(world.bob, SMOKE, at=200)
    world.free = lambda: runner.FREE_FLOOR + GiB
    seen = []

    def act(child):
        seen.append(runner.read_state()["waiting"])
        ends(child)
    world.act = act
    runner._dispatch(runner._supervisor())
    [c] = world.children
    assert c.args[6:9] == ["bob", EID, "smoke"]
    words = ("waiting for disk: it needs about 2.6 GB, and leaving 20.0 GB "
             "free allows 1.0 GB now")
    # while bob's runs, alice's line says why it waits
    assert [(w["folder"], w["why"]) for w in seen[0]] == [("alice", words)]
    assert runner.position("alice", "sihrs_2024-25_full_oracle")["why"] == words
    # room again: it runs
    world.free = lambda: 500 * GiB
    runner._dispatch(runner._supervisor())
    assert world.children[-1].args[6:9] == [
        "alice", "sihrs_2024-25_full_oracle", "full"]


def test_the_heartbeat_and_the_waiting_move_while_a_job_runs(world):
    f = _job(world.alice)
    est = runner._estimate_of(f, [])["seconds"]
    world.start = claims
    seen = []

    def act(child):
        r = runner.read_state()
        seen.append((r["heartbeat_utc"], r["job"]["seconds"],
                     [(w["folder"], w["id"]) for w in r["waiting"]]))
        if child.polls == 1:
            _job(world.bob)                  # queued while alice's runs
        if child.polls == 6:
            ends(child)
    world.act = act
    t0 = world.clock[0]
    runner._dispatch(runner._supervisor())
    # the job's seconds are its estimate; every POLL_S the heartbeat moves
    # and the waiting take in the job queued meanwhile
    assert seen[0] == (runner._utc(t0), est, [])
    assert seen[3] == (runner._utc(t0 + runner.POLL_S), est, [("bob", EID)])
    assert seen[5][0] == runner._utc(t0 + 2 * runner.POLL_S)
    assert runner.position("bob", EID)["position"] == 1


def test_a_stop_from_its_page_is_said_on_the_runner(world):
    f = _job(world.alice)
    world.start = claims
    world.act = lambda c: c.polls == 2 and ends(c, status="stopped")
    runner._dispatch(runner._supervisor())
    m = retro.read_meta(f)
    assert (m["status"], m["stop_reason"]) == ("stopped", runner._PAGE_STOP)
    assert not (f / "weeks" / W1).exists() and _cleared(f)
    r = runner.read_state()["recent"][0]
    assert (r["outcome"], r["text"]) == ("stopped", runner._PAGE_STOP)


# ------------------------------------------------------------- the limits


def _limited(world, words: str, f: Path, *, outcome="limit") -> dict:
    """The job's tree killed and the folder settled: its record stopped
    with these words, the week under way gone, the flags cleared, recent
    saying so. recent's entry."""
    [c] = world.children
    assert c.signals == ["TERM"]
    m = retro.read_meta(f)
    assert (m["status"], m["stop_reason"]) == ("stopped", words)
    assert m["segment_start_utc"] is None and m["finished_utc"]
    assert m["weeks_completed"] == 1
    assert not (f / "weeks" / W1).exists() and (f / "weeks" / W0).is_dir()
    assert _cleared(f)
    r = runner.read_state()
    assert r["job"] is None
    assert (r["recent"][0]["outcome"], r["recent"][0]["text"]) == (outcome,
                                                                   words)
    assert world.swept and set(world.swept) == {world.registry}
    return r["recent"][0]


def test_time_limit_kills_and_records(world):
    f = _job(world.alice)
    world.start = claims

    def act(child):
        (f / retro.STOP_NAME).touch()          # a Stop pressed meanwhile
    world.act = act
    t0 = world.clock[0]
    runner._dispatch(runner._supervisor())
    lim = runner.limits("smoke")
    assert world.clock[0] - t0 == lim.seconds + runner.WATCH_S
    _limited(world, "The runner stopped it at its time limit: a smoke "
             "experiment may run 30:00 at a time. Finished weeks are kept; "
             "Resume queues it again.", f)
    assert not (f / X.QUEUED).exists()          # not queued again


def test_memory_limit_kills_at_once(world):
    f = _job(world.alice)
    world.start = claims
    lim = runner.limits("smoke")
    third = (lim.memory + MiB) // 3 // 1024 + 1

    def ps(columns):
        if columns != "pid=,ppid=,rss=":
            return []
        c = world.children[-1].pid
        return ["  PID  PPID   RSS", f"{c} 1 {third}", f"{c + 100} {c} {third}",
                f"{c + 101} {c + 100} {third}", f"1 0 {10 ** 9}"]
    world.ps = ps
    runner._dispatch(runner._supervisor())
    [c] = world.children
    assert c.polls == 1
    rss = 3 * third * 1024
    entry = _limited(world, f"The runner stopped it: its fits used "
                     f"{retro.human_bytes(rss)} of memory, and a smoke "
                     f"experiment may use {retro.human_bytes(lim.memory)}. "
                     "Finished weeks are kept; Resume queues it again.", f)
    assert (c.pid + 100, TERM) in world.signals
    assert (c.pid + 101, TERM) in world.signals
    assert entry["rss_peak"] == rss
    assert runner._tree(c.pid) == ([c.pid + 100, c.pid + 101], rss)


def test_folder_cap_and_floor_kill(world, monkeypatch):
    f = _job(world.alice)
    world.start = claims
    lim = runner.limits("smoke")
    real = retro.dir_size
    monkeypatch.setattr(retro, "dir_size", lambda p: lim.disk + 50 * MiB)
    runner._dispatch(runner._supervisor())
    entry = _limited(world, "The runner stopped it: its folder reached "
                     "562.0 MB, and a smoke experiment may hold 512.0 MB. "
                     "Finished weeks are kept; Resume queues it again.", f)
    assert entry["disk_peak"] == lim.disk + 50 * MiB
    assert world.children[0].polls == 1
    # the disk falls below the floor a minute in
    monkeypatch.setattr(retro, "dir_size", real)
    world.children.clear()
    world.swept.clear()
    (f / X.QUEUED).touch()
    t0 = world.clock[0]
    world.free = lambda: (500 * GiB if world.clock[0] < t0 + 60
                          else runner.FREE_FLOOR - 1)
    runner._dispatch(runner._supervisor())
    _limited(world, "The runner stopped it: this disk fell below 20.0 GB "
             "free, which FluBNF keeps free. Finished weeks are kept; Resume "
             "queues it again once there is room.", f)
    assert world.clock[0] - t0 == 60            # measured every 30 s


def test_a_tree_that_outlives_its_term_is_killed(world, monkeypatch):
    class Stubborn:
        """A child that ignores SIGTERM."""
        pid = PID0 + 7

        def __init__(self):
            self.signals, self.code = [], None

        def terminate(self):
            self.signals.append("TERM")

        def kill(self):
            self.signals.append("KILL")
            self.code = -9

        def wait(self, timeout=None):
            if self.code is None:
                raise subprocess.TimeoutExpired("job", timeout)
            return self.code
    p = Stubborn()
    world.ps = lambda columns: [f"{p.pid} 1 10", f"{p.pid + 1} {p.pid} 10",
                                f"{p.pid + 2} {p.pid + 1} 10"]
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: pid == p.pid + 2)
    runner._kill_tree(p)
    kill = getattr(signal, "SIGKILL", TERM)
    assert p.signals == ["TERM", "KILL"]
    assert world.signals == [(p.pid + 1, TERM), (p.pid + 2, TERM),
                             (p.pid + 2, kill)]
    assert world.swept == [world.registry]


@POSIX
def test_a_fit_started_after_the_ps_read_is_reached_by_its_group(
        world, monkeypatch):
    # on public each shard runner leads its own group and starts a PyBNF
    # process per cell in it: one started after the ps read is on no list,
    # and only its group's killpg reaches it; so does what the child
    # starts in its own group (its session, _spawn's) after the read, a
    # BNG2.pl say; the runner's own group is never signalled
    job, shard, cell, late = PID0 + 30, PID0 + 31, PID0 + 32, PID0 + 33
    bng = PID0 + 34
    own = os.getpgrp()
    members = {job: {job}, shard: {shard, cell}, own: {own}}
    got, log = {}, []

    def ps(columns):
        members[shard].add(late)              # a cell starts once ps is read
        members[job].add(bng)
        return [f"{job} 1 10", f"{shard} {job} 10", f"{cell} {shard} 10",
                f"{own} {job} 10"]
    world.ps = ps
    leads = {job: job, shard: shard, cell: shard, own: own}
    monkeypatch.setattr(runner, "_pgid", lambda pid: leads.get(pid))
    monkeypatch.setattr(runner, "_signal",
                        lambda pid, sig: log.append(("pid", pid, sig)))

    def killpg(pgid, sig):
        log.append(("group", pgid, sig))
        for m in members[pgid]:
            got.setdefault(m, []).append(sig)
    monkeypatch.setattr(runner, "_killpg", killpg)
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
    p = types.SimpleNamespace(pid=job, terminate=lambda: None,
                              kill=lambda: None, wait=lambda timeout: 0)
    runner._kill_tree(p)
    kill = getattr(signal, "SIGKILL", TERM)
    assert log == [("pid", shard, TERM), ("pid", own, TERM),
                   ("pid", cell, TERM), ("group", job, TERM),
                   ("group", shard, TERM), ("group", job, kill),
                   ("group", shard, kill)]
    assert got[late] == got[bng] == [TERM, kill]
    assert world.swept == [world.registry]


def test_a_crashed_child_is_recorded_not_requeued(world):
    f = _job(world.alice)
    world.start = claims
    world.act = lambda c: c.polls == 2 and setattr(c, "code", 1)
    sv = runner._supervisor()
    runner._dispatch(sv)
    words = ("It ended unexpectedly (exit code 1). Finished weeks are kept; "
             "Resume queues it again.")
    m = retro.read_meta(f)
    assert (m["status"], m["stop_reason"]) == ("stopped", words)
    assert m["elapsed_s"] == pytest.approx(300.0, abs=5)
    assert _cleared(f) and not (f / "weeks" / W1).exists()
    r = runner.read_state()
    assert (r["recent"][0]["outcome"], r["recent"][0]["text"]) == ("ended",
                                                                   words)
    assert world.children[0].signals == []
    runner._dispatch(sv)          # nothing queued: no job, only its tidy
    assert [c.args[4] for c in world.children] == ["run", "tidy"]
    assert X.status(f)["status"] == "stopped"


# ----------------------------------------------------- restarts and stops


def test_restart_requeues_at_the_front_unless_stop_stands(world,
                                                          monkeypatch):
    old = PID0 + 500
    alive = {old}
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: pid in alive
                        or pid == os.getpid())
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: (
        f"/x/.venv/bin/python -I -c {runner.JOB_ENTRY} run" if pid == old
        else ""))

    def signal_(pid, sig):
        world.signals.append((pid, sig))
        alive.discard(pid)
    monkeypatch.setattr(runner, "_signal", signal_)
    world.ps = lambda columns: [f"{old} 1 100", f"{old + 1} {old} 100"]
    f = experiment(world.alice)
    child = types.SimpleNamespace(folder=f, pid=old)
    for stop in (False, True):
        claims(child)
        if stop:
            (f / retro.STOP_NAME).touch()
        state(world.students, pid=PID0 + 999, job={
            "kind": "run", "folder": "alice", "id": EID, "size": "smoke",
            "pid": old})
        alive.add(old)
        world.signals.clear()
        world.swept.clear()
        sv = runner._supervisor()
        runner._recover(sv)
        assert (old, TERM) in world.signals and (old + 1, TERM) in world.signals
        assert world.swept == [world.registry, world.registry]
        m = retro.read_meta(f)
        words = (runner._PAGE_STOP if stop else "The runner restarted while "
                 "it replayed; it was queued again.")
        assert (m["status"], m["stop_reason"]) == ("stopped", words)
        assert not (f / "weeks" / W1).exists() and (f / "weeks" / W0).is_dir()
        assert not (f / retro.STOP_NAME).exists()
        if stop:
            assert not (f / X.QUEUED).exists()
        else:
            assert os.lstat(f / X.QUEUED).st_mtime == 0
            assert runner.queue()[0]["queued_utc"] == "1970-01-01T00:00:00Z"
            (f / X.QUEUED).unlink()
        assert sv["recent"][0]["outcome"] == "ended"
    # a pid whose command line is no job is never signalled
    claims(child)
    monkeypatch.setattr(cli, "_pid_cmdline", lambda pid: "/usr/bin/vim")
    world.signals.clear()
    runner._recover(runner._supervisor())
    assert world.signals == []


def test_restart_closes_the_record_of_a_child_that_died_with_it(world):
    f = experiment(world.alice)
    child = types.SimpleNamespace(folder=f, pid=PID0 + 501)   # no process
    claims(child)
    state(world.students, pid=PID0 + 999, job={
        "kind": "run", "folder": "alice", "id": EID, "size": "smoke",
        "pid": child.pid})
    sv = runner._supervisor()
    runner._recover(sv)
    assert world.signals == []
    m = retro.read_meta(f)
    assert (m["status"], m["stop_reason"]) == (
        "stopped", "The runner restarted while it replayed; it was queued "
        "again.")
    assert not (f / "weeks" / W1).exists() and (f / "weeks" / W0).is_dir()
    assert os.lstat(f / X.QUEUED).st_mtime == 0
    # a child that queued itself again when its runner died: left as it is
    retro.write_meta(f, {**m, "stop_reason": runner._RUNNER_STOP})
    (f / "weeks" / W1).mkdir()
    state(world.students, pid=PID0 + 999, job={
        "kind": "run", "folder": "alice", "id": EID, "size": "smoke",
        "pid": child.pid})
    runner._recover(runner._supervisor())
    assert retro.read_meta(f)["stop_reason"] == runner._RUNNER_STOP
    assert not (f / "weeks" / W1).exists()
    assert runner.queue()[0]["queued_utc"] == "1970-01-01T00:00:00Z"


def test_a_stop_that_ended_the_child_too_queues_it_again(world,
                                                         monkeypatch):
    monkeypatch.setattr(runner, "_stopping", False)
    f = _job(world.alice)
    world.start = claims

    def act(child):
        if child.polls == 2:                 # a logout's SIGTERM to both
            child.code = -15
            runner._stopping = True
    world.act = act
    runner._dispatch(runner._supervisor())
    m = retro.read_meta(f)
    assert (m["status"], m["stop_reason"]) == ("stopped",
                                               runner._RUNNER_STOP)
    assert os.lstat(f / X.QUEUED).st_mtime == 0
    assert runner.read_state()["recent"][0]["outcome"] == "stopped"
    # one that finished as the stop came: done, not queued again
    runner._stopping = False
    (f / X.QUEUED).unlink()
    g = _job(world.bob)

    def done(child):
        if child.polls == 2:
            ends(child)
            runner._stopping = True
    world.act = done
    runner._dispatch(runner._supervisor())
    assert retro.read_meta(g)["status"] == "done"
    assert not (g / X.QUEUED).exists()
    assert runner.read_state()["recent"][0]["outcome"] == "done"


@POSIX
def test_sigterm_kills_and_requeues_at_the_front(world, monkeypatch):
    monkeypatch.setattr(runner, "_stopping", False)
    f = _job(world.alice)
    world.start = claims

    handlers = []

    def act(child):
        handlers.append(signal.getsignal(signal.SIGINT))
        if child.polls == 3:
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    world.act = act
    before = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    assert runner.serve() == 0
    assert handlers and set(handlers) == {runner._on_signal}   # ^C too
    assert (signal.getsignal(signal.SIGTERM),
            signal.getsignal(signal.SIGINT)) == before
    assert runner._stopping is False
    [c] = world.children
    assert c.signals == ["TERM"] and c.polls == 3
    m = retro.read_meta(f)
    words = "The runner stopped while it replayed; it was queued again."
    assert (m["status"], m["stop_reason"]) == ("stopped", words)
    assert os.lstat(f / X.QUEUED).st_mtime == 0
    assert not (f / "weeks" / W1).exists()
    r = runner.read_state()
    assert r["job"] is None
    assert [(w["folder"], w["id"], w["queued_utc"]) for w in r["waiting"]] == [
        ("alice", EID, "1970-01-01T00:00:00Z")]
    assert (r["recent"][0]["outcome"], r["recent"][0]["text"]) == ("stopped",
                                                                   words)
    fd = runner._lock()                         # released at the exit
    assert fd is not None
    os.close(fd)


class HungUp:
    """stdout once its Terminal has closed: the tty refuses every write
    (EIO)."""

    def write(self, text):
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    def flush(self):
        raise OSError(errno.EIO, os.strerror(errno.EIO))


@POSIX
@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="no SIGHUP here")
def test_the_terminal_closing_stops_it_and_nohup_is_left_alone(world,
                                                               monkeypatch):
    monkeypatch.setattr(runner, "_stopping", False)
    f = _job(world.alice)
    world.start = claims
    hup, seen, out = signal.getsignal(signal.SIGHUP), [], sys.stdout

    def act(child):
        seen.append(signal.getsignal(signal.SIGHUP))
        if callable(seen[-1]):
            seen[-1](signal.SIGHUP, None)        # the Terminal closing,
            sys.stdout = HungUp()                # and its tty with it
        else:                                    # under nohup: a SIGTERM
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    world.act = act
    try:
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        assert runner.serve() == 0               # its words lost, not its stop
        sys.stdout = out
        assert seen[-1] is runner._on_signal
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL
        assert world.children[-1].signals == ["TERM"]
        assert os.lstat(f / X.QUEUED).st_mtime == 0     # queued again
        r = runner.read_state()
        assert r["job"] is None and r["recent"][0]["outcome"] == "stopped"
        # under nohup: ignored before, so ignored throughout
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        assert runner.serve() == 0
        assert seen[-1] is signal.SIG_IGN
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
    finally:
        sys.stdout = out
        signal.signal(signal.SIGHUP, hup)


def test_a_new_head_reexecs_between_jobs_only(world):
    _job(world.alice)
    world.start = claims

    def act(child):
        world.head = "b" * 40                    # a pull meanwhile
        if child.polls == 3:
            assert world.execs == []
            ends(child)
    world.act = act
    sv = runner._supervisor()
    runner._dispatch(sv)
    assert world.execs == [] and len(world.children) == 1
    with pytest.raises(Reexec):
        runner._dispatch(sv)
    assert world.execs == [(sys.executable,
                            [sys.executable, *sys.orig_argv[1:]])]
    # a HEAD that cannot be read never re-executes
    world.execs.clear()
    world.head = ""
    runner._dispatch(sv)
    assert world.execs == []


def test_dispatch_refusals_are_recorded_and_the_flag_removed(world, tmp_path):
    sv = runner._supervisor()
    if os.name != "nt":
        f = _job(world.alice)
        # queued a minute before the supervisor's clock, whatever the date
        os.utime(f / X.SETTINGS, (world.clock[0] - 60,) * 2)
        (f / "weeks").mkdir()
        (tmp_path / "elsewhere").mkdir()
        os.symlink(tmp_path / "elsewhere", f / "weeks" / W0)
        runner._dispatch(sv)
        words = (f"experiments/{EID}/weeks/{W0} is a link, and the runner "
                 "follows no link in a student folder (MACHINE)")
        assert world.children == [] and not (f / X.QUEUED).exists()
        r = runner.read_state()
        assert (r["recent"][0]["outcome"], r["recent"][0]["text"]) == (
            "refused", words)
        assert r["waiting"] == []
        assert runner.refusal("alice", EID) == words
        (f / "weeks" / W0).unlink()
        # queued again: its settings written again, the note goes
        os.utime(f / X.SETTINGS, (world.clock[0] + 5, world.clock[0] + 5))
        assert runner.refusal("alice", EID) == ""
    # the child refuses (exit 3): the last line of its log
    g = _job(world.bob)
    os.utime(g / X.SETTINGS, (world.clock[0] - 60,) * 2)
    said = ("beta@9: no such version; the library has no model of that name "
            "(MODEL_NOT_FOUND)")

    def start(child):
        child.kw["stdout"].write("Traceback (most recent call last):\n"
                                 f"{said}\n\n")
    world.start = start
    world.act = lambda c: setattr(c, "code", 3)
    runner._dispatch(sv)
    r = runner.read_state()
    assert (r["recent"][0]["outcome"], r["recent"][0]["text"]) == (
        "refused", said)
    assert not (g / X.QUEUED).exists()
    assert runner.refusal("bob", EID) == said


def test_pause_is_cleared_while_a_job_runs(world):
    f = _job(world.alice)
    world.start = claims
    seen = []

    def act(child):
        if child.polls == 1:
            (f / retro.PAUSE_NAME).touch()
        seen.append((f / retro.PAUSE_NAME).exists())
        if child.polls == 3:
            ends(child)
    world.act = act
    runner._dispatch(runner._supervisor())
    assert seen == [True, False, False]
    assert runner.read_state()["recent"][0]["outcome"] == "done"
    assert _cleared(f)


def test_recent_records_seconds_k_and_peaks(world, monkeypatch):
    monkeypatch.setattr(pf, "DEFAULT_SHARD_WIDTH", 16)
    f = _job(world.alice)
    # a segment before this one stored the first week
    retro.write_meta(f, {"status": "stopped", "week_seconds": {W0: 60.0}})
    world.start = claims
    world.ps = lambda columns: ([f"{world.children[-1].pid} 1 {2 ** 20}"]
                                if columns == "pid=,ppid=,rss=" else [])

    def act(child):
        if child.polls == 4:
            retro.delete_tree(f / "weeks" / W1)
            stored(f, W1)
            ends(child, week_seconds={W0: 60.0, W1: 75.0})
    world.act = act
    t0 = world.clock[0]
    runner._dispatch(runner._supervisor())
    [entry] = runner.read_state()["recent"]
    cost = pf.cell_seconds({"n_obs": runner._week_n("2024-25", W1),
                            "particles": 10_000})
    assert entry == {
        "folder": "alice", "id": EID, "size": "smoke", "kind": "run",
        "utc": runner._utc(t0 + 15), "outcome": "done", "text": "",
        "seconds": 15.0, "weeks": 1, "k": round(75.0 / cost, 3),
        "rss_peak": GiB, "disk_peak": entry["disk_peak"]}
    assert entry["disk_peak"] >= retro.dir_size(f) > 0
    # the next estimate of a smoke is timed by it
    est = runner.estimate(SMOKE, weeks=[W0, W1],
                          recent=runner.read_state()["recent"])
    assert est["measured"] is True


def _within(fn, folder: Path) -> None:
    """fn() in a thread, joined: a call that waits on a pipe in the folder
    (opened, or read once it stood in the record's place) is let go by a
    writer opened and closed there, and the test fails, never hangs."""
    failed = []

    def go():
        try:
            fn()
        except BaseException as e:            # noqa: BLE001 (said below)
            failed.append(e)
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(30)
    if t.is_alive():
        for p in folder.iterdir():
            if stat.S_ISFIFO(os.lstat(p).st_mode):
                try:
                    os.close(os.open(p, os.O_WRONLY | os.O_NONBLOCK))
                except OSError:
                    pass
        t.join(30)
        pytest.fail("the supervisor waited on a pipe a student left")
    if failed:
        raise failed[0]


@POSIX
def test_the_supervisors_writes_never_open_what_a_student_left(world):
    """After the child: a pipe or a hard link at run_meta.json.tmp or a
    pipe at QUEUED is removed, never opened (a pipe's writer would wait
    for good, and a pipe in the record's place stops every read; a hard
    link would write into another folder's file). A reader holds each
    pipe open, and _within lets go of a read that waits."""
    f = experiment(world.alice)
    child = types.SimpleNamespace(folder=f, pid=PID0 + 502)
    claims(child)
    tmp = retro.meta_path(f).with_suffix(".json.tmp")
    other = world.students.parent / "other.json"
    other.write_text("kept", encoding="utf-8")
    readers = []
    try:
        for planted in ("pipe", "link"):
            if planted == "pipe":
                os.mkfifo(tmp)
                readers.append(os.open(tmp, os.O_RDONLY | os.O_NONBLOCK))
            else:
                os.link(other, tmp)
            os.mkfifo(f / X.QUEUED)
            readers.append(os.open(f / X.QUEUED, os.O_RDONLY | os.O_NONBLOCK))
            _within(lambda: runner._settle(f, "why", live=True,
                                           requeue=True), f)
            # files, before anything here reads one
            assert runner._is_file(retro.meta_path(f))
            assert runner._is_file(f / X.QUEUED)
            m = retro.read_meta(f)
            assert (m["status"], m["stop_reason"]) == ("stopped", "why")
            assert os.lstat(f / X.QUEUED).st_mtime == 0
            assert not os.path.lexists(tmp)
            assert other.read_text(encoding="utf-8") == "kept"
            os.unlink(f / X.QUEUED)
            claims(child)
        assert all(os.read(fd, 100) == b"" for fd in readers)
        # a record that is not a regular file is not written at all
        os.unlink(retro.meta_path(f))
        os.symlink(other, retro.meta_path(f))
        runner._close(f, "why")
        assert other.read_text(encoding="utf-8") == "kept"
        assert os.path.islink(retro.meta_path(f))
    finally:
        for fd in readers:
            os.close(fd)


@POSIX
def test_the_runners_own_files_are_never_written_through_a_link(world):
    away = world.students.parent / "away.txt"
    away.write_text("kept", encoding="utf-8")
    d = runner.state_dir()
    os.symlink(away, d / runner.LOG_FILE)
    os.symlink(away, d / (runner.STATE_FILE + ".tmp"))
    _job(world.alice)
    world.act = ends
    runner._dispatch(runner._supervisor())
    assert len(world.children) == 1
    assert away.read_text(encoding="utf-8") == "kept"
    assert runner._is_file(d / runner.LOG_FILE)
    assert runner._is_file(d / runner.STATE_FILE)
    assert not os.path.lexists(d / (runner.STATE_FILE + ".tmp"))


def test_a_command_line_that_is_not_utf8_hides_no_replay(monkeypatch):
    out = (b"  1 /Applications/Caf\xe9.app/x\n"
           b"  2 /x/.venv/bin/python /x/weeks/2024-12-28/runner_0.py\n")

    def run(args, **kw):
        # subprocess's own decoding: the locale's, strict, unless told
        assert args[:2] == ["ps", "-Ao"] and kw.get("text") is True
        text = out.decode(kw.get("encoding") or "utf-8",
                          kw.get("errors") or "strict")
        return subprocess.CompletedProcess(args, 0, text, "")
    monkeypatch.setattr(runner.subprocess, "run", run)
    lines = runner._ps("pid=,command=")
    assert len(lines) == 2 and "\ufffd" in lines[0]
    assert lines[1].endswith("runner_0.py")


# ------------------------------------------------------------------- tidy


def _scored(f: Path, *, heavy: bool = False, summary: bool = True,
            shipped=None) -> Path:
    """A finished experiment: its record, two stored weeks (lean, or with
    their samples when heavy) and, with summary, a summary.json newer
    than all of it, scored by this rule (no truth here to move)."""
    retro.write_meta(f, {"status": "done", "finished_utc": time.time() - 900,
                         "started_utc": time.time() - 2000,
                         "settings": {"experiment": "e" * 64,
                                      "weeks": [W0, W1]}})
    for w in (W0, W1):
        wd = f / "weeks" / w
        wd.mkdir(parents=True)
        (wd / "quantiles.json").write_text("{}", encoding="utf-8")
        if heavy and w == W1:
            (wd / "samples.json").write_text("{}", encoding="utf-8")
        else:
            (wd / "samples.dropped.json").write_text('{"bytes": 1}',
                                                     encoding="utf-8")
    if summary:
        p = f / X.SUMMARY
        p.write_text(json.dumps({"format_version": 1, "shipped": shipped,
                                 "scored": {"scores_v": retro.SCORES_V}}),
                     encoding="utf-8")
        later = time.time() + 100
        os.utime(p, (later, later))
    return f


def test_tidy_resets_drops_and_rescores_only_when_needed(world):
    top = world.alice
    fresh = _scored(experiment(top, {**SMOKE, "oracle": False}))
    unscored = _scored(experiment(top), summary=False)
    heavy = _scored(experiment(top, {**SMOKE, "size": "pilot"}), heavy=True)
    moved = _scored(experiment(top, {**SMOKE, "size": "full"}), shipped={
        "root": str(world.students.parent / "elsewhere" / "2024-25"),
        "started_utc": None})
    _job(world.bob)                              # queued: never tidied
    rr = runs.APP_STATE / "retro"
    assert X.stale(fresh, retro_root=rr) == ""
    assert X.stale(unscored, retro_root=rr) == "not scored yet"
    assert X.stale(heavy, retro_root=rr) == ""
    assert X.stale(moved, retro_root=rr) == (
        "the shipped replay it was compared with moved")
    world.act = lambda c: setattr(c, "code", 0)
    sv = runner._supervisor()
    for _ in range(5):
        runner._tidy(sv)
    assert [c.args[4:] for c in world.children] == [
        ["tidy", str(world.students), "alice", f.name]
        for f in (moved, heavy, unscored)]
    assert all(c.at_spawn["job"]["kind"] == "tidy" for c in world.children)
    pilot = runner.limits("pilot")
    assert world.children[0].at_spawn["job"]["limits"]["disk"] == pilot.disk
    assert runner.read_state()["recent"] == []
    # an unfinished week, and a folder whose job just ended: looked at at once
    (fresh / "weeks" / "2025-02-08").mkdir()
    sv["tidy_due"].add(("alice", fresh.name))
    runner._tidy(sv)
    assert world.children[-1].args[7] == fresh.name
    # an hour on, each is looked at again
    n = len(world.children)
    runner._tidy(sv)
    assert len(world.children) == n
    world.clock[0] += runner.TIDY_EVERY_S
    runner._tidy(sv)
    assert len(world.children) == n + 1


def test_a_held_queue_starts_no_tidy(world, monkeypatch):
    f = _scored(experiment(world.alice), summary=False)     # needs one
    seen = []
    real = X.status
    monkeypatch.setattr(X, "status", lambda folder: seen.append(
        os.path.realpath(folder)) or real(folder))
    g = None
    if os.name != "nt":
        # a record that is a link: never followed, the folder left alone
        g = experiment(world.bob)
        retro.write_meta(world.students.parent / "away", {"status": "done"})
        os.symlink(world.students.parent / "away" / retro.META_NAME,
                   retro.meta_path(g))
    sv = runner._supervisor()
    monkeypatch.setattr(runner, "_engine_ready", lambda: False)
    runner._dispatch(sv)
    assert world.children == []
    assert runner.read_state()["waiting_why"] == (
        "the particle-filter engine is not installed on the runner")
    monkeypatch.setattr(runner, "_engine_ready", lambda: True)
    world.act = lambda c: setattr(c, "code", 0)
    for _ in range(3):
        runner._dispatch(sv)
    assert [c.args[4:] for c in world.children] == [
        ["tidy", str(world.students), "alice", f.name]]
    assert g is None or os.path.realpath(g) not in seen


# ------------------------------------------------------------- the command


def test_runner_command_is_listed_and_refuses_without_students(tmp_path,
                                                               monkeypatch):
    from typer.testing import CliRunner
    from flubnf.cli import HELP_PANELS, app
    assert HELP_PANELS["Replay & verification"][-1] == "runner"
    r = CliRunner().invoke(app, ["--help"], env={"NO_COLOR": "1"},
                           terminal_width=200)
    assert r.exit_code == 0, r.output
    out = re.sub(r"\x1b\[[0-9;]*m", "", r.output)
    panel = out[out.index("─ Replay & verification "):out.index(
        "─ Donor banks ")]
    assert re.search(r"│ runner +Work the student experiment queue on this "
                     r"computer", panel), panel
    r = CliRunner().invoke(app, ["runner"])
    assert r.exit_code == 1
    assert r.output.strip() == (
        f"Not started: {runner.STUDENTS} is missing: make it, and clone each "
        "student's fork into it (~/Students/<name>).")
    # Windows: no killpg (nor flock)
    s = tmp_path / "Students"
    s.mkdir()
    monkeypatch.setattr(runner, "STUDENTS", s)
    monkeypatch.delattr(os, "killpg", raising=False)
    r = CliRunner().invoke(app, ["runner"])
    assert r.exit_code == 1
    assert r.output.strip() == (
        "Not started: the runner needs flock and killpg, which this computer "
        "lacks; it runs on the students' Mac.")
    assert list(s.iterdir()) == []
