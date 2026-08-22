"""The calendar-analogue engine: instant, pure-python, no workroot needed
beyond a place to write its quantiles.

Wraps flubnf.analogue with the LOSO-frozen bandwidth. Returns QUANTILES per
horizon (the analogue is quantile-native); the ensemble vincentizes them with
the PF's sample-derived quantiles directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from flubnf import analogue as AN                     # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL # noqa: E402
from app.core.data import LOCATIONS, vintage_path     # noqa: E402


def completeness_args(spec, fips: str, anchor_date, newest_date) -> tuple:
    """(completeness, widen_log_sd) for one state, or (None, None).

    Build 2 (2026-08-21 handoff section 4): a frozen per-state first-issue
    completeness table may ride in `spec.extra["analogue_completeness"]`
    ({fips: c}), with the residual widening sd in
    `spec.extra["analogue_widen_log_sd"]`. The correction applies ONLY when
    the state's anchor is the vintage's newest week (lag 0) -- an older
    anchor is already near settled (lag-2 median vintage/final is 1.000 in
    every measured season) and must be neither scaled nor widened.

    Specs without `extra`, or without the keys, return (None, None), which
    leaves flubnf.analogue byte-identical to the pre-Build-2 path.
    """
    extra = getattr(spec, "extra", None) or {}
    cmap = extra.get("analogue_completeness") or {}
    c = cmap.get(fips)
    if c is None or anchor_date != newest_date:
        return None, None
    sig = extra.get("analogue_widen_log_sd") or None
    return float(c), (float(sig) if sig else None)


def run(spec) -> dict:
    """location -> {horizon(str): {level(float): value}} quantiles."""
    v = vintage_path(spec.forecast_date)
    t = pd.read_csv(v, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    t = t[t.date <= pd.Timestamp(spec.forecast_date)]     # vintage honesty
    bank = AN.build_bank(t.itertuples())
    newest = t.date.max()                                  # current report week

    locs = pd.read_csv(LOCATIONS, dtype=str)
    name2fips = dict(zip(locs.location_name, locs.location))

    out = {}
    T = pd.Timestamp(spec.forecast_date)
    for loc in spec.locations:
        fips = name2fips.get(loc)
        if fips is None:
            continue
        g = t[t.location == fips].sort_values("date")
        vals = pd.to_numeric(g.value, errors="coerce").dropna()
        if not len(vals):
            continue                                       # gap: engine skips, report shows it
        anchor = float(vals.iloc[-1])
        anchor_date = g.date.loc[vals.index[-1]]
        c, sig = completeness_args(spec, fips, anchor_date, newest)
        qs = {}
        for h in (1, 2, 3, 4):
            q = AN.forecast(anchor, T.date(), h, bank, QL,
                            completeness=c, widen_log_sd=sig)
            if q:
                qs[str(h)] = {float(L): float(x) for L, x in q.items()}
        if qs:
            out[loc] = qs
    return out
