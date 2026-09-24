"""PRODUCTION: a FluSight submission file checked the way the hub checks it
(submit.write_submission's gate, the Output page, app/tests/test_hubcheck.py).

The hub validates every pull request with the hubValidations R package,
which reads hub-config/tasks.json. R is not part of this app, so the checks
that matter for a file are reproduced here from the same tasks.json, one
function per hubValidations check (the name in brackets):

  file_name          <reference_date>-<team>-<model>.csv, both abbreviations
                     ^[A-Za-z0-9_+]+$ and at most 16 characters
                     [check_valid_filename, model-metadata-schema.json]
  file_location      the file sits in a directory named <team>-<model>
                     [check_file_location]
  round_id_valid     the file's date is one of tasks.json's reference dates
                     [check_valid_round_id]
  colnames           exactly the eight columns, any order [check_tbl_colnames]
  col_types          horizon an integer, dates ISO, value a number
                     [check_tbl_col_types]
  match_round_id     every reference_date equals the file's date
                     [check_tbl_match_round_id, check_tbl_unique_round_id]
  values_valid       every row is a task tasks.json defines: target, horizon,
                     location, target_end_date, output type and output type
                     id, written as the config writes them ("01", "0.025")
                     [check_tbl_values]
  rows_unique        no repeated task + output type id [check_tbl_rows_unique]
  values_required    a task that carries an output type carries all of its
                     required ids (the 23 quantile levels)
                     [check_tbl_values_required]
  value_col_valid    no NA, within tasks.json's minimum/maximum, integers
                     where the type is integer [check_tbl_value_col]
  value_integer      FluSight 2026-27: 'wk inc flu hosp' and 'peak inc flu
                     hosp' values are whole numbers (model-output/README.md)
  ascending          quantile values non-decreasing with the level
                     [check_tbl_value_col_ascending]
  sum1               pmf values sum to 1 per task, to R's all.equal
                     tolerance (1.5e-8) [check_tbl_value_col_sum1]
  horizon_timediff   target_end_date = reference_date + 7 * horizon, so a
                     horizon -1 row ends the week before the reference
                     date (validations.yml: opt_check_tbl_horizon_timediff)
  counts_lt_popn     'wk inc flu hosp' below the jurisdiction's population
                     (validations.yml: opt_check_tbl_counts_lt_popn)
  plausible          the README's plausibility bounds: admissions at most 30
                     percent of the population, ED proportion at most 0.25
  samples            100 samples per compound task, ids at most 15 characters

`round_id_valid` is the one check a correct file can fail: a replay of a
summer week has a reference date outside the season. Everything else is a
defect in the file.

The rules come from app/core/assets/flusight-tasks.json, a byte copy of the
hub's hub-config/tasks.json (the suite compares it with a hub clone
whenever one is present), so the check needs no clone at run time.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

#: byte copy of cdcepi/FluSight-forecast-hub hub-config/tasks.json
VENDORED_TASKS = Path(__file__).parent / "assets" / "flusight-tasks.json"

COLUMNS = ("reference_date", "target", "horizon", "target_end_date",
           "location", "output_type", "output_type_id", "value")
TASK_IDS = ("reference_date", "target", "horizon", "location",
            "target_end_date")

#: FluSight 2026-27 (model-output/README.md "value"): whole numbers required
INTEGER_TARGETS = ("wk inc flu hosp", "peak inc flu hosp")
#: README "Forecast validation": plausibility bounds
PLAUSIBLE_POPN_SHARE = {"wk inc flu hosp": 0.30, "peak inc flu hosp": 0.30}
PLAUSIBLE_MAX = {"wk inc flu prop ed visits": 0.25}

#: the check a correct file can fail (an off-season reference date)
ROUND_CHECK = "round_id_valid"

#: a pmf task's values must sum to 1 within this: hubValidations compares
#: the sum with all.equal(), whose default tolerance this is
PMF_SUM_TOL = 1.5e-8

_ABBR = re.compile(r"^[A-Za-z0-9_+]{1,16}$")
_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([^-]+)-([^-]+)\.(csv|parquet)$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT = re.compile(r"^-?\d+$")
_NA = ("", "NA")
#: task ids whose allowed values are the season's calendar
_ROUND_DATES = ("reference_date", "target_end_date")


def _txt(v) -> str:
    """A tasks.json value as R's as.character writes it: 0.025 -> '0.025',
    1 -> '1' (what hubValidations compares a CSV cell against)."""
    if isinstance(v, bool):
        return str(v).upper()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def load_tasks(path=None) -> dict:
    """tasks.json as a dict: `path`, else the vendored copy."""
    return json.loads(Path(path or VENDORED_TASKS).read_text())


def rules_from_tasks(tasks: dict) -> dict:
    """The facts the checks use, from one tasks.json:

    {"rounds": sorted reference dates, "window": (start, end) days relative
     to the reference date, "tasks": [{"target", task id -> allowed texts
     (None = must be NA), "output_types": {name: {"ids", "required_ids",
     "is_required", "type", "minimum", "maximum", "samples"}}}]}"""
    rounds, tasks_out, window = set(), [], None
    for rnd in tasks["rounds"]:
        sd = rnd.get("submissions_due") or {}
        if "start" in sd:
            window = (int(sd["start"]), int(sd["end"]))
        for mt in rnd["model_tasks"]:
            ids = {}
            for k, spec in mt["task_ids"].items():
                req, opt = spec.get("required"), spec.get("optional")
                if req is None and opt is None:
                    ids[k] = None
                else:
                    ids[k] = sorted({_txt(v) for v in (req or []) + (opt or [])})
            rounds.update(ids.get("reference_date") or [])
            ots = {}
            for name, ot in mt["output_type"].items():
                oid = ot.get("output_type_id") or {}
                req = [_txt(v) for v in (oid.get("required") or [])]
                opt = [_txt(v) for v in (oid.get("optional") or [])]
                val = ot.get("value") or {}
                params = ot.get("output_type_id_params")
                ots[name] = {
                    "ids": None if params else req + opt,
                    "required_ids": req,
                    "is_required": bool(ot.get("is_required")),
                    "type": val.get("type"),
                    "minimum": val.get("minimum"),
                    "maximum": val.get("maximum"),
                    "samples": params,
                }
            (target,) = ids["target"]
            tasks_out.append({"target": target, "task_ids": ids,
                              "output_types": ots})
    return {"rounds": sorted(rounds), "window": window, "tasks": tasks_out}


_RULES_CACHE: dict = {}


def vendored_rules() -> dict:
    """rules_from_tasks of the vendored tasks.json, parsed once."""
    if "v" not in _RULES_CACHE:
        _RULES_CACHE["v"] = rules_from_tasks(load_tasks())
    return _RULES_CACHE["v"]


def _populations() -> dict:
    from flubnf.settings import load_locations
    locs = load_locations()
    return {str(l): float(p) for l, p in zip(locs.location, locs.population)}


def submission_window(reference_date: str, rules: dict | None = None) -> tuple:
    """(first day, last day) a file for `reference_date` is accepted, from
    tasks.json's submissions_due (FluSight: the Sunday through the
    Wednesday before the reference date; the hub closes at 11 PM ET)."""
    start, end = (rules or vendored_rules())["window"] or (-6, -3)
    ref = _dt.date.fromisoformat(str(reference_date)[:10])
    return (ref + _dt.timedelta(days=start), ref + _dt.timedelta(days=end))


def check_frame(df: pd.DataFrame, file_name: str | None = None,
                dir_name: str | None = None, rules: dict | None = None,
                populations: dict | None = None) -> dict:
    """Every check on one submission, as {check: [problems]} (an empty list
    is a pass). `df` holds the file's cells as TEXT (read with dtype=str,
    keep_default_na=False), so '01' and '0.025' are checked as written."""
    rules = rules or vendored_rules()
    out = {k: [] for k in (
        "file_name", "file_location", ROUND_CHECK, "colnames", "col_types",
        "match_round_id", "values_valid", "rows_unique", "values_required",
        "value_col_valid", "value_integer", "ascending", "sum1",
        "horizon_timediff", "counts_lt_popn", "plausible", "samples")}
    file_date = None
    if file_name is not None:
        m = _FILE.match(file_name)
        if not m:
            out["file_name"].append(
                f"{file_name!r} is not <YYYY-MM-DD>-<team>-<model>.csv")
        else:
            file_date, team, model = m.group(1), m.group(2), m.group(3)
            for what, v in (("team", team), ("model", model)):
                if not _ABBR.match(v):
                    out["file_name"].append(
                        f"{what} abbreviation {v!r}: letters, digits, _ or +,"
                        " at most 16 characters")
            if dir_name is not None and dir_name != f"{team}-{model}":
                out["file_location"].append(
                    f"file for {team}-{model} sits in {dir_name!r}")
            if file_date not in rules["rounds"]:
                out[ROUND_CHECK].append(
                    f"reference date {file_date} is not a FluSight round "
                    f"({rules['rounds'][0]} to {rules['rounds'][-1]}, "
                    "season weeks only)")
    cols = list(df.columns)
    missing = [c for c in COLUMNS if c not in cols]
    extra = [c for c in cols if c not in COLUMNS]
    if missing or extra:
        out["colnames"].append(
            "; ".join(b for b in (
                missing and f"missing {', '.join(missing)}",
                extra and f"not allowed {', '.join(map(str, extra))}") if b))
        return out
    if df.empty:
        out["values_valid"].append("the file has no rows")
        return out
    d = df[list(COLUMNS)].astype(str).apply(lambda s: s.str.strip()).astype(object)

    # --- round id
    refs = sorted(set(d.reference_date))
    if len(refs) != 1:
        out["match_round_id"].append(
            f"{len(refs)} reference dates in one file: {', '.join(refs[:4])}")
    elif file_date is not None and refs[0] != file_date:
        out["match_round_id"].append(
            f"rows carry {refs[0]}, the file name {file_date}")
    for r in refs:
        # every FluSight reference date is a Saturday (the epiweek's end)
        try:
            if _DATE.match(r) and _dt.date.fromisoformat(r).weekday() != 5:
                out["match_round_id"].append(
                    f"reference date {r} is not a Saturday")
        except ValueError:
            pass

    # --- column types
    for c in ("reference_date",):
        bad = sorted({v for v in d[c] if not _DATE.match(v)})
        if bad:
            out["col_types"].append(f"{c} not ISO dates: {bad[:3]}")
    bad = sorted({v for v in d.target_end_date
                  if v not in _NA and not _DATE.match(v)})
    if bad:
        out["col_types"].append(f"target_end_date not ISO dates: {bad[:3]}")
    bad = sorted({v for v in d.horizon if v not in _NA and not _INT.match(v)})
    if bad:
        out["col_types"].append(f"horizon not integers: {bad[:3]}")
    val = pd.to_numeric(d.value.where(~d.value.isin(_NA)), errors="coerce")
    nonnum = d.value[val.isna() & ~d.value.isin(_NA)]
    if len(nonnum):
        out["col_types"].append(
            f"value not numeric: {sorted(set(nonnum))[:3]}")

    # --- every row a defined task
    by_target = {}
    for t in rules["tasks"]:
        by_target.setdefault(t["target"], []).append(t)
    row_task = [None] * len(d)
    bad_rows: dict = {}

    def _note(key, msg):
        bad_rows.setdefault(key, msg)
    for i, r in enumerate(d.itertuples(index=False)):
        cands = by_target.get(r.target)
        if not cands:
            _note(("target", r.target), f"unknown target {r.target!r}")
            continue
        hit, why = None, ""
        for t in cands:
            ot = t["output_types"].get(r.output_type)
            if ot is None:
                why = (f"output_type {r.output_type!r} is not offered for "
                       f"{r.target!r}")
                continue
            ok = True
            for k in TASK_IDS:
                allowed = t["task_ids"].get(k)
                v = getattr(r, k)
                if allowed is None:
                    if v not in _NA:
                        ok, why = False, f"{k} must be NA for {r.target!r}"
                        break
                elif v not in allowed:
                    if k in _ROUND_DATES and _DATE.match(v):
                        # an off-season week: the round check's finding,
                        # not a malformed row
                        _add_once(out[ROUND_CHECK],
                                  f"{k} {v} is outside the hub's season "
                                  "weeks", cap=4)
                        continue
                    ok, why = False, (f"{k} {v!r} is not allowed for "
                                      f"{r.target!r}")
                    break
            if not ok:
                continue
            if ot["ids"] is not None and r.output_type_id not in ot["ids"]:
                why = (f"output_type_id {r.output_type_id!r} is not a "
                       f"{r.output_type} id for {r.target!r}")
                continue
            if ot["samples"] and (not r.output_type_id or len(
                    r.output_type_id) > int(ot["samples"].get("max_length", 15))):
                why = f"sample id {r.output_type_id!r} too long or empty"
                continue
            hit = (t, ot)
            break
        if hit is None:
            _note(why, why)
        row_task[i] = hit
    out["values_valid"].extend(list(bad_rows.values())[:12])

    # --- uniqueness
    key = list(TASK_IDS) + ["output_type", "output_type_id"]
    dup = d.duplicated(subset=key, keep=False)
    if dup.any():
        out["rows_unique"].append(f"{int(dup.sum())} rows repeat a task and "
                                  "output_type_id")

    # --- values
    na = d.value.isin(_NA)
    if na.any():
        out["value_col_valid"].append(f"{int(na.sum())} rows have no value")
    vals, raws, otypes = val.to_numpy(float), list(d.value), list(d.output_type)
    for i, hit in enumerate(row_task):
        if hit is None or not np.isfinite(vals[i]):
            continue
        t, ot = hit
        v = float(vals[i])
        if ot["minimum"] is not None and v < float(ot["minimum"]):
            _add_once(out["value_col_valid"],
                      f"{t['target']} {otypes[i]}: value {v:g} below "
                      f"the minimum {ot['minimum']}")
        if ot["maximum"] is not None and v > float(ot["maximum"]):
            _add_once(out["value_col_valid"],
                      f"{t['target']} {otypes[i]}: value {v:g} above "
                      f"the maximum {ot['maximum']}")
        if ot["type"] == "integer" and not float(v).is_integer():
            _add_once(out["value_col_valid"],
                      f"{t['target']} {otypes[i]}: integer required, "
                      f"got {raws[i]}")
        if (t["target"] in INTEGER_TARGETS and otypes[i] == "quantile"
                and not float(v).is_integer()):
            _add_once(out["value_integer"],
                      f"{t['target']}: whole numbers required (2026-27), "
                      f"got {raws[i]}")

    # --- per task: required ids, ascending, sum to one, samples
    d = d.assign(vnum=val.to_numpy())
    grp_cols = list(TASK_IDS) + ["output_type"]
    lookup = {id(h[1]): h for h in row_task if h is not None}
    d = d.assign(otkey=[id(h[1]) if h else None for h in row_task])
    for keyv, g in d[d.otkey.notna()].groupby(grp_cols + ["otkey"], sort=False):
        t, ot = lookup[keyv[-1]]
        label = (f"{keyv[3]} {keyv[1]} h={keyv[2]}" if keyv[2] not in _NA
                 else f"{keyv[3]} {keyv[1]}")
        have = set(g.output_type_id)
        miss = [x for x in ot["required_ids"] if x not in have]
        if miss and ot["samples"] is None:
            _add_once(out["values_required"],
                      f"{label} {keyv[5]}: {len(miss)} required id(s) "
                      f"missing ({', '.join(miss[:4])}"
                      + (", ..." if len(miss) > 4 else "") + ")")
        if keyv[5] == "quantile":
            lv = pd.to_numeric(g.output_type_id, errors="coerce").to_numpy()
            v = g.vnum.to_numpy(float)[np.argsort(lv, kind="stable")]
            if np.isfinite(v).all() and (np.diff(v) < -1e-9).any():
                _add_once(out["ascending"],
                          f"{label}: quantile values decrease with the level")
        if keyv[5] == "pmf":
            s = float(np.nansum(g.vnum.to_numpy(float)))
            if abs(s - 1.0) > PMF_SUM_TOL:
                _add_once(out["sum1"], f"{label}: pmf sums to {s:.10g}")
    for t in rules["tasks"]:
        for name, ot in t["output_types"].items():
            p = ot["samples"]
            if not p:
                continue
            s = d[(d.target == t["target"]) & (d.output_type == name)]
            for k, g in s.groupby(list(p.get("compound_taskid_set") or
                                       ("reference_date", "location",
                                        "target"))):
                n = g.output_type_id.nunique()
                lo, hi = p.get("min_samples_per_task"), p.get(
                    "max_samples_per_task")
                if (lo and n < lo) or (hi and n > hi):
                    _add_once(out["samples"],
                              f"{' '.join(map(str, k))}: {n} samples, "
                              f"want {lo} to {hi}")

    # --- dates and population
    for r in d.itertuples(index=False):
        if r.horizon in _NA or r.target_end_date in _NA:
            continue
        try:
            want = (_dt.date.fromisoformat(r.reference_date)
                    + _dt.timedelta(weeks=int(r.horizon))).isoformat()
        except ValueError:
            continue
        if r.target_end_date != want:
            _add_once(out["horizon_timediff"],
                      f"{r.location} h={r.horizon}: target_end_date "
                      f"{r.target_end_date}, want {want}")
    pops = populations if populations is not None else _safe_populations()
    if pops:
        for r in d.itertuples(index=False):
            if not np.isfinite(r.vnum):
                continue
            pop = pops.get(r.location)
            if r.target == "wk inc flu hosp" and pop and r.vnum >= pop:
                _add_once(out["counts_lt_popn"],
                          f"{r.location}: {r.vnum:g} admissions, population "
                          f"{pop:.0f}")
            share = PLAUSIBLE_POPN_SHARE.get(r.target)
            if (share and pop and r.output_type == "quantile"
                    and r.vnum > share * pop):
                _add_once(out["plausible"],
                          f"{r.location} {r.target}: {r.vnum:g} is above "
                          f"{share:.0%} of the population")
            cap = PLAUSIBLE_MAX.get(r.target)
            if cap is not None and r.vnum > cap:
                _add_once(out["plausible"],
                          f"{r.location} {r.target}: {r.vnum:g} above {cap}")
    return out


def _add_once(bucket: list, msg: str, cap: int = 12) -> None:
    if msg not in bucket and len(bucket) < cap:
        bucket.append(msg)


def _safe_populations() -> dict:
    try:
        return _populations()
    except Exception:
        return {}


def read_text_frame(path) -> pd.DataFrame:
    """A submission CSV with every cell as written (no NA or number
    guessing), the way the checks want it."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def check_file(path, rules: dict | None = None,
               populations: dict | None = None) -> dict:
    """check_frame for a file on disk, with its name and directory."""
    p = Path(path)
    return check_frame(read_text_frame(p), p.name, p.parent.name,
                       rules=rules, populations=populations)


def failures(result: dict, allow_round: bool = True) -> list:
    """Flat "check: problem" lines; the round check is left out when
    `allow_round` (a correct file for an off-season week)."""
    return [f"{k}: {m}" for k, ms in result.items() for m in ms
            if not (allow_round and k == ROUND_CHECK)]


def summary(path) -> dict:
    """One file's status for a page: {"ok": no defect, "round": is a hub
    round, "problems": [...], "due": (first, last) or None}. Never raises."""
    try:
        res = check_file(path)
    except Exception as e:
        return {"ok": False, "round": False, "due": None,
                "problems": [f"unreadable: {type(e).__name__}"]}
    probs = failures(res)
    m = _FILE.match(Path(path).name)
    ref = m.group(1) if m else ""
    is_round = not res[ROUND_CHECK] and bool(ref)
    return {"ok": not probs, "round": is_round, "problems": probs,
            "reference_date": ref,
            "due": submission_window(ref) if is_round else None}
