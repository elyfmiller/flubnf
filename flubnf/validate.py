"""FluSight submission CSV schema validator.

Validates a submission CSV before writing so a bad fit can't produce an
invalid submission that gets rejected at PR review time. Rules mirror
the FluSight forecast hub schema documented at
https://github.com/cdcepi/FluSight-forecast-hub/blob/main/model-output/README.md

Validated rules:
  * Required columns: reference_date, target, horizon, target_end_date,
    location, output_type, output_type_id, value
  * `reference_date` is the same ISO date for every row
  * `target` == "wk inc flu hosp" (the standard flu target)
  * `horizon` ∈ {0, 1, 2, 3}
  * `target_end_date` = reference_date + horizon * 7 days
  * `location` is a 2-digit FIPS string or "US"
  * `output_type` == "quantile"
  * `output_type_id` ∈ the FluSight quantile levels (23 values)
  * `value` is finite and non-negative
  * For each (location, horizon), the quantile values are monotonically
    non-decreasing in `output_type_id`
  * Every required (location, horizon, quantile) cell is present

Usage:
    from flubnf.validate import validate_submission_df, ValidationReport
    report = validate_submission_df(df)
    if not report.ok:
        for e in report.errors: print(e)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .quantiles import FLUSIGHT_QUANTILES


REQUIRED_COLUMNS = (
    "reference_date", "target", "horizon", "target_end_date",
    "location", "output_type", "output_type_id", "value",
)
EXPECTED_TARGET = "wk inc flu hosp"
EXPECTED_HORIZONS = {0, 1, 2, 3}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_submission_df(df: pd.DataFrame) -> ValidationReport:
    """Validate a FluSight submission DataFrame.

    Errors prevent the submission from being valid. Warnings are
    advisory (e.g., suspicious-but-legal patterns)."""
    rep = ValidationReport()

    # 1. Required columns.
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        rep.errors.append(f"missing required columns: {missing}")
        return rep   # can't validate further without columns

    if df.empty:
        rep.errors.append("submission is empty")
        return rep

    # 2. reference_date is one consistent value.
    ref_dates = df["reference_date"].astype(str).unique()
    if len(ref_dates) != 1:
        rep.errors.append(
            f"reference_date must be a single value; found {sorted(ref_dates)}"
        )
    try:
        ref_date = date.fromisoformat(str(ref_dates[0]))
    except (ValueError, TypeError):
        rep.errors.append(f"reference_date not ISO-formatted: {ref_dates[0]!r}")
        ref_date = None

    # 3. target.
    bad_target = df[df["target"] != EXPECTED_TARGET]
    if not bad_target.empty:
        unique = bad_target["target"].unique()[:3]
        rep.errors.append(
            f"target must be {EXPECTED_TARGET!r}; found {unique} in "
            f"{len(bad_target)} row(s)"
        )

    # 4. horizon.
    horizons = set(df["horizon"].unique().tolist())
    invalid_h = horizons - EXPECTED_HORIZONS
    if invalid_h:
        rep.errors.append(f"unexpected horizon values: {sorted(invalid_h)}")

    # 5. target_end_date = reference_date + horizon * 7.
    if ref_date is not None:
        for h, group in df.groupby("horizon"):
            expected_end = ref_date + timedelta(days=int(h) * 7)
            actual_ends = group["target_end_date"].unique()
            bad = [a for a in actual_ends if str(a) != expected_end.isoformat()]
            if bad:
                rep.errors.append(
                    f"horizon={h}: target_end_date must be "
                    f"{expected_end.isoformat()}; found {bad[:3]}"
                )

    # 6. location.
    loc_strs = df["location"].astype(str).unique()
    bad_loc = [
        l for l in loc_strs
        if not (l == "US" or (l.isdigit() and len(l) == 2))
    ]
    if bad_loc:
        rep.errors.append(
            f"location must be 'US' or 2-digit FIPS string; "
            f"found {bad_loc[:5]}"
        )

    # 7. output_type.
    if (df["output_type"] != "quantile").any():
        bad = df[df["output_type"] != "quantile"]["output_type"].unique()
        rep.errors.append(f"output_type must be 'quantile'; found {bad[:3]}")

    # 8. output_type_id is a valid quantile level.
    q_levels = sorted(set(float(q) for q in FLUSIGHT_QUANTILES))
    bad_q = sorted(set(
        float(q) for q in df["output_type_id"].unique()
        if float(q) not in q_levels
    ))
    if bad_q:
        rep.errors.append(
            f"output_type_id must be one of {q_levels}; "
            f"found {bad_q[:5]}"
        )

    # 9. value finite + non-negative.
    values = pd.to_numeric(df["value"], errors="coerce")
    n_nan = int(values.isna().sum())
    if n_nan:
        rep.errors.append(f"{n_nan} row(s) have non-numeric values")
    n_neg = int((values < 0).sum())
    if n_neg:
        rep.errors.append(f"{n_neg} row(s) have negative values")
    n_inf = int(np.isinf(values).sum())
    if n_inf:
        rep.errors.append(f"{n_inf} row(s) have infinite values")

    # 10. Quantile monotonicity per (location, horizon).
    n_non_mono = 0
    for (loc, h), group in df.groupby(["location", "horizon"]):
        ordered = group.sort_values("output_type_id")
        vals = pd.to_numeric(ordered["value"], errors="coerce").to_numpy()
        if np.any(np.diff(vals) < 0):
            n_non_mono += 1
    if n_non_mono:
        rep.errors.append(
            f"{n_non_mono} (location, horizon) cells have non-monotonic "
            f"quantiles (output should rise with output_type_id)"
        )

    # 11. Coverage: every (location, horizon, quantile) cell present.
    expected_per_loc_h = len(FLUSIGHT_QUANTILES)
    incomplete = []
    for (loc, h), group in df.groupby(["location", "horizon"]):
        if len(group) != expected_per_loc_h:
            incomplete.append((loc, h, len(group)))
    if incomplete:
        rep.errors.append(
            f"incomplete coverage: {len(incomplete)} (location, horizon) "
            f"cells don't have all {expected_per_loc_h} quantiles "
            f"(first: {incomplete[:3]})"
        )

    # 12. Warnings — soft signals.
    # Median values that look extreme:
    median_rows = df[df["output_type_id"].astype(float) == 0.5]
    if not median_rows.empty:
        med_max = float(pd.to_numeric(median_rows["value"]).max())
        if med_max > 1e6:
            rep.warnings.append(
                f"max median forecast is {med_max:.0f} (suspiciously large)"
            )

    return rep


def validate_submission_csv(path: Path) -> ValidationReport:
    """Convenience wrapper to validate a file on disk."""
    df = pd.read_csv(path, dtype={"location": str})
    df["location"] = df["location"].str.zfill(2).where(df["location"] != "US",
                                                       df["location"])
    return validate_submission_df(df)
