"""PRODUCTION: did every jurisdiction report the newest week? (the Data
tab's FluSight hub card, the Update data message, the Forecast tab's
anchor line)

Read from the file a real-time run reads for the newest week
(app/core/data.py observed_source: the live target file when it holds that
week). Each location of the hub's locations table (50 states, DC, Puerto
Rico, US) is either reported or one of three gaps:

  no row   the file has no row for it on the newest week
  blank    the row is there, its value is blank
  zero     the value reads 0 and the week before read ZERO_FLOOR or more
           (app/core/missing.py; a 0 after a small week is a genuine low
           count, docs/MISSING-DATA.md)

What a run does with each gap is not restated here: the Groundhog's own
walk (app/core/engines/analogue.py _walk, MAX_ANCHOR_LAG, which the particle
filter shares) is run over the gap locations with the run defaults, plus
the "Newest weeks reading 0" setting when it is given, so the message and
the run cannot disagree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pandas as pd

from app.core import missing as MS
from app.core import ttlcache

#: the short line names at most this many locations, then "and N more"
LINE_NAMES = 6

REASON_TEXT = {"no row": "no row", "blank": "blank value",
               "zero": "reads 0"}


@dataclass
class Gap:
    """One location without a usable newest week."""
    location: str
    reason: str                    # "no row" | "blank" | "zero"
    prev: Optional[float] = None   # the week before, for "zero"
    action: str = "skip"           # "forecast" | "no_groundhog" | "skip"
    from_week: str = ""            # the week a run forecasts from
    why: str = ""                  # the engine's own note, when it made one

    def outcome(self) -> str:
        """What a run does, in a few words."""
        if self.action == "forecast":
            return f"forecast from {self.from_week}"
        if self.action == "no_groundhog":
            return "no Groundhog forecast"
        return "skipped"


@dataclass
class Report:
    week: str
    kind: str                      # "live" | "vintage"
    expected: int
    gaps: list = field(default_factory=list)

    @property
    def max_lag(self) -> int:
        """Unreported weeks a run still forecasts across (the engines')."""
        from app.core.engines.analogue import MAX_ANCHOR_LAG
        return MAX_ANCHOR_LAG

    @property
    def complete(self) -> bool:
        return not self.gaps

    def line(self) -> str:
        """One short line: 'All 53 jurisdictions reported for week W', or
        how many are missing, their names and, when they share it, what a
        run does."""
        if self.complete:
            return (f"All {self.expected} jurisdictions reported for week "
                    f"{self.week}")
        n = len(self.gaps)
        zeros = sum(g.reason == "zero" for g in self.gaps)
        what = ("not reported" if not zeros else
                "read 0" if zeros == n else "not reported or reading 0")
        if what == "read 0" and n == 1:
            what = "reads 0"
        head = (f"{n} jurisdiction{'s' if n != 1 else ''} {what} for "
                f"{self.week}")
        names = [g.location for g in self.gaps]
        shown = ", ".join(names[:LINE_NAMES])
        if n > LINE_NAMES:
            shown += f" and {n - LINE_NAMES} more"
        outs = {g.outcome() for g in self.gaps}
        tail = f" ({outs.pop()})" if len(outs) == 1 else ""
        return f"{head}: {shown}{tail}"

    def short(self) -> str:
        """The Forecast tab's line when nothing is missing."""
        return f"All {self.expected} reported"

    def details(self) -> list:
        """Per-location sentences for the tip, one group per (gap, what a
        run does): 'No row: Nebraska, Utah. Forecast from 2026-09-26.'"""
        groups: dict = {}
        for g in self.gaps:
            key = (g.reason, g.prev if g.reason == "zero" else None,
                   g.outcome(), g.why)
            groups.setdefault(key, []).append(g.location)
        out = []
        for (reason, prev, outc, why), locs in groups.items():
            what = REASON_TEXT[reason]
            if reason == "zero":
                what += f" after {prev:,.0f}"
            then = outc[0].upper() + outc[1:]
            if why:
                then += f": {why}"
            elif outc == "no Groundhog forecast" and reason == "zero":
                then += ("; set Newest weeks reading 0 to missing to "
                         "forecast from the week before")
            out.append(f"{what[0].upper() + what[1:]}: {', '.join(locs)}. "
                       f"{then}.")
        return out


def _classify(frame: pd.DataFrame, names: dict, week: str) -> list:
    """Gaps (without actions) of the newest week, in the table's order."""
    wk = pd.Timestamp(week)
    prev_wk = wk - pd.Timedelta(days=7)
    at = frame[frame.date == wk]
    before = frame[frame.date == prev_wk]
    val = dict(zip(at.location, at.value))
    prev = dict(zip(before.location, before.value))
    gaps = []
    for fips, name in names.items():
        if fips not in val:
            gaps.append(Gap(name, "no row"))
        elif pd.isna(val[fips]):
            gaps.append(Gap(name, "blank"))
        elif (float(val[fips]) <= 0 and fips in prev
              and not pd.isna(prev[fips])
              and float(prev[fips]) >= MS.ZERO_FLOOR):
            gaps.append(Gap(name, "zero", prev=float(prev[fips])))
    return gaps


def _actions(gaps: list, week: str, zero_rule: str) -> None:
    """Fill each gap's action from the Groundhog's own walk (defaults, plus
    the zero setting): the walk skips a location beyond MAX_ANCHOR_LAG
    unreported weeks, moves its anchor back otherwise, and a 0 anchor gives
    no Groundhog forecast (engines/analogue.py run)."""
    from app.core.engines import analogue as AE
    knobs = ({"data.trailing_zero": "missing"} if zero_rule == "missing"
             else {})
    spec = SimpleNamespace(
        engine="analogue", forecast_date=week, weeks_to_drop=0,
        drop_same_day=False, locations=[g.location for g in gaps],
        extra=({"knobs": knobs} if knobs else {}))
    notes: dict = {}
    flags: list = []
    walked = {}
    for loc, anchor, anchor_date, lag, _fc in AE._walk(spec, notes, flags):
        walked[loc] = (anchor, str(pd.Timestamp(anchor_date).date()), lag)
    for g in gaps:
        hit = walked.get(g.location)
        if hit is None:
            g.action = "skip"
            # the engine's note names the week and its age; said plainly
            m = re.search(r"(\d{4}-\d{2}-\d{2}) is (\d+) weeks",
                          str(notes.get(g.location) or ""))
            g.why = (f"its newest reported week, {m.group(1)}, is "
                     f"{m.group(2)} weeks old (more than "
                     f"{AE.MAX_ANCHOR_LAG} unreported)" if m else
                     "no reported week in the data")
            continue
        anchor, adate, lag = hit
        g.from_week = adate
        g.action = "forecast" if anchor > 0 else "no_groundhog"
        if g.action == "no_groundhog" and adate != week:
            g.why = f"its newest reported week, {adate}, reads 0"


@ttlcache.ttl_cache(ttl_s=300.0)
def _check_cached(path: str, mtime_ns: int, size: int, kind: str,
                  week: str, loc_path: str, zero_rule: str) -> Report:
    from flubnf.settings import load_locations
    try:
        locs = pd.read_csv(loc_path, dtype=str)
    except Exception:
        locs = load_locations()
    names = dict(zip(locs.location.str.zfill(2), locs.location_name))
    t = pd.read_csv(path, dtype={"location": str})
    t["location"] = t["location"].str.zfill(2)
    t["date"] = pd.to_datetime(t["date"].astype(str).str[:10])
    t["value"] = pd.to_numeric(t["value"], errors="coerce")
    gaps = _classify(t, names, week)
    if gaps:
        _actions(gaps, week, zero_rule)
    return Report(week=week, kind=kind, expected=len(names), gaps=gaps)


def check(zero_rule: str = MS.TRAILING_ZERO) -> Optional[Report]:
    """The newest week's report, or None when there is no hub data (or it
    cannot be read). `zero_rule` is the "Newest weeks reading 0" setting a
    run would use ("keep", the shipped default, or "missing")."""
    from app.core import data as D
    from app.core.engines import analogue as AE
    try:
        week = D.newest_week()
        if not week:
            return None
        path, kind = D.observed_source(week, "realtime")
        st = Path(path).stat()
        return _check_cached(str(path), st.st_mtime_ns, st.st_size, kind,
                             week, str(AE.LOCATIONS), str(zero_rule or ""))
    except Exception:
        return None
