"""The retrospective's remaining-time estimate.

The old ETA (global mean per week x weeks left, EMA-smoothed client-side)
froze for whole weeks: it only moved on week completion, rising week costs
cancelled the falling count, and the EMA resisted upward corrections. Each
week refits from the season start, so its cost climbs with the data it
covers, close to a straight line. The estimator fits that line to the run's
own weeks and prices every remaining week on it (a recorded ramp stands in
until eight weeks are in), credits time already spent in the week in
flight, and reports a range (withdrawn when it cannot be computed). The
replay tests drive the REAL recorded full-grid seasons through it.
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
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402

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
    before = dict(ui_retro_seasons._retro_status)
    yield
    ui_retro_seasons._retro_status.clear()
    ui_retro_seasons._retro_status.update(before)


# ------------------------------------------------------- the pure estimator

def test_estimate_needs_a_measured_week_and_a_remaining_one():
    assert ui_retro_seasons._eta_estimate([], [0.5]) is None
    assert ui_retro_seasons._eta_estimate([(0.0, 100.0)], []) is None


def test_estimate_follows_a_machine_that_slowed_down():
    # ten fast weeks then three slow ones: the machine is slow NOW
    measured = ([(i / 19, 100.0) for i in range(10)]
                + [(i / 19, 300.0) for i in range(10, 13)])
    remaining = [i / 19 for i in range(13, 20)]
    _, mid, _ = ui_retro_seasons._eta_estimate(measured, remaining)
    global_mean = (10 * 100.0 + 3 * 300.0) / 13
    assert mid > global_mean * 7          # above what the old estimator said


def test_remaining_weeks_are_priced_on_the_measured_climb():
    """Each week refits from the season start, so week k costs a + b*k: with
    eight weeks on a clean line, every remaining week is priced on it."""
    measured = [(i / 19, 200.0 + 13.0 * i) for i in range(8)]
    remaining = [i / 19 for i in range(8, 20)]
    lo, mid, hi = ui_retro_seasons._eta_estimate(measured, remaining)
    assert mid == pytest.approx(sum(200.0 + 13.0 * i for i in range(8, 20)))
    assert mid > 12 * sum(s for _, s in measured) / 8   # not the mean week
    # a clean line earns the tightest band there is
    assert lo == pytest.approx(0.92 * mid) and hi == pytest.approx(1.08 * mid)


def test_a_noisy_climb_widens_the_band():
    clean = [(i / 19, 200.0 + 13.0 * i) for i in range(10)]
    noisy = [(p, s * (1.25 if i % 2 else 0.8)) for i, (p, s) in enumerate(clean)]
    remaining = [i / 19 for i in range(10, 20)]
    lo1, mid1, hi1 = ui_retro_seasons._eta_estimate(clean, remaining)
    lo2, mid2, hi2 = ui_retro_seasons._eta_estimate(noisy, remaining)
    assert (hi2 - lo2) / mid2 > (hi1 - lo1) / mid1


def test_spent_seconds_inside_the_week_in_flight_are_credited():
    measured = [(i / 20, 600.0) for i in range(8)]
    remaining = [0.4, 0.45, 0.5]
    _, fresh, _ = ui_retro_seasons._eta_estimate(measured, remaining, spent_s=0.0)
    _, part, _ = ui_retro_seasons._eta_estimate(measured, remaining, spent_s=200.0)
    assert part == pytest.approx(fresh - 200.0)
    # the credit never exceeds one week, so a week running long cannot push
    # the estimate below the untouched weeks' cost
    _, over, _ = ui_retro_seasons._eta_estimate(measured, remaining, spent_s=5000.0)
    assert over == pytest.approx(fresh - 600.0)


def test_range_is_ordered_and_widens_when_little_is_measured():
    remaining = [0.5, 0.6, 0.7]
    lo1, mid1, hi1 = ui_retro_seasons._eta_estimate([(0.0, 600.0)], remaining)
    lo9, mid9, hi9 = ui_retro_seasons._eta_estimate(
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
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
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
    ui_retro_seasons._retro_status[SEASON] = "running"
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
    """The frozen-ETA regression: with no week completing, time spent in the
    week in flight lowers the estimate."""
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


def test_basis_names_the_weeks_and_the_prior(tmp_path, monkeypatch):
    _running_season(tmp_path, monkeypatch)
    p = _get()
    assert p["eta_basis"] == ("estimate from 2 completed weeks and the "
                              "recorded season ramp, until this run's own "
                              "climb takes over at 8 weeks")
    assert p["eta_lo_s"] < p["eta_s"] < p["eta_hi_s"]


def test_basis_names_the_runs_own_climb_once_eight_weeks_are_in(tmp_path,
                                                                 monkeypatch):
    root = _running_season(tmp_path, monkeypatch)
    for w in VINTAGES[2:8]:
        (root / "weeks" / w).mkdir(parents=True, exist_ok=True)
        (root / "weeks" / w / "samples.json").write_text("{}")
    m = retro.read_meta(root)
    m["week_seconds"] = {w: 100.0 + 10.0 * i for i, w in enumerate(VINTAGES[:8])}
    m["weeks_completed"], m["elapsed_s"] = 8, 1100.0
    retro.write_meta(root, m)
    p = _get()
    assert p["eta_basis"] == ("estimate from this run's 8 completed weeks, "
                              "priced on their week-by-week climb")


# ------------------------------------------- the replay, on the real seasons
# Per-week durations reconstructed from the sealed full-grid runs (earliest
# file mtime to samples.json mtime per week), frozen so this runs anywhere.
# Between-week overhead there was ~23.5 s.

REAL_2324 = [199.9, 204.3, 218.6, 218.0, 234.8, 253.7, 257.5, 274.8, 285.0,
             297.9, 307.8, 322.0, 337.9, 349.8, 374.4, 377.0, 396.6, 414.3,
             425.4, 428.7, 459.9, 448.7, 475.9, 474.3, 488.2, 507.4, 512.8,
             546.8, 559.9, 547.0, 605.5, 607.1]
REAL_2425 = [320.0, 318.4, 348.7, 379.1, 399.5, 398.3, 424.4, 432.4, 450.9,
             453.5, 467.9, 477.7, 493.4, 506.4, 518.5, 541.4, 555.8, 577.8,
             577.8, 597.7, 602.5, 646.9, 651.1, 664.4, 681.6, 674.9, 702.6]
GAP = 23.5


def _replay(durs):
    """The estimator at every week-completion instant, against the frozen
    one (mean week x weeks left). Returns (old MAE, new MAE, coverage of the
    truth by the range, mean half-width of the range as a fraction)."""
    n = len(durs)
    errs_old, errs_new, hits, widths = [], [], 0, []
    for k in range(1, n):
        actual = sum(durs[k:]) + GAP * (n - k)
        old = (sum(durs[:k]) / k) * (n - k)
        lo, mid, hi = ui_retro_seasons._eta_estimate(
            [(i / (n - 1), durs[i]) for i in range(k)],
            [i / (n - 1) for i in range(k, n)], overhead_s=GAP)
        errs_old.append(abs(old - actual))
        errs_new.append(abs(mid - actual))
        hits += (lo <= actual <= hi)
        widths.append((hi - lo) / 2 / mid)
    return (sum(errs_old) / len(errs_old), sum(errs_new) / len(errs_new),
            hits / (n - 1), sum(widths) / len(widths))


def test_replay_of_the_real_seasons():
    """Both recorded seasons replayed week by week. The previous estimator
    (a recorded ramp at the recent level, no fit) averaged 9.6 and 10.4 min
    off with a +/-35% band; pricing the run's own climb brings that to about
    7 and 8 min with a +/-15% band that still holds the truth every time."""
    for durs, mae_cap in ((REAL_2425, 7.5 * 60), (REAL_2324, 8.5 * 60)):
        mae_old, mae_new, coverage, width = _replay(durs)
        assert mae_old > 45 * 60              # the frozen one was ~50 min off
        assert mae_new < mae_cap
        assert coverage >= 0.9                # the stated range is honest
        assert width < 0.16                   # and far tighter than +/-35%


def test_ten_weeks_in_the_estimate_is_within_twelve_minutes():
    """About three hours still to run on either season: within 6%."""
    for durs in (REAL_2425, REAL_2324):
        n = len(durs)
        actual = sum(durs[10:]) + GAP * (n - 10)
        lo, mid, hi = ui_retro_seasons._eta_estimate(
            [(i / (n - 1), durs[i]) for i in range(10)],
            [i / (n - 1) for i in range(10, n)], overhead_s=GAP)
        assert abs(mid - actual) < 12 * 60
        assert lo <= actual <= hi


# ------------------------------------------------------- the client ticker

def test_ticker_no_longer_smooths_or_resists_the_server():
    """No EMA or upward-correction counter: the ticker shows the range sent."""
    assert "st.ema" not in TICKER_SRC and "0.3 *" not in TICKER_SRC
    assert "st.up" not in TICKER_SRC and "st.shown" not in TICKER_SRC
    assert "eta_lo_s" in TICKER_SRC and "eta_hi_s" in TICKER_SRC
    # the basis line prefers the server's statement, or says there is none
    assert "eta_basis" in TICKER_SRC
    assert "estimate arrives once the first week completes" in TICKER_SRC


def test_ticker_updates_every_element_that_states_progress():
    """Every element stating progress is driven by the ticker (every .rcount),
    so a card never shows two counts; a live card shows only the run bar's."""
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
    assert '<span class="rcount" hidden>10/32 weeks</span>' in html
    assert html.count("10/32 weeks") == 2              # .rstat shown, .rcount hidden


def test_ticker_freezes_honestly_when_polls_stop_arriving():
    """After 3 failed polls the clock and ETA freeze at their last-good values
    and say the connection is lost; a successful poll clears it."""
    assert "Connection lost. Numbers paused." in TICKER_SRC
    assert "fails = 0; stalled = false" in TICKER_SRC
    assert "stalled = true; stallAt = Date.now()" in TICKER_SRC
    assert "var now = stalled ? stallAt : Date.now()" in TICKER_SRC
    # the forecast run card follows the same rule for its elapsed clock
    fc_html = (Path(__file__).resolve().parents[1] / "ui" / "templates"
               / "forecast.html").read_text(encoding="utf-8")
    assert "++FAILS===3" in fc_html


def test_reload_yields_to_the_guard_modal_and_a_focused_form():
    """Reloads wait while the guard modal is open or focus is in a form (so a
    half-marked checklist survives); the ticker keeps polling either way."""
    retro_html = (Path(__file__).resolve().parents[1] / "ui" / "templates"
                  / "retro.html").read_text(encoding="utf-8")
    assert "GUARD_BUSY" in retro_html
    assert "document.activeElement.form" in retro_html


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
