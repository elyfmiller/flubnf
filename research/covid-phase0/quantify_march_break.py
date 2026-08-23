"""Is the 2026-03-21 -> 2026-03-28 43% fall a reporting change or real?

The memo flagged it and refused to score through it "until explained". This
script explains it. Four tests, in the order that makes the verdict falsifiable:

  1. SIZE. Where does the step sit in the distribution of week-over-week moves
     in the whole 84-vintage record? An epidemic that merely fell fast should
     not be an outlier among epidemic weeks.
  2. BREADTH. Is it one or two states, or most of them? A handful of states
     would point at those states' reporting.
  3. CO-MOVEMENT. NHSN measures COVID, influenza and RSV on ONE form. If all
     three step together the cause is the form, not the viruses. This is the
     decisive test and it is the one the memo did not have.
  4. COVERAGE. Did hospitals stop reporting? A collapse in the reporting
     denominator would explain a step without any change in case definition,
     and is a different finding with a different remedy.

Run:  .venv/bin/python research/covid-phase0/quantify_march_break.py
Writes research/covid-phase0/out/march_break.json.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flubnf import covid_vintage as cv                       # noqa: E402
from flubnf.reporting_breaks import (cross_pathogen_step,    # noqa: E402
                                     level_break_scan)
from flubnf.settings import HUB                              # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
LAST_CLEAN = "2026-03-21"
FIRST_SHIFTED = "2026-03-28"
SOCRATA = "https://data.cdc.gov/resource/mpgq-jmmr.json?"


def us_settled() -> pd.DataFrame:
    df = cv.vintage_frame(cv.vintages()[-1])
    return df[df["location"] == "US"].sort_values("date").reset_index(drop=True)


def nhsn_national(start: str = "2026-01-01", end: str = "2026-06-01") -> pd.DataFrame:
    """The reporting-coverage columns the hub's own file does not carry."""
    cols = ("weekendingdate,totalconfc19newadm,totalconfc19newadmhosprep,"
            "totalconfflunewadm,totalconfflunewadmhosprep,totalconfrsvnewadm,"
            "totalconfrsvnewadmhosprep,numinptbedshosprep")
    q = {"$select": cols,
         "$where": (f"weekendingdate >= '{start}T00:00:00' and "
                    f"weekendingdate <= '{end}T00:00:00' and jurisdiction='USA'"),
         "$order": "weekendingdate", "$limit": "500"}
    rows = json.load(urllib.request.urlopen(SOCRATA + urllib.parse.urlencode(q),
                                            timeout=120))
    df = pd.DataFrame(rows)
    df["week"] = df["weekendingdate"].str[:10]
    for c in df.columns:
        if c.startswith("total") or c.startswith("num"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict = {"window": [LAST_CLEAN, FIRST_SHIFTED]}

    # 1. SIZE
    us = us_settled()
    scan = level_break_scan(us["date"], us["value"])
    res["size"] = {
        "n_weeks": int(len(us)),
        "robust_sd_of_residual": scan[0].robust_sd if scan else None,
        "worst_down_excursions": [
            {"week": c.week, "ratio": round(c.ratio, 4),
             "excess_log": round(c.excess_log, 4),
             "excess_pct": round(c.excess_pct, 4), "z": round(c.z, 2)}
            for c in scan[:5]],
    }
    res["size"]["is_the_largest"] = bool(scan and scan[0].week == FIRST_SHIFTED)

    # 2. BREADTH
    settled = cv.vintage_frame(cv.vintages()[-1])
    piv = settled.pivot_table(index="date", columns="location", values="value")
    piv = piv.drop(columns=[c for c in piv.columns if c == "US"])
    drop = piv.loc[FIRST_SHIFTED] / piv.loc[LAST_CLEAN]
    prev = piv.loc[LAST_CLEAN] / piv.loc["2026-03-14"]
    res["breadth"] = {
        "states": int(drop.notna().sum()),
        "median_step_ratio": float(np.nanmedian(drop)),
        "median_previous_week_ratio": float(np.nanmedian(prev)),
        "n_below_0.75": int((drop < 0.75).sum()),
        "n_below_0.60": int((drop < 0.60).sum()),
        "jurisdictions_reporting": {w: int(piv.loc[w].notna().sum())
                                    for w in ("2026-03-14", LAST_CLEAN,
                                              FIRST_SHIFTED, "2026-04-04")},
    }

    # 3 + 4. CO-MOVEMENT and COVERAGE
    try:
        nat = nhsn_national()
        res["co_movement"] = cross_pathogen_step(
            nat, FIRST_SHIFTED, LAST_CLEAN,
            ["totalconfc19newadm", "totalconfflunewadm", "totalconfrsvnewadm"],
            reporting_col="totalconfc19newadmhosprep")
        res["coverage"] = {
            w: {"hospitals_reporting": int(r["totalconfc19newadmhosprep"]),
                "beds_reporting": int(r["numinptbedshosprep"])}
            for w, r in nat.set_index("week").iterrows()
            if w in ("2026-03-07", "2026-03-14", LAST_CLEAN, FIRST_SHIFTED,
                     "2026-04-04")}
    except Exception as exc:
        res["co_movement"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    # cross-check against the FluSight hub's own truth file, a separate artifact
    try:
        f = pd.read_csv(HUB / "target-data/target-hospital-admissions.csv",
                        dtype={"location": str})
        f["date"] = f["date"].astype(str).str[:10]
        fs = f[(f["location"] == "US")].set_index("date")["value"]
        res["flusight_cross_check"] = {
            "flu_ratio_from_the_flusight_hub":
                float(fs[FIRST_SHIFTED] / fs[LAST_CLEAN])}
    except Exception as exc:
        res["flusight_cross_check"] = {"error": str(exc)[:200]}

    # 5. was it there in the first issue, or introduced by a revision?
    parq = cv._frame()
    g = parq[(parq["location"] == "US")
             & (parq["target_end_date"] == FIRST_SHIFTED)].sort_values("as_of")
    p = parq[(parq["location"] == "US")
             & (parq["target_end_date"] == LAST_CLEAN)].sort_values("as_of")
    res["first_issue"] = {
        "as_of": str(g["as_of"].iloc[0]),
        "first_issue_ratio": float(g["observation"].iloc[0]
                                   / p["observation"].iloc[0]),
        "settled_ratio": float(g["observation"].iloc[-1]
                               / p["observation"].iloc[-1]),
        "note": ("a step present in the first issue was visible to real-time "
                 "forecasters; a step introduced by revision was not"),
    }

    cm = res.get("co_movement", {})
    res["verdict"] = cm.get("verdict", "NOT ATTRIBUTABLE (Socrata unavailable)")
    res["action"] = ("exclude every scored cell whose anchor week <= "
                     f"{LAST_CLEAN} and whose target_end_date >= {FIRST_SHIFTED}; "
                     "keep cells wholly on one side, where the level shift is "
                     "common to model and truth")
    (OUT / "march_break.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
