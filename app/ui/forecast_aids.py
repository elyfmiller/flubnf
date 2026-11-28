"""Display-only aids for the Forecast tab (GET /forecast): the date's
reference date and FluSight window, the next round's data, the run the fan
card draws, the location presets, the last form kept across a restart and
what the form changes against the last run.

Nothing here touches a run: the form still posts explicit values, and the
only state written is app/state/last_form.json (the form's non-date fields,
restored when the console starts with no form in memory). The read-only
GET /api/forecast/week-info (routes/forecast.py) answers with week_info.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

#: the file the last form's non-date fields live in (under runs.APP_STATE,
#: read at call time so the test suite's state folder applies)
LAST_FORM_NAME = "last_form.json"

#: fields never kept across a restart: the date (the form opens on the
#: newest week), what belongs to one week's data or one refusal, and the
#: override with its reason (one run's decision, never the next one's)
_NOT_KEPT = ("forecast_date", "season_start", "data_choices", "ms_refused",
             "submit_modified", "modified_reason")

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
    """{"week", "label", "round", "reference", "badge": [state, words],
    "state", "text"} for an anchor week: "label" is what a run from it
    reads and forecasts, in the words every run is named by
    (app/core/run_label: "Data through Nov 21 · forecasts for weeks ending
    Nov 28 to Dec 19"); "round" the hub round it answers ("FluSight round
    2026-11-28", the reference date a week later); the badge the hub's
    window for that round (output._date_status). {} for a non-date."""
    try:
        w = date.fromisoformat(str(week)[:10])
    except (TypeError, ValueError):
        return {}
    from app.core import run_label as _rl
    ref = (w + timedelta(days=7)).isoformat()
    from app.ui.routes.output import _date_status
    st = _date_status(ref, today=today, now=now) or {}
    badge = list(st.get("badge") or ("neutral", "window unknown"))
    return {"week": w.isoformat(), "label": _rl.text(w, today=today),
            "round": _rl.round_text(w), "reference": ref, "badge": badge,
            "state": st.get("state", ""), "text": st.get("text", "")}


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


#: the newest run's status, as the "earlier run" badge says why it is not
#: the one drawn
_NOT_DRAWN = {"running": "still running", "error": "failed",
              "failed": "failed", "stopped": "stopped",
              "interrupted": "interrupted"}


def _stored_spec(rid) -> str:
    """The spec a run kept in its own results.json (JSON text, its
    forecast date taken from the file's when the spec has none); '' when
    there is none to read. Storage's "Clear N rows not running (files
    kept)" drops a run's ledger row and keeps its workroot, whose fans the
    card still draws."""
    from app.core import runs as _runs
    from app.ui.shared import _spec_dict
    if not _runs.is_run_id(rid):
        return ""
    try:
        res = json.loads((Path(_runs.APP_STATE) / "workroots" / rid
                          / "results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(res, dict):
        return ""
    spec = dict(_spec_dict(res.get("spec")))
    if not spec.get("forecast_date") and res.get("forecast_date"):
        spec["forecast_date"] = str(res["forecast_date"])
    return json.dumps(spec) if spec else ""


def fan_run(ledger_rows: list, rid) -> dict | None:
    """The run the Forecasts card draws: {"run_id", "label", "name",
    "modified", "earlier"}. label: its one-line name (shared._run_label);
    name: its parts (shared._run_name, the card's tips.runname), read
    from the run's own results.json when the ledger has no row for it.
    modified: it ran with modified model settings (the card
    badges it). earlier: "" when it is the newest hub row of the ledger,
    else the badge's words, saying why the newest is not drawn (it failed,
    stopped or is still running, is a research run, Storage deleted its
    files, or it left no forecasts)."""
    if not rid:
        return None
    from app.core import runs as _runs
    from app.ui.shared import _run_label, _run_name
    spec, outcome = "", None
    for r in ledger_rows or []:
        if r.get("run_id") == rid:
            spec, outcome = r.get("spec") or "", r.get("outcome")
            break
    else:
        try:
            row = _runs.Ledger().row(rid)
        except Exception:
            row = None
        spec = (row or {}).get("spec") or ""
        outcome = (row or {}).get("outcome")
    if not spec:
        spec = _stored_spec(rid)
    top = (ledger_rows or [None])[0] if ledger_rows else None
    earlier = ""
    if top and top.get("run_id") != rid:
        why = (_NOT_DRAWN.get(top.get("status") or "")
               or ("is research" if _runs.is_research(top.get("spec") or "")
                   else "has its files deleted" if top.get("files_deleted")
                   else "has no forecasts"))
        earlier = f"earlier run · newest {why}"
    return {"run_id": rid,
            "label": _run_label(rid, spec, tag=False, outcome=outcome),
            "name": _run_name(rid, spec, outcome),
            "modified": _runs.is_modified(spec), "earlier": earlier}


# === The Forecasts card's chart: the 95% range, the axis, the order ===
#: the levels of the 95% range. results.json keeps 0.1 to 0.9 only, so the
#: chart reads these two from the run's own files (wide_levels)
WIDE = ("0.025", "0.975")
#: the hub chart's y axis
HUB_VALUE_LABEL = "Weekly flu hospital admissions"
#: a dataset's y axis when neither its run nor its file names the value
DATASET_VALUE_LABEL = "Weekly value"
#: value-column names that say nothing about what is counted
_GENERIC_VALUE = ("value", "values", "observation", "observations", "y")


def _grid_levels(workroot) -> dict:
    """A hub run's 95% ranges from its weekly report's bundle: the "All
    locations" grid (report_grid, bundle version 8) keeps each model's own
    forecast at 2.5% and 97.5%, the same forecast results.json keeps at
    10% to 90% (before the upper-tail cap; the submitted file is after
    it). National keyed "US"; {} without a grid."""
    from app.core import report_grid, report_v2
    try:
        bundle = json.loads((Path(workroot) / report_v2.BUNDLE_NAME)
                            .read_text(encoding="utf-8"))
        lo = report_grid.LEVELS.index(float(WIDE[0]))
        hi = report_grid.LEVELS.index(float(WIDE[1]))
    except (OSError, ValueError):
        return {}
    grid = bundle.get("grid") if isinstance(bundle, dict) else None
    panels = grid.get("panels") if isinstance(grid, dict) else None
    out: dict = {}
    for p in panels if isinstance(panels, list) else []:
        if not isinstance(p, dict):
            continue
        name = "US" if p.get("key") == "US" else p.get("name")
        for m, f in (p.get("models") or {}).items():
            if not isinstance(f, dict):
                continue
            for t, row in zip(f.get("times") or [], f.get("q") or []):
                try:
                    out.setdefault(m, {}).setdefault(name, {})[str(t)[:10]] = {
                        WIDE[0]: float(row[lo]), WIDE[1]: float(row[hi])}
                except (TypeError, ValueError, IndexError):
                    continue
    return out


def _export_levels(workroot, ds) -> dict:
    """A dataset run's 95% ranges from its export files (custom_run:
    export/<export id>[-suffix]/*.csv, all 23 levels, keyed by the
    dataset's own unit column), group names through the dataset's source
    keys. {} without the files."""
    import csv
    from app.core import custom_run as CR
    root = Path(workroot) / CR.EXPORT_DIR
    if not root.is_dir():
        return {}
    try:
        back = {str(k): n for n, k in CR.source_keys(ds).items()}
        col = CR.key_col(ds)
    except Exception:
        back, col = {}, ""
    out: dict = {}
    for m, mid in CR.EXPORT_IDS.items():
        files = sorted(f for d in root.iterdir() if d.is_dir()
                       and (d.name == mid or d.name.startswith(mid + "-"))
                       for f in d.glob("*.csv"))
        if not files:
            continue
        try:
            with open(files[-1], newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r.get("output_type") != "quantile":
                        continue
                    lv = f"{float(r['output_type_id']):g}"
                    if lv not in WIDE:
                        continue
                    key = str(r.get(col) or r.get("target_group")
                              or r.get("location") or "")
                    out.setdefault(m, {}).setdefault(
                        back.get(key, key), {}).setdefault(
                        str(r["target_end_date"])[:10], {})[lv] = float(
                            r["value"])
        except (OSError, KeyError, ValueError):
            continue
    return out


def wide_levels(workroot, ds=None) -> dict:
    """model -> location -> target date -> {"0.025", "0.975"}: a run's
    95% ranges from its own files, the weekly report's bundle for a hub
    run, the export files for a dataset run (`ds` given). {} for none."""
    if not workroot:
        return {}
    try:
        return (_export_levels(workroot, ds) if ds is not None
                else _grid_levels(workroot))
    except Exception:
        return {}


def widen_fans(fanq: dict, wide: dict, fc_date: str) -> dict:
    """The fans with each stored horizon h's 95% range from `wide`, matched
    by its target date (the as-of + 7h, where the chart draws it), kept
    outside the 80% range (the bundle's whole numbers could cross it). A
    horizon without both levels keeps its five."""
    from app.core import us_national
    try:
        base = date.fromisoformat(str(fc_date)[:10])
    except ValueError:
        return fanq
    out = {}
    for m, by_loc in (fanq or {}).items():
        wm = (wide or {}).get(m) or {}
        out[m] = {}
        for loc, hs in by_loc.items():
            wl = wm.get(loc) or (wm.get("US") if us_national.is_us(loc)
                                 else None) or {}
            row = {}
            for h, q in hs.items():
                try:
                    t = (base + timedelta(days=7 * int(h))).isoformat()
                except (TypeError, ValueError):
                    row[h] = q
                    continue
                w = wl.get(t) or {}
                if isinstance(q, dict) and all(k in w for k in WIDE):
                    q = dict(q)
                    q[WIDE[0]] = min(w[WIDE[0]], q.get("0.1", w[WIDE[0]]))
                    q[WIDE[1]] = max(w[WIDE[1]], q.get("0.9", w[WIDE[1]]))
                row[h] = q
            out[m][loc] = row
    return out


def fan_first(locations, national: str = "") -> str:
    """The location the chart's list starts with: a dataset's national
    group when it names one, else the national series among `locations`;
    "" when there is none."""
    from app.core import us_national
    locs = list(locations or [])
    if national:
        return national if national in locs else ""
    return next((l for l in locs if us_national.is_us(l)), "")


def fan_chart(fanq: dict, *, label: str, kind: str = "count",
              national: str = "", first_label: str = "",
              dataset: str = "") -> dict:
    """What the Forecasts card's script reads beside the fans (FANC): the
    y axis's words, whether values are counts (whole numbers in the hover)
    or rates, the location listed first and its name there, the models'
    drawing order (the weekly report's: the first drawn sits under the
    others) and the dataset's name for a saved figure ("" on the hub)."""
    from app.core import report_grid
    locs = [l for qs in (fanq or {}).values() for l in qs]
    first = fan_first(locs, national)
    return {"label": label, "kind": "rate" if kind == "rate" else "count",
            "first": first, "first_label": (first_label or first) if first
            else "", "order": list(report_grid.MODELS), "dataset": dataset}


def dataset_value_label(ds, res=None) -> str:
    """A dataset chart's y axis: the target the run recorded (a hub-style
    file's target column), else the dataset's value column when its name
    says what is counted, else DATASET_VALUE_LABEL."""
    tgt = str(((res or {}).get("dataset") or {}).get("target") or "")
    if tgt and tgt != "custom":
        return tgt
    try:
        col = str((ds.meta.get("columns") or {}).get("value") or "")
    except Exception:
        col = ""
    name = re.sub(r"[_\s]+", " ", col).strip()
    if name and name.lower() not in _GENERIC_VALUE:
        return f"Weekly {name}"
    return DATASET_VALUE_LABEL


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
    the panel's raw value}} for the knobs that applied to it, and for a run
    with modified settings "hub_names", whether its files took the hub
    names by override (the box starts unticked each run); None without a
    run or a readable spec. The season start is left out (it follows the
    date)."""
    row = (ledger_rows or [None])[0] if ledger_rows else None
    spec = _spec(row)
    if not spec:
        return None
    from app.core import knobs as K
    from app.core import us_national as _usn
    locs = list(spec.get("locations") or [])
    # a state left out in Data issues was still picked: the form's pick is
    # the run's before the box's choices
    dc = (spec.get("extra") or {}).get("data_choices") or {}
    locs += [l for l, st in (dc.get("states") or {}).items()
             if isinstance(st, dict) and st.get("choice") == "omit"
             and l not in locs]
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
    out = {"engine": str(spec.get("engine") or "all"),
           "locations": (["all"] if (len(states) >= 52 and us)
                         else sorted(states) + (["US"] if us else [])),
           "knobs": kn}
    if K.modified(spec):
        out["hub_names"] = K.hub_names(spec)
    return out


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
