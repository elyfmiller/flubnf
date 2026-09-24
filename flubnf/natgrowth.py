"""SHIPPED (loaded by the PF engine for its 'natg' research variant).

Exogenous national-growth term for the per-state particle filter (BUILD 1).

Leave-one-out national log-growth at week *t* predicts a state's own growth
at *t+1* beyond its AR(1) and the PF's Fourier seasonal (partial correlation
+0.469). Nothing else in the product sees "the Midwest peaked last week":
the PF is per-state and the analogue pools prior seasons.

THE FORM: specified on growth, never level (a level importation term only
restates prevalence the filter already has):

    beta_s(t)  *=  exp( iota * ( g_nat^{-s}(t) - g_s^obs(t) ) )

The difference is neutral by construction (multiplier 1 when the state
grows at the national rate). Zero new fitted parameters: `iota` is FROZEN a
priori; the ODEs stay uncoupled.

VINTAGE: both series come from ONE vintage file (the caller passes
`app.core.data.vintage_path(asof)`), incomplete last point included, the
same point the filter's likelihood sees.

FORECAST (pre-registered): **The last observed (g_nat - g_s) gap is held
constant across the 1 to 4 week horizon.** No extrapolation or decay. The
rule is restated in the template header and each generated model file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace as _dc_replace
from pathlib import Path

import numpy as np
import pandas as pd

#: Coupling on the national/own growth gap, FROZEN a priori, never refitted:
#: 0.5 x the mean OLS coefficient of next-week own log-growth on LOO national
#: log-growth (given own lag-1 growth and a first harmonic) over 2023-24
#: (0.7574) and 2024-25 (0.4504); 2025-26 (0.8040) excluded.
#: iota multiplies beta, so the realized log-growth response is about
#: gamma*Reff*iota ~ 0.66 per unit gap: do not report 0.302 as "half strength".
IOTA_FROZEN: float = 0.302

#: Admissions below this are counting noise, not growth (keeps 1-vs-3 log
#: ratios out). A week under it yields no growth value, i.e. gap = 0.
MIN_LEVEL: float = 5.0

#: Jurisdictions with a defined growth needed before a national LOO value is
#: used; with fewer the "national wave" is a few small states.
MIN_PEERS: int = 20

#: Hard bound on |g_nat - g_s| (log-growth), applied BEFORE `iota`: an ODE
#: stiffness guard, not a tuning knob (beta multiplier within [0.74, 1.35]
#: at the frozen iota). Binding weeks are counted and reported.
GAP_CLIP: float = 1.0

#: Model-file tokens this module resolves (one definition for template and
#: materialize path).
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

        The filter's final observation can precede the vintage's last row
        (weeks_to_drop, NaN weeks); the hold must start where the FORECAST
        starts. Truncating is exact (gap[w] depends only on weeks w-1, w). A
        `last_week` beyond the series repeats the final gap (the hold rule).
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

    A week whose predecessor is absent (e.g. NHSN's 2024 pause) yields no
    value, not a growth across the gap. Both endpoints must clear `min_level`.
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

    `truth_csv` must be `app.core.data.vintage_path(as_of)`; the latest file
    would be look-ahead. Only weeks in [season_start, as_of] are read, for
    every jurisdiction.
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

    A literal nested `if()` (verified through both BNG2.pl network
    generation and bngsim's generated RHS). The value on [w-1, w) is
    `gap[w-1]`, growth realised before that week began: strictly causal.
    The final branch has no upper guard, so t >= last_week holds
    `gap[last_week]` (the pre-registered hold rule). Runs of equal values are
    merged, so nesting depth is the number of distinct values.
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
