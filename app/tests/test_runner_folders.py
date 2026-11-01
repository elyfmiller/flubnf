"""The runner's student folders (app/core/runner.py): which children of
STUDENTS are students' folders, which Sandbox is one (folder_of, a
linked STUDENTS resolved), and check, which names a job's folder by
(name, id) only: a link at every level, a pipe, a hard link, a giant
file and a strange entry in a week are refused with exact words naming
the path; Finder's files are allowed; a name or an id with a path in it
never reaches the disk; nor does a library model in another student's
folder.

The helpers here make the student folders the other runner tests use
(test_runner_queue, _estimates, _serve and _job)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import retro_store as RS                   # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.problem_codes import Refusal               # noqa: E402

#: the smoke of the shipped Oracle SIHRS, and its two weeks of 2024-25
SMOKE = {"model": "sihrs", "season": "2024-25"}
W0, W1 = "2024-12-28", "2025-01-11"
#: the 30 vintages of 2024-25 (2025-01-18 has none), and those with no
#: FluSight round (test_experiments' calendar)
VINTAGES = ["2024-11-16", "2024-11-23", "2024-11-30", "2024-12-07",
            "2024-12-14", "2024-12-21", "2024-12-28", "2025-01-04",
            "2025-01-11", "2025-01-25", "2025-02-01", "2025-02-08",
            "2025-02-15", "2025-02-22", "2025-03-01", "2025-03-08",
            "2025-03-15", "2025-03-22", "2025-03-29", "2025-04-05",
            "2025-04-12", "2025-04-19", "2025-04-26", "2025-05-03",
            "2025-05-10", "2025-05-17", "2025-05-24", "2025-05-31",
            "2025-06-07", "2025-06-14"]
NO_ROUND = {"2025-05-31", "2025-06-07", "2025-06-14"}

LINKS = pytest.mark.skipif(os.name == "nt",
                           reason="links need rights on Windows")
LINK = "is a link, and the runner follows no link in a student folder"


@pytest.fixture
def students(tmp_path, monkeypatch) -> Path:
    """STUDENTS under tmp_path with the runner's folder in it: a computer
    with a runner. Its path, resolved."""
    s = Path(os.path.realpath(tmp_path)) / "Students"
    (s / runner.STATE_NAME).mkdir(parents=True)
    monkeypatch.setattr(runner, "STUDENTS", s)
    return s


def calendar(monkeypatch) -> None:
    """2024-25's vintages and rounds, the suite reading no hub."""
    monkeypatch.setattr(retro, "available_seasons", lambda: ["2024-25"])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(VINTAGES) if s == "2024-25" else [])
    monkeypatch.setattr(X, "_has_round", lambda w: w not in NO_ROUND)


def student(students: Path, name: str) -> Path:
    """A student's clone with its Sandbox folder (models, runs and
    experiments in it); the Sandbox folder."""
    top = students / name / "sandbox"
    for d in ("models", "runs", "experiments"):
        (top / d).mkdir(parents=True, exist_ok=True)
    return top


def experiment(top: Path, settings=SMOKE, *, weeks=None, meta=None,
               queued: bool = False) -> Path:
    """An experiment's folder in a Sandbox: its experiment.json; with
    weeks or meta, a run record freezing the weeks; with queued, its
    QUEUED flag."""
    f = top / "experiments" / X.experiment_id(settings)
    f.mkdir(parents=True, exist_ok=True)
    L.write_json(f / X.SETTINGS, json.loads(X.settings_text(settings)))
    if weeks is not None or meta is not None:
        retro.write_meta(f, {"status": "done",
                             "settings": {"experiment": "e" * 64,
                                          "weeks": list(weeks or ())},
                             **(meta or {})})
    if queued:
        (f / X.QUEUED).write_bytes(b"")
    return f


def stored(f: Path, asof: str) -> Path:
    """A stored week: its samples file and sidecar; its folder."""
    wd = f / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    (wd / RS.SAMPLES_JSON).write_text("{}", encoding="utf-8")
    (wd / RS.QUANTILES_NAME).write_text("{}", encoding="utf-8")
    return wd


def refused(fn, *a) -> str:
    """fn(*a)'s MACHINE refusal, in its words."""
    with pytest.raises(Refusal) as e:
        fn(*a)
    assert e.value.code == "MACHINE", e.value.findings
    return str(e.value)


def tree(root: Path) -> dict:
    """Every path under a tree, links not followed: (size, mtime_ns), -1
    for a folder's size."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for n in dirs + files:
            p = Path(dirpath) / n
            st = os.lstat(p)
            out[p.relative_to(root).as_posix()] = (
                -1 if p.is_dir() and not p.is_symlink() else st.st_size,
                st.st_mtime_ns)
    return out


def _library(top: Path, name: str = "beta", version: int = 1) -> Path:
    """A library version's three files, written by hand (check reads none
    of them; the replay re-hashes them): its folder."""
    d = top / "library" / name / str(version)
    d.mkdir(parents=True)
    for n in ("model.json", "model.bngl", "priors.conf"):
        (d / n).write_text("# " + n + "\n", encoding="utf-8")
    return d


def _case_blind(folder: Path) -> bool:
    probe = folder / "Case-Probe"
    probe.mkdir()
    try:
        return (folder / "case-probe").exists()
    finally:
        probe.rmdir()


# ---------------------------------------------------------- the folders


def test_folders_are_real_named_clones_only(students, tmp_path,
                                           monkeypatch):
    for n in ("alice", "bob", "Carol"):
        student(students, n)
    (students / ".hidden" / "sandbox").mkdir(parents=True)
    (students / "notes.txt").write_text("x\n")
    (students / "no-sandbox").mkdir()
    (students / "bad name" / "sandbox").mkdir(parents=True)
    (students / "dave").mkdir()
    (students / "dave" / "sandbox").write_text("a file\n")
    assert runner.folders() == ["alice", "bob", "Carol"]
    assert runner.folder("alice") == students / "alice" / "sandbox"
    assert runner.folder("dave") is None and runner.folder(".runner") is None
    if os.name != "nt":
        os.symlink(students / "alice", students / "alias")
        (students / "erin").mkdir()
        (tmp_path / "far" / "sandbox").mkdir(parents=True)
        os.symlink(tmp_path / "far" / "sandbox", students / "erin" / "sandbox")
        assert runner.folders() == ["alice", "bob", "Carol"]
    if not _case_blind(students):
        # two folders the same ignoring case: both are left out
        student(students, "ALICE")
        assert runner.folders() == ["bob", "Carol"]
    # no STUDENTS at all
    monkeypatch.setattr(runner, "STUDENTS", tmp_path / "none")
    assert runner.folders() == [] and runner.folder("alice") is None


def test_folder_of_names_only_a_sandbox_in_a_student_folder(students,
                                                            tmp_path,
                                                            monkeypatch):
    top = student(students, "alice")
    assert runner.folder_of(top) == "alice"
    assert runner.folder_of(str(top)) == "alice"
    # a laptop's Sandbox, a student's clone, a folder that is no student's
    assert runner.folder_of(tmp_path / "laptop" / "sandbox") is None
    assert runner.folder_of(students / "alice") is None
    assert runner.folder_of(students / "zed" / "sandbox") is None
    # no runner's folder: no runner, even for a student's Sandbox
    (students / runner.STATE_NAME).rmdir()
    assert runner.folder_of(top) is None
    (students / runner.STATE_NAME).mkdir()
    if os.name != "nt":
        # STUDENTS a link Ely made: resolved at each use
        link = tmp_path / "linked-students"
        os.symlink(students, link)
        monkeypatch.setattr(runner, "STUDENTS", link)
        assert runner.folder_of(link / "alice" / "sandbox") == "alice"
        assert runner.folder_of(top) == "alice"
        assert runner.folders() == ["alice"]
        assert runner.folder("alice") == top


@LINKS
def test_check_refuses_a_link_at_every_level(students, tmp_path):
    top = student(students, "alice")
    f = experiment(top, weeks=[W0, W1])
    eid = f.name
    wd = stored(f, W0)
    beta = experiment(top, {"model": "beta@1", "season": "2024-25"})
    lib = _library(top)
    assert runner.check("alice", eid) == f
    assert runner.check("alice", beta.name) == beta
    assert runner.check("alice") == top
    hold = tmp_path / "hold"

    def swapped(p: Path, words: str, eid: str = eid) -> None:
        """p moved aside and a link to it put in its place: refused in
        these words; then put back."""
        p.rename(hold)
        os.symlink(hold, p)
        try:
            assert refused(runner.check, "alice", eid) == words
        finally:
            p.unlink()
            hold.rename(p)

    nobody = "there is no student folder 'alice' on this computer"
    swapped(students / "alice", nobody)
    swapped(top, nobody)
    swapped(top / "experiments", f"experiments {LINK}")
    swapped(f, f"experiments/{eid} {LINK}")
    swapped(f / "weeks", f"experiments/{eid}/weeks {LINK}")
    swapped(wd, f"experiments/{eid}/weeks/{W0} {LINK}")
    swapped(wd / RS.QUANTILES_NAME,
            f"experiments/{eid}/weeks/{W0}/{RS.QUANTILES_NAME} {LINK}")
    swapped(f / X.SETTINGS, f"experiments/{eid}/{X.SETTINGS} {LINK}")
    # the library version an experiment names, on its way and in its files
    swapped(top / "library", f"library {LINK}", beta.name)
    swapped(lib.parent, f"library/beta {LINK}", beta.name)
    swapped(lib, f"library/beta/1 {LINK}", beta.name)
    swapped(lib / "model.bngl", f"library/beta/1/model.bngl {LINK}",
            beta.name)
    # the student's folder alone checks the way to experiments only
    swapped(f, f"experiments/{eid} {LINK}")
    assert runner.check("alice") == top
    assert runner.check("alice", eid) == f


def test_check_refuses_pipes_hard_links_and_giant_files(students, tmp_path):
    top = student(students, "alice")
    f = experiment(top, weeks=[W0, W1])
    eid = f.name
    wd = stored(f, W0)
    assert runner.check("alice", eid) == f
    if hasattr(os, "mkfifo"):
        for p, rel in ((f / retro.META_NAME, retro.META_NAME),
                       (wd / "cells.json", f"weeks/{W0}/cells.json")):
            kept = p.with_name(p.name + ".kept")
            if p.exists():
                p.rename(kept)
            os.mkfifo(p)
            assert refused(runner.check, "alice", eid) == (
                f"experiments/{eid}/{rel} is a pipe, and the runner reads "
                "no pipe in a student folder")
            p.unlink()
            if kept.exists():
                kept.rename(p)
    log = f / "failures.log"
    log.write_text(f"{W1}: boom\n", encoding="utf-8")
    os.link(log, tmp_path / "another-folders.log")
    assert refused(runner.check, "alice", eid) == (
        f"experiments/{eid}/failures.log is a hard link (one file with 2 "
        "names), and the runner writes into no file another folder may "
        "share")
    (tmp_path / "another-folders.log").unlink()
    with open(f / X.SUMMARY, "wb") as fh:          # sparse: no disk used
        fh.truncate(65 * runner.MiB)
    assert refused(runner.check, "alice", eid) == (
        f"experiments/{eid}/summary.json is 65.0 MB, and the runner reads "
        "no file over 64.0 MB in a student folder")
    (f / X.SUMMARY).unlink()
    # a week's samples may be larger
    with open(wd / RS.SAMPLES_GZ, "wb") as fh:
        fh.truncate(65 * runner.MiB)
    assert runner.check("alice", eid) == f
    settings = (f / X.SETTINGS).read_text(encoding="utf-8")
    (f / X.SETTINGS).write_text(settings + " " * 5000, encoding="utf-8")
    assert X.read(f / X.SETTINGS) == X.read(SMOKE)
    assert refused(runner.check, "alice", eid) == (
        f"experiments/{eid}/experiment.json is 4.9 KB, and an "
        "experiment.json is at most 4.0 KB")
    (f / X.SETTINGS).write_text(settings, encoding="utf-8")
    # weeks frozen in the run record that are not dates
    retro.write_meta(f, {"settings": {"experiment": "e" * 64,
                                      "weeks": [W0, "../.."]}})
    assert refused(runner.check, "alice", eid) == (
        f"experiments/{eid}/run_meta.json names a week that is not a "
        "date: '../..'")
    assert runner.check("alice") == top


def test_check_allows_finder_files_and_refuses_strange_week_entries(
        students, monkeypatch):
    from app.core import oracle
    assert runner._WEEK_DIRS == (retro.CELL_DONE_DIRNAME,
                                 oracle.BANK_DIRNAME)
    top = student(students, "alice")
    f = experiment(top, weeks=[W0, W1])
    eid = f.name
    wd = stored(f, W0)
    for p in (top / ".DS_Store", f / ".DS_Store", f / "weeks" / ".DS_Store",
              wd / ".DS_Store", wd / "runner_0.py", wd / "notes.txt"):
        p.write_text("x\n", encoding="utf-8")
    for d in ("Vermont_r0", "New_York_r12", "cells_done", "oracle_bank"):
        (wd / d / "deeper").mkdir(parents=True)
    (f / "notes").mkdir()                    # folders beside weeks/ are free
    assert runner.check("alice", eid) == f
    for p, words in (
            (f / "weeks" / "foo", f"experiments/{eid}/weeks/foo is not a "
             "week: a folder in weeks is named by its date, such as "
             "2024-12-28"),
            (wd / "json.py", f"experiments/{eid}/weeks/{W0}/json.py is not "
             "a runner script FluBNF writes (runner_<n>.py), and a week "
             "holds no other Python file"),
            (wd / "x", f"experiments/{eid}/weeks/{W0}/x is not a folder "
             "FluBNF writes in a week (cells_done, oracle_bank or a fit's "
             "<location>_r<n>)"),
            (wd / "__pycache__", f"experiments/{eid}/weeks/{W0}/__pycache__ "
             "is not a folder FluBNF writes in a week (cells_done, "
             "oracle_bank or a fit's <location>_r<n>)")):
        if p.suffix == ".py":
            p.write_text("import os\n", encoding="utf-8")
        else:
            p.mkdir()
        assert refused(runner.check, "alice", eid) == words
        p.unlink() if p.is_file() else p.rmdir()
    assert runner.check("alice", eid) == f
    # a name gone between the listing and its look (the child's heartbeat
    # replaces run_meta.json.tmp while it checks the folder) is no refusal
    real = os.walk

    def walk(top, **kw):
        for dirpath, dirs, files in real(top, **kw):
            yield dirpath, dirs, files + ["run_meta.json.tmp"]
    monkeypatch.setattr(os, "walk", walk)
    assert runner.check("alice", eid) == f


def test_ids_and_names_with_path_parts_never_reach_the_disk(students,
                                                            tmp_path):
    top = student(students, "alice")
    bob = student(students, "bob")
    f = experiment(bob, queued=True)
    experiment(top)
    # a folder whose settings name another experiment
    other = top / "experiments" / "sihrs_2024-25_full"
    other.mkdir()
    L.write_json(other / X.SETTINGS, json.loads(X.settings_text(SMOKE)))
    before = tree(tmp_path)
    for name in ("../bob", "a/b", ".x", "x" * 300, "", None, "alice/..",
                 ".runner"):
        assert refused(runner.check, name, f.name) == (
            f"there is no student folder {runner._shown(name)} on this "
            "computer")
        assert runner.folder(name) is None
        assert runner.stop(name, f.name) == ""
        assert runner.position(name, f.name) is None
        assert runner.refusal(name, f.name) == ""
    for eid in ("../bob", "a/b", ".x", "x" * 300, "", 7,
                "../../bob/sandbox/experiments/" + f.name):
        assert refused(runner.check, "alice", eid) == (
            f"{runner._shown(eid)} is not an experiment's id")
        assert runner.stop("alice", eid) == ""
        assert runner.position("alice", eid) is None
    # an id that is not there, and one whose settings name another
    assert refused(runner.check, "alice", "beta-v1_2024-25_smoke") == (
        "experiments/beta-v1_2024-25_smoke is not in alice's folder")
    assert refused(runner.check, "alice", other.name) == (
        f"experiments/{other.name}/experiment.json does not name this "
        "experiment: its settings give another id, or cannot be read")
    assert runner.stop("alice", other.name) == ""
    # nothing was written, moved or made anywhere
    assert tree(tmp_path) == before


@LINKS
def test_a_job_never_resolves_a_model_in_another_folder(students):
    top = student(students, "alice")
    bob = student(students, "bob")
    theirs = _library(bob)
    beta = experiment(top, {"model": "beta@1", "season": "2024-25"})
    (top / "library").mkdir()
    os.symlink(theirs.parent, top / "library" / "beta")
    assert refused(runner.check, "alice", beta.name) == f"library/beta {LINK}"
    (top / "library" / "beta").unlink()
    mine = _library(top)
    os.unlink(mine / "priors.conf")
    os.symlink(theirs / "priors.conf", mine / "priors.conf")
    assert refused(runner.check, "alice", beta.name) == (
        f"library/beta/1/priors.conf {LINK}")
    os.unlink(mine / "priors.conf")
    os.link(theirs / "priors.conf", mine / "priors.conf")
    assert refused(runner.check, "alice", beta.name) == (
        "library/beta/1/priors.conf is a hard link (one file with 2 "
        "names), and the runner writes into no file another folder may "
        "share")
    os.unlink(mine / "priors.conf")
    (mine / "priors.conf").write_text("# mine\n", encoding="utf-8")
    assert runner.check("alice", beta.name) == beta
    # the job's Sandbox is alice's: the library it reads is hers
    with runner._as_folder("alice") as sandbox:
        assert sandbox == top and L.root() == top / "library"
    assert sb.SANDBOX != top
