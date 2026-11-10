"""Per-cell and per-step timings, kept beside a run's record and never in it.

Each shard runner (pf._RUNNER, lwf.RUNNER) times every cell it finishes
and keeps the seconds in <status>.secs.prog beside its status; execute()
gathers them, once every runner is reaped, into pf_timing.json with what
the cost model reads (n_obs, weeks_dropped, particles), each cell's shard,
and the grid's engine, width and wall clock. The console run notes when
each step began (shared._phase and _phase_mark) and writes run_timing.json.

What must not move: pf_status.json and each shard's status (their bytes),
the .prog files api_progress reads (their keys), results.json and the
ledger's outcome. reclaim prunes the per-shard seconds with the other
runner files and keeps both timing records. A timing write that fails
never fails a run.

Subprocess tests run the GENERATED runners against a stub pybnf, as
test_pf_runner_reports.py does.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import reclaim                             # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.tests import test_engine_lwf as _lwf_tests      # noqa: E402
from app.tests import test_oracle_step as _oracle_tests  # noqa: E402
from app.tests import test_pf_runner_reports as _runner_tests  # noqa: E402
from app.ui import pipeline as ui_pipeline               # noqa: E402
from app.ui import shared as ui_shared                   # noqa: E402

# the fixtures and helpers those files hold, used here as they are
public = _lwf_tests.public
console, hubfiles = _oracle_tests.console, _oracle_tests.hubfiles
engine = _runner_tests.engine
_cell, _record = _lwf_tests._cell, _lwf_tests._record
_run, _grid = _oracle_tests._run, _runner_tests._grid


def _timing(w: Path) -> dict:
    return json.loads((w / pf.TIMING_NAME).read_text(encoding="utf-8"))


# ------------------------------------------------------------ the fits


def test_every_finished_cell_has_its_seconds(engine, tmp_path):
    """Three cells on two shards: each has its seconds (the stub sleeps
    0.05 s), its shard, and what the cost model reads; the grid's engine,
    width, wall clock and prediction are there too."""
    engine("        time.sleep(0.05)\n")
    w = tmp_path / "wr"
    w.mkdir()
    cells = _grid(w, 3)
    cells[2]["weeks_dropped"] = 1
    (w / "cells.json").write_text(json.dumps(cells))
    assert pf.execute(w, width=2) == {f"cell_{i}": "ok" for i in range(3)}
    t = _timing(w)
    assert (t["engine"], t["width"], t["shards"], t["cells_planned"]) == (
        "private", 2, 2, 3)
    assert t["platform"] == sys.platform and t["cpus"] >= 1
    assert set(t["cells"]) == {"cell_0", "cell_1", "cell_2"}
    assert [t["cells"][f"cell_{i}"]["shard"] for i in range(3)] == [0, 1, 0]
    # the runner (this Python) times a cell with time.monotonic, whose
    # reading can lag by one tick: 15.6 ms on Windows before Python 3.13,
    # so a 0.05 s sleep can read 0.047 there (well under 1 ms elsewhere)
    tick = time.get_clock_info("monotonic").resolution
    for k, c in t["cells"].items():
        assert round(0.05 - tick, 3) <= c["seconds"] < t["seconds"], k
        assert (c["n_obs"], c["particles"]) == (1, 100)
    assert t["cells"]["cell_2"]["weeks_dropped"] == 1
    assert t["predicted_seconds"] == pytest.approx(
        pf.expected_seconds(pf.shard_cells(cells, 2)), abs=1e-3)


def test_the_records_the_console_reads_keep_their_bytes_and_keys(engine,
                                                                  tmp_path):
    """The shard status is the bytes json.dump wrote before; the .prog
    keys are the four api_progress reads; the merged status is the
    record; and api_progress's pattern does not see the seconds."""
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 3)
    out = pf.execute(w, width=1)
    assert (w / "pf_status_0.json").read_bytes() == json.dumps(out).encode()
    assert json.loads((w / "pf_status.json").read_text()) == out
    prog = json.loads((w / "pf_status_0.json.prog").read_text())
    assert sorted(prog) == ["done", "now", "t0", "total"]
    assert sorted(p.name for p in w.glob("pf_status*.json.prog")) == [
        "pf_status_0.json.prog"]
    assert sorted(p.name for p in w.glob("pf_status*.json")) == [
        "pf_status.json", "pf_status_0.json"]
    assert json.loads((w / "pf_status_0.json.secs.prog").read_text()).keys() \
        == {"cell_0", "cell_1", "cell_2"}


def test_api_progress_reads_the_same_with_the_seconds_beside_it(
        engine, tmp_path, monkeypatch):
    """/api/progress on a finished grid: the same counts and tiles with
    the per-shard seconds there and with them removed."""
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    from app.ui import state as ui_state
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    pf.execute(w, width=1)
    before = dict(ui_state._status)
    try:
        ui_state._status.update({"running": "all:x", "workroot": str(w),
                                 "expected_total": 2,
                                 "started_utc": time.time() - 5})
        client = TestClient(srv.app)

        def counts():
            got = client.get("/api/progress").json()
            return got["done"], got["total"], got["locations"]
        with_secs = counts()
        (w / "pf_status_0.json.secs.prog").unlink()
        assert counts() == with_secs == (2, 2, with_secs[2])
    finally:
        ui_state._status.clear()
        ui_state._status.update(before)


def test_a_stopped_grid_keeps_the_seconds_of_the_cells_it_finished(
        engine, tmp_path, monkeypatch):
    """cell_0 asks for the stop: the runner halts before cell_1, the
    grid ends stopped, and pf_timing.json has cell_0 alone.

    The supervisor starts looking for the STOP only once the runner has
    written cell_0's seconds. A look in the moment between the cell's end
    and that write stops the runner there, and a cell a stop cuts off has
    no seconds. The first look comes right after the runners are recorded,
    which takes about as long as a runner's start: on Windows it sometimes
    came in that moment."""
    engine("        if os.path.basename(os.getcwd()) == 'cell_0':\n"
           "            open(os.path.join(os.path.dirname(os.getcwd()),\n"
           "                              'STOP'), 'w').close()\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 3)
    secs = w / "pf_status_0.json.secs.prog"
    record = pf.record_runner_pids

    def record_then_wait(*a, **k):
        record(*a, **k)
        end = time.monotonic() + 60
        while time.monotonic() < end:
            try:
                if "cell_0" in json.loads(secs.read_text()):
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.02)
    monkeypatch.setattr(pf, "record_runner_pids", record_then_wait)
    with pytest.raises(pf.RunStopped):
        pf.execute(w, width=1)
    assert set(_timing(w)["cells"]) == {"cell_0"}


def test_a_timing_write_that_fails_never_fails_the_grid(engine, tmp_path,
                                                        monkeypatch):
    engine("        pass\n")

    def refuse(tmp, path, tries=10):
        raise PermissionError(13, "in use", str(path))
    monkeypatch.setattr(pf, "replace_file", refuse)
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    assert pf.execute(w, width=1) == {"cell_0": "ok", "cell_1": "ok"}
    assert not (w / pf.TIMING_NAME).exists()


def test_unreadable_seconds_leave_the_cell_out(engine, tmp_path, monkeypatch):
    """A shard whose seconds file is missing or not a mapping: its cells
    are left out; the others stay."""
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    cells = _grid(w, 4)
    shards = pf.shard_cells(cells, 2)
    status = [w / "pf_status_0.json", w / "pf_status_1.json"]
    Path(str(status[0]) + ".secs.prog").write_text(
        json.dumps({"cell_0": 1.5, "cell_2": True}))
    Path(str(status[1]) + ".secs.prog").write_text("[1, 2]")
    pf._write_timing(w, shards, status, False, 2, 3.0)
    assert _timing(w)["cells"] == {"cell_0": {
        "seconds": 1.5, "shard": 0, "n_obs": 1, "weeks_dropped": 0,
        "particles": 100}}


def test_the_public_runner_times_each_cell_too(public, monkeypatch, tmp_path):
    """The real public runner, in a Python without pybnf: the cell it runs
    (and fails) has its seconds; the cell refused before any run has none."""
    import sys as _sys
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC", _sys.executable)
    good, bad = _cell(tmp_path, "A_r0"), _cell(tmp_path, "B_r0")
    (bad / "pf.conf").write_text((bad / "pf.conf").read_text()
                                 + "pf_continue = 0\n")
    (tmp_path / "cells.json").write_text(json.dumps([_record(good),
                                                     _record(bad)]))
    st = pf.execute(tmp_path, width=1)
    assert st["A_r0"].startswith("FAIL: the public engine stopped")
    t = _timing(tmp_path)
    assert t["engine"] == "public"
    assert set(t["cells"]) == {"A_r0"}
    assert t["cells"]["A_r0"]["seconds"] > 0
    assert t["cells"]["A_r0"]["n_obs"] == _record(good)["n_obs"]


def test_reclaim_prunes_the_seconds_and_keeps_the_timing_records(engine,
                                                                 tmp_path):
    engine("        pass\n")
    w = tmp_path / "wr"
    w.mkdir()
    _grid(w, 2)
    pf.execute(w, width=1)
    (w / "results.json").write_text("{}")       # a complete run
    (w / ui_pipeline.RUN_TIMING_NAME).write_text("{}")
    gone = {p.name for p in reclaim.workroot_intermediates(w)}
    assert "pf_status_0.json.secs.prog" in gone
    assert pf.TIMING_NAME not in gone
    assert ui_pipeline.RUN_TIMING_NAME not in gone
    reclaim.prune_workroot(w)
    assert (w / pf.TIMING_NAME).is_file()
    assert (w / ui_pipeline.RUN_TIMING_NAME).is_file()


# ------------------------------------------------------------ the console run

#: the steps a console run with the Oracle step goes through, in order
STEPS = ["setting up the run",
         "materializing models (BNG network generation)",
         "filtering 2 location(s) × 1 replicate(s)",
         "reading the fits",
         "the Oracle step: the donor bank from the vintage",
         "keeping the filter's own forecasting sample",
         "consulting the Groundhog",
         "writing submissions",
         "scoring",
         "writing the weekly report",
         "writing the results and the archive",
         "closing the run and pruning its fit folders"]


def test_a_console_run_writes_its_steps_beside_its_record(console):
    srv, _raw = console
    _spec, row, outcome, w = _run(srv)
    t = json.loads((w / ui_pipeline.RUN_TIMING_NAME).read_text())
    assert t["run_id"] == row["run_id"] and t["ended"] == "ok"
    assert [p["phase"] for p in t["phases"]] == STEPS
    assert all(p["seconds"] >= 0 for p in t["phases"])
    assert t["seconds"] == pytest.approx(
        sum(p["seconds"] for p in t["phases"]), abs=0.01)
    assert "timing" not in json.dumps(outcome)
    assert not (set(json.loads((w / "results.json").read_text()))
                & {"phases", "phase_seconds", "timing", "seconds"})


def test_results_and_the_outcome_are_the_same_without_the_timing(
        console, monkeypatch):
    """The same run twice, the second with the timing turned off: the
    same results.json, byte for byte, and the same outcome but its paths."""
    srv, _raw = console
    _s1, row1, out1, w1 = _run(srv)
    monkeypatch.setattr(ui_shared, "_PHASE_MARKS_MAX", 0)    # no marks
    monkeypatch.setattr(ui_pipeline, "_write_run_timing",
                        lambda *a, **k: None)
    _s2, row2, out2, w2 = _run(srv)
    assert ui_shared._phase_marks == []
    assert w1 != w2 and not (w2 / ui_pipeline.RUN_TIMING_NAME).exists()
    assert (w1 / "results.json").read_bytes() == (w2 / "results.json").read_bytes()

    def same(o, w):
        """o with its workroot written <W>, in the parsed strings: in
        json.dumps text a Windows path's backslashes (and any non-ASCII
        letter) are escaped, and str(w) would not be found there."""
        if isinstance(o, str):
            return o.replace(str(w), "<W>")
        if isinstance(o, dict):
            return {same(k, w): same(v, w) for k, v in o.items()}
        if isinstance(o, list):
            return [same(v, w) for v in o]
        return o
    assert "<W>" in json.dumps(same(out1, w1))      # its paths were there
    assert same(out1, w1) == same(out2, w2)
    assert row1["status"] == row2["status"] == "ok"


def test_a_run_that_errors_records_how_far_it_got(console, monkeypatch):
    import app.core.engines.pf as pf_engine
    srv, _raw = console

    def boom(w):
        raise RuntimeError("the fits could not start")
    monkeypatch.setattr(pf_engine, "execute", boom)
    _spec, row, _outcome, w = _run(srv)
    assert row["status"] == "error"
    t = json.loads((w / ui_pipeline.RUN_TIMING_NAME).read_text())
    assert t["ended"] == "error"
    assert [p["phase"] for p in t["phases"]] == STEPS[:3]


def test_a_run_timing_write_that_fails_never_fails_the_run(console,
                                                           monkeypatch):
    srv, _raw = console
    # a name in a folder that is not there: the write fails
    monkeypatch.setattr(ui_pipeline, "RUN_TIMING_NAME",
                        "no-such-folder/run_timing.json")
    _spec, row, _outcome, w = _run(srv)
    assert row["status"] == "ok"
    assert not (w / "no-such-folder").exists()
    assert not list(w.glob("run_timing*"))


def test_the_marks_never_grow_without_end():
    ui_shared._phase_start("a run")
    for i in range(ui_shared._PHASE_MARKS_MAX + 50):
        ui_shared._phase_mark(f"step {i}")
    assert len(ui_shared._phase_marks) == ui_shared._PHASE_MARKS_MAX
    got = ui_shared._phase_seconds()
    assert got[0]["phase"] == "a run" and len(got) == ui_shared._PHASE_MARKS_MAX
    ui_shared._phase_start("next")
    assert [p["phase"] for p in ui_shared._phase_seconds()] == ["next"]
