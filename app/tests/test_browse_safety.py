"""Browsing never touches a run: the GET-route audit, encoded as tests.

The audit (2026-08-21), for the record:

  * No GET route writes a STOP, PAUSE, or HALT flag, touches run_meta.json,
    or mutates the ledger. The stop and pause flags are written only by the
    POST endpoints (/run/stop, /retro/stop, /retro/{season}/stop, /pause)
    and cleared only by POST /retro/{season}/resume and the worker itself.
  * /api/busy and every page that derives a season status may reconcile the
    IN-MEMORY claim of a DEAD worker (stale heartbeat, or a record closed
    after the claim); they never write files and never touch a live claim,
    because a live worker's heartbeat is fresh by definition.
  * Four GET paths write, and each write is confined to a derived artifact
    a running worker never reads:
      - /output/report and /runs/{id}/report may rebuild a STALE report.html
        in place from its inputs bundle, via write-beside-then-os.replace
        (report_v2.build_report), touching nothing else. It cannot contend
        with a run's own report write: a running run's workroot is invisible
        to /output/report until results.json lands, which the run writes
        AFTER report.html, and a just-written report is fresher than the
        builder sources, so it serves verbatim. The rebuild runs at most
        once per builder change (failures are memoized), on the request
        thread, while fits run in separate low-priority OS processes, so it
        cannot starve a fit.
      - /retro/{season} may rescore scores.json (write-beside-then-replace,
        made atomic in this change) so a mid-replay page view and the
        worker's own final write can never hand anyone a half-written file.
      - /api/retro/{season}/playback/{asof} caches its payload under
        playback_cache/ only; a corrupt cache is detected and rebuilt.
      - /retro/{season}/report builds the season report file inside the
        season tree; the worker never reads it. (Its write is not atomic;
        that lives in report_season.py, outside this change, and a garbled
        file can only affect a concurrent download, never a run.)
  * The TTL caches (app/core/ttlcache.py) memoize read-only scans in
    process memory, keyed by the root they describe; they create nothing on
    disk (asserted below).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402
from fastapi.routing import APIRoute                # noqa: E402

import app.core.runs as runs_mod                    # noqa: E402
from app.core import playback                       # noqa: E402
from app.core import report_v2                      # noqa: E402
from app.core import retro                          # noqa: E402
from app.core import ttlcache                       # noqa: E402
from app.ui import server as srv                    # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL   # noqa: E402

client = TestClient(srv.app)

OLD_MTIME = (1_000_000_000, 1_000_000_000)          # 2001: always stale
FUTURE_MTIME = (4_000_000_000, 4_000_000_000)       # 2096: always fresh

RUNNING_SEASON = "2098-99"
PAUSED_SEASON = "2097-98"

#: how to fill each path parameter a GET route declares. A NEW parameter
#: name fails the walk on purpose: whoever adds the route must add it here
#: so the route stays covered.
PATH_PARAMS = {"run_id": "20981231T000000-abc123", "name": "pf",
               "season": RUNNING_SEASON, "asof": "2098-11-07"}


@pytest.fixture(autouse=True)
def _isolated_state():
    status_before = dict(srv._status)
    retro_before = dict(srv._retro_status)
    stop_before = set(srv._retro_stop)
    claim_before = dict(srv._retro_claim_at)
    ttlcache.clear_all()
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._retro_status.clear(); srv._retro_status.update(retro_before)
    srv._retro_stop.clear(); srv._retro_stop.update(stop_before)
    srv._retro_claim_at.clear(); srv._retro_claim_at.update(claim_before)
    ttlcache.clear_all()


# ------------------------------------------------------------ the GET walk

def _live_world(tmp_path, monkeypatch):
    """A simulated live application: one console run fitting (in-memory
    claim plus a workroot with a progress shard), one retrospective running
    (fresh-heartbeat record), one paused (record plus its PAUSE flag)."""
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "seal")
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    now = time.time()
    run_root = tmp_path / "retro" / RUNNING_SEASON
    retro.write_meta(run_root, {
        "season": RUNNING_SEASON, "status": "running", "heartbeat_utc": now,
        "segment_start_utc": now, "started_utc": now, "elapsed_s": 5.0,
        "total_weeks": 30, "weeks_completed": 0, "week_seconds": {},
        "settings": {"season": RUNNING_SEASON, "scope": "panel6",
                     "locations": ["Ohio"], "particles": 10_000,
                     "replicates": 3, "width": 4, "engine": "pf"}})
    pause_root = tmp_path / "retro" / PAUSED_SEASON
    retro.write_meta(pause_root, {
        "season": PAUSED_SEASON, "status": "paused", "heartbeat_utc": now,
        "segment_start_utc": None, "started_utc": now, "elapsed_s": 9.0,
        "total_weeks": 30, "weeks_completed": 1, "week_seconds": {}})
    retro.pause_path(pause_root).touch()
    srv._retro_status.update({RUNNING_SEASON: "running",
                              PAUSED_SEASON: "paused"})
    workroot = tmp_path / "console_workroot"
    workroot.mkdir()
    (workroot / "pf_status.json.prog").write_text(
        json.dumps({"done": 3, "total": 12, "t0": now}))
    srv._status.update({"running": "all:20981231T000000-abc123",
                        "workroot": str(workroot),
                        "run_label": "2098-12-26 · 1 state(s) + US",
                        "phase": "filtering 2 location(s) × 3 replicate(s)",
                        "started_utc": now, "expected_total": 12,
                        "settings": [("engine", "pf")]})
    ttlcache.clear_all()
    return run_root, pause_root, workroot


def _control_state(run_root, pause_root, workroot):
    """Everything a GET must leave alone: flags, records, claims."""
    def flags(root):
        return {"stop": retro.stop_path(root).exists(),
                "pause": retro.pause_path(root).exists(),
                "meta": retro.meta_path(root).read_bytes()}
    return {
        "running_season": flags(run_root),
        "paused_season": flags(pause_root),
        "console_stop": (workroot / "STOP").exists(),
        "console_files": sorted(p.name for p in workroot.iterdir()),
        "status": {k: srv._status.get(k)
                   for k in ("running", "workroot", "phase", "run_label",
                             "expected_total", "started_utc", "settings")},
        "retro_status": dict(srv._retro_status),
        "retro_stop": set(srv._retro_stop),
    }


def _get_routes():
    out = []
    for r in srv.app.router.routes:
        if isinstance(r, APIRoute) and "GET" in r.methods:
            out.append(r.path)
    return sorted(out)


def test_every_get_route_leaves_the_live_runs_alone(tmp_path, monkeypatch):
    run_root, pause_root, workroot = _live_world(tmp_path, monkeypatch)
    # fixture sanity: the simulated runs really read as live, so the null
    # result below means something
    b = client.get("/api/busy").json()
    assert b["console_run"] == "2098-12-26 · 1 state(s) + US"
    assert b["retro"] == {RUNNING_SEASON: "running",
                          PAUSED_SEASON: "paused"}
    before = _control_state(run_root, pause_root, workroot)
    walked = []
    for path in _get_routes():
        unknown = [p for p in re.findall(r"\{(\w+)\}", path)
                   if p not in PATH_PARAMS]
        assert not unknown, (f"route {path} declares parameter(s) {unknown} "
                             "not in PATH_PARAMS; add them so the "
                             "browse-safety walk keeps covering it")
        url = re.sub(r"\{(\w+)\}", lambda m: PATH_PARAMS[m.group(1)], path)
        r = client.get(url)
        assert r.status_code < 500, (url, r.status_code)
        walked.append(path)
        # the walk must never trip a flag mid-way either, not just at the end
        assert not retro.stop_path(run_root).exists(), url
        assert retro.pause_path(pause_root).exists(), url
    # the routes the audit cares most about were actually walked
    assert {"/", "/forecast", "/retro", "/api/busy", "/api/progress",
            "/output/report", "/retro/{season}",
            "/api/retro/{season}/playback/{asof}"} <= set(walked)
    after = _control_state(run_root, pause_root, workroot)
    assert after == before, "a GET route changed run control state"


# ------------------------------------------------------- TTL cache reads

def test_cached_scans_never_create_state(tmp_path):
    ghost = tmp_path / "ghost"
    assert srv._weeks_done(ghost / RUNNING_SEASON) == 0
    assert srv._scan_results(ghost / "workroots") == []
    assert srv._scan_archive_dates(ghost / "archive") == []
    assert srv._scan_archive_entries(ghost, RUNNING_SEASON) == []
    assert srv._seasons_on_disk(ghost) == ()
    assert not ghost.exists()


# -------------------------------------- weekly report rebuild confinement

def _synth_run(workroot: Path):
    """Drive the real report build path with synthetic samples (the same
    construction test_report_bundle uses), so the confinement assertions
    run against a genuine bundle and report."""
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(7)
    pf_samples = {loc: {str(h): (rng.gamma(5.0, 20.0, 400) + 10 * h).tolist()
                        for h in (1, 2, 3, 4)}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    srv._write_weekly_report(spec, workroot, pf_samples, obs,
                             pd.DataFrame(), locs, n2f, 42.0, {})


def test_stale_report_rebuild_writes_only_report_html(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    d = tmp_path / "archive" / "2098-01-03"
    _synth_run(d)
    srv._REPORT_REBUILD_FAILED.clear()
    os.utime(d / "report.html", OLD_MTIME)
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    srv._invalidate_scans()
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200
    # the rebuild happened: the stored file is fresh again
    assert (d / "report.html").stat().st_mtime >= \
        report_v2.builder_sources_mtime()
    after = {p.name: p.read_bytes() for p in d.iterdir()}
    # confined: no new files, no leftover .tmp, nothing else modified
    assert set(after) == set(before)
    assert not list(d.glob("*.tmp"))
    changed = {n for n in before if before[n] != after[n]}
    assert changed <= {"report.html"}
    assert after[report_v2.BUNDLE_NAME] == before[report_v2.BUNDLE_NAME]


def test_output_report_never_serves_an_unfinished_workroot(tmp_path,
                                                           monkeypatch):
    """The ordering that makes serve-time rebuilds unable to contend with a
    run's own report write: a workroot without results.json (the run is
    still inside step 5b/6) is invisible to /output/report, so its
    report.html is never read, rebuilt, or touched."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    done = tmp_path / "workroots" / "20980101T000000-aaaaaa"
    done.mkdir(parents=True)
    (done / "results.json").write_text(json.dumps(
        {"forecast_date": "2098-01-03", "models": {}, "observed": {}}))
    (done / "report.html").write_text("<html><body>DONE REPORT</body></html>")
    os.utime(done / "report.html", FUTURE_MTIME)     # fresh: verbatim serve
    live = tmp_path / "workroots" / "20980108T000000-bbbbbb"  # newer, mid-run
    live.mkdir(parents=True)
    (live / "report.html").write_text("<html><body>MID-RUN</body></html>")
    os.utime(live / "report.html", OLD_MTIME)        # stale on purpose
    before = ((live / "report.html").read_bytes(),
              (live / "report.html").stat().st_mtime)
    srv._invalidate_scans()
    r = client.get("/output/report")
    assert r.status_code == 200
    assert "DONE REPORT" in r.text
    assert "MID-RUN" not in r.text
    after = ((live / "report.html").read_bytes(),
             (live / "report.html").stat().st_mtime)
    assert after == before


# ------------------------------------------- playback payload confinement

ASOF = "2026-01-03"
PB_SEASON = "2025-26"
N2F = {"Ohio": "39", "Utah": "49"}


def _pb_truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0), ("US", 1000.0)):
        for k in range(-8, 6):
            d = pd.Timestamp(ASOF) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    return t, dict(N2F)


def test_playback_endpoint_writes_only_its_cache(tmp_path, monkeypatch):
    truth, n2f = _pb_truth()
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, n2f))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    root = tmp_path / PB_SEASON
    wd = root / "weeks" / ASOF
    wd.mkdir(parents=True)
    pf, an = {}, {}
    for loc, fips in N2F.items():
        pf[loc] = {str(h): [truth[(fips, pd.Timestamp(ASOF)
                                   + pd.Timedelta(days=7 * h))] + d
                            for d in (-1.0, 0.0, 1.0)] for h in range(5)}
        an[loc] = {str(h): {str(L): truth[(fips, pd.Timestamp(ASOF)
                                           + pd.Timedelta(days=7 * h))]
                            + (L - 0.5) * 10.0 for L in QL}
                   for h in range(1, 5)}
    (wd / "samples.json").write_text(json.dumps(
        {"asof": ASOF, "pf": pf, "analogue": an}))
    # the season reads as live while its payload is browsed
    retro.write_meta(root, {"season": PB_SEASON, "status": "running",
                            "heartbeat_utc": time.time(), "total_weeks": 30})
    ttlcache.clear_all()
    meta_before = retro.meta_path(root).read_bytes()
    files_before = {p for p in root.rglob("*") if p.is_file()}
    r = client.get(f"/api/retro/{PB_SEASON}/playback/{ASOF}")
    assert r.status_code == 200
    assert r.json()["asof"] == ASOF
    new = {p for p in root.rglob("*") if p.is_file()} - files_before
    assert new, "the payload cache should have been written"
    cache_dir = root / "playback_cache"
    assert all(cache_dir in p.parents for p in new), sorted(map(str, new))
    assert retro.meta_path(root).read_bytes() == meta_before
    assert not retro.stop_path(root).exists()
    assert not retro.pause_path(root).exists()


# ----------------------------------------------- scores.json atomic write

def test_retro_worker_writes_scores_atomically(tmp_path, monkeypatch):
    """The season worker's final scores.json lands by write-beside-then-
    replace, so a page rescoring or reading mid-write can never see a
    half-written file (the results page's own rescore uses the same
    pattern)."""
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    root = tmp_path / RUNNING_SEASON
    root.mkdir(parents=True)
    monkeypatch.setattr(retro, "run_season", lambda *a, **k: [])
    df = pd.DataFrame({"model": ["ensemble"], "wis": [1.0],
                       "base_wis": [2.0]})
    monkeypatch.setattr(retro, "score_season", lambda *a, **k: df)
    replaced = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append(str(dst))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    srv._retro_bg(RUNNING_SEASON, ["Ohio"], width=1)
    assert srv._retro_status[RUNNING_SEASON] == "done"
    assert json.loads((root / "scores.json").read_text())
    assert not (root / "scores.json.tmp").exists()
    assert any(d.endswith("scores.json") for d in replaced)
