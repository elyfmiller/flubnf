"""WIS scoring of stored forecasts against truth — feeds the report's
accuracy figures and the per-run WIS breakdown.

One formula, one vintage: every score uses the settled truth available NOW for
actuals, and the FluSight baseline built from the same series. relWIS < 1
beats the baseline. Cells are (location, forecast_date, horizon); a run is
scored only for weeks whose truth exists.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Mapping

import numpy as np
import pandas as pd

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
from flubnf.wis import wis
from flubnf.settings import HUB


def load_truth() -> tuple:
    """(location_fips, week_ending Timestamp) -> value, from the hub's
    current target file; plus name->fips."""
    t = pd.read_csv(HUB / "target-data/target-hospital-admissions.csv",
                    dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    locs = pd.read_csv(HUB / "auxiliary-data/locations.csv", dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    return truth, n2f


def _baseline_cells(forecast_date: str, fips_set, truth):
    """The VALIDATED baseline construction (scripts/anchor_analysis.py) --
    the hand-rolled version scored ~40% easier and was retired the day it
    was calibrated (2026-08-17)."""
    import importlib.util
    from pathlib import Path
    sp = importlib.util.spec_from_file_location(
        "aa", Path(__file__).resolve().parents[2] / "scripts/anchor_analysis.py")
    AA = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(AA)
    b = AA.baseline_cells([forecast_date], set(fips_set), truth)
    if b.empty:
        # early-season weeks: <5 history points -> no baseline, no cells.
        # An empty frame has no columns; guard or every caller crashes.
        return {}
    b["k"] = list(zip(b.location, b["asof"], b.horizon))
    s = b.set_index("k").wis
    return s[~s.index.duplicated()].to_dict()


def score_samples(samples_by_loc: Mapping, forecast_date: str,
                  name2fips: Mapping, truth: Mapping) -> pd.DataFrame:
    """rows: location, horizon, wis, base_wis, rel. Skips cells without truth."""
    rows = []
    T = pd.Timestamp(forecast_date)
    for loc, s in samples_by_loc.items():
        fips = name2fips.get(loc)
        if not fips:
            continue
        for h in (1, 2, 3, 4):
            arr = np.asarray(s.get(str(h), []), float)
            arr = arr[np.isfinite(arr)]
            actual = truth.get((fips, T + timedelta(days=7 * h)))
            if actual is None or actual <= 0 or not arr.size:
                continue
            q = {float(L): float(np.quantile(arr, L)) for L in QL}
            if q[0.5] <= 0:
                continue
            try:
                w = float(wis(q, actual).wis)
            except Exception:
                continue
            rows.append({"location": loc, "fips": fips, "horizon": h,
                         "wis": w})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    bs = _baseline_cells(forecast_date, set(df.fips), truth)
    df["base_wis"] = [bs.get((r.fips, forecast_date, r.horizon - 1), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df


def summary_table_html(df: pd.DataFrame) -> str:
    """The report's WIS-breakdown card. Empty df -> honest placeholder."""
    if df.empty:
        return ("<p class='hint'>No scored weeks yet — WIS appears once "
                "truth for forecast weeks is published.</p>")
    per_loc = (df.groupby("location")
                 .apply(lambda g: g.wis.sum() / g.base_wis.sum(),
                        include_groups=False)
                 .sort_values())
    total = df.wis.sum() / df.base_wis.sum()
    rows = "".join(f"<tr><td>{l}</td><td>{v:.3f}</td></tr>"
                   for l, v in per_loc.items())
    return (f"<table><tr><th>location</th><th>relWIS</th></tr>{rows}"
            f"<tr><th>all</th><th>{total:.3f}</th></tr></table>")
