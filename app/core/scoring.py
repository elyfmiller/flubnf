"""PRODUCTION: WIS scoring and the frozen cell rule (server run scoring, retro,
playback, site_build).

WIS scoring of stored forecasts against truth: the report's accuracy
figures and the per-run WIS breakdown.

Settled truth available NOW for actuals, the FluSight baseline from the same
series; relWIS < 1 beats the baseline. Cells are (location, forecast_date,
horizon).

THE CELL RULE (restated by playback and retro): scored only when settled
truth exists and is positive, the model's median is positive, and a baseline
cell exists. The median condition drops a collapsed forecast's own cells
from both sums instead of penalising them as official FluSight scoring
would, so console and official relWIS may differ in value and cell count.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Mapping

import numpy as np
import pandas as pd

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL
from flubnf.wis import wis
from flubnf.settings import HUB


#: what the last load_truth() served: "settled", or "vintage <date>" when the
#: newest archived vintage stood in (surfaces print it: never a silent fallback)
TRUTH_SOURCE = "settled"


def load_truth() -> tuple:
    """(location_fips, week_ending Timestamp) -> value, from the hub's
    current target file; plus name->fips. Sets TRUTH_SOURCE."""
    global TRUTH_SOURCE
    target = HUB / "target-data/target-hospital-admissions.csv"
    TRUTH_SOURCE = "settled"
    if not target.is_file():
        # the newest vintage is settled for older weeks (retrospectives) but
        # provisional for its last 1-2: record the substitution and say so
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
    """The VALIDATED baseline construction (flubnf.baseline; a hand-rolled
    one scored ~40% easier). Raises when the clone lacks FluSight-baseline."""
    from flubnf.baseline import baseline_cells
    from flubnf.settings import HUB as _HUB
    if not (_HUB / "model-output" / "FluSight-baseline").is_dir():
        raise FileNotFoundError(
            "the hub clone has no model-output/FluSight-baseline (sparse "
            "checkout predates the baseline requirement). Press Update data "
            "on the Data tab to fetch it, then rescore.")
    b = baseline_cells([forecast_date], set(fips_set), truth, hub=_HUB)
    if b.empty:
        # early season (<5 history points): an empty frame has no columns
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
        for h in (0, 1, 2, 3):
            # canonical h is h+1 weeks past the as-of; ORIGIN is never scored
            arr = np.asarray(s.get(str(h), []), float)
            arr = arr[np.isfinite(arr)]
            actual = truth.get((fips, T + timedelta(days=7 * (h + 1))))
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
    df["base_wis"] = [bs.get((r.fips, forecast_date, r.horizon), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df


def score_quantiles(q_by_loc: Mapping, forecast_date: str,
                    name2fips: Mapping, truth: Mapping) -> pd.DataFrame:
    """score_samples for members stored as quantile sets, {location:
    {"0".."3": {level: value}}}: same cell rule, baseline and columns."""
    rows = []
    T = pd.Timestamp(forecast_date)
    for loc, qs in q_by_loc.items():
        fips = name2fips.get(loc)
        if not fips or not isinstance(qs, Mapping):
            continue
        for h in (0, 1, 2, 3):
            q = qs.get(str(h)) or qs.get(h)
            if not q:
                continue
            try:
                q = {float(L): float(v) for L, v in q.items()}
            except (TypeError, ValueError):
                continue
            actual = truth.get((fips, T + timedelta(days=7 * (h + 1))))
            if actual is None or actual <= 0 or q.get(0.5, 0) <= 0:
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
    df["base_wis"] = [bs.get((r.fips, forecast_date, r.horizon), np.nan)
                      for r in df.itertuples()]
    df = df.dropna(subset=["base_wis"])
    df["rel"] = df.wis / df.base_wis
    return df


#: the empty-table placeholder (the weekly report recognises it)
NO_SCORES_HTML = ("<p class='hint'>No scored weeks yet. relWIS appears once "
                  "truth for forecast weeks is published.</p>")


def summary_table_html(df: pd.DataFrame) -> str:
    """The report's WIS-breakdown card: the member named in the header,
    ok/bad classes, each score with its cell count; a placeholder when empty.
    The US row keeps its own (fitted) line but stays out of the pooled total
    (us_national.POOLED_INCLUDES_US)."""
    from app.core import us_national as usn
    if df.empty:
        return NO_SCORES_HTML
    try:                       # the shared name map, one source (no drift)
        from app.core.report_season import MODEL_NAMES
        member = MODEL_NAMES.get("pf", "Oracle SIHRS")
    except Exception:
        member = "Oracle SIHRS"
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
    # the total row names its scope when US is present
    total_label = ("All jurisdictions (US excluded)" if has_us
                   else "All locations")
    total_row = (
        f'<tr class="total"><td>{total_label}</td>{score_td(total)}'
        f'<td class="num hint">{len(pooled)}</td></tr>'
        if total is not None else "")
    note = (f'<p class="hint">{usn.POOLED_SCOPE_NOTE}</p>' if has_us else "")
    # disclose the cell rule where the counts render; the frame's own
    # truth_source stamp wins over the (racy) module global
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
