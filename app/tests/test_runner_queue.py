"""The runner's queue as a student's console sees it (app/core/runner.py):
enqueue writes experiment.json and an empty QUEUED and nothing else, and
answers already queued, replaying and complete in words; the plan's
refusals pass through, the reference is named from runner.json's retro
root, NO_REFERENCE is said, and the free floor counts the keep of the
job running and those ahead. The queue is first in, first out with a
requeued job first; position and the wait come from runner.json (a stale
heartbeat, a dead pid or an unknown format reading as a runner that is
not running, whose job then holds nothing); Stop dequeues or stops;
status says queued; Storage leaves out a folder whose record it cannot
read safely; and without a runner every function answers as before."""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402
from test_runner_folders import (SMOKE, W0, W1, calendar,  # noqa: E402,F401
                                 experiment, stored, student, students,
                                 tree)

GiB, MiB = runner.GiB, runner.MiB
EID = "sihrs_2024-25_smoke_oracle"
#: a pid no process has (above every pid_max)
DEAD = 2_147_483_646


@pytest.fixture
def alice(students, monkeypatch) -> Path:
    """This console's Sandbox is alice's folder on the runner, 2024-25's
    calendar is the suite's, and the disk has room."""
    top = student(students, "alice")
    monkeypatch.setattr(sb, "SANDBOX", top)
    monkeypatch.setattr(sb, "MODELS", top / "models")
    monkeypatch.setattr(sb, "RUNS", top / "runs")
    calendar(monkeypatch)
    monkeypatch.setattr(runner, "_free", lambda: 500 * GiB)
    return top


def state(students: Path, **fields) -> dict:
    """runner.json as a running supervisor writes it (this process its
    pid, a heartbeat now), `fields` over it."""
    now = runner._now()
    obj = {"format_version": 1, "pid": os.getpid(), "build": "24ac926",
           "started_utc": runner._utc(now - 600),
           "heartbeat_utc": runner._utc(now), "retro_root": "",
           "waiting_why": "", "job": None, "waiting": [], "recent": [],
           **fields}
    (students / runner.STATE_NAME / runner.STATE_FILE).write_text(
        json.dumps(obj), encoding="utf-8", newline="\n")
    return obj


def _running(f: Path) -> None:
    """A run record under way in this process."""
    retro.write_meta(f, {"status": "running", "pid": os.getpid(),
                         "heartbeat_utc": time.time(),
                         "segment_start_utc": time.time(),
                         "settings": {"experiment": "e" * 64,
                                      "weeks": [W0, W1]}})


# ---------------------------------------------------------------- enqueue


def test_enqueue_writes_the_settings_and_the_flag_only(alice, students,
                                                       tmp_path):
    state(students)
    threads = threading.active_count()
    before = tree(students)
    got = runner.enqueue(SMOKE)
    f = alice / "experiments" / EID
    assert sorted(p.name for p in f.iterdir()) == [X.QUEUED, X.SETTINGS]
    assert (f / X.SETTINGS).read_text(encoding="utf-8") == X.settings_text(
        SMOKE)
    assert (f / X.QUEUED).read_bytes() == b""
    after = tree(students)
    assert sorted(set(after) - set(before)) == [
        f"alice/sandbox/experiments/{EID}",
        f"alice/sandbox/experiments/{EID}/{X.QUEUED}",
        f"alice/sandbox/experiments/{EID}/{X.SETTINGS}"]
    # every file there before is as it was (a folder's mtime moves)
    assert all(after[k] == v for k, v in before.items() if v[0] != -1)
    assert threading.active_count() == threads      # no worker, no claim
    assert (got["id"], got["state"], got["position"], got["runner"]) == (
        EID, "queued", 1, True)
    assert got["estimate"]["weeks"] == 2 and got["free"] == 500 * GiB
    # a file elsewhere queues the same way
    src = tmp_path / "pilot.json"
    src.write_text(json.dumps({**SMOKE, "size": "pilot"}), encoding="utf-8")
    got = runner.enqueue(src)
    assert got["state"] == "queued" and got["id"] == "sihrs_2024-25_pilot_oracle"
    assert (alice / "experiments" / got["id"] / X.QUEUED).is_file()


def test_enqueue_answers(alice, students, tmp_path):
    from test_experiments import _replay
    rr = tmp_path / "retro"
    _replay(rr / "2024-25")
    state(students, retro_root=str(rr))
    got = runner.enqueue(SMOKE)
    assert got["kind"] == "ok" and got["findings"] == []
    assert got["reference"] == {"member": "pf", "root": str(rr / "2024-25"),
                                "started_utc": "2026-09-21T14:13:20Z"}
    assert ("Compared with the shipped replay of 2024-25 (the Oracle SIHRS) "
            "on the cells both score.") in got["detail"]
    f = alice / "experiments" / EID
    mtime = (f / X.SETTINGS).stat().st_mtime_ns
    again = runner.enqueue(SMOKE)
    assert (again["state"], again["kind"], again["text"]) == (
        "already", "info", f"{EID} is already queued: 1st in line.")
    assert (f / X.SETTINGS).stat().st_mtime_ns == mtime
    # the runner's job, or a record under way: replaying
    assert runner.stop("alice", EID) == "dequeued"
    state(students, retro_root=str(rr),
          job={"kind": "run", "folder": "alice", "id": EID, "size": "smoke",
               "pid": 4242, "keep_bytes": 0})
    got = runner.enqueue(SMOKE)
    assert (got["state"], got["kind"], got["text"]) == (
        "replaying", "info", f"{EID} is replaying on the runner.")
    # a tidy of it (scoring, its weeks made lean) does not stop a queueing
    state(students, retro_root=str(rr),
          job={"kind": "tidy", "folder": "alice", "id": EID, "size": "smoke",
               "pid": 4242, "keep_bytes": 0})
    assert runner.enqueue(SMOKE)["state"] == "queued"
    assert runner.stop("alice", EID) == "dequeued"
    state(students, retro_root=str(rr))
    _running(f)
    assert runner.enqueue(SMOKE)["state"] == "replaying"
    assert not (f / X.QUEUED).exists()
    # every week stored: complete
    retro.write_meta(f, {"status": "done", "settings": {
        "experiment": "e" * 64, "weeks": [W0, W1]}})
    for w in (W0, W1):
        stored(f, w)
    got = runner.enqueue(SMOKE)
    assert (got["state"], got["text"]) == (
        "complete", f"{EID} is complete: every week is stored, nothing to "
        "fit.")
    assert not (f / X.QUEUED).exists()
    # the plan's refusals, with their codes, before anything is written
    with pytest.raises(Refusal) as e:
        runner.enqueue({"model": "beta@9", "season": "2024-25"})
    assert e.value.code == "MODEL_NOT_FOUND"
    with pytest.raises(Refusal) as e:
        runner.enqueue({"model": "sihrs", "season": "1999-00"})
    assert e.value.code == "SEASON_NO_WEEKS"
    assert sorted(p.name for p in (alice / "experiments").iterdir()) == [EID]
    # a retro root with no shipped replay: NO_REFERENCE, said, and warn
    state(students, retro_root=str(tmp_path / "empty"))
    got = runner.enqueue({**SMOKE, "oracle": False})
    assert got["kind"] == "warn" and got["reference"] is None
    assert [x["code"] for x in got["findings"]] == ["NO_REFERENCE"]
    assert ("no shipped replay of 2024-25 here holds the Liu-West filter on "
            "the shipped settings: the summary will have no shipped side "
            "(NO_REFERENCE).") in got["detail"]
    # no runner.json at all: the reference waits for the runner
    (students / runner.STATE_NAME / runner.STATE_FILE).unlink()
    got = runner.enqueue({**SMOKE, "size": "pilot"})
    assert got["findings"] == [] and got["runner"] is False
    assert got["text"] == ("Queued sihrs_2024-25_pilot_oracle; the runner is "
                           "not running, so it waits until it is started.")
    assert "The reference is checked when the runner starts it." in got[
        "detail"]
    assert got["kind"] == "warn"


@pytest.mark.skipif(os.name == "nt", reason="links need rights on Windows")
def test_enqueue_refuses_a_folder_check_refuses(alice, students, tmp_path):
    state(students)
    f = experiment(alice, weeks=[W0, W1])
    (tmp_path / "elsewhere").mkdir()
    (f / "weeks").mkdir()
    os.symlink(tmp_path / "elsewhere", f / "weeks" / W0)
    with pytest.raises(Refusal) as e:
        runner.enqueue(SMOKE)
    assert str(e.value) == (f"experiments/{EID}/weeks/{W0} is a link, and the "
                            "runner follows no link in a student folder")
    assert not (f / X.QUEUED).exists()


def test_enqueue_keeps_the_free_floor(alice, students, monkeypatch):
    peak = runner.estimate(SMOKE, weeks=[W0, W1])["peak_bytes"]
    state(students, job={"kind": "run", "folder": "bob", "id": "x_2024-25_full",
                         "size": "full", "pid": 1, "keep_bytes": 100 * MiB},
          waiting=[{"folder": "carol", "id": "y_2024-25_pilot",
                    "size": "pilot", "seconds": 600, "keep_bytes": 300 * MiB}])
    ahead = 400 * MiB
    free = runner.FREE_FLOOR - int(1.8 * GiB) + ahead + peak
    monkeypatch.setattr(runner, "_free", lambda: free)
    with pytest.raises(Refusal) as e:
        runner.enqueue(SMOKE)
    assert e.value.code == "MACHINE"
    assert [x["text"] for x in e.value.findings] == [
        f"{EID} needs about 33.7 MB of disk while it runs, which would leave "
        "18.2 GB free; FluBNF keeps 20.0 GB free on this disk",
        "The experiments queued ahead of it keep 400.0 MB. Delete experiments "
        "you no longer need, or ask Ely to free space."]
    assert list((alice / "experiments").iterdir()) == []
    # the room it needs: queued, behind carol's
    monkeypatch.setattr(runner, "_free", lambda: free + 2 * GiB)
    got = runner.enqueue(SMOKE)
    assert (got["state"], got["position"]) == ("queued", 2)


# ------------------------------------------------------- the queue's order


def test_queue_is_first_in_first_out_with_requeued_first(students):
    tops = {n: student(students, n) for n in ("alice", "bob", "carol")}
    jobs = {
        ("alice", "pilot"): 300, ("alice", "smoke"): 300, ("bob", "smoke"): 200,
        ("carol", "full"): 0, ("carol", "smoke"): 100}
    for (name, size), t in jobs.items():
        f = experiment(tops[name], {**SMOKE, "size": size}, queued=True)
        os.utime(f / X.QUEUED, (t, t))
    # neither a folder without the flag, nor a flag that is not a file
    experiment(tops["bob"], {**SMOKE, "size": "full"})
    odd = experiment(tops["bob"], {**SMOKE, "size": "pilot"})
    (odd / X.QUEUED).mkdir()
    got = [(q["folder"], q["size"], q["queued_utc"]) for q in runner.queue()]
    assert got == [("carol", "full", "1970-01-01T00:00:00Z"),
                   ("carol", "smoke", "1970-01-01T00:01:40Z"),
                   ("bob", "smoke", "1970-01-01T00:03:20Z"),
                   ("alice", "pilot", "1970-01-01T00:05:00Z"),
                   ("alice", "smoke", "1970-01-01T00:05:00Z")]
    assert runner.queue()[0]["id"] == "sihrs_2024-25_full_oracle"
    if os.name != "nt":
        # a linked experiment folder is no job
        link = tops["alice"] / "experiments" / "sihrs_2024-25_full_oracle"
        os.symlink(tops["carol"] / "experiments" / "sihrs_2024-25_full_oracle",
                   link)
        assert [q["folder"] for q in runner.queue()].count("alice") == 2


def test_position_and_wait_from_the_runner_state(alice, students):
    f = experiment(alice, queued=True)
    job = {"kind": "run", "folder": "bob", "id": "x_2024-25_full",
           "size": "full", "pid": 1, "eta_s": 600, "keep_bytes": 0}
    mine = {"folder": "alice", "id": EID, "size": "smoke", "seconds": 76.0,
            "measured": False, "peak_bytes": 35_332_432,
            "keep_bytes": 878_000, "why": ""}
    ahead = {"folder": "carol", "id": "y_2024-25_pilot", "size": "pilot",
             "seconds": 300.0, "peak_bytes": 1, "keep_bytes": 1, "why": ""}
    state(students, job=job, waiting=[ahead, mine])
    assert runner.position("alice", EID) == {
        "position": 2, "wait_s": 900.0, "seconds": 76.0, "measured": False,
        "peak_bytes": 35_332_432, "keep_bytes": 878_000, "why": "",
        "runner": True}
    # why it waits: its own, else the runner's
    state(students, job=None, waiting=[ahead, {**mine, "why": "waiting for "
                                               "disk: it needs about 1 B"}],
          waiting_why="the runner's install is on dev, not main")
    q = runner.position("alice", EID)
    assert (q["wait_s"], q["why"]) == (300.0, "waiting for disk: it needs "
                                       "about 1 B")
    state(students, waiting=[mine],
          waiting_why="the runner's install is on dev, not main")
    assert runner.position("alice", EID)["why"] == (
        "waiting: the runner's install is on dev, not main")
    # not seen by the supervisor yet: at the back, its estimate made here
    state(students, job=job, waiting=[ahead])
    q = runner.position("alice", EID)
    assert (q["position"], q["wait_s"], q["peak_bytes"]) == (
        2, 900.0, 35_332_432)
    assert q["seconds"] == runner.estimate(SMOKE, weeks=[W0, W1])["seconds"]
    # a heartbeat older than ALIVE_S, a dead pid, an unknown format
    now = runner._now()
    state(students, heartbeat_utc=runner._utc(now - runner.ALIVE_S - 5))
    assert runner.read_state()["alive"] is False
    assert runner.position("alice", EID)["runner"] is False
    state(students, pid=DEAD)
    assert runner.position("alice", EID)["runner"] is False
    state(students)
    assert runner.position("alice", EID)["runner"] is True
    for v in (2, True, "1", None):
        state(students, format_version=v)
        assert runner.read_state() == {}
        assert runner.position("alice", EID)["runner"] is False
    # not queued, or the runner's job (starting): no position
    state(students, job={**job, "folder": "alice", "id": EID})
    assert runner.position("alice", EID) is None
    (f / X.QUEUED).unlink()
    state(students)
    assert runner.position("alice", EID) is None


def test_the_job_of_a_runner_that_is_not_running_holds_nothing(alice,
                                                               students):
    # runner.json names the job, but its runner died without its stop:
    # the job waits for a runner again, so it is queued, not replaying
    job = {"kind": "run", "folder": "alice", "id": EID, "size": "smoke",
           "pid": 4242, "keep_bytes": 0}
    state(students, job=job, pid=DEAD)
    got = runner.enqueue(SMOKE)
    assert (got["state"], got["runner"]) == ("queued", False)
    f = alice / "experiments" / EID
    assert (f / X.QUEUED).is_file()
    q = runner.position("alice", EID)
    assert (q["position"], q["runner"]) == (1, False)
    assert runner.enqueue(SMOKE)["state"] == "already"
    # a running runner's job: starting (no place), and replaying
    state(students, job=job)
    assert runner.position("alice", EID) is None
    assert runner.enqueue(SMOKE)["state"] == "replaying"
    # a child still fitting after its runner died: its record says so
    state(students, job=job, pid=DEAD)
    runner.stop("alice", EID)
    _running(f)
    assert runner.enqueue(SMOKE)["state"] == "replaying"
    assert not (f / X.QUEUED).exists()


def test_stop_dequeues_or_stops(alice, students):
    f = experiment(alice, queued=True)
    before = sorted(p.name for p in f.iterdir())
    assert runner.stop("alice", EID) == "dequeued"
    assert sorted(p.name for p in f.iterdir()) == [
        n for n in before if n != X.QUEUED]
    assert runner.stop("alice", EID) == ""
    _running(f)
    assert runner.stop("alice", EID) == "stopping"
    assert retro.stop_path(f).is_file()
    assert runner.stop("alice", "beta-v1_2024-25_smoke") == ""
    assert runner.stop("bob", EID) == ""


def test_status_reads_queued(alice, students):
    state(students)
    runner.enqueue(SMOKE)
    f = alice / "experiments" / EID
    assert X.status(f)["queued"] is True
    _running(f)
    assert X.status(f)["queued"] is False          # under way: not waiting
    retro.write_meta(f, {"status": "stopped"})
    assert X.status(f)["queued"] is True
    runner.stop("alice", EID)
    assert X.status(f)["queued"] is False


def test_nothing_changes_without_a_runner(tmp_path, monkeypatch):
    # the suite's STUDENTS (conftest) does not exist
    calendar(monkeypatch)
    top = tmp_path / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", top)
    nothing = {"rows": [], "runner": [], "down": False, "why": ""}
    for _ in range(2):
        assert runner.folder_of(top) is None
        assert runner.folder_of(runner.STUDENTS / "alice" / "sandbox") is None
        assert runner.busy_words() == ""
        assert runner.read_state() == {}
        assert runner.storage() == nothing
        assert runner.queue() == []
        assert runner.position("alice", EID) is None
        assert runner.refusal("alice", EID) == ""
        assert runner.stop("alice", EID) == ""
        with pytest.raises(Refusal) as e:
            runner.enqueue(SMOKE)
        assert str(e.value) == "this computer has no runner"
        assert not (top / "experiments" / EID).exists()
        # STUDENTS there but no runner's folder in it: the same
        s = tmp_path / "Students"
        student(s, "alice")
        monkeypatch.setattr(runner, "STUDENTS", s)
        top = s / "alice" / "sandbox"
        monkeypatch.setattr(sb, "SANDBOX", top)
    assert not (s / runner.STATE_NAME).exists()
    assert not (top / "experiments" / EID).exists()


def test_busy_words_and_the_main_console(alice, students, tmp_path,
                                         monkeypatch):
    state(students)
    assert runner.busy_words() == ""
    job = {"kind": "run", "folder": "alice", "id": EID, "size": "smoke",
           "pid": 1}
    state(students, job=job)
    assert runner.busy_words() == (
        f"the runner on this computer is replaying alice's {EID}")
    state(students, job={**job, "kind": "tidy"})
    assert runner.busy_words() == ""
    state(students, job=job, pid=DEAD)
    assert runner.busy_words() == ""
    # the main console's own Sandbox is no student's: it does not queue
    main = tmp_path / "main" / "sandbox"
    monkeypatch.setattr(sb, "SANDBOX", main)
    assert runner.folder_of(main) is None
    with pytest.raises(Refusal) as e:
        runner.enqueue(SMOKE)
    assert str(e.value) == (
        f"this computer's runner works the student folders in {students} "
        "only, and this Sandbox is not one of them")


def test_storage_rows_by_folder(alice, students):
    bob = student(students, "bob")
    queued = experiment(alice, queued=True)
    os.utime(queued / X.QUEUED, (0, 0))
    done = experiment(alice, {**SMOKE, "size": "pilot"}, weeks=[W0])
    stored(done, W0)
    os.utime(queued / X.SETTINGS, (2_000_000, 2_000_000))
    os.utime(done / X.SETTINGS, (1_000_000, 1_000_000))
    theirs = experiment(bob, {**SMOKE, "oracle": False})
    _running(theirs)
    state(students, job={"kind": "run", "folder": "bob", "id": theirs.name,
                         "size": "smoke", "pid": os.getpid(),
                         "started_utc": runner._utc(runner._now()),
                         "keep_bytes": 0})
    got = runner.storage(size=lambda p: 1000)
    # by folder, newest first in each
    assert [r["ident"] for r in got["rows"]] == [
        f"alice/{EID}", "alice/sihrs_2024-25_pilot_oracle",
        f"bob/{theirs.name}"]
    rows = {r["ident"]: r for r in got["rows"]}
    q = rows[f"alice/{EID}"]
    assert q["queued"]["position"] == 1 and not q["busy"]
    assert q["parts"] == ["queued again", "runs about 1:16",
                          "needs about 33.7 MB"]
    assert (q["size"], q["size_h"], q["folder"]) == (1000, "1000 B", "alice")
    b = rows[f"bob/{theirs.name}"]
    assert b["busy"] and b["queued"] is None
    assert b["why"] == (f"bob/{theirs.name} is replaying on the runner; stop "
                        "it from its page in bob's console first.")
    assert not rows["alice/sihrs_2024-25_pilot_oracle"]["busy"]
    assert got["down"] is False
    assert got["runner"][0].startswith(
        f"The runner: replaying bob/{theirs.name} since ")
    assert got["runner"][1:] == ["500.0 GB free · FluBNF keeps 20.0 GB free"]
    # a run record that is not a regular file is never followed nor read:
    # the row is left out (check refuses the folder)
    if os.name != "nt":
        meta = done / retro.META_NAME
        retro.write_meta(students.parent / "elsewhere", {"status": "running"})
        meta.unlink(missing_ok=True)
        os.symlink(students.parent / "elsewhere" / retro.META_NAME, meta)
        got = runner.storage(size=lambda p: 1000)
        assert "alice/sihrs_2024-25_pilot_oracle" not in [
            r["ident"] for r in got["rows"]]
        meta.unlink()
        os.mkfifo(meta)
        got = runner.storage(size=lambda p: 1000)
        assert "alice/sihrs_2024-25_pilot_oracle" not in [
            r["ident"] for r in got["rows"]]
        meta.unlink()
    # the runner not running
    state(students, pid=DEAD)
    got = runner.storage(size=lambda p: 0)
    assert got["down"] is True
    assert got["why"].endswith("Queued experiments wait until it is "
                               "started: in a Terminal of this account, run "
                               f"{Path(sb.REPO) / '.venv' / 'bin' / 'flubnf'}"
                               " runner.")
