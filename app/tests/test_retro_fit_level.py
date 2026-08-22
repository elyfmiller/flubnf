"""Fit-level stop, pause, and resume inside a retrospective week.

The controls used to land only at week boundaries: a full-grid week is
roughly 150 fits and ten minutes of work, which made Pause useless for
getting the machine back. run_week now polls the STOP and PAUSE flags
between individual fits, drains only the fits in flight, checkpoints every
finished fit in the week's cells_done/, and a resumed week refits only the
cells that never ran. samples.json still appears only when the week is
fully done, so week atomicity downstream is unchanged.

These tests drive run_week with stubbed engines and fake runner processes
whose fits take two polls each and whose drain matches the real runner: the
fit in flight always finishes and leaves its marker, nothing after it is
started. One test runs the real runner script in a subprocess against a
fake pybnf, so the generated code itself is executed, not just formatted.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                         # noqa: E402

from app.core import report_season, retro             # noqa: E402
from app.ui import server as srv                      # noqa: E402

SEASON = "2098-99"
W1 = "2098-11-07"
N_CELLS = 6


def _stub_engines(monkeypatch, log, ticks_per_fit=2):
    """Stub prepare/collect/analogue and the runner processes. Returns the
    call counter so tests can assert preparation reuse."""
    calls = {"prepare": 0}

    def fake_prepare(spec, wd):
        calls["prepare"] += 1
        cells = [{"key": f"cell_{i}", "dir": str(Path(wd) / f"cell_{i}")}
                 for i in range(N_CELLS)]
        (Path(wd) / "cells.json").write_text(json.dumps(cells))
        return cells

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {"Ohio": {"0": [1.0]}})
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {"1": {0.5: 2.0}}})

    class FakeRunner:
        """One runner subprocess: a fit takes ticks_per_fit polls, HALT is
        checked only BETWEEN fits, and the fit in flight always finishes
        and leaves its marker -- the real runner's drain semantics."""

        def __init__(self, wd, shard, halt):
            self.wd, self.shard, self.halt = Path(wd), list(shard), halt
            self.i, self.tick, self.dead = 0, 0, False

        def poll(self):
            if self.dead or self.i >= len(self.shard):
                return 0
            self.tick += 1
            if self.tick < ticks_per_fit:
                return None                    # the fit is still in flight
            c = self.shard[self.i]             # ... and now it finishes
            retro.mark_cell_done(self.wd, c["key"])
            log.append(c["key"])
            self.i, self.tick = self.i + 1, 0
            if self.halt.exists() or self.i >= len(self.shard):
                self.i = len(self.shard)       # HALT: start nothing more
                return 0
            return None

        def kill(self):
            self.dead = True

    monkeypatch.setattr(
        retro, "_launch_runners",
        lambda wd, shards, halt: [FakeRunner(wd, s, halt) for s in shards])
    return calls


def _run(root, **kw):
    return retro.run_week(root, SEASON, W1, ["Ohio"], **kw)


# ------------------------------------------------- stop lands between fits

def test_stop_drains_in_flight_fits_and_resume_refits_only_the_rest(
        tmp_path, monkeypatch):
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    log = []
    calls = _stub_engines(monkeypatch, log)
    stop = {"sent": False}

    def press_stop(_s):
        # the click lands mid-week, after the second fit completes
        if not stop["sent"] and len(log) >= 2:
            stop["sent"] = True
            retro.request_stop(root)

    monkeypatch.setattr(retro, "_sleep", press_stop)
    with pytest.raises(retro.SeasonStopped):
        _run(root, width=2)

    # only the fits in flight finished; nothing after them was started, and
    # the week's samples.json was NOT written (the week stays incomplete)
    finished = retro.cells_done(wd)
    assert finished == set(log)
    assert 2 <= len(finished) < N_CELLS
    assert not (wd / "samples.json").exists()
    assert not retro.week_done(root, W1)

    # resume: the same week refits EXACTLY the cells that never ran; the
    # preparation is reused, no finished fit is redone, and samples.json
    # appears only now, at completion
    retro.clear_flags(root)
    log2 = []
    _stub_engines(monkeypatch, log2)
    monkeypatch.setattr(retro.pf_engine, "prepare",
                        lambda *a, **k: pytest.fail("prep must be reused"))
    monkeypatch.setattr(retro, "_sleep", lambda _s: None)
    out = _run(root, width=2)
    assert calls["prepare"] == 1                    # prepared once, reused
    assert set(log2) == {f"cell_{i}" for i in range(N_CELLS)} - finished
    assert len(log2) == N_CELLS - len(finished)     # nothing fitted twice
    assert retro.week_done(root, W1)
    assert out["asof"] == W1 and "pf" in out and "analogue" in out


def test_stop_before_any_fit_leaves_the_week_untouched(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    log = []
    _stub_engines(monkeypatch, log)
    root.mkdir(parents=True)
    retro.request_stop(root)                   # the flag already stands
    with pytest.raises(retro.SeasonStopped):
        _run(root, width=2)
    assert log == []                           # no fit was dispatched
    assert not retro.week_done(root, W1)


# ----------------------------------------------- pause drains, holds, resumes

def test_pause_drains_in_flight_fits_then_holds_then_finishes(
        tmp_path, monkeypatch):
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    log, held = [], []
    _stub_engines(monkeypatch, log)
    state = {"sent": False}

    def fake_sleep(_s):
        m = retro.read_meta(root)
        if m.get("status") == "paused":
            # the hold is real and observable; the drained fits are already
            # checkpointed. Then the Resume click releases it.
            held.append(frozenset(retro.cells_done(wd)))
            retro.clear_pause(root)
            return
        if not state["sent"] and len(log) >= 2:
            state["sent"] = True
            retro.request_pause(root)

    monkeypatch.setattr(retro, "_sleep", fake_sleep)
    _run(root, width=2)
    assert len(held) == 1                          # it really held, once
    assert 2 <= len(held[0]) < N_CELLS             # after the in-flight drain
    assert held[0] == frozenset(log[:len(held[0])])
    # the hold released, the remaining fits ran, each cell exactly once
    assert sorted(log) == sorted(f"cell_{i}" for i in range(N_CELLS))
    assert retro.week_done(root, W1)


def test_stop_while_paused_mid_week_exits_without_samples(tmp_path,
                                                          monkeypatch):
    root = tmp_path / SEASON
    log = []
    _stub_engines(monkeypatch, log)
    state = {"sent": False}

    def fake_sleep(_s):
        m = retro.read_meta(root)
        if m.get("status") == "paused":
            retro.request_stop(root)     # request_stop clears PAUSE to wake
            return
        if not state["sent"] and len(log) >= 2:
            state["sent"] = True
            retro.request_pause(root)

    monkeypatch.setattr(retro, "_sleep", fake_sleep)
    with pytest.raises(retro.SeasonStopped):
        _run(root, width=2)
    assert not retro.week_done(root, W1)
    assert len(log) < N_CELLS


# ------------------------------------------------------- mid-week resume

def test_resume_with_all_cells_done_just_assembles(tmp_path, monkeypatch):
    """A stop that lands after the last fit drains leaves every marker and
    no samples.json; the resumed week dispatches nothing and assembles.
    The state is built with completion hygiene disabled (a completed week
    prunes its markers), because the real scenario -- every fit drained,
    assembly never reached -- is exactly a week that never completed."""
    from app.core import reclaim
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    log = []
    _stub_engines(monkeypatch, log)
    monkeypatch.setattr(retro, "_sleep", lambda _s: None)
    monkeypatch.setattr(reclaim, "prune_week", lambda _wd: 0)
    _run(root, width=2)                                # complete the week
    retro.samples_file(wd).unlink()                    # ...but lose assembly
    log2 = []
    _stub_engines(monkeypatch, log2)
    monkeypatch.setattr(
        retro, "_launch_runners",
        lambda *a, **k: pytest.fail("no fit may be dispatched"))
    out = _run(root, width=2)
    assert log2 == []                                  # nothing refitted
    assert retro.week_done(root, W1)
    assert out["asof"] == W1


def test_changed_settings_rebuild_the_week_from_scratch(tmp_path,
                                                        monkeypatch):
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    log = []
    calls = _stub_engines(monkeypatch, log)
    stop = {"sent": False}

    def press_stop(_s):
        if not stop["sent"] and len(log) >= 2:
            stop["sent"] = True
            retro.request_stop(root)

    monkeypatch.setattr(retro, "_sleep", press_stop)
    with pytest.raises(retro.SeasonStopped):
        _run(root, width=2)
    survivors = retro.cells_done(wd)
    assert survivors
    retro._record_partial(root, W1, 40.0)      # the stopped segment's bank
    retro.clear_flags(root)

    # a resume under DIFFERENT settings must not mix in the old fits: the
    # week rebuilds clean, refits everything, and the banked seconds retire
    log2 = []
    calls2 = _stub_engines(monkeypatch, log2)
    monkeypatch.setattr(retro, "_sleep", lambda _s: None)
    _run(root, width=2, particles=5_000)
    assert calls["prepare"] == 1               # the first stub's count stands
    assert calls2["prepare"] == 1              # ... and the rebuild prepared
    assert len(log2) == N_CELLS                # every cell refit
    assert retro.week_done(root, W1)
    assert retro.read_meta(root).get("week_partial_s", {}) == {}


def test_broken_runners_raise_instead_of_spinning(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    _stub_engines(monkeypatch, [])

    class DeadProc:
        def poll(self):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [DeadProc()])
    monkeypatch.setattr(retro, "_sleep", lambda _s: None)
    with pytest.raises(RuntimeError):
        _run(root, width=2)


# --------------------------------------------------- the real runner script

def test_real_runner_script_marks_ok_and_fail_cells(tmp_path, monkeypatch):
    """_run_round end to end with real subprocesses: the generated runner
    executes against a fake pybnf, marks a good cell ok and a raising cell
    FAIL, and the round completes without flags."""
    pkg = tmp_path / "fake_pybnf" / "pybnf"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "parse.py").write_text("def load_config(p):\n    return p\n")
    (pkg / "pf.py").write_text(
        "import os\n"
        "class ParticleFilter:\n"
        "    def __init__(self, cfg):\n"
        "        self.cfg = cfg\n"
        "    def run(self, _):\n"
        "        if os.getcwd().endswith('cell_1'):\n"
        "            raise RuntimeError('synthetic failure')\n")
    monkeypatch.setattr(retro.pf_engine, "PYBNF_PF", tmp_path / "fake_pybnf")
    monkeypatch.setattr(retro.pf_engine, "PY310", Path(sys.executable))
    monkeypatch.setattr(retro, "_sleep", lambda _s: time.sleep(0.05))
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    cells = []
    for i in range(2):
        d = wd / f"cell_{i}"
        d.mkdir(parents=True)
        cells.append({"key": f"cell_{i}", "dir": str(d)})
    retro._run_round(root, wd, cells, width=2)
    done = retro._cell_done_dir(wd)
    ok = json.loads((done / "cell_0.json").read_text())
    bad = json.loads((done / "cell_1.json").read_text())
    assert ok["status"] == "ok"
    assert bad["status"].startswith("FAIL")
    assert retro.cells_done(wd) == {"cell_0", "cell_1"}


# ------------------------------------------------ mid-week stop timing rule

def test_midweek_stop_banks_partial_time_and_defers_week_seconds(
        tmp_path, monkeypatch):
    root = tmp_path / SEASON
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(retro, "_now", lambda: clock["t"])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1])

    def stopped_week(r, season, asof, *a, **k):
        clock["t"] += 40.0
        raise retro.SeasonStopped("fit-level stop mid-week")

    monkeypatch.setattr(retro, "run_week", stopped_week)
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    m = retro.read_meta(root)
    assert m["status"] == "stopped"
    assert m["week_seconds"] == {}              # an incomplete week is untimed
    assert m["week_partial_s"] == {W1: 40.0}    # but its work is banked
    assert m["elapsed_s"] == pytest.approx(40.0)   # and counted as elapsed
    assert retro.timing(m)["mean_s"] is None    # the mean stays honest

    def finishing_week(r, season, asof, *a, **k):
        clock["t"] += 20.0
        wk = Path(r) / "weeks" / asof
        wk.mkdir(parents=True, exist_ok=True)
        (wk / "samples.json").write_text(json.dumps({"asof": asof}))
        return {"asof": asof}

    monkeypatch.setattr(retro, "run_week", finishing_week)
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    m2 = retro.read_meta(root)
    assert m2["status"] == "done"
    assert m2["week_seconds"] == {W1: 60.0}     # both segments' work, once
    assert m2["week_partial_s"] == {}           # the bank is spent
    assert m2["elapsed_s"] == pytest.approx(60.0)


# ------------------------------------------- no fabricated zero wall time

def _index_card(elapsed_s):
    return {"name": SEASON, "total": 30, "done": 30, "seal": False,
            "running": False, "paused": False, "active": False,
            "status": "done", "elapsed_s": elapsed_s, "mean_s": None,
            "weeks_measured": 0, "eta_s": None, "scored": True}


def test_retro_index_never_fabricates_a_zero_wall_time():
    # the base template's startover modal script carries the phrase itself,
    # so the assertion targets the card's rendered timing line
    tpl = srv.templates.env.get_template("retro.html")
    for bad in (None, 0, 0.4):
        html = tpl.render(active="Retrospective", state_names=["Ohio"],
                          engine_ok=True, seasons=[_index_card(bad)])
        assert "total wall time 0:00:00" not in html
        assert 'class="hint timing"' not in html
    ok = tpl.render(active="Retrospective", state_names=["Ohio"],
                    engine_ok=True, seasons=[_index_card(3725.0)])
    assert "total wall time 1:02:05" in ok


def test_season_page_never_fabricates_a_zero_wall_time():
    def render(elapsed_s):
        return srv.templates.env.get_template("retro_season.html").render(
            active="Retrospective", season=SEASON, heads={}, curve=[],
            states=[], weeks=[W1], week=W1, map_html="", n_weeks=1,
            score_error="", prog={"status": "stopped", "active": False,
                                  "done": 5, "total": 30,
                                  "elapsed_s": elapsed_s, "mean_s": None,
                                  "weeks_measured": 0, "eta_s": None,
                                  "slowest_week": None, "slowest_s": None})

    for bad in (None, 0, 0.4):
        assert "Replay wall time" not in render(bad)
    assert "Replay wall time 1:02:05" in render(3725.0)


def test_season_report_header_refuses_a_sub_second_record(tmp_path):
    root = tmp_path / "seasonroot"
    retro.write_meta(root, {"status": "done", "elapsed_s": 0.4,
                            "weeks_completed": 26, "total_weeks": 26,
                            "heartbeat_utc": time.time()})
    assert report_season._timing_note(root) == ""
    retro.write_meta(root, {"status": "done", "elapsed_s": 3725.0,
                            "weeks_completed": 26, "total_weeks": 26,
                            "heartbeat_utc": time.time()})
    assert "Total wall time 1:02:05" in report_season._timing_note(root)


def test_startover_api_withholds_a_sub_second_wall_time(tmp_path,
                                                        monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    retro.write_meta(root, {"status": "stopped", "elapsed_s": 0.4})
    client = TestClient(srv.app)
    b = client.get(f"/api/retro/startover?season={SEASON}").json()
    assert b["elapsed_hms"] == ""


# --------------------------------------------------------------- UI copy

def test_stopping_badge_names_the_fits_in_flight():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 3, "seal": False,
                  "running": True, "paused": False, "active": True,
                  "status": "stopping", "elapsed_s": 600.0, "mean_s": 60.0,
                  "weeks_measured": 3, "eta_s": None, "scored": False}])
    assert "stopping after the fits in flight" in html
    assert "after the current week" not in html
