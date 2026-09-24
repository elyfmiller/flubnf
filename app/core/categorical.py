"""PRODUCTION: FluSight rate-change categories for every map and card (via
report.categorical_probs*, server).

The FluSight rate-trend categories, computed one way for every model.

The hub's "wk flu hosp rate change" target (FluSight-forecast-hub
model-output/README.md) classifies a forecast week by its change from the
baseline week (the last reported week, this project's anchor):

  * stable: |rate change| below the horizon's stable cut (per 100k) OR
    |count change| below 10 admissions;
  * increase / decrease: not stable, |rate change| below the large cut;
  * large_increase / large_decrease: at or above it.

Cuts by hub horizon (0 = one week ahead): 0: 0.3/1.7; 1: 0.5/3; 2: 0.7/4; 3: 1/5.

As in the CDC's report code, the CDF is read at the cutpoints and
differenced (`probs_from_cdf`), fed by either samples (empirical CDF) or a
quantile grid (piecewise-linear CDF), so no two models' categories are
computed by two rules.
"""
from __future__ import annotations

import numpy as np

CATS = ("large_decrease", "decrease", "stable", "increase", "large_increase")

#: hub horizon -> (stable cut, large cut), rate change per 100,000
RATE_CUTS = {0: (0.3, 1.7), 1: (0.5, 3.0), 2: (0.7, 4.0), 3: (1.0, 5.0)}

#: a count change below this is stable at every horizon, whatever the rate
COUNT_STABLE = 10.0


def cutpoints(population: float, horizon: int = 0) -> tuple:
    """(stable, large) as admission-count differences from the baseline
    week, for one jurisdiction and one hub horizon. Stable is the larger
    of the rate cut in counts and the count criterion (the hub's OR: a
    change below either is stable); large never falls below stable, so a
    jurisdiction small enough for the count criterion to swallow the
    increase band reads large for any change past stable."""
    try:
        lo_rate, hi_rate = RATE_CUTS[int(horizon)]
    except (KeyError, ValueError, TypeError):
        raise ValueError(f"hub horizon must be one of {sorted(RATE_CUTS)}, "
                         f"got {horizon!r}") from None
    scale = float(population) / 1e5
    stable = max(lo_rate * scale, COUNT_STABLE)
    large = max(hi_rate * scale, stable)
    return stable, large


def probs_from_cdf(cdf, last_observed: float, population: float,
                   horizon: int = 0) -> dict:
    """The five probabilities from a CDF of the forecast week's count,
    `cdf(x) = P(count <= x)`, by differencing it at the cutpoints around
    the baseline value. Clamped to [0, 1]; a CDF that is not monotone
    within floating error cannot produce a negative category."""
    s, big = cutpoints(population, horizon)
    F = {d: float(cdf(last_observed + d)) for d in (-big, -s, s, big)}
    p = {
        "large_increase": 1.0 - F[big],
        "increase": F[big] - F[s],
        "stable": F[s] - F[-s],
        "decrease": F[-s] - F[-big],
        "large_decrease": F[-big],
    }
    return {c: min(1.0, max(0.0, v)) for c, v in p.items()}


def probs_from_samples(samples, last_observed: float, population: float,
                       horizon: int = 0) -> dict:
    """P(category) from forecast draws: the empirical CDF at the cutpoints.
    {} for no finite draws or no population."""
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if not s.size or population <= 0:
        return {}
    s.sort()
    n = float(s.size)

    def cdf(x):
        return float(np.searchsorted(s, x, side="right")) / n
    return probs_from_cdf(cdf, float(last_observed), population, horizon)


def probs_from_quantiles(qmap: dict, last_observed: float, population: float,
                         horizon: int = 0) -> dict:
    """P(category) from a stored quantile grid {level: value}: the grid read
    as the forecast CDF, level a piecewise-linear function of value between
    the stored quantiles and clamped at the outermost levels (with the
    23-level FluSight grid the unmodeled tails clamp at the 1 percent
    levels). Level keys may be float or str (results.json round-trips them
    as str). Ties in value (a partially degenerate grid) collapse to the
    highest level, the right-continuous reading. {} rather than invented
    numbers when the grid is unusable."""
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

    def cdf(c: float) -> float:
        if len(xs) == 1:
            return 1.0 if c >= xs[0] else 0.0
        return float(np.interp(c, xs, ls))
    return probs_from_cdf(cdf, float(last_observed), population, horizon)
