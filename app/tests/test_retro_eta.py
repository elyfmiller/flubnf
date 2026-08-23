"""The retrospective's remaining-time estimate, rebuilt after a field
failure: on a live 52-state replay the displayed ETA rose to ~3.3 h and then
did not move for over ninety minutes.

Three defects compounded. The server's estimate (global mean seconds per
week times weeks remaining) only changed when a week completed, so it held a
plateau for the whole of every ten-minute week; week cost climbs roughly
threefold through a season, so as slower weeks raised the mean, the falling
remaining count cancelled it and the plateau barely moved between weeks
either; and the client smoothed that flat value with an EMA that resisted
upward corrections, re-pinning the display to it every few polls.

The estimator here is recency-weighted, shaped by a completed same-scope
season's per-week cost profile, credited with the seconds already inside the
week in flight, and honest: a range instead of a point, withdrawn entirely
when it cannot be computed. The replay regression at the bottom drives the
REAL recorded full-grid seasons through both estimators and pins the
improvement, so the fix can never quietly regress to the frozen one.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                         # noqa: E402
from fastapi.testclient import TestClient             # noqa: E402

from app.core import retro                            # noqa: E402
from app.ui import server as srv                      # noqa: E402

client = TestClient(srv.app)

SEASON = "2097-98"
OTHER = "2096-97"
VINTAGES = [f"2097-11-{d:02d}" for d in range(1, 9)] + ["2097-12-01",
                                                        "2097-12-08"]
W1, W2, W3 = VINTAGES[0], VINTAGES[1], VINTAGES[2]

TICKER = Path(__file__).resolve().parents[1] / "ui" / "static" / "retro_progress.js"
TICKER_SRC = TICKER.read_text(encoding="utf-8")
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
needs_jsc = pytest.mark.skipif(not JSC.is_file(),
                               reason="JavaScriptCore jsc not available")


@pytest.fixture(autouse=True)
def _isolated_status():
    before = dict(srv._retro_status)
    yield
    srv._retro_status.clear()
    srv._retro_status.update(before)


# ------------------------------------------------------- the pure estimator

def test_estimate_needs_a_measured_week_and_a_remaining_one():
    assert srv._eta_estimate([], [0.5]) is None
    assert srv._eta_estimate([(0.0, 100.0)], []) is None


def test_estimate_is_recency_weighted_not_a_global_mean():
    # ten fast weeks then three slow ones: the machine is slow NOW, and the
    # estimate must say so instead of averaging the past away
    measured = ([(i / 19, 100.0) for i in range(10)]
                + [(i / 19, 300.0) for i in range(10, 13)])
    remaining = [i / 19 for i in range(13, 20)]
    _, mid, _ = srv._eta_estimate(measured, remaining)
    global_mean = (10 * 100.0 + 3 * 300.0) / 13
    assert mid > global_mean * 7          # above what the old estimator said
    assert mid > 200.0 * 7                # the recent slow weeks dominate


def test_profile_prices_the_remaining_weeks_not_the_average_week():
    # a season whose late weeks cost twice its early ones: with only early
    # weeks measured, the flat estimate under-prices what is left
    profile = tuple((i / 9, 0.5 + i / 9) for i in range(10))   # 0.5x -> 1.5x
    measured = [(i / 9, 100.0 * (0.5 + i / 9)) for i in range(3)]
    remaining = [i / 9 for i in range(3, 10)]
    _, flat, _ = srv._eta_estimate(measured, remaining)
    _, shaped, _ = srv._eta_estimate(measured, remaining, profile=profile)
    assert shaped > flat * 1.3            # the late-season climb is priced in


def test_spent_seconds_inside_the_week_in_flight_are_credited():
    measured = [(0.0, 600.0), (0.1, 600.0), (0.2, 600.0)]
    remaining = [0.3, 0.4, 0.5]
    _, fresh, _ = srv._eta_estimate(measured, remaining, spent_s=0.0)
    _, part, _ = srv._eta_estimate(measured, remaining, spent_s=200.0)
    assert part == pytest.approx(fresh - 200.0)
    # the credit never exceeds the week in flight: a week running long
    # cannot drive the estimate below the untouched weeks' cost
    _, over, _ = srv._eta_estimate(measured, remaining, spent_s=5000.0)
    assert over == pytest.approx(fresh - 600.0)


def test_range_is_ordered_and_widens_when_little_is_measured():
    remaining = [0.5, 0.6, 0.7]
    lo1, mid1, hi1 = srv._eta_estimate([(0.0, 600.0)], remaining)
    lo9, mid9, hi9 = srv._eta_estimate(
        [(i / 20, 600.0) for i in range(9)], remaining)
    assert lo1 < mid1 < hi1 and lo9 < mid9 < hi9
    assert (hi1 - lo1) / mid1 > (hi9 - lo9) / mid9
    # one measured week earns the widest band there is
    assert lo1 == pytest.approx(0.5 * mid1)
    assert hi1 == pytest.approx(1.5 * mid1)


# ---------------------------------------------- the endpoint, wired through

def _running_season(tmp_path, monkeypatch, scope="all", spent_age=None):
    """A live season two weeks in, week three in flight, over a monkeypatched
    vintage calendar so positions and the in-flight scan are exercised."""
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [OTHER, SEASON])
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: list(VINTAGES) if s == SEASON else [])
    root = tmp_path / SEASON
    for w in (W1, W2):
        (root / "weeks" / w).mkdir(parents=True)
        (root / "weeks" / w / "samples.json").write_text("{}")
    if spent_age is not None:
        wd = root / "weeks" / W3
        wd.mkdir(parents=True)
        f = wd / "cells.json"
        f.write_text("{}")
        t0 = time.time() - spent_age
        import os
        os.utime(f, (t0, t0))
    srv._retro_status[SEASON] = "running"
    retro.write_meta(root, {"status": "running", "total_weeks": len(VINTAGES),
                            "weeks_completed": 2, "elapsed_s": 240.0,
                            "segment_start_utc": None,
                            "settings": {"scope": scope, "season": SEASON},
                            "week_seconds": {W1: 100.0, W2: 140.0},
                            "heartbeat_utc": time.time()})
    return root


def _get(season=SEASON):
    return client.get(f"/api/retro/progress?season={season}").json()[season]


def test_estimate_moves_between_week_completions(tmp_path, monkeypatch):
    """The frozen-ETA regression itself: with NO new week completing, time
    passing inside the week in flight must lower the estimate. The old
    estimator held a plateau here for the whole of every week."""
    root = _running_season(tmp_path, monkeypatch, spent_age=10.0)
    p1 = _get()
    assert p1["eta_s"] is not None
    import os
    f = root / "weeks" / W3 / "cells.json"
    t0 = time.time() - 100.0
    os.utime(f, (t0, t0))
    p2 = _get()
    assert p2["eta_s"] == pytest.approx(p1["eta_s"] - 90.0, abs=5.0)
    assert p2["eta_lo_s"] < p2["eta_s"] < p2["eta_hi_s"]


def test_basis_names_the_weeks_and_the_profile(tmp_path, monkeypatch):
    _running_season(tmp_path, monkeypatch)
    other = tmp_path / OTHER
    other.mkdir(parents=True)
    retro.write_meta(other, {
        "status": "done", "settings": {"scope": "all", "season": OTHER},
        "week_seconds": {f"2096-11-{d:02d}": 100.0 + 20.0 * d
                         for d in range(1, 11)}})
    srv._profile_scan.cache_clear()
    p = _get()
    assert p["eta_basis"] == ("estimate from 2 completed weeks, weighted "
                              f"by the {OTHER} week profile")
    assert p["eta_lo_s"] < p["eta_s"] < p["eta_hi_s"]


def test_profile_must_match_the_location_scope(tmp_path, monkeypatch):
    _running_season(tmp_path, monkeypatch, scope="panel6")
    other = tmp_path / OTHER
    other.mkdir(parents=True)
    retro.write_meta(other, {           # an all-52 run: not this run's scope
        "status": "done", "settings": {"scope": "all", "season": OTHER},
        "week_seconds": {f"2096-11-{d:02d}": 100.0 + 20.0 * d
                         for d in range(1, 11)}})
    srv._profile_scan.cache_clear()
    p = _get()
    assert p["eta_basis"] == "estimate from 2 completed weeks"


def test_a_thin_record_cannot_serve_as_a_profile(tmp_path, monkeypatch):
    _running_season(tmp_path, monkeypatch)
    other = tmp_path / OTHER
    other.mkdir(parents=True)
    retro.write_meta(other, {           # three weeks carry no season shape
        "status": "done", "settings": {"scope": "all", "season": OTHER},
        "week_seconds": {f"2096-11-{d:02d}": 300.0 for d in range(1, 4)}})
    srv._profile_scan.cache_clear()
    p = _get()
    assert "weighted by" not in p["eta_basis"]


# ------------------------------------------- the replay, on the real seasons
#
# Per-week durations reconstructed from the sealed full-grid runs on the
# development machine (each week directory's earliest file mtime to its
# samples.json mtime), frozen here so the regression runs anywhere. The
# between-week overhead measured there was ~23.5 s.

REAL_2324 = [199.9, 204.3, 218.6, 218.0, 234.8, 253.7, 257.5, 274.8, 285.0,
             297.9, 307.8, 322.0, 337.9, 349.8, 374.4, 377.0, 396.6, 414.3,
             425.4, 428.7, 459.9, 448.7, 475.9, 474.3, 488.2, 507.4, 512.8,
             546.8, 559.9, 547.0, 605.5, 607.1]
REAL_2425 = [320.0, 318.4, 348.7, 379.1, 399.5, 398.3, 424.4, 432.4, 450.9,
             453.5, 467.9, 477.7, 493.4, 506.4, 518.5, 541.4, 555.8, 577.8,
             577.8, 597.7, 602.5, 646.9, 651.1, 664.4, 681.6, 674.9, 702.6]
GAP = 23.5


def _profile_points(durs):
    mean = sum(durs) / len(durs)
    n = len(durs)
    return tuple((i / (n - 1), d / mean) for i, d in enumerate(durs))


def _replay(durs, profile):
    """Both estimators at every week-completion instant. Returns each one's
    mean absolute error in seconds and the range's coverage of the truth."""
    n = len(durs)
    errs_old, errs_new, hits = [], [], 0
    for k in range(1, n):
        actual = sum(durs[k:]) + GAP * (n - k)
        old = (sum(durs[:k]) / k) * (n - k)
        lo, mid, hi = srv._eta_estimate(
            [(i / (n - 1), durs[i]) for i in range(k)],
            [i / (n - 1) for i in range(k, n)],
            profile=profile, overhead_s=GAP)
        errs_old.append(abs(old - actual))
        errs_new.append(abs(mid - actual))
        hits += (lo <= actual <= hi)
    return (sum(errs_old) / len(errs_old), sum(errs_new) / len(errs_new),
            hits / (n - 1))


def test_replay_of_the_real_seasons_beats_the_frozen_estimator():
    """The proof the rebuild is better, not an assertion: the real 2024-25
    full-grid run replayed week by week, with the real 2023-24 run as its
    same-scope profile, exactly as the server would use them."""
    mae_old, mae_new, coverage = _replay(REAL_2425, _profile_points(REAL_2324))
    assert mae_old > 45 * 60              # the old estimator was ~50 min off
    assert mae_new < 0.55 * mae_old       # the rebuild at least halves that
    assert mae_new < 30 * 60
    assert coverage >= 0.9                # and the stated range is honest
    # the reverse replay holds too: no season-pair cherry-picking
    mae_old2, mae_new2, coverage2 = _replay(REAL_2324,
                                            _profile_points(REAL_2425))
    assert mae_new2 < 0.55 * mae_old2
    assert coverage2 >= 0.9


def test_the_profile_is_what_moves_the_estimate_on_the_real_data():
    """Ten weeks into the real 2024-25 replay (the position the field report
    was filed from), the season profile shifts the estimate by over an hour
    toward the truth: the whole reason remaining weeks are priced by shape
    rather than by the current average."""
    n = len(REAL_2425)
    measured = [(i / (n - 1), REAL_2425[i]) for i in range(10)]
    remaining = [i / (n - 1) for i in range(10, n)]
    actual = sum(REAL_2425[10:]) + GAP * (n - 10)
    _, flat, _ = srv._eta_estimate(measured, remaining, overhead_s=GAP)
    _, shaped, _ = srv._eta_estimate(measured, remaining,
                                     profile=_profile_points(REAL_2324),
                                     overhead_s=GAP)
    assert shaped - flat > 3600.0
    assert abs(shaped - actual) < abs(flat - actual)


# ------------------------------------------------------- the client ticker

def test_ticker_no_longer_smooths_or_resists_the_server():
    """The EMA and its upward-correction counter are what pinned the display
    to a frozen server value; the ticker must take the range as sent."""
    assert "st.ema" not in TICKER_SRC and "0.3 *" not in TICKER_SRC
    assert "st.up" not in TICKER_SRC and "st.shown" not in TICKER_SRC
    assert "eta_lo_s" in TICKER_SRC and "eta_hi_s" in TICKER_SRC
    # the basis line prefers the server's own statement of what the
    # estimate rests on, and still says plainly when there is none yet
    assert "eta_basis" in TICKER_SRC
    assert "estimate arrives once the first week completes" in TICKER_SRC


def test_ticker_updates_every_element_that_states_progress():
    """One source of truth (field-found: a card whose headline read 10/32
    while the line under it still said 1/32): the ticker must drive every
    .rcount, and the index template must mark its secondary counter so."""
    assert ".rcount" in TICKER_SRC
    retro_html = (Path(__file__).resolve().parents[1] / "ui" / "templates"
                  / "retro.html").read_text(encoding="utf-8")
    assert 'class="rcount"' in retro_html
    html = srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[{"name": SEASON, "total": 32, "done": 10, "seal": False,
                  "running": True, "paused": False, "active": True,
                  "status": "running", "elapsed_s": 5945.0, "mean_s": 594.0,
                  "weeks_measured": 10, "eta_s": 9000.0, "scored": False}])
    assert '<span class="rcount">10/32 weeks</span>' in html


def _jsc(tmp_path, expr):
    drv = tmp_path / "driver.js"
    drv.write_text("var I = FluBNFRetroTicker._internals;\n"
                   "print(JSON.stringify((function(){ return "
                   + expr + "; })()));\n")
    out = subprocess.run([str(JSC), str(TICKER), str(drv)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_jsc
def test_eta_text_states_a_range_in_one_unit(tmp_path):
    assert _jsc(tmp_path, "I.etaText(11160, 14400)") == "3.1 to 4.0 h"
    assert _jsc(tmp_path, "I.etaText(700, 950)") == "12 to 16 min"
    # the unit follows the high end, so a range never mixes units
    assert _jsc(tmp_path, "I.etaText(4800, 6000)") == "1.3 to 1.7 h"


@needs_jsc
def test_eta_text_collapses_an_agreeing_range(tmp_path):
    assert _jsc(tmp_path, "I.etaText(11900, 12000)") == "~3.3 h"
    assert _jsc(tmp_path, "I.etaText(890, 910)") == "~15 min"


@needs_jsc
def test_eta_text_never_goes_negative(tmp_path):
    # a decayed range clamps at the floor instead of counting into debt
    assert _jsc(tmp_path, "I.etaText(-30, 70)") == "~1 min"
