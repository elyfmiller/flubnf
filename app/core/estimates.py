"""PRODUCTION: how long a run takes before it starts, from the engine's own
cost model (the Forecast, Retrospective and own-data Replay forms, with
static/estimate.js).

One estimate for every run form, so no page writes its own. A run fits
`fits` cells a week (locations x Independent Runs), dealt across `width`
runners that run at once, so a week costs ceil(fits / width) waves of one
cell each:

    seconds = sum over the weeks of ceil(fits / width) * pf.cell_seconds

pf.cell_seconds is the engine's cost model (fitted on the production
machine, linear in particles, PUBLIC_COST_RATIO times it on the public
engine, the Liu-West filter), the one runner._week_cost and
sandbox.eta_seconds use, so a refit of its constants reaches every form.

What the figure leaves out. The cost model times the fits alone: not
prepare (each location read and its network generated, one after another),
not the Oracle step and not the Groundhog. Slower computers run several
times the model (laptops 2.9 to 3.3 times it in the Sandbox walkthroughs;
the shipped 2024-25 replay ran 1.91 times it at width 8). So the 1x end of
a span is the cost model alone, a floor, and a page always shows the span
(span, then human), never the low end alone. Before this computer has a
recorded ratio, the span is sandbox.ETA_FIRST_SPAN times the model; with
one, the model times that ratio at both ends, as sandbox.eta_span does.

A run with no fits (the Groundhog alone) gets no figure here: the
Groundhog's time depends on how much data it searches, which the model
does not price, so human() says nothing for zero seconds rather than
"under a minute".

Width. The Forecast form runs at pf.shard_width() (FLUBNF_PF_WIDTH, else
pf.DEFAULT_SHARD_WIDTH): page_params(None) gives it. The Retrospective
form runs at its own width field: pass it. runner._week_cost uses
pf.DEFAULT_SHARD_WIDTH.

Weeks observed. n_obs_for counts the weeks from the season's start to the
anchor, as runner._week_n does: an upper bound, since prepare drops
unreported weeks and weeks_to_drop.

static/estimate.js (FluBNFEstimate) repeats every rule here in ES5, with
the same floating-point steps in the same order, reading the constants
from the data-est-* attributes page_params() gives, so a form recomputes
its line in the browser without a request. app/tests/test_estimates.py
holds the two equal.

Pure: no file is read or written, nothing is cached, and nothing here
changes a run.
"""
from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from app.core.engines import pf

#: the human text's switch to hours: from 90 minutes up (retro_progress.js
#: etaText's rule)
HOURS_FROM_S = 5400
#: below this many seconds at the high end, the human text is "under a
#: minute"
MINUTE_S = 60

#: the data-* attributes page_params() gives, in order
PARAM_NAMES = ("data-est-intercept", "data-est-per-week",
               "data-est-forecast-weeks", "data-est-reference-particles",
               "data-est-public-ratio", "data-est-first-span",
               "data-est-engine", "data-est-width")


def _first_span() -> tuple:
    """sandbox.ETA_FIRST_SPAN, read when asked (sandbox imports numpy;
    nothing here needs it until a span is wanted)."""
    from app.core import sandbox
    return tuple(sandbox.ETA_FIRST_SPAN)


def fit_seconds(n_obs: int, particles: int | None,
                engine: str | None = None) -> float:
    """Predicted seconds for one fit of `n_obs` observed weeks and
    `particles` particles (none: the model's reference, 10,000), on
    `engine` ("public" or "private"; by default the one this process
    runs): pf.cell_seconds itself."""
    return pf.cell_seconds({"n_obs": int(n_obs or 0),
                            "particles": int(particles or 0)}, engine)


def run_seconds(weeks_n_obs: Iterable[int], fits_per_week: int,
                particles: int | None, width: int | None = None,
                engine: str | None = None) -> float:
    """Predicted seconds for a run: over the weeks (each its own n_obs),
    ceil(fits_per_week / width) waves of fit_seconds. `width` None is
    pf.shard_width() (FLUBNF_PF_WIDTH, else pf.DEFAULT_SHARD_WIDTH); never
    below 1. The weeks are added one by one, as estimate.js adds them."""
    w = pf.shard_width(width)
    waves = -(-max(0, int(fits_per_week or 0)) // w)
    total = 0.0
    for n in weeks_n_obs:
        total += waves * fit_seconds(n, particles, engine)
    return total


def default_season_start(anchor: str) -> str:
    """August 1 of the anchor's season: runs.default_season_start."""
    from app.core import runs
    return runs.default_season_start(anchor)


def n_obs_for(anchor, season_start="") -> int:
    """Observed weeks at `anchor` (a YYYY-MM-DD Saturday) in a season
    starting `season_start` (blank: runs.default_season_start(anchor)):
    (anchor - start).days // 7 + 1, as runner._week_n counts, never below
    0. An upper bound: prepare drops unreported weeks and weeks_to_drop.
    ValueError for a blank or malformed anchor."""
    a = str(anchor or "")[:10]
    s = str(season_start or "")[:10] or default_season_start(a)
    n = (date.fromisoformat(a) - date.fromisoformat(s)).days // 7 + 1
    return max(0, n)


def round_tenth(x: float) -> float:
    """round(x, 1): Python's own rule (half to even on the exact value),
    named so estimate.js can name its copy."""
    return round(x, 1)


def span(seconds: float, ratio: float | None = None,
         first: tuple | None = None) -> tuple:
    """(low, high) seconds, rounded to 0.1 as sandbox.eta_span rounds: with
    this computer's recorded `ratio`, the model times it at both ends;
    without one, `first` (default sandbox.ETA_FIRST_SPAN) times the model.
    span(sandbox.eta_seconds(n, p), r) == sandbox.eta_span(n, p, r)."""
    lo, hi = (ratio, ratio) if ratio else (first or _first_span())
    return round_tenth(seconds * lo), round_tenth(seconds * hi)


def _js_fixed1(x: float) -> str:
    """JavaScript's x.toFixed(1) for x >= 0: the exact value rounded, a tie
    to the larger."""
    return str(Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _js_round(x: float) -> int:
    """JavaScript's Math.round(x) for x >= 0: a tie to the larger."""
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def human(lo: float, hi: float) -> str:
    """A span in words, by retro_progress.js etaText's rule after "about":
    the unit is the high end's, hours with one decimal from HOURS_FROM_S
    up, else whole minutes, never below 1; one figure when both ends read
    alike. "about 10 to 20 min", "about 1.5 to 6.0 h", "about 3 min";
    "under a minute" when 0 < hi < MINUTE_S; "" for no estimate (hi not
    above 0, or not finite)."""
    try:
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return ""
    if not (math.isfinite(lo) and math.isfinite(hi)) or not hi > 0:
        return ""
    if hi < MINUTE_S:
        return "under a minute"
    hours = hi >= HOURS_FROM_S

    def fmt(s: float) -> str:
        return (_js_fixed1(s / 3600) + " h" if hours
                else str(max(1, _js_round(s / 60))) + " min")

    a, b = fmt(max(0.0, lo)), fmt(max(0.0, hi))
    if a == b:
        return "about " + a
    return "about " + a.rsplit(" ", 1)[0] + " to " + b


def page_params(width: int | None = None,
                engine: str | None = None) -> dict:
    """The data-est-* attributes a form carries for estimate.js, as
    {attribute: text}: the cost model's constants, PUBLIC_COST_RATIO,
    ETA_FIRST_SPAN, the engine ("public" or "private"; by default the one
    this process runs) and the width (pf.shard_width(width): the Forecast
    form passes None, the Retrospective form its own width field). Floats
    are written with repr, so JavaScript reads back the same numbers. A
    fresh dict each call."""
    if engine is None:
        engine = "public" if pf._public() else "private"
    else:
        engine = "public" if engine == "public" else "private"
    lo, hi = _first_span()
    values = (repr(float(pf.COST_INTERCEPT_S)),
              repr(float(pf.COST_PER_WEEK_S)),
              str(int(pf.COST_FORECAST_WEEKS)),
              str(int(pf.COST_REFERENCE_PARTICLES)),
              repr(float(pf.PUBLIC_COST_RATIO)),
              f"{float(lo)!r} {float(hi)!r}",
              engine,
              str(pf.shard_width(width)))
    return dict(zip(PARAM_NAMES, values))
