"""Pins for the 2026-08-26 audit's confirmed defects.

Each test here exists because the audit found the behavior either broken or
unpinned; a regression on any of these reopens a published finding.
"""
import json

import numpy as np
import pandas as pd


def test_floor_adaptive_branch_ignores_anchored_origin():
    # The documented dead-week case: origin anchored at the last observed
    # value (nonzero), every FORECAST horizon flat zero, sporadic recent
    # background. The adaptive branch must fire; before the fix the origin's
    # anchored mass vetoed it and the submitted medians stayed 0.
    from app.core.floor import floor_samples
    samples = {"0": [2.0] * 200, "1": [0.0] * 200, "2": [0.0] * 200,
               "3": [0.0] * 200, "4": [0.0] * 200}
    out = floor_samples(samples, "Arkansas", "2026-07-04",
                        recent=[1.0, 1.0, 4.0, 0.0])
    med1 = float(np.median(np.asarray(out["1"], float)))
    assert med1 >= 1.0, (
        f"adaptive floor did not fire: h1 median {med1}; the origin's "
        "anchored mass is vetoing the collapse test again")


def test_floor_healthy_fit_untouched_by_adaptive_branch():
    # A healthy in-season fit must never trigger the adaptive rate.
    from app.core.floor import LAM, floor_samples
    samples = {"0": [50.0] * 200, "1": [60.0] * 200, "2": [70.0] * 200}
    out = floor_samples(samples, "Ohio", "2026-01-03",
                        recent=[40.0, 45.0, 50.0, 55.0])
    # Poisson(LAM=0.35) noise moves a median of 60 by at most a count or two
    assert abs(float(np.median(np.asarray(out["1"], float))) - 60.0) <= 3.0


def test_cells_failed_reads_marker_status(tmp_path):
    from app.core import retro
    retro.mark_cell_done(tmp_path, "Ohio_r0", "ok")
    retro.mark_cell_done(tmp_path, "Ohio_r1", "FAIL: netgen exploded")
    assert retro.cells_done(tmp_path) == {"Ohio_r0", "Ohio_r1"}
    failed = retro.cells_failed(tmp_path)
    assert set(failed) == {"Ohio_r1"}
    assert failed["Ohio_r1"].startswith("FAIL")


def test_latest_results_skips_research_runs(tmp_path, monkeypatch):
    from app.ui import server
    new = tmp_path / "20260826T120000" / "results.json"
    old = tmp_path / "20260825T120000" / "results.json"
    new.parent.mkdir(parents=True)
    old.parent.mkdir(parents=True)
    new.write_text(json.dumps({"research": True, "forecast_date": "x"}))
    old.write_text(json.dumps({"forecast_date": "y"}))
    monkeypatch.setattr(server, "_workroot_results", lambda: [new, old])
    rid, res = server._latest_results()
    assert rid == "20260825T120000", (
        "a research run's results leaked onto a shipped-product surface")
    assert res["forecast_date"] == "y"


def test_latest_results_recognises_pre_flag_research_specs(tmp_path,
                                                           monkeypatch):
    # results.json files written before the research flag existed carry only
    # the spec; the skip must recognise those too
    from app.ui import server
    f = tmp_path / "w" / "results.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({
        "forecast_date": "x",
        "spec": json.dumps({"extra": {"members": 3}})}))
    monkeypatch.setattr(server, "_workroot_results", lambda: [f])
    rid, res = server._latest_results()
    assert rid is None and res is None


def test_wis_card_discloses_the_cell_rule():
    from app.core import scoring
    df = pd.DataFrame({
        "location": ["Ohio", "Iowa"], "fips": ["39", "19"],
        "horizon": [1, 1], "wis": [10.0, 12.0], "base_wis": [20.0, 12.0],
        "rel": [0.5, 1.0]})
    html = scoring.summary_table_html(df)
    assert "A cell is scored when settled truth exists" in html
    assert "counts can differ" in html


def test_load_truth_records_its_source():
    from app.core import scoring
    scoring.load_truth()
    # on this machine the settled file exists; the marker must say so, and
    # exist at all (the fallback used to be recorded nowhere)
    assert scoring.TRUTH_SOURCE == "settled"


def test_retro_week_budget_never_below_fixed_floor():
    from app.core import retro
    from app.core.engines import pf as pf_engine
    tiny = [{"n_obs": 5, "particles": 1000}]
    assert max(retro.WEEK_TIMEOUT_S,
               pf_engine.budget_seconds(pf_engine.shard_cells(tiny, 4))) \
        >= retro.WEEK_TIMEOUT_S


def _fake_cell(tmp_path, n_obs, n_cols, k, last_observed=10.0):
    import numpy as np
    d = tmp_path / "cell"
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True, exist_ok=True)
    # two particles; column j holds the value j, so labels are decodable
    tr = np.tile(np.arange(n_cols, dtype=float), (2, 1))
    np.savetxt(runs / "x_traj_noise.txt", tr)
    cell = {"key": "Ohio_r0", "dir": str(d), "location": "Ohio",
            "n_obs": n_obs, "last_observed": last_observed,
            "weeks_dropped": k}
    (tmp_path / "cells.json").write_text(json.dumps([cell]))
    return tmp_path


def test_collect_zero_drop_unchanged(tmp_path):
    # n_obs=3, forecast 4: columns 0..6; origin col 2 -> scale 10/2 = 5
    from app.core.engines import pf as pf_engine
    wr = _fake_cell(tmp_path, n_obs=3, n_cols=7, k=0)
    d = pf_engine.collect(wr)["Ohio"]
    assert d["0"] == [10.0, 10.0]           # anchored origin, col 2 * 5
    assert d["1"] == [15.0, 15.0]           # col 3 * 5
    assert d["4"] == [30.0, 30.0]           # col 6 * 5


def test_collect_shifts_horizons_by_weeks_dropped(tmp_path):
    # k=1: conf extended the forecast to 5 steps -> 8 columns. The as-of
    # week is col 3 (the model's nowcast of the dropped week); horizon 1
    # is col 4. Before the fix, h=1 read col 3 and every label rode one
    # week early relative to the calendar it claimed.
    from app.core.engines import pf as pf_engine
    wr = _fake_cell(tmp_path, n_obs=3, n_cols=8, k=1)
    d = pf_engine.collect(wr)["Ohio"]
    assert d["0"] == [15.0, 15.0]           # col 3 * 5: nowcast of asof week
    assert d["1"] == [20.0, 20.0]           # col 4 * 5
    assert d["4"] == [35.0, 35.0]           # col 7 * 5


def test_collect_refuses_pre_fix_workroot_with_drop(tmp_path):
    # a trimmed run whose traj was NOT extended must fail loudly, never
    # silently relabel the wrong columns
    import pytest
    from app.core.engines import pf as pf_engine
    wr = _fake_cell(tmp_path, n_obs=3, n_cols=7, k=1)
    with pytest.raises(RuntimeError, match="horizon-alignment"):
        pf_engine.collect(wr)


def test_analogue_drop_moves_anchor_and_extends_span(tmp_path, monkeypatch):
    from app.core.engines import analogue as eng
    vintage = tmp_path / "v.csv"
    rows = ["date,location,location_name,value"]
    dates = pd.date_range("2025-12-06", periods=5, freq="7D")
    for d, val in zip(dates, [5, 6, 7, 8, 9]):
        rows.append(f"{d.date()},39,Ohio,{val}")
    vintage.write_text("\n".join(rows) + "\n")
    locs = tmp_path / "locations.csv"
    locs.write_text("location,location_name,abbreviation\n39,Ohio,OH\n")
    monkeypatch.setattr(eng, "vintage_path", lambda d: str(vintage))
    monkeypatch.setattr(eng, "LOCATIONS", str(locs))
    calls = []

    def fake_forecast(anchor, as_of, horizon, bank, levels, **kw):
        calls.append((anchor, str(as_of), horizon))
        return {0.5: anchor}

    monkeypatch.setattr(eng.AN, "forecast", fake_forecast)

    def spec(drop, same_day):
        return type("S", (), {"forecast_date": "2026-01-03",
                              "locations": ["Ohio"],
                              "weeks_to_drop": drop,
                              "drop_same_day": same_day})()

    eng.run(spec(0, False))
    assert calls[0] == (9.0, "2026-01-03", 1)      # historical path exact
    calls.clear()
    eng.run(spec(1, False))
    # anchor steps back one observed week; window follows it; spans extend
    assert calls[0] == (8.0, "2025-12-27", 2)
    assert [c[2] for c in calls] == [2, 3, 4, 5]
    calls.clear()
    # the nowcast rule: the vintage's last row is dated the forecast date
    # itself, so drop_same_day trims it automatically -- same arithmetic
    # as an explicit one-week drop
    eng.run(spec(0, True))
    assert calls[0] == (8.0, "2025-12-27", 2)
    calls.clear()
    # and when the vintage has NO same-day row, the rule trims nothing:
    # forecast a week later than the data ends
    spec_late = type("S", (), {"forecast_date": "2026-01-10",
                               "locations": ["Ohio"],
                               "weeks_to_drop": 0,
                               "drop_same_day": True})()
    eng.run(spec_late)
    assert calls[0] == (9.0, "2026-01-10", 1)
