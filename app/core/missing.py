"""PRODUCTION (off by default): the optional missing-data rules for the
newest reported weeks, read by both engines (app/core/engines/analogue.py,
app/core/engines/pf.py) and set through two model settings
(app/core/knobs.py: data.trailing_zero, data.partial_week), plus the
per-state data choices a forecaster makes on the Forecast tab (the Data
issues box, app/ui/templates/_data_issues.html) and the Groundhog's
zero-anchor rule (groundhog.zero_anchor, no shipped default).

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

Per-state choices (extra["data_choices"], CHOICES_KEY) are recorded data
decisions, not model changes: they never mark a run modified. The record:

  {"week": "2026-07-04", "source_sha256": "<the file's digest>",
   "states": {"Arkansas": {"issue": "zero", "reported": [["2026-07-04", 0.0]],
                           "choice": "level", "from_week": "2026-07-04",
                           "recommended": "level", "followed": true}}}

Every state the Data issues box listed is recorded, with the choice the
box recommended (app/core/reported.py recommend) and whether it was
followed; a run whose week had no such state has no key, so a shipped
spec is unchanged byte for byte. rules_for() gives an engine one
location's rules; rules_of() the run-wide ones.

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

#: a newest week of 0 after a week of ZERO_FLOOR or more is worded "reads 0
#: after 19, 24, 3" (app/core/reported.py); the hub's 119 newest-week
#: zeros all followed a week of 7 or fewer (docs/MISSING-DATA.md, "large
#: neighbour"). Display only: no run rule reads it.
ZERO_FLOOR = 10.0

KEYS = {"data.trailing_zero": TRAILING_ZERO, "data.partial_week": PARTIAL_WEEK}

#: rules a custom dataset cannot carry: the partial-week floor
#: (PARTIAL_FLOOR admissions in the prior week) assumes hospital admission
#: counts, which a dataset's values need not be. Hidden from its Model
#: settings panels and refused for its runs; trailing_zero stays.
HUB_ONLY_KEYS = ("data.partial_week",)

# --- the Groundhog's zero-anchor rule ---------------------------------------------
#
# The Groundhog forecasts anchor x donor ratio, so a newest week reading 0
# gives it nothing to scale (flubnf/analogue.py returns None). What it does
# instead is the forecaster's choice, per jurisdiction on a live run and
# per replay; there is no shipped default (ZERO_ANCHOR_DEFAULT is None,
# "ask"). The rules, scored on the archive (docs/MISSING-DATA.md):
#
#   abstain  no forecast (what every run did before the rule existed)
#   level    anchor = the mean of the newest ZERO_ANCHOR_WEEKS reported
#            weeks, zeros included, at the 0 week's own date; when all of
#            them read 0, Poisson quantiles at ZERO_ANCHOR_LAM
#   extend   anchor = the newest positive week at its own date, the donor
#            ratio spanning the trailing zeros as well (1 or 2 of them,
#            MAX_CARRY; longer runs fall back to the Poisson quantiles)
#   blend    the level and extend quantiles averaged level by level

ZERO_ANCHOR_KEY = "groundhog.zero_anchor"
ZERO_ANCHOR_RULES = ("abstain", "level", "extend", "blend")
ZERO_ANCHOR_DEFAULT = None
#: what a replay recorded before the rule existed did
ZERO_ANCHOR_LEGACY = "abstain"
#: level: the mean of this many newest reported weeks
ZERO_ANCHOR_WEEKS = 4
#: the Poisson rate's bounds when every one of them reads 0 (app/core/floor.py's)
ZERO_ANCHOR_LAM = (0.35, 5.0)
#: the engine note's prefix, counted apart from "no forecast" and "abstained"
ZERO_ANCHOR_NOTE = "zero-anchor"

# --- per-state choices ---------------------------------------------------------------

CHOICES_KEY = "data_choices"
#: a state whose newest week reads 0: the Groundhog's rule for it (the
#: Oracle SIHRS keeps the 0), or both models from the week before, or out
ZERO_CHOICES = ZERO_ANCHOR_RULES + ("set_aside", "omit")
#: a state whose newest week collapsed (under PARTIAL_SHARE of a week of
#: PARTIAL_FLOOR or more)
COLLAPSED_CHOICES = ("keep", "set_aside", "omit")
#: a state with no row or a blank value: the engines' own walk, or out
UNREPORTED_CHOICES = ("carry", "omit")
ISSUE_CHOICES = {"zero": ZERO_CHOICES, "collapsed": COLLAPSED_CHOICES,
                 "no row": UNREPORTED_CHOICES, "blank": UNREPORTED_CHOICES}
#: the choice that changes nothing (the box preselects the recommendation,
#: app/core/reported.py recommend; a zero has no such choice)
DEFAULT_CHOICE = {"collapsed": "keep", "no row": "carry", "blank": "carry"}
#: the data_flags rule names the per-state choices record
SET_ASIDE_RULE = "set aside (Forecast tab)"
LEFT_OUT_RULE = "left out (Forecast tab)"
#: the engine note when a set-aside no longer matches the data read
NOT_APPLIED_NOTE = "set-aside not applied"


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


def zero_anchor_of(extra) -> str:
    """The run-wide zero-anchor rule a spec's extra records (the knob), or
    "" when none: the engine then reads ZERO_ANCHOR_LEGACY, and a live run
    is refused earlier unless every zero state has its own choice."""
    rec = (extra or {}).get("knobs") if isinstance(extra, Mapping) else None
    rec = rec if isinstance(rec, Mapping) else {}
    v = str(rec.get(ZERO_ANCHOR_KEY) or "")
    return v if v in ZERO_ANCHOR_RULES else ""


def choices_of(extra) -> dict:
    """The per-state choices record ({location: entry}); {} when none."""
    rec = (extra or {}).get(CHOICES_KEY) if isinstance(extra, Mapping) else None
    st = rec.get("states") if isinstance(rec, Mapping) else None
    return dict(st) if isinstance(st, Mapping) else {}


def followed_line(states: Mapping) -> str:
    """The run page's count of a choices record's states against the
    box's recommendations: "5 states, 4 recommended, 1 changed"; "" when no
    entry carries a "followed" flag (a record from before the rule)."""
    flagged = [st for st in (states or {}).values()
               if isinstance(st, Mapping) and "followed" in st]
    if not flagged:
        return ""
    n = len(states)
    yes = sum(bool(st.get("followed")) for st in flagged)
    changed = n - yes
    return (f"{n} state{'s' if n != 1 else ''}, {yes} recommended, "
            f"{changed} changed")


def rules_for(extra, loc: str, member: str) -> dict:
    """One location's rules for one member ("analogue" or "pf"): the
    run-wide rules (rules_of), the zero-anchor rule (the knob, or the
    state's own choice for the Groundhog) and, when the state was set
    aside on the Forecast tab, "set_aside" = its recorded entry (the weeks
    to match against the data and trim). Falls back to rules_of when the
    state has no entry, so a run without choices is unchanged."""
    out = rules_of(extra)
    za = zero_anchor_of(extra)
    if za:
        out[ZERO_ANCHOR_KEY] = za
    st = choices_of(extra).get(loc)
    if not isinstance(st, Mapping):
        return out
    choice = str(st.get("choice") or "")
    if choice == "set_aside":
        out["set_aside"] = dict(st)
    elif choice in ZERO_ANCHOR_RULES and member == "analogue":
        out[ZERO_ANCHOR_KEY] = choice
    return out


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


def set_aside_flags(weeks: Sequence[str], values: Sequence[float],
                    rules: Mapping) -> tuple:
    """A state's set-aside weeks, matched against the data actually read:
    (flags as tail_flags gives them, note). `weeks` (ISO dates) and
    `values` are the reported rows, oldest first, after the trims. The
    recorded (week, value) pairs must be the newest rows and still hold
    the recorded values; otherwise nothing is trimmed and the note says
    what changed ("set-aside not applied: 2026-07-04 now reads 3"), so a
    choice made on one pull never trims another's data."""
    st = rules.get("set_aside") if rules else None
    if not isinstance(st, Mapping):
        return [], ""
    rec = [(str(w)[:10], float(v)) for w, v in (st.get("reported") or ())]
    if not rec or len(rec) > MAX_CARRY:
        return [], ""
    n = len(values)
    if n <= len(rec):
        return [], f"{NOT_APPLIED_NOTE}: too few reported weeks"
    have = {str(w)[:10]: float(v) for w, v in zip(weeks, values)}
    for w, v in rec:
        if w not in have:
            return [], f"{NOT_APPLIED_NOTE}: {w} is not in the data"
        if have[w] != v:
            return [], f"{NOT_APPLIED_NOTE}: {w} now reads {have[w]:g}"
    tail = [str(w)[:10] for w in weeks[n - len(rec):]]
    if sorted(tail) != sorted(w for w, _ in rec):
        return [], (f"{NOT_APPLIED_NOTE}: the newest weeks are now "
                    f"{', '.join(tail)}")
    return [(i, SET_ASIDE_RULE) for i in range(n - len(rec), n)], ""


def trim_flags(weeks: Sequence[str], values: Sequence[float],
               rules: Mapping) -> tuple:
    """Both trims for one location: the per-state set-aside when the state
    has one (it replaces the run-wide rules for that state), else
    tail_flags. Returns (flags, note)."""
    if rules and "set_aside" in rules:
        return set_aside_flags(weeks, values, rules)
    return tail_flags(values, rules), ""


def zero_run(values: Sequence[float]) -> int:
    """How many of the newest `values` read 0 (or less), newest first."""
    run = 0
    for v in reversed([float(x) for x in values]):
        if v > 0:
            break
        run += 1
    return run


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


def unreported_flags(flags) -> dict:
    """A run record's flags without the zero-anchor and left-out rows
    (those name a forecast made or a state left out, not a week treated as
    unreported): the input for line()."""
    out = {}
    for m, rows in (flags or {}).items():
        out[m] = [r for r in rows or ()
                  if not str(r.get("rule", "")).startswith(ZERO_ANCHOR_NOTE)
                  and r.get("rule") != LEFT_OUT_RULE]
    return out


def choices_line(flags, choices: Mapping | None = None) -> str:
    """The run page's "Data issues" value: counts by outcome over the
    recorded flags and choices, e.g. "3 set aside, 1 left out, 2
    zero-anchor level"; "" when there is nothing to count."""
    seen: dict = {}
    for m, rows in (flags or {}).items():
        for r in rows or ():
            rule = str(r.get("rule", ""))
            if rule == SET_ASIDE_RULE:
                seen.setdefault(("set aside", r.get("location")), 1)
            elif rule == LEFT_OUT_RULE:
                seen.setdefault(("left out", r.get("location")), 1)
            elif rule.startswith(ZERO_ANCHOR_NOTE):
                seen.setdefault((rule, r.get("location")), 1)
    counts: dict = {}
    for (what, _loc) in seen:
        counts[what] = counts.get(what, 0) + 1
    order = ["set aside", "left out"] + [f"{ZERO_ANCHOR_NOTE} {r}"
                                        for r in ZERO_ANCHOR_RULES]
    bits = [f"{counts[k]} {k}" for k in order if k in counts]
    bits += [f"{counts[k]} {k}" for k in sorted(counts) if k not in order]
    return ", ".join(bits)


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
                for rows in (unreported_flags(flags) or {}).values()
                for r in rows or ()}
        n += len(seen)
        weeks += bool(seen)
    if not n:
        return "on; no week flagged"
    total = len(by_week)
    return (f"{n} newest week{'s' if n != 1 else ''} treated as unreported, "
            f"in {weeks} of {total} forecast week{'s' if total != 1 else ''}")


def replay_zero_anchor_count(by_week) -> str:
    """A replay's count of zero-anchor location-weeks by rule ({as-of:
    {member: [rows]}}): "2 level, 1 abstain" style; "" when none."""
    if not isinstance(by_week, Mapping) or not by_week:
        return ""
    counts: dict = {}
    for flags in by_week.values():
        for rows in (flags or {}).values():
            for r in rows or ():
                rule = str(r.get("rule", ""))
                if rule.startswith(ZERO_ANCHOR_NOTE + " "):
                    k = rule[len(ZERO_ANCHOR_NOTE) + 1:]
                    counts[k] = counts.get(k, 0) + 1
    if not counts:
        return ""
    n = sum(counts.values())
    by = ", ".join(f"{counts[r]} {r}" for r in ZERO_ANCHOR_RULES if r in counts)
    return f"{n} location-week{'s' if n != 1 else ''} ({by})"
