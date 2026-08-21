"""FluSight submission formatting + validation.

Hub facts (verified against model-metadata/README.md, 2026-08-17):
  * model identity lives in the PATH (model-output/<team>-<model>/), never in
    a CSV column -- one file per model_id per reference date;
  * a team may designate up to two models for the ensemble (more via email
    with out-of-sample evidence);
  * quantile targets: 'wk inc flu hosp' at 23 quantiles, horizons -1..3.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

QUANTILES = (0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45,
             0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99)


def quantile_rows(samples: dict, location_fips: str, asof: str) -> list:
    """FluSight rows for one location from horizon->samples arrays.

    THE FROZEN JOIN (must match scripts/anchor_analysis.py, the formula the
    seal's scoring validated): hub reference_date = our as-of Saturday + 7
    days, and hub horizon 0..3 carries our samples "1".."4". Callers pass
    the AS-OF date (spec.forecast_date); the reference is computed here, in
    exactly one place. Passing the as-of straight through as the reference
    mislabeled every exported CSV by one week (caught 2026-08-21, before
    any real submission)."""
    ref = pd.Timestamp(asof) + pd.Timedelta(days=7)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        s = np.asarray(samples.get(str(h + 1), []), float)
        s = s[np.isfinite(s)]
        if not s.size:
            continue
        target_end = ref + pd.Timedelta(weeks=h)
        for q in QUANTILES:
            rows.append({
                "reference_date": reference_date,
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": str(target_end.date()),
                "location": location_fips,
                "output_type": "quantile",
                "output_type_id": q,
                "value": float(np.quantile(s, q)),
            })
    return rows


def validate(df: pd.DataFrame) -> list:
    """Gate before anything leaves the machine. Returns list of defects.

    The degenerate-cell rule is measured, not theoretical: 0.23% of cells once
    carried 49% of total WIS (zero-width quantiles at wrong levels).
    """
    problems = []
    if df.empty:
        return ["submission is empty"]
    for (loc, h), g in df[df.output_type == "quantile"].groupby(
            ["location", "horizon"]):
        g = g.sort_values("output_type_id")
        v = g.value.to_numpy()
        if (np.diff(v) < 0).any():
            problems.append(f"{loc} h={h}: quantiles not monotone")
        if (v < 0).any():
            problems.append(f"{loc} h={h}: negative quantile value")
        if v[0] == v[-1] and v[0] > 0:
            problems.append(f"{loc} h={h}: degenerate (zero-width) distribution")
    return problems


def write_submission(all_rows: Iterable[dict], model_id: str, team: str,
                     reference_date: str, out_dir: Path) -> Path:
    """One hub-format CSV per model_id (identity is the PATH, rule above)."""
    df = pd.DataFrame(list(all_rows))
    problems = validate(df)
    if problems:
        raise ValueError("submission failed validation:\n  " +
                         "\n  ".join(problems[:10]))
    d = Path(out_dir) / f"{team}-{model_id}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{reference_date}-{team}-{model_id}.csv"
    df.to_csv(p, index=False)
    return p


def rows_from_quantiles(qs: dict, location_fips: str, asof: str) -> list:
    """FluSight rows from horizon -> {level: value} (quantile-native members).
    Same frozen join as quantile_rows: reference = as-of + 7 days."""
    ref = pd.Timestamp(asof) + pd.Timedelta(days=7)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        q = qs.get(str(h + 1))
        if not q:
            continue
        target_end = ref + pd.Timedelta(weeks=h)
        for level in QUANTILES:
            if float(level) not in q:
                continue
            rows.append({
                "reference_date": reference_date,
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": str(target_end.date()),
                "location": location_fips,
                "output_type": "quantile",
                "output_type_id": level,
                "value": float(q[float(level)]),
            })
    return rows
