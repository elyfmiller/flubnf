"""Calendar-conditioned empirical analogue forecaster.

Verified 2026-08-09 at real-time relWIS 0.665 on the 2025-26 season (2179 cells,
26 states, vintage anchors, scored against settled truth and the official
FluSight-baseline). SIHRS on the identical cells scores 0.918; the hub's
multi-team ensemble scores ~0.682.

THE METHOD
----------
For a target (state, as-of week T, horizon h):
    anchor   = the last OBSERVED value at T (vintage -- what was knowable)
    donors   = every (state', week W) from STRICTLY PRIOR seasons whose epiweek
               is within `bandwidth` weeks of T's epiweek
    ratios   = truth[state', W + 7h] / truth[state', W]
    forecast = anchor * quantiles(ratios)

Donors are pooled ACROSS states on purpose: per-state donors number about one
per prior season, which cannot support a 23-quantile predictive distribution.

WHY IT BEATS THE COMPARTMENTAL MODEL (measured, WIS decomposition)
-----------------------------------------------------------------
    component        SIHRS      analogue   ratio
    median error     266,232     201,864   0.758
    dispersion       546,044     672,640   1.232
    overprediction    11,966      52,576   4.394
    underprediction 1,492,128     251,288   0.168   <- the entire advantage

The analogue is WORSE on dispersion and 4x worse on overprediction. It wins
because SIHRS systematically forecasts too low and WIS punishes that
asymmetrically. Coverage tells the same story: SIHRS's central-95% interval is
WIDER than the analogue's (4.06 vs 3.09 relative to the actual) yet covers 87%
against 93% -- wide but misplaced, centred too low.

DEPENDS ON DONOR DEPTH -- do not assume it transfers
----------------------------------------------------
Measured by target season: 2023-24 -> 0.993, 2024-25 -> 0.813, 2025-26 -> 0.630.
With one or two prior seasons it is no better than the baseline. Its current
strength rests on four seasons of history.

TWO TRAPS, BOTH PAID FOR
------------------------
1. ANCHOR ALIGNMENT. Taking the anchor one week later than allowed improves the
   score from 0.665 to 0.488. A one-week look-ahead is worth 0.177 relWIS here,
   which is larger than most real effects in this project. `season_start` and
   the vintage file must correspond to the same as-of date.
2. NaN CONTAMINATION. `value <= 0` is False for NaN, so NaNs pass every naive
   filter, and `np.quantile` returns NaN for ALL levels if the array contains a
   single one. That silently produced a 100%-NaN control arm during
   verification. Every filter here is explicitly `np.isfinite`.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import NormalDist
from typing import Iterable, Mapping, Optional

import numpy as np

DEFAULT_BANDWIDTH = 2
MIN_DONORS = 30

_STD_NORMAL = NormalDist()


def epiweek(d: date) -> int:
    """CDC MMWR week number. Weeks end Saturday; week 1 ends on the first
    Saturday whose week contains >= 4 January days."""
    y = d.year
    for yy in (y + 1, y, y - 1):
        j = date(yy, 1, 1)
        wd = (j.weekday() + 1) % 7          # Sunday = 0
        start = date.fromordinal(j.toordinal() - wd + (7 if wd > 3 else 0))
        n = (d.toordinal() - start.toordinal()) // 7
        if 0 <= n < 53:
            return n + 1
    return -1


def season_of(d: date) -> int:
    """Influenza season label: Aug-Jul, named by the starting year."""
    return d.year if d.month >= 8 else d.year - 1


def calendar_distance(a: int, b: int, period: int = 52) -> int:
    """Circular distance between epiweeks -- weeks 52 and 1 are adjacent."""
    d = abs(a - b)
    return min(d, period - d)


def donor_ratios(bank: Mapping[tuple, float], target_epiweek: int,
                 target_season: int, horizon: int,
                 bandwidth: int = DEFAULT_BANDWIDTH,
                 allow_same_season: bool = False) -> np.ndarray:
    """Growth ratios at `horizon` weeks, from calendar-matched prior seasons.

    `allow_same_season` exists ONLY so tests can demonstrate that leaking the
    target season improves the score. It must never be True in production.
    """
    out = []
    for (loc, d), v0 in bank.items():
        if not np.isfinite(v0) or v0 <= 0:
            continue
        if not allow_same_season and season_of(d) >= target_season:
            continue
        if calendar_distance(epiweek(d), target_epiweek) > bandwidth:
            continue
        v1 = bank.get((loc, d + timedelta(days=7 * horizon)))
        if v1 is None or not np.isfinite(v1) or v1 <= 0:
            continue
        out.append(v1 / v0)
    arr = np.asarray(out, dtype=float)
    return arr[np.isfinite(arr)]


def analogue_quantiles(anchor: float, ratios: np.ndarray,
                       levels: Iterable[float], *,
                       completeness: Optional[float] = None,
                       widen_log_sd: Optional[float] = None) -> Optional[dict]:
    """Scale the anchor by the empirical ratio distribution.

    Returns None rather than a degenerate dict when the inputs cannot support a
    forecast -- callers must treat None as "no forecast", not as zero.

    `completeness` (Build 2, 2026-08-21 handoff section 4): the state's frozen
    first-issue/final ratio at lag 0. The anchor is divided by it, so a state
    whose newest point typically arrives at 93% of its settled value forecasts
    from anchor/0.93. None (the default) is byte-identical to the historical
    behavior. A non-finite or non-positive value raises: a broken correction
    table must fail loudly, not pass as a silent un-correction.

    `widen_log_sd`: residual uncertainty of the completeness correction, as a
    log-scale sd. Applied as q'(L) = q(L) * exp(z_L * widen_log_sd) with z_L
    the standard normal quantile of L -- the median is unchanged (z = 0),
    tails widen multiplicatively, monotonicity is preserved. None or 0.0 is
    byte-identical to the historical behavior.
    """
    if anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return None
    if completeness is not None:
        c = float(completeness)
        if not math.isfinite(c) or c <= 0:
            raise ValueError(f"completeness must be finite and > 0, got {c!r}")
        anchor = anchor / c
    r = np.asarray(ratios, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < MIN_DONORS:
        return None
    q = {float(L): float(anchor * np.quantile(r, L)) for L in levels}
    if widen_log_sd is not None:
        s = float(widen_log_sd)
        if not math.isfinite(s) or s < 0:
            raise ValueError(f"widen_log_sd must be finite and >= 0, got {s!r}")
        if s > 0:
            q = {L: v * math.exp(_STD_NORMAL.inv_cdf(L) * s)
                 for L, v in q.items()}
    if not np.isfinite(q.get(0.5, np.nan)) or q[0.5] <= 0:
        return None
    # np.quantile is monotone in L, and anchor > 0, so the result is already
    # sorted (the widening factor is itself increasing in L); assert rather
    # than sort, because a violation means a real bug.
    vals = [q[float(L)] for L in sorted(q)]
    if any(b < a - 1e-9 for a, b in zip(vals, vals[1:])):
        return None
    return q


def forecast(anchor: float, as_of: date, horizon: int,
             bank: Mapping[tuple, float], levels: Iterable[float],
             bandwidth: int = DEFAULT_BANDWIDTH, *,
             completeness: Optional[float] = None,
             widen_log_sd: Optional[float] = None) -> Optional[dict]:
    """One analogue predictive distribution. `bank` maps (location, date)->value.

    `completeness` / `widen_log_sd` pass through to `analogue_quantiles`;
    their None defaults keep this byte-identical to the historical path.
    """
    r = donor_ratios(bank, epiweek(as_of), season_of(as_of), horizon,
                     bandwidth=bandwidth)
    return analogue_quantiles(anchor, r, levels, completeness=completeness,
                              widen_log_sd=widen_log_sd)


def build_bank(truth_rows: Iterable) -> dict:
    """(location, date) -> value, with non-finite and non-positive dropped.

    Dropping here rather than at use is deliberate: a single NaN reaching
    np.quantile poisons every quantile it produces.
    """
    bank = {}
    for r in truth_rows:
        v = float(r.value)
        if np.isfinite(v) and v > 0:
            bank[(r.location, r.date)] = v
    return bank
