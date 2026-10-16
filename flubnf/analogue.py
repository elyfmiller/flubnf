"""SHIPPED: calendar-conditioned empirical analogue forecaster (the core of
the Groundhog and the Oracle's donor paths).

For a target (state, as-of week T, horizon h):
    anchor   = the last OBSERVED value at T (vintage: what was knowable)
    donors   = every (state', week W) from STRICTLY PRIOR seasons whose epiweek
               is within `bandwidth` weeks of T's epiweek
    ratios   = truth[state', W + 7h] / truth[state', W]
    forecast = anchor * quantiles(ratios)

Donors are pooled ACROSS states: per-state pools (~5 per prior season) cannot
support 23 quantiles. The pool also keeps the US national row, which is the
sum of the 52 jurisdictions (15 of 793 donors on a representative date).
Removing it tied inside the pre-registered 0.001 band (analogue relWIS 0.7714
with vs 0.7717 without; shipped ensemble 0.7233 vs 0.7234); record in the
lab archive (research/us-donor).

Against SIHRS over the sealed archive the two members tie on total WIS
(ratio 0.998) and alternate by season, which is why the blend pays; the
analogue loses less to dispersion and overprediction and 1.8x more to
underprediction. Skill depends on donor COMPOSITION, not depth.

Seasons leave the donor pool only through a registered DonorSeasonExclusion
(DONOR_SEASON_EXCLUSIONS; the records below carry the evidence). A season
label is relative to the influenza 1 August boundary and is not portable to
another disease (resolve_donor_exclusions).

Two traps, both paid for:
1. ANCHOR ALIGNMENT. A one-week look-ahead on the anchor is worth ~0.18
   relWIS, so `season_start` and the vintage file must share the as-of date.
2. NaN. `v <= 0` is False for NaN and one NaN makes np.quantile all-NaN, so
   every filter here is np.isfinite.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import NormalDist
from typing import Iterable, Mapping, Optional

import numpy as np

# Bandwidth 2 is what the sealed record ran at. It was never re-selected on
# the current pipeline (the per-season optimum reverses season to season;
# pre-seal sweep in the lab archive); changing it invalidates the seal and
# is the lead's decision.
DEFAULT_BANDWIDTH = 2
MIN_DONORS = 30
#: the shipped Groundhog's own-state donor weight (LocalPooling.own_share):
#: the jurisdiction's own past weeks carry half of the admissions pool
#: (prereg c66c50adc20bdf84, screen of 2026-10-15: leave-one-season-out
#: relWIS 0.6604 against 0.6701 pooled on 17,116 cells; the lead's decision
#: 2026-10-15). 0 is the pooled form every jurisdiction shared before.
SHIPPED_OWN_SHARE = 0.5

#: First month of an influenza season label (season_of).
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
    """Circular distance between epiweeks (52 and 1 are adjacent).

    Week 53 sits at 52.5, BETWEEN 52 and 1 (distance(53, 1) == 1), never on
    top of week 1, which would skew the bandwidth around an epiweek-53
    target. Pairs within 1..52 keep plain integer arithmetic.
    """
    aa = 52.5 if a == 53 else float(a)
    bb = 52.5 if b == 53 else float(b)
    d = abs(aa - bb)
    return int(math.ceil(min(d, period - d)))


# ---------------------------------------------------------------------------
# Donor-season exclusions
# ---------------------------------------------------------------------------
# A season leaves the donor pool ONLY through a registered record: an
# untraced exclusion looks like a bug.

@dataclass(frozen=True)
class DonorSeasonExclusion:
    """One season removed from the analogue's donor pool, with its evidence.

    A season LABEL depends on the season boundary (influenza's is 1 August),
    so resolve_donor_exclusions refuses a record whose
    `season_boundary_month` is not this module's.
    """
    season: int
    label: str
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


#: The ONLY seasons that may be dropped, by label. Adding one requires a full
#: record (prereg hash, mechanism, measured effect, depth control).
DONOR_SEASON_EXCLUSIONS: dict = {
    SEASON_2021_22_CALENDAR_INVERSION.season: SEASON_2021_22_CALENDAR_INVERSION,
    SEASON_2020_21_SUPPRESSED.season: SEASON_2020_21_SUPPRESSED,
}

#: donor_ratios' default: forgetting the argument must not restore the pool
#: published figures moved away from; `exclude_seasons=()` does that explicitly.
EXCLUDED_DONOR_SEASONS = frozenset(DONOR_SEASON_EXCLUSIONS)


def resolve_donor_exclusions(exclude_seasons: Iterable[int]) -> frozenset:
    """Validate a donor-season exclusion set, LOUDLY; returns season labels.

    Raises for a season with no registered record (an unreproducible pool)
    and for a record minted under another disease's season boundary (the
    same label names different calendar weeks).
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

    `allow_same_season` exists ONLY so tests can show that leaking the
    target season improves the score; never True in production.

    `exclude_seasons` defaults to the shipped pool (EXCLUDED_DONOR_SEASONS);
    `()` restores the unrestricted pre-2026-08-24 pool. Every value passes
    resolve_donor_exclusions.
    """
    drop = resolve_donor_exclusions(exclude_seasons)
    out = []
    for (loc, d), v0 in _donor_cells(bank, target_epiweek, target_season,
                                     bandwidth, allow_same_season, drop):
        v1 = bank.get((loc, d + timedelta(days=7 * horizon)))
        if v1 is None or not np.isfinite(v1) or v1 <= 0:
            continue
        out.append(v1 / v0)
    arr = np.asarray(out, dtype=float)
    return arr[np.isfinite(arr)]


def donor_paths(bank: Mapping[tuple, float], target_epiweek: int,
                target_season: int, length: int = 6,
                bandwidth: int = DEFAULT_BANDWIDTH,
                allow_same_season: bool = False, *,
                exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS,
                with_keys: bool = False):
    """Growth PATHS, one row per donor: `v(d + 7k) / v(d)` for k = 1..length.

    Same donors as donor_ratios (shared _donor_cells), kept only when all
    `length` future cells are finite and positive, so column k-1 is a subset
    of donor_ratios(..., k). Shape `(n, length)`, `(0, length)` when none.
    `with_keys=True` also returns each row's `(loc, d)` in bank order.

    No donor floor (MIN_DONORS is the caller's). Future values are read by
    date arithmetic, so the week-53 seam is handled by construction. Ratios
    are on the bank's own scale (see fit_log_ratio_shrink).
    """
    length = int(length)
    if length < 1:
        raise ValueError(f"donor_paths: length must be >= 1, got {length}")
    drop = resolve_donor_exclusions(exclude_seasons)
    rows, keys = [], []
    for (loc, d), v0 in _donor_cells(bank, target_epiweek, target_season,
                                     bandwidth, allow_same_season, drop):
        row = []
        for k in range(1, length + 1):
            v = bank.get((loc, d + timedelta(days=7 * k)))
            if v is None or not np.isfinite(v) or v <= 0:
                break
            row.append(v / v0)
        else:
            if all(math.isfinite(x) for x in row):
                rows.append(row)
                keys.append((loc, d))
    paths = (np.asarray(rows, dtype=float) if rows
             else np.empty((0, length), dtype=float))
    return (paths, keys) if with_keys else paths


def _donor_cells(bank: Mapping[tuple, float], target_epiweek: int,
                 target_season: int, bandwidth: int,
                 allow_same_season: bool, drop):
    """The donor SELECTION rule, in one place (donor_ratios, donor_paths).

    Yields `((loc, d), v0)` in bank order for finite positive cells in a
    strictly prior season (unless `allow_same_season`), not in `drop` (an
    already-resolved set), within `bandwidth` epiweeks. No future values, no
    floor. tests/test_donor_paths.py pins donor_ratios on the committed banks.
    """
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
        yield (loc, d), v0


def analogue_quantiles(anchor: float, ratios: np.ndarray,
                       levels: Iterable[float], *,
                       completeness: Optional[float] = None,
                       widen_log_sd: Optional[float] = None) -> Optional[dict]:
    """Scale the anchor by the empirical ratio distribution.

    Returns None ("no forecast", never zero) when inputs cannot support one.

    RESEARCH, dormant: `completeness` (lag-0 first-issue/final ratio) divides
    the anchor; non-finite or non-positive raises. `widen_log_sd` applies
    q'(L) = q(L) * exp(z_L * widen_log_sd) (median unchanged). None keeps
    the historical arithmetic.
    """
    if anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return None
    anchor, r = _anchor_and_pool(anchor, ratios, completeness)
    if r is None:
        return None
    return _scale_ratio_quantiles(
        anchor, {float(L): float(np.quantile(r, L)) for L in levels},
        widen_log_sd)


def _anchor_and_pool(anchor: float, ratios, completeness) -> tuple:
    """The anchor divided by `completeness` (non-finite or non-positive
    raises) and the finite ratio pool; the pool is None under MIN_DONORS."""
    if completeness is not None:
        c = float(completeness)
        if not math.isfinite(c) or c <= 0:
            raise ValueError(f"completeness must be finite and > 0, got {c!r}")
        anchor = anchor / c
    r = np.asarray(ratios, dtype=float)
    r = r[np.isfinite(r)]
    return anchor, (r if r.size >= MIN_DONORS else None)


def _scale_ratio_quantiles(anchor: float, ratio_q: dict,
                           widen_log_sd: Optional[float]) -> Optional[dict]:
    """Shared tail of the single-pool and spliced paths: scale the RATIO
    quantiles (`ratio_q`, level -> quantile) by the anchor, widen, validate."""
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
    # Already monotone by construction; check rather than sort (a violation
    # is a real bug).
    vals = [q[float(L)] for L in sorted(q)]
    if any(b < a - 1e-9 for a, b in zip(vals, vals[1:])):
        return None
    return q


# ---------------------------------------------------------------------------
# Auxiliary donor pools (the ILI+ splice)
# ---------------------------------------------------------------------------
# Donor pools from OTHER surveillance streams, vincentized (RATIO quantile
# functions averaged level by level) with the admissions pool. Nothing here
# runs unless a caller passes a DonorSplice (the Groundhog does).


@dataclass(frozen=True, eq=False)
class AuxPool:
    """One auxiliary donor pool and the weight it carries in the blend.

    `bank`: (location, date) -> value; locations need only be
    self-consistent (the pool is cross-location). `weight`: this pool's
    share; the admissions pool keeps the rest. `shrink`: log-ratios scaled
    `r -> exp(shrink * log r)`, fit with fit_log_ratio_shrink on strictly
    prior seasons. `exclude_seasons` goes through resolve_donor_exclusions.
    `label` names the stream in errors and records only.
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

    A weighted average of RATIO quantile functions, not concatenated donors
    (which would weight streams by donor COUNT). Auxiliary weights sum to at
    most 1; the admissions pool keeps the rest.
    """
    pools: tuple
    #: Per-run memo of auxiliary donor ratios (they do not depend on the
    #: location), so a bank is not rescanned per location and horizon.
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

    Compares stream volatility where both carry signal (off-season weeks
    are dominated by near-zero denominators).
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

    A distribution-matching factor, not a regression slope (which is
    attenuated by the correlation and would under-disperse the pool).
    Returns None (the caller decides, loudly) when no prior season is
    shared, either side has < MIN_DONORS ratios, or the aux spread is 0.
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

    EVERY pool must clear MIN_DONORS on its own (a thin aux pool is just
    noise at a fixed weight). None means "no forecast", as in
    analogue_quantiles.
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
    anchor, r = _anchor_and_pool(anchor, ratios, completeness)
    if r is None:
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
            # exp(s * log r), not r ** s: the pre-registered harness's form
            a = np.exp(sh * np.log(a))
        prepared.append((a, float(w)))
    rq = {}
    for L in levels:
        v = w0 * np.quantile(r, L)
        for a, w in prepared:
            v += w * np.quantile(a, L)
        rq[float(L)] = float(v)
    return _scale_ratio_quantiles(anchor, rq, widen_log_sd)


# ---------------------------------------------------------------------------
# Locally weighted donor pools (the shipped form since 2026-10-15, prereg
# c66c50adc20bdf84; SHIPPED_OWN_SHARE above)
# ---------------------------------------------------------------------------
# forecast() with local=None is the POOLED form: every location scales one
# pooled ratio distribution by its own anchor, so every forecast has the
# same shape, the path every submission before 2026-10-15 took, untouched.
# A LocalPooling weights a location's own past weeks (and, research only,
# its region's) up in the admissions pool, and can let a location with its
# own FluSurv-NET site read that site (research only; worse on the screen).


@dataclass(frozen=True, eq=False)
class LocalPooling:
    """How much of the donor weight a location's own history carries.

    Admissions pool: the target location's own donor cells carry total
    share `own_share` of the weight, other locations of the same region
    (`region_of`, location -> region id) share `region_share`, every other
    cell shares the rest; a class with no donors passes its share to the
    rest. `own_site`: an auxiliary pool restricted to the location's own
    site codes (`aux_sites`, location -> tuple of bank site codes) replaces
    the pooled auxiliary ratios when it clears MIN_DONORS. Shares are
    validated on construction.
    """
    own_share: float = 0.0
    region_share: float = 0.0
    own_site: bool = False
    region_of: Mapping = field(default_factory=dict)
    aux_sites: Mapping = field(default_factory=dict)
    #: RESEARCH (prereg 0815e4709ab06b2f): the admissions pool by each
    #: donor cell's own count v0. `anchor_floor`: a cell counts only if
    #: v0 >= the floor (fewer than MIN_DONORS left: the unfloored pool).
    #: `anchor_weight`: within each class every donor's weight is
    #: multiplied by g(v0), "count" (v0), "sqrt" (v0 ** 0.5) or "kernel"
    #: (exp(-(ln v0 - ln a)^2 / (2 kernel_sd^2)) in the target's own anchor
    #: a), and the class is renormalised, so the class shares hold.
    anchor_floor: float = 0.0
    anchor_weight: str = "none"
    kernel_sd: float = 1.0
    #: per-run memo of own-site auxiliary ratios, keyed by pool, location,
    #: epiweek, season, horizon and bandwidth
    _memo: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        for name in ("own_share", "region_share"):
            v = float(getattr(self, name))
            if not math.isfinite(v) or v < 0 or v > 1:
                raise ValueError(f"{name} must be in [0, 1], got {v!r}")
        if self.own_share + self.region_share > 1 + 1e-12:
            raise ValueError(
                f"own_share + region_share = "
                f"{self.own_share + self.region_share!r} exceeds 1")
        f = float(self.anchor_floor)
        if not math.isfinite(f) or f < 0:
            raise ValueError(f"anchor_floor must be finite and >= 0, got {f!r}")
        if self.anchor_weight not in ANCHOR_WEIGHTS:
            raise ValueError(f"anchor_weight must be one of {ANCHOR_WEIGHTS}, "
                             f"got {self.anchor_weight!r}")
        k = float(self.kernel_sd)
        if not math.isfinite(k) or k <= 0:
            raise ValueError(f"kernel_sd must be finite and > 0, got {k!r}")


#: the anchor weightings LocalPooling accepts
ANCHOR_WEIGHTS = ("none", "count", "sqrt", "kernel")


def anchor_factor(anchors, local: "LocalPooling", target_anchor) -> np.ndarray:
    """g(v0) per donor for the research anchor weightings; ones for "none"
    (and for a kernel with no usable target anchor)."""
    a = np.asarray(anchors, dtype=float)
    w = local.anchor_weight
    if w == "count":
        return a
    if w == "sqrt":
        return np.sqrt(a)
    if w == "kernel":
        if target_anchor is None or not np.isfinite(target_anchor) or target_anchor <= 0:
            return np.ones(a.size)
        d = np.log(a) - math.log(float(target_anchor))
        return np.exp(-0.5 * (d / float(local.kernel_sd)) ** 2)
    return np.ones(a.size)


def weighted_quantile(values, weights, levels: Iterable[float]) -> dict:
    """{level: weighted empirical quantile}. Values sorted (stable), each
    placed at (cumulative weight - weight / 2) / total, linear interpolation
    between them, clamped to the extremes. Uniform weights are close to,
    not identical with, np.quantile's default; the shipped path never calls
    this."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    if v.size == 0 or v.shape != w.shape:
        raise ValueError("weighted_quantile needs matching non-empty arrays")
    if not np.all(np.isfinite(w)) or np.any(w < 0) or not w.sum() > 0:
        raise ValueError("weights must be finite, >= 0 and not all zero")
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cw = np.cumsum(w)
    pos = (cw - 0.5 * w) / cw[-1]
    return {float(L): float(np.interp(float(L), pos, v)) for L in levels}


def keyed_ratios(bank: Mapping[tuple, float], target_epiweek: int,
                 target_season: int, horizon: int,
                 bandwidth: int = DEFAULT_BANDWIDTH, *,
                 exclude_seasons: Iterable[int] = EXCLUDED_DONOR_SEASONS,
                 sites=None, with_anchor: bool = False) -> tuple:
    """donor_ratios with each ratio's donor location beside it: (ratios,
    locations), the same donors in the same order as donor_ratios. `sites`
    (a set of bank location codes) keeps only those donors. `with_anchor`
    adds a third array, each donor cell's own value v0 (its count at the
    donor week, the research weightings' input)."""
    drop = resolve_donor_exclusions(exclude_seasons)
    vals, locs, v0s = [], [], []
    for (loc, d), v0 in _donor_cells(bank, target_epiweek, target_season,
                                     bandwidth, False, drop):
        if sites is not None and loc not in sites:
            continue
        v1 = bank.get((loc, d + timedelta(days=7 * horizon)))
        if v1 is None or not np.isfinite(v1) or v1 <= 0:
            continue
        vals.append(v1 / v0)
        locs.append(loc)
        v0s.append(v0)
    arr = np.asarray(vals, dtype=float)
    ok = np.isfinite(arr)
    out = (arr[ok], np.asarray(locs, dtype=object)[ok])
    if with_anchor:
        out = out + (np.asarray(v0s, dtype=float)[ok],)
    return out


def local_weights(locs, location, local: "LocalPooling", anchors=None,
                  target_anchor=None) -> np.ndarray:
    """One weight per donor so that the location's own cells sum to
    own_share, its region's other cells to region_share and the rest to the
    remainder; a class with no cells passes its share to the rest. With a
    research anchor weighting, each donor inside its class is multiplied by
    anchor_factor(v0) and the class renormalised, so the shares hold."""
    locs = np.asarray(locs, dtype=object)
    # a class whose share is 0 is not a class: its cells stay in the rest
    # (found in review 2026-10-15: same-region cells were being dropped)
    is_own = locs == location
    own = is_own if local.own_share > 0 else np.zeros(locs.size, dtype=bool)
    region = (local.region_of.get(location) if local.region_share > 0
              else None)
    # region cells are OTHER jurisdictions of the region: never the target's
    same = (np.array([local.region_of.get(l) == region for l in locs],
                     dtype=bool) & ~is_own) if region is not None else np.zeros(
        locs.size, dtype=bool)
    rest = ~own & ~same
    s_own = float(local.own_share) if own.any() else 0.0
    s_reg = float(local.region_share) if same.any() else 0.0
    s_rest = 1.0 - s_own - s_reg
    if not rest.any():
        # only own and region cells: renormalise what is there
        tot = s_own + s_reg
        s_own, s_reg, s_rest = (s_own / tot, s_reg / tot, 0.0) if tot > 0 else (
            1.0 if own.any() else 0.0, 0.0 if own.any() else 1.0, 0.0)
    w = np.zeros(locs.size, dtype=float)
    g = (anchor_factor(anchors, local, target_anchor)
         if (anchors is not None and local.anchor_weight != "none") else None)
    for mask, share in ((own, s_own), (same, s_reg), (rest, s_rest)):
        if not mask.any():
            continue
        if g is None or not np.isfinite(g[mask]).all() or g[mask].sum() <= 0:
            w[mask] = share / mask.sum()
        else:
            w[mask] = share * g[mask] / g[mask].sum()
    return w


def _local_forecast(anchor, as_of, horizon, bank, levels, bandwidth, *,
                    completeness, widen_log_sd, exclude_seasons, splice,
                    local, location):
    """forecast() under a LocalPooling: weighted admissions quantiles, the
    own-site auxiliary pool where it is deep enough, the same
    vincentization and the same tail as spliced_quantiles."""
    if location is None:
        # the 2026-10-14 defect made an error: a location the weights cannot
        # find silently gives uniform weights
        raise ValueError("local pooling needs `location`, the bank's key "
                         "for the target jurisdiction")
    if anchor is None or not np.isfinite(anchor) or anchor <= 0:
        return None
    ew, se = epiweek(as_of), season_of(as_of)
    target_anchor = float(anchor)                 # the newest count itself
    r, locs, v0 = keyed_ratios(bank, ew, se, horizon, bandwidth,
                               exclude_seasons=exclude_seasons,
                               with_anchor=True)
    if local.anchor_floor > 0:
        # RESEARCH: drop small-count donors; under MIN_DONORS keep them all
        keep = v0 >= float(local.anchor_floor)
        if keep.sum() >= MIN_DONORS:
            r, locs, v0 = r[keep], locs[keep], v0[keep]
    anchor, r2 = _anchor_and_pool(anchor, r, completeness)
    if r2 is None:
        return None
    if (local.own_share == 0 and local.region_share == 0
            and local.anchor_weight == "none"):
        # no local weight asked: the shipped quantile rule, exactly, so an
        # own_site-only pooling changes the auxiliary pool and nothing else
        rq_primary = {float(L): float(np.quantile(r2, L)) for L in levels}
    else:
        rq_primary = weighted_quantile(
            r2, local_weights(locs, location, local, anchors=v0,
                              target_anchor=target_anchor), levels)
    if splice is None:
        return _scale_ratio_quantiles(anchor, rq_primary, widen_log_sd)
    ws = [float(p.weight) for p in splice.pools]
    if any(not math.isfinite(w) or w < 0 for w in ws):
        raise ValueError(f"splice weights must be finite and >= 0, got {ws!r}")
    if sum(ws) > 1.0 + 1e-12:
        raise ValueError(
            f"auxiliary splice weights sum to {sum(ws)!r}, leaving the "
            f"admissions pool a negative weight; they must sum to at most 1")
    w0 = max(1.0 - sum(ws), 0.0)
    prepared = []
    for i, pool in enumerate(splice.pools):
        bw = bandwidth if pool.bandwidth is None else pool.bandwidth
        a = None
        sites = local.aux_sites.get(location) if local.own_site else None
        if sites:
            # keyed by the pool object, not its index: a LocalPooling reused
            # with another splice must not return the other pool's ratios
            key = (pool, location, ew, se, horizon, bw)
            a = local._memo.get(key)
            if a is None:
                a, _ = keyed_ratios(pool.bank, ew, se, horizon, bw,
                                    exclude_seasons=pool.exclude_seasons,
                                    sites=frozenset(sites))
                local._memo[key] = a
            if a.size < MIN_DONORS:
                a = None                       # thin own site: pooled ratios
        if a is None:
            memo_key = (i, ew, se, horizon, bw)
            a = splice._ratio_memo.get(memo_key)
            if a is None:
                a = donor_ratios(pool.bank, ew, se, horizon, bandwidth=bw,
                                 exclude_seasons=pool.exclude_seasons)
                splice._ratio_memo[memo_key] = a
        a = np.asarray(a, dtype=float)
        a = a[np.isfinite(a)]
        if a.size < MIN_DONORS:
            return None
        if pool.shrink is not None:
            sh = float(pool.shrink)
            if not math.isfinite(sh) or sh <= 0:
                raise ValueError(f"shrink for pool {pool.label!r} must be "
                                 f"finite and > 0, got {pool.shrink!r}")
            a = a[a > 0]
            if a.size < MIN_DONORS:
                return None
            a = np.exp(sh * np.log(a))
        prepared.append((a, float(pool.weight)))
    rq = {}
    for L in levels:
        v = w0 * rq_primary[float(L)]
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
             splice: Optional["DonorSplice"] = None,
             local: Optional["LocalPooling"] = None,
             location=None) -> Optional[dict]:
    """One analogue predictive distribution. `bank` maps (location, date)->value.

    `completeness` / `widen_log_sd` pass to analogue_quantiles;
    `exclude_seasons` to donor_ratios (default: the shipped pool). `splice`
    adds auxiliary pools (DonorSplice); None is the single-pool path.
    `local` (LocalPooling) weights `location`'s own donors up, the shipped
    form (the engine passes SHIPPED_OWN_SHARE); None is the pooled form,
    the path before 2026-10-15 byte for byte.
    """
    if local is not None:
        return _local_forecast(anchor, as_of, horizon, bank, levels, bandwidth,
                               completeness=completeness,
                               widen_log_sd=widen_log_sd,
                               exclude_seasons=exclude_seasons, splice=splice,
                               local=local, location=location)
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

    Dropped here because one NaN reaching np.quantile poisons every level.
    """
    bank = {}
    for r in truth_rows:
        v = float(r.value)
        if np.isfinite(v) and v > 0:
            bank[(r.location, r.date)] = v
    return bank
