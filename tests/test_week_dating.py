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
