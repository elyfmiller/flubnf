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
the files agree.

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
#: the recent level is the mean of this many newest reported weeks
RECENT_WEEKS = 3
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


def cap_rows(rows: list, limit_by_fips: Mapping[str, float]) -> tuple:
    """Apply the cap to hub quantile rows (app.core.submit's dicts) in place
    of value: rows of TARGET with output_type "quantile" are grouped by
    (location, horizon), each block capped with its location's limit.
    Returns (rows, cells) where cells counts the blocks that changed."""
    blocks: dict = {}
    for i, r in enumerate(rows):
        if r.get("target") == TARGET and r.get("output_type") == "quantile":
            blocks.setdefault((str(r["location"]), str(r["horizon"])), []).append(i)
    cells = 0
    out = [dict(r) for r in rows]
    for (fips, _h), idx in blocks.items():
        lim = limit_by_fips.get(fips, float("nan"))
        if lim is None or not math.isfinite(lim):
            continue
        block = {float(out[i]["output_type_id"]): float(out[i]["value"]) for i in idx}
        capped = cap_block(block, lim)
        changed = False
        for i in idx:
            level = float(out[i]["output_type_id"])
            if capped[level] != block[level]:
                out[i]["value"] = capped[level]
                changed = True
        cells += int(changed)
    return out, cells
