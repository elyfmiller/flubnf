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

HOW IT COMPARES TO THE COMPARTMENTAL MODEL (measured, WIS decomposition)
------------------------------------------------------------------------
Alpha-weighted additive components, summed over the sealed archive: three
seasons, 52 jurisdictions, 16,775 filter cells and 16,978 analogue cells, on
the SHIPPED donor pool. The four rows sum to each column's total WIS.

    component        SIHRS      analogue   ratio
    median error      71,766      73,660   1.026
    dispersion       563,049     373,570   0.663
    overprediction   182,914     122,990   0.672
    underprediction  309,739     555,283   1.793
    TOTAL          1,127,467   1,125,503   0.998

Read this carefully, because it does NOT say what an earlier version of this
docstring said. Pooled over the whole archive the two members are very nearly
TIED, 0.998 on raw WIS and 0.7723 against 0.7746 on relWIS. Neither "beats"
the other in any general sense; they alternate by season, which is the actual
reason the blend is worth having.

Where they differ is in the shape of the loss, and the direction is the
opposite of what was previously recorded. The analogue is BETTER on dispersion
and BETTER on overprediction, and it is WORSE on underprediction by a factor
of 1.8. It is not the case that the analogue wins by escaping a SIHRS
low-forecasting bias.

RETRACTION, 2026-08-24. This table previously read 266,232 / 546,044 / 11,966
/ 1,492,128 against 201,864 / 672,640 / 52,576 / 251,288, and concluded that
underprediction was "the entire advantage". Those figures came from a
2,179-cell, 26-state, single-season pilot dated 2026-08-09 and were presented
as a general result. Recomputed over the full sealed archive every ratio moves
and three of the four reverse direction, so the conclusion drawn from them
does not hold. Do not carry the old table or its explanation into any
write-up.

What DOES survive is the directional observation, which is real but smaller
than the retracted claim implied: the filter's median sits below truth in
60.5 percent of cells against the analogue's 54.3, with median log bias -0.155
against -0.066. The filter does forecast low. That is simply not what drives
the difference in WIS.

DEPENDS ON DONOR COMPOSITION, NOT DONOR DEPTH
----------------------------------------------
An earlier version of this section read "DEPENDS ON DONOR DEPTH" and cited
0.993 / 0.813 / 0.630 by target season as evidence that the member needs many
prior seasons. The depth control run for the 2021-22 exclusion disproves that
reading: randomly subsampling the full pool to a smaller pool of the same size
moves the score by 0.199 percent, while changing WHICH seasons are in the pool
moves it by 17.64 percent. Donor count is close to free at these pool sizes.
The by-season series above is real, but it reflects which seasons were
available to donate, not how many donors there were.

The 0.665 anchor-alignment figure elsewhere in this module was also measured
on the UNRESTRICTED pool, before the 2021-22 exclusion adopted on 2026-08-24,
and is a historical record of that configuration.

THE 2021-22 DONOR EXCLUSION (adopted 2026-08-24)
------------------------------------------------
Season 2021-22 is excluded from the donor pool. `DONOR_SEASON_EXCLUSIONS` is
the registry, `EXCLUDED_DONOR_SEASONS` is the default `donor_ratios` applies,
and `SEASON_2021_22_CALENDAR_INVERSION` carries the full provenance. The short
version, because a donor pool that quietly differs from the published one is
the worst failure available here:

  MECHANISM. 2021-22 peaked at epiweek 16 (2022-04-23); the other four donor
  seasons peaked between epiweek 48 and epiweek 6. The archived NHSN series
  begins 2022-02-05, so the archive holds only that season's Feb-Jul tail. A
  calendar-matched pool asks "what happened in March" and 2021-22 answers
  "the epidemic was still growing": its March donor ratios have median
  1.36-1.50 against 0.50-0.83 for every other season, q97.5 6.94-9.00
  against 2.00-2.68. The season is calendar-INVERTED, not merely unusual.

  EFFECT. Pre-registered, hash 8f3c7a45a989e905, full grid, 15,460 cells.
  Shipped 50/50 ensemble 0.7039 -> 0.6781 pooled, +3.66 percent, positive in
  4000 of 4000 clustered bootstrap replicates. Analogue member 0.8290 ->
  0.7723 pooled. No cell is gained or lost: the restricted pool's smallest
  donor count is 223 against MIN_DONORS = 30, so the analogue is never
  silenced by the exclusion.

  COMPOSITION, NOT COUNT. The control that makes the claim answerable.
  On the 9,363 cells where the exclusion actually removes donors, randomly
  subsampling the FULL pool to the restricted pool's size moves the score
  +0.199 percent, while removing 2021-22 moves it +17.64 percent. The gain
  is which donors are dropped, not how many.

  SCOPE. The exclusion is an influenza season LABEL under the 1 August
  boundary, not a date range. It is not portable to another disease's
  calendar; see `resolve_donor_exclusions` and `flubnf.profiles`.

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
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist
from typing import Iterable, Mapping, Optional

import numpy as np

DEFAULT_BANDWIDTH = 2
MIN_DONORS = 30

#: Month whose first day opens a new influenza season label. This module's
#: `season_of` IS this boundary; `flubnf.profiles.INFLUENZA` mirrors it and
#: tests/test_profiles.py asserts the two agree on every day of twelve years.
#: A donor-season exclusion is a label under THIS boundary and no other.
SEASON_BOUNDARY_MONTH = 8

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
    return d.year if d.month >= SEASON_BOUNDARY_MONTH else d.year - 1


def calendar_distance(a: int, b: int, period: int = 52) -> int:
    """Circular distance between epiweeks -- weeks 52 and 1 are adjacent."""
    d = abs(a - b)
    return min(d, period - d)


# ---------------------------------------------------------------------------
# Donor-season exclusions
# ---------------------------------------------------------------------------
# A season may leave the donor pool ONLY through a registered record. The
# pattern is deliberately the one `flubnf.profiles.ExcludedWindow` already
# uses for scoring exclusions, and for the same reason: an exclusion that
# leaves no trace is indistinguishable from a bug.

@dataclass(frozen=True)
class DonorSeasonExclusion:
    """One season removed from the analogue's donor pool, with its evidence.

    `profile_key` and `season_boundary_month` are not decoration. A season
    LABEL only means a stretch of calendar relative to some boundary, and the
    boundary differs by disease (influenza 1 August, COVID 1 June). Applying
    an influenza label under COVID's boundary would silently remove the wrong
    weeks rather than none, so `resolve_donor_exclusions` refuses to apply a
    record whose boundary is not this module's.
    """
    season: int
    label: str
    profile_key: str
    season_boundary_month: int
    #: The calendar stretch the label covers under that boundary, inclusive.
    covers: tuple
    prereg_hash: str
    tested_on: str
    adopted_on: str
    mechanism: str
    effect: str
    depth_control: str
    evidence: str


SEASON_2021_22_CALENDAR_INVERSION = DonorSeasonExclusion(
    season=2021,
    label="2021-22",
    profile_key="influenza",
    season_boundary_month=SEASON_BOUNDARY_MONTH,
    covers=(date(2021, 8, 1), date(2022, 7, 31)),
    prereg_hash="8f3c7a45a989e905",
    tested_on="2026-08-24",
    adopted_on="2026-08-24",
    mechanism=(
        "Calendar inversion. 2021-22 peaked at epiweek 16 (2022-04-23) while "
        "the other four donor seasons peaked between epiweek 48 and epiweek "
        "6, and the archived NHSN series begins 2022-02-05, so the archive "
        "holds only that season's Feb-Jul tail. A calendar-matched donor pool "
        "asks what happened in March; 2021-22 answers that the epidemic was "
        "still growing. Its March donor ratios have median 1.36-1.50 against "
        "0.50-0.83 for every other season, and q97.5 6.94-9.00 against "
        "2.00-2.68."),
    effect=(
        "Full grid, 15,460 cells, three sealed seasons. Shipped 50/50 "
        "ensemble pooled relWIS 0.7039 -> 0.6781, +3.66 percent; paired "
        "cluster bootstrap on as-of dates (4000 replicates, 76 clusters) "
        "95 percent CI +1.83 to +6.07 percent, better in 4000 of 4000 "
        "replicates. Analogue member pooled 0.8290 -> 0.7723, +6.83 percent, "
        "and improves in all three seasons independently "
        "(+5.44 / +9.49 / +3.11 percent). Cell count is unchanged: the "
        "restricted pool's smallest donor count is 223 against MIN_DONORS "
        "= 30, so no forecast is silenced."),
    depth_control=(
        "The effect is COMPOSITION, not count. On the 9,363 cells where the "
        "exclusion actually removes donors, randomly subsampling the full "
        "pool to the restricted pool's size (10 seeds) moves the score "
        "+0.199 percent, while removing 2021-22 moves it +17.64 percent."),
    evidence=(
        "Pre-registered harness, arm A2, at "
        "~/Documents/FluBNF-local/donor-floor/harness.py with results in "
        "out/results.json and out/bootstrap.json. Its control arm A0 "
        "reproduces the sealed analogue quantiles to 0.0 and the sealed "
        "member WIS to 3.05e-10. The bootstrap endpoints are Monte Carlo and "
        "wander by about 0.1 percentage points across seeds; the point "
        "estimate and the sign do not."),
)


#: The ONLY seasons that may be dropped, keyed by season label. Adding a key
#: here is the whole cost of excluding another season, and it is meant to be
#: expensive: the record must carry a pre-registration hash, a mechanism, a
#: measured effect and a depth control before anything can use it.
DONOR_SEASON_EXCLUSIONS: dict = {
    SEASON_2021_22_CALENDAR_INVERSION.season: SEASON_2021_22_CALENDAR_INVERSION,
}

#: What `donor_ratios` applies when the caller says nothing. The default is the
#: exclusion rather than the empty set on purpose: forgetting the argument must
#: not silently restore the donor pool that every published figure moved away
#: from. Reintroducing 2021-22 requires writing `exclude_seasons=()`.
EXCLUDED_DONOR_SEASONS = frozenset(DONOR_SEASON_EXCLUSIONS)


def resolve_donor_exclusions(exclude_seasons: Iterable[int]) -> frozenset:
    """Validate a donor-season exclusion set, LOUDLY. Returns season labels.

    Closes two failure modes, in both directions:

    * Excluding a season with no registered record. A donor pool that quietly
      differs from the published one produces numbers nobody can reproduce, so
      an unregistered season raises rather than silently narrowing the pool.
    * Applying an exclusion minted under another disease's calendar. Season
      labels are boundary-relative: under influenza's 1 August rule label 2021
      is 2021-08-01 to 2022-07-31, while under COVID's 1 June rule the same
      label is 2021-06-01 to 2022-05-31. This function owns the influenza
      boundary (`season_of`), so it refuses any record minted under another.
    """
    seasons = frozenset(int(s) for s in exclude_seasons)
    unknown = sorted(seasons - frozenset(DONOR_SEASON_EXCLUSIONS))
    if unknown:
        raise ValueError(
            f"donor season(s) {unknown} are not registered in "
            f"flubnf.analogue.DONOR_SEASON_EXCLUSIONS. A season may only "
            f"leave the donor pool through a DonorSeasonExclusion record "
            f"carrying its pre-registration, mechanism, measured effect and "
            f"depth control. Registered: {sorted(DONOR_SEASON_EXCLUSIONS)}")
    foreign = sorted(
        s for s in seasons
        if DONOR_SEASON_EXCLUSIONS[s].season_boundary_month
        != SEASON_BOUNDARY_MONTH)
    if foreign:
        raise ValueError(
            f"donor season(s) {foreign} were registered under a season "
            f"boundary this module does not implement. flubnf.analogue."
            f"season_of is influenza's month-{SEASON_BOUNDARY_MONTH} rule; a "
            f"label minted under a different boundary names a different "
            f"stretch of calendar and would remove the wrong weeks.")
    return seasons


def donor_ratios(bank: Mapping[tuple, float], target_epiweek: int,
                 target_season: int, horizon: int,
                 bandwidth: int = DEFAULT_BANDWIDTH,
                 allow_same_season: bool = False, *,
                 exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS
                 ) -> np.ndarray:
    """Growth ratios at `horizon` weeks, from calendar-matched prior seasons.

    `allow_same_season` exists ONLY so tests can demonstrate that leaking the
    target season improves the score. It must never be True in production.

    `exclude_seasons` defaults to `EXCLUDED_DONOR_SEASONS`, which is the
    shipped donor pool: every strictly prior season EXCEPT 2021-22. Pass `()`
    to restore the unrestricted pool that figures published before 2026-08-24
    were measured on, and pass another profile's set (see `flubnf.profiles`)
    when forecasting a disease whose seasons this module does not label. Every
    value is checked against the registry by `resolve_donor_exclusions`, so an
    unregistered or foreign-calendar season raises instead of quietly changing
    which donors survive.
    """
    drop = resolve_donor_exclusions(exclude_seasons)
    out = []
    for (loc, d), v0 in bank.items():
        if not np.isfinite(v0) or v0 <= 0:
            continue
        s = season_of(d)
        if not allow_same_season and s >= target_season:
            continue
        if s in drop:
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
             widen_log_sd: Optional[float] = None,
             exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS
             ) -> Optional[dict]:
    """One analogue predictive distribution. `bank` maps (location, date)->value.

    `completeness` / `widen_log_sd` pass through to `analogue_quantiles`;
    their None defaults keep this byte-identical to the historical path.

    `exclude_seasons` passes through to `donor_ratios` and defaults to the
    shipped pool, which excludes 2021-22.
    """
    r = donor_ratios(bank, epiweek(as_of), season_of(as_of), horizon,
                     bandwidth=bandwidth, exclude_seasons=exclude_seasons)
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
