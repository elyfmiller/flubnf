"""Calendar-conditioned empirical analogue forecaster.

Pilot verification 2026-08-09, real-time relWIS 0.665 on the 2025-26 season
(2,179 cells, 26 states, vintage anchors, scored against settled truth and the
official FluSight-baseline; SIHRS on the identical cells scored 0.918, the
hub's multi-team ensemble ~0.682). That pilot figure was later understood to
be flattered by the bandwidth choice; the validation of record is the sealed
full-grid figure below (0.7723 pooled on the shipped donor pool).

THE METHOD
----------
For a target (state, as-of week T, horizon h):
    anchor   = the last OBSERVED value at T (vintage -- what was knowable)
    donors   = every (state', week W) from STRICTLY PRIOR seasons whose epiweek
               is within `bandwidth` weeks of T's epiweek
    ratios   = truth[state', W + 7h] / truth[state', W]
    forecast = anchor * quantiles(ratios)

Donors are pooled ACROSS states on purpose: per-state donors number about
five per prior season under the two-week calendar window, which cannot
support a 23-quantile predictive distribution.

That pool also carries the US national row, which the vintage files hold as
one more location. The US national row is the sum of the 52 jurisdictions, so
it is not independent of them; on a representative date it supplied 15 of 793
donors. Keeping it was measured against removing it over all 85 archived
as-of weeks of the three resealed seasons, on identical cells: pooled
analogue relWIS 0.7714 with the row against 0.7717 without it, and 0.7233
against 0.7234 for the shipped ensemble. That is a tie inside the
pre-registered 0.001 band, so the shipped pool keeps the row and this
paragraph is where it says so. The pre-registration and the results are in
the lab archive (research/us-donor, 2026-09-08), not in this repository.

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
  "the epidemic was still growing": it is the only donor season whose March
  ratios have a median above one (1.27 in the 2026-08-26 settled-truth
  recomputation, every other season at or below 1.00), with an upper tail
  more than twice as heavy as any other season's (q97.5 7.0 vs 3.0
  next-highest). Exact ranges depend on how the March pool is defined, so
  the claim is stated at the strength at which it reproduces. The season is
  calendar-INVERTED, not merely unusual.

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
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import NormalDist
from typing import Iterable, Mapping, Optional

import numpy as np

# PROVENANCE OF THE BANDWIDTH, stated because every sealed analogue and
# ensemble number was computed at this value and the record on it is mixed.
#   (a) 2 is the value the seal ran at. On the sealed shipped-pool record
#       (ratio of sums vs FluSight-baseline, US excluded) the analogue member
#       scores 1.045 / 0.756 / 0.621 by season at this bandwidth.
#   (b) The pre-seal sweep on the superseded pipeline (lab archive, not
#       in this repository; "Corrections worth remembering" item 1)
#       found the per-season optimum reverses season to season; the honest
#       out-of-season selection there picked +/-8, which scored 0.806 held
#       out on 2025-26, versus 0.665 at +/-2 and 0.547 at the in-season
#       oracle +/-1. The +0.259 gap recorded there is honest-vs-oracle, not
#       the cost of choosing 2.
#   (c) The bandwidth has NOT been re-selected on the current pipeline and
#       shipped donor pool. Changing it invalidates the sealed record, so the
#       re-selection decision belongs to the lead, not to a quiet edit here.
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
    """Circular distance between epiweeks -- weeks 52 and 1 are adjacent.

    Week 53, the extra MMWR week some years carry, sits BETWEEN weeks 52
    and 1 on the ring: it maps to position 52.5, so distance(53, 1) == 1,
    distance(53, 52) == 1, and distance(53, 3) == 3. The plain period-52
    arithmetic mapped week 53 ONTO week 1 (distance 0), which admitted
    donors one week beyond the stated bandwidth on one side of an
    epiweek-53 target and starved the other side (audit finding; the
    2025-26 season peaked on an epiweek-53 Saturday, so the case is not
    hypothetical). All pairs within 1..52 are untouched: their arithmetic
    stays integer and identical to the historical path.
    """
    aa = 52.5 if a == 53 else float(a)
    bb = 52.5 if b == 53 else float(b)
    d = abs(aa - bb)
    return int(math.ceil(min(d, period - d)))


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
        "still growing: it is the only donor season whose March ratios have "
        "a median above one, with an upper tail more than twice as heavy as "
        "any other season's. Exact ranges depend on the pool definition and "
        "are stated at the strength at which they reproduce (audit "
        "2026-08-26)."),
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
        "Pre-registered harness, arm A2 (donor-floor harness, lab archive, "
        "not in this repository; docs/archive/RELEASE-1.0.md restates the result). "
        "Its control arm A0 "
        "reproduces the sealed analogue quantiles to 0.0 and the sealed "
        "member WIS to 3.05e-10. The bootstrap endpoints are Monte Carlo and "
        "wander by about 0.1 percentage points across seeds; the point "
        "estimate and the sign do not."),
)


SEASON_2020_21_SUPPRESSED = DonorSeasonExclusion(
    season=2020,
    label="2020-21",
    profile_key="influenza",
    season_boundary_month=SEASON_BOUNDARY_MONTH,
    covers=(date(2020, 8, 1), date(2021, 7, 31)),
    prereg_hash="086bda9a0736e983",
    tested_on="2026-09-18",
    adopted_on="2026-09-19",
    mechanism=(
        "A suppressed season. Non-pharmaceutical intervention during the "
        "COVID-19 response all but removed influenza from circulation: in the "
        "ILI+ donor bank the 2020-21 in-season median (epiweek >= 47 or <= 20) "
        "is 0.2855 against 3.78 to 67.07 in every other season, a factor of 13 "
        "below the nearest and about 100 below a typical one. The failure this "
        "causes is NOT extra noise, and an earlier draft of this record said it "
        "was. Measured, the season's pooled log-ratio spread is 0.8775 against "
        "1.1053 for the rest of the pool, so it is the LEAST volatile "
        "contributor, which is exactly the fingerprint of an epidemic that "
        "never happened. Its ratios sit near one. A calendar-matched pool asks "
        "what happens over the next four weeks, and 2020-21 answers 'nothing "
        "much', damping the pool toward no growth in precisely the weeks when "
        "an ordinary season is climbing."),
    effect=(
        "Auxiliary ILI+ pool only, vincentized at weight 0.5 with the shrink "
        "applied, scored against the production particle filter on 15,460 "
        "ensemble and 15,764 member cells over 76 as-of weeks. Ensemble pooled "
        "relWIS 0.6707 -> 0.6688, +0.293 percent; member 0.6315 -> 0.6284, "
        "+0.495 percent. Clustered bootstrap on as-of dates, 4000 replicates: "
        "ensemble delta median -0.00198, 95 percent CI -0.00309 to -0.00064, "
        "better in 3993 of 4000; member median -0.00316, CI -0.00521 to "
        "-0.00053, better in 3956 of 4000. Ensemble coverage is unchanged to "
        "within a thousandth (worst deviation 0.015 -> 0.014). This is a SMALL "
        "effect and the record says so: the case for the exclusion is the "
        "mechanism above, and the measurement is here to show the direction is "
        "right and the cost is nil, not to claim a material gain."),
    depth_control=(
        "The effect is COMPOSITION, not count, by the same test the 2021-22 "
        "record uses. Randomly cutting the 2020-21-inclusive pool to the size "
        "the exclusion leaves, 5 seeds, moves the ensemble -0.004 percent "
        "(seed spread -0.015 to +0.018 percent) and the member -0.007 percent, "
        "against +0.293 and +0.495 percent for removing the season itself. "
        "Unlike the 2021-22 exclusion, which bites only where that season "
        "supplies in-window donors, this one changes every scored cell, "
        "because the auxiliary pool is pooled across all locations and so "
        "every quantile moves."),
    evidence=(
        "Pre-registered factorial, prereg 086bda9a0736e983 amendment 2, arms "
        "B1 against B2 and B3 against B4, which froze the 2020-21 in/out "
        "contrast before any score was read. The figures quoted above are the "
        "vincentize-plus-shrink pair (B6 against B5) re-scored against the "
        "production filter under prereg 90c935a5e2ed62f7, with the depth "
        "control run afterwards to this record's requirement. Harness, "
        "pre-registrations and results are in the lab archive "
        "(research/iliplus-splice), not in this repository. NOTE ON SCOPE: the "
        "admissions bank carries no 2020-21 data at all, since the archived "
        "NHSN series begins 2022-02-05 (season 2021-22). This record is "
        "therefore INERT for the admissions donor pool and changes only the "
        "auxiliary pool, which is verified by a byte-identity check over all "
        "85 archived as-of weeks."),
)


#: The ONLY seasons that may be dropped, keyed by season label. Adding a key
#: here is the whole cost of excluding another season, and it is meant to be
#: expensive: the record must carry a pre-registration hash, a mechanism, a
#: measured effect and a depth control before anything can use it.
DONOR_SEASON_EXCLUSIONS: dict = {
    SEASON_2021_22_CALENDAR_INVERSION.season: SEASON_2021_22_CALENDAR_INVERSION,
    SEASON_2020_21_SUPPRESSED.season: SEASON_2020_21_SUPPRESSED,
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
    return _scale_ratio_quantiles(
        anchor, {float(L): float(np.quantile(r, L)) for L in levels},
        widen_log_sd)


def _scale_ratio_quantiles(anchor: float, ratio_q: dict,
                           widen_log_sd: Optional[float]) -> Optional[dict]:
    """Shared tail: scale a ratio quantile function by the anchor, widen it,
    and validate. `ratio_q` maps level -> the RATIO distribution's quantile.

    Both the single-pool path (`analogue_quantiles`) and the spliced path
    (`spliced_quantiles`) end here on purpose, so the two cannot disagree
    about widening, the median check or monotonicity.
    """
    q = {float(L): float(anchor * v) for L, v in ratio_q.items()}
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
    # sorted (the widening factor is itself increasing in L, and a convex
    # combination of two monotone quantile functions is monotone); assert
    # rather than sort, because a violation means a real bug.
    vals = [q[float(L)] for L in sorted(q)]
    if any(b < a - 1e-9 for a, b in zip(vals, vals[1:])):
        return None
    return q


# ---------------------------------------------------------------------------
# Auxiliary donor pools (the ILI+ splice)
# ---------------------------------------------------------------------------
# A second donor pool drawn from a DIFFERENT surveillance stream, combined with
# the admissions pool by averaging the two RATIO quantile functions level by
# level (vincentization). Averaging quantile functions rather than pooling the
# donors is deliberate: concatenating two pools is a linear pool weighted by
# donor COUNT, which hands the larger stream most of the say for a reason that
# has nothing to do with how informative it is.
#
# DORMANT BY DEFAULT. `forecast(..., splice=None)` is byte-identical to the
# historical single-pool path; nothing below runs unless a caller passes a
# DonorSplice.


@dataclass(frozen=True, eq=False)
class AuxPool:
    """One auxiliary donor pool and the weight it carries in the blend.

    `bank` has the same (location, date) -> value shape as the admissions
    bank and is read only by `donor_ratios`, which pools across locations,
    so an auxiliary stream's location keys need not match the admissions
    bank's. They only need to be self-consistent, because a location key is
    used solely to find a week's own future value. That is why a 20-site
    FluSurv-NET catchment and a 48-state ILI+ bank can sit in the same blend
    without either being a coverage map.

    `weight` is this pool's share of the blended quantile function. The
    admissions pool takes whatever is left, so a single pool at 0.5 is the
    equal-weight case and two pools at 0.25 split the auxiliary half.

    `shrink` rescales this pool's log-ratios by `r -> exp(shrink * log r)`
    before its quantiles are taken, putting a stream of different volatility
    on the admissions pool's scale. Fit it with `fit_log_ratio_shrink` on
    strictly prior seasons, never on the target.

    `exclude_seasons` goes through `resolve_donor_exclusions` exactly as the
    admissions pool's does, so an auxiliary pool cannot drop a season the
    registry has not accepted.

    `label` names the stream in errors and in run records; no behaviour.
    """
    bank: Mapping[tuple, float]
    weight: float
    shrink: Optional[float] = None
    exclude_seasons: tuple = tuple(sorted(EXCLUDED_DONOR_SEASONS))
    bandwidth: Optional[int] = None
    label: str = "aux"


@dataclass(frozen=True, eq=False)
class DonorSplice:
    """One or more auxiliary pools to vincentize into the admissions pool.

    The blend is a weighted average of RATIO quantile functions, level by
    level. Averaging quantile functions rather than pooling the donors is
    deliberate: concatenating pools is a linear pool weighted by donor
    COUNT, which hands the largest stream most of the say for a reason that
    has nothing to do with how informative it is.

    The admissions pool's weight is 1 minus the auxiliary weights, so those
    must sum to at most 1.
    """
    pools: tuple
    #: Per-instance memo of auxiliary donor ratios, keyed by the arguments
    #: that determine them. `donor_ratios` does not depend on the location
    #: being forecast -- the pool is cross-location -- so without this each
    #: auxiliary bank is rescanned once per location per horizon, which on a
    #: 52-jurisdiction run is 208 identical scans per pool. The memo is
    #: scoped to one DonorSplice, so it is built and dropped with the run
    #: and cannot leak between forecast dates.
    _ratio_memo: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def primary_weight(self) -> float:
        """What the admissions pool keeps."""
        return 1.0 - sum(float(p.weight) for p in self.pools)


def in_season_log_ratios(bank: Mapping[tuple, float], horizon: int,
                         seasons: Iterable[int], *,
                         first_epiweek: int = 47,
                         last_epiweek: int = 20) -> np.ndarray:
    """Log growth ratios at `horizon`, restricted to the named seasons and to
    the in-season window that wraps the new year (epiweek >= 47 or <= 20).

    Used to compare two surveillance streams' volatility on the stretch of
    calendar where both actually carry epidemic signal; the off-season weeks
    are dominated by near-zero denominators in both streams.
    """
    seas = frozenset(int(x) for x in seasons)
    out = []
    for (loc, d), v0 in bank.items():
        if season_of(d) not in seas:
            continue
        w = epiweek(d)
        if not (w >= first_epiweek or w <= last_epiweek):
            continue
        v1 = bank.get((loc, d + timedelta(days=7 * horizon)))
        if v1 is None or not (v1 > 0) or not (v0 > 0):
            continue
        out.append(math.log(v1 / v0))
    return np.asarray(out, dtype=float)


def fit_log_ratio_shrink(bank: Mapping[tuple, float],
                         aux_bank: Mapping[tuple, float],
                         target_season: int, *,
                         horizons: Iterable[int] = (1, 2, 3, 4),
                         exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS
                         ) -> Optional[float]:
    """sd(admissions log-ratio) / sd(auxiliary log-ratio), on seasons STRICTLY
    PRIOR to `target_season` that both banks carry.

    This is a distribution-matching factor, not a regression slope. The
    regression slope of one stream on the other is the right coefficient for
    PREDICTING admissions from ILI+, but it is attenuated by the correlation
    between them and would under-disperse a pool that is being used as a
    donor distribution rather than as a predictor.

    Returns None when no prior season is shared, or when either side has
    fewer than MIN_DONORS ratios, or the auxiliary spread is not positive.
    A None shrink means "do not rescale", which is the caller's decision to
    make loudly rather than a silent 1.0.
    """
    drop = resolve_donor_exclusions(exclude_seasons)
    shared = ({season_of(d) for _, d in bank}
              & {season_of(d) for _, d in aux_bank})
    prior = {s for s in shared if s < target_season and s not in drop}
    if not prior:
        return None
    a = np.concatenate([in_season_log_ratios(bank, h, prior) for h in horizons])
    b = np.concatenate([in_season_log_ratios(aux_bank, h, prior)
                        for h in horizons])
    if a.size < MIN_DONORS or b.size < MIN_DONORS:
        return None
    sb = float(np.std(b))
    if not (math.isfinite(sb) and sb > 0):
        return None
    sa = float(np.std(a))
    if not math.isfinite(sa):
        return None
    return sa / sb


def spliced_quantiles(anchor: float, ratios: np.ndarray,
                      aux: Iterable, levels: Iterable[float], *,
                      completeness: Optional[float] = None,
                      widen_log_sd: Optional[float] = None) -> Optional[dict]:
    """Vincentize a primary ratio pool with one or more auxiliary pools.

    `aux` is a sequence of (ratios, weight, shrink, label). The blended
    ratio quantile function is

        q(L) = w0 * Q_primary(L) + sum_i w_i * Q_i(L),   w0 = 1 - sum w_i

    EVERY pool must independently clear MIN_DONORS. That is stricter than
    requiring it of the blend, and deliberately so: a blend whose auxiliary
    half rests on a handful of donors is not a blend, it is the primary pool
    with noise added at a fixed weight.

    Returns None on the same terms as `analogue_quantiles`, which callers
    must read as "no forecast" rather than as zero.
    """
    if anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return None
    aux = list(aux)
    ws = [float(w) for _, w, _, _ in aux]
    if any(not math.isfinite(w) or w < 0 for w in ws):
        raise ValueError(f"splice weights must be finite and >= 0, got {ws!r}")
    w0 = 1.0 - sum(ws)
    if w0 < -1e-12:
        raise ValueError(
            f"auxiliary splice weights sum to {sum(ws)!r}, leaving the "
            f"admissions pool a negative weight; they must sum to at most 1")
    w0 = max(w0, 0.0)
    if completeness is not None:
        c = float(completeness)
        if not math.isfinite(c) or c <= 0:
            raise ValueError(f"completeness must be finite and > 0, got {c!r}")
        anchor = anchor / c
    r = np.asarray(ratios, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < MIN_DONORS:
        return None
    prepared = []
    for a_raw, w, shrink, label in aux:
        a = np.asarray(a_raw, dtype=float)
        a = a[np.isfinite(a)]
        if a.size < MIN_DONORS:
            return None
        if shrink is not None:
            sh = float(shrink)
            if not math.isfinite(sh) or sh <= 0:
                raise ValueError(
                    f"shrink for pool {label!r} must be finite and > 0, got "
                    f"{shrink!r}")
            a = a[a > 0]
            if a.size < MIN_DONORS:
                return None
            # exp(s * log r) rather than r ** s: the two agree to within an
            # ulp, and this is the form the pre-registered harness measured.
            a = np.exp(sh * np.log(a))
        prepared.append((a, float(w)))
    rq = {}
    for L in levels:
        v = w0 * np.quantile(r, L)
        for a, w in prepared:
            v += w * np.quantile(a, L)
        rq[float(L)] = float(v)
    return _scale_ratio_quantiles(anchor, rq, widen_log_sd)


def forecast(anchor: float, as_of: date, horizon: int,
             bank: Mapping[tuple, float], levels: Iterable[float],
             bandwidth: int = DEFAULT_BANDWIDTH, *,
             completeness: Optional[float] = None,
             widen_log_sd: Optional[float] = None,
             exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS,
             splice: Optional["DonorSplice"] = None) -> Optional[dict]:
    """One analogue predictive distribution. `bank` maps (location, date)->value.

    `completeness` / `widen_log_sd` pass through to `analogue_quantiles`;
    their None defaults keep this byte-identical to the historical path.

    `exclude_seasons` passes through to `donor_ratios` and defaults to the
    shipped pool, which excludes 2021-22.

    `splice`, when given, adds a second donor pool from another surveillance
    stream and vincentizes the two ratio quantile functions (see
    `DonorSplice`). None, the default, does not touch the single-pool
    arithmetic above and is byte-identical to the historical path.
    """
    r = donor_ratios(bank, epiweek(as_of), season_of(as_of), horizon,
                     bandwidth=bandwidth, exclude_seasons=exclude_seasons)
    if splice is None:
        return analogue_quantiles(anchor, r, levels, completeness=completeness,
                                  widen_log_sd=widen_log_sd)
    ew, se = epiweek(as_of), season_of(as_of)
    aux = []
    for i, pool in enumerate(splice.pools):
        bw = bandwidth if pool.bandwidth is None else pool.bandwidth
        memo_key = (i, ew, se, horizon, bw)
        got = splice._ratio_memo.get(memo_key)
        if got is None:
            got = donor_ratios(pool.bank, ew, se, horizon, bandwidth=bw,
                               exclude_seasons=pool.exclude_seasons)
            splice._ratio_memo[memo_key] = got
        aux.append((got, pool.weight, pool.shrink, pool.label))
    return spliced_quantiles(anchor, r, aux, levels,
                             completeness=completeness,
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
