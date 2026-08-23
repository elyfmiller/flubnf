"""Phase 0: re-run the analogue arm on COVID, VINTAGE-TRUE, on the June boundary.

WHAT THE PRIOR MEASUREMENT DID AND DID NOT ESTABLISH
-----------------------------------------------------
covid_model_assessment.md section 3 measured calendar matching on COVID at
relWIS 0.812 against a matched calendar-blind control (flu: 0.806) and concluded
the analogue's premise transfers. Two caveats travelled with it, both stated by
its author:

  * SETTLED TRUTH, not vintage anchors. The anchor-alignment trap in
    analogue.py is worth 0.177 relWIS on flu -- larger than most real effects in
    this project -- so an un-vintaged analogue number is not a forecast number.
  * FLU'S AUGUST BOUNDARY, which cuts a COVID epidemic in half and therefore
    mislabels donor seasons.

This script fixes both. Same two arms, same donor bank, same MIN_DONORS rule,
same quantile machinery; the ONLY difference between arms is whether donors are
calendar-matched, so the ratio is exactly the incremental value of the
analogue's premise. A flat random-walk arm is scored alongside for context.

WHAT VINTAGE-TRUE COSTS, AND IT IS NOT SMALL
---------------------------------------------
Under the June boundary, target season 2025 runs 2025-06-01 to 2026-05-31 and
its donors must come from season 2024 or earlier. The COVID vintage record
begins 2024-11-20 with a data edge of 2024-11-09. So a vintage-true donor bank
holds season 2024 only from November onward, and calendar weeks in roughly
June-October have NO prior-season donor at the matching epiweek. The analogue
is therefore SILENT for the first third of a COVID season under vintage-true
rules -- a structural consequence of the 2024-11-20 horizon, not a tuning
choice. This script measures where it goes silent rather than papering over it
with settled truth.

Run:  .venv/bin/python research/covid-phase0/analogue_vintage_true.py
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flubnf import covid_vintage as cv                          # noqa: E402
from flubnf.analogue import (DEFAULT_BANDWIDTH, analogue_quantiles,  # noqa: E402
                             build_bank, epiweek)
from flubnf.profiles import COVID                               # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES                 # noqa: E402
from flubnf.wis import wis                                      # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
TARGET_SEASON = 2025
HORIZONS = (1, 2, 3, 4)


def donor_ratios_profiled(bank, target_epiweek, target_season, horizon,
                          bandwidth, calendar_blind=False):
    """The shipped donor rule with the PROFILE's season boundary.

    `flubnf.analogue.donor_ratios` calls the module-level `season_of`, which is
    influenza's August rule. Reimplementing only that one line keeps the donor
    pooling, the finite filters and the ratio construction identical -- the
    verification in the assessment showed that pooling must be byte-identical
    or the comparison is not a comparison.
    """
    out = []
    for (loc, d), v0 in bank.items():
        if not np.isfinite(v0) or v0 <= 0:
            continue
        if COVID.season_of(d) >= target_season:
            continue
        if not calendar_blind:
            a, b = epiweek(d), target_epiweek
            if min(abs(a - b), 52 - abs(a - b)) > bandwidth:
                continue
        v1 = bank.get((loc, d + timedelta(days=7 * horizon)))
        if v1 is None or not np.isfinite(v1) or v1 <= 0:
            continue
        out.append(v1 / v0)
    arr = np.asarray(out, float)
    return arr[np.isfinite(arr)]


def flat_quantiles(anchor: float, sd_log: float = 0.25):
    """A FluSight-baseline-shaped flat random walk, for context only."""
    from statistics import NormalDist
    nd = NormalDist()
    return {float(L): float(anchor * np.exp(nd.inv_cdf(L) * sd_log))
            for L in FLUSIGHT_QUANTILES}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settled = cv.vintage_frame(cv.vintages()[-1])
    settled["d"] = pd.to_datetime(settled["date"]).dt.date
    tmap = {(r.location, r.d): float(r.value) for r in settled.itertuples()}

    season_start = pd.Timestamp(COVID.season_start(TARGET_SEASON)).date()
    season_end = pd.Timestamp(COVID.season_bounds(TARGET_SEASON)[1]).date()
    asofs = [a for a in cv.vintages()
             if season_start <= pd.Timestamp(a).date() <= season_end]

    rows, silence = [], []
    for asof in asofs:
        frame = cv.vintage_frame(asof)
        frame["d"] = pd.to_datetime(frame["date"]).dt.date
        bank = build_bank(frame[["location", "d", "value"]]
                          .rename(columns={"d": "date"}).itertuples(index=False))
        edge = max(d for (_, d) in bank)
        ew = epiweek(edge)
        n_donor_any = 0
        for h in HORIZONS:
            r_cal = donor_ratios_profiled(bank, ew, TARGET_SEASON, h,
                                          DEFAULT_BANDWIDTH)
            r_bli = donor_ratios_profiled(bank, ew, TARGET_SEASON, h,
                                          DEFAULT_BANDWIDTH, calendar_blind=True)
            n_donor_any = max(n_donor_any, r_cal.size)
            target = edge + timedelta(days=7 * h)
            excl = COVID.excluded_for(str(edge), str(target))
            for loc in sorted({l for (l, _) in bank}):
                if loc == "US":
                    continue
                anchor = bank.get((loc, edge))
                actual = tmap.get((loc, target))
                if anchor is None or actual is None or excl:
                    continue
                q_cal = analogue_quantiles(anchor, r_cal, FLUSIGHT_QUANTILES)
                q_bli = analogue_quantiles(anchor, r_bli, FLUSIGHT_QUANTILES)
                if q_cal is None or q_bli is None:
                    continue
                rows.append({
                    "asof": asof, "edge": str(edge), "epiweek": ew,
                    "location": loc, "horizon": h, "actual": actual,
                    "n_donors_calendar": int(r_cal.size),
                    "n_donors_blind": int(r_bli.size),
                    "wis_analogue": wis(q_cal, actual).wis,
                    "wis_blind": wis(q_bli, actual).wis,
                    "wis_flat": wis(flat_quantiles(anchor), actual).wis})
        silence.append({"asof": asof, "edge": str(edge), "epiweek": ew,
                        "max_calendar_donors": int(n_donor_any),
                        "silent": bool(n_donor_any < 30)})

    df = pd.DataFrame(rows)
    sil = pd.DataFrame(silence)
    res = {"target_season": COVID.season_label(TARGET_SEASON),
           "season_boundary_month": COVID.season_boundary_month,
           "as_of_weeks_in_season": len(asofs),
           "as_of_weeks_silent_no_donors": int(sil["silent"].sum()),
           "first_week_with_donors": (sil[~sil["silent"]]["asof"].min()
                                      if (~sil["silent"]).any() else None),
           "cells_scored": int(len(df))}
    if len(df):
        res["relwis_analogue_over_blind"] = float(df["wis_analogue"].sum()
                                                  / df["wis_blind"].sum())
        res["relwis_analogue_over_flat"] = float(df["wis_analogue"].sum()
                                                 / df["wis_flat"].sum())
        res["relwis_blind_over_flat"] = float(df["wis_blind"].sum()
                                              / df["wis_flat"].sum())
        by_h = df.groupby("horizon").apply(
            lambda g: g["wis_analogue"].sum() / g["wis_blind"].sum(),
            include_groups=False)
        res["by_horizon_analogue_over_blind"] = {int(k): round(float(v), 4)
                                                 for k, v in by_h.items()}
        res["median_calendar_donors"] = int(df["n_donors_calendar"].median())
        res["median_blind_donors"] = int(df["n_donors_blind"].median())
        # state-level bootstrap, same estimator the assessment used
        rng = np.random.default_rng(0)
        locs = df["location"].unique()
        boots = []
        for _ in range(2000):
            pick = rng.choice(locs, size=len(locs), replace=True)
            g = pd.concat([df[df["location"] == l] for l in pick])
            boots.append(g["wis_analogue"].sum() / g["wis_blind"].sum())
        lo, hi = np.percentile(boots, [2.5, 97.5])
        res["relwis_ci95"] = [float(lo), float(hi)]
    res["reference_settled_truth_august_boundary"] = 0.8121
    res["caveat"] = ("vintage anchors and the June boundary; the 0.812 "
                     "reference used settled truth and the August boundary, so "
                     "the two differ in two ways at once and the delta cannot "
                     "be attributed to either alone")
    df.to_csv(OUT / "analogue_vintage_cells.csv", index=False)
    sil.to_csv(OUT / "analogue_donor_availability.csv", index=False)
    (OUT / "analogue_vintage_true.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
