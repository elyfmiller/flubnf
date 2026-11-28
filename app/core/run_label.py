"""PRODUCTION: one name for a run, on every page that names one (app/ui:
Output, Storage, Forecast, the run page, Home), and in the weekly report
(report_v2) with the year rule below taken against the run's as-of: the
data it read and the weeks it forecasts,

    "Data through Nov 21 · forecasts for weeks ending Nov 28 to Dec 19"

and, for a FluSight hub run, its round as a quieter second line,

    "FluSight round 2026-11-28"

The round is the hub's reference date (submit.hub_reference_date: the
as-of + 7 days), which the submission files keep in their names; a week
the hub takes no files for reads "Not a FluSight round (2026-07-11)". A
run on your own data never names a round. The four weeks are the forecasts'
(horizons 0 to 3: the as-of + 7, 14, 21 and 28 days).

Dates read "Nov 21" while every date of a label falls in this year; when
one does not, every date carries its year, written once at the end of a
range whose two ends share it ("Nov 22 to Dec 13, 2025"). The pages
take "this year" as today's; the weekly report takes it as the run's
as-of's (report_v2.report_dates), so a stored report reads the same
whatever day it is rebuilt, and the report of an earlier year's run leaves
out years its pages show ("Nov 22 to Dec 13" where they read "Nov 22 to
Dec 13, 2025").

"Data through" is the newest week of data the run read: what it recorded
(its outcome's "data_source" "newest_week"); for a run from before that
record, the newest week of the series it stored (results.json
"observed"); else its as-of. Never later than the as-of. Nothing here
writes: stored runs and file names stay as they are.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

#: the weeks a run forecasts: the weeks ending 1 to 4 weeks after its as-of
WEEKS_AHEAD = 4

#: the quieter line under a hub run's name
ROUND_WORDS = "FluSight round"


def _day(value) -> date | None:
    """An ISO date (a longer string's first ten characters) as a date;
    None when it is not one."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def target_weeks(asof) -> list:
    """The four weeks a run with this as-of forecasts (the last day of
    each); [] for an unreadable as-of."""
    a = _day(asof)
    return [a + timedelta(days=7 * h) for h in range(1, WEEKS_AHEAD + 1)] \
        if a else []


def reference_date(asof) -> str:
    """The hub's reference date for this as-of (its first forecast week),
    '' for an unreadable one."""
    weeks = target_weeks(asof)
    return weeks[0].isoformat() if weeks else ""


def is_round(reference) -> bool:
    """Whether a reference date is one of the hub's rounds (its vendored
    tasks.json, hubcheck.vendored_rules); True when the rules cannot be
    read, so a label never denies a round it cannot check."""
    try:
        from app.core import hubcheck
        rounds = hubcheck.vendored_rules()["rounds"]
    except Exception:
        return True
    return str(reference)[:10] in {str(r)[:10] for r in rounds}


def round_text(asof) -> str:
    """'FluSight round 2026-11-28' for a hub run's as-of: the reference
    date the hub and the file names use; 'Not a FluSight round
    (2026-07-11)' for a week the hub takes no files for (its files are a
    record); '' when unreadable."""
    ref = reference_date(asof)
    if not ref:
        return ""
    return (f"{ROUND_WORDS} {ref}" if is_round(ref)
            else f"Not a {ROUND_WORDS} ({ref})")


def _md(d: date, year: bool = False) -> str:
    return f"{d:%b} {d.day}" + (f", {d.year}" if year else "")


def _span(a: date, b: date, years: bool) -> str:
    """'Nov 28 to Dec 19'; with years, the year once when both ends share
    it ('Nov 22 to Dec 13, 2025'), else on each end."""
    if not years:
        return f"{_md(a)} to {_md(b)}"
    if a.year == b.year:
        return f"{_md(a)} to {_md(b, True)}"
    return f"{_md(a, True)} to {_md(b, True)}"


def span_text(first, last, today=None) -> str:
    """Two weeks' dates as a span in the labels' year rule ('Sep 26 to
    Nov 21'; 'Nov 15, 2025 to Oct 24, 2026' when one is not this year), the
    earlier first; '' when either is unreadable."""
    a, b = _day(first), _day(last)
    if a is None or b is None:
        return ""
    a, b = min(a, b), max(a, b)
    year = (_day(today) or date.today()).year
    return _span(a, b, a.year != year or b.year != year)


def through(asof, data_through=None) -> date | None:
    """The data-through week a label states: the recorded one when it is a
    date no later than the as-of, else the as-of."""
    a = _day(asof)
    if a is None:
        return None
    d = _day(data_through)
    return d if d is not None and d <= a else a


def text(asof, data_through=None, today=None) -> str:
    """The label itself: 'Data through Nov 21 · forecasts for weeks ending
    Nov 28 to Dec 19' ('' for an unreadable as-of). `today` fixes the year
    rule (date.today() when None)."""
    a = _day(asof)
    if a is None:
        return ""
    d = through(a, data_through)
    weeks = target_weeks(a)
    year = (_day(today) or date.today()).year
    years = any(x.year != year for x in (d, weeks[0], weeks[-1]))
    return (f"Data through {_md(d, years)} · forecasts for weeks ending "
            f"{_span(weeks[0], weeks[-1], years)}")


def name(asof, data_through=None, hub: bool = True, today=None) -> dict:
    """A run's name in its parts: {"text" (the label), "round" (the hub
    round's line, '' for a run on your own data), "asof", "data_through",
    "reference"} (ISO dates; '' when the as-of is unreadable)."""
    a = _day(asof)
    if a is None:
        return {"text": "", "round": "", "asof": str(asof or ""),
                "data_through": "", "reference": ""}
    return {"text": text(a, data_through, today=today),
            "round": round_text(a) if hub else "",
            "asof": a.isoformat(),
            "data_through": through(a, data_through).isoformat(),
            "reference": reference_date(a)}


# --- what the run read --------------------------------------------------------

def recorded_through(outcome) -> str:
    """The newest week a run recorded reading (outcome "data_source"
    "newest_week", data.source_record), '' when it recorded none."""
    if isinstance(outcome, str):
        try:
            outcome = json.loads(outcome or "{}")
        except ValueError:
            return ""
    src = (outcome or {}).get("data_source") if isinstance(outcome, dict) \
        else None
    wk = str((src or {}).get("newest_week") or "") if isinstance(src, dict) \
        else ""
    return wk if _day(wk) else ""


def series_through(observed, asof="") -> str:
    """The newest week of a stored series ({location: [[date, value],
    ...]}) no later than the as-of; '' when it holds none."""
    a = _day(asof)
    best = None
    for rows in (observed or {}).values() if isinstance(observed, dict) else ():
        for row in rows or ():
            try:
                d = _day(row[0])
            except (TypeError, IndexError, KeyError):
                continue
            if d is not None and (a is None or d <= a) \
                    and (best is None or d > best):
                best = d
    return best.isoformat() if best else ""


@lru_cache(maxsize=512)
def _stored(path: str, stamp: int, asof: str) -> str:
    try:
        res = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return series_through(res.get("observed") if isinstance(res, dict)
                          else None, asof)


def stored_through(workroot, asof="") -> str:
    """The newest week of the series a run stored (its results.json
    "observed"), read once per file version; '' when there is none."""
    if not workroot:
        return ""
    p = Path(workroot) / "results.json"
    try:
        stamp = os.stat(p).st_mtime_ns
    except OSError:
        return ""
    return _stored(str(p), stamp, str(asof or ""))


def data_through(asof, outcome=None, workroot=None) -> str:
    """The newest week a run read: recorded, else from its stored series,
    else its as-of; never later than the as-of ('' when unreadable)."""
    a = _day(asof)
    if a is None:
        return ""
    got = recorded_through(outcome) or stored_through(workroot, a.isoformat())
    return through(a, got).isoformat()
