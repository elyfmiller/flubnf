"""Exogenous national-growth term for the per-state particle filter (BUILD 1).

WHAT THIS IS
------------
Leave-one-out national log-growth of admissions at week *t* predicts a state's
own growth at *t+1* after controlling for the state's AR(1) **and** the Fourier
seasonal the PF already carries (`eps1`/`phi1`). Partial correlation +0.469;
LOSO turn-week RMSE reductions +8.9% / +2.4% / +14.7% across the three seasons.
Nothing in the production system sees "the Midwest peaked last week": the PF is
a per-state filter and the analogue pools *prior* seasons, calendar-matched.

See `research/spatial-nowcast-probe/FINDINGS.md` section 1 and the handoff
`research/2026-08-21-HANDOFF.md` section 3.

THE FORM, AND WHY IT IS ON GROWTH
---------------------------------
    beta_s(t)  *=  exp( iota * ( g_nat^{-s}(t) - g_s^obs(t) ) )

specified on **growth**, never on level. A level-form importation term
`sum_s' w_ss' * A_s'/N_s'` restates prevalence, which the filter already has --
the occupancy-ratio trap. The DIFFERENCE form is neutral by construction: when
a state grows at the national rate the multiplier is exactly 1, so the term can
only speak when this state and the country disagree.

Zero new fitted parameters. `iota` is FROZEN a priori (below). Per-state
filters, particle count, jitter and the other five parameters are untouched;
the ODEs are not coupled.

VINTAGE DISCIPLINE
------------------
Both series are computed from ONE vintage file -- the caller passes
`app.core.data.vintage_path(asof)`, never the latest file. Every jurisdiction's
growth at week *w* is therefore exactly what was knowable on the as-of date,
including the incomplete last point. That is deliberate: the production filter
sees the same incomplete last point in its own likelihood, so the two agree.

FORECAST WEEKS -- THE PRE-REGISTERED RULE
-----------------------------------------
`g_nat` at horizons 1..4 is unknown at forecast time. **The last observed
(g_nat - g_s) gap is held constant across the 1 to 4 week horizon.** No
extrapolation, no decay toward zero, no forecast of the national series. This
rule is fixed before any fit and is restated in the template header and in the
generated model file so a materialized cell states its own convention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace as _dc_replace
from pathlib import Path

import numpy as np
import pandas as pd

# =====================================================================
# FROZEN CONSTANT -- derived once, before any PF run, never refitted.
# =====================================================================
#: Coupling strength on the national/own growth gap.
#:
#: DERIVATION (reproduce with
#: `./.venv/bin/python research/spatial-nowcast-probe/iota_freeze.py`):
#: OLS of next-week own log-growth on leave-one-out population-weighted
#: national log-growth, given own lag-1 growth and a first Fourier harmonic on
#: week-of-season -- the same design matrix `probe.py::spatial()` measured the
#: effect with. Fitted separately on each of the two seasons the handoff names:
#:
#:     2023-24   n=1393   b[g_nat] = 0.7574
#:     2024-25   n=1418   b[g_nat] = 0.4504
#:     mean                          0.6039
#:     x 0.5 shrink toward zero  ->  0.3020
#:
#: (Cross-check: pooling those two seasons into one fit gives b = 0.5528, so
#: 0.276 -- the same number to within the season-to-season spread. 2025-26 is
#: NOT in the average; its own coefficient, 0.8040, is recorded only so a
#: reader can see that excluding it made the constant smaller, not larger.)
#:
#: HONEST NOTE ON EFFECTIVE STRENGTH. `iota` multiplies beta, not the growth
#: rate. Near the current operating point a multiplier exp(iota*gap) changes
#: the weekly log-growth by roughly (beta*s0)*iota*gap = gamma*Reff*iota*gap,
#: and gamma is 2.19/week. So the implemented response is ~0.66 per unit gap,
#: i.e. the x0.5 shrink is approximately cancelled by that amplification and
#: the term lands near 1.0x the regression coefficient rather than 0.5x. The
#: recipe is the handoff's, verbatim, and the number is frozen as specified;
#: this note exists so nobody reads 0.302 as "half strength" when reporting
#: the arm. If the arm is over-powered at the gate, that is the reason.
IOTA_FROZEN: float = 0.302

#: Weekly admissions below this are not a growth signal, they are counting
#: noise (Alaska's whole season peaks at 64). `probe.py` used the same idea
#: with a floor of 20 on the epidemic weeks it regressed; production runs
#: every week of every state, so the floor is lower and its only job is to
#: keep log-ratios of 1-vs-3 admissions out of the model. A week under the
#: floor yields NO growth value, which downstream becomes gap = 0 (neutral).
MIN_LEVEL: float = 5.0

#: Jurisdictions that must contribute a defined growth before a national
#: leave-one-out value is used at all. Below this the "national wave" is a few
#: small states and the term stays silent.
MIN_PEERS: int = 20

#: Hard bound on |g_nat - g_s|, in log-growth units, applied BEFORE `iota`.
#: This is a stiffness guard, not a tuning knob: beta enters the model as
#: beta0*exp(...), the amplitude bounds on `eps1` are already documented as
#: stiffness-critical, and one state reporting 2 admissions after 40 would
#: otherwise hand exp() an argument no ODE solver should see. At the frozen
#: iota a clipped gap is a beta multiplier of exp(+-0.302) = [0.74, 1.35].
#: Weeks where it binds are counted and reported, never silently absorbed.
GAP_CLIP: float = 1.0

#: Model-file tokens this module resolves. Kept here so the template and the
#: materialize path cannot drift apart.
TOKEN_IOTA = "{{IOTA}}"
TOKEN_GAPEXPR = "{{GAPEXPR}}"
TOKEN_GAPNOTE = "{{GAPNOTE}}"


@dataclass
class GrowthGap:
    """One state's national-growth gap series, as of one vintage.

    `gap[w]` is the value that applies on model time [w, w+1) -- the growth
    realised up to and including observation week `w`, which is strictly
    causal for the interval that follows it. `last_week` is the final observed
    week offset; `gap[last_week]` is what the forecast holds constant.
    """
    state: str
    fips: str
    as_of: str
    weeks: np.ndarray = field(repr=False)     # 0..last_week, contiguous
    g_own: np.ndarray = field(repr=False)     # NaN where undefined
    g_nat: np.ndarray = field(repr=False)     # NaN where undefined
    gap: np.ndarray = field(repr=False)       # clipped; 0.0 where undefined
    clipped: np.ndarray = field(repr=False)   # bool: GAP_CLIP bound this week
    n_peers: np.ndarray = field(repr=False)   # jurisdictions behind g_nat
    last_week: int

    @property
    def n_active(self) -> int:
        """Weeks where the term is not the identity."""
        return int((self.gap != 0.0).sum())

    @property
    def n_clipped(self) -> int:
        """Weeks where the stiffness guard bound. Reported, never hidden."""
        return int(self.clipped.sum())

    @property
    def last_gap(self) -> float:
        """The gap held constant over the 1..4 week forecast horizon."""
        return float(self.gap[self.last_week]) if self.gap.size else 0.0

    def truncate(self, last_week: int) -> "GrowthGap":
        """Re-anchor the forecast hold at `last_week`.

        `RunSpec.weeks_to_drop` and dropped NaN weeks both mean the filter's
        real final observation can sit earlier than the last row in the
        vintage. The hold branch must begin where the FORECAST begins, or the
        first forecast week would silently take a gap the filter never
        assimilated. Truncating is exact -- gap[w] depends only on weeks w-1
        and w, so shortening the series changes no retained value.

        A `last_week` beyond the series (no data to truncate) extends it by
        repeating the final gap, which is the hold rule applied one week
        earlier and therefore the same convention.
        """
        target = int(last_week)
        if target < 0:
            raise ValueError(f"last_week must be >= 0, got {last_week}")
        if target == self.last_week:
            return self
        if target < self.last_week:
            sl = slice(0, target + 1)
            weeks, g_own, g_nat = self.weeks[sl], self.g_own[sl], self.g_nat[sl]
            gap, clipped, n_peers = (self.gap[sl], self.clipped[sl],
                                     self.n_peers[sl])
        else:
            pad = target - self.last_week
            nan = np.full(pad, np.nan)
            weeks = np.arange(target + 1, dtype=int)
            g_own = np.concatenate([self.g_own, nan])
            g_nat = np.concatenate([self.g_nat, nan])
            gap = np.concatenate([self.gap,
                                  np.full(pad, self.last_gap, dtype=float)])
            clipped = np.concatenate([self.clipped,
                                      np.zeros(pad, dtype=bool)])
            n_peers = np.concatenate([self.n_peers, np.zeros(pad, dtype=int)])
        return _dc_replace(self, weeks=weeks, g_own=g_own, g_nat=g_nat,
                           gap=gap, clipped=clipped, n_peers=n_peers,
                           last_week=target)


def _week_offsets(dates: pd.Series, season_start: str) -> np.ndarray:
    return ((pd.to_datetime(dates) - pd.Timestamp(season_start)).dt.days // 7
            ).to_numpy(dtype=int)


def _log_growth(by_week: dict, min_level: float) -> dict:
    """{week: value} -> {week: log-growth vs the IMMEDIATELY preceding week}.

    A week whose predecessor is absent (NHSN's 2024 reporting pause leaves real
    holes) yields no growth value rather than a growth computed across the gap.
    Both endpoints must clear `min_level`.
    """
    out = {}
    for w, v in by_week.items():
        p = by_week.get(w - 1)
        if p is None:
            continue
        if not (np.isfinite(v) and np.isfinite(p)):
            continue
        if v < min_level or p < min_level:
            continue
        out[w] = float(np.log(v) - np.log(p))
    return out


def growth_gap_series(state: str, *, truth_csv: str | Path,
                      locations_csv: str | Path, season_start: str,
                      as_of: str, min_level: float = MIN_LEVEL,
                      min_peers: int = MIN_PEERS,
                      clip: float = GAP_CLIP) -> GrowthGap:
    """Build one state's (g_nat - g_s) gap series from a SINGLE truth vintage.

    `truth_csv` must be `app.core.data.vintage_path(as_of)`. Passing the latest
    file would make every historical week look settled, which is look-ahead.

    Only weeks in [season_start, as_of] are read, for every jurisdiction, so
    the national series is as-of-consistent with the state's own.
    """
    locs = pd.read_csv(locations_csv, dtype={"location": str})
    locs["location"] = locs["location"].str.zfill(2)
    row = locs[locs.location_name == state]
    if row.empty:
        raise KeyError(f"{state!r} not in {locations_csv}")
    fips = str(row.iloc[0]["location"]).zfill(2)
    pops = {r.location: float(r.population) for r in locs.itertuples()
            if str(r.location).upper() != "US" and pd.notna(r.population)}

    t = pd.read_csv(truth_csv, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"])
    t["value"] = pd.to_numeric(t["value"], errors="coerce")
    t = t[(t.location.str.upper() != "US")
          & (t.date >= pd.Timestamp(season_start))
          & (t.date <= pd.Timestamp(as_of))]
    if t.empty:
        raise ValueError(f"no rows in {truth_csv} for "
                         f"{season_start}..{as_of}")
    t = t.assign(w=_week_offsets(t["date"], season_start))

    # per-jurisdiction {week: value} -> {week: log-growth}
    growth: dict = {}
    for loc_id, g in t.groupby("location"):
        if loc_id not in pops:
            continue                     # not a FluSight jurisdiction
        by_week = {int(w): float(v) for w, v in zip(g.w, g.value)}
        gr = _log_growth(by_week, min_level)
        if gr:
            growth[loc_id] = gr

    own = growth.get(fips, {})
    own_weeks = {int(w) for w in t.loc[t.location == fips, "w"]}
    if not own_weeks:
        raise ValueError(f"no observations for {state} in "
                         f"{season_start}..{as_of}")
    last_week = int(max(own_weeks))
    weeks = np.arange(last_week + 1, dtype=int)

    g_own = np.full(weeks.size, np.nan)
    g_nat = np.full(weeks.size, np.nan)
    n_peers = np.zeros(weeks.size, dtype=int)
    for w in weeks:
        if w in own:
            g_own[w] = own[w]
        num = den = 0.0
        k = 0
        for loc_id, gr in growth.items():
            if loc_id == fips or w not in gr:
                continue                 # LEAVE ONE OUT: never own state
            p = pops[loc_id]
            num += p * gr[w]
            den += p
            k += 1
        n_peers[w] = k
        if k >= min_peers and den > 0:
            g_nat[w] = num / den

    raw = g_nat - g_own                  # NaN wherever either side is missing
    gap = np.where(np.isfinite(raw), raw, 0.0)
    clipped = np.abs(gap) > clip
    gap = np.clip(gap, -clip, clip)
    return GrowthGap(state=state, fips=fips, as_of=str(as_of), weeks=weeks,
                     g_own=g_own, g_nat=g_nat, gap=gap, clipped=clipped,
                     n_peers=n_peers, last_week=last_week)


# ---------------------------------------------------------------------
# BNGL rendering
# ---------------------------------------------------------------------
_SAFE_EXPR = re.compile(r"^[0-9eE_.+\-*/(),<t if]*$")


def bngl_gap_expression(gg: GrowthGap, decimals: int = 6) -> str:
    """The gap as a piecewise-constant BNGL function of the model clock `t`.

    Every value is known at materialize time, so this is a literal nested
    `if()` -- BNGL's conditional, verified to survive BNG2.pl network
    generation AND bngsim's code-generated RHS (both paths reproduce an exact
    piecewise-exponential analytic solution).

    Alignment. The filter integrates one segment per observation, [w-1, w], so
    the value on [w-1, w) is `gap[w-1]`: the growth realised BEFORE that week
    began. Strictly causal, no look-ahead.

    Forecast. The final branch has no upper guard, so every t >= last_week
    takes `gap[last_week]` -- the pre-registered "hold the last observed gap
    constant across the 1 to 4 week horizon" rule, expressed as the structure
    of the expression rather than as a separate code path.

    Runs of equal values are merged, which collapses the (silent) pre-season
    zeros and keeps the nesting depth to the number of DISTINCT weekly values.
    """
    vals = [round(float(v), decimals) for v in gg.gap]
    if not vals:
        return "0.0"
    # run-length compress: (upper_bound_exclusive, value)
    runs: list = []
    for w, v in enumerate(vals):
        if runs and runs[-1][1] == v:
            runs[-1][0] = w + 1
        else:
            runs.append([w + 1, v])
    # the last run extends to +infinity (the forecast hold)
    expr = f"{runs[-1][1]:.{decimals}f}"
    for upper, v in reversed(runs[:-1]):
        expr = f"if(t<{int(upper)},{v:.{decimals}f},{expr})"
    if not _SAFE_EXPR.match(expr):
        raise ValueError(f"refusing to emit a non-numeric gap expression: "
                         f"{expr[:120]}")
    return expr


def natg_note(gg: GrowthGap, iota: float) -> str:
    """One BNGL comment line recording what this cell's term actually is."""
    return (f"as-of {gg.as_of}; iota {iota:g} FROZEN; last observed week "
            f"{gg.last_week}; gap held at {gg.last_gap:+.4f} over h=1..4; "
            f"{gg.n_active}/{gg.weeks.size} weeks active; "
            f"{gg.n_clipped} clipped at +-{GAP_CLIP:g}")


def natg_tokens(gg: GrowthGap, iota: float = IOTA_FROZEN) -> dict:
    """`materialize_model(extra_tokens=...)` payload for SIHRS_pop_natg.bngl."""
    return {TOKEN_IOTA: f"{float(iota):.6g}",
            TOKEN_GAPEXPR: bngl_gap_expression(gg),
            TOKEN_GAPNOTE: natg_note(gg, iota)}
