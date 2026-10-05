"""Display-only aids for the Forecast tab (GET /forecast): the date's
reference date and FluSight window, the next round's data, the run the fan
card draws, the location presets, the last form kept across a restart and
what the form changes against the last run.

Nothing here touches a run: the form still posts explicit values, and the
only state written is app/state/last_form.json (the form's non-date fields,
restored when the console starts with no form in memory). GET
/api/forecast/week-info is read-only; routes/forecast.py includes the
router.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

#: the file the last form's non-date fields live in (under runs.APP_STATE,
#: read at call time so the test suite's state folder applies)
LAST_FORM_NAME = "last_form.json"

#: fields never kept across a restart: the date (the form opens on the
#: newest week) and what belongs to one week's data or one refusal
_NOT_KEPT = ("forecast_date", "season_start", "data_choices", "ms_refused")

#: the hub publishes a week's data on the Wednesday after it (Saturday + 4)
_PUBLISH_LAG_DAYS = 4


# === The last form, kept across a restart ===
def _last_form_path() -> Path:
    from app.core import runs as _runs
    return Path(_runs.APP_STATE) / LAST_FORM_NAME


def _kept(form: dict) -> dict:
    """The fields of a form worth keeping, JSON-safe."""
    out = {}
    for k, v in (form or {}).items():
        if k in _NOT_KEPT:
            continue
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out


def save_last_form(form: dict) -> None:
    """Write the form's non-date fields to app/state/last_form.json when
    they changed; never raises (a read-only disk only loses the memory)."""
    kept = _kept(form)
    if not kept:
        return
    p = _last_form_path()
    try:
        text = json.dumps(kept, sort_keys=True, indent=1)
        if p.is_file() and p.read_text(encoding="utf-8") == text:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def load_last_form() -> dict:
    """The kept fields ({} when none or unreadable)."""
    try:
        got = json.loads(_last_form_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(got, dict):
        return {}
    return {k: v for k, v in got.items() if k not in _NOT_KEPT}


#: when this process started: only a file an EARLIER process wrote is
#: restored (one written since is already in memory, or was cleared on
#: purpose), and only once
_STARTED = time.time()
_restored = {"done": False}


def restore_last_form(last_form: dict, default_date) -> bool:
    """Fill an empty in-memory form (state._last_form, in place) from the
    kept file after a restart, its date the default (`default_date`,
    called only then). Once per process; True when it restored."""
    if last_form or _restored["done"]:
        return False
    _restored["done"] = True
    try:
        if _last_form_path().stat().st_mtime >= _STARTED:
            return False
    except OSError:
        return False
    kept = load_last_form()
    if not kept or not kept.get("locations"):
        return False
    try:
        kept["forecast_date"] = default_date()
    except Exception:
        return False
    last_form.update(kept)
    return True


# === The date: reference date and FluSight window ===
def week_info(week: str, today=None, now=None) -> dict:
    """{"week", "reference", "badge": [state, words], "state", "text"} for
    an anchor week (a Saturday): the reference date is a week later, the
    window the hub's for that round (output._date_status); {} for a
    non-date."""
    try:
        w = date.fromisoformat(str(week)[:10])
    except (TypeError, ValueError):
        return {}
    ref = (w + timedelta(days=7)).isoformat()
    from app.ui.routes.output import _date_status
    st = _date_status(ref, today=today, now=now) or {}
    badge = list(st.get("badge") or ("neutral", "window unknown"))
    return {"week": w.isoformat(), "reference": ref, "badge": badge,
            "state": st.get("state", ""), "text": st.get("text", "")}


@router.get("/api/forecast/week-info")
def api_week_info(week: str = ""):
    """The Forecast form's date row (read-only): a week's reference date
    and FluSight window badge."""
    return week_info(week)


def next_round(default_week: str, today=None) -> dict | None:
    """When the default as-of's reference date is not an open round (not a
    FluSight round, or its window closed): the next round still open, the
    week of data it needs and the Wednesday that data is expected.
    {"round", "needs", "expected", "expected_past"} or None."""
    info = week_info(default_week, today=today)
    if not info or info["state"] in ("due", "soon", ""):
        return None
    try:
        from app.core import hubcheck
        rules = hubcheck.vendored_rules()
        rounds = sorted(str(r)[:10] for r in rules["rounds"])
    except Exception:
        return None
    today = today or date.today()
    for r in rounds:
        if r <= info["reference"]:
            continue
        last = hubcheck.submission_window(r, rules)[1]
        if last < today:
            continue
        needs = date.fromisoformat(r) - timedelta(days=7)
        exp = needs + timedelta(days=_PUBLISH_LAG_DAYS)
        return {"round": r, "needs": needs.isoformat(),
                "expected": f"{exp:%a %b} {exp.day}",
                "expected_past": exp < today}
    return None


# === The latest run: its error, the run the fans draw ===
def error_head(error: str) -> str:
    """A run's error as one short clause: before its first parenthesis or
    newline, capitalised, "location(s)" said in the plural it needs."""
    def plural(m):
        n = int(m.group(1))
        return f"{n} {m.group(2)}{'' if n == 1 else 's'}"
    text = re.sub(r"(\d+) (\w+)\(s\)", plural, str(error or "").strip())
    head = re.split(r"\s*[\(\n]", text, maxsplit=1)[0]
    head = head.strip().rstrip(":;,.")
    return head[:1].upper() + head[1:] if head else ""


def fan_run(ledger_rows: list, rid) -> dict | None:
    """The run the Forecasts card draws: {"run_id", "label", "earlier"}
    (earlier: it is not the newest hub row of the ledger, which failed or
    is still to finish)."""
    if not rid:
        return None
    from app.ui.shared import _run_label
    spec = ""
    for r in ledger_rows or []:
        if r.get("run_id") == rid:
            spec = r.get("spec") or ""
            break
    else:
        try:
            from app.core.runs import Ledger
            row = Ledger().row(rid)
            spec = (row or {}).get("spec") or ""
        except Exception:
            spec = ""
    newest = (ledger_rows or [{}])[0].get("run_id") if ledger_rows else None
    return {"run_id": rid, "label": _run_label(rid, spec, tag=False),
            "earlier": bool(newest and newest != rid)}


# === Location presets ===
def _spec(row) -> dict:
    try:
        s = json.loads((row or {}).get("spec") or "{}")
        return s if isinstance(s, dict) else {}
    except ValueError:
        return {}


def _as_form(locs, all_locs: list, us_choice: str) -> list:
    """A run's locations as the checklist's values: the state names it
    names that the list holds, and the national box's value."""
    from app.core import us_national as _usn
    names = set(all_locs)
    out = [l for l in _usn.state_names(locs) if l in names]
    if any(_usn.is_us(l) for l in locs or []):
        out.append(us_choice)
    return out


def _failed_locations(row, all_locs: list, us_choice: str) -> list:
    """The latest run's locations whose fits failed (its pf_failures cells,
    <Name>_r<k>), or every location when it failed as a whole before any
    fit (a prepare that failed everywhere)."""
    try:
        o = json.loads((row or {}).get("outcome") or "{}")
    except ValueError:
        return []
    by_tag = {l.replace(" ", "_"): l for l in all_locs}
    by_tag["US"] = us_choice
    fails = o.get("pf_failures") if isinstance(o, dict) else None
    out = []
    if isinstance(fails, dict) and fails:
        for cell in fails:
            name = by_tag.get(re.sub(r"_r\d+$", "", str(cell)))
            if name and name not in out:
                out.append(name)
        return out
    err = str((o or {}).get("error") or "")
    if (row or {}).get("status") in ("error", "failed") and \
            "failed for all" in err:
        return _as_form(_spec(row).get("locations") or [], all_locs, us_choice)
    return []


def presets(ledger_rows: list, all_locs: list, us_choice: str) -> dict:
    """The checklist's preset chips' picks: "last" (the latest hub run's
    locations) and "failed" (its failed locations); [] when none."""
    row = (ledger_rows or [None])[0] if ledger_rows else None
    if not row:
        return {"last": [], "failed": []}
    return {"last": _as_form(_spec(row).get("locations") or [], all_locs,
                             us_choice),
            "failed": _failed_locations(row, all_locs, us_choice)}


# === The form against the last run ===
def last_run_values(ledger_rows: list) -> dict | None:
    """What the latest hub run was given, as the form's controls hold it:
    {"engine", "locations" (the names, "all" for the 53), "knobs": {key:
    the panel's raw value}} for the knobs that applied to it; None without
    a run or a readable spec. The season start is left out (it follows the
    date)."""
    row = (ledger_rows or [None])[0] if ledger_rows else None
    spec = _spec(row)
    if not spec:
        return None
    from app.core import knobs as K
    from app.core import us_national as _usn
    locs = list(spec.get("locations") or [])
    states = _usn.state_names(locs)
    us = len(locs) > len(states)
    try:
        # an older spec may lack a field a knob reads: RunSpec's defaults
        import dataclasses
        from app.core.runs import RunSpec
        full = {f.name: f.default for f in dataclasses.fields(RunSpec)
                if f.default is not dataclasses.MISSING}
        full.update(spec)
        table = K.effective(full)
    except Exception:
        table = []
    reg = {k.key: k for k in K.REGISTRY}
    kn = {}
    for r in table:
        if not r.get("applies") or r["key"] == "run.season_start":
            continue
        k = reg.get(r["key"])
        if k is None or r["key"] in K.DECISION_KEYS:
            continue
        try:
            kn[r["key"]] = K._raw(k, r["value"])
        except Exception:
            continue
    return {"engine": str(spec.get("engine") or "all"),
            "locations": (["all"] if (len(states) >= 52 and us)
                          else sorted(states) + (["US"] if us else [])),
            "knobs": kn}


def page_aids(ledger_rows: list, rid, all_locs: list, us_choice: str,
              default_date: str) -> dict:
    """Everything above the Forecast page shows, each part None or empty
    when it cannot be read (the page renders without it)."""
    out = {"fan_run": None, "next_round": None,
           "presets": {"last": [], "failed": []}, "last_run": None}
    for key, fn in (("fan_run", lambda: fan_run(ledger_rows, rid)),
                    ("next_round", lambda: next_round(default_date)),
                    ("presets", lambda: presets(ledger_rows, all_locs,
                                                us_choice)),
                    ("last_run", lambda: last_run_values(ledger_rows))):
        try:
            out[key] = fn()
        except Exception:
            pass
    return out
