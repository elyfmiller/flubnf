"""Observed week i is the MMWR week ENDING onset Sunday + 7i + 6 (a Saturday).

pymmwr.epiweek_to_date returns the SUNDAY that starts an epiweek, while every
FluSight target_end_date (and every target-data date) is the week-ending
SATURDAY. The legacy calibration paths dated observed week i as onset + 7i,
a Sunday, so no realized actual ever matched a submission's target dates and
the calibration tracker / slope sweep silently saw nothing.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pymmwr as pm

from flubnf.config import FluBNFConfig
from flubnf.constants import load_locations

REPO = Path(__file__).resolve().parents[1]
LOCS_CSV = REPO / "flubnf" / "data" / "locations.csv"
N_OBS = 12
REF_IDX = 8     # the reference date is the week ending of observed week 8


def _cfg():
    return FluBNFConfig(locations_csv=LOCS_CSV)


def _saturday(cfg, i):
    onset = pm.epiweek_to_date(pm.Epiweek(cfg.season.year,
                                          cfg.season.onset_week))
    return onset + timedelta(days=7 * i + 6)


def _submission(cfg) -> pd.DataFrame:
    ref = _saturday(cfg, REF_IDX)
    assert ref.weekday() == 5
    rows = []
    for h in range(4):
        ted = (ref + timedelta(weeks=h)).isoformat()
        for q in (0.025, 0.05, 0.25, 0.5, 0.75, 0.95, 0.975):
            rows.append({"reference_date": ref.isoformat(), "location": "01",
                         "horizon": h, "target_end_date": ted,
                         "output_type": "quantile", "output_type_id": q,
                         "value": 100.0})
    return pd.DataFrame(rows)


OBS = np.array([100.0 + i for i in range(N_OBS)])


def test_weekly_job_ingests_actuals_on_week_ending_saturdays(tmp_path):
    from flubnf import weekly_job
    cfg = _cfg()
    (tmp_path / "submissions").mkdir()
    _submission(cfg).to_csv(tmp_path / "submissions" / "sub.csv", index=False)

    recorded = []
    tracker = SimpleNamespace(record=recorded.append)
    added = weekly_job._ingest_realized_actuals(
        SimpleNamespace(root=tmp_path), tracker, {"Alabama": OBS}, cfg)

    assert added == 4
    got = {r.horizon: r.actual for r in recorded}
    # FluSight h -> internal h+1; its target is observed week REF_IDX + h
    assert got == {h + 1: OBS[REF_IDX + h] for h in range(4)}


def test_slope_tune_matches_actuals_and_cuts_history_at_the_as_of(
        monkeypatch):
    from flubnf import amcmc, cli, slope_tune
    cfg = _cfg()
    locs = load_locations(LOCS_CSV)
    seen = {}

    monkeypatch.setattr(amcmc, "read_traj_noise", lambda *a, **k: "traj")
    monkeypatch.setattr(cli, "_observed_for_state", lambda *a, **k: OBS)

    def sweep(traj, obs, actuals, state):
        seen["obs"], seen["actuals"] = obs, actuals
        return "res"
    monkeypatch.setattr(slope_tune, "sweep_slope_blend", sweep)
    monkeypatch.setattr(slope_tune, "recommend_blend", lambda r: 0.5)

    status, _res, rec = cli._tune_slope_for_state(
        "Alabama", sub_df=_submission(cfg), df_raw=None, cfg=cfg, locs=locs,
        paths=SimpleNamespace(results_for=lambda s: None),
        geo_col="g", date_col="d", val_col="v")

    assert status == "ok" and rec == 0.5
    assert seen["actuals"] == {h + 1: OBS[REF_IDX + h] for h in range(4)}
    # the forecast is made as of reference_date - 7: horizon 0's week (the
    # reference week itself) is a target, never part of the history
    np.testing.assert_array_equal(seen["obs"], OBS[:REF_IDX])
