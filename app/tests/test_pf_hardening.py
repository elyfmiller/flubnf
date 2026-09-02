"""Field hardening of the PF paths (2026-09-01 final pass).

Four failure modes, each measured or reproduced before it was fixed:

  * A path containing a space cannot be expressed in pf.conf at all:
    PyBNF's grammar splits bng_command and output_dir on whitespace
    (reproduced: "C:\\Users\\John Smith\\..." raises ParseException
    "Expected end of text, found Smith"), and on Windows the default
    workroot lives under C:\\Users\\<name>\\AppData, so any student with a
    space in the username failed every fit. prepare() now substitutes the
    8.3 short form on Windows and refuses legibly everywhere else.
  * collect() read every cell in cells.json regardless of its recorded
    status, and a failed cell's leftover empty or single-row trajectory
    file killed the WHOLE assembly with an IndexError: one dead cell cost
    the other 158 their samples.
  * prepare() was all-or-nothing: resolve_state refuses an empty window or
    an all-NaN tail (the documented MA/MN/WV reporting-pause pattern, 55
    of 87 vintages), and one such state aborted the whole 53-jurisdiction
    run. It is now contained per location and recorded like a fit failure.
  * The runners are plain Popen children supervised from daemon threads: a
    console takeover or window close killed the supervisor without its
    finally block, orphaning running fits, and a heartbeat-stale resume
    could then fit the same cells concurrently. Runners now lead their own
    process groups and are recorded for the relaunch sweep
    (flubnf/cli.py::_sweep_runner_groups). run_week also keeps a failed
    week's evidence instead of pruning the failed cells' inputs.
"""
import json
import os
import subprocess
import sys
import time
import types
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import reclaim, retro                      # noqa: E402
from app.core.engines import pf                          # noqa: E402


# ------------------------------------------------------- conf-safe paths

def test_conf_safe_path_passes_space_free_paths_unchanged():
    assert pf.conf_safe_path("/a/b/c") == "/a/b/c"
    assert pf.conf_safe_path(Path("/a/b/c")) == "/a/b/c"
    assert pf.conf_safe_path("C:\\x\\y", _platform="win32") == "C:\\x\\y"


def test_a_spaced_path_is_refused_legibly_where_no_short_form_exists(
        monkeypatch):
    """The grammar limit is platform-independent, so POSIX refuses too, and
    the refusal names the path and the remedy instead of leaving the user a
    ParseException from inside the engine venv."""
    with pytest.raises(RuntimeError) as e:
        pf.conf_safe_path("/Users/John Smith/flubnf", _platform="linux")
    msg = str(e.value)
    assert "John Smith" in msg and "space" in msg
    assert "Move the FluBNF folder" in msg
    # Windows with 8.3 short-name creation disabled is the same dead end
    monkeypatch.setattr(pf, "_short_path_win", lambda s: None)
    with pytest.raises(RuntimeError, match="8.3"):
        pf.conf_safe_path("C:\\Users\\John Smith\\f", _platform="win32")


def test_windows_substitutes_the_8dot3_short_form(monkeypatch):
    monkeypatch.setattr(pf, "_short_path_win",
                        lambda s: "C:\\Users\\JOHNSM~1\\flubnf")
    assert pf.conf_safe_path("C:\\Users\\John Smith\\flubnf",
                             _platform="win32") == "C:\\Users\\JOHNSM~1\\flubnf"
    # a short form that still carries a space is no rescue
    monkeypatch.setattr(pf, "_short_path_win", lambda s: "C:\\st ill\\x")
    with pytest.raises(RuntimeError):
        pf.conf_safe_path("C:\\Users\\John Smith\\f", _platform="win32")


def test_short_path_win_sizes_its_buffer_through_the_wide_api():
    """GetShortPathNameW is called twice: once with no buffer to learn the
    size (terminator included), once to fill a buffer of exactly that
    size. Zero returns from either call mean no short form."""
    short = "C:\\USERS\\JOHNSM~1"
    sizes = []

    def api(s, buf, n):
        sizes.append(n)
        if buf is None:
            return len(short) + 1
        buf.value = short
        return len(short)

    assert pf._short_path_win("C:\\Users\\John Smith", _api=api) == short
    assert sizes == [0, len(short) + 1]
    assert pf._short_path_win("x", _api=lambda *a: 0) is None
    assert pf._short_path_win(
        "x", _api=lambda s, buf, n: 5 if buf is None else 0) is None


@pytest.mark.skipif(os.name == "nt", reason="Windows substitutes the 8.3 "
                    "short form instead of refusing; covered by the unit "
                    "tests above")
def test_prepare_refuses_a_spaced_workroot_before_any_state_is_touched(
        tmp_path):
    spec = type("S", (), {"forecast_date": "2098-11-07"})()
    with pytest.raises(RuntimeError) as e:
        pf.prepare(spec, tmp_path / "has space" / "wr")
    assert "has space" in str(e.value)


# ------------------------------------------- per-location prepare containment

class _State:
    """The bits of StateSetup that prepare() actually touches."""

    def __init__(self):
        self.times = [0, 1, 2]
        self.observed = [4.0, 5.0, 6.0]
        self.n_obs = 3
        self.last_week_offset = 2


def _spec(locations, replicates=2):
    return type("S", (), {
        "forecast_date": "2098-11-07", "season_start": "2098-08-01",
        "weeks_to_drop": 0, "drop_same_day": False,
        "locations": list(locations), "replicates": replicates,
        "particles": 100, "jitter": 0.3,
        "observable_mode": "integrated", "extra": None})()


def _prep_env(monkeypatch, tmp_path, resolve, netgen_fails_for=()):
    """Hub-free prepare(): fakes for resolve_state, the materializer, the
    exp writer, the vintage path, and the netgen subprocess (which writes
    m.net unless the cell directory is on the fail list)."""
    import app.core.data as data
    import flubnf.sihrs_fit as sf

    def fake_materialize(s, template, out_path, suffix, extra_tokens=None,
                         **kw):
        p = Path(out_path)
        p.write_text("begin parameters\nend parameters\n")
        return p

    def fake_netgen(cmd, **kw):
        cwd = Path(kw.get("cwd", "."))
        if cwd.name not in netgen_fails_for:
            (cwd / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(sf, "resolve_state", resolve)
    monkeypatch.setattr(sf, "materialize_model", fake_materialize)
    monkeypatch.setattr(sf, "write_exp",
                        lambda s, p: Path(p).write_text("# t v\n"))
    vfile = tmp_path / "vintage.csv"
    vfile.write_text("date,location,location_name,value\n")
    monkeypatch.setattr(data, "vintage_path", lambda d: str(vfile))
    monkeypatch.setattr(pf.subprocess, "run", fake_netgen)


def test_one_unresolvable_state_costs_itself_not_the_run(monkeypatch,
                                                         tmp_path):
    """The 53-jurisdiction grid must survive the documented MA/MN/WV
    pattern: resolve_state raising for one state leaves the other states'
    cells intact and records the failure under the location's tag."""
    def resolve(loc, **kw):
        if loc == "Bad State":
            raise ValueError(f"no observations for {loc} in window")
        return _State()

    _prep_env(monkeypatch, tmp_path, resolve)
    w = tmp_path / "wr"
    cells = pf.prepare(_spec(["Ohio", "Bad State"]), w)

    assert [c["key"] for c in cells] == ["Ohio_r0", "Ohio_r1"]
    assert json.loads((w / "cells.json").read_text()) == cells
    failures = pf.read_prepare_failures(w)
    assert set(failures) == {"Bad_State"}
    assert failures["Bad_State"].startswith("FAIL: prepare: ")
    assert "no observations for Bad State" in failures["Bad_State"]


def test_a_location_that_fails_mid_replicate_leaves_no_partial_cells(
        monkeypatch, tmp_path):
    """Containment is per LOCATION: a netgen failure on the second
    replicate must not leave the first replicate's cell in the grid beside
    a recorded failure for the same location."""
    _prep_env(monkeypatch, tmp_path, lambda loc, **kw: _State(),
              netgen_fails_for=("Flaky_r1",))
    w = tmp_path / "wr"
    cells = pf.prepare(_spec(["Ohio", "Flaky"]), w)

    assert [c["key"] for c in cells] == ["Ohio_r0", "Ohio_r1"]
    failures = pf.read_prepare_failures(w)
    assert set(failures) == {"Flaky"}
    assert "netgen failed" in failures["Flaky"]


def test_every_location_failing_prepare_still_raises_loudly(monkeypatch,
                                                            tmp_path):
    def resolve(loc, **kw):
        raise ValueError(f"{loc}: all weeks are NaN (reporting pause?)")

    _prep_env(monkeypatch, tmp_path, resolve)
    w = tmp_path / "wr"
    with pytest.raises(RuntimeError, match=r"all 2 location\(s\)"):
        pf.prepare(_spec(["A State", "B State"]), w)
    assert set(pf.read_prepare_failures(w)) == {"A_State", "B_State"}


def test_a_single_location_run_reraises_its_one_error_verbatim(monkeypatch,
                                                               tmp_path):
    """One location has nothing to continue with, and callers (and the
    existing gapped-tail test) pin the original exception type and text."""
    def resolve(loc, **kw):
        raise ValueError(f"no observations for {loc} in window")

    _prep_env(monkeypatch, tmp_path, resolve)
    with pytest.raises(ValueError, match="no observations for Ohio"):
        pf.prepare(_spec(["Ohio"]), tmp_path / "wr")


# --------------------------------------------------- the execute-level fold

def _fake_pybnf(root: Path, body: str) -> Path:
    """A pybnf whose ParticleFilter.run does whatever the test needs (same
    scaffolding as test_pf_shards, so the generated runner really runs)."""
    pkg = root / "fake_pybnf" / "pybnf"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "parse.py").write_text("def load_config(p):\n    return p\n")
    (pkg / "pf.py").write_text(
        "import os, time\n"
        "class ParticleFilter:\n"
        "    def __init__(self, cfg):\n"
        "        self.cfg = cfg\n"
        "    def run(self, _):\n" + body)
    return root / "fake_pybnf"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """The engine venv, faked: this interpreter and a stub pybnf."""
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    monkeypatch.setattr(pf, "_sleep", lambda _s: time.sleep(0.02))

    def install(body):
        monkeypatch.setattr(pf, "PYBNF_PF", _fake_pybnf(tmp_path, body))
    return install


def _grid(w: Path, n: int) -> list:
    cells = []
    for i in range(n):
        d = w / f"cell_{i}"
        d.mkdir(parents=True)
        (d / "pf.conf").write_text("")
        cells.append({"key": f"cell_{i}", "dir": str(d), "n_obs": 1,
                      "particles": 100})
    (w / "cells.json").write_text(json.dumps(cells))
    return cells


def test_prepare_failures_flow_into_the_merged_status(engine, tmp_path):
    """The forecast path computes pf_failures from execute()'s merged
    status, so a prepare-stage failure must ride in it beside the fit
    statuses; the keys cannot collide because cell keys carry _r<rep>."""
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    (w / pf.PREPARE_FAILURES_NAME).write_text(json.dumps(
        {"Bad_State": "FAIL: prepare: no observations"}))
    out = pf.execute(w, width=2)
    assert out["Bad_State"] == "FAIL: prepare: no observations"
    assert out["cell_0"] == out["cell_1"] == "ok"
    assert json.loads((w / "pf_status.json").read_text()) == out


def test_a_grid_of_only_prepare_failures_still_surfaces_them(engine,
                                                             tmp_path):
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    (w / "cells.json").write_text("[]")
    (w / pf.PREPARE_FAILURES_NAME).write_text(json.dumps(
        {"Bad_State": "FAIL: prepare: no observations"}))
    out = pf.execute(w)
    assert out == {"Bad_State": "FAIL: prepare: no observations"}
    assert json.loads((w / "pf_status.json").read_text()) == out


# ------------------------------------------------- collect() torn-file guard

def _traj_cell(w: Path, key: str, loc: str, content) -> dict:
    """One cell directory shaped the way collect() reads it. `content` is
    the trajectory file's text, or None for no file at all."""
    d = w / key
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    if content is not None:
        (runs / "sim_traj_noise.txt").write_text(content)
    return {"key": key, "dir": str(d), "location": loc, "n_obs": 3,
            "particles": 100, "last_observed": 10.0}


#: two particles over 7 columns; origin is column 2 (value 2), so the
#: anchor scale is 10/2 = 5 and horizon h pools to (2+h)*5
_GOOD_TRAJ = "0 1 2 3 4 5 6\n0 1 2 3 4 5 6\n"


def test_collect_skips_cells_whose_recorded_status_is_a_failure(tmp_path):
    """The reproduced field crash: a failed cell's leftover EMPTY
    trajectory file (genfromtxt gives shape (0,)) raised an IndexError at
    assembly and cost every healthy cell its samples. The recorded status
    is consulted first, so the failed cell is simply not read."""
    w = tmp_path / "wr"
    w.mkdir()
    cells = [_traj_cell(w, "Ohio_r0", "Ohio", _GOOD_TRAJ),
             _traj_cell(w, "Ohio_r1", "Ohio", "")]
    (w / "cells.json").write_text(json.dumps(cells))
    status = {"Ohio_r0": "ok", "Ohio_r1": "FAIL: synthetic engine crash"}
    (w / "pf_status.json").write_text(json.dumps(status))

    out = pf.collect(w)
    assert sorted(out) == ["Ohio"]
    assert out["Ohio"]["0"] == [10.0, 10.0]      # only the ok replicate
    assert out["Ohio"]["4"] == [30.0, 30.0]
    # the failed cell keeps its own FAIL reason: skipped, never re-recorded
    assert json.loads((w / "pf_status.json").read_text()) == status


def test_a_torn_trajectory_downgrades_to_a_recorded_failure(tmp_path):
    """A torn file under an ok (or unrecorded) status: empty and
    single-row files are 1-D to genfromtxt, and a ragged file raises. All
    three become recorded per-cell failures instead of assembly crashes."""
    w = tmp_path / "wr"
    w.mkdir()
    cells = [_traj_cell(w, "Ohio_r0", "Ohio", _GOOD_TRAJ),
             _traj_cell(w, "Ohio_r1", "Ohio", ""),
             _traj_cell(w, "Ohio_r2", "Ohio", "0 1 2 3 4 5 6\n"),
             _traj_cell(w, "Ohio_r3", "Ohio", "0 1 2 3 4 5 6\n0 1\n")]
    (w / "cells.json").write_text(json.dumps(cells))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # genfromtxt's empty-file warning
        out = pf.collect(w)
    assert out["Ohio"]["0"] == [10.0, 10.0]      # the healthy cell survives
    recorded = json.loads((w / "pf_status.json").read_text())
    assert set(recorded) == {"Ohio_r1", "Ohio_r2", "Ohio_r3"}
    for v in recorded.values():
        assert v.startswith("FAIL:")
        assert "excluded from assembly" in v


def test_collect_reads_the_retrospective_markers_too(tmp_path):
    """The replay path records statuses as cells_done/<key>.json markers,
    not pf_status.json; a failed cell's torn file must be skipped there as
    well, and the skip records nothing new (the marker already says why)."""
    w = tmp_path / "wr"
    w.mkdir()
    cells = [_traj_cell(w, "Ohio_r0", "Ohio", _GOOD_TRAJ),
             _traj_cell(w, "Ohio_r1", "Ohio", "")]
    (w / "cells.json").write_text(json.dumps(cells))
    retro.mark_cell_done(w, "Ohio_r0", "ok")
    retro.mark_cell_done(w, "Ohio_r1", "FAIL: synthetic engine crash")

    out = pf.collect(w)
    assert out["Ohio"]["0"] == [10.0, 10.0]
    assert not (w / "pf_status.json").exists()


def test_a_statusless_workroot_reads_every_cell_as_before(tmp_path):
    """An older workroot has neither pf_status.json nor markers; every
    cell with a healthy trajectory is still read."""
    w = tmp_path / "wr"
    w.mkdir()
    cells = [_traj_cell(w, "Ohio_r0", "Ohio", _GOOD_TRAJ),
             _traj_cell(w, "Ohio_r1", "Ohio", _GOOD_TRAJ)]
    (w / "cells.json").write_text(json.dumps(cells))
    out = pf.collect(w)
    assert out["Ohio"]["0"] == [10.0] * 4        # both replicates pooled


# --------------------------------------------- runner process-group plumbing

def test_runner_popen_kwargs_puts_a_runner_in_its_own_group():
    posix = pf.runner_popen_kwargs({}, _os_name="posix")
    assert posix == {"start_new_session": True}
    nt = pf.runner_popen_kwargs({"creationflags": 0x4000}, _os_name="nt")
    assert nt["creationflags"] == 0x4000 | pf._CREATE_NEW_PROCESS_GROUP
    # the base kwargs ride along untouched
    both = pf.runner_popen_kwargs({"close_fds": True}, _os_name="posix")
    assert both == {"close_fds": True, "start_new_session": True}


def test_record_and_unrecord_runner_pids_round_trip(tmp_path):
    reg = tmp_path / "reg.json"
    a = types.SimpleNamespace(pid=111111, args=["nice", "-n", "5", "py",
                                                "/w/pf_runner_0.py"])
    b = types.SimpleNamespace(pid=222222, args=["py", "/w/runner_1.py"])
    pf.record_runner_pids([a, b], path=reg)
    rec = json.loads(reg.read_text())
    assert rec["111111"]["runner"].endswith("pf_runner_0.py")
    assert rec["222222"]["runner"].endswith("runner_1.py")
    if os.name == "posix":
        assert rec["111111"]["pgid"] == 111111
    pf.unrecord_runner_pids([a], path=reg)
    assert set(json.loads(reg.read_text())) == {"222222"}
    # never fatal, even against a registry that is not there
    pf.unrecord_runner_pids([b], path=tmp_path / "absent.json")


def _spy_popen(monkeypatch, needle: str):
    """Every runner subprocess started, with the kwargs it was started
    with (same idea as test_pf_shards, filtered to the runner scripts)."""
    made = []
    real = subprocess.Popen

    def spy(*a, **k):
        p = real(*a, **k)
        cmd = [str(c) for c in a[0]]
        if any(needle in c and c.endswith(".py") for c in cmd):
            made.append({"cmd": cmd, "kwargs": k, "proc": p})
        return p

    monkeypatch.setattr(pf.subprocess, "Popen", spy)
    return made


@pytest.mark.skipif(os.name != "posix",
                    reason="start_new_session is the POSIX spelling; the "
                           "Windows creationflags branch is unit-tested "
                           "above")
def test_execute_runners_lead_their_own_sessions_and_are_registered(
        engine, tmp_path, monkeypatch):
    """During a run the takeover registry names every runner (pid, pgid,
    script); after the supervisor's finally the entries are gone, so a
    later sweep can never chase recycled pids of a run that ended."""
    engine("        time.sleep(30)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    made = _spy_popen(monkeypatch, "pf_runner")
    seen = {}

    def press(_s):
        if not seen:
            seen["reg"] = json.loads(pf.RUNNER_PIDS_FILE.read_text())
            (w / "STOP").touch()
        time.sleep(0.02)

    monkeypatch.setattr(pf, "_sleep", press)
    with pytest.raises(pf.RunStopped):
        pf.execute(w, width=2)

    assert len(made) == 2
    for m in made:
        assert m["kwargs"].get("start_new_session") is True
    live = seen["reg"]
    assert set(live) == {str(m["proc"].pid) for m in made}
    for pid_s, meta in live.items():
        assert meta["pgid"] == int(pid_s)
        assert meta["runner"].endswith(".py")
        assert "pf_runner_" in meta["runner"]
    # the finally unrecorded them
    assert json.loads(pf.RUNNER_PIDS_FILE.read_text()) == {}


@pytest.mark.skipif(os.name != "posix",
                    reason="start_new_session is the POSIX spelling")
def test_retro_runners_lead_their_own_sessions_and_are_registered(
        tmp_path, monkeypatch):
    """The replay path launches through its own _launch_runners; it must
    start its runners exactly the way the forecast path does, and record
    them in the same registry."""
    monkeypatch.setattr(pf, "PY310", Path(sys.executable))
    wd = tmp_path / "wk"
    wd.mkdir()
    halt = wd / "HALT"
    halt.touch()                    # the launched runner exits immediately
    made = _spy_popen(monkeypatch, "runner_")
    shards = [[{"key": "c0", "dir": str(tmp_path)}]]
    procs = retro._launch_runners(wd, shards, halt)
    try:
        assert len(made) == 1
        assert made[0]["kwargs"].get("start_new_session") is True
        rec = json.loads(pf.RUNNER_PIDS_FILE.read_text())
        assert set(rec) == {str(procs[0].pid)}
        assert rec[str(procs[0].pid)]["runner"].endswith("runner_0.py")
        for p in procs:
            p.wait(20)
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.wait()


# ------------------------------------- a failed week keeps its evidence

SEASON = "2098-99"
W1 = "2098-11-07"


def _stub_week(monkeypatch, statuses, prepare_failures=None):
    """run_week with stubbed engines: prepare writes the given grid (and,
    when asked, a prepare-failures file), each runner marks its cells with
    the given statuses, collect and the analogue return fixed shapes."""
    def fake_prepare(spec, wd):
        wd = Path(wd)
        cells = [{"key": k, "dir": str(wd / k)} for k in statuses]
        (wd / "cells.json").write_text(json.dumps(cells))
        if prepare_failures:
            (wd / pf.PREPARE_FAILURES_NAME).write_text(
                json.dumps(prepare_failures))
        return cells

    class Runner:
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], statuses[c["key"]])
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {"Ohio": {"0": [1.0]}})
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"1": {0.5: 2.0}}})
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s)
                                                  for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)
    pruned = []
    monkeypatch.setattr(reclaim, "prune_week",
                        lambda wd: pruned.append(Path(wd)) or 0)
    return pruned


def test_a_week_with_failed_cells_keeps_its_evidence(tmp_path, monkeypatch):
    """The console rule: a run with failures keeps everything. Pruning a
    partially failed week destroyed the failed cells' pf.conf, model, and
    exp inputs, the exact material a rerun or an autopsy needs."""
    pruned = _stub_week(monkeypatch, {"cell_0": "ok",
                                      "cell_1": "FAIL: synthetic crash"})
    root = tmp_path / SEASON
    out = retro.run_week(root, SEASON, W1, ["Ohio"], width=1)

    assert out["pf_failures"] == {"cell_1": "FAIL: synthetic crash"}
    assert pruned == []                          # nothing was reclaimed
    wd = root / "weeks" / W1
    assert (wd / "cells.json").is_file()         # the evidence survives
    assert (wd / retro.CELL_DONE_DIRNAME).is_dir()
    assert "cell_1" in (root / "failures.log").read_text()


def test_a_clean_week_is_still_pruned(tmp_path, monkeypatch):
    """The converse pins the guard's polarity: hygiene is unchanged for
    the weeks that earned it."""
    pruned = _stub_week(monkeypatch, {"cell_0": "ok", "cell_1": "ok"})
    root = tmp_path / SEASON
    out = retro.run_week(root, SEASON, W1, ["Ohio"], width=1)
    assert "pf_failures" not in out
    assert pruned == [root / "weeks" / W1]


def test_prepare_stage_failures_reach_the_weeks_failure_record(tmp_path,
                                                               monkeypatch):
    """A state resolve_state refused left no cell and no marker, but the
    stored week must still say so, and the keep-evidence rule must see
    it."""
    pruned = _stub_week(monkeypatch, {"cell_0": "ok"},
                        prepare_failures={"Bad_State":
                                          "FAIL: prepare: no observations"})
    root = tmp_path / SEASON
    out = retro.run_week(root, SEASON, W1, ["Ohio"], width=1)
    assert out["pf_failures"] == {"Bad_State":
                                  "FAIL: prepare: no observations"}
    assert pruned == []


def test_a_week_of_only_torn_trajectories_is_refused_not_stored_empty():
    """Reviewer note from the 2026-09-01 final pass: markers can say ok
    while every trajectory is unreadable, in which case collect() downgrades
    them all and the week would have stored with an empty pf and no failure
    record, the exact hazard the all-fits-failed refusal exists for. Source
    pin (the guard sits mid-run_week behind a full week's machinery): the
    refusal must trigger on empty pf_samples alone, not only when failures
    were recorded, and both branches must refuse storage."""
    import inspect
    from app.core import retro
    src = inspect.getsource(retro.run_week)
    guard = src.split("pf_samples = pf_engine.collect(wd)")[1]
    head = guard.split("raise RuntimeError")[0]
    assert "if not pf_samples:" in head, (
        "the storage refusal is again conditioned on recorded failures, "
        "so a week of collect-downgraded cells stores empty and silent")
    assert guard.count("the week is not stored") >= 2, (
        "one of the two refusal branches lost its refusal")
