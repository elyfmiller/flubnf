"""PRODUCTION: did every jurisdiction report the newest week, and which
newest weeks need a decision? (the Data tab's FluSight hub card, the Update
data message, the Forecast tab's anchor line and its Data issues box)

Read from the file a real-time run reads for the newest week
(app/core/data.py observed_source: the live target file when it holds that
week). Each location of the hub's locations table (50 states, DC, Puerto
Rico, US) is either reported or one of four gaps:

  no row     the file has no row for it on the newest week
  blank      the row is there, its value is blank
  zero       the value reads 0 (every newest-week 0: of the hub's such
             weeks since 2023 about three quarters stayed 0 once settled
             and none rose above 5, docs/MISSING-DATA.md, so it is a real
             low count, not a non-report; the Groundhog still needs a rule
             for it, app/core/missing.py ZERO_ANCHOR_RULES)
  collapsed  the value is under MS.PARTIAL_SHARE of a prior week of
             MS.PARTIAL_FLOOR or more (a partial report, or a real drop:
             9 of the 17 such weeks in the archive were later revised to
             at least twice the reported value)

The first two make the week incomplete (Report.complete); the other two
are issues the forecaster decides per state on the Forecast tab (the Data
issues box, box_rows below). What a run does with an unreported week is
not restated here: the Groundhog's own walk (app/core/engines/analogue.py
_walk, MAX_ANCHOR_LAG, which the particle filter shares) is run over the
gap locations with the run defaults, so the message and the run cannot
disagree.
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
#: newest weeks kept with each gap (the wording and the recorded choice)
RECENT_WEEKS = 8

REASON_TEXT = {"no row": "no row", "blank": "blank value",
               "zero": "reads 0", "collapsed": "collapsed"}
#: gaps that leave the week incomplete (a value the models never saw)
UNREPORTED = ("no row", "blank")

#: the Data issues box's facts, from the hub survey (docs/MISSING-DATA.md)
ZERO_FACT = ("Of the hub's newest-week zeros since 2023, about three "
             "quarters stayed 0 once settled and none rose above 5.")
COLLAPSED_FACT = ("9 of the 17 such weeks in the archive were later revised "
                  "to at least twice the reported value.")
#: the Data tab's pointer to the per-state choice
CHOOSE_NOTE = "Groundhog: choose in Data issues"


def _num(v: float) -> str:
    return f"{float(v):,.0f}"


@dataclass
class Gap:
    """One location whose newest week needs a look."""
    location: str
    reason: str                    # "no row" | "blank" | "zero" | "collapsed"
    fips: str = ""
    prev: Optional[float] = None   # the week before (zero, collapsed)
    #: the newest reported weeks, oldest first, (ISO week, value); for a
    #: zero or collapsed week the newest one IS that week
    reported: list = field(default_factory=list)
    action: str = "skip"           # "forecast" | "no_groundhog" | "skip"
    from_week: str = ""            # the week a run forecasts from
    why: str = ""                  # the engine's own note, when it made one

    @property
    def unreported(self) -> bool:
        return self.reason in UNREPORTED

    @property
    def zeros(self) -> int:
        """The run of trailing zeros (a zero gap), else 0."""
        return MS.zero_run([v for _, v in self.reported])

    @property
    def last_positive(self) -> Optional[tuple]:
        """(ISO week, value) of the newest positive week, or None."""
        for w, v in reversed(self.reported):
            if v > 0:
                return w, v
        return None

    @property
    def can_set_aside(self) -> bool:
        """Whether setting the newest weeks aside is offered: 1 or 2
        trailing zeros after a positive week (MS.MAX_CARRY), or a collapsed
        week with a week before it."""
        if self.reason == "zero":
            return 1 <= self.zeros <= MS.MAX_CARRY and self.last_positive is not None
        return self.reason == "collapsed" and len(self.reported) >= 2

    @property
    def aside(self) -> list:
        """The (week, value) rows a set-aside would treat as unreported."""
        if not self.can_set_aside:
            return []
        if self.reason == "zero":
            return list(self.reported[-self.zeros:])
        return list(self.reported[-1:])

    def what(self) -> str:
        """The gap in a few words, by consequence: 'reads 0, recent weeks
        1-4', 'reads 0 after 19, 24, 3', 'reads 0 for 5 weeks (last 2 on
        2026-05-30)', 'reads 8 after 194', 'no row', 'blank value'."""
        if self.reason == "zero":
            n = self.zeros
            if n >= 2:
                lp = self.last_positive
                if lp is None:                # every kept week reads 0
                    return f"reads 0 for {n} weeks or more"
                return f"reads 0 for {n} weeks (last {_num(lp[1])} on {lp[0]})"
            prior = [v for _, v in self.reported[:-1]][-3:]
            if prior and max(prior) >= MS.ZERO_FLOOR:
                return "reads 0 after " + ", ".join(_num(v) for v in reversed(prior))
            if prior:
                lo, hi = min(prior), max(prior)
                rng = _num(lo) if lo == hi else f"{_num(lo)}-{_num(hi)}"
                return f"reads 0, recent weeks {rng}"
            return "reads 0"
        if self.reason == "collapsed":
            v = self.reported[-1][1] if self.reported else 0.0
            return f"reads {_num(v)} after {_num(self.prev or 0)}"
        return REASON_TEXT[self.reason]

    def outcome(self) -> str:
        """What a run does, in a few words."""
        if self.action == "forecast":
            return f"forecast from {self.from_week}"
        if self.action == "no_groundhog":
            return "no Groundhog forecast"
        return "skipped"


def _names(locs: list) -> str:
    shown = ", ".join(locs[:LINE_NAMES])
    if len(locs) > LINE_NAMES:
        shown += f" and {len(locs) - LINE_NAMES} more"
    return shown


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
    def unreported(self) -> list:
        return [g for g in self.gaps if g.unreported]

    @property
    def zeros(self) -> list:
        return [g for g in self.gaps if g.reason == "zero"]

    @property
    def collapsed(self) -> list:
        return [g for g in self.gaps if g.reason == "collapsed"]

    @property
    def complete(self) -> bool:
        """Every jurisdiction has a row with a value."""
        return not self.unreported

    @property
    def clean(self) -> bool:
        """Complete, and no newest week reads 0 or collapsed."""
        return not self.gaps

    def _issue_clauses(self) -> list:
        out = []
        z = self.zeros
        if z:
            out.append(f"{len(z)} read{'s' if len(z) == 1 else ''} 0: "
                       f"{_names([g.location for g in z])} ({CHOOSE_NOTE})")
        c = self.collapsed
        if c:
            out.append(f"{len(c)} collapsed: " + ", ".join(
                f"{g.location} ({g.what()})" for g in c[:LINE_NAMES])
                + (f" and {len(c) - LINE_NAMES} more" if len(c) > LINE_NAMES
                   else ""))
        return out

    def line(self) -> str:
        """One short line: 'All 53 jurisdictions reported for week W',
        or how many are missing, their names and, when they share it,
        what a run does; then the newest weeks reading 0 or collapsed,
        with the pointer to the Forecast tab's Data issues box."""
        if self.clean:
            return (f"All {self.expected} jurisdictions reported for week "
                    f"{self.week}")
        issues = "; ".join(self._issue_clauses())
        un = self.unreported
        if not un:
            return f"All {self.expected} reported for {self.week}; {issues}"
        n = len(un)
        head = (f"{n} jurisdiction{'s' if n != 1 else ''} not reported for "
                f"{self.week}")
        outs = {g.outcome() for g in un}
        tail = f" ({outs.pop()})" if len(outs) == 1 else ""
        text = f"{head}: {_names([g.location for g in un])}{tail}"
        return f"{text}; {issues}" if issues else text

    def short(self) -> str:
        """The Forecast tab's line: 'All 53 reported', 'All 53 reported; 5
        read 0', '51 of 53 reported; 1 collapsed'."""
        n = self.expected - len(self.unreported)
        head = (f"All {self.expected} reported" if n == self.expected
                else f"{n} of {self.expected} reported")
        bits = []
        if self.zeros:
            bits.append(f"{len(self.zeros)} read{'s' if len(self.zeros) == 1 else ''} 0")
        if self.collapsed:
            bits.append(f"{len(self.collapsed)} collapsed")
        return head + (f"; {', '.join(bits)}" if bits else "")

    def details(self) -> list:
        """Per-location sentences for the tip, one group per (gap, what a
        run does): 'No row: Nebraska, Utah. Forecast from 2026-09-26.',
        'Reads 0, recent weeks 1-4: Arkansas. Choose what the Groundhog does
        in Data issues on the Forecast tab.'"""
        groups: dict = {}
        for g in self.gaps:
            then = ""
            if g.unreported:
                then = g.outcome()
                then = then[0].upper() + then[1:]
                if g.why:
                    then += f": {g.why}"
            elif g.reason == "zero":
                then = ("Choose what the Groundhog does in Data issues on "
                        "the Forecast tab; the Oracle SIHRS keeps the 0")
            else:
                then = ("Kept as reported unless set aside in Data issues on "
                        "the Forecast tab")
            key = (g.what(), then)
            groups.setdefault(key, []).append(g.location)
        out = []
        for (what, then), locs in groups.items():
            out.append(f"{what[0].upper() + what[1:]}: {', '.join(locs)}. "
                       f"{then}.")
        if self.zeros:
            out.append(ZERO_FACT)
        if self.collapsed:
            out.append(COLLAPSED_FACT)
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
        g = frame[(frame.location == fips) & (frame.date <= wk)]
        g = g[g.value.notna()].sort_values("date").tail(RECENT_WEEKS)
        recent = [(str(d)[:10], float(v)) for d, v in zip(g.date, g.value)]
        p = prev.get(fips)
        p = None if p is None or pd.isna(p) else float(p)
        if fips not in val:
            gaps.append(Gap(name, "no row", fips, reported=recent))
        elif pd.isna(val[fips]):
            gaps.append(Gap(name, "blank", fips, reported=recent))
        elif float(val[fips]) <= 0:
            gaps.append(Gap(name, "zero", fips, prev=p, reported=recent))
        elif (p is not None and p >= MS.PARTIAL_FLOOR
              and float(val[fips]) < MS.PARTIAL_SHARE * p):
            gaps.append(Gap(name, "collapsed", fips, prev=p, reported=recent))
    return gaps


def _actions(gaps: list, week: str, zero_rule: str) -> None:
    """Fill each gap's action from the Groundhog's own walk (defaults, plus
    the zero setting): the walk skips a location beyond MAX_ANCHOR_LAG
    unreported weeks, moves its anchor back otherwise, and a 0 anchor gives
    no Groundhog forecast (engines/analogue.py run) unless a zero-anchor
    rule is chosen for it."""
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


def check(zero_rule: str = MS.TRAILING_ZERO,
          week: Optional[str] = None) -> Optional[Report]:
    """The newest week's report (or `week`'s, from the file a run anchored
    there reads), or None when there is no hub data (or it cannot be
    read). `zero_rule` is the "Newest weeks reading 0" setting a run would
    use ("keep", the shipped default, or "missing")."""
    from app.core import data as D
    from app.core.engines import analogue as AE
    try:
        newest = D.newest_week()
        week = week or newest
        if not week:
            return None
        path, kind = D.observed_source(
            week, "realtime" if week == newest else "vintage")
        st = Path(path).stat()
        return _check_cached(str(path), st.st_mtime_ns, st.st_size, kind,
                             week, str(AE.LOCATIONS), str(zero_rule or ""))
    except Exception:
        return None


# --- the Forecast tab's Data issues box -----------------------------------------------

#: the box's option labels, by choice; {name}, {week}, {value} and {from}
#: are filled per state
OPTION_TEXT = {
    "abstain": "Groundhog: no forecast; Oracle SIHRS keeps the 0",
    "level": "Groundhog: level (mean of last 4 weeks); Oracle SIHRS keeps the 0",
    "extend": "Groundhog: extend {value} from {from}; Oracle SIHRS keeps the 0",
    "blend": "Groundhog: blend of level and extend; Oracle SIHRS keeps the 0",
    "set_aside": "Both models from {from} ({value}): count the {what} as unreported",
    "omit": "Leave {name} out of both files",
    "keep": "Keep {value} as reported, both models",
    "carry": "Both models from the last reported week",
}


def box_rows(report: Report) -> list:
    """One row per state for templates/_data_issues.html: {fips, name,
    issue, what, hint, reported, default, options: [(value, label)],
    aside: [[week, value]]}. Choices a state cannot take (extend, blend and
    set aside for 3 or more trailing zeros) are left out of its options."""
    rows = []
    for g in report.gaps:
        opts = []
        lp = g.last_positive
        fill = {"name": g.location, "week": report.week,
                "value": _num(g.reported[-1][1]) if g.reported else "0",
                "from": lp[0] if lp else "", "what": "0"}
        if g.reason == "zero":
            fill["value"] = _num(lp[1]) if lp else "0"
            for c in MS.ZERO_CHOICES:
                if c in ("extend", "blend", "set_aside") and not g.can_set_aside:
                    continue
                opts.append((c, OPTION_TEXT[c].format(**fill)))
            hint = g.what()
            if not g.can_set_aside and g.zeros > MS.MAX_CARRY:
                hint += ("; setting weeks aside is offered for 1 or "
                         f"{MS.MAX_CARRY}")
        elif g.reason == "collapsed":
            fill["what"] = _num(g.reported[-1][1]) if g.reported else "0"
            fill["from"] = g.reported[-2][0] if len(g.reported) >= 2 else ""
            fill["value"] = _num(g.reported[-2][1]) if len(g.reported) >= 2 else ""
            for c in MS.COLLAPSED_CHOICES:
                if c == "set_aside" and not g.can_set_aside:
                    continue
                text = OPTION_TEXT[c].format(**{
                    **fill, "value": (_num(g.reported[-1][1]) if c == "keep"
                                      else fill["value"])})
                opts.append((c, text))
            hint = g.what()
        else:
            for c in MS.UNREPORTED_CHOICES:
                opts.append((c, OPTION_TEXT[c].format(**fill)))
            hint = g.what()
            if g.action == "forecast":
                hint += f"; forecast from {g.from_week}"
            elif g.action == "skip":
                hint += f"; {g.why}" if g.why else "; skipped"
        rows.append({"fips": g.fips, "name": g.location, "issue": g.reason,
                     "what": g.what(), "hint": hint,
                     "reported": [[w, v] for w, v in g.reported],
                     "default": MS.DEFAULT_CHOICE.get(g.reason, ""),
                     "options": opts,
                     "aside": [[w, v] for w, v in g.aside]})
    return rows
