"""The runner's job child (app/core/runner.py job_main, run in this
process with resource and the parent's pid faked): the job runs in its
student's folder only, the library read from there and the fits'
registry in the runner's folder; an unfinished week is fitted from its
start; the flag is claimed at the first week (gone already: stopped,
nothing fitted); a supervisor gone without its stop queues the job
again first unless STOP stands; a link planted between weeks stops the
job before the next, and a folder swapped for a link while a week fits
has nothing dropped or removed through it; every stored week is lean
before scoring and the
summary is the one a heavy run gives; a failed week is removed whole;
refusals exit 3 and errors 1; and RLIMIT_FSIZE is set before anything
else.

retro.run_week is faked (test_experiments._weeks_run), writing the real
samples and sidecar of test_lean_storage._store where the drop needs
them; the truth is test_experiment_summary's synthetic hub."""
import json
import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import runs                                # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from test_experiments import (SMOKE_FP, _register,       # noqa: E402,F401
                              _weeks_run, season, truth)
from test_runner_folders import (SMOKE, W0, W1,          # noqa: E402,F401
                                 experiment, student, students, tree)

EID = "sihrs_2024-25_smoke_oracle"
LINKS = pytest.mark.skipif(os.name == "nt",
                           reason="links need rights on Windows")


@pytest.fixture
def job(season, students, tmp_path, monkeypatch):
    """job_main in this process: resource faked (its calls kept), the
    parent's pid fixed, the install's state and its build in tmp, alice
    and bob on the runner. (setrlimit, argv(...) for a run of alice's)."""
    calls = []
    monkeypatch.setitem(sys.modules, "resource", types.SimpleNamespace(
        RLIMIT_FSIZE="FSIZE",
        setrlimit=lambda what, lim: calls.append((what, lim,
                                                  runner.STUDENTS))))
    monkeypatch.setattr(os, "getppid", lambda: 4242)
    monkeypatch.setattr(runs, "APP_STATE", tmp_path / "state")
    (tmp_path / "state" / "retro").mkdir(parents=True)
    monkeypatch.setattr(runs, "_git_sha", lambda repo: "53f1acf")
    w = types.SimpleNamespace(
        setrlimit=calls, students=students,
        alice=student(students, "alice"), bob=student(students, "bob"),
        main=sb.SANDBOX)
    w.argv = lambda eid=EID, size="smoke", name="alice": [
        "run", str(students), name, eid, size]
    return w


@contextmanager
def _in(top: Path):
    """The Sandbox moved to a student's folder for a moment (registering
    a model there)."""
    saved = (sb.SANDBOX, sb.MODELS, sb.RUNS)
    sb.SANDBOX, sb.MODELS, sb.RUNS = top, top / "models", top / "runs"
    try:
        yield top
    finally:
        sb.SANDBOX, sb.MODELS, sb.RUNS = saved


def _queued(top: Path, settings=SMOKE) -> Path:
    return experiment(top, settings, queued=True)


def _frozen(f: Path, status: str = "stopped") -> None:
    """The smoke's run record as a stopped first segment leaves it."""
    retro.write_meta(f, {"status": status, "season": "2024-25",
                         "settings": {"experiment": SMOKE_FP, "model": "sihrs",
                                      "weeks": [W0, W1],
                                      "locations": ["California", "Vermont"],
                                      "replicates": 1, "particles": 10_000}})


def test_the_job_runs_in_its_folder_only(job, monkeypatch, capsys):
    with _in(job.alice):
        ref = _register("beta")
    settings = {"model": ref, "season": "2024-25"}
    f = _queued(job.alice, settings)
    experiment(job.bob, settings, queued=True)
    (job.main / "experiments").mkdir(parents=True, exist_ok=True)
    (runs.APP_STATE / "ledger.txt").write_text("kept\n", encoding="utf-8")
    seen = []
    real = L._verified

    def verified(name, version):
        seen.append(("library", L.root()))
        return real(name, version)
    monkeypatch.setattr(L, "_verified", verified)

    def at_week(root, asof):
        seen.append(("week", sb.SANDBOX, X.root(), pf.RUNNER_PIDS_FILE,
                     root))
    calls = _weeks_run(monkeypatch, at_week)
    before = {"bob": tree(job.bob), "main": tree(job.main),
              "state": tree(runs.APP_STATE),
              "alice": {k: v for k, v in tree(job.alice).items()
                        if not k.startswith(f"experiments/{f.name}")
                        and k != "experiments"}}
    rest = {k: v for k, v in tree(job.students).items()
            if not k.startswith(("alice", "bob", runner.STATE_NAME))}
    assert runner.job_main(job.argv(f.name)) == 0
    assert [c["asof"] for c in calls] == [W0, W1]
    assert {s[1] for s in seen if s[0] == "library"} == {
        job.alice / "library"}
    weeks = [s for s in seen if s[0] == "week"]
    assert {(s[1], s[2], s[3]) for s in weeks} == {(
        job.alice, job.alice / "experiments",
        runner.state_dir() / runner.REGISTRY_FILE)}
    assert {s[4] for s in weeks} == {f}
    assert retro.read_meta(f)["status"] == "done"
    assert retro.read_meta(f)["settings"]["model"] == ref
    # put back after: this process's Sandbox and registry are its own
    assert sb.SANDBOX == job.main and pf.RUNNER_PIDS_FILE != (
        runner.state_dir() / runner.REGISTRY_FILE)
    assert tree(job.bob) == before["bob"]
    assert tree(job.main) == before["main"]
    assert tree(runs.APP_STATE) == before["state"]
    assert {k: v for k, v in tree(job.alice).items()
            if not k.startswith(f"experiments/{f.name}")
            and k != "experiments"} == before["alice"]
    assert {k: v for k, v in tree(job.students).items()
            if not k.startswith(("alice", "bob", runner.STATE_NAME))} == rest
    assert not (f / X.QUEUED).exists()


def test_unfinished_weeks_are_fitted_from_their_start(job, monkeypatch):
    f = _queued(job.alice)
    _frozen(f)
    wd = f / "weeks" / W0
    (wd / "Vermont_r0").mkdir(parents=True)
    (wd / "Vermont_r0" / "pf.conf").write_text("bng_command = /bin/sh\n",
                                               encoding="utf-8")
    (wd / "cells.json").write_text(json.dumps([{"key": "Vermont_r0",
                                                "dir": "/elsewhere"}]),
                                   encoding="utf-8")
    (wd / retro.PREP_NAME).write_text("{}", encoding="utf-8")
    (wd / "json.py").write_text("import os\n", encoding="utf-8")
    there = []
    calls = _weeks_run(monkeypatch)
    real = retro.run_week

    def week(root, season, asof, *a, **k):
        there.append(sorted(p.name for p in (Path(root) / "weeks" / asof)
                            .iterdir()) if (Path(root) / "weeks" / asof)
                     .exists() else None)
        return real(root, season, asof, *a, **k)
    monkeypatch.setattr(retro, "run_week", week)
    assert runner.job_main(job.argv()) == 0
    assert [c["asof"] for c in calls] == [W0, W1]
    assert there == [None, None]
    assert sorted(p.name for p in wd.iterdir()) == [RS.SAMPLES_JSON]


def test_the_flag_is_claimed_at_the_first_week(job, monkeypatch):
    f = _queued(job.alice)
    flag = []
    calls = _weeks_run(monkeypatch, lambda root, asof: flag.append(
        (root / X.QUEUED).exists()))
    assert runner.job_main(job.argv()) == 0
    assert flag == [False, False] and len(calls) == 2
    # gone already (Stop on its page meanwhile): stopped, nothing fitted
    retro.delete_tree(f)
    f = experiment(job.alice)
    calls.clear()
    assert runner.job_main(job.argv()) == 0
    assert calls == []
    m = retro.read_meta(f)
    assert m["status"] == "stopped" and not m.get("stop_reason")
    assert X.status(f)["weeks_done"] == 0
    # a supervisor gone without its stop (its Terminal closed, a crash;
    # the parent's pid changed): stops before a week and, as the
    # supervisor's stop would, queues the job again first
    retro.delete_tree(f)
    f = _queued(job.alice)
    pids = iter([4242, 1])
    monkeypatch.setattr(os, "getppid", lambda: next(pids, 1))
    assert runner.job_main(job.argv()) == 0
    m = retro.read_meta(f)
    assert calls == [] and (m["status"], m["stop_reason"]) == (
        "stopped", runner._RUNNER_STOP)
    assert os.lstat(f / X.QUEUED).st_mtime == 0
    assert runner.queue()[0]["queued_utc"] == "1970-01-01T00:00:00Z"
    # after its first week, with a Stop from its page standing: its words,
    # and not queued again
    retro.delete_tree(f)
    f = _queued(job.alice)

    def ppid(n=[0]):
        n[0] += 1
        if n[0] == 3:                        # the hook's second look
            retro.request_stop(f)
        return 4242 if n[0] < 3 else 1
    monkeypatch.setattr(os, "getppid", ppid)
    assert runner.job_main(job.argv()) == 0
    m = retro.read_meta(f)
    assert [c["asof"] for c in calls] == [W0]
    assert (m["status"], m["stop_reason"]) == ("stopped", runner._PAGE_STOP)
    assert not os.path.lexists(f / X.QUEUED)
    assert not retro.stop_path(f).exists()


@LINKS
def test_a_link_planted_between_weeks_stops_the_job(job, monkeypatch,
                                                    tmp_path):
    f = _queued(job.alice)
    (tmp_path / "elsewhere").mkdir()

    def plant(root, asof):
        if asof == W0:
            os.symlink(tmp_path / "elsewhere", root / "weeks" / W0 / "planted")
    calls = _weeks_run(monkeypatch, plant)
    assert runner.job_main(job.argv()) == 0
    assert [c["asof"] for c in calls] == [W0]
    m = retro.read_meta(f)
    assert m["status"] == "stopped"
    assert m["stop_reason"] == (
        f"The runner stopped it before {W1}: experiments/{EID}/weeks/{W0}/"
        "planted is a link, and the runner follows no link in a student "
        "folder. Finished weeks are kept.")
    assert X.status(f)["stop_reason"] == m["stop_reason"]


def test_each_week_is_made_lean_before_scoring(job, truth, monkeypatch):
    from app.tests.test_experiment_summary import _q, _shipped_root
    from test_lean_storage import _store, _without
    monkeypatch.setattr(retro, "_now", lambda: 1_790_000_000.0)
    rr = runs.APP_STATE / "retro"
    _shipped_root(rr, pf={w: _q(12.0, ["California", "Vermont"])
                          for w in (W0, W1)})
    seeds = {W0: 0, W1: 1}
    calls = _weeks_run(monkeypatch, lambda root, asof: _store(
        root, asof, seed=seeds[asof]))
    lean_at_score = []
    real = X.score

    def score(folder, **kw):
        lean_at_score.append([RS._lean(RS._week_dir(folder, w))
                              for w in (W0, W1)])
        return real(folder, **kw)
    monkeypatch.setattr(X, "score", score)
    f = _queued(job.alice)
    assert runner.job_main(job.argv()) == 0
    assert len(calls) == 2 and lean_at_score == [[True, True]]
    for w in (W0, W1):
        names = {p.name for p in (f / "weeks" / w).iterdir()}
        assert RS.DROPPED_NAME in names and names <= set(X.LEAN_KEEP)
    # the control: the same experiment in bob's folder, kept heavy
    with _in(job.bob):
        X.run(SMOKE, retro_root=rr, flubnf_build="53f1acf")
    g = job.bob / "experiments" / EID
    assert all(RS.samples_file(g / "weeks" / w) for w in (W0, W1))
    lean = X.read_summary(f / X.SUMMARY)
    heavy = X.read_summary(g / X.SUMMARY)
    assert lean["shipped"]["member"] == "pf"
    assert lean["cells"]["compared"] == 2 * 2 * 4
    assert (_without(lean, ("ran", "disk_bytes"))
            == _without(heavy, ("ran", "disk_bytes")))
    assert lean["ran"]["disk_bytes"] < heavy["ran"]["disk_bytes"] / 2
    assert lean["ran"]["flubnf_build"] == "53f1acf"


def test_a_failed_week_is_removed_whole(job, truth, monkeypatch):
    f = _queued(job.alice)

    def week(root, season, asof, *a, **k):
        wd = Path(root) / "weeks" / asof
        (wd / "Vermont_r0" / "out").mkdir(parents=True)
        (wd / "Vermont_r0" / "out" / "traj.npz").write_bytes(b"x" * 5000)
        if asof == W1:
            raise RuntimeError("all 2 PF fits failed (first: boom); the week "
                               "is not stored")
        (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
        return {"asof": asof}
    monkeypatch.setattr(retro, "run_week", week)
    assert runner.job_main(job.argv()) == 0
    assert not (f / "weeks" / W1).exists()
    assert (f / "weeks" / W0 / RS.SAMPLES_JSON).is_file()
    assert (f / "failures.log").read_text(encoding="utf-8") == (
        f"{W1}: all 2 PF fits failed (first: boom); the week is not stored\n")
    m = retro.read_meta(f)
    assert (m["status"], m["weeks_completed"]) == ("done", 1)
    s = X.read_summary(f / X.SUMMARY)
    assert {"week": W1, "text": "all 2 PF fits failed (first: boom); the "
            "week is not stored"} in s["failures"]



@LINKS
def test_a_weeks_folder_swapped_mid_week_is_left_alone(job, monkeypatch,
                                                       tmp_path, capsys):
    f = _queued(job.alice)
    victim = tmp_path / "victim"
    (victim / W0).mkdir(parents=True)
    (victim / W0 / "keep.txt").write_text("mine", encoding="utf-8")
    before = tree(victim)

    def week(root, season, asof, *a, **k):
        (Path(root) / "weeks" / asof).mkdir(parents=True)
        os.rename(Path(root) / "weeks", tmp_path / "aside")
        os.symlink(victim, Path(root) / "weeks")
        raise RuntimeError("all 2 PF fits failed (first: boom); the week "
                           "is not stored")
    monkeypatch.setattr(retro, "run_week", week)
    assert runner.job_main(job.argv()) == 0
    assert tree(victim) == before
    assert f"runner: {W0} left as it is" in capsys.readouterr().err
    assert retro.read_meta(f)["stop_reason"].startswith(
        f"The runner stopped it before {W1}: experiments/{EID}/weeks is a "
        "link")


@LINKS
def test_an_experiments_folder_swapped_mid_week_drops_nothing_of_bobs(
        job, monkeypatch, tmp_path):
    from test_lean_storage import _store
    f = _queued(job.alice)
    g = experiment(job.bob, meta={"settings": {"experiment": SMOKE_FP,
                                               "weeks": [W0, W1]}})
    _store(g, W0, seed=0)
    before = tree(g / "weeks")

    def swap(root, asof):
        _store(root, asof, seed=0)
        os.rename(job.alice / "experiments", tmp_path / "aside")
        os.symlink(job.bob / "experiments", job.alice / "experiments")
    calls = _weeks_run(monkeypatch, swap)
    assert runner.job_main(job.argv()) == 0
    assert [c["asof"] for c in calls] == [W0]
    assert tree(g / "weeks") == before
    assert RS.samples_file(g / "weeks" / W0) is not None
    assert not (g / X.QUEUED).exists()
    assert not RS._lean(tmp_path / "aside" / EID / "weeks" / W0)


def test_refusals_exit_3_and_errors_exit_1(job, monkeypatch, capsys):
    calls = _weeks_run(monkeypatch)

    def said() -> str:
        return capsys.readouterr().err.strip().splitlines()[-1]
    assert runner.job_main(job.argv(name="zed")) == 3
    assert said() == "there is no student folder 'zed' on this computer (MACHINE)"
    assert runner.job_main(job.argv(eid="sihrs_2024-25_full")) == 3
    assert said() == ("experiments/sihrs_2024-25_full is not in alice's "
                      "folder (MACHINE)")
    f = _queued(job.alice, {"model": "beta@9", "season": "2024-25"})
    assert runner.job_main(job.argv(eid=f.name)) == 3
    assert said() == ("beta@9: no such version; the library has no model of "
                      "that name (MODEL_NOT_FOUND)")
    assert (f / X.QUEUED).is_file()             # never claimed
    assert sorted(p.name for p in f.iterdir()) == [X.QUEUED, X.SETTINGS]
    # a record of another experiment: refused by the plan
    g = _queued(job.alice)
    retro.write_meta(g, {"settings": {"experiment": "0" * 64}})
    assert runner.job_main(job.argv()) == 3
    assert said().endswith("(EXPERIMENT_CHANGED)")
    # every week stored: complete, nothing run
    _frozen(g, status="done")
    for w in (W0, W1):
        (g / "weeks" / w).mkdir(parents=True)
        (g / "weeks" / w / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
    assert runner.job_main(job.argv()) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "complete"
    assert calls == []
    # anything else exits 1, its traceback in the log; flags cleared
    retro.delete_tree(g)
    g = _queued(job.alice)

    def broken(*a, **k):
        retro.request_pause(g)
        raise RuntimeError("the disk went away")
    monkeypatch.setattr(X, "run", broken)
    assert runner.job_main(job.argv()) == 1
    err = capsys.readouterr().err
    assert "RuntimeError: the disk went away" in err and "Traceback" in err
    assert not retro.pause_path(g).exists()
    for argv in ([], ["run"], ["run", "x", "alice", EID, "huge"],
                 ["tidy", "x", "alice"], ["fit", "x", "alice", EID]):
        assert runner.job_main(argv) == 1
    assert job.setrlimit[-1][0] == "FSIZE"


def test_rlimit_fsize_is_set_first(job, truth, monkeypatch, tmp_path):
    _weeks_run(monkeypatch)
    _queued(job.alice)
    before = tmp_path / "before"
    for argv, code, lim in (
            (job.argv(), 0, 512 * runner.MiB),
            (job.argv(eid="sihrs_2024-25_full_oracle", size="full"), 3,
             10 * runner.GiB),
            (["tidy", str(job.students), "alice", EID], 0, 1 * runner.GiB)):
        monkeypatch.setattr(runner, "STUDENTS", before)
        assert runner.job_main(argv) == code
        # the size's disk limit (a tidy: the pilot's), before STUDENTS was
        # set; then STUDENTS is the supervisor's
        assert job.setrlimit[-1] == ("FSIZE", (lim, lim), before)
        assert runner.STUDENTS == job.students
    assert len(job.setrlimit) == 3


def test_tidy_drops_and_scores_a_heavy_folder(job, truth, monkeypatch):
    from test_lean_storage import _store
    f = _queued(job.alice)
    calls = _weeks_run(monkeypatch, lambda root, asof: _store(root, asof))
    with _in(job.alice):
        X.run(SMOKE, retro_root=runs.APP_STATE / "retro")
    (f / X.QUEUED).unlink()
    assert len(calls) == 2 and all(RS.samples_file(f / "weeks" / w)
                                   for w in (W0, W1))
    (f / X.SUMMARY).unlink()
    (f / "weeks" / "2025-02-08" / "Vermont_r0").mkdir(parents=True)
    assert runner._tidy_needed(f, runs.APP_STATE / "retro")
    assert runner.job_main(["tidy", str(job.students), "alice", EID]) == 0
    assert not (f / "weeks" / "2025-02-08").exists()
    assert all(RS._lean(f / "weeks" / w) for w in (W0, W1))
    assert X.read_summary(f / X.SUMMARY)["complete"] is True
    assert not runner._tidy_needed(f, runs.APP_STATE / "retro")
    t = (f / X.SUMMARY).stat().st_mtime_ns
    assert runner.job_main(["tidy", str(job.students), "alice", EID]) == 0
    assert (f / X.SUMMARY).stat().st_mtime_ns == t      # scored once only
