"""A season replay's live facts: what its card, its page and its clock say
while it runs, after it stops, and after the console that ran it is gone.

The card counts the live replay's own weeks beside a fuller sealed record;
a finished replay that gained weeks offers its one-click Resume; the page of
a running season renders from its caches with the live card instead of
starting a finalize job per visit; the title counts the weeks that scored;
and a dead worker's record reads 'interrupted' with its clock stopped.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd                                         # noqa: E402
import pytest                                               # noqa: E402
from fastapi.testclient import TestClient                   # noqa: E402

from app.core import playback, retro, scoring               # noqa: E402
from app.core import ttlcache                               # noqa: E402
from app.ui import server as srv                            # noqa: E402
from app.ui import retro_prep as ui_retro_prep              # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons        # noqa: E402
from app.ui import shared as ui_shared                      # noqa: E402
from app.ui.routes import retro as ui_retro                 # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL       # noqa: E402

client = TestClient(srv.app)

SEASON = "2025-26"          # in available_seasons, so the index lists it
W1, W2, W3 = "2025-11-01", "2025-11-08", "2025-11-15"
N2F = {"Ohio": "39", "Utah": "49"}
SETTINGS = {"season": SEASON, "scope": "custom", "locations": ["Ohio", "Utah"],
            "particles": 4000, "replicates": 2, "width": 3,
            "engine": "analogue"}


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """A controlled live root and seal, and every store a visit touches."""
    retro_before = dict(ui_retro_seasons._retro_status)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "seal")
    ui_retro_prep._results_jobs.clear()
    ui_shared._invalidate_scans()
    ttlcache.clear_all()
    yield
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(retro_before)
    ui_retro_prep._results_jobs.clear()
    ttlcache.clear_all()


def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 10):
            t[(fips, pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = base + k
    return t


def _weeks(root: Path, weeks) -> Path:
    """Groundhog samples for each week, centred on the truth."""
    truth = _truth()
    for asof in weeks:
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        an = {loc: {str(h): {str(L): truth[(fips, pd.Timestamp(asof)
                                             + pd.Timedelta(days=7 * h))]
                             + (L - 0.5) * 10 for L in QL}
                    for h in range(1, 5)}
              for loc, fips in N2F.items()}
        (wd / "samples.json").write_text(json.dumps({"asof": asof,
                                                     "analogue": an}))
    return root


def _stub_scoring(monkeypatch, tmp_path, unscored=()):
    """Synthetic truth and baselines, no hub; the weeks in `unscored` have
    no baseline round yet, so none of their cells score."""
    truth = _truth()
    for mod in (scoring, playback):
        monkeypatch.setattr(mod, "load_truth", lambda: (truth, dict(N2F)))
        monkeypatch.setattr(mod, "_baseline_cells",
                            lambda asof, fips_set, tr: {} if asof in unscored
                            else {(f, asof, h): 2.0 for f in fips_set
                                  for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")


def _baseline_round(hub: Path, asof: str):
    """The hub's FluSight-baseline file for the round of `asof`."""
    ref = (pd.Timestamp(asof) + pd.Timedelta(days=7)).date().isoformat()
    fp = hub / "model-output" / "FluSight-baseline" / f"{ref}-FluSight-baseline.csv"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("reference_date\n")


def _record(root: Path, status: str, **extra):
    root.mkdir(parents=True, exist_ok=True)
    meta = {"season": SEASON, "status": status, "total_weeks": 3,
            "elapsed_s": 20.0, "heartbeat_utc": time.time(),
            "settings": dict(SETTINGS)}
    meta.update(extra)
    retro.write_meta(root, meta)


def _ended_pid() -> int:
    """The pid of a process that has run and been reaped."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# ------------------------------------------------- RE-09: a dead worker

def test_a_record_whose_worker_process_ended_reads_interrupted_at_once():
    now = time.time()
    fresh = {"status": "running", "heartbeat_utc": now - 5,
             "segment_start_utc": now - 60, "elapsed_s": 0.0}
    # this process's own worker, and a record from before pids were kept,
    # are left to the heartbeat
    assert retro.effective_status({**fresh, "pid": os.getpid()}, now) == "running"
    assert retro.effective_status(fresh, now) == "running"
    # a console killed mid-replay: its pid is gone, so no 4-minute wait
    gone = {**fresh, "pid": _ended_pid()}
    assert retro.worker_gone(gone) is True
    assert retro.effective_status(gone, now) == "interrupted"
    # a live worker in another process (a CLI replay) still runs
    with subprocess.Popen([sys.executable, "-c",
                           "import time; time.sleep(30)"]) as p:
        try:
            alive = {**fresh, "pid": p.pid}
            assert retro.worker_gone(alive) is False
            assert retro.effective_status(alive, now) == "running"
        finally:
            p.kill()
    # settled statuses are never second-guessed
    assert retro.effective_status({**gone, "status": "done"}, now) == "done"


def test_a_season_started_here_records_this_process(tmp_path):
    retro._start_record(tmp_path, SEASON, 3, dict(SETTINGS))
    assert retro.read_meta(tmp_path)["pid"] == os.getpid()


def test_after_a_relaunch_the_dead_replay_frees_the_engine(tmp_path):
    root = ui_retro_seasons.RETRO_ROOT / SEASON
    _weeks(root, [W1])
    _record(root, "running", pid=_ended_pid(),
            segment_start_utc=time.time() - 30)
    assert ui_retro_seasons._season_status(SEASON) == "interrupted"
    p = client.get(f"/api/retro/progress?season={SEASON}").json()[SEASON]
    assert p["status"] == "interrupted" and p["eta_s"] is None
    assert client.get("/api/busy").json()["retro"] == {}


# ---------------------------------------------- RE-08: a stopped clock

def test_an_interrupted_replay_keeps_the_time_it_ran():
    hb = 1_000_000.0
    meta = {"status": "running", "elapsed_s": 20.0,
            "segment_start_utc": hb - 5, "heartbeat_utc": hb}
    later = hb + retro.HEARTBEAT_STALE_S + 600
    assert retro.effective_status(meta, now=later) == "interrupted"
    # 20 s before this segment, 5 s in it up to the last heartbeat; the
    # minutes since the worker died never count
    assert retro.elapsed_now(meta, now=later) == pytest.approx(25.0)
    assert retro.elapsed_now(meta, now=later + 3600) == pytest.approx(25.0)
    # a live run still counts up to now
    assert retro.elapsed_now(meta, now=hb + 10) == pytest.approx(35.0)


# ------------------------------------- RE-05: the live replay's own facts

def test_a_replay_over_a_sealed_season_counts_its_own_weeks(tmp_path):
    seal = ui_retro_seasons.RETRO_SEAL / SEASON
    _weeks(seal, [W1, W2, W3])
    _record(seal, "done", total_weeks=3)
    live = ui_retro_seasons.RETRO_ROOT / SEASON
    _weeks(live, [W1])
    _record(live, "running", pid=os.getpid(),
            week_seconds={W1: 10.0}, segment_start_utc=time.time())
    ui_retro_seasons._retro_status[SEASON] = "running"
    p = ui_retro_seasons._retro_progress(SEASON)
    assert p["done"] == 1 and p["eta_s"] is not None
    assert ui_retro_seasons._card_root(SEASON, "running") == (live, False)
    # stopped with weeks: still the live tree's card, not the seal's
    _record(live, "stopped")
    ui_retro_seasons._retro_status.pop(SEASON, None)
    assert ui_retro_seasons._card_root(SEASON, "stopped") == (live, False)
    html = client.get("/retro").text
    card = html[html.index(f'data-season="{SEASON}"'):]
    card = card[:card.index("</form>")] if "</form>" in card else card
    assert "1/" in card and "3/3" not in card
    # no live weeks: the seal speaks for the season
    shutil.rmtree(live)
    ttlcache.clear_all()
    assert ui_retro_seasons._card_root(SEASON, "")[0] == seal


# ---------------------------- RE-06: a finished replay that gained weeks

def test_a_finished_replay_that_gained_weeks_offers_its_resume(monkeypatch):
    live = ui_retro_seasons.RETRO_ROOT / SEASON
    _weeks(live, [W1, W2])
    _record(live, "done", total_weeks=2, finished_utc=time.time())
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2, W3])
    p = ui_retro_seasons._retro_progress(SEASON)
    assert p["status"] == "done" and p["added"] == [W3]
    html = client.get("/retro").text
    # the record's own settings, so nothing is re-entered by hand
    form = html.split('class="resume-run"', 1)[1].split("</form>", 1)[0]
    assert f'name="season" value="{SEASON}"' in form
    assert 'name="mode" value="resume"' in form
    assert 'name="custom_locations" value="Ohio"' in form
    assert 'name="national" value="0"' in form
    # nothing added: a finished replay offers no Resume
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    ttlcache.clear_all()
    assert 'class="resume-run"' not in client.get("/retro").text


# ------------------------- RE-03: the page of a season still replaying

def test_the_page_of_a_running_replay_shows_its_live_card(tmp_path,
                                                          monkeypatch):
    _stub_scoring(monkeypatch, tmp_path)
    live = ui_retro_seasons.RETRO_ROOT / SEASON
    _weeks(live, [W1, W2])
    for asof in (W1, W2):           # both weeks could score once finalized
        _baseline_round(tmp_path / "hub", asof)
    _record(live, "running", pid=os.getpid(),
            segment_start_utc=time.time())
    ui_retro_seasons._retro_status[SEASON] = "running"

    def no_job(*a, **kw):
        raise AssertionError("a finalize job started beside the replay")

    # no finalize job per visit: the worker finalizes at the end
    monkeypatch.setattr(ui_retro_prep, "_ensure_results_job", no_job)
    html = client.get(f"/retro/{SEASON}").text
    assert "preparing results" not in html
    assert "Replay in progress" in html
    # not scored yet is neither a failure nor truth still to come
    assert "Scoring failed" not in html
    assert "No scoreable weeks yet" not in html
    # a rescore waits for the replay too
    assert client.get(f"/retro/{SEASON}?rescore=1").status_code == 200


def test_a_replay_over_a_sealed_season_leaves_the_seals_page_whole(
        tmp_path, monkeypatch):
    """The page shows the seal while the fresh replay holds fewer weeks:
    it reads the seal as it always has, the replay running or not. A seal
    is never recomputed, so its finished job covers it: once its caches
    are fresh the page renders, never a 500 over the job's empty stamp."""
    _stub_scoring(monkeypatch, tmp_path)
    seal = ui_retro_seasons.RETRO_SEAL / SEASON
    _weeks(seal, [W1, W2, W3])
    _record(seal, "done", total_weeks=3)
    retro.finalize_season(seal, SEASON)
    agg = seal / "playback_cache" / "us_aggregate.json"
    agg.unlink(missing_ok=True)
    # a stale aggregate: the first visit makes the seal's job
    assert client.get(f"/retro/{SEASON}").status_code == 200
    assert ui_retro_prep._results_jobs[str(seal)]["inputs"] is None
    # the aggregate fresh again (an in-request build writes it): nothing
    # is pending, and the page asks whether a job covers the seal
    agg.parent.mkdir(parents=True, exist_ok=True)
    agg.write_text(json.dumps({"key": retro._national_cache_key(seal)}))
    ttlcache.clear_all()
    assert ui_retro_prep._results_pending(seal) == ""
    assert client.get(f"/retro/{SEASON}").status_code == 200
    live = ui_retro_seasons.RETRO_ROOT / SEASON
    _weeks(live, [W1])
    _record(live, "running", pid=os.getpid(),
            segment_start_utc=time.time())
    ui_retro_seasons._retro_status[SEASON] = "running"
    ttlcache.clear_all()
    r = client.get(f"/retro/{SEASON}")
    assert r.status_code == 200
    assert "Replay in progress" in r.text


# ----------------------------- RE-07: the title counts weeks that scored

def test_the_title_counts_the_weeks_that_scored(tmp_path, monkeypatch):
    _stub_scoring(monkeypatch, tmp_path, unscored=(W3,))
    root = _weeks(tmp_path / "tree" / SEASON, [W1, W2, W3])
    retro.finalize_season(root, SEASON)
    ctx = ui_retro.season_page_context(root, SEASON)
    assert ctx["score_error"] == "", ctx["score_error"]
    assert ctx["n_weeks"] == 2
    # a convention with no figures for the season scores no weeks
    ctx = ui_retro.season_page_context(root, SEASON, conv="pairwise")
    assert ctx["n_weeks"] == 0
