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


# ---------------------------------------------------- hub value precision

def test_values_are_whole_admissions_like_the_official_files():
    """Measured in the hub clone (2026-08-21): every official
    FluSight-baseline and FluSight-ensemble 'wk inc flu hosp' quantile
    value from 2025 on is an integer count -- the long float tails in
    recent official files belong to the 'wk inc flu prop ed visits'
    proportion target. Our writers match that precision; the raw numpy
    quantiles were leaking 17-digit tails into the CSVs."""
    tailed = {str(h): [10.1234567890123 * h + i * 0.337 for i in range(40)]
              for h in (1, 2, 3, 4)}
    rows = quantile_rows(tailed, "06", ASOF)
    assert rows
    for r in rows:
        assert isinstance(r["value"], int), r
    qd = {str(h): {0.25: 9.700000000000001 * h, 0.5: 10.1 * h,
                   0.75: 11.499999999999998 * h} for h in (1, 2, 3, 4)}
    for r in rows_from_quantiles(qd, "06", ASOF):
        assert isinstance(r["value"], int), r


def test_rounding_preserves_quantile_monotonicity():
    """The guard: round, then enforce non-decreasing. A vector whose raw
    values are monotone but sit within one count of each other must come
    out monotone (never decreasing) after rounding."""
    import numpy as np
    from app.core.submit import QUANTILES, _hub_values
    raw = [10.0 + 0.04 * i for i in range(len(QUANTILES))]   # 10.0 .. 10.88
    v = _hub_values(raw)
    assert all(b >= a for a, b in zip(v, v[1:]))
    # a deliberately jittered near-tie stays monotone too
    raw2 = [5.49, 5.51, 5.49999, 5.5001, 6.49, 6.51]
    v2 = _hub_values(raw2)
    assert all(b >= a for a, b in zip(v2, v2[1:]))
    assert all(float(x).is_integer() for x in v2)


def test_csv_writes_integers_not_float_tails(tmp_path):
    """End to end through write_submission: the file on disk carries '12',
    never '12.0' and never a 17-digit tail."""
    from app.core.submit import write_submission
    samples = {str(h): [3.3 * h + i * 1.7 for i in range(50)]
               for h in (1, 2, 3, 4)}
    rows = quantile_rows(samples, "06", ASOF)
    p = write_submission(rows, "SIHRS", "NAU", "2025-12-20", tmp_path)
    text = p.read_text()
    lines = text.strip().splitlines()
    vals = [ln.rsplit(",", 1)[1] for ln in lines[1:]]
    assert vals
    for v in vals:
        assert "." not in v, v                       # whole counts only
        int(v)                                       # and parseable as such
