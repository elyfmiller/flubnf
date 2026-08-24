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
    target = HUB / "target-data/target-hospital-admissions.csv"
    if not target.is_file():
        # Sparse or stale hub clones sometimes lack the current target file.
        # The NEWEST dated vintage is settled truth for anything older than a
        # few months, which is exactly what retrospectives score against.
        from app.core.data import vintage_path, vintages
        vs = vintages()
        if not vs:
            raise FileNotFoundError(
                f"no settled truth: {target} missing and no dated vintages in "
                f"{HUB}/auxiliary-data/target-data-archive. Update the hub "
                "clone from the Data tab.")
        target = vintage_path(vs[-1])
    t = pd.read_csv(target, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    locs = pd.read_csv(HUB / "auxiliary-data/locations.csv", dtype=str)
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    truth = {(r.location, r.date): float(r.value)
             for r in t.itertuples() if np.isfinite(r.value)}
    return truth, n2f


def _baseline_cells(forecast_date: str, fips_set, truth):
    """The VALIDATED baseline construction -- the hand-rolled version scored
    ~40% easier and was retired the day it was calibrated (2026-08-17).

    It lives in flubnf.baseline. It used to be loaded out of
    scripts/anchor_analysis.py by path, which raised FileNotFoundError on
    every pip-installed copy (no wheel carries scripts/) and re-executed a
    217-line analysis module on every call."""
    from flubnf.baseline import baseline_cells
    from flubnf.settings import HUB as _HUB
    if not (_HUB / "model-output" / "FluSight-baseline").is_dir():
        raise FileNotFoundError(
            "the hub clone has no model-output/FluSight-baseline (sparse "
            "checkout predates the baseline requirement). Press Update data "
            "on the Data tab to fetch it, then rescore.")
    b = baseline_cells([forecast_date], set(fips_set), truth, hub=_HUB)
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
    """The report's WIS-breakdown card, under the one-relWIS rule: the
    member is named in the header, every score wears the ok/bad
    below-1-beats-baseline classes, the table style supplies tabular
    numerals, and each score states the cell count it rests on. Empty
    df -> honest placeholder."""
    if df.empty:
        return ("<p class='hint'>No scored weeks yet. relWIS appears once "
                "truth for forecast weeks is published.</p>")
    try:                       # the shared name map, one source (no drift)
        from app.core.report_season import MODEL_NAMES
        member = MODEL_NAMES.get("pf", "PF-SIHRS")
    except Exception:
        member = "PF-SIHRS"
    per_loc = (df.groupby("location")
                 .apply(lambda g: g.wis.sum() / g.base_wis.sum(),
                        include_groups=False)
                 .sort_values())
    cells = df.groupby("location").size()
    total = df.wis.sum() / df.base_wis.sum()

    def score_td(v):
        return f'<td class="num {"ok" if v < 1 else "bad"}">{v:.3f}</td>'

    rows = "".join(
        f"<tr><td>{l}</td>{score_td(v)}"
        f'<td class="num hint">{int(cells.get(l, 0))}</td></tr>'
        for l, v in per_loc.items())
    return ('<table><thead><tr><th>Location</th>'
            f'<th class="num">{member} relWIS</th>'
            '<th class="num">Cells</th></tr></thead><tbody>'
            + rows
            + f'<tr class="total"><td>All locations</td>{score_td(total)}'
            f'<td class="num hint">{len(df)}</td></tr></tbody></table>')
