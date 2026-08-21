"""The FluSight CSV writers carry the frozen join: reference = as-of + 7,
hub horizon 0..3 = internal samples "1".."4". This is the same formula
scripts/anchor_analysis.py validated against three seasons of scoring; the
writers computing anything else mislabels a real submission by a week."""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.submit import quantile_rows, rows_from_quantiles  # noqa: E402


ASOF = "2025-12-13"          # a Saturday as-of; submission is due Wed 12-17
SAMPLES = {str(h): [10.0 * h, 12.0 * h, 14.0 * h] for h in (1, 2, 3, 4)}
QDICTS = {str(h): {0.5: 10.0 * h} for h in (1, 2, 3, 4)}


def test_reference_is_asof_plus_seven_matching_anchor_analysis():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    ref = (pd.Timestamp(ASOF) + timedelta(days=7)).date().isoformat()
    rows = quantile_rows(SAMPLES, "06", ASOF)
    assert rows and all(r["reference_date"] == ref == "2025-12-20"
                        for r in rows)


def test_target_end_dates_walk_the_four_target_weeks():
    rows = quantile_rows(SAMPLES, "06", ASOF)
    by_h = {r["horizon"]: r["target_end_date"] for r in rows}
    assert by_h == {0: "2025-12-20", 1: "2025-12-27",
                    2: "2026-01-03", 3: "2026-01-10"}


def test_horizon_zero_carries_internal_sample_one():
    rows = [r for r in quantile_rows(SAMPLES, "06", ASOF)
            if r["horizon"] == 0 and r["output_type_id"] == 0.5]
    assert rows[0]["value"] == 12.0          # median of samples "1"


def test_quantile_native_writer_same_join():
    rows = rows_from_quantiles(QDICTS, "06", ASOF)
    assert all(r["reference_date"] == "2025-12-20" for r in rows)
    by_h = {r["horizon"]: (r["target_end_date"], r["value"]) for r in rows}
    assert by_h[0] == ("2025-12-20", 10.0)
    assert by_h[3] == ("2026-01-10", 40.0)
