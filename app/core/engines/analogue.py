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


def run(spec) -> dict:
    """location -> {horizon(str): {level(float): value}} quantiles."""
    v = vintage_path(spec.forecast_date)
    t = pd.read_csv(v, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    t = t[t.date <= pd.Timestamp(spec.forecast_date)]     # vintage honesty
    bank = AN.build_bank(t.itertuples())

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
        qs = {}
        for h in (1, 2, 3, 4):
            q = AN.forecast(anchor, T.date(), h, bank, QL)
            if q:
                qs[str(h)] = {float(L): float(x) for L, x in q.items()}
        if qs:
            out[loc] = qs
    return out
