"""Tests for flubnf.season_report."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from flubnf.calibration import CalibrationTracker, CoverageRecord
from flubnf.paths import WorkspacePaths
from flubnf.season_report import build_season_report
from flubnf.session import StateSession, save_session, record_step
from flubnf.conf_files import FreeParam
from datetime import date


def _seed_workspace(tmp_path: Path) -> WorkspacePaths:
    paths = WorkspacePaths(root=tmp_path / "season_test").ensure()

    # Session for Alabama with three weeks of history (K grows 1→2→2).
    al = StateSession(state="Alabama", bounds=[FreeParam("b0__FREE", 0.1, 1.5)])
    record_step(al, reference_date=date(2026, 1, 3),
                bounds_changed=["b0__FREE"], bounds_added=[],
                best_obj=1000.0)
    al.n_steps = 1
    record_step(al, reference_date=date(2026, 1, 10),
                bounds_changed=[], bounds_added=["b1__FREE", "t1__FREE"],
                best_obj=900.0)
    al.n_steps = 2
    record_step(al, reference_date=date(2026, 1, 17),
                bounds_changed=["mult__FREE"], bounds_added=[],
                best_obj=850.0)
    al.n_steps = 2
    save_session(paths.root, al)

    # Calibration tracker for Alabama h=1.
    tracker = CalibrationTracker()
    for w in range(12):
        tracker.record(CoverageRecord(
            state="Alabama", horizon=1, reference_date=f"w{w}",
            q025=80, q05=85, q25=95, q50=100, q75=105, q95=115, q975=120,
            actual=102.0,
        ))
    tracker.save(paths.root / "calibration.json")

    # A submission CSV.
    sub_dir = paths.root / "submissions"
    sub_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for h in range(4):
        rows.append({
            "reference_date": "2026-01-17",
            "target": "wk inc flu hosp",
            "horizon": h,
            "target_end_date": f"2026-01-{17+7*h:02d}",
            "location": "01",
            "output_type": "quantile",
            "output_type_id": 0.5,
            "value": 100 + h * 10,
        })
    pd.DataFrame(rows).to_csv(
        sub_dir / "2026-01-17-LosAlamos_NAU-CModel_Flu.csv", index=False,
    )

    return paths


def test_build_season_report_returns_all_pieces(tmp_path):
    paths = _seed_workspace(tmp_path)
    report = build_season_report(paths)
    # Session history
    assert len(report.state_records) == 3
    assert set(report.state_records["state"]) == {"Alabama"}
    # Calibration
    assert len(report.calibration) == 1
    assert report.calibration.iloc[0]["state"] == "Alabama"
    assert report.calibration.iloc[0]["n_records"] == 12
    # Submissions
    assert len(report.submissions) == 4
    assert all(report.submissions["location"] == "01")
    # Aggregates
    assert len(report.aggregate_k_trend) == 3
    assert len(report.aggregate_calibration) == 1


def test_empty_workspace_returns_empty_frames(tmp_path):
    paths = WorkspacePaths(root=tmp_path / "empty").ensure()
    report = build_season_report(paths)
    assert report.state_records.empty
    assert report.calibration.empty
    assert report.submissions.empty
    assert report.aggregate_k_trend.empty
    assert report.aggregate_calibration.empty
