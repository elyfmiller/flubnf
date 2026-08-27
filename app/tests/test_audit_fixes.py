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
