"""Results preparation off the request path, and the startup-freeze fixes.

Four behaviors, all field-driven (laptop, 2026-08-22):

  * the season worker finalizes BEFORE marking done -- scores, the US
    national aggregate, and warmed playback caches, timed into run_meta --
    so the results page after a finished replay is a cache read;
  * a results-page visit that still finds stale caches starts ONE shared
    background job and shows a live preparing state polled from a status
    endpoint, never a frozen request; small seasons finish inside the grace
    wait and render complete in one round trip, and an unsettled-truth
    season never loops (a completed job covering the same inputs is
    believed);
  * the console CLI and the server import no longer pay for pandas/scipy
    or the engine-venv version probe before the window can open: the CLI's
    science imports are lazy, and VERSIONS resolves on a background thread
    (pages fill in via /api/versions);
  * the fluid type scale keeps growing past the old ~1800px ceilings while
    900px renders exactly as before.
"""
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient                  # noqa: E402

from app.core import playback, retro, scoring              # noqa: E402
from app.ui import server as srv                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

client = TestClient(srv.app)

SEASON = "2098-99"
W1, W2 = "2098-01-03", "2098-01-10"
N2F = {"Ohio": "39", "Utah": "49"}
WEIGHTS = {"pf": 0.5, "analogue": 0.5}


# ------------------------------------------------------------------ fixtures

def _truth():
    t = {}
    for fips, base in (("39", 100.0), ("49", 50.0)):
        for k in range(-8, 8):
            d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
            t[(fips, d)] = base + k
    for k in range(-8, 8):
        t[("US", pd.Timestamp(W1) + pd.Timedelta(days=7 * k))] = 150.0
    return t


def _mk_tree(tmp_path, weeks=(W1, W2)) -> Path:
    root = tmp_path / SEASON
    for asof in weeks:
        wd = root / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        truth = _truth()
        pf, an = {}, {}
        for loc, fips in N2F.items():
            pf[loc] = {str(h): [truth[(fips, pd.Timestamp(asof)
                                       + pd.Timedelta(days=7 * h))] + d
                                for d in (-1.0, 0.0, 1.0)] for h in range(5)}
            an[loc] = {str(h): {str(L): truth[(fips, pd.Timestamp(asof)
                                               + pd.Timedelta(days=7 * h))]
                                + (L - 0.5) * 10 for L in QL}
                       for h in range(1, 5)}
        (wd / "samples.json").write_text(
            json.dumps({"asof": asof, "pf": pf, "analogue": an}))
    return root


@pytest.fixture
def _stubbed(monkeypatch, tmp_path):
    """Synthetic truth and baselines for BOTH scoring surfaces (score_season
    reads scoring.*, playback reads its own rebinds), no hub."""
    truth = _truth()
    monkeypatch.setattr(scoring, "load_truth", lambda: (truth, dict(N2F)))
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, dict(N2F)))
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    return truth


@pytest.fixture
def _routed(monkeypatch, tmp_path):
    """Point the app at a controlled retro root and forget every job."""
    rr = tmp_path / "retro"
    rr.mkdir(exist_ok=True)
    monkeypatch.setattr(srv, "RETRO_ROOT", rr)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    srv._results_jobs.clear()
    srv._invalidate_scans()
    yield rr
    srv._results_jobs.clear()


# ------------------------------------------- finalize_season, the one job

def test_finalize_builds_every_cache_and_times_each_phase(tmp_path, _stubbed):
    root = _mk_tree(tmp_path)
    phases = []
    sec = retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS,
                                phase_cb=phases.append)
    assert phases == list(retro.FINALIZE_PHASES)
    for k in ("scoring", "national", "playback", "total"):
        assert k in sec and sec[k] >= 0.0, k
    # scores.json: real rows through the frozen formula
    df = pd.read_json(root / "scores.json")
    assert "model" in df.columns and len(df)
    # the national aggregate cache, valid for the tree as it stands
    assert (root / "playback_cache" / "us_aggregate.json").is_file()
    assert retro.national_aggregate_fresh(root, WEIGHTS)
    # every week's playback payload warmed
    for w in (W1, W2):
        assert (root / "playback_cache" / f"{w}.json").is_file(), w
    assert retro.scores_current(root) and retro.scores_scoreable(root)


def test_finalize_skips_scoring_when_current_unless_forced(tmp_path,
                                                           _stubbed,
                                                           monkeypatch):
    root = _mk_tree(tmp_path)
    retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS)
    calls = []
    real = retro.score_season
    monkeypatch.setattr(retro, "score_season",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    # current and scoreable: the aggregate-only path must not pay a rescore
    sec = retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS)
    assert not calls and "scoring" not in sec
    # the explicit-rescore path still forces it
    retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS, force=True)
    assert calls


def test_record_finalize_lands_in_run_meta(tmp_path):
    root = tmp_path / SEASON
    retro.write_meta(root, {"status": "done", "elapsed_s": 10.0})
    retro.record_finalize(root, {"scoring": 4.0, "national": 2.0,
                                 "playback": 1.0, "total": 7.0})
    m = retro.read_meta(root)
    assert m["finalize_seconds"]["total"] == 7.0
    assert m["elapsed_s"] == 10.0          # nothing else touched


def test_freshness_helpers_read_the_tree_honestly(tmp_path, _stubbed):
    root = _mk_tree(tmp_path)
    assert not retro.scores_current(root)              # never scored
    assert not retro.national_aggregate_fresh(root, WEIGHTS)
    retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS)
    assert retro.scores_current(root)
    # a new week staled everything
    import os
    sp = root / "weeks" / W1 / "samples.json"
    later = time.time() + 60
    os.utime(sp, (later, later))
    assert not retro.scores_current(root)
    assert not retro.national_aggregate_fresh(root, WEIGHTS)


# ------------------------------------------ the worker finalizes before done

def test_season_worker_finalizes_and_records_before_done(tmp_path, _stubbed,
                                                         _routed, monkeypatch):
    root = _routed / SEASON
    _mk_tree(_routed)
    monkeypatch.setattr(retro, "run_season", lambda *a, **k: [])
    srv._retro_bg(SEASON, ["Ohio"], width=1)
    assert srv._retro_status[SEASON] == "done"
    assert retro.scores_scoreable(root)
    assert retro.national_aggregate_fresh(root, WEIGHTS)
    m = retro.read_meta(root)
    assert "finalize_seconds" in m and m["finalize_seconds"]["total"] >= 0.0


# --------------------------------------- the page: grace, preparing, status

def test_small_season_first_visit_renders_complete_in_one_round_trip(
        tmp_path, _stubbed, _routed):
    _mk_tree(_routed)
    html = client.get(f"/retro/{SEASON}").text
    assert "preparing results" not in html
    assert "weeks scored" in html
    assert "Download season report" in html


def test_slow_job_shows_the_preparing_state_and_status_endpoint(
        tmp_path, _stubbed, _routed, monkeypatch):
    _mk_tree(_routed)
    hold = threading.Event()

    def _slow(root, season, ensemble_weights=None, phase_cb=None,
              force=False):
        if phase_cb:
            phase_cb("scoring cells")
        hold.wait(10)
        return {"total": 0.0}

    monkeypatch.setattr(retro, "finalize_season", _slow)
    monkeypatch.setattr(srv, "_RESULTS_GRACE_S", 0.05)
    try:
        html = client.get(f"/retro/{SEASON}").text
        # the preparing card, its live phase, and the poll wiring
        assert "preparing results" in html
        assert "scoring cells" in html
        assert f"/api/retro/{SEASON}/results_status" in html
        assert "location.reload()" in html
        # nothing heavy rendered behind it
        assert "Download season report" not in html
        st = client.get(f"/api/retro/{SEASON}/results_status").json()
        assert st["pending"] is True and st["phase"] == "scoring cells"
        assert st["elapsed_s"] >= 0.0
    finally:
        hold.set()
    job = srv._results_jobs[str(_routed / SEASON)]
    assert job["done"].wait(5)
    st = client.get(f"/api/retro/{SEASON}/results_status").json()
    assert st["pending"] is False


def test_one_job_per_root_even_under_concurrent_visits(tmp_path, _stubbed,
                                                       _routed, monkeypatch):
    _mk_tree(_routed)
    starts = []
    hold = threading.Event()

    def _slow(root, season, ensemble_weights=None, phase_cb=None,
              force=False):
        starts.append(1)
        hold.wait(10)
        return {"total": 0.0}

    monkeypatch.setattr(retro, "finalize_season", _slow)
    monkeypatch.setattr(srv, "_RESULTS_GRACE_S", 0.05)
    try:
        client.get(f"/retro/{SEASON}")
        client.get(f"/retro/{SEASON}")
        client.get(f"/retro/{SEASON}")
        assert len(starts) == 1
    finally:
        hold.set()
        srv._results_jobs[str(_routed / SEASON)]["done"].wait(5)


def test_unsettled_truth_never_loops(tmp_path, _routed, monkeypatch):
    """Zero scoreable cells: the first visit runs the job once; the covered
    job is then believed and later visits render the honest empty state
    without recomputing (the infinite preparing-reload loop this guards
    against)."""
    _mk_tree(_routed)
    # truth that never overlaps the season: everything scores to nothing
    monkeypatch.setattr(scoring, "load_truth", lambda: ({}, dict(N2F)))
    monkeypatch.setattr(playback, "load_truth", lambda: ({}, dict(N2F)))
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    calls = []
    real = retro.finalize_season
    monkeypatch.setattr(retro, "finalize_season",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    html1 = client.get(f"/retro/{SEASON}").text
    n_after_first = len(calls)
    assert n_after_first == 1
    html2 = client.get(f"/retro/{SEASON}").text
    assert len(calls) == n_after_first      # believed, not recomputed
    assert "preparing results" not in html2
    assert "No scoreable weeks yet" in html2 or "Scoring failed" in html2


def test_rescore_forces_a_fresh_job_over_current_scores(tmp_path, _stubbed,
                                                        _routed, monkeypatch):
    _mk_tree(_routed)
    client.get(f"/retro/{SEASON}")          # scored and cached
    forces = []
    real = retro.finalize_season

    def _spy(root, season, ensemble_weights=None, phase_cb=None, force=False):
        forces.append(force)
        return real(root, season, ensemble_weights=ensemble_weights,
                    phase_cb=phase_cb, force=force)

    monkeypatch.setattr(retro, "finalize_season", _spy)
    html = client.get(f"/retro/{SEASON}?rescore=1").text
    assert forces == [True]
    assert "weeks scored" in html           # finished inside the grace wait


def test_week_map_cards_cache_on_disk_and_are_reused(tmp_path, _stubbed,
                                                     _routed):
    """The season page's weekly map no longer re-parses the raw samples
    (~140 MB on a full-grid week) per view: the reduced cards cache under
    playback_cache/map_cards/, keyed by the samples mtime, and the report
    freshness glob (playback_cache/*.json) deliberately cannot see them."""
    import os
    root = _mk_tree(_routed)
    cards = srv._week_map_cards(root, W1)
    assert cards["39"]["name"] == "Ohio" and cards["39"]["probs"]
    cf = root / "playback_cache" / "map_cards" / f"{W1}.json"
    assert cf.is_file()
    # served from the cache while the mtime stands: a re-parse would raise
    sp = root / "weeks" / W1 / "samples.json"
    st = sp.stat()
    sp.write_text("not json")
    os.utime(sp, (st.st_atime, st.st_mtime))
    again = srv._week_map_cards(root, W1)
    assert again["39"]["probs"] == cards["39"]["probs"]
    # a changed mtime invalidates; the unparseable file then raises, which
    # is the honest failure (the tree is corrupt)
    os.utime(sp, (st.st_atime + 60, st.st_mtime + 60))
    with pytest.raises(Exception):
        srv._week_map_cards(root, W1)
    # warming another week's map cards is INVISIBLE to the report input
    # scan: the 25 MB export must not rebuild because a map was viewed
    from app.core import report_season
    newest0 = report_season._newest_input(root)
    srv._week_map_cards(root, W2)
    assert report_season._newest_input(root) == newest0


# ----------------------------------------- the export carries the aggregate

def test_season_report_carries_the_us_aggregate_with_the_honest_label(
        tmp_path, _stubbed, monkeypatch):
    from app.core import report_season
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    root = _mk_tree(tmp_path)
    retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS)
    html = report_season.build_season_report(root, SEASON).read_text()
    # the verdict tile, wearing the independence label
    assert "US (aggregated)" in html
    assert "aggregated from state forecasts" in html
    assert "states treated as independent" in html
    # the leading table row, in the console's own distinct class
    assert '<tr class="usagg"><td>US (aggregated)</td>' in html
    # the construction stated in full under the table
    assert "not a fitted national forecast" in html
    assert "vincentized 50/50" in html
    assert "aligned by draw index" in html
    # still self-contained
    assert "<script src" not in html and "fetch(" not in html


def test_unscored_report_states_the_aggregate_absence_never_invents_it(
        tmp_path, _stubbed, monkeypatch):
    """No figure is invented for an unscored season, and since 2026-08-23
    the absence is STATED in the artifact rather than left as a silent
    hole (the recurring exported-artifact failure class): no tile, no
    table row, no construction note, one plain sentence saying why."""
    from app.core import report_season
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    root = _mk_tree(tmp_path)                # weeks, never scored
    html = report_season.build_season_report(root, SEASON).read_text()
    assert 'class="tilename">US (aggregated)' not in html
    assert '<tr class="usagg">' not in html
    assert "not a fitted national forecast" not in html
    assert "is not in this export" in html
    assert "has not been scored" in html


def test_export_freshness_covers_the_aggregate_cache(tmp_path, _stubbed,
                                                     monkeypatch):
    """A report exported before the aggregate existed rebuilds once the
    cache lands: playback_cache/*.json is part of _newest_input."""
    import os
    from app.core import report_season
    monkeypatch.setattr(report_season, "_plotlyjs", lambda: "/* stub */")
    root = _mk_tree(tmp_path)
    p = report_season.build_season_report(root, SEASON)
    p.write_text("sentinel")
    future = p.stat().st_mtime + 60
    os.utime(p, (future, future))
    assert report_season.build_season_report(root, SEASON).read_text() \
        == "sentinel"                        # fresh: reused
    retro.finalize_season(root, SEASON, ensemble_weights=WEIGHTS)
    cf = root / "playback_cache" / "us_aggregate.json"
    os.utime(cf, (future + 60, future + 60))
    html = report_season.build_season_report(root, SEASON).read_text()
    assert html != "sentinel" and "US (aggregated)" in html


# --------------------------------------------------- startup: lazy and warm

def test_cli_import_stays_light():
    """`flubnf app` must not pay pandas/scipy before its window can open:
    importing the CLI module alone loads neither."""
    code = ("import sys; import flubnf.cli; "
            "sys.exit(2 if 'pandas' in sys.modules else "
            "3 if 'scipy' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=str(Path(__file__).resolve().parents[2]),
                       capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode()[-400:]


def test_cli_lazy_names_still_resolve():
    import flubnf.cli as cli
    assert len(cli.JURISDICTIONS) == 52
    assert cli.STATE_TO_ABBREV["Ohio"] == "OH"
    assert callable(cli.FluBNFConfig.load)


def test_versions_resolve_off_the_import_path_and_fill_in():
    # the dict exists at import with every key, resolved or pending
    assert set(srv._VERSION_KEYS) <= set(srv.VERSIONS)
    r = client.get("/api/versions").json()
    assert set(srv._VERSION_KEYS) <= set(r["versions"])
    assert isinstance(r["resolved"], bool)
    # the shell carries the fill-in: spans on home, the poller in the base
    html = client.get("/").text
    assert 'data-vkey="pybnf"' in html
    assert "/api/versions" in html


def test_server_import_does_not_block_on_the_engine_probe(tmp_path):
    """The regression itself (added 2026-08-19): the engine-venv subprocess
    ran at server import. With the engine python stubbed to hang, the import
    must still complete promptly -- the probe now runs on a background
    thread."""
    stub = tmp_path / "python"
    stub.write_text("#!/bin/sh\nsleep 30\n")
    stub.chmod(0o755)
    code = ("import time; t0=time.perf_counter(); import app.ui.server; "
            "print('%.1f' % (time.perf_counter()-t0))")
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=str(Path(__file__).resolve().parents[2]),
                       capture_output=True, text=True, timeout=60,
                       env={**__import__('os').environ,
                            "FLUBNF_PY_ENGINE": str(stub)})
    assert r.returncode == 0, r.stderr[-400:]
    assert float(r.stdout.strip().splitlines()[-1]) < 15.0


# --------------------------------------------------- the fluid type ceilings

def _clamp_px(css_text, token, width_px, root_px=16.0):
    m = re.search(re.escape(token)
                  + r":clamp\(([\d.]+)rem,([\d.]+)rem \+ ([\d.]+)vw,"
                  r"([\d.]+)rem\)", css_text)
    assert m, token
    lo, anchor, slope, hi = (float(g) for g in m.groups())
    v = anchor * root_px + slope / 100.0 * width_px
    return max(lo * root_px, min(v, hi * root_px))


def test_type_keeps_growing_past_1800_and_900_is_unchanged():
    css = (Path(__file__).resolve().parents[1]
           / "ui" / "static" / "nau.css").read_text()
    for tok, at900 in (("--fs-body", 14.63), ("--fs-h2", 13.32),
                       ("--fs-hint", 13.64), ("--fs-table", 13.96),
                       ("--fs-sub", 15.8), ("--fs-h1", 23.0)):
        a = _clamp_px(css, tok, 1280)
        b = _clamp_px(css, tok, 1800)
        c = _clamp_px(css, tok, 2200)
        assert a < b < c, (tok, a, b, c)     # monotone growth, no dead cap
        # 900px identical to the pre-change scale (anchor and slope frozen)
        assert abs(_clamp_px(css, tok, 900) - at900) < 0.05, tok
    # the A-/A/A+ control still multiplies: the rem anchor scales with root
    assert _clamp_px(css, "--fs-body", 2200, root_px=18.4) > \
        _clamp_px(css, "--fs-body", 2200, root_px=16.0)
