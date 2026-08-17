"""Tests for flubnf.validate (submission schema validator)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from flubnf.quantiles import FLUSIGHT_QUANTILES
from flubnf.validate import (REQUIRED_COLUMNS, validate_submission_df)


def _make_valid_submission(
    reference_date: date = date(2026, 1, 3),
    locations: list[str] = None,
    horizons: list[int] = None,
) -> pd.DataFrame:
    """Build a minimal valid FluSight submission DataFrame."""
    locations = locations or ["01", "06", "US"]
    horizons = horizons or [0, 1, 2, 3]
    rows = []
    for loc in locations:
        for h in horizons:
            tgt = (reference_date + timedelta(days=7 * h)).isoformat()
            for i, q in enumerate(FLUSIGHT_QUANTILES):
                rows.append({
                    "reference_date": reference_date.isoformat(),
                    "target": "wk inc flu hosp",
                    "horizon": h,
                    "target_end_date": tgt,
                    "location": loc,
                    "output_type": "quantile",
                    "output_type_id": float(q),
                    # Monotonically increasing quantile values.
                    "value": 10.0 + h * 5 + i * 2,
                })
    return pd.DataFrame(rows)


def test_valid_submission_passes():
    df = _make_valid_submission()
    rep = validate_submission_df(df)
    assert rep.ok
    assert rep.errors == []


def test_missing_required_column_fails():
    df = _make_valid_submission().drop(columns=["target"])
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("missing" in e.lower() for e in rep.errors)


def test_inconsistent_reference_date_fails():
    df = _make_valid_submission()
    df.loc[0, "reference_date"] = "2026-01-10"
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("reference_date" in e for e in rep.errors)


def test_wrong_target_fails():
    df = _make_valid_submission()
    df.loc[0, "target"] = "covid hospitalizations"
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("target" in e.lower() for e in rep.errors)


def test_invalid_horizon_fails():
    df = _make_valid_submission(horizons=[0, 1, 2, 5])
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("horizon" in e for e in rep.errors)


def test_wrong_target_end_date_fails():
    df = _make_valid_submission()
    # Mangle the h=2 target end date.
    df.loc[df["horizon"] == 2, "target_end_date"] = "2026-12-31"
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("target_end_date" in e for e in rep.errors)


def test_bad_location_fails():
    df = _make_valid_submission()
    df.loc[0, "location"] = "1"  # not zero-padded
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("location" in e for e in rep.errors)


def test_us_location_is_valid():
    """US row should be accepted as a special case."""
    df = _make_valid_submission(locations=["01", "US"])
    rep = validate_submission_df(df)
    assert rep.ok


def test_negative_value_fails():
    df = _make_valid_submission()
    df.loc[0, "value"] = -1.0
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("negative" in e for e in rep.errors)


def test_nan_value_fails():
    df = _make_valid_submission()
    df.loc[0, "value"] = float("nan")
    rep = validate_submission_df(df)
    assert not rep.ok


def test_non_monotonic_quantiles_fails():
    df = _make_valid_submission(locations=["01"], horizons=[0])
    # Make the 75% quantile lower than the 50%.
    df.loc[df["output_type_id"] == 0.75, "value"] = 0.0
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("monoton" in e.lower() for e in rep.errors)


def test_incomplete_coverage_fails():
    df = _make_valid_submission()
    # Drop a quantile from one (location, horizon) cell.
    df = df[~((df["location"] == "01") & (df["horizon"] == 0) &
              (df["output_type_id"] == 0.5))]
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("coverage" in e.lower() for e in rep.errors)


def test_invalid_quantile_level_fails():
    df = _make_valid_submission(locations=["01"], horizons=[0])
    df.loc[df["output_type_id"] == 0.5, "output_type_id"] = 0.555
    rep = validate_submission_df(df)
    assert not rep.ok
    assert any("output_type_id" in e for e in rep.errors)


def test_empty_submission_fails():
    rep = validate_submission_df(pd.DataFrame({c: [] for c in REQUIRED_COLUMNS}))
    assert not rep.ok
    assert any("empty" in e.lower() for e in rep.errors)


def test_huge_median_emits_warning():
    # Inflate everything proportionally so monotonicity is preserved.
    df = _make_valid_submission()
    df["value"] = df["value"] * 1e6
    rep = validate_submission_df(df)
    assert rep.ok
    assert any("large" in w.lower() or "suspicious" in w.lower()
               for w in rep.warnings)
