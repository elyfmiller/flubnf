"""Form parsing shared by the run forms: the model-settings (knob) channel
of /run, /runs/{id}/rerun, /retro/run and the dataset forms, the field
coercions, and anchor-date resolution (one definition for the form's anchor
line and the run).

Request is imported at module level: FastAPI resolves _knob_form's
`request: Request` annotation from this module's globals.
"""
from __future__ import annotations

import re

from fastapi import Request

from app.ui import state


# === Anchor dates ===
def resolve_anchor(day: str, vintages=None):
    """(anchor_vintage, why) for any typed date; ONE definition for the
    form's anchor line and the run, so they cannot disagree.

    A non-Saturday snaps back to Saturday, then to the newest available
    week (an archived vintage, or the live target file's newest week). A
    typed Saturday is returned as-is even when it has no data (the caller
    refuses it rather than re-aiming).
    """
    from datetime import date as _d, timedelta as _td
    try:
        d = _d.fromisoformat(day)
    except (ValueError, TypeError):
        return None, ""
    if vintages is None:
        try:
            vintages = state.data_mod.available_weeks()
        except Exception:
            vintages = []
    if d.weekday() == 5:
        return day, "typed"
    sat = (d - _td(days=(d.weekday() - 5) % 7)).isoformat()
    earlier = [v for v in vintages if v <= sat]
    if earlier and earlier[-1] != sat:
        return earlier[-1], "not-published-yet"
    return (earlier[-1] if earlier else sat), "snapped"


def _default_forecast_date() -> str:
    """Latest Saturday, clamped to the newest week the hub's data holds
    (the live target file's, or the newest archived vintage: the hub stops
    publishing off-season and archives by hand)."""
    import datetime as dt
    d = dt.date.today()
    sat = str(d - dt.timedelta(days=(d.weekday() - 5) % 7))
    newest = state.data_mod.newest_week()
    return min(sat, newest) if newest else sat


# === Model knobs (app/core/knobs.py) on the run and retro forms ===
class _LazyKnobs:
    """app.core.knobs on first use: it imports the engines, which the app's
    start must not wait for."""
    FORM_PREFIX = "knob."          # held equal to knobs.FORM_PREFIX by tests

    def __getattr__(self, name):
        from app.core import knobs
        return getattr(knobs, name)


_knobs = _LazyKnobs()


async def _knob_form(request: Request) -> dict:
    """The panel's `knob.<key>` fields ({key: raw}); the parsed form is
    cached by Starlette, so the route's own Form fields still read it."""
    try:
        form = await request.form()
    except Exception:
        return {}
    out = _KnobFields()
    for k, v in form.multi_items():
        if not k.startswith(_knobs.FORM_PREFIX):
            continue
        key = k[len(_knobs.FORM_PREFIX):]
        if key in out or not isinstance(v, str):
            # sent twice (or as a file): _knob_raw refuses it in words
            # rather than silently taking the last value
            if k not in out.repeated:
                out.repeated.append(k)
            continue
        out[key] = v
    return out


#: the Data issues box's field prefix (templates/_data_issues.html): one
#: select per state, gap.<fips>; gap._sha is the data file the box was
#: built from
GAP_PREFIX = "gap."


async def _gap_form(request: Request) -> dict:
    """The Data issues box's `gap.<fips>` fields ({fips: raw}); blank
    values kept (a zero state left at "Choose…" is what the route refuses).
    {} when the fieldset was disabled (an older anchor week) or absent."""
    try:
        form = await request.form()
    except Exception:
        return {}
    out = {}
    for k, v in form.multi_items():
        if k.startswith(GAP_PREFIX) and isinstance(v, str):
            out[k[len(GAP_PREFIX):]] = v.strip()
    return out


class _KnobFields(dict):
    """_knob_form's result: {key: raw}, plus the field names the form sent
    more than once (refused by _knob_raw)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.repeated: list = []


def _str_field(v) -> str:
    """A form value, or '' for a FastAPI default object (a direct call)."""
    return v if isinstance(v, str) else ("" if v is None or not isinstance(
        v, (int, float)) else str(v))


def _int_field(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _season_auto(*days) -> set:
    """August 1 of each day's season (RunSpec's rule), as the panel's
    script fills Season start: the values that mean "the default"."""
    out = set()
    for d in days:
        m = re.match(r"^(\d{4})-(\d{2})", str(d or ""))
        if m:
            y = int(m.group(1)) if int(m.group(2)) >= 8 else int(m.group(1)) - 1
            out.add(f"{y}-08-01")
    return out


def _knob_panel(scope: str, form: dict | None = None,
                season_auto=(), busy: bool = False,
                **panel_kw) -> dict | None:
    """The Model settings panel's context (knobs.panel) with the values a
    form last held: the knob fields, then the older field names. None
    (no panel) if the registry cannot be read, so a page still renders.
    `panel_kw` passes through to knobs.panel (a dataset's member names).

    `season_auto`: the Season start values the panel's script fills in by
    itself (the browser posts that filled value with every run); one of
    them is the default, not a change, so it neither marks the panel
    modified nor survives as a typed value. The panel renders open after
    a refusal over its settings (form["ms_refused"]), or when its values
    differ from the defaults and no run is in progress (`busy`); closed
    otherwise. The page's script remembers the user's own open/closed
    choice for the session."""
    form = form or {}
    vals = {k: str(v) for k, v in (form.get("knobs") or {}).items()}
    for fld, key in _knobs.LEGACY_FIELDS.items():
        v = form.get(fld)
        if v is None or v == "":
            continue
        if fld == "drop_same_day":
            v = "1" if _int_field(v) else "0"
        vals.setdefault(key, str(v))
    if vals.get("run.season_start") in set(season_auto or ()):
        del vals["run.season_start"]
    try:
        p = _knobs.panel(scope, vals, **panel_kw)
    except Exception:
        return None
    p["open"] = bool(form.get("ms_refused")) or (
        bool(p.get("modified")) and not busy)
    return p


def _knob_raw(fields, knobs_json) -> dict:
    """The knob channel's raw values: the JSON field (one-click resume,
    re-run) under the panel's own fields. A malformed JSON field raises
    KnobError, so the route refuses rather than guessing; so does a knob
    field the form sent more than once."""
    repeated = getattr(fields, "repeated", None)
    if repeated:
        raise _knobs.KnobError(
            "the form sent " + ", ".join(repeated) + " more than once, so "
            "which value to use is not clear")
    raw: dict = {}
    text = _str_field(knobs_json).strip()
    if text:
        import json as _json
        try:
            got = _json.loads(text)
        except ValueError:
            raise _knobs.KnobError("the recorded model settings are not "
                                   "readable JSON") from None
        if not isinstance(got, dict):
            raise _knobs.KnobError("the recorded model settings are not a "
                                   "dictionary")
        raw.update(got)
    if isinstance(fields, dict):
        raw.update({k: v for k, v in fields.items() if str(v).strip()})
    return raw
