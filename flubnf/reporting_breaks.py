"""RESEARCH (only tests import this; not on the shipped console path).

Detect and record measurement discontinuities in a truth series.

A reporting break is a LEVEL SHIFT, not an outlier: post-shift values are
good measurements of a newly defined quantity, so what must be dropped is
the CROSSING (a forecast anchored on the old scale and scored on the new
one measures the instrument, not the forecast).

`level_break_scan`: log week-over-week ratios minus the median of the eight
surrounding ratios, in robust SDs (MAD x 1.4826); small everywhere but at a
step.

`cross_pathogen_step`: NHSN measures three pathogens on one form, so a step
shared by COVID, influenza and RSV in one week, with the reporting-hospital
count flat, is the instrument, not epidemiology.

The one break found is in `COVID_BREAKS` (2026-03-21 -> 2026-03-28).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BreakCandidate:
    week: str                 # target_end_date of the first shifted week
    ratio: float              # value(week) / value(previous week)
    excess_log: float         # log ratio minus the local median log ratio
    excess_pct: float
    robust_sd: float          # of the residual series
    z: float                  # excess_log / robust_sd


def level_break_scan(dates: Sequence, values: Sequence,
                     half_window: int = 4) -> list:
    """Rank single-week level excursions, most negative first.

    Returns BreakCandidate rows sorted by `excess_log` ascending, so the first
    entry is the largest DOWN step. Non-positive and non-finite values break the
    log ratio and are dropped with their week.
    """
    d = [str(x)[:10] for x in dates]
    v = np.asarray(values, dtype=float)
    keep = np.isfinite(v) & (v > 0)
    d = [dd for dd, k in zip(d, keep) if k]
    v = v[keep]
    if v.size < 2 * half_window + 3:
        return []
    lr = np.log(v[1:] / v[:-1])
    res = np.empty_like(lr)
    for i in range(lr.size):
        lo, hi = max(0, i - half_window), min(lr.size, i + half_window + 1)
        nb = np.concatenate([lr[lo:i], lr[i + 1:hi]])
        res[i] = lr[i] - (np.median(nb) if nb.size else 0.0)
    mad = float(np.median(np.abs(res - np.median(res))))
    sd = mad * 1.4826 if mad > 0 else float("nan")
    out = [BreakCandidate(week=d[i + 1], ratio=float(v[i + 1] / v[i]),
                          excess_log=float(res[i]),
                          excess_pct=float(np.exp(res[i]) - 1.0),
                          robust_sd=sd,
                          z=float(res[i] / sd) if sd and np.isfinite(sd) else float("nan"))
           for i in range(lr.size)]
    return sorted(out, key=lambda c: c.excess_log)


def cross_pathogen_step(frame: pd.DataFrame, week: str, prev_week: str,
                        pathogen_cols: Sequence[str],
                        reporting_col: Optional[str] = None) -> dict:
    """Did every pathogen on the same form step together?

    `frame` is indexed by week (a column named `week`) with one column per
    pathogen and, optionally, the count of hospitals reporting. Returns the
    per-pathogen ratios, their spread, and the reporting-count ratio. A verdict
    of INSTRUMENT requires the pathogens to agree AND the reporting count to
    stay put -- a collapse in reporting would explain the step without any
    change in the case definition, and is a different finding.
    """
    f = frame.set_index("week")
    ratios = {}
    for c in pathogen_cols:
        a, b = float(f.loc[prev_week, c]), float(f.loc[week, c])
        ratios[c] = b / a if a > 0 else float("nan")
    vals = np.array([r for r in ratios.values() if np.isfinite(r)])
    rep = float("nan")
    if reporting_col is not None:
        a = float(f.loc[prev_week, reporting_col])
        b = float(f.loc[week, reporting_col])
        rep = b / a if a > 0 else float("nan")
    agree = bool(vals.size >= 2 and (vals.max() - vals.min()) < 0.10)
    reporting_stable = bool(np.isfinite(rep) and abs(rep - 1.0) < 0.05)
    if agree and reporting_stable and vals.mean() < 0.75:
        verdict = "INSTRUMENT, not epidemiology"
    elif agree and np.isfinite(rep) and rep < 0.9:
        verdict = "REPORTING COVERAGE fell; step is coverage, not definition"
    else:
        verdict = "NOT ATTRIBUTABLE from this test"
    return {"week": week, "prev_week": prev_week, "ratios": ratios,
            "ratio_spread": float(vals.max() - vals.min()) if vals.size else float("nan"),
            "reporting_ratio": rep, "pathogens_agree": agree,
            "reporting_stable": reporting_stable, "verdict": verdict}


# ---------------------------------------------------------------------------
# The recorded finding
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecordedBreak:
    series: str
    last_clean_week: str
    first_shifted_week: str
    measured: dict
    verdict: str
    action: str


#: Measured 2026-08-22 on the CovidHub parquet (as_of 2026-08-19) and on Socrata
#: mpgq-jmmr for the reporting counts (reproduction script in the lab
#: archive, not this repo).
COVID_BREAKS: tuple = (
    RecordedBreak(
        series="wk inc covid hosp, US national",
        last_clean_week="2026-03-21",
        first_shifted_week="2026-03-28",
        measured={
            "covid_ratio": 2280 / 3978,          # 0.573
            "influenza_ratio": 3341 / 6100,      # 0.548
            "rsv_ratio": 3900 / 6609,            # 0.590
            "hospitals_reporting_ratio": 5159 / 5249,   # 0.983
            "jurisdictions_reporting_before": 52,   # excluding US
            "jurisdictions_reporting_after": 52,
            "excess_log_vs_local_median": -0.441,
            "excess_pct": -0.357,
            "robust_sd_of_residual": 0.0578,
            "z": -7.63,
            "next_largest_down_excursion_log": -0.233,
            "states_with_ratio_below_0_75": 34,
            "states_scored": 52,
            "present_in_first_issue": True,
        },
        verdict=("INSTRUMENT, not epidemiology. Three pathogens measured by one "
                 "NHSN form step together by 41-45% in one week with the "
                 "hospital-reporting count flat at -1.7% and all 52 "
                 "non-national jurisdictions still reporting."),
        action=("Exclude every scored cell whose anchor week is on or before "
                "2026-03-21 AND whose target_end_date is on or after "
                "2026-03-28. Cells wholly on one side are kept: the level shift "
                "is common to model and truth there. Enforced by "
                "DiseaseProfile.excluded_for()."),
    ),
)
