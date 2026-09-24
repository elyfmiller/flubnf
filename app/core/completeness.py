"""RESEARCH (not on the shipped path): reached only through the spec.extra keys
analogue_completeness (engines/analogue.py) and pf_mean_scale_column
(engines/pf.py); no shipped configuration sets them.

Real-time reporting completeness c_k(v) by lag, pooled across jurisdictions.

c_k(v) = median, over (jurisdiction, week) pairs formed from vintages dated
<= v, of value(week, vintage at lag k) / value(week, v), for weeks of the
current season whose lag-k vintage is >= MATURITY_WEEKS older than v and whose
value in v is >= MIN_VALUE. Nothing dated after v is read. Lags 0-2 carry a
factor (older rows are complete at the median); older lags, and lags with
< MIN_PAIRS pairs, carry 1. Pooled, never per state: the per-state forms were
rejected (docs/archive/RELEASE-1.0.md).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

LAGS = (0, 1, 2)
MATURITY_WEEKS = 4
MIN_PAIRS = 30
MIN_VALUE = 20.0
CLIP = (0.5, 1.05)
#: the .exp column the engine key pf_mean_scale_column names
COLUMN = "completeness"


class Archive:
    """The vintage archive as the factor sees it: a sorted list of dates
    and a frame (date, location, value) per date. The default reads
    app.core.data; a test injects its own dates and loader."""

    def __init__(self, dates=None, loader=None):
        self._dates = dates
        self._loader = loader

    def dates(self) -> list:
        if self._dates is not None:
            return sorted(str(d) for d in self._dates)
        from app.core import data
        return data.vintages()

    def load(self, date: str) -> pd.DataFrame:
        if self._loader is not None:
            return _with_dates(self._loader(date))
        return _load_cached(date)


def _with_dates(df: pd.DataFrame) -> pd.DataFrame:
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df = df.assign(date=pd.to_datetime(df["date"]))
    return df


@lru_cache(maxsize=None)
def _load_cached(date: str) -> pd.DataFrame:
    from app.core import data
    df = data.load_vintage(date)
    return _with_dates(df[["date", "location", "value"]].copy())


def _week_values(df: pd.DataFrame, week) -> pd.Series:
    g = df[(df["date"] == week) & (df["location"] != "US")]
    return pd.Series(g["value"].to_numpy(dtype=float),
                     index=g["location"].to_numpy())


def factors(asof: str, season_start: str, archive: Archive | None = None, *,
            lags=LAGS, maturity_weeks: int = MATURITY_WEEKS,
            min_pairs: int = MIN_PAIRS, min_value: float = MIN_VALUE,
            clip=CLIP) -> dict:
    """{"factors": {k: c_k}, "pairs": {k: n}, "raw": {k: median or None}}
    for as-of date `asof`, from vintages dated at or before it only."""
    arc = archive or Archive()
    V, S = pd.Timestamp(asof), pd.Timestamp(season_start)
    horizon = V - pd.Timedelta(days=7 * maturity_weeks)
    dates = [d for d in arc.dates() if S <= pd.Timestamp(d) <= horizon]
    ratios = {k: [] for k in lags}
    if dates:
        mature = arc.load(asof)
        for d in dates:
            early = arc.load(d)
            for k in lags:
                w = pd.Timestamp(d) - pd.Timedelta(days=7 * k)
                if w < S:
                    continue
                e, m = _week_values(early, w), _week_values(mature, w)
                m = m[m >= min_value]
                j = e.index.intersection(m.index)
                if not len(j):
                    continue
                r = e.loc[j].to_numpy() / m.loc[j].to_numpy()
                ratios[k].extend(float(x) for x in r[np.isfinite(r)])
    out = {"asof": str(asof), "season_start": str(season_start),
           "factors": {}, "pairs": {}, "raw": {}}
    for k in lags:
        n = len(ratios[k])
        out["pairs"][k] = n
        if n >= min_pairs:
            med = float(np.median(ratios[k]))
            out["raw"][k] = med
            out["factors"][k] = float(min(max(med, clip[0]), clip[1]))
        else:
            out["raw"][k] = None
            out["factors"][k] = 1.0
    return out


@lru_cache(maxsize=None)
def factors_cached(asof: str, season_start: str) -> dict:
    """factors() on the real archive, once per (as-of, season start) per
    process: every cell of a week and the analogue member share it."""
    return factors(asof, season_start)


def row_scales(times, asof_off: int, fac: dict) -> list:
    """The multiplier for each fit row: c_lag for lag = asof_off - t when
    a factor exists for that lag, else 1."""
    f = fac["factors"]
    return [float(f.get(int(asof_off) - int(t), 1.0)) for t in times]
