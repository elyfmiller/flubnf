"""PRODUCTION: the optional FluSight rows of a console run's files
(app/ui/pipeline._run_all), behind the knobs output.horizon_minus1 and
output.rate_change_pmf (app/core/knobs.py; both off by default, and with
both off nothing here runs and the files are byte for byte as before).

HORIZON -1. The week ending reference_date - 7, the as-of week. The hub
takes it for 'wk inc flu hosp', never scores it, and publishes that week's
first report on the submission Wednesday, so it is a nowcast of a reported
but revisable count.

  * Oracle SIHRS: the anchor block of its draws (horizons.ORIGIN; the
    Oracle step's provenance already maps it to FluSight horizon -1), after
    the output floor like every other block. With nothing trimmed it is the
    filter's own predictive for the reported week, its median pinned to the
    report (pf.collect); with k weeks trimmed it is a forecast k weeks out.
  * Groundhog: its forecast is anchor x donor ratio. With nothing trimmed
    the anchor IS the as-of week, a ratio over zero weeks is 1, and it has
    no distribution for that week: it writes no -1 rows rather than a point
    mass at the report. With k >= 1 weeks trimmed (weeks to drop, or the
    same-day week treated as unreported) the week is k weeks ahead of its
    anchor and it forecasts it like any other (engines.analogue.nowcast).

RATE CHANGE. 'wk flu hosp rate change', horizons 0..3, five categories
from the change between the baseline week (the as-of week) and the target
week (app/core/categorical.py, the hub's scoring rules).

  * Baseline: the vintage's reported count for the as-of week, when the
    model's anchor is that reported week (the default; the same baseline
    the console's maps use).
  * Oracle SIHRS with its anchor before the as-of week: the change along
    each path, target week minus the same path's as-of week, so the
    baseline's uncertainty is carried.
  * Groundhog with its anchor before the as-of week: quantiles per week
    carry no joint paths, so the change cannot be read honestly: no rows
    for that location.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core import categorical as cat
from app.core import horizons as hz
from app.core import submit as SB


def reported_counts(vintage_csv, asof: str) -> dict:
    """{two-character FIPS or 'US': the count reported for the week ending
    `asof`} from one vintage; a location without that week is absent."""
    try:
        t = pd.read_csv(vintage_csv, dtype={"location": str})
    except Exception:
        return {}
    t["location"] = t["location"].str.zfill(2)
    t = t[t["date"].astype(str).str[:10] == str(asof)[:10]]
    v = pd.to_numeric(t["value"], errors="coerce")
    return {loc: float(x) for loc, x in zip(t["location"], v)
            if np.isfinite(x)}


def pf_weeks_dropped(workroot, spec, reported: dict, n2f: dict) -> dict:
    """{location: k}, the weeks each PF cell trimmed: cells.json's
    weeks_dropped when the cell recorded it, else the spec's rule (weeks to
    drop, plus the same-day week when it is set and reported)."""
    import json
    rec = {}
    try:
        for c in json.loads((Path(workroot) / "cells.json").read_text()):
            rec.setdefault(c.get("location"), int(c.get("weeks_dropped", 0) or 0))
    except Exception:
        pass
    base = int(getattr(spec, "weeks_to_drop", 0) or 0)
    same = bool(getattr(spec, "drop_same_day", False))
    out = {}
    for loc, fips in n2f.items():
        out[loc] = rec[loc] if loc in rec else (
            base + (1 if same and fips in reported else 0))
    return out


def pf_rate_change(samples: dict, baseline, population: float,
                   k: int) -> dict:
    """{hub horizon: {category: probability}} from the Oracle SIHRS's draws:
    against the reported baseline when its anchor is the as-of week (k = 0
    and the week reported), else along each path from its own as-of-week
    draw. {} when neither is available."""
    out = {}
    if not population or population <= 0:
        return out
    origin = np.asarray(samples.get(hz.ORIGIN, []), float)
    for h in SB.RATE_CHANGE_HORIZONS:
        x = np.asarray(samples.get(str(h), []), float)
        if not x.size:
            continue
        if k == 0 and baseline is not None:
            p = cat.probs_from_samples(x, baseline, population, h)
        elif origin.size == x.size:
            ok = np.isfinite(x) & np.isfinite(origin)
            p = cat.probs_from_changes(np.rint(x[ok]) - np.rint(origin[ok]),
                                       population, h)
        else:
            p = {}
        if p:
            out[h] = p
    return out


def groundhog_rate_change(q_by_h: dict, info, baseline, asof: str,
                          population: float) -> dict:
    """{hub horizon: {category: probability}} from the Groundhog's quantile
    grids, only where its anchor is the reported as-of week (`info` from
    engines.analogue.nowcast); {} otherwise."""
    if (not info or int(info.get("k", 1)) != 0 or baseline is None
            or str(info.get("anchor_date")) != str(asof)[:10]
            or not population or population <= 0):
        return {}
    out = {}
    for h in SB.RATE_CHANGE_HORIZONS:
        q = q_by_h.get(str(h))
        if q:
            p = cat.probs_from_quantiles(q, baseline, population, h)
            if p:
                out[h] = p
    return out


def notes(counts: dict, want_m1: bool, want_pmf: bool) -> dict:
    """What each file carries, for the run's outcome: {model id: {"horizon
    -1": locations, "rate change": locations}} plus a plain reason when a
    model wrote none of an asked-for kind."""
    out = {}
    for mid, c in counts.items():
        d = {}
        if want_m1:
            d["horizon -1"] = c.get("m1", 0)
        if want_pmf:
            d["rate change"] = c.get("pmf", 0)
        why = []
        if want_m1 and not c.get("m1") and c.get("groundhog"):
            why.append("no horizon -1 rows: the Groundhog's forecast starts "
                       "from that week's reported count, so it has no "
                       "spread to give for it")
        if want_pmf and not c.get("pmf"):
            why.append("no rate-change rows: no location had a baseline week "
                       "the model could use")
        if why:
            d["why"] = "; ".join(why)
        out[mid] = d
    return out
