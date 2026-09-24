"""The console forecast path shards its grid and sizes its own timeout.

A full grid (53 jurisdictions x 3 replicates = 159 cells, 34.3 s/cell at
n_obs 48) needs ~91 min in one process against the old fixed 60-min
timeout. Pinned: the same partition as the retrospective path, and a budget
from the measured cost model. Subprocess tests run the GENERATED runner
against a fake pybnf.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import horizons as hz                      # noqa: E402
from app.core import proc as proc_mod                    # noqa: E402
from app.core import reclaim, retro                      # noqa: E402
from app.core.engines import pf                          # noqa: E402

#: the grid that failed: every jurisdiction plus US, 3 replicates, at the
#: season's most expensive n_obs
FULL_GRID_CELLS = 53 * 3
FULL_GRID_N_OBS = 48


# ------------------------------------------------------------- the partition

def _cells(n: int, n_obs: int = 10, particles: int = 10_000) -> list:
    return [{"key": f"cell_{i}", "n_obs": n_obs, "particles": particles}
            for i in range(n)]


def test_partition_covers_every_cell_exactly_once(monkeypatch):
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    cells = _cells(159)
    shards = pf.shard_cells(cells, 4)
    assert len(shards) == 4
    flat = [c for s in shards for c in s]
    assert sorted(c["key"] for c in flat) == sorted(c["key"] for c in cells)
    assert len(flat) == len(cells)
    # balanced to within one cell (the budget assumes it)
    assert max(map(len, shards)) - min(map(len, shards)) <= 1


def test_forecast_and_retrospective_divide_a_grid_identically(monkeypatch):
    """Retro's _run_round partitions through the engine's shard_cells, so the
    two paths cannot drift into two mechanisms."""
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    assert "pf_engine.shard_cells(pending, width)" in Path(
        retro.__file__).read_text()
    pending = _cells(11)
    assert pf.shard_cells(pending, 3) == [pending[i::3] for i in range(3)]


def test_the_two_paths_share_one_default_width():
    """Forecast and replay share one default width (same wall clock)."""
    import inspect
    for fn in (retro.run_week, retro.run_season):
        assert (inspect.signature(fn).parameters["width"].default
                == pf.DEFAULT_SHARD_WIDTH)


def test_width_falls_back_through_caller_environment_default(monkeypatch):
    monkeypatch.delenv(pf.WIDTH_ENV, raising=False)
    assert pf.shard_width() == pf.DEFAULT_SHARD_WIDTH
    assert pf.shard_width(7) == 7
    monkeypatch.setenv(pf.WIDTH_ENV, "6")
    assert pf.shard_width() == 6
    assert pf.shard_width(2) == 2            # the caller still wins
    monkeypatch.setenv(pf.WIDTH_ENV, "not a number")
    assert pf.shard_width() == pf.DEFAULT_SHARD_WIDTH
    monkeypatch.setenv(pf.WIDTH_ENV, "0")
    assert pf.shard_width() == 1             # never below one


def test_width_one_reproduces_the_old_single_process_behaviour():
    cells = _cells(10)
    assert pf.shard_cells(cells, 1) == [cells]


# ------------------------------------------------------------ the cost model

def test_cost_model_reproduces_the_measured_seconds_per_cell():
    """1.194 + 0.6365 * (n_obs + 4), the fit on 680 shard-weeks."""
    assert pf.cell_seconds({"n_obs": FULL_GRID_N_OBS}) == pytest.approx(34.3,
                                                                       abs=0.1)
    assert pf.cell_seconds({"n_obs": 23}) == pytest.approx(18.4, abs=0.1)


def test_a_heavier_particle_count_scales_the_prediction():
    base = pf.cell_seconds({"n_obs": 20, "particles": 10_000})
    assert pf.cell_seconds({"n_obs": 20, "particles": 20_000}) == pytest.approx(
        2 * base)
    # a cell written before the model existed is read at the reference count
    assert pf.cell_seconds({"n_obs": 20}) == pytest.approx(base)


def test_the_grid_that_failed_would_now_fit_its_budget():
    cells = _cells(FULL_GRID_CELLS, n_obs=FULL_GRID_N_OBS)
    sequential = sum(pf.cell_seconds(c) for c in cells)
    assert sequential == pytest.approx(5452, rel=0.02)    # 91 min, the failure
    assert sequential > 3600.0                            # against the old fixed hour

    shards = pf.shard_cells(cells, pf.DEFAULT_SHARD_WIDTH)
    predicted = pf.expected_seconds(shards)
    budget = pf.budget_seconds(shards)
    assert predicted == pytest.approx(
        sequential / pf.DEFAULT_SHARD_WIDTH, rel=0.05)
    assert budget > predicted                    # the honest run has room
    # floor or multiple, whichever is larger (with a core-scaled width the
    # predicted wall can fall under the floor)
    assert budget == pytest.approx(
        max(pf.TIMEOUT_FLOOR_S, pf.TIMEOUT_SAFETY * predicted))


def test_even_unsharded_the_budget_follows_the_work_not_a_constant():
    """At every width, a run is never killed for taking the predicted time."""
    cells = _cells(FULL_GRID_CELLS, n_obs=FULL_GRID_N_OBS)
    for width in (1, 2, 4, 8, 16):
        shards = pf.shard_cells(cells, width)
        assert pf.budget_seconds(shards) > pf.expected_seconds(shards)


def test_a_mid_january_forecast_is_covered_too():
    """n_obs 23 (mid-January) is 49 min sequential: covered too."""
    cells = _cells(FULL_GRID_CELLS, n_obs=23)
    shards = pf.shard_cells(cells, pf.DEFAULT_SHARD_WIDTH)
    assert pf.budget_seconds(shards) > pf.expected_seconds(shards)


def test_tiny_grids_get_the_floor_not_a_two_minute_budget():
    shards = pf.shard_cells(_cells(3, n_obs=10), pf.DEFAULT_SHARD_WIDTH)
    assert pf.expected_seconds(shards) < pf.TIMEOUT_FLOOR_S
    assert pf.budget_seconds(shards) == pf.TIMEOUT_FLOOR_S


#: the constant the sized budget replaces, and the bar it may never fall under
OLD_FIXED_TIMEOUT_S = 3600.0


def test_the_budget_never_undercuts_the_hour_it_replaces():
    """For EVERY grid the budget is at least the old fixed hour, so the change
    only ever extends a run's allowance. The multiple alone does not give
    this: it assumes the machine delivers the width's concurrency."""
    for n_obs in (0, 1, 10, 23, 48):
        for n in (1, 3, 12, 53, FULL_GRID_CELLS, 400):
            for width in (1, 2, 4, 8, 16):
                shards = pf.shard_cells(_cells(n, n_obs=n_obs), width)
                assert pf.budget_seconds(shards) >= OLD_FIXED_TIMEOUT_S


def test_the_mid_january_grid_keeps_the_hour_the_multiple_would_take_away():
    """159 cells at n_obs 23 is ~2922 s sequential, yet 3x the slowest of four
    shards is ~2206 s: the floor keeps the budget above the old hour for a
    machine without 4-way concurrency. Pinned at width 4; at every width the
    budget must cover the work."""
    cells = _cells(FULL_GRID_CELLS, n_obs=23)
    sequential = sum(pf.cell_seconds(c) for c in cells)
    assert sequential == pytest.approx(2922, rel=0.02)     # 49 min
    assert sequential < OLD_FIXED_TIMEOUT_S                # the old code coped

    # the historical near-miss, at its own width
    four = pf.shard_cells(cells, 4)
    assert pf.TIMEOUT_SAFETY * pf.expected_seconds(four) < sequential
    assert pf.budget_seconds(four) >= sequential           # the floor saves it

    # and the invariant, at whatever width this machine resolves to
    shards = pf.shard_cells(cells, pf.DEFAULT_SHARD_WIDTH)
    assert pf.budget_seconds(shards) >= sequential / pf.DEFAULT_SHARD_WIDTH


def test_the_peak_grid_still_gets_the_enlargement_it_needed():
    """At the peak grid the multiple, not the floor, sets the budget, and it
    exceeds the work."""
    cells = _cells(FULL_GRID_CELLS, n_obs=FULL_GRID_N_OBS)
    shards = pf.shard_cells(cells, pf.DEFAULT_SHARD_WIDTH)
    budget = pf.budget_seconds(shards)
    sequential = sum(pf.cell_seconds(c) for c in cells)
    # The invariant is about the WORK: the budget exceeds the predicted wall
    # time with the safety margin at this machine's width (it may fall below
    # 3600 s once the width scales with the cores).
    assert budget == pytest.approx(max(
        pf.TIMEOUT_FLOOR_S,
        pf.TIMEOUT_SAFETY * pf.expected_seconds(shards)))
    assert budget > sequential / pf.DEFAULT_SHARD_WIDTH
    # and at the old fixed width it still clears the hour it once failed
    old = pf.shard_cells(cells, 4)
    assert pf.budget_seconds(old) > OLD_FIXED_TIMEOUT_S


# --------------------------------------------------- the real runner scripts

def _grid(w: Path, n: int, n_obs: int = 1) -> list:
    """A prepared workroot: n cell directories and a cells.json."""
    cells = []
    for i in range(n):
        d = w / f"cell_{i}"
        d.mkdir(parents=True)
        (d / "pf.conf").write_text("")
        cells.append({"key": f"cell_{i}", "dir": str(d), "n_obs": n_obs,
                      "particles": 10_000})
    (w / "cells.json").write_text(json.dumps(cells))
    return cells


def _fake_pybnf(root: Path, body: str) -> Path:
    """A pybnf whose ParticleFilter.run does whatever the test needs."""
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


def _spy_popen(monkeypatch):
    """Every RUNNER subprocess execute() starts (cmd, kwargs, proc).

    Filtered to runners: a cancel also runs `ps` through the same patched
    Popen, and counting those would race with the stop."""
    made = []
    real = subprocess.Popen

    def spy(*a, **k):
        p = real(*a, **k)
        cmd = [str(c) for c in a[0]]
        if any("pf_runner" in c and c.endswith(".py") for c in cmd):
            made.append({"cmd": cmd, "kwargs": k, "proc": p})
        return p

    monkeypatch.setattr(pf.subprocess, "Popen", spy)
    return made


def test_shards_run_in_parallel_and_their_statuses_merge(engine, tmp_path,
                                                         monkeypatch):
    engine("        if os.getcwd().endswith('cell_1'):\n"
           "            raise RuntimeError('synthetic failure')\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    made = _spy_popen(monkeypatch)
    out = pf.execute(w, width=2)

    assert len(made) == 2                              # one runner per shard
    assert set(out) == {f"cell_{i}" for i in range(4)}
    assert out["cell_1"].startswith("FAIL")
    assert [out[k] for k in ("cell_0", "cell_2", "cell_3")] == ["ok"] * 3
    # the merged status is the run's record, on disk under the old name
    assert json.loads((w / "pf_status.json").read_text()) == out
    # and the scaffolding is per shard
    for i in range(2):
        assert (w / f"pf_runner_{i}.py").is_file()
        assert (w / f"pf_cells_{i}.json").is_file()
        assert (w / f"pf_status_{i}.json").is_file()


def test_a_shard_that_dies_leaves_its_unfinished_cells_visible(engine, tmp_path):
    """Cells a dead shard never reported come back as failures naming it."""
    engine("        if os.getcwd().endswith('cell_2'):\n"
           "            os._exit(9)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    out = pf.execute(w, width=2)          # shard 0 takes cells 0 and 2

    assert len(out) == 4                  # nothing dropped from the count
    assert out["cell_0"] == "ok"          # what the dead shard did finish
    assert out["cell_2"].startswith("FAIL: shard 0")
    assert out["cell_1"] == out["cell_3"] == "ok"    # the other shard is fine
    # the caller's failure filter therefore sees it
    assert {k for k, v in out.items() if v != "ok"} == {"cell_2"}


def test_no_status_at_all_still_raises_the_specific_error_with_stderr(
        engine, tmp_path, monkeypatch):
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    monkeypatch.setattr(pf, "_RUNNER",
                        "import sys\n"
                        "sys.stderr.write('ModuleNotFoundError: pybnf\\n')\n"
                        "raise SystemExit(3)\n")
    with pytest.raises(RuntimeError) as e:
        pf.execute(w, width=2)
    assert "produced no status" in str(e.value)
    assert "ModuleNotFoundError" in str(e.value)      # the stderr is quoted


def test_stop_terminates_every_runner_and_raises(engine, tmp_path, monkeypatch):
    """Cancel with several runners: all stop promptly and RunStopped raises."""
    engine("        time.sleep(30)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 6)
    made = _spy_popen(monkeypatch)
    pressed = {"done": False}

    def press(_s):
        if not pressed["done"]:
            pressed["done"] = True
            (w / "STOP").touch()
        time.sleep(0.02)

    monkeypatch.setattr(pf, "_sleep", press)
    t0 = time.time()
    with pytest.raises(pf.RunStopped):
        pf.execute(w, width=3)
    assert time.time() - t0 < 25                  # not waiting out the fits
    assert len(made) == 3
    for m in made:
        assert m["proc"].poll() is not None       # every runner is dead


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.mark.skipif(os.name != "posix",
                    reason="process groups are POSIX; Windows keeps the "
                           "single-process terminate it always had")
def test_a_cancel_takes_the_engine_pool_with_the_runner(engine, tmp_path,
                                                        monkeypatch):
    """A cancel signals each runner's process GROUP, so PyBNF's worker pool
    goes with it instead of holding cores."""
    engine("        import subprocess, sys\n"
           "        g = subprocess.Popen([sys.executable, '-c',\n"
           "                              'import time; time.sleep(45)'])\n"
           "        open(os.path.join(os.getcwd(), 'GPID'), 'w').write(\n"
           "            str(g.pid))\n"
           "        time.sleep(45)\n")
    w = tmp_path / "wr"
    w.mkdir()
    cells = _grid(w, 2)
    made = _spy_popen(monkeypatch)

    def press(_s):
        # stop only once both shards have an engine process to strand
        if all((Path(c["dir"]) / "GPID").is_file() for c in cells):
            (w / "STOP").touch()
        time.sleep(0.1)

    monkeypatch.setattr(pf, "_sleep", press)
    gpids = []
    try:
        with pytest.raises(pf.RunStopped):
            pf.execute(w, width=2, timeout=60)   # bounded: never hang the suite
        gpids = [int((Path(c["dir"]) / "GPID").read_text()) for c in cells]
        assert len(gpids) == 2                   # both shards spawned one
        for m in made:
            assert m["proc"].poll() is not None   # every runner is dead
        deadline = time.time() + 10
        while time.time() < deadline and any(_alive(p) for p in gpids):
            time.sleep(0.1)
        assert [_alive(p) for p in gpids] == [False, False]
    finally:
        for p in gpids:            # a failure must not leak into the next test
            try:
                os.kill(p, 9)
            except OSError:
                pass


def test_a_standing_stop_flag_means_no_cell_is_dispatched(engine, tmp_path):
    """Runners check the flag between cells too, so a stop halts dispatch."""
    engine("        open(os.path.join(os.getcwd(), 'RAN'), 'w').close()\n")
    w = tmp_path / "wr"
    w.mkdir()
    cells = _grid(w, 4)
    (w / "STOP").touch()
    with pytest.raises(pf.RunStopped):
        pf.execute(w, width=2)
    assert not any((Path(c["dir"]) / "RAN").exists() for c in cells)


def test_every_runner_starts_at_reduced_priority(engine, tmp_path, monkeypatch):
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    made = _spy_popen(monkeypatch)
    pf.execute(w, width=2)
    prefix = proc_mod.low_priority_prefix()
    # compare with the kwargs execute() really passes (priority folded with
    # the process group: on Windows both are bits of one creationflags)
    kwargs = pf.runner_popen_kwargs(proc_mod.low_priority_popen_kwargs())
    assert len(made) == 2
    for m in made:
        assert m["cmd"][:len(prefix)] == prefix        # [] on non-POSIX: fine
        assert m["cmd"][len(prefix)] == sys.executable
        for k, v in kwargs.items():
            assert m["kwargs"].get(k) == v


def test_a_caller_supplied_timeout_says_how_far_the_run_got(engine, tmp_path):
    engine("        time.sleep(30)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    with pytest.raises(RuntimeError) as e:
        pf.execute(w, width=2, timeout=0.5)
    msg = str(e.value)
    assert "0 of 4 cells finished" in msg
    assert "set by the caller" in msg
    assert "timed out" not in msg              # never the bare old message


def test_the_sized_budget_names_the_cost_model_it_came_from(engine, tmp_path,
                                                            monkeypatch):
    engine("        time.sleep(30)\n")
    monkeypatch.setattr(pf, "TIMEOUT_FLOOR_S", 0.5)
    monkeypatch.setattr(pf, "TIMEOUT_SAFETY", 0.001)
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)
    with pytest.raises(RuntimeError) as e:
        pf.execute(w, width=2)
    msg = str(e.value)
    assert "0 of 4 cells finished" in msg
    assert "cost model" in msg and "n_obs" in msg
    assert "2 shard(s)" in msg
    assert pf.WIDTH_ENV in msg                 # and what to do about it


def test_a_prepared_grid_with_no_cells_is_not_a_failure(engine, tmp_path):
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    (w / "cells.json").write_text("[]")
    assert pf.execute(w) == {}
    assert json.loads((w / "pf_status.json").read_text()) == {}


def test_the_message_names_which_term_actually_set_the_budget(engine, tmp_path,
                                                              monkeypatch):
    """The timeout message names the term that bound the budget (floor or
    multiple), so its arithmetic is never visibly false."""
    engine("        time.sleep(30)\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 4)

    monkeypatch.setattr(pf, "TIMEOUT_FLOOR_S", 0.5)
    monkeypatch.setattr(pf, "TIMEOUT_SAFETY", 0.001)       # the floor binds
    with pytest.raises(RuntimeError) as e:
        pf.execute(w, width=2)
    floored = str(e.value)
    assert "the floor" in floored
    assert "cost model" in floored          # it still reports the prediction
    assert "= 0.001 x" not in floored       # but does not claim to BE it

    monkeypatch.setattr(pf, "TIMEOUT_FLOOR_S", 0.0)
    monkeypatch.setattr(pf, "TIMEOUT_SAFETY", 0.05)        # the multiple binds
    with pytest.raises(RuntimeError) as e:
        pf.execute(w, width=2)
    multiplied = str(e.value)
    assert "the floor" not in multiplied
    assert "= 0.05 x" in multiplied


# ------------------------------------------------------ sharded == sequential

#: A fake fit whose output depends on the cell directory alone, so any
#: difference between two arrangements of a grid is caused by the arrangement.
_DETERMINISTIC_FIT = (
    "        import os, pathlib\n"
    "        d = pathlib.Path(os.getcwd())\n"
    "        runs = d / 'out' / 'Results' / 'PF' / 'Runs'\n"
    "        runs.mkdir(parents=True, exist_ok=True)\n"
    "        base = sum(ord(ch) for ch in d.name)\n"
    "        rows = [' '.join('%.6f' % (base + 10 * i + j) for j in range(8))\n"
    "                for i in range(4)]\n"
    "        (runs / 'sim_traj_noise.txt').write_text('\\n'.join(rows) + '\\n')\n")


def _collectable_grid(w: Path, n_locs: int = 3, reps: int = 3,
                      n_obs: int = 3) -> list:
    """A prepared workroot shaped the way collect() reads one."""
    cells = []
    for li in range(n_locs):
        for rep in range(1, reps + 1):
            key = f"loc{li}_r{rep}"
            d = w / key
            d.mkdir(parents=True)
            (d / "pf.conf").write_text("")
            cells.append({"key": key, "dir": str(d), "location": f"Location {li}",
                          "replicate": rep, "n_obs": n_obs, "particles": 10_000,
                          "last_observed": 100.0 + li})
    (w / "cells.json").write_text(json.dumps(cells))
    return cells


def test_sharding_changes_no_number(engine, tmp_path):
    """Width 1 and width 4 give identical statuses and collect() samples.

    Structural: a cell's seed is a pure function of the cell, each cell fits
    in its own directory, and collect() iterates cells.json, which execute()
    never rewrites."""
    engine(_DETERMINISTIC_FIT)
    out = {}
    for width in (1, 4):
        w = tmp_path / f"wr{width}"
        w.mkdir()
        _collectable_grid(w)
        out[width] = (pf.execute(w, width=width), pf.collect(w))

    # the two arrangements really were different
    assert len(pf.shard_cells(_cells(9), 1)) == 1
    assert len(pf.shard_cells(_cells(9), 4)) == 4
    assert set(out[1][0].values()) == {"ok"}              # nothing failed
    assert out[1][0] == out[4][0]                         # same statuses
    assert out[1][1] == out[4][1]                         # same pooled samples
    # and the comparison is not vacuous: real numbers, pooled in order
    assert sorted(out[1][1]) == ["Location 0", "Location 1", "Location 2"]
    for pooled in out[1][1].values():
        assert sorted(pooled) == sorted((hz.ORIGIN, *hz.HORIZONS))
        assert all(len(v) == 3 * 4 for v in pooled.values())
        assert len(set(pooled[hz.ORIGIN])) > 1


def test_collect_reads_the_unpartitioned_cells_json(engine, tmp_path):
    """execute() leaves cells.json byte-identical, so collect() cannot see the
    partition."""
    engine(_DETERMINISTIC_FIT)
    w = tmp_path / "wr"
    w.mkdir()
    _collectable_grid(w)
    before = (w / "cells.json").read_bytes()
    pf.execute(w, width=4)
    assert (w / "cells.json").read_bytes() == before
    assert [c["key"] for c in json.loads(before)] == [
        c["key"] for c in json.loads((w / "cells.json").read_text())]


# ------------------------------------------------- what the rest of the app sees

def test_api_progress_sums_the_per_shard_progress_files(tmp_path, monkeypatch):
    """api_progress finds per-shard .prog files and the pre-sharding name."""
    from app.core import ttlcache
    from app.ui import server as srv
    from app.ui import state as ui_state
    w = tmp_path / "wr"
    w.mkdir()
    now = time.time()
    for i, done in enumerate((3, 2)):
        (w / f"pf_status_{i}.json.prog").write_text(
            json.dumps({"done": done, "total": 4, "t0": now - 60}))
    monkeypatch.setitem(ui_state._status, "running", "all:x")
    monkeypatch.setitem(ui_state._status, "workroot", str(w))
    monkeypatch.setitem(ui_state._status, "expected_total", 8)
    monkeypatch.setitem(ui_state._status, "started_utc", now - 60)
    ttlcache.clear_all()
    out = srv.api_progress()
    assert (out["done"], out["total"]) == (5, 8)


def test_reclaim_prunes_shard_scaffolding_and_keeps_the_merged_record(tmp_path):
    w = tmp_path / "20980118T090000-aaaaaa"
    w.mkdir()
    (w / "results.json").write_text('{"models": {}}')      # a completed run
    (w / "cells.json").write_text("[]")
    (w / "pf_status.json").write_text("{}")
    for i in range(3):
        (w / f"pf_runner_{i}.py").write_text("# runner")
        (w / f"pf_runner_{i}.err").write_text("")
        (w / f"pf_cells_{i}.json").write_text("[]")
        (w / f"pf_status_{i}.json").write_text("{}")
        (w / f"pf_status_{i}.json.prog").write_text("{}")
    gone = {p.name for p in reclaim.workroot_intermediates(w)}
    assert "pf_runner_0.py" in gone and "pf_runner_2.err" in gone
    assert "pf_cells_1.json" in gone and "pf_status_1.json" in gone
    assert "pf_status_0.json.prog" in gone
    assert "pf_status.json" not in gone and "cells.json" not in gone
    assert "results.json" not in gone


def test_default_width_is_sized_to_the_machine():
    """Width scales with the cores (a couple reserved for the console),
    capped where the measured speedup goes flat."""
    assert pf.default_shard_width(12) == 10
    assert pf.default_shard_width(8) == 6
    assert pf.default_shard_width(4) == 2
    assert pf.default_shard_width(2) == 2       # never below two
    assert pf.default_shard_width(1) == 2
    assert pf.default_shard_width(64) == pf.SHARD_WIDTH_CAP
    assert pf.DEFAULT_SHARD_WIDTH == pf.default_shard_width()


def test_more_runners_than_cells_is_harmless():
    """shard_cells drops empty shards: a wide default on a tiny grid runs one
    cell per runner."""
    cells = [{"key": f"c{i}"} for i in range(3)]
    shards = pf.shard_cells(cells, 10)
    assert len(shards) == 3
    assert sorted(c["key"] for sh in shards for c in sh) == ["c0", "c1", "c2"]
