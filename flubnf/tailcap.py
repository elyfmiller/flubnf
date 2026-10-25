"""The upper-tail cap: a plausibility bound on the hub rows of both members.

Spencer Fox's red-flag rule (2026-10-21) reads each forecast's 97.5% quantile
against the jurisdiction's recent level and flags a horizon-3 value above
about 30 times it. Both members' far-horizon upper tails in small-count
states failed it on the 2026-10-24 round (the Oracle SIHRS's from the
filter's early-season tail, the Groundhog's from erratic own-state donor
histories), while the medians sat with the other members'.

The cap clips every quantile ABOVE THE MEDIAN of a (location, horizon)
block at `n` times the recent level, the mean of the last `RECENT_WEEKS`
reported weeks at the forecast date, and never below the block's own median:
the median and every lower quantile are untouched, order is preserved
(clipped levels tie at the limit), and a block whose recent level is 0 or
unknown is left alone. It runs on the hub rows at the output stage, after
the Oracle step, the narrowing and the output floor, so the run record and
the files agree. The rows arrive in whole admissions (app.core.submit), so
the levels the cap moves are rounded back to whole admissions and the block
kept monotone: the limit is met to within half an admission.

Screened post hoc on the stored replays (docs/team/submission.md,
2026-10-22): on the Oracle member's 44 stage-rule weeks a cap at 15-20x
left pooled relative WIS and coverage within a thousandth and removed every
horizon-3 cell above 30x; on the Groundhog's three retro seasons it was
free season-wide and a gain in September-October weeks. CAP_PRODUCTION = 0
(no cap) is the registered form; a run at another value is a modified run
with an override reason, as for the narrowing, until a card sentence
changes the default.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping

#: the registered form: no cap (knob output.tail_cap; 0 = off)
CAP_PRODUCTION = 0.0
#: how the cap is applied (knob output.tail_mode): "clip" clips every level
#: above the median at the limit (levels tie there); "shrink" is the
#: location-wide form (Ely, 2026-10-22): the exponent the worst horizon
#: needs to bring its 97.5% quantile to the limit is applied to every
#: horizon of the location above the median, q' = m (q/m)^k, so the band
#: keeps its shape across horizons and only the worst horizon touches the
#: limit. On the replays the clip scores a little better over whole seasons,
#: the shrink better in September-October weeks (docs/team/submission.md).
MODE_PRODUCTION = "clip"
MODES = ("clip", "shrink")
#: the recent level is the mean of this many newest reported weeks
RECENT_WEEKS = 3
#: the historical ceiling (knob output.tail_hist; Spencer Fox's bound read
#: on our data, 2026-10-25): per horizon, the upper quantiles are clipped at
#: the recent level times a quantile of the growth history has produced,
#: y[W+h+1] / recent(W), over every jurisdiction's weeks within HIST_WINDOW
#: epiweeks of the forecast date in strictly earlier seasons whose recent
#: level was at least HIST_FLOOR. The knob is that quantile level: 1.0 the
#: maximum (nothing history never did), 0.975 the 97.5th percentile; 0 is
#: off, the registered form. It runs before the n-cap, as a clip.
HIST_PRODUCTION = 0.0
HIST_WINDOW = 2
HIST_FLOOR = 10.0
HORIZONS = (0, 1, 2, 3)
#: the hub target the cap applies to
TARGET = "wk inc flu hosp"


def recent_level(values: Iterable[float], weeks: int = RECENT_WEEKS) -> float:
    """Mean of the last `weeks` finite values (the newest reported weeks,
    oldest to newest); NaN when there are none."""
    v = [float(x) for x in values if x is not None and math.isfinite(float(x))]
    if not v:
        return float("nan")
    tail = v[-weeks:]
    return float(sum(tail) / len(tail))


def limit_for(n: float, values: Iterable[float], weeks: int = RECENT_WEEKS) -> float:
    """The cap for one location: n times its recent level; NaN (no cap) when
    n is 0 or the recent level is unknown or 0."""
    if not n or n <= 0:
        return float("nan")
    r = recent_level(values, weeks)
    if not math.isfinite(r) or r <= 0:
        return float("nan")
    return float(n) * r


def cap_block(values_by_level: Mapping[float, float], limit: float) -> dict:
    """One (location, horizon) block {level: value}: levels above 0.5 are
    clipped at max(limit, the block's median); everything else is returned
    as given. A NaN limit returns the block unchanged."""
    out = dict(values_by_level)
    if limit is None or not math.isfinite(limit):
        return out
    med = out.get(0.5)
    if med is None or not math.isfinite(float(med)):
        return out
    top = max(float(limit), float(med))
    for level, v in out.items():
        if float(level) > 0.5 and math.isfinite(float(v)) and float(v) > top:
            out[level] = top
    return out


def exponent_needed(values_by_level: Mapping[float, float], limit: float) -> float:
    """The exponent k <= 1 that brings a block's 97.5% quantile to `limit`
    about its median (1.0 when the block is already under it, has no
    positive median, or the limit is at or below the median)."""
    if limit is None or not math.isfinite(limit):
        return 1.0
    m = values_by_level.get(0.5); q = values_by_level.get(0.975)
    if m is None or q is None or not (float(m) > 0) or float(q) <= float(m):
        return 1.0
    if float(q) <= float(limit) or float(limit) <= float(m):
        return 1.0
    return math.log(float(limit) / float(m)) / math.log(float(q) / float(m))


def shrink_block(values_by_level: Mapping[float, float], k: float) -> dict:
    """One block narrowed above its median by exponent k (q' = m (q/m)^k for
    levels above 0.5; everything else as given; k >= 1 returns the block)."""
    out = dict(values_by_level)
    m = out.get(0.5)
    if k is None or k >= 1 or m is None or not (float(m) > 0):
        return out
    for level, v in out.items():
        if float(level) > 0.5 and math.isfinite(float(v)) and float(v) > 0:
            out[level] = float(m) * (float(v) / float(m)) ** k
    return out


def whole_block(capped: Mapping[float, float], block: Mapping[float, float]) -> dict:
    """`capped` in whole admissions, as the hub rows came (app.core.submit
    rounds every quantile and keeps the block monotone): the levels that
    differ from `block` are rounded half to even, then the block is made
    monotone in level order; levels the cap left alone are returned as
    given, so an untouched block is unchanged."""
    out: dict = {}
    top = -math.inf
    for level in sorted(capped):
        v = capped[level]
        if math.isfinite(float(v)):
            if v != block[level]:
                v = int(round(float(v)))
            if v < top:
                v = top
            top = v
        out[level] = v
    return out


def _epiweek(d: "date") -> int:
    return int(d.isocalendar()[1])


def _season_of(d: "date") -> int:
    return d.year if d.month >= 8 else d.year - 1


def history_ratios(series_by_fips: Mapping[str, Iterable], asof: "date | str",
                   level: float = 1.0, window: int = HIST_WINDOW,
                   floor: float = HIST_FLOOR, weeks: int = RECENT_WEEKS,
                   horizons: Iterable[int] = HORIZONS) -> dict:
    """{horizon: ratio}: the `level` quantile (1.0 = the maximum) of
    y[W+h+1] / recent(W) over every series' weeks W within `window`
    epiweeks of `asof` in strictly earlier seasons, recent(W) the mean of
    the `weeks` values ending at W and at least `floor`. `series_by_fips`
    maps a jurisdiction to (date, value) pairs, dates ISO strings or dates,
    oldest first; the national row should not be among them. A horizon
    with no history gives NaN."""
    from datetime import date as _date, timedelta
    asof_d = asof if isinstance(asof, _date) else _date.fromisoformat(str(asof)[:10])
    ew, se = _epiweek(asof_d), _season_of(asof_d)
    hs = [int(h) for h in horizons]
    pools: dict = {h: [] for h in hs}
    for _fips, pairs in series_by_fips.items():
        pts = []
        for d, v in pairs:
            dd = d if isinstance(d, _date) else _date.fromisoformat(str(d)[:10])
            if v is not None and math.isfinite(float(v)):
                pts.append((dd, float(v)))
        pts.sort()
        by_date = dict(pts)
        for i, (w, _v) in enumerate(pts):
            if _season_of(w) >= se:
                continue
            dw = abs(_epiweek(w) - ew)
            if min(dw, 52 - dw) > window:
                continue
            base_vals = [x for (_d, x) in pts[max(0, i - weeks + 1): i + 1]]
            base = sum(base_vals) / len(base_vals)
            if not (base >= floor):
                continue
            for h in hs:
                y = by_date.get(w + timedelta(days=7 * (h + 1)))
                if y is not None:
                    pools[h].append(y / base)
    out = {}
    for h in hs:
        r = sorted(pools[h])
        if not r:
            out[h] = float("nan")
        elif level >= 1.0:
            out[h] = float(r[-1])
        else:
            # the quantile by linear interpolation, as numpy's default
            pos = (len(r) - 1) * float(level)
            lo = int(math.floor(pos)); hi = min(lo + 1, len(r) - 1)
            out[h] = float(r[lo] + (r[hi] - r[lo]) * (pos - lo))
    return out


def history_limits(ratios: Mapping[int, float], recent: float) -> dict:
    """{horizon: limit}: the recent level times each horizon's ratio; NaN
    (no ceiling) where either is unknown or the recent level is 0."""
    if recent is None or not math.isfinite(float(recent)) or float(recent) <= 0:
        return {int(h): float("nan") for h in ratios}
    return {int(h): (float(recent) * float(r) if r is not None and math.isfinite(float(r))
                     else float("nan")) for h, r in ratios.items()}


def clip_rows_by_horizon(rows: list, limits_by_fips: Mapping[str, Mapping[int, float]]) -> tuple:
    """The historical ceiling on hub quantile rows: each (location,
    horizon) block of TARGET clipped above its median at that location's
    limit FOR THAT HORIZON (cap_block, then whole_block), levels below or at
    the median untouched. Returns (rows, cells changed)."""
    blocks: dict = {}
    for i, r in enumerate(rows):
        if r.get("target") == TARGET and r.get("output_type") == "quantile":
            blocks.setdefault((str(r["location"]), int(r["horizon"])), []).append(i)
    out = [dict(r) for r in rows]
    cells = 0
    for (fips, h), idx in blocks.items():
        lim = (limits_by_fips.get(fips) or {}).get(h, float("nan"))
        if lim is None or not math.isfinite(float(lim)):
            continue
        block = {float(out[i]["output_type_id"]): float(out[i]["value"]) for i in idx}
        capped = whole_block(cap_block(block, float(lim)), block)
        changed = False
        for i in idx:
            level = float(out[i]["output_type_id"])
            if capped[level] != block[level]:
                out[i]["value"] = capped[level]
                changed = True
        cells += int(changed)
    return out, cells


def cap_rows(rows: list, limit_by_fips: Mapping[str, float],
             mode: str = MODE_PRODUCTION) -> tuple:
    """Apply the cap to hub quantile rows (app.core.submit's dicts) in place
    of value: rows of TARGET with output_type "quantile" are grouped by
    (location, horizon), each block capped with its location's limit by
    `mode` ("clip" or "shrink", MODES) and the moved levels rounded back to
    whole admissions (whole_block). Returns (rows, cells) where cells
    counts the blocks that changed."""
    blocks: dict = {}
    for i, r in enumerate(rows):
        if r.get("target") == TARGET and r.get("output_type") == "quantile":
            blocks.setdefault((str(r["location"]), str(r["horizon"])), []).append(i)
    if mode not in MODES:
        raise ValueError(f"tail cap mode must be one of {MODES}, got {mode!r}")
    cells = 0
    out = [dict(r) for r in rows]
    # the location-wide exponent: the worst horizon's, for the shrink form
    k_loc: dict = {}
    if mode == "shrink":
        for (fips, _h), idx in blocks.items():
            lim = limit_by_fips.get(fips, float("nan"))
            block = {float(out[i]["output_type_id"]): float(out[i]["value"]) for i in idx}
            k_loc[fips] = min(k_loc.get(fips, 1.0), exponent_needed(block, lim))
    for (fips, _h), idx in blocks.items():
        lim = limit_by_fips.get(fips, float("nan"))
        if lim is None or not math.isfinite(lim):
            continue
        block = {float(out[i]["output_type_id"]): float(out[i]["value"]) for i in idx}
        capped = cap_block(block, lim) if mode == "clip" else shrink_block(block, k_loc.get(fips, 1.0))
        capped = whole_block(capped, block)
        changed = False
        for i in idx:
            level = float(out[i]["output_type_id"])
            if capped[level] != block[level]:
                out[i]["value"] = capped[level]
                changed = True
        cells += int(changed)
    return out, cells
