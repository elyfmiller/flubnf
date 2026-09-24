"""PRODUCTION: FluSight rate-change categories for every map and card (via
report.categorical_probs*, server) and the optional "wk flu hosp rate
change" pmf rows of a submission (submit.rate_change_rows).

The FluSight rate-trend categories, computed one way for every model.

The hub's "wk flu hosp rate change" target (FluSight-forecast-hub
model-output/README.md, "Rate-trend forecast specifications") classifies
the change from the baseline week (the week ending reference_date - 7,
this project's anchor, the as-of week) to the target week, in admissions
per 100,000 people:

  * stable: |count change| below 10 admissions, OR |rate change| below
    the horizon's stable cut;
  * increase / decrease: not stable, |rate change| up to the large cut;
  * large_increase / large_decrease: not stable, |rate change| past it.

Cuts by hub horizon (0 = the reference week): 0: 0.3/1.7; 1: 0.5/3;
2: 0.7/4; 3: 1/5. The boundaries are the hub's scoring code's
(target-data/get_target_data_hubverse.R, calc_oracle_output_rate_change):
both "below" tests are strict and "large" is a rate change strictly past
the large cut (the README says "larger than or equal to"; the code that
scores says ">", and a count change never lands exactly on a rate cut for
a real population).

Counts are whole numbers, so a category is a set of integer count changes
(`bins`): the continuous forecast X of a week is read as the count
round(X), whose CDF at an integer m is F(m + 1/2). A change of exactly
+10 is therefore never stable (it once read stable here, the only place
the rule was applied, so every map and file had it). The CDF is read at
those half-integer edges and differenced (`probs_from_cdf`), fed by either
samples (empirical CDF of the rounded draws) or a quantile grid
(piecewise-linear CDF), so no two models' categories are computed by two
rules. `category` classifies one observed change the way the hub does,
for checks against its oracle output.
"""
from __future__ import annotations

import math

import numpy as np

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")

#: hub horizon -> (stable cut, large cut), rate change per 100,000
RATE_CUTS = {0: (0.3, 1.7), 1: (0.5, 3.0), 2: (0.7, 4.0), 3: (1.0, 5.0)}

#: a count change below this is stable at every horizon, whatever the rate
COUNT_STABLE = 10.0


def _cuts(horizon) -> tuple:
    try:
        return RATE_CUTS[int(horizon)]
    except (KeyError, ValueError, TypeError):
        raise ValueError(f"hub horizon must be one of {sorted(RATE_CUTS)}, "
                         f"got {horizon!r}") from None


def cutpoints(population: float, horizon: int = 0) -> tuple:
    """(stable, large) as admission-count differences from the baseline
    week, for one jurisdiction and one hub horizon. Stable is the larger
    of the rate cut in counts and the count criterion (the hub's OR: a
    change below either is stable); large never falls below stable, so a
    jurisdiction small enough for the count criterion to swallow the
    increase band reads large for any change past stable."""
    lo_rate, hi_rate = _cuts(horizon)
    scale = float(population) / 1e5
    stable = max(lo_rate * scale, COUNT_STABLE)
    large = max(hi_rate * scale, stable)
    return stable, large


def bins(population: float, horizon: int = 0) -> tuple:
    """(s, L): the integer count changes d of each category. stable is
    |d| <= s; increase s < d < L; large_increase d >= L (decrease and
    large_decrease the mirror image). s + 1 <= L always."""
    lo_rate, hi_rate = _cuts(horizon)
    scale = float(population) / 1e5
    # |d| < max(10, lo * scale), strictly
    s = int(math.ceil(max(COUNT_STABLE, lo_rate * scale))) - 1
    # large: past stable and rate strictly above the large cut
    big = max(int(math.floor(hi_rate * scale)) + 1, s + 1)
    return s, big


def category(change: float, population: float, horizon: int = 0) -> str:
    """One count change's category, the hub scoring code's case_when on
    the rate (per 100,000) and the count."""
    lo, hi = _cuts(horizon)
    rate = float(change) / float(population) * 1e5
    if abs(change) < COUNT_STABLE or -lo < rate < lo:
        return "stable"
    if rate > hi:
        return "large_increase"
    if rate < -hi:
        return "large_decrease"
    return "increase" if rate > 0 else "decrease"


def probs_from_cdf(cdf, last_observed: float, population: float,
                   horizon: int = 0) -> dict:
    """The five probabilities from a CDF of the forecast week's count,
    `cdf(x) = P(X <= x)`, X read as the whole count round(X): the CDF is
    differenced at the half-integer edges of `bins` around the baseline
    count (itself a whole number). Clamped to [0, 1]; a CDF that is not
    monotone within floating error cannot produce a negative category."""
    s, big = bins(population, horizon)
    b = float(np.rint(float(last_observed)))
    F = {e: float(cdf(b + e)) for e in (-big + 0.5, -s - 0.5, s + 0.5,
                                        big - 0.5)}
    p = {
        "large_increase": 1.0 - F[big - 0.5],
        "increase": F[big - 0.5] - F[s + 0.5],
        "stable": F[s + 0.5] - F[-s - 0.5],
        "decrease": F[-s - 0.5] - F[-big + 0.5],
        "large_decrease": F[-big + 0.5],
    }
    return {c: min(1.0, max(0.0, v)) for c, v in p.items()}


def probs_from_samples(samples, last_observed: float, population: float,
                       horizon: int = 0) -> dict:
    """P(category) from forecast draws: the empirical CDF of the rounded
    draws at the edges. {} for no finite draws or no population."""
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if not s.size or population <= 0:
        return {}
    s = np.sort(np.rint(s))
    n = float(s.size)

    def cdf(x):
        return float(np.searchsorted(s, x, side="right")) / n
    return probs_from_cdf(cdf, float(last_observed), population, horizon)


def probs_from_changes(changes, population: float, horizon: int = 0) -> dict:
    """P(category) from draws of the count CHANGE itself (a path's target
    week minus the same path's baseline week), for a model whose baseline
    week is a forecast too. {} for no finite draws or no population."""
    return probs_from_samples(changes, 0.0, population, horizon)


def probs_from_quantiles(qmap: dict, last_observed: float, population: float,
                         horizon: int = 0) -> dict:
    """P(category) from a stored quantile grid {level: value}: the grid read
    as the forecast CDF, level a piecewise-linear function of value between
    the stored quantiles, and beyond the outermost ones (the FluSight
    grid's 1 and 99 percent levels) the outermost segment carried on to
    levels 0 and 1, never below a count of 0. Level keys may be float or
    str (results.json round-trips them as str). Ties in value (a partially
    degenerate grid) collapse to the highest level, the right-continuous
    reading. {} rather than invented numbers when the grid is unusable."""
    if not qmap or population <= 0:
        return {}
    try:
        pairs = sorted((float(v), float(l)) for l, v in qmap.items())
    except (TypeError, ValueError):
        return {}
    xs: list = []
    ls: list = []
    for v, l in pairs:
        if not np.isfinite(v):
            continue
        if xs and v <= xs[-1]:
            ls[-1] = max(ls[-1], l)
        else:
            xs.append(v)
            ls.append(l)
    if not xs:
        return {}
    if len(xs) >= 2:
        # the unmodeled tails: the outermost segment carried on to levels
        # 0 and 1 (never below a count of 0), rather than the tail mass
        # lumped at +/- infinity, where it would read as a large change
        # no count can make
        lo = xs[0] - (xs[1] - xs[0]) * ls[0] / max(ls[1] - ls[0], 1e-12)
        lo = max(lo, -0.5)
        if ls[0] > 0 and lo < xs[0]:
            xs.insert(0, lo)
            ls.insert(0, 0.0)
        hi = xs[-1] + (xs[-1] - xs[-2]) * (1 - ls[-1]) / max(
            ls[-1] - ls[-2], 1e-12)
        if ls[-1] < 1 and hi > xs[-1]:
            xs.append(hi)
            ls.append(1.0)

    def cdf(c: float) -> float:
        if len(xs) == 1:
            return 1.0 if c >= xs[0] else 0.0
        return float(np.interp(c, xs, ls))
    return probs_from_cdf(cdf, float(last_observed), population, horizon)
