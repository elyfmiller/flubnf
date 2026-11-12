"""A live Oracle replay shows progress inside its long weeks (UX package
P10, F57).

  * /api/retro/progress names the week in flight and its fits: the cell
    markers (failed fits counted, as the fit loop counts them) of the
    prepared cells (cells.json), for an active Oracle replay only. A week
    that failed earlier is not the week in flight unless the replay is
    back on it.
  * Before any week has been timed, a running Oracle replay has a first
    estimate from the engine's cost model over the weeks left (the fits
    already run taken off), never while paused or interrupted.
  * The ticker (retro_progress.js) reads "week <as-of> · 96 of 159 fits"
    and moves its bar by the fits, never back.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import estimates, retro, runner              # noqa: E402
from app.ui import retro_seasons as RS                     # noqa: E402
from app.ui import server as srv                           # noqa: E402
from app.ui import shared as ui_shared                     # noqa: E402

client = TestClient(srv.app)

TICKER_JS = Path(__file__).resolve().parents[1] / "ui" / "static" \
    / "retro_progress.js"
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
NODE = shutil.which("node")
needs_js = pytest.mark.skipif(
    not (JSC.is_file() or NODE),
    reason="no JavaScript engine (JavaScriptCore jsc or node)")

SEASON, START = "2098-99", "2098-08-01"
W0, W1, W2, W3 = "2098-10-03", "2098-10-10", "2098-10-17", "2098-10-24"
WEEKS = [W0, W1, W2, W3]
LOCS = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
        "California", "US"]
FIRST = "first estimate from the engine's cost model"


@pytest.fixture
def live(tmp_path, monkeypatch):
    """A live root holding SEASON's tree, the season's four weeks."""
    rr = tmp_path / "retro"
    monkeypatch.setattr(RS, "RETRO_ROOT", rr)
    monkeypatch.setattr(RS, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: list(WEEKS))
    before = dict(RS._retro_status)
    RS._retro_status.clear()
    ui_shared._invalidate_scans()
    yield rr / SEASON
    RS._retro_status.clear()
    RS._retro_status.update(before)
    ui_shared._invalidate_scans()


@pytest.fixture(params=["private", "public"])
def engine(request, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", request.param)
    return request.param


def _record(root: Path, status: str = "running", engine: str = "pf",
            **extra) -> None:
    root.mkdir(parents=True, exist_ok=True)
    retro.write_meta(root, {
        "season": SEASON, "status": status, "total_weeks": len(WEEKS),
        "elapsed_s": 60.0, "segment_start_utc": time.time(),
        "heartbeat_utc": time.time(), "pid": os.getpid(),
        "settings": {"season": SEASON, "engine": engine, "scope": "panel6",
                     "locations": LOCS, "replicates": 3,
                     "particles": 10_000, "width": 4},
        **extra})
    RS._retro_status[SEASON] = "running" if status == "running" else ""


def _stored(root: Path, asof: str, at: float | None = None) -> None:
    wd = root / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    sf = wd / "samples.json"
    sf.write_text(json.dumps({"asof": asof, "pf": {}}))
    if at is not None:
        os.utime(sf, (at, at))


def _prepared(root: Path, asof: str, cells: int, ok: int = 0,
              failed: int = 0, at: float | None = None) -> Path:
    """A week whose cells.json holds `cells` fits, `ok` and `failed` of them
    marked as the runner marks them."""
    wd = root / "weeks" / asof
    wd.mkdir(parents=True, exist_ok=True)
    keys = [f"Loc{i}_r0" for i in range(cells)]
    (wd / "cells.json").write_text(json.dumps(
        [{"key": k, "dir": str(wd / k)} for k in keys]))
    for k in keys[:ok]:
        retro.mark_cell_done(wd, k)
    for k in keys[ok:ok + failed]:
        retro.mark_cell_done(wd, k, status="FAIL: engine exited 1")
    if at is not None:
        for p in (wd, wd / retro.CELL_DONE_DIRNAME):
            if p.is_dir():
                os.utime(p, (at, at))
    return wd


def _progress() -> dict:
    ui_shared._invalidate_scans()
    return client.get(f"/api/retro/progress?season={SEASON}").json()[SEASON]


def _seeded_seconds(in_flight_left: int) -> float:
    """The cost model over the weeks left: the week in flight's fits not yet
    run, then W2 and W3 in full (7 locations x 3 Independent Runs)."""
    n = {w: estimates.n_obs_for(w, START) for w in WEEKS}
    return (estimates.run_seconds([n[W1]], in_flight_left, 10_000, 4)
            + estimates.run_seconds([n[W2]], 21, 10_000, 4)
            + estimates.run_seconds([n[W3]], 21, 10_000, 4))


# ------------------------------------------------ the week in flight

def test_the_week_in_flight_counts_its_fits_and_seeds_the_estimate(
        live, engine):
    """10 prepared cells, 4 marked (one of them failed), no samples: 4 of 10,
    and a first estimate before any week has been timed."""
    _record(live)
    _stored(live, W0)
    _prepared(live, W1, 10, ok=3, failed=1)
    p = _progress()
    assert (p["week_asof"], p["week_fits_done"], p["week_fits_total"]) == \
        (W1, 4, 10)
    assert p["done"] == 1 and p["weeks_measured"] == 0
    secs = _seeded_seconds(10 - 4)
    lo, hi = estimates.span(secs)
    assert (p["eta_lo_s"], p["eta_hi_s"]) == (lo, hi)
    assert p["eta_s"] == pytest.approx(secs * runner.K_FIRST)
    assert lo < p["eta_s"] < hi
    assert p["eta_basis"] == FIRST
    # more fits in: less left
    wd = live / "weeks" / W1
    for k in ("Loc4_r0", "Loc5_r0"):
        retro.mark_cell_done(wd, k)
    q = _progress()
    assert q["week_fits_done"] == 6
    assert q["eta_hi_s"] < p["eta_hi_s"]


def test_a_week_still_being_prepared_has_no_fits_yet(live):
    _record(live)
    (live / "weeks" / W0).mkdir(parents=True)
    p = _progress()
    assert (p["week_asof"], p["week_fits_done"], p["week_fits_total"]) == \
        (W0, 0, 0)
    # a re-prepared week (another count) is read again
    _prepared(live, W0, 10, ok=2)
    assert _progress()["week_fits_total"] == 10
    time.sleep(0.01)
    _prepared(live, W0, 12, ok=2)
    assert _progress()["week_fits_total"] == 12


def test_a_failed_earlier_week_is_not_the_week_in_flight(live):
    """A week that failed keeps its prepared folder unstored: between weeks
    (nothing touched since the newest stored week) there is no week in
    flight; once the replay is back on it, it is."""
    now = time.time()
    _record(live)
    _prepared(live, W0, 10, failed=10, at=now - 300)
    _stored(live, W1, at=now - 200)
    p = _progress()
    assert p["week_asof"] is None and p["week_fits_total"] is None
    # the next week starts: it is the one in flight
    _prepared(live, W2, 8, ok=1, at=now - 100)
    assert _progress()["week_asof"] == W2
    # a resume goes back to the failed week: its markers move
    os.utime(live / "weeks" / W0 / retro.CELL_DONE_DIRNAME, (now, now))
    p = _progress()
    assert (p["week_asof"], p["week_fits_done"]) == (W0, 10)


def test_paused_or_interrupted_has_no_first_estimate(live):
    _record(live, status="paused")
    RS._retro_status[SEASON] = "running"
    _prepared(live, W0, 10, ok=4)
    p = _progress()
    assert p["status"] == "paused"
    # paused is still active: its week and fits show, held
    assert (p["week_fits_done"], p["week_fits_total"]) == (4, 10)
    assert p["eta_s"] is None and p["eta_lo_s"] is None
    assert p["eta_basis"] is None
    # a dead worker: interrupted, nothing live
    from test_retro_live_progress import _ended_pid
    _record(live, pid=_ended_pid())
    p = _progress()
    assert p["status"] == "interrupted"
    assert p["eta_s"] is None and p["week_asof"] is None


def test_a_groundhog_only_replay_has_no_fits_and_no_seed(live):
    _record(live, engine="analogue")
    (live / "weeks" / W0).mkdir(parents=True)
    p = _progress()
    assert p["status"] == "running"
    assert p["week_asof"] is None and p["week_fits_total"] is None
    assert p["eta_s"] is None


def test_a_timed_week_hands_over_to_the_measured_estimate(live):
    _record(live, week_seconds={W0: 600.0})
    _stored(live, W0)
    _prepared(live, W1, 10, ok=2)
    p = _progress()
    assert p["eta_s"] is not None
    assert not p["eta_basis"].startswith("first estimate")


def test_a_recorded_pace_here_tightens_the_first_estimate(live, tmp_path):
    """With this computer's timed replays on record, both ends are the
    model times that pace, and the basis says so."""
    old = RS.RETRO_ROOT / f"2097-98{retro.ARCHIVE_SEP}20980101T000000Z"
    old.mkdir(parents=True)
    w = "2097-11-01"
    model = estimates.run_seconds([estimates.n_obs_for(w, "2097-08-01")],
                                  21, 10_000, 4, "private")
    retro.write_meta(old, {"season": "2097-98", "status": "done",
                           "settings": {"engine": "pf", "locations": LOCS,
                                        "replicates": 3, "particles": 10_000,
                                        "width": 4},
                           "week_seconds": {w: 1.5 * model}})
    _record(live)
    _prepared(live, W0, 10, ok=4)
    p = _progress()
    ratio, n = RS._own_cost_ratio()
    assert (ratio, n) == (1.5, 1)
    secs = (estimates.run_seconds([estimates.n_obs_for(W0, START)], 6,
                                  10_000, 4)
            + sum(estimates.run_seconds([estimates.n_obs_for(x, START)], 21,
                                        10_000, 4) for x in WEEKS[1:]))
    assert p["eta_lo_s"] == p["eta_hi_s"] == estimates.span(secs, 1.5)[0]
    assert p["eta_s"] == pytest.approx(1.5 * secs)
    assert p["eta_basis"] == FIRST + " and this computer's earlier replays"


def test_archived_progress_has_the_same_shape(live):
    _record(live, status="done")
    a = RS._archive_progress(live, SEASON)
    assert {"week_asof", "week_fits_done", "week_fits_total"} <= set(a)
    assert a["week_asof"] is None


# ------------------------------------------------------- the ticker

def _js(tmp_path, body: str):
    drv = tmp_path / "driver.js"
    drv.write_text(body, encoding="utf-8")
    if JSC.is_file():
        cmd = [str(JSC), str(TICKER_JS), str(drv)]
    else:
        both = tmp_path / "both.js"
        both.write_text("var print = function(s){ console.log(s); };\n"
                        + TICKER_JS.read_text(encoding="utf-8") + "\n"
                        + body, encoding="utf-8")
        cmd = [NODE, str(both)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_js
def test_the_readout_names_the_week_and_its_fits(tmp_path):
    got = _js(tmp_path, """
      var R = FluBNFRetroTicker._internals.readout, none = {lo: null, hi: null};
      var d = {status: "running", done: 12, total: 32, elapsed_s: 3723, at: 0,
               week_asof: "2026-03-21", week_fits_done: 96,
               week_fits_total: 159};
      function plain(o) { var c = {}; for (var k in o) c[k] = o[k]; return c; }
      var prep = plain(d); prep.week_fits_done = 0; prep.week_fits_total = 0;
      var old = plain(d); delete old.week_asof; delete old.week_fits_done;
      delete old.week_fits_total;
      var paused = plain(d); paused.status = "paused";
      print(JSON.stringify({
        fits: R(d, 0, 0, none),
        held: R(d, 60, 0, none),
        prep: R(prep, 0, 0, none),
        old: R(old, 0, 0, none),
        eta: R(d, 0, 10000, {lo: 3 * 3600, hi: 4 * 3600, etaAt: 0}),
        paused: R(paused, 0, 10000, {lo: 3600, hi: 7200, etaAt: 0})}));
    """)
    pct = 100 * (12 + 96 / 159) / 32
    assert got["fits"]["pct"] == pytest.approx(pct)
    # the date's hyphens do not break on a phone (a word joiner after each)
    assert got["fits"]["line"] == ("39% · 12/32 weeks · week 2026-\u206003"
                                   "-\u206021 · 96 of 159 fits · 1:02:03 "
                                   "elapsed")
    assert got["fits"]["count"] == "12/32 weeks"
    # the bar never moves back
    assert got["held"]["pct"] == 60
    # no prepared cells yet, or a payload without the week: weeks only
    assert got["prep"]["line"] == "38% · 12/32 weeks · 1:02:03 elapsed"
    assert got["old"]["line"] == got["prep"]["line"]
    # the ETA rides after it, decayed by the clock (10 s here)
    assert got["eta"]["line"].endswith(
        "96 of 159 fits · 1:02:13 elapsed · 3.0 to 4.0 h left")
    # paused: the clock and the ETA held
    assert got["paused"]["line"].endswith(
        "96 of 159 fits · 1:02:03 elapsed · paused")
    for r in got.values():
        assert "\u2013" not in r["line"] and "\u2014" not in r["line"]


@needs_js
def test_the_ticker_paints_the_fits_a_poll_brings(tmp_path):
    """init() on a fake card, one poll answered with a week in flight: the
    bar and the readout show its fits."""
    got = _js(tmp_path, """
      var els = {}, now = 1000;
      function elem() { return {style: {}, textContent: "", hidden: false}; }
      [".rquip", ".rfill", ".rstat", ".rt-stall", ".rbasis"].forEach(
        function (s) { els[s] = elem(); });
      var card = {dataset: {season: "2098-99", status: "running", done: "1",
                            total: "4", results: "1"},
                  querySelector: function (s) { return els[s] || null; },
                  querySelectorAll: function () { return []; }};
      document = {hidden: false, addEventListener: function () {},
                  querySelectorAll: function () { return [card]; }};
      setTimeout = function () { return 0; };
      clearTimeout = function () {};
      setInterval = function () { return 0; };
      Date.now = function () { return now; };
      var payload = {"2098-99": {status: "running", done: 1, total: 4,
        elapsed_s: 90, eta_lo_s: 600, eta_hi_s: 2400,
        eta_basis: "first estimate from the engine's cost model",
        weeks_measured: 0, week_asof: "2098-10-10", week_fits_done: 4,
        week_fits_total: 10}};
      fetch = function () {
        return Promise.resolve({json: function () { return payload; }}); };
      var api = FluBNFRetroTicker.init({});
      var before = {line: els[".rstat"].textContent,
                    width: els[".rfill"].style.width};
      Promise.resolve().then(function () {}).then(function () {})
        .then(function () {}).then(function () {}).then(function () {
          api.paint();
          print(JSON.stringify({before: before,
            line: els[".rstat"].textContent,
            width: els[".rfill"].style.width,
            basis: els[".rbasis"].textContent}));
        });
    """)
    assert got["before"]["line"] == "25% · 1/4 weeks"
    assert got["width"] == "35%"
    assert got["line"] == ("35% · 1/4 weeks · week 2098-\u206010-\u206010 · "
                           "4 of 10 fits · 0:01:30 elapsed · 10 to 40 min "
                           "left")
    assert got["basis"] == "first estimate from the engine's cost model"


def test_the_ticker_keeps_its_fallback_words():
    src = TICKER_JS.read_text(encoding="utf-8")
    assert "estimate arrives once the first week completes" in src
