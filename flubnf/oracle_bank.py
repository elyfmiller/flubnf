"""The admissions growth-path bank of the Oracle SIHRS: one week's donor pool
from one hub vintage file, written with a manifest and a content digest.

WHAT IS BANKED
--------------
The identified transmission index G = beta * S / N = gamma + weekly log
growth, from smoothed log counts of weekly hospital admissions, for every
row of a hub target-data vintage (52 jurisdictions plus US), with explicit
time stamps. A donor path is one (location, week W) of a strictly earlier
season whose eight raw weeks W-1 .. W+6 are reported and positive, with the
origin stamp G_inst(W) and the four midpoint stamps G_week(W+k), k = 1..4.

This module is the B1 collector of the registered screen
(oracle_member/bank_fbase/oracle_bank.py, sha256 a001ec7f91e9c011, itself
stage0/bank/oracle_bank.py c6c84cf56c95c231 with the floor_weeks parameter)
ported as a library module: the estimators, the collector, the path-table
writer and every constant are as that file has them, so a pool rebuilt here
from a vintage file equals the record's paths_<T>.csv byte for byte
(tests/test_oracle_bank.py pins it against the record where the record is
on the machine). What is new is the edge: the vintage is a FILE the caller
names, populations are a dict the caller passes, and the written pool
carries a sibling manifest with a content digest that `read_pool` verifies,
exactly as `flubnf.bank` does for the auxiliary donor banks, so a week's
provenance can name its pool as "<stream>@<digest8>".

TIME STAMPS. Dates are week-ending Saturdays.
    ly(W)      log count of the week ENDING at W (covers the instants W-1 to W)
    Y(W)       smoothed log count = [ly(W-1) + ly(W) + ly(W+1)] / 3
    G_inst(W)  = GAMMA + Y(W+1) - Y(W)           G at the INSTANT W (the forecast
                                                 origin: end of week W)
    G_week(W)  = GAMMA + [Y(W+1) - Y(W-1)] / 2   G at the MIDPOINT of the week
                                                 ending at W (instant W - 0.5)
    rho_k(W)   = G_week(W+k) / G_inst(W), k = 1..4: the donor ratio path.
    G_trail(W) = GAMMA + [ly(W) - ly(W-2)] / 2   one-sided trailing estimate,
                                                 centred at W - 1.5

Everything a consumer needs is a function of one as-of vintage. Nothing
dated after the as-of date is ever read: the loader truncates exactly as the
Groundhog engine does (app/core/engines/analogue.py), the same-day row kept.

THE RULE (pre-registration section 3, S2; bank change B1): the primary
donor pool is FBASE. Every raw count of the four weeks W-1 .. W+2, the window
the origin stamp reads, is at or above COUNT_FLOOR, and all eight weeks
W-1 .. W+6 are reported and positive; every week a path touches lies in a
season strictly earlier than the target season and not in the registered
exclusions (the season-crossing rule); G_inst(W) > 0 and every midpoint
stamp is finite (the guards). Fewer than MIN_DONOR_SEASONS donor seasons, or
fewer than flubnf.analogue.MIN_DONORS paths, is the identity rule: the pool
holds one IDENTITY row and a consumer applies factor 1.

Donor selection is flubnf.analogue by reference (season_of, epiweek,
calendar_distance with week 53 at 52.5, resolve_donor_exclusions,
DEFAULT_BANDWIDTH, MIN_DONORS); nothing is restated as a literal.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import analogue as AN

# ---------------------------------------------------------------------------
# CONSTANTS. Frozen by the pre-registration before the member was scored; some
# were written after looks at the scored seasons (its sections 10.1 and 10.2).
# ---------------------------------------------------------------------------

#: The stream name of the pool this module builds. Bank change B2 is a
#: registered switch of this name (and of the rule behind it); the label a
#: week records, "<STREAM>@<digest8>", changes with it and nothing else does.
STREAM = "admissions-fbase"

#: Bumped when the on-disk layout of a written pool changes.
LAYOUT_VERSION = 1

#: Removal rate per week: the shipped SIHRS fixes gamma = 7 / 3.2 d mean
#: generation time (flubnf/sihrs_priors.py gamma_per_week). G = gamma +
#: growth is only meaningful at the model's own gamma.
GENERATION_TIME_DAYS = 3.2
GAMMA = 7.0 / GENERATION_TIME_DAYS

#: The one smoother: centred 3-point mean of LOG counts, the smallest
#: symmetric window. Two-sided smoothing is vintage honest for donors
#: because donor weeks lie in strictly earlier seasons.
SMOOTHER_ID = "c3log"
SMOOTHER_TEXT = "centred 3-point arithmetic mean of natural-log weekly counts"

#: The one count floor: at a count of 10 one admission is a 10 percent step,
#: about 0.1 per week in G; below that the integer lattice sets the tails.
COUNT_FLOOR = 10.0

#: Horizons of a donor path.
HORIZONS = (1, 2, 3, 4)
#: Weeks (relative to the origin W) that a full path reads.
PATH_WEEKS = tuple(range(-1, 7))          # W-1 .. W+6
#: Weeks that G_inst(W) alone reads: the FBASE floor window (S2).
BASE_WEEKS = tuple(range(-1, 3))          # W-1 .. W+2

#: Convention C for the secondary beta column (carried in the path table for
#: the record; no arm reads it): attack rate 0.18 per state-season, s0 0.85,
#: omega 0.019, rho*mult = season admissions per capita / attack rate.
CONV_C_ATTACK_RATE = 0.18
CONV_C_S0 = 0.85
CONV_C_OMEGA = 0.019
CONV_C_ID = "C:AR0.18,s0=0.85,omega=0.019,rho*mult=season_total_per_capita/AR"

#: A donor season's total is known in a vintage only if the season is
#: complete there; NA weeks are filled log-linearly for the total only and
#: the filled share may not exceed this.
MAX_FILL_SHARE = 0.02

#: With fewer than this many admissible donor SEASONS the forward rule is
#: the identity (GAMEPLAN v2 F9, fixed a priori).
MIN_DONOR_SEASONS = 2

#: DATA CAVEAT, not a rule: NHSN reporting was voluntary from 2024-05-01 to
#: 2024-10-31. No row is removed; a path touching the period is flagged.
VOLUNTARY_REPORTING = (date(2024, 5, 1), date(2024, 10, 31))

Row = namedtuple("Row", "location date value")

_EW_CACHE: dict = {}


def epiweek(d: date) -> int:
    """flubnf.analogue.epiweek, memoised (the library function is pure)."""
    e = _EW_CACHE.get(d)
    if e is None:
        e = _EW_CACHE[d] = AN.epiweek(d)
    return e


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_populations(locations_csv) -> dict:
    """location (2-char FIPS or 'US') -> population, from a hub
    locations.csv. Population enters only convention C."""
    out = {}
    with open(locations_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["location"].zfill(2)] = float(r["population"])
    return out


def load_rows(path, as_of: date | None) -> list:
    """Rows of one target-data file, the Groundhog engine's way: location
    read as a string and zero-filled to 2 characters, date parsed, rows
    dated after the as-of date DROPPED, the same-day row kept. value is
    float, NaN for NA. File order is preserved (it fixes the bank's
    iteration order)."""
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            y, m, d = (int(x) for x in r["date"].split("-"))
            dd = date(y, m, d)
            if as_of is not None and dd > as_of:
                continue                                   # vintage honesty
            try:
                v = float(r["value"])
            except (TypeError, ValueError):
                v = float("nan")
            rows.append(Row(r["location"].zfill(2), dd, v))
    return rows


# ---------------------------------------------------------------------------
# Estimators on one weekly series (numpy arrays on a contiguous weekly grid)
# ---------------------------------------------------------------------------

def _shift(a: np.ndarray, k: int) -> np.ndarray:
    """a shifted so that out[i] = a[i+k]; NaN where i+k is off the grid."""
    out = np.full(a.shape, np.nan)
    n = len(a)
    if k >= 0:
        if k < n:
            out[:n - k] = a[k:]
    else:
        if -k < n:
            out[-k:] = a[:n + k]
    return out


def _window_min(v: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """min of v[i+lo .. i+hi]; NaN if any of those weeks is missing/off grid."""
    stack = np.vstack([_shift(v, k) for k in range(lo, hi + 1)])
    bad = ~np.isfinite(stack).all(axis=0)
    m = np.where(np.isfinite(stack), stack, np.inf).min(axis=0)
    m[bad] = np.nan
    return m


def estimate_G(v: np.ndarray, floor: float = COUNT_FLOOR,
               smooth: bool = True) -> dict:
    """All G estimators for one contiguous weekly count series v (NaN = not
    reported, 0 = reported zero). smooth=False replaces Y by ly."""
    v = np.asarray(v, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ly = np.where(np.isfinite(v) & (v > 0), np.log(np.where(v > 0, v, 1.0)),
                      np.nan)
    if smooth:
        Y = (_shift(ly, -1) + ly + _shift(ly, 1)) / 3.0
        half = 1
    else:
        Y = ly.copy()
        half = 0
    G_inst = GAMMA + _shift(Y, 1) - Y
    G_week = GAMMA + (_shift(Y, 1) - _shift(Y, -1)) / 2.0
    mid_ok = np.isfinite(_shift(ly, -1))          # the middle week is reported
    G_trail = np.where(mid_ok, GAMMA + (ly - _shift(ly, -2)) / 2.0, np.nan)
    G_back2 = GAMMA + ly - _shift(ly, -1)
    with np.errstate(invalid="ignore"):
        fl_inst = _window_min(v, -half, 1 + half) >= floor
        fl_week = _window_min(v, -1 - half, 1 + half) >= floor
        fl_trail = _window_min(v, -2, 0) >= floor
        fl_path = _window_min(v, PATH_WEEKS[0], PATH_WEEKS[-1]) >= floor
    return dict(ly=ly, Y=Y, G_inst=G_inst, G_week=G_week, G_trail=G_trail,
                G_back2=G_back2, fl_inst=fl_inst, fl_week=fl_week,
                fl_trail=fl_trail, fl_path=fl_path,
                min_path=_window_min(v, PATH_WEEKS[0], PATH_WEEKS[-1]))


def rho_path(est: dict, i: int) -> np.ndarray:
    """rho_1..rho_4 for the origin at grid index i (NaN where undefined)."""
    g0 = est["G_inst"][i]
    out = np.full(len(HORIZONS), np.nan)
    n = len(est["G_week"])
    for j, k in enumerate(HORIZONS):
        if i + k < n:
            out[j] = est["G_week"][i + k] / g0
    return out


def closed_form_counts(I0: float, G_path, obs_scale: float) -> np.ndarray:
    """Closed-form propagation of a G path from the state I0 at the origin
    instant: lam_k = G_k - gamma; weekly count k = obs_scale * gamma *
    I_(k-1) * (exp(lam_k) - 1) / lam_k; I_k = I_(k-1) * exp(lam_k). No S,
    no omega. The same recursion flubnf.oracle evaluates on the median path."""
    out = []
    I = float(I0)
    for G in G_path:
        lam = float(G) - GAMMA
        f = math.expm1(lam) / lam if abs(lam) > 1e-12 else 1.0
        out.append(obs_scale * GAMMA * I * f)
        I *= math.exp(lam)
    return np.asarray(out)


# ---------------------------------------------------------------------------
# Convention C (secondary column, carried for the record)
# ---------------------------------------------------------------------------

def season_weeks(season: int) -> list:
    """Every week-ending Saturday d with flubnf.analogue.season_of(d) == season."""
    d = date(season, AN.SEASON_BOUNDARY_MONTH, 1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    out = []
    while AN.season_of(d) == season:
        out.append(d)
        d += timedelta(days=7)
    return out


def _fill_loglinear(y: np.ndarray) -> tuple:
    """Fill NaN weeks by log-linear interpolation between the nearest
    reported neighbours (on log(y + 0.5)); leading or trailing gaps stay
    NaN. Returns (filled, was_filled_mask)."""
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(y)
    filled = y.copy()
    mask = np.zeros(len(y), dtype=bool)
    if ok.sum() >= 2:
        idx = np.arange(len(y))
        first, last = idx[ok][0], idx[ok][-1]
        inner = (~ok) & (idx > first) & (idx < last)
        if inner.any():
            li = np.interp(idx[inner], idx[ok], np.log(y[ok] + 0.5))
            filled[inner] = np.maximum(np.exp(li) - 0.5, 0.0)
            mask[inner] = True
    return filled, mask


def convention_C(y_raw: np.ndarray, Y_smooth: np.ndarray, G_week: np.ndarray,
                 N: float, attack_rate: float = CONV_C_ATTACK_RATE,
                 s0: float = CONV_C_S0, omega: float = CONV_C_OMEGA,
                 allow_trailing_gap: int = 0, y_fill: np.ndarray | None = None,
                 was_filled: np.ndarray | None = None) -> dict:
    """Closed-form depletion for ONE complete state-season. No i0, no fit."""
    y_raw = np.asarray(y_raw, dtype=float)
    n = len(y_raw)
    if y_fill is None:
        y_fill, was_filled = _fill_loglinear(y_raw)
    else:
        y_fill = np.array(y_fill, dtype=float)
        was_filled = np.array(was_filled, dtype=bool)
    trailing = 0
    if allow_trailing_gap:
        k = n
        while k > 0 and not np.isfinite(y_fill[k - 1]):
            k -= 1
        trailing = n - k
        if 0 < trailing <= allow_trailing_gap and k > 0:
            y_fill[k:] = y_fill[k - 1]
            was_filled[k:] = True
    res = dict(complete=False, reason="", total=float("nan"),
               rho_mult=float("nan"), fill_share=float("nan"),
               n_weeks=n, n_reported=int(np.isfinite(y_raw).sum()),
               n_filled=int(was_filled.sum()),
               dep_inst=np.full(n, np.nan), dep_week=np.full(n, np.nan))
    if not np.isfinite(y_fill).all():
        res["reason"] = "season_not_covered_by_file"
        return res
    total = float(y_fill.sum())
    if total <= 0:
        res["reason"] = "zero_total"
        return res
    share = float(y_fill[was_filled].sum() / total)
    res.update(total=total, fill_share=share)
    if share > MAX_FILL_SHARE:
        res["reason"] = "filled_share_above_limit"
        return res
    rm = total / N / attack_rate
    lam = np.where(np.isfinite(G_week), G_week - GAMMA, 0.0)
    ys = np.where(np.isfinite(Y_smooth) & np.isfinite(G_week),
                  np.exp(np.where(np.isfinite(Y_smooth), Y_smooth, 0.0)),
                  y_fill)
    small = np.abs(lam) <= 1e-9
    fac = np.where(small, 1.0, lam / -np.expm1(-np.where(small, 1.0, lam)))
    I_end = ys / (rm * GAMMA) * fac
    I_prev = np.empty(n)
    I_prev[0] = I_end[0] * math.exp(-lam[0])
    I_prev[1:] = I_end[:-1]
    S = np.empty(n + 1)
    S[0] = N * s0
    for j in range(n):
        newinf = y_fill[j] / rm + (I_end[j] - I_prev[j])
        Rj = N - S[j] - 0.5 * (I_end[j] + I_prev[j])
        S[j + 1] = S[j] - newinf + omega * Rj
    res.update(complete=True, reason="ok", rho_mult=rm,
               dep_inst=S[1:] / (N * s0),
               dep_week=np.sqrt(S[:-1] * S[1:]) / (N * s0))
    return res


# ---------------------------------------------------------------------------
# One vintage
# ---------------------------------------------------------------------------

@dataclass
class VintageBank:
    label: str                      # the as-of date string
    as_of: date
    target_season: int              # donors are seasons strictly below this
    source: Path
    source_sha256: str
    count_bank: dict                # AN.build_bank(rows): (loc, date) -> count > 0
    raw: dict                       # (loc, date) -> float, NaN for NA, 0 kept
    grid0: date                     # first week of the common weekly grid
    n_grid: int
    locations: list
    est: dict = field(default_factory=dict)       # loc -> estimate_G dict
    series: dict = field(default_factory=dict)    # loc -> counts on the grid
    dep_inst: dict = field(default_factory=dict)  # loc -> array on the grid
    dep_week: dict = field(default_factory=dict)
    convC_status: dict = field(default_factory=dict)   # (loc, season) -> dict
    n_duplicate_rows: int = 0

    def index(self, d: date) -> int:
        return (d - self.grid0).days // 7

    def week(self, i: int) -> date:
        return self.grid0 + timedelta(days=7 * i)

    def newest_row_date(self) -> date:
        return max(d for (_, d) in self.raw)

    def y_T(self) -> dict:
        """location -> the value of the row dated the as-of date, where one
        exists (the vintage row y_T of the pre-registration's section 2)."""
        return {loc: v for (loc, d), v in self.raw.items() if d == self.as_of}


def build_vintage(asof: str, source, populations: dict,
                  raw_override: dict | None = None,
                  rows_override: list | None = None) -> VintageBank:
    """Load one vintage FILE and compute every banked quantity.

    `source` is the hub's target-data vintage for `asof`
    (auxiliary-data/target-data-archive/target-hospital-admissions_<asof>.csv,
    or the live pull of a production week). Its newest row must be dated
    exactly `asof` (each archived vintage has that property); a file whose
    newest row is another date is refused rather than silently truncated
    to a week it does not describe. `populations` maps location to
    population (load_populations). raw_override / rows_override exist for
    the canary test and synthetic checks only.
    """
    T = date.fromisoformat(asof)
    src = Path(source)
    rows = rows_override if rows_override is not None else load_rows(src, T)
    if not rows:
        raise ValueError(f"the vintage {src} holds no rows dated on or before {asof}")
    assert all(r.date <= T for r in rows), "row dated after the as-of date"
    count_bank = AN.build_bank(rows)
    raw = {}
    for r in rows:
        raw[(r.location, r.date)] = r.value
    if raw_override is not None:
        raw = raw_override
    n_dup = len(rows) - len(raw)
    dates = sorted({d for (_, d) in raw})
    assert all(d.weekday() == 5 for d in dates), "non-Saturday week ending"
    if dates[-1] != T and rows_override is None:
        raise ValueError(
            f"the vintage {src} has newest row {dates[-1]}, not the as-of "
            f"date {asof}: each vintage has its newest row dated exactly T "
            "(pre-registration section 2), and a pool built for T from a "
            "file that stops earlier would not be that week's pool")
    grid0, last = dates[0], dates[-1]
    n_grid = (last - grid0).days // 7 + 1
    locs = sorted({loc for (loc, _) in raw})
    target_season = AN.season_of(T)
    sha = sha256_file(src) if rows_override is None else "synthetic"
    vb = VintageBank(asof, T, target_season, src, sha, count_bank, raw,
                     grid0, n_grid, locs, n_duplicate_rows=n_dup)
    seasons = sorted({AN.season_of(d) for d in dates})
    for loc in locs:
        vb.series[loc] = np.full(n_grid, np.nan)
    for (loc, d), val in raw.items():
        vb.series[loc][(d - grid0).days // 7] = val
    for loc in locs:
        v = vb.series[loc]
        v_fill, v_filled = _fill_loglinear(v)
        est = estimate_G(v)
        vb.est[loc] = est
        dep_i = np.full(n_grid, np.nan)
        dep_w = np.full(n_grid, np.nan)
        N = populations.get(loc)
        for s in seasons:
            key = (loc, s)
            if s >= target_season:
                vb.convC_status[key] = dict(
                    complete=False, reason="target_season_total_unknown",
                    total=float("nan"), rho_mult=float("nan"),
                    fill_share=float("nan"), n_weeks=len(season_weeks(s)),
                    n_reported="", n_filled="")
                continue
            wk = season_weeks(s)
            idx = np.array([(d - grid0).days // 7 for d in wk])
            ingrid = (idx >= 0) & (idx < n_grid)
            y = np.full(len(wk), np.nan)
            yf = np.full(len(wk), np.nan)
            ym = np.zeros(len(wk), dtype=bool)
            Ys = np.full(len(wk), np.nan)
            Gw = np.full(len(wk), np.nan)
            y[ingrid] = v[idx[ingrid]]
            yf[ingrid] = v_fill[idx[ingrid]]
            ym[ingrid] = v_filled[idx[ingrid]]
            Ys[ingrid] = est["Y"][idx[ingrid]]
            Gw[ingrid] = est["G_week"][idx[ingrid]]
            if N is None:
                vb.convC_status[key] = dict(complete=False,
                                            reason="no_population")
                continue
            c = convention_C(y, Ys, Gw, N, allow_trailing_gap=0,
                             y_fill=yf, was_filled=ym)
            vb.convC_status[key] = {k: c[k] for k in (
                "complete", "reason", "total", "rho_mult", "fill_share",
                "n_weeks", "n_reported", "n_filled")}
            vb.convC_status[key]["population"] = N
            if c["complete"]:
                dep_i[idx[ingrid]] = c["dep_inst"][ingrid]
                dep_w[idx[ingrid]] = c["dep_week"][ingrid]
        vb.dep_inst[loc] = dep_i
        vb.dep_week[loc] = dep_w
    return vb


def in_voluntary_period(week_ending: date) -> bool:
    """True if the week ending on this Saturday overlaps VOLUNTARY_REPORTING."""
    return (week_ending >= VOLUNTARY_REPORTING[0]
            and week_ending - timedelta(days=6) <= VOLUNTARY_REPORTING[1])


# ---------------------------------------------------------------------------
# Donor selection (flubnf.analogue, unchanged) and the path-coherent collector
# ---------------------------------------------------------------------------

def _selected(vb: VintageBank, target_epiweek: int, target_season: int,
              bandwidth: int, exclude_seasons):
    """Yield (loc, d, v0, season, distance) in the library's own iteration
    order under the library's own rule: flubnf.analogue.donor_ratios with
    the donor identity kept; every test is a call into the library."""
    drop = AN.resolve_donor_exclusions(exclude_seasons)
    for (loc, d), v0 in vb.count_bank.items():
        if not np.isfinite(v0) or v0 <= 0:
            continue
        s = AN.season_of(d)
        if s >= target_season:
            continue
        if s in drop:
            continue
        dist = AN.calendar_distance(epiweek(d), target_epiweek)
        if dist > bandwidth:
            continue
        yield loc, d, v0, s, dist


DonorPath = namedtuple(
    "DonorPath",
    "location week season epiweek cal_dist count_W min_count G_origin G_mid "
    "rho G_trail_origin fl_trail_origin dep_origin dep_mid vol24")


@dataclass
class DonorPaths:
    as_of: date
    target_season: int
    target_epiweek: int
    rule: str                  # "donor" or "identity"
    reason: str                # "ok", "fewer_than_two_donor_seasons", ...
    donors: list               # DonorPath list to USE (empty under identity)
    diagnostic: list           # the eligible donors even when rule == identity
    n_by_season: dict
    counts: dict               # bookkeeping, see collect_paths

    def rho_matrix(self) -> np.ndarray:
        """(n_donors, 4) ratio paths. Under the identity rule a single row
        of ones, so a consumer that ignores the flag still reproduces the
        shipped forecast."""
        if self.rule != "donor":
            return np.ones((1, len(HORIZONS)))
        return np.array([p.rho for p in self.donors], dtype=float)


def collect_paths(vb: VintageBank, as_of: date | None = None,
                  bandwidth: int = AN.DEFAULT_BANDWIDTH,
                  exclude_seasons=AN.EXCLUDED_DONOR_SEASONS,
                  floor: float = COUNT_FLOOR,
                  target_season: int | None = None,
                  target_epiweek: int | None = None,
                  floor_weeks: tuple = BASE_WEEKS) -> DonorPaths:
    """Path-coherent donors for a target (as-of date, horizons 1..4).

    Selection is the library's (see _selected). A selected donor (loc, W)
    then yields a path only if
      (1) all eight weeks W-1 .. W+6 are reported and positive, and every
          raw count of the weeks in floor_weeks is >= floor. BASE_WEEKS
          (W-1 .. W+2, the window G_inst(W) reads) is the registered FBASE
          rule and this module's default; PATH_WEEKS is the eight-week rule
          of the bank as first built, the reported sensitivity F8W;
      (2) all eight weeks lie in seasons strictly earlier than the target
          season and not in the exclusion set (the season-crossing rule: no
          target-season row and no row after the as-of date can enter);
      (3) G_inst(W) > 0 and every G_week(W+k) is finite.
    Fewer than MIN_DONOR_SEASONS donor seasons, or fewer than
    flubnf.analogue.MIN_DONORS paths, returns the identity rule, flagged.
    """
    as_of = as_of or vb.as_of
    tseason = AN.season_of(as_of) if target_season is None else target_season
    tew = epiweek(as_of) if target_epiweek is None else target_epiweek
    drop = AN.resolve_donor_exclusions(exclude_seasons)
    n_sel = n_present = n_base = n_cross = 0
    paths = []
    for loc, d, v0, s, dist in _selected(vb, tew, tseason, bandwidth,
                                         exclude_seasons):
        n_sel += 1
        i = vb.index(d)
        v = vb.series[loc]
        if i + PATH_WEEKS[0] < 0 or i + PATH_WEEKS[-1] >= vb.n_grid:
            continue
        win = v[i + PATH_WEEKS[0]: i + PATH_WEEKS[-1] + 1]
        if not (np.isfinite(win).all() and (win > 0).all()):
            continue
        n_present += 1
        base = v[i + BASE_WEEKS[0]: i + BASE_WEEKS[-1] + 1]
        if (base >= floor).all():
            n_base += 1
        if not all(v[i + k] >= floor for k in floor_weeks):
            continue
        wk_seasons = {AN.season_of(vb.week(i + k)) for k in PATH_WEEKS}
        if any(ws >= tseason or ws in drop for ws in wk_seasons):
            n_cross += 1
            continue
        if vb.as_of is not None:
            assert vb.week(i + PATH_WEEKS[-1]) <= vb.as_of
        est = vb.est[loc]
        g0 = est["G_inst"][i]
        rho = rho_path(est, i)
        if not (np.isfinite(g0) and g0 > 0 and np.isfinite(rho).all()):
            continue
        gmid = tuple(float(est["G_week"][i + k]) for k in HORIZONS)
        same = all(AN.season_of(vb.week(i + k)) == s for k in range(0, 5))
        if same:
            d0 = float(vb.dep_inst[loc][i])
            dm = tuple(float(vb.dep_week[loc][i + k]) for k in HORIZONS)
        else:
            d0, dm = float("nan"), tuple(float("nan") for _ in HORIZONS)
        paths.append(DonorPath(
            loc, d, s, epiweek(d), dist, float(v0), float(win.min()),
            float(g0), gmid, tuple(float(x) for x in rho),
            float(est["G_trail"][i]), bool(est["fl_trail"][i]), d0, dm,
            any(in_voluntary_period(vb.week(i + k)) for k in PATH_WEEKS)))
    by_season = {}
    for p in paths:
        by_season[p.season] = by_season.get(p.season, 0) + 1
    if len(by_season) < MIN_DONOR_SEASONS:
        rule, reason = "identity", "fewer_than_two_donor_seasons"
    elif len(paths) < AN.MIN_DONORS:
        rule, reason = "identity", "fewer_than_MIN_DONORS_paths"
    else:
        rule, reason = "donor", "ok"
    counts = dict(n_selected=n_sel, n_window_present=n_present,
                  n_base_floor_only=n_base, n_dropped_season_crossing=n_cross,
                  n_path=len(paths), floor_weeks=list(floor_weeks))
    return DonorPaths(as_of, tseason, tew, rule, reason,
                      paths if rule == "donor" else [], paths, by_season,
                      counts)


# ---------------------------------------------------------------------------
# The path table (the bank's own format), written and read
# ---------------------------------------------------------------------------

def _f(x, nd=4) -> str:
    if x is None:
        return ""
    try:
        if not math.isfinite(x):
            return ""
    except TypeError:
        return str(x)
    return f"{x:.{nd}f}"


def _cnt(x) -> str:
    if x is None or not math.isfinite(x):
        return "NA"
    return str(int(x)) if float(x).is_integer() else repr(float(x))


PATH_COLUMNS = (["asof", "target_season", "target_epiweek", "rule",
                 "donor_location", "donor_week", "donor_season",
                 "donor_epiweek", "cal_dist", "count_W", "min_count_Wm1_Wp6",
                 "G_origin"] + [f"G_mid{k}" for k in HORIZONS]
                + [f"rho_{k}" for k in HORIZONS]
                + ["G_trail_origin", "fl_trail_origin", "dep_origin"]
                + [f"dep_mid{k}" for k in HORIZONS] + ["touches_voluntary_2024"])


def _path_row(dp: DonorPaths, p: DonorPath, rule: str) -> list:
    return ([dp.as_of.isoformat(), dp.target_season, dp.target_epiweek, rule,
             p.location, p.week.isoformat(), p.season, p.epiweek, p.cal_dist,
             _cnt(p.count_W), _cnt(p.min_count), _f(p.G_origin, 5)]
            + [_f(x, 5) for x in p.G_mid] + [_f(x, 6) for x in p.rho]
            + [_f(p.G_trail_origin, 5), int(p.fl_trail_origin),
               _f(p.dep_origin, 5)] + [_f(x, 5) for x in p.dep_mid]
            + [int(p.vol24)])


def _identity_row(dp: DonorPaths) -> list:
    return ([dp.as_of.isoformat(), dp.target_season, dp.target_epiweek,
             "identity:" + dp.reason, "IDENTITY", "", "", "", "", "", "", ""]
            + [""] * 4 + ["1.000000"] * 4 + ["", "", ""] + [""] * 4 + [""])


def path_rows(dp: DonorPaths, diagnostic: bool = False) -> list:
    """The rows of the path table as strings, exactly as write_paths writes
    them: the donors under rule "donor", ONE IDENTITY row under the identity
    rule, or (diagnostic=True) the eligible single-season donors marked
    DIAGNOSTIC_NOT_FOR_USE."""
    if diagnostic:
        return [_path_row(dp, p, "DIAGNOSTIC_NOT_FOR_USE") for p in dp.diagnostic]
    if dp.rule != "donor":
        return [_identity_row(dp)]
    return [_path_row(dp, p, "donor") for p in dp.donors]


def write_paths(dp: DonorPaths, path, diagnostic: bool = False) -> int:
    """The path table for one as-of date. Under the identity rule the file
    holds ONE row, donor_location = IDENTITY with rho = 1, so that applying
    the file blindly reproduces the shipped forecast."""
    rows = path_rows(dp, diagnostic)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(PATH_COLUMNS)
        for r in rows:
            w.writerow(r)
    return len(rows)


def read_path_rows(path) -> list:
    """The rows of a written path table, as the dicts csv.DictReader gives."""
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def pool_from_rows(rows: list) -> dict:
    """A pool as the member reads it, from path-table rows (strings): every
    level at the FILE's precision (5 dp for G, 6 dp for rho), so a pool
    rebuilt in memory and a pool read back from disk are the same floats.

    Keys: n, rule (1 donor, 0 identity), rule_text, loc, week, season,
    G_origin (n,), G_mid (n, 4), rho (n, 4), vol24 (n,)."""
    if not rows or rows[0]["rule"] != "donor":
        text = rows[0]["rule"] if rows else "identity:empty"
        return {"n": 0, "rule": 0, "rule_text": text,
                "loc": np.array([], dtype="U2"), "week": np.array([], dtype="U10"),
                "season": np.zeros(0, int), "G_origin": np.zeros(0),
                "G_mid": np.zeros((0, 4)), "rho": np.zeros((0, 4)),
                "vol24": np.zeros(0, int)}
    return {"n": len(rows), "rule": 1, "rule_text": "donor",
            "loc": np.array([r["donor_location"] for r in rows], dtype="U2"),
            "week": np.array([r["donor_week"] for r in rows], dtype="U10"),
            "season": np.array([int(r["donor_season"]) for r in rows]),
            "G_origin": np.array([float(r["G_origin"]) for r in rows]),
            "G_mid": np.array([[float(r[f"G_mid{k}"]) for k in HORIZONS] for r in rows]),
            "rho": np.array([[float(r[f"rho_{k}"]) for k in HORIZONS] for r in rows]),
            "vol24": np.array([int(r["touches_voluntary_2024"]) for r in rows])}


def pool_from_paths(dp: DonorPaths) -> dict:
    """pool_from_rows on the rows write_paths would write."""
    return pool_from_rows([dict(zip(PATH_COLUMNS, [str(x) for x in r]))
                           for r in path_rows(dp)])


# ---------------------------------------------------------------------------
# The manifest and the content digest, the flubnf.bank contract
# ---------------------------------------------------------------------------

def digest_rows(rows: list) -> str:
    """A stable content hash of a pool: sha256 over the lines
    "<donor_location>|<donor_week>=<G_origin>,<G_mid1>,..,<G_mid4>\\n" at
    the file's own precision, sorted by (location, week). Over the CONTENT
    the member reads and not the file bytes, so a pool rebuilt from the
    vintage compares with a written one without a file, and a bookkeeping
    column cannot change the identity of the pool. An identity pool digests
    over its one IDENTITY row."""
    h = hashlib.sha256()
    lines = []
    for r in rows:
        mids = ",".join(r[f"G_mid{k}"] for k in HORIZONS)
        lines.append(f"{r['donor_location']}|{r['donor_week']}={r['G_origin']},{mids}\n")
    for line in sorted(lines):
        h.update(line.encode())
    return h.hexdigest()


def rule_block() -> dict:
    """The rule a written pool was built under, stated in the manifest."""
    return {"name": "FBASE", "count_floor": COUNT_FLOOR,
            "floor_weeks": list(BASE_WEEKS), "path_weeks": list(PATH_WEEKS),
            "bandwidth": AN.DEFAULT_BANDWIDTH, "min_donors": AN.MIN_DONORS,
            "min_donor_seasons": MIN_DONOR_SEASONS,
            "excluded_donor_seasons": sorted(AN.EXCLUDED_DONOR_SEASONS),
            "identity_rule": ("fewer than min_donor_seasons donor seasons, or "
                              "fewer than min_donors paths: factor 1"),
            "season_crossing_rule": ("every raw week a path reads (W-1 to W+6) "
                                     "lies in a strictly earlier, non-excluded season"),
            "guards": "G_inst(W) > 0 and every midpoint stamp finite",
            "gamma": GAMMA, "smoother": SMOOTHER_ID}


def pool_path(out_dir, asof: str) -> Path:
    return Path(out_dir) / f"paths_{asof}.csv"


def manifest_path(out_dir, asof: str) -> Path:
    return Path(out_dir) / f"paths_{asof}.manifest.json"


def label(manifest: dict) -> str:
    """"<stream>@<digest8>": what a week's provenance records, the same
    stamp app.core.engines.analogue.aux_preset writes for the Groundhog."""
    return f"{manifest['stream']}@{manifest['digest'][:8]}"


def write_pool(dp: DonorPaths, vb: VintageBank, out_dir, *, built_utc: str,
               builder: str = "flubnf.oracle_bank") -> dict:
    """Write one week's pool (the path table in the bank's own format, ONE
    IDENTITY row under the identity rule) and its manifest, atomically, and
    return the manifest. The manifest carries the flubnf.bank fields plus
    the rule block and the vintage's sha256."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    asof = dp.as_of.isoformat()
    fp = pool_path(out_dir, asof)
    tmp = fp.with_name(fp.name + ".tmp")
    write_paths(dp, tmp)
    tmp.replace(fp)
    rows = read_path_rows(fp)
    locs = sorted({r["donor_location"] for r in rows if r["donor_location"] != "IDENTITY"})
    weeks = sorted(r["donor_week"] for r in rows if r["donor_week"])
    man = {"stream": STREAM, "layout_version": LAYOUT_VERSION,
           "builder": builder, "built_utc": built_utc,
           "source_url": str(vb.source), "source_sha256": vb.source_sha256,
           "asof": asof, "target_season": dp.target_season,
           "target_epiweek": dp.target_epiweek,
           "rule": rule_block(), "pool_rule": dp.rule, "pool_reason": dp.reason,
           "counts": dp.counts,
           "n_by_season": {str(k): v for k, v in sorted(dp.n_by_season.items())},
           "cells": len(dp.donors), "locations": locs, "location_count": len(locs),
           "span": ([weeks[0], weeks[-1]] if weeks else []),
           "digest": digest_rows(rows)}
    mp = manifest_path(out_dir, asof)
    tmp = mp.with_name(mp.name + ".tmp")
    tmp.write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")
    tmp.replace(mp)
    return man


def read_pool(out_dir, asof: str) -> tuple:
    """(pool, manifest) for a written week, digest verified. Raises rather
    than returning a pool that cannot say what it is; a caller that catches
    this and applies the identity is the bug (flubnf.bank's rule)."""
    fp, mp = pool_path(out_dir, asof), manifest_path(out_dir, asof)
    if not fp.is_file():
        raise FileNotFoundError(f"no written pool at {fp}")
    if not mp.is_file():
        raise FileNotFoundError(f"the pool at {fp} has no manifest at {mp}")
    man = json.loads(mp.read_text())
    rows = read_path_rows(fp)
    got = digest_rows(rows)
    if got != man.get("digest"):
        raise ValueError(
            f"the pool at {fp} does not match its manifest.\n"
            f"  manifest says {man.get('digest')}\n"
            f"  the file is   {got}\n"
            "One of them was changed without the other. This pool is NOT "
            "used while they disagree: a week labelled with a bank must be "
            "able to say which donors it drew.")
    return pool_from_rows(rows), man


def build_pool(asof: str, vintage_file, populations: dict,
               out_dir=None, *, built_utc: str = "") -> dict:
    """One call for a week: the vintage from its file, the FBASE pool, and
    (with out_dir) the written table and manifest. Returns a dict with the
    vintage bank, the DonorPaths, the pool the member reads, the manifest
    (None when not written) and the label."""
    vb = build_vintage(asof, vintage_file, populations)
    dp = collect_paths(vb)
    man = None
    if out_dir is not None:
        man = write_pool(dp, vb, out_dir, built_utc=built_utc)
    else:
        rows = [dict(zip(PATH_COLUMNS, [str(x) for x in r])) for r in path_rows(dp)]
        man = {"stream": STREAM, "digest": digest_rows(rows), "cells": len(dp.donors),
               "pool_rule": dp.rule, "pool_reason": dp.reason, "counts": dp.counts,
               "source_sha256": vb.source_sha256, "rule": rule_block()}
    return {"vintage": vb, "paths": dp, "pool": pool_from_paths(dp),
            "manifest": man, "label": label(man)}
