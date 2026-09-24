"""PRODUCTION (off by default): the optional missing-data rules for the
newest reported weeks, read by both engines (app/core/engines/analogue.py,
app/core/engines/pf.py) and set through two model settings
(app/core/knobs.py: data.trailing_zero, data.partial_week).

The standing policy is unchanged: a missing week is dropped, never imputed
(app/core/data.py). These rules only decide that a REPORTED newest week is
treated as unreported; the engines then move their anchor back exactly as
weeks_to_drop does, so every horizon stays aligned to the as-of date.

  trailing_zero "missing"  the newest 1 or 2 weeks read 0 after a positive
                           week (no carry past MAX_CARRY weeks: longer
                           runs are kept, and the Groundhog abstains).
  partial_week  "missing"  the newest week is below PARTIAL_SHARE of the
                           week before, and that week had PARTIAL_FLOOR or
                           more admissions (a collapsed, partial report).

Why only these, and why off: docs/MISSING-DATA.md (the hub survey and the
replay). Nothing here is ever interpolated.
"""
from __future__ import annotations

from typing import Mapping, Sequence

#: shipped values (the knobs' defaults are read from these)
TRAILING_ZERO = "keep"
PARTIAL_WEEK = "keep"
CHOICES = ("keep", "missing")

#: longest run of trailing zeros the trailing-zero rule carries back over
MAX_CARRY = 2
#: the partial-week rule: newest < PARTIAL_SHARE * previous, previous >= PARTIAL_FLOOR
PARTIAL_SHARE = 0.2
PARTIAL_FLOOR = 20.0

#: a newest week of 0 after a week of ZERO_FLOOR or more is shown as a
#: likely non-report (app/core/reported.py); the hub's 119 newest-week
#: zeros all followed a week of 7 or fewer (docs/MISSING-DATA.md, "large
#: neighbour"). Display only: no run rule reads it.
ZERO_FLOOR = 10.0

KEYS = {"data.trailing_zero": TRAILING_ZERO, "data.partial_week": PARTIAL_WEEK}

#: rules a custom dataset cannot carry: the partial-week floor
#: (PARTIAL_FLOOR admissions in the prior week) assumes hospital admission
#: counts, which a dataset's values need not be. Hidden from its Model
#: settings panels and refused for its runs; trailing_zero stays.
HUB_ONLY_KEYS = ("data.partial_week",)


def refuse_on_dataset(extra, name: str) -> None:
    """Raise ValueError when a dataset run's extra turns on a HUB_ONLY_KEYS
    rule (the engines call this on their dataset branch)."""
    bad = [k for k in HUB_ONLY_KEYS if k in rules_of(extra)]
    if bad:
        raise ValueError(
            f"{', '.join(bad)}: this rule's floor (a prior week of "
            f"{PARTIAL_FLOOR:g} or more) assumes hospital admission counts "
            f"and cannot run on the custom dataset {name!r}")


def rules_of(extra) -> dict:
    """{key: choice} of the rules a spec's extra records as "missing"; {}
    on a shipped spec (the knobs record holds non-default values only)."""
    rec = (extra or {}).get("knobs") if isinstance(extra, Mapping) else None
    rec = rec if isinstance(rec, Mapping) else {}
    return {k: rec[k] for k in KEYS if rec.get(k) == "missing"}


def tail_flags(values: Sequence[float], rules: Mapping) -> list:
    """The newest reported weeks to treat as unreported, newest last:
    a list of (index into `values`, rule name). `values` are the reported
    counts, oldest first, after any weeks_to_drop or same-day trim. Empty
    when no rule is on or none fires."""
    if not rules or not len(values):
        return []
    v = [float(x) for x in values]
    n = len(v)
    if rules.get("data.trailing_zero") == "missing" and v[-1] <= 0:
        run = 0
        while run < n and v[n - 1 - run] <= 0:
            run += 1
        if run <= MAX_CARRY and run < n and v[n - 1 - run] > 0:
            return [(i, "trailing zero") for i in range(n - run, n)]
        return []
    if (rules.get("data.partial_week") == "missing" and n >= 2
            and v[-2] >= PARTIAL_FLOOR and v[-1] < PARTIAL_SHARE * v[-2]):
        return [(n - 1, "partial week")]
    return []


def line(flags) -> str:
    """The run page's one line for a run record's flags ({member: [rows]});
    "" when nothing was flagged. Each row: {location, week, value, rule}."""
    rows = []
    seen = set()
    for member_rows in (flags or {}).values():
        for r in member_rows or ():
            key = (r.get("location"), r.get("week"))
            if key not in seen:
                seen.add(key)
                rows.append(r)
    if not rows:
        return ""
    # one short line: weeks per location, newest week and rules named once;
    # every week, value and rule stays in the record (outcome data_flags)
    n = len(rows)
    per: dict = {}
    for r in rows:
        per[r["location"]] = per.get(r["location"], 0) + 1
    rules = sorted({r["rule"] for r in rows})
    newest = max(r["week"] for r in rows)
    bits = [f"{loc} {c}" for loc, c in per.items()]
    return (f"{n} week{'s' if n != 1 else ''} to {newest} treated as "
            f"unreported ({', '.join(rules)}): " + ", ".join(bits))


def cell_flags(cells) -> list:
    """The particle filter's flagged weeks from prepare()'s cells (the
    per-cell `data_flags`; replicate 0 only, as every replicate holds the
    same rows): one {location, week, value, rule} row each."""
    out = []
    for c in cells or ():
        if isinstance(c, dict) and c.get("replicate", 0) == 0:
            out += [{"location": c.get("location"), **r}
                    for r in c.get("data_flags") or ()]
    return out


def replay_count(by_week) -> str:
    """A replay's settings value for its flagged weeks ({as-of: {member:
    [rows]}}, recorded only with a rule on): "" when nothing is recorded;
    else how many newest weeks were treated as unreported (once per as-of
    week and location, members pooled) in how many forecast weeks."""
    if not isinstance(by_week, Mapping) or not by_week:
        return ""
    n = weeks = 0
    for flags in by_week.values():
        seen = {(r.get("location"), r.get("week"))
                for rows in (flags or {}).values() for r in rows or ()}
        n += len(seen)
        weeks += bool(seen)
    if not n:
        return "on; no week flagged"
    total = len(by_week)
    return (f"{n} newest week{'s' if n != 1 else ''} treated as unreported, "
            f"in {weeks} of {total} forecast week{'s' if total != 1 else ''}")
