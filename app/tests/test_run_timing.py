"""Wall-time counters, and the retrospective's stop and pause controls.

Covers the run record written by app.core.retro.run_season (timing that
accumulates across a resume rather than restarting, a heartbeat that exposes
a dead worker, per-week seconds behind the mean and the slowest week), the
STOP and PAUSE flags and the endpoints that set them, the /api/progress and
/api/retro/progress shapes, the timing lines carried by both report exports
and the run ledger, and the retro pages' controls and live ticker.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                   # noqa: E402
import pytest                                         # noqa: E402
from fastapi.testclient import TestClient             # noqa: E402

from app.core import playback, report_season, retro   # noqa: E402
from app.core.runs import Ledger, RunSpec, fmt_hms    # noqa: E402
from app.ui import server as srv                      # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL  # noqa: E402

client = TestClient(srv.app)

SEASON = "2098-99"
W1, W2, W3 = "2098-11-07", "2098-11-14", "2098-11-21"


@pytest.fixture(autouse=True)
def _isolated_status():
    """Snapshot and restore the module-level status stores around each test
    so mocked run states never leak between tests."""
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)


def _fake_season(monkeypatch, root, weeks, seconds_per_week=60.0):
    """A season whose weeks cost a fixed, fake number of seconds. Returns the
    mutable clock so a test can inspect or advance it."""
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(retro, "_now", lambda: clock["t"])
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(weeks))

    def fake_week(r, season, asof, locations, replicates, particles, width,
                  **kw):
        clock["t"] += seconds_per_week
        wd = Path(r) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "samples.json").write_text(json.dumps({"asof": asof}))
        return {"asof": asof}

    monkeypatch.setattr(retro, "run_week", fake_week)
    return clock


# ------------------------------------------------------------------- fmt_hms

def test_fmt_hms_formats_and_refuses_to_invent_zero():
    assert fmt_hms(0) == "0:00:00"
    assert fmt_hms(65) == "0:01:05"
    assert fmt_hms(3725) == "1:02:05"
    assert fmt_hms(86_400 + 61) == "24:01:01"      # never wraps at a day
    for bad in (None, "", -1, float("nan")):
        assert fmt_hms(bad) == "--"


# ------------------------------------------------- season record and timing

def test_run_season_records_timing_and_per_week_seconds(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2])
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    m = retro.read_meta(root)
    assert m["status"] == "done"
    assert m["elapsed_s"] == pytest.approx(120.0)
    assert m["weeks_completed"] == 2
    assert m["total_weeks"] == 2
    assert set(m["week_seconds"]) == {W1, W2}
    t = retro.timing(m)
    assert t["mean_s"] == pytest.approx(60.0)
    assert t["weeks_measured"] == 2
    assert t["slowest_week"] in (W1, W2)
    assert t["slowest_s"] == pytest.approx(60.0)


def test_timing_accumulates_across_a_resume(tmp_path, monkeypatch):
    """A resumed replay carries its earlier segments forward: the clock
    accumulates, it never restarts, and weeks skipped as already complete are
    not timed (a zero-second skip would drag the mean toward nothing)."""
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2])
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    first = retro.read_meta(root)
    assert first["elapsed_s"] == pytest.approx(120.0)

    # the season grows a week; the replay is run again and resumes
    _fake_season(monkeypatch, root, [W1, W2, W3])
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    second = retro.read_meta(root)
    assert second["elapsed_s"] == pytest.approx(180.0)     # 120 + one week
    assert second["started_utc"] == first["started_utc"]   # not restarted
    assert second["weeks_completed"] == 3
    # the two resumed weeks kept their original timings and were not re-timed
    assert second["week_seconds"][W1] == first["week_seconds"][W1]
    assert retro.timing(second)["mean_s"] == pytest.approx(60.0)


def test_record_survives_a_crash_mid_week(tmp_path, monkeypatch):
    """A week that dies takes its own partial time with it, but the record on
    disk stays readable and keeps every completed week's seconds."""
    root = tmp_path / SEASON
    clock = _fake_season(monkeypatch, root, [W1, W2])
    real_week = retro.run_week

    def boom(r, season, asof, *a, **k):
        if asof == W2:
            clock["t"] += 5.0
            raise KeyboardInterrupt("power cut")      # not caught per-week
        return real_week(r, season, asof, *a, **k)

    monkeypatch.setattr(retro, "run_week", boom)
    with pytest.raises(KeyboardInterrupt):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    m = retro.read_meta(root)
    assert m["status"] == "error"
    assert m["week_seconds"] == {W1: 60.0}          # the completed week stands
    assert m["elapsed_s"] >= 60.0
    assert retro.week_done(root, W1)


# ------------------------------------------------------------ stop and pause

def test_stop_finishes_the_current_week_then_exits(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2, W3])
    real_week = retro.run_week

    def stop_after_first(r, season, asof, *a, **k):
        out = real_week(r, season, asof, *a, **k)
        if asof == W1:
            retro.request_stop(r)          # the click lands mid-week
        return out

    monkeypatch.setattr(retro, "run_week", stop_after_first)
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    # the week in flight finished and checkpointed; no later week started
    assert retro.week_done(root, W1)
    assert not retro.week_done(root, W2)
    m = retro.read_meta(root)
    assert m["status"] == "stopped"
    assert m["weeks_completed"] == 1
    assert m["week_seconds"] == {W1: 60.0}

    # pressing Run again resumes exactly where it left off
    _fake_season(monkeypatch, root, [W1, W2, W3])
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    m2 = retro.read_meta(root)
    assert m2["status"] == "done"
    assert m2["weeks_completed"] == 3
    assert m2["elapsed_s"] == pytest.approx(180.0)   # 60 kept + two new weeks


def test_pause_holds_then_resume_continues(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    clock = _fake_season(monkeypatch, root, [W1, W2])
    real_week = retro.run_week
    seen = []

    def pause_after_first(r, season, asof, *a, **k):
        out = real_week(r, season, asof, *a, **k)
        if asof == W1:
            retro.request_pause(r)
        return out

    def fake_sleep(_s):
        # the hold is observable on disk, and held time does not tick
        seen.append(retro.read_meta(root)["status"])
        clock["t"] += 500.0
        retro.clear_pause(root)                       # the Resume click

    monkeypatch.setattr(retro, "run_week", pause_after_first)
    monkeypatch.setattr(retro, "_sleep", fake_sleep)
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert seen == ["paused"]                         # it really held
    assert retro.week_done(root, W2)                  # and then continued
    m = retro.read_meta(root)
    assert m["status"] == "done"
    assert m["elapsed_s"] == pytest.approx(120.0)     # the 500 s hold is not work


def test_stop_while_paused_wakes_the_worker(tmp_path, monkeypatch):
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2])
    real_week = retro.run_week

    def pause_after_first(r, season, asof, *a, **k):
        out = real_week(r, season, asof, *a, **k)
        if asof == W1:
            retro.request_pause(r)
        return out

    def fake_sleep(_s):
        retro.request_stop(root)          # request_stop clears PAUSE as well

    monkeypatch.setattr(retro, "run_week", pause_after_first)
    monkeypatch.setattr(retro, "_sleep", fake_sleep)
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert not retro.week_done(root, W2)
    assert retro.read_meta(root)["status"] == "stopped"


def test_flag_requests_never_create_a_season_tree(tmp_path):
    absent = tmp_path / "never-replayed"
    assert retro.request_stop(absent) is False
    assert retro.request_pause(absent) is False
    assert not absent.exists()


def test_run_season_clears_stale_flags_from_an_earlier_replay(tmp_path,
                                                              monkeypatch):
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    retro.request_stop(root)                  # left behind by a past stop
    _fake_season(monkeypatch, root, [W1])
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert retro.week_done(root, W1)          # not stopped before it began
    assert retro.read_meta(root)["status"] == "done"


# ------------------------------------------------------- stale heartbeat

def test_stale_heartbeat_unmasks_a_dead_worker():
    now = 5_000.0
    live = {"status": "running", "heartbeat_utc": now - 5}
    dead = {"status": "running", "heartbeat_utc": now - retro.HEARTBEAT_STALE_S - 1}
    assert retro.effective_status(live, now=now) == "running"
    assert retro.effective_status(dead, now=now) == "interrupted"
    assert retro.is_stale(dead, now=now) is True
    assert retro.is_stale(live, now=now) is False
    # a paused worker still beats, so a fresh pause stays paused
    assert retro.effective_status({"status": "paused",
                                   "heartbeat_utc": now - 5}, now=now) == "paused"
    # settled statuses are never second-guessed by the clock
    assert retro.effective_status({"status": "done",
                                   "heartbeat_utc": now - 99_999}, now=now) == "done"
    # no heartbeat at all is not evidence of life
    assert retro.is_stale({"status": "running"}, now=now) is True


def test_season_status_stops_claiming_a_dead_run(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    srv._retro_status[SEASON] = "running"      # the claim the dead worker left
    retro.write_meta(root, {"status": "running", "elapsed_s": 12.0,
                            "heartbeat_utc": time.time() - 10})
    assert srv._season_status(SEASON) == "running"
    retro.write_meta(root, {"status": "running", "elapsed_s": 12.0,
                            "heartbeat_utc": time.time()
                            - retro.HEARTBEAT_STALE_S - 60})
    assert srv._season_status(SEASON) == "interrupted"
    assert srv._retro_status[SEASON] == "interrupted"   # the claim is released
    assert client.get("/api/busy").json()["retro"] == {}


def test_season_status_reads_pause_from_the_record(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    srv._retro_status[SEASON] = "running"      # the worker is alive, holding
    retro.write_meta(root, {"status": "paused", "elapsed_s": 30.0,
                            "heartbeat_utc": time.time()})
    assert srv._season_status(SEASON) == "paused"
    # a paused season still holds the engine: the guard must warn over it
    assert client.get("/api/busy").json()["retro"] == {SEASON: "paused"}


# --------------------------------------------------------------- API shapes

def test_api_progress_carries_the_console_wall_clock():
    srv._status.update({"running": None, "started_utc": None,
                        "phase": "", "run_label": "", "workroot": None})
    idle = client.get("/api/progress").json()
    assert idle["started_utc"] is None and idle["elapsed_s"] is None
    t0 = time.time() - 125.0
    srv._status.update({"running": "all:x", "started_utc": t0,
                        "run_label": "2099-01-02 · 3 state(s) + US"})
    live = client.get("/api/progress").json()
    assert live["started_utc"] == t0
    assert 124.0 <= live["elapsed_s"] <= 135.0


def test_api_retro_progress_shape_and_eta(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    for w in (W1, W2):
        (root / "weeks" / w).mkdir(parents=True)
        (root / "weeks" / w / "samples.json").write_text("{}")
    srv._retro_status[SEASON] = "running"
    retro.write_meta(root, {"status": "running", "total_weeks": 10,
                            "weeks_completed": 2, "elapsed_s": 240.0,
                            "segment_start_utc": None,
                            "week_seconds": {W1: 100.0, W2: 140.0},
                            "heartbeat_utc": time.time()})
    p = client.get(f"/api/retro/progress?season={SEASON}").json()[SEASON]
    assert p["status"] == "running" and p["active"] is True
    assert (p["done"], p["total"]) == (2, 10)
    assert p["elapsed_s"] == pytest.approx(240.0)
    assert p["mean_s"] == pytest.approx(120.0)
    assert p["weeks_measured"] == 2
    # the estimate is recency-weighted (half-life three weeks), never the
    # global mean: the recent 140 s week outvotes the older 100 s one, so
    # the level sits above the mean; and with no season profile the
    # remaining weeks are priced by the recorded full-grid shape (later
    # weeks cost more), so the estimate sits above level x remaining. The
    # API must agree with the pure estimator on this fixture's positions
    # (no vintage calendar for a fake season: index over total_weeks).
    w = 0.5 ** (1 / 3)
    level = (100.0 * w + 140.0) / (w + 1.0)
    measured = [(0 / 9, 100.0), (1 / 9, 140.0)]
    remaining = [j / 9 for j in range(2, 10)]
    _, mid, _ = srv._eta_estimate(measured, remaining)
    assert p["eta_s"] == pytest.approx(mid)
    assert p["eta_s"] > level * 8 > 120.0 * 8
    # and it is a RANGE: two measured weeks cannot claim precision, so the
    # band is at its widest floor (half to one-and-a-half times the middle)
    assert p["eta_lo_s"] == pytest.approx(0.5 * p["eta_s"])
    assert p["eta_hi_s"] == pytest.approx(1.5 * p["eta_s"])
    assert p["eta_basis"] == ("estimate from 2 completed weeks, shaped by "
                              "the recorded full-grid week profile")
    assert p["slowest_week"] == W2 and p["slowest_s"] == pytest.approx(140.0)
    # an unrecognized season name never reaches the filesystem
    assert client.get("/api/retro/progress?season=../etc").json() == {}


def test_api_retro_progress_withholds_eta_when_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    srv._retro_status[SEASON] = "running"
    retro.write_meta(root, {"status": "paused", "total_weeks": 10,
                            "elapsed_s": 240.0, "week_seconds": {W1: 100.0},
                            "heartbeat_utc": time.time()})
    p = client.get(f"/api/retro/progress?season={SEASON}").json()[SEASON]
    assert p["status"] == "paused"
    # nothing is being worked through: the whole estimate is withdrawn, so
    # the page can say "paused" instead of decaying a stale range
    assert p["eta_s"] is None
    assert p["eta_lo_s"] is None and p["eta_hi_s"] is None
    assert p["eta_basis"] is None


# -------------------------------------------------------- control endpoints

def _running_root(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / SEASON
    root.mkdir(parents=True)
    srv._retro_status[SEASON] = "running"
    retro.write_meta(root, {"status": "running", "total_weeks": 3,
                            "elapsed_s": 10.0, "heartbeat_utc": time.time()})
    return root


def test_season_stop_endpoint_sets_the_flag(tmp_path, monkeypatch):
    root = _running_root(tmp_path, monkeypatch)
    r = client.post(f"/retro/{SEASON}/stop", follow_redirects=False)
    assert r.status_code == 303
    assert retro.stop_path(root).exists()
    assert srv._retro_status[SEASON] == "stopping"
    assert SEASON in srv._retro_stop


def test_season_pause_and_resume_endpoints(tmp_path, monkeypatch):
    root = _running_root(tmp_path, monkeypatch)
    assert client.post(f"/retro/{SEASON}/pause",
                       follow_redirects=False).status_code == 303
    assert retro.pause_path(root).exists()
    assert client.post(f"/retro/{SEASON}/resume",
                       follow_redirects=False).status_code == 303
    assert not retro.pause_path(root).exists()


def test_season_controls_are_harmless_when_idle(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    srv._retro_status.pop(SEASON, None)
    for verb in ("stop", "pause"):
        r = client.post(f"/retro/{SEASON}/{verb}", follow_redirects=False)
        assert r.status_code == 303
    assert not (tmp_path / SEASON).exists()      # no tree conjured up


def test_season_controls_refuse_an_unrecognized_name(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    for verb in ("stop", "pause", "resume"):
        r = client.post(f"/retro/not-a-season/{verb}", follow_redirects=False)
        assert r.status_code == 303
    assert list(tmp_path.iterdir()) == []


def test_global_stop_also_releases_a_paused_season(tmp_path, monkeypatch):
    root = _running_root(tmp_path, monkeypatch)
    retro.write_meta(root, {"status": "paused", "total_weeks": 3,
                            "elapsed_s": 10.0, "heartbeat_utc": time.time()})
    retro.request_pause(root)
    r = client.post("/retro/stop", follow_redirects=False)
    assert r.status_code == 303
    assert retro.stop_path(root).exists()
    assert not retro.pause_path(root).exists()   # so the worker can wake
    assert srv._retro_status[SEASON] == "stopping"


def test_stop_endpoint_stops_the_season_worker_end_to_end(tmp_path,
                                                          monkeypatch):
    """The whole path: a click on Stop, the flag, the worker finishing its
    current week, the ledgered status, and a tree left ready to resume."""
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2, W3])
    real_week = retro.run_week

    def stop_via_endpoint(r, season, asof, *a, **k):
        out = real_week(r, season, asof, *a, **k)
        if asof == W1:
            assert client.post(f"/retro/{SEASON}/stop",
                               follow_redirects=False).status_code == 303
        return out

    def no_score(*a, **k):
        raise AssertionError("a stopped run must not be scored")

    monkeypatch.setattr(retro, "run_week", stop_via_endpoint)
    monkeypatch.setattr(retro, "score_season", no_score)
    srv._retro_bg(SEASON, ["Ohio"], width=1)
    assert srv._retro_status[SEASON] == "stopped"
    assert retro.week_done(root, W1)              # the completed week is kept
    assert not retro.week_done(root, W2)          # no half-week was started
    assert not retro.stop_path(root).exists()     # the flag is consumed
    assert SEASON not in srv._retro_stop
    assert retro.read_meta(root)["status"] == "stopped"


def test_pause_endpoint_holds_the_season_worker_end_to_end(tmp_path,
                                                           monkeypatch):
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    root = tmp_path / SEASON
    _fake_season(monkeypatch, root, [W1, W2])
    real_week = retro.run_week
    seen = []

    def pause_via_endpoint(r, season, asof, *a, **k):
        out = real_week(r, season, asof, *a, **k)
        if asof == W1:
            client.post(f"/retro/{SEASON}/pause", follow_redirects=False)
        return out

    def fake_sleep(_s):
        # while held, the console reports the hold and the guard warns over it
        seen.append(client.get("/api/busy").json()["retro"].get(SEASON))
        client.post(f"/retro/{SEASON}/resume", follow_redirects=False)

    monkeypatch.setattr(retro, "run_week", pause_via_endpoint)
    monkeypatch.setattr(retro, "_sleep", fake_sleep)
    monkeypatch.setattr(retro, "score_season", lambda *a, **k: pd.DataFrame())
    srv._retro_bg(SEASON, ["Ohio"], width=1)
    assert seen == ["paused"]
    assert retro.week_done(root, W2)              # Resume carried it on
    assert srv._retro_status[SEASON] == "done"


# ------------------------------------------------------------ ledger elapsed

def test_ledger_records_elapsed_and_migrates_an_old_database(tmp_path):
    import sqlite3
    p = tmp_path / "ledger.sqlite"
    db = sqlite3.connect(p)                      # the pre-timing schema
    db.execute("""CREATE TABLE runs (
        run_id TEXT PRIMARY KEY, created_utc REAL, spec_json TEXT,
        flubnf_sha TEXT, pybnf_sha TEXT, engine_versions TEXT,
        workroot TEXT, status TEXT, outcome_json TEXT)""")
    db.execute("INSERT INTO runs VALUES ('old',1.0,'{}','','','{}','w','ok','{}')")
    db.commit(); db.close()

    led = Ledger(p)
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       tmp_path, {})
    led.close_run(rid, "ok", {"pf_cells": 2})
    rows = {r["run_id"]: r for r in led.rows(10)}
    assert rows["old"]["elapsed_s"] is None      # history is not invented
    assert rows[rid]["elapsed_s"] is not None
    assert rows[rid]["elapsed_s"] >= 0
    assert rows[rid]["finished_utc"] >= rows[rid]["created_utc"]


def test_runs_page_shows_elapsed_per_completed_run():
    html = srv.templates.env.get_template("runs.html").render(
        active="Runs", ledger=[
            {"run_id": "r1", "label": "2098-01-03 · Jan 03 09:31", "status": "ok",
             "chips": "PF 2 fits", "elapsed_s": 3725.0},
            {"run_id": "r0", "label": "2097-12-27 · Dec 27 08:00", "status": "ok",
             "chips": "", "elapsed_s": None}])
    assert "<th>elapsed</th>" in html
    assert "1:02:05" in html
    # a pre-timing row is dashed out, never given a fabricated duration and
    # never the flat contradiction of an all-n/a column under the footnote
    assert '<td class="elapsed">--</td>' in html
    assert "n/a" not in html
    assert ("recorded before this measurement existed show a dash"
            in " ".join(html.split()))


def test_run_all_closes_its_ledger_row_end_to_end(tmp_path, monkeypatch):
    """The whole close-out contract, through the real pipeline: a completing
    run must leave its ledger row closed (status settled, finished_utc and
    elapsed_s written) and must replace the 'pending' workroot placeholder
    with the leased workroot, so the row the footnote describes is true and
    the row remains the record of record for reproducing the run."""
    import sqlite3
    import app.core.runs as runs_mod
    from app.core.engines import analogue as an_engine
    from app.core.runs import RunSpec
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    monkeypatch.setattr(an_engine, "run", lambda spec: {})
    spec = RunSpec(engine="analogue", forecast_date="2098-01-03",
                   locations=["Ohio"])
    srv._run_all(spec)
    row = sqlite3.connect(tmp_path / "ledger.sqlite").execute(
        "SELECT run_id, status, created_utc, finished_utc, elapsed_s, "
        "workroot FROM runs").fetchall()
    assert len(row) == 1
    run_id, status, created, finished, elapsed, workroot = row[0]
    assert status == "ok"
    assert finished is not None and finished >= created
    assert elapsed is not None and elapsed >= 0
    assert workroot != "pending"                  # the placeholder is closed out
    assert workroot == str(tmp_path / "workroots" / run_id)
    assert Path(workroot).is_dir()


# ------------------------------------------------------------ report timing

def test_weekly_report_footer_states_the_run_wall_time(tmp_path):
    from app.core.report_v2 import build_report
    p = build_report("2098-01-03", {}, {}, {}, tmp_path / "r.html",
                     elapsed_s=3725.0)
    assert "Run wall time: 1:02:05" in p.read_text()
    q = build_report("2098-01-03", {}, {}, {}, tmp_path / "q.html")
    assert "Run wall time" not in q.read_text()   # never guessed


def _mini_season(tmp_path, monkeypatch):
    """A one-week synthetic season root, enough to build a season report."""
    n2f = {"Ohio": "39"}
    truth = {("39", pd.Timestamp(W1) + pd.Timedelta(days=7 * k)): 100.0 + k
             for k in range(-8, 8)}
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, dict(n2f)))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    root = tmp_path / "seasonroot"
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    pf = {"Ohio": {str(h): [truth[("39", pd.Timestamp(W1)
                                   + pd.Timedelta(days=7 * h))] + d
                            for d in (-1.0, 0.0, 1.0)] for h in range(5)}}
    an = {"Ohio": {str(h): {str(L): truth[("39", pd.Timestamp(W1)
                                           + pd.Timedelta(days=7 * h))]
                            + (L - 0.5) * 10 for L in QL}
                   for h in range(1, 5)}}
    (wd / "samples.json").write_text(
        json.dumps({"asof": W1, "pf": pf, "analogue": an}))
    return root


def test_season_report_header_carries_the_timing(tmp_path, monkeypatch):
    root = _mini_season(tmp_path, monkeypatch)
    # no record: the header says nothing rather than inventing a duration
    assert "Total wall time" not in report_season.build_season_report(
        root, SEASON).read_text()
    retro.write_meta(root, {"status": "done", "elapsed_s": 3725.0,
                            "weeks_completed": 1, "total_weeks": 1,
                            "week_seconds": {W1: 3725.0},
                            "heartbeat_utc": time.time()})
    html = report_season.build_season_report(root, SEASON).read_text()
    assert "Total wall time 1:02:05" in html      # the record refreshed it
    assert "1 weeks completed" in html
    assert "mean 3725 s per week over 1 timed" in html


# ----------------------------------------------------------- page treatments

def test_forecast_running_card_shows_a_live_elapsed_clock():
    r = client.get("/forecast")
    assert r.status_code == 200
    assert '<script src="/static/quips.js">' in r.text
    srv._status.update({"running": "all:x", "run_label": "x",
                        "started_utc": time.time() - 30})
    html = client.get("/forecast").text
    assert 'id="elapsed"' in html
    assert "flubnfQuips('quip')" in html          # the shared list, not a copy
    assert "d.elapsed_s" in html                  # re-anchored on every poll
    assert "elapsed0" not in html                 # the value, not the name


def test_retro_index_offers_pause_and_stop_while_running():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 3, "seal": False,
                  "running": True, "paused": False, "active": True,
                  "status": "running", "elapsed_s": 3725.0, "mean_s": 60.0,
                  "weeks_measured": 3, "eta_s": 1620.0, "scored": False}])
    assert f'action="/retro/{SEASON}/pause"' in html
    assert f'action="/retro/{SEASON}/stop"' in html
    assert f'action="/retro/{SEASON}/resume"' not in html
    # stopping is safe and carries no confirmation guard
    assert html.count('data-guard="') == 1
    # the console's run treatment: solid fill on a track, prominent readout,
    # a basis line for the estimate, and rotating quips
    assert 'class="runbar"' in html and 'class="rfill"' in html
    assert 'class="runstat rstat"' in html
    assert 'class="hint rbasis"' in html
    assert 'class="quip rquip"' in html
    assert 'src="/static/retro_progress.js"' in html
    assert "GUARD_BUSY" in html


def test_retro_index_offers_resume_while_paused():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 3, "seal": False,
                  "running": False, "paused": True, "active": True,
                  "status": "paused", "elapsed_s": 3725.0, "mean_s": 60.0,
                  "weeks_measured": 3, "eta_s": None, "scored": False}])
    assert f'action="/retro/{SEASON}/resume"' in html
    assert f'action="/retro/{SEASON}/stop"' in html
    assert f'action="/retro/{SEASON}/pause"' not in html
    assert "· paused" in html
    assert "GUARD_BUSY" in html            # the ticker still runs, and yields


def test_retro_index_reports_total_wall_time_for_a_finished_season():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 30, "seal": False,
                  "running": False, "paused": False, "active": False,
                  "status": "done", "elapsed_s": 3725.0, "mean_s": 124.0,
                  "weeks_measured": 30, "eta_s": None, "scored": True}])
    assert "total wall time 1:02:05" in html
    assert "mean 124 s per week over 30 timed" in html
    assert f'action="/retro/{SEASON}/stop"' not in html      # nothing to stop


def test_retro_index_calls_an_interrupted_season_interrupted():
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 30, "done": 3, "seal": False,
                  "running": False, "paused": False, "active": False,
                  "status": "interrupted", "elapsed_s": 600.0, "mean_s": 200.0,
                  "weeks_measured": 3, "eta_s": None, "scored": False}])
    assert "interrupted" in html
    assert "· running" not in html


def test_season_page_carries_controls_and_timing():
    def render(prog):
        return srv.templates.env.get_template("retro_season.html").render(
            active="Retrospective", season=SEASON, heads={}, curve=[],
            states=[], weeks=[W1], week=W1, map_html="", n_weeks=1,
            score_error="", prog=prog)

    live = render({"status": "running", "active": True, "done": 3,
                   "total": 30, "elapsed_s": 3725.0, "mean_s": 60.0,
                   "weeks_measured": 3, "eta_s": 1620.0,
                   "slowest_week": W1, "slowest_s": 90.0})
    assert f'action="/retro/{SEASON}/pause"' in live
    assert f'action="/retro/{SEASON}/stop"' in live
    assert 'class="runbar"' in live and 'class="quip rquip"' in live

    held = render({"status": "paused", "active": True, "done": 3, "total": 30,
                   "elapsed_s": 3725.0, "mean_s": 60.0, "weeks_measured": 3,
                   "eta_s": None, "slowest_week": W1, "slowest_s": 90.0})
    assert f'action="/retro/{SEASON}/resume"' in held
    assert "Replay paused" in held

    over = render({"status": "done", "active": False, "done": 30, "total": 30,
                   "elapsed_s": 3725.0, "mean_s": 124.0, "weeks_measured": 30,
                   "eta_s": None, "slowest_week": W1, "slowest_s": 300.0})
    assert "Replay wall time 1:02:05" in over
    assert f"slowest week {W1} at 300 s" in over
    assert f'action="/retro/{SEASON}/stop"' not in over

    # the template must still render for a season with no record at all
    assert "Replay wall time" not in render(None)


# ------------------------------------------------------------------- quips

def test_quips_are_shared_and_in_voice():
    src = (Path(__file__).resolve().parents[1] / "ui" / "static"
           / "quips.js").read_text()
    quips = [ln.strip().strip(",").strip('"')
             for ln in src.split("window.FLUBNF_QUIPS = [")[1].split("];")[0]
             .splitlines()
             if ln.strip().startswith('"')]
    assert len(quips) >= 65                       # the original 50, plus more
    assert "teaching 10,000 particles to sneeze responsibly" in quips
    assert len(set(quips)) == len(quips)          # no duplicates
    for q in quips:
        assert q == q.lower() or q[0].islower(), q
        assert "!" not in q, q
        assert q.isascii(), q                     # no emoji
        assert len(q) < 70, q
    # the replay voice actually arrived
    assert any("season" in q or "week" in q or "winter" in q for q in quips)


def test_both_run_pages_draw_from_the_shared_quip_list():
    fc = (Path(__file__).resolve().parents[1] / "ui" / "templates"
          / "forecast.html").read_text()
    rt = (Path(__file__).resolve().parents[1] / "ui" / "templates"
          / "retro.html").read_text()
    assert '/static/quips.js' in fc and '/static/quips.js' in rt
    assert "const quips=[" not in fc              # the inline copy is gone
    ticker = (Path(__file__).resolve().parents[1] / "ui" / "static"
              / "retro_progress.js").read_text()
    assert "flubnfQuips" in ticker
    # the paused card holds its quip still
    assert "st.quips.pause()" in ticker
