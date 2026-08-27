"""WIS scoring of stored forecasts against truth — feeds the report's
accuracy figures and the per-run WIS breakdown.

One formula, one vintage: every score uses the settled truth available NOW for
actuals, and the FluSight baseline built from the same series. relWIS < 1
beats the baseline. Cells are (location, forecast_date, horizon).

THE CELL RULE, in full (the frozen formula playback.py restates): a cell is
scored only when settled truth exists AND is positive, the model's own
forecast median is positive, and a baseline cell exists for the same key.
The middle condition means a fully collapsed forecast removes its own cells
from numerator and denominator rather than taking the penalty an official
FluSight evaluation would assign, so console relWIS and an official score
of the same submission can legitimately differ in both value and cell
count. Stated here because the docstrings used to mention only truth
availability, sending anyone reconciling the counts to debug the wrong
join (audit finding).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Mapping

import numpy as np
import pandas as pd

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
from flubnf.wis import wis
from flubnf.settings import HUB


#: what the last load_truth() call actually served: "settled", or
#: "vintage <date>" when the current target file was missing and the newest
#: archived vintage stood in. Surfaces read this so a fallback is never
#: silent (audit finding: the substitution had no warning, log entry, or
#: marker, and a vintage's last weeks carry provisional values).
TRUTH_SOURCE = "settled"


def load_truth() -> tuple:
    """(location_fips, week_ending Timestamp) -> value, from the hub's
    current target file; plus name->fips. Sets TRUTH_SOURCE."""
    global TRUTH_SOURCE
    target = HUB / "target-data/target-hospital-admissions.csv"
    TRUTH_SOURCE = "settled"
    if not target.is_file():
        # Sparse or stale hub clones sometimes lack the current target file.
        # The NEWEST dated vintage is settled truth for anything older than a
        # few months, which is exactly what retrospectives score against.
        # For LIVE scoring the newest 1-2 weeks of that vintage are
        # provisional, so the substitution is recorded and said out loud.
        from app.core.data import vintage_path, vintages
        vs = vintages()
        if not vs:
            raise FileNotFoundError(
                f"no settled truth: {target} missing and no dated vintages in "
                f"{HUB}/auxiliary-data/target-data-archive. Update the hub "
                "clone from the Data tab.")
        target = vintage_path(vs[-1])
        TRUTH_SOURCE = f"vintage {vs[-1]}"
        import sys
        print(f"scoring: current target file missing; scoring against the "
              f"newest archived vintage ({vs[-1]}). Its final weeks may be "
              "provisional. Update the hub clone from the Data tab.",
              file=sys.stderr)
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
    df -> honest placeholder.

    The US national row keeps its own line, labelled as fitted, but stays
    OUT of the pooled total under the named policy in app/core/us_national
    (POOLED_INCLUDES_US). The console run fits the national series on every
    run, so without that gate the pooled figure would silently become a
    53-location number dominated by a cell that is the sum of the other
    52."""
    from app.core import us_national as usn
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
    pooled = usn.pooled_frame(df)
    has_us = len(pooled) != len(df)
    total = (pooled.wis.sum() / pooled.base_wis.sum()) if len(pooled) else None

    def score_td(v):
        return f'<td class="num {"ok" if v < 1 else "bad"}">{v:.3f}</td>'

    def label_of(l):
        return (usn.SHORT_LABELS[usn.FITTED] if usn.is_us(l) else str(l))

    rows = "".join(
        f"<tr><td>{label_of(l)}</td>{score_td(v)}"
        f'<td class="num hint">{int(cells.get(l, 0))}</td></tr>'
        for l, v in per_loc.items())
    # the total row NAMES its scope: "All locations" is literally true when
    # no national row is present, and would be a lie the moment one is, so
    # a frame carrying US says outright that the row excludes it
    total_label = ("All jurisdictions (US excluded)" if has_us
                   else "All locations")
    total_row = (
        f'<tr class="total"><td>{total_label}</td>{score_td(total)}'
        f'<td class="num hint">{len(pooled)}</td></tr>'
        if total is not None else "")
    note = (f'<p class="hint">{usn.POOLED_SCOPE_NOTE}</p>' if has_us else "")
    # the cell rule, disclosed where the counts render: it used to live
    # only in code comments, and a reader reconciling these counts against
    # an official FluSight score had no way to see why they differ
    # the frame's own stamp wins: the module global can be rewritten by any
    # concurrent load_truth() between scoring and rendering
    src = getattr(df, "attrs", {}).get("truth_source", TRUTH_SOURCE)
    rule = ('<p class="hint">A cell is scored when settled truth exists and '
            'is positive, the forecast median is positive, and the baseline '
            'covers the same cell; official FluSight scoring keeps cells '
            'this rule drops, so counts can differ.'
            + (f" Truth source: {src}."
               if src != "settled" else "") + '</p>')
    return ('<table><thead><tr><th>Location</th>'
            f'<th class="num">{member} relWIS</th>'
            '<th class="num">Cells</th></tr></thead><tbody>'
            + rows + total_row + "</tbody></table>" + note + rule)
