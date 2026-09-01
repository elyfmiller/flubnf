"""The calendar-analogue engine: instant, pure-python, no workroot needed
beyond a place to write its quantiles.

Wraps flubnf.analogue at its DEFAULT_BANDWIDTH and its shipped donor pool;
neither is overridden or restated here, so the engine cannot disagree with
the library about what production runs. The bandwidth's value and provenance
live beside flubnf.analogue.DEFAULT_BANDWIDTH. Returns QUANTILES per
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
    This path is DORMANT: no shipped configuration sets these keys, and
    both pre-registered completeness corrections were tested and killed
    (docs/RELEASE-1.0.md, the two reporting-completeness entries).

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
    # Trims move the ANCHOR back, exactly as they move the PF's fit origin:
    # the ratios then span h + k weeks so every labelled horizon still
    # lands on as-of + 7h. Two trims combine per state: the operator's
    # weeks_to_drop, and the nowcast rule (drop_same_day, OFF by default
    # since the 2026-08-27 v1.1 measurement; see RunSpec.drop_same_day).
    # Before this the analogue ignored both trims, anchoring on the very
    # week the fit dropped and desyncing the members (audit finding).
    # With both off the arithmetic is byte-identical to the historical path.
    k_user = int(getattr(spec, "weeks_to_drop", 0) or 0)
    drop_same = bool(getattr(spec, "drop_same_day", False))
    for loc in spec.locations:
        fips = name2fips.get(loc)
        if fips is None:
            continue
        g = t[t.location == fips].sort_values("date")
        vals = pd.to_numeric(g.value, errors="coerce").dropna()
        auto = 1 if (drop_same and len(vals)
                     and g.date.loc[vals.index[-1]] == T) else 0
        k = k_user + auto
        if k:
            vals = vals.iloc[:-k] if len(vals) > k else vals.iloc[0:0]
        if not len(vals):
            continue                                       # gap: engine skips, report shows it
        anchor = float(vals.iloc[-1])
        anchor_date = g.date.loc[vals.index[-1]]
        window_ref = (T - pd.Timedelta(days=7 * k)).date()
        c, sig = completeness_args(spec, fips, anchor_date, newest)
        qs = {}
        for h in (1, 2, 3, 4):
            # Donor pool: AN.forecast's default, which is every strictly prior
            # season EXCEPT 2021-22 (flubnf.analogue.EXCLUDED_DONOR_SEASONS,
            # adopted 2026-08-24). Deliberately not restated as a literal here
            # -- the engine must not be able to disagree with the library about
            # which pool production uses.
            q = AN.forecast(anchor, window_ref, h + k, bank, QL,
                            completeness=c, widen_log_sd=sig)
            if q:
                qs[str(h)] = {float(L): float(x) for L, x in q.items()}
        if qs:
            out[loc] = qs
    return out
