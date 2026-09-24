"""PRODUCTION: hub submission CSVs and their validation
(app/ui/pipeline._run_all, oracle provenance).

FluSight submission formatting + validation.

Hub facts (model-metadata/README.md):
  * model identity lives in the PATH (model-output/<team>-<model>/), never in
    a CSV column: one file per model_id per reference date;
  * a team may designate up to two models for the ensemble;
  * quantile targets: 'wk inc flu hosp' at 23 quantiles; the hub takes
    horizons -1..3 and this app writes 0..3 (-1, the week already reported,
    is optional and never scored: the output.horizon_minus1 knob adds it);
  * the optional 'wk flu hosp rate change' target (pmf over five
    categories, horizons 0..3; app.core.categorical) is added by the
    output.rate_change_pmf knob; both are off by default, and a default
    file is byte for byte the file written without them;
  * value precision: whole admissions, which FluSight requires from 2026-27
    (model-output/README.md; _hub_values);
  * every file is checked the way the hub checks it before it takes its
    name (app/core/hubcheck.py, the vendored tasks.json).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

#: optional hub outputs, off by default (the knobs output.horizon_minus1
#: and output.rate_change_pmf read their defaults here)
HORIZON_MINUS1 = False
RATE_CHANGE_PMF = False

#: the 'wk inc flu hosp' horizons written by default; -1 (the as-of week,
#: reference_date - 7) is added only by output.horizon_minus1
HORIZONS = (0, 1, 2, 3)
HORIZONS_WITH_MINUS1 = (-1, 0, 1, 2, 3)

#: the rate-trend target: its horizons are 0..3 (model-output/README.md
#: "horizon"; tasks.json also lists -1, a change from the baseline week to
#: itself, which the hub's scoring code never computes)
RATE_CHANGE_TARGET = "wk flu hosp rate change"
RATE_CHANGE_HORIZONS = (0, 1, 2, 3)
#: pmf values are written to this many decimals, summing to exactly 1
PMF_DECIMALS = 4

QUANTILES = (0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45,
             0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99)

#: Hub identity (model-metadata/<TEAM>-<abbr>.yml): directory, file and
#: metadata names are all built from these. A constant because
#: model-metadata/ is not packaged; app/tests/test_submit_join.py holds it
#: equal to the YAML. NAU_PyBNF is a new registration (2026-09-22) for the
#: two standalone models; the old LosAlamos_NAU cards stay on the hub.
TEAM_ABBR = "NAU_PyBNF"

#: internal member key -> hub model_abbr; two standalone, designated
#: submissions, nothing blended
MODEL_ABBR = {"pf": "OracleSIHRS", "analogue": "GroundHogCGR"}

#: identities no longer produced; empty (the retired cards belong to the old
#: LosAlamos_NAU registration)
RETIRED_ABBR = ()

#: model-output directory names earlier versions of this app wrote, under
#: registrations since retired, -> the member that wrote them ("pf",
#: "analogue") or "blend" (the retired blend, which has no successor).
#: Read only, to present old run folders; nothing writes these names.
LEGACY_DIRS = {
    "NAU-PF-SIHRS": "pf", "NAU_FluBNF-SIHRS": "pf",
    "LosAlamos_NAU-SIHRS": "pf",
    "LosAlamos_NAU-GroundhogCGR": "analogue",
    "NAU-Ensemble": "blend", "NAU_FluBNF-ensemble": "blend",
    "LosAlamos_NAU-CModel_Flu": "blend",
}


def hub_model_id(model: str) -> str:
    """`<team_abbr>-<model_abbr>`: the hub's model identity, which is also
    the model-output directory name and the tail of every file name in it."""
    try:
        return f"{TEAM_ABBR}-{MODEL_ABBR[model]}"
    except KeyError:
        raise ValueError(
            f"unregistered model {model!r}: hub identity comes from "
            f"model-metadata/, and the registered keys are "
            f"{sorted(MODEL_ABBR)}") from None


def hub_reference_date(asof) -> pd.Timestamp:
    """THE FROZEN JOIN: hub reference_date = our as-of Saturday + 7 days.

    Every producer (row builders and the file name) calls this, so the two
    cannot disagree; the hub rejects a file whose name and `reference_date`
    differ."""
    return pd.Timestamp(asof) + pd.Timedelta(days=7)


def _hub_values(vals) -> list:
    """Whole admissions (the officials' precision since 2025), re-made
    monotone after rounding (a hub rule, not assumed); Python ints so the
    CSV writes '14', never '14.0'."""
    v = np.rint(np.asarray(vals, float))
    v = np.maximum.accumulate(v)
    return [int(x) for x in v]


def _key(h: int) -> str:
    """The canonical in-memory key of hub horizon h: "0".."3", and the
    anchor block (horizons.ORIGIN, the as-of week) for -1."""
    from app.core.horizons import ORIGIN
    return ORIGIN if int(h) == -1 else str(int(h))


def quantile_rows(samples: dict, location_fips: str, asof: str,
                  horizons=HORIZONS) -> list:
    """FluSight rows for one location from horizon->samples arrays.

    Hub horizon 0..3 carries our canonical "0".."3"; the anchor under
    ORIGIN (the as-of week) is submitted only as horizon -1, when
    `horizons` includes it (output.horizon_minus1). Callers pass the AS-OF
    date; the reference comes from hub_reference_date."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in horizons:
        s = np.asarray(samples.get(_key(h), []), float)
        s = s[np.isfinite(s)]
        if not s.size:
            continue
        target_end = ref + pd.Timedelta(weeks=h)
        values = _hub_values(np.quantile(s, QUANTILES))
        for q, v in zip(QUANTILES, values):
            rows.append({
                "reference_date": reference_date,
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": str(target_end.date()),
                "location": location_fips,
                "output_type": "quantile",
                "output_type_id": q,
                "value": v,
            })
    return rows


def _level_report(levels: list) -> str:
    """How a quantile set differs from the hub's 23, in words."""
    have, want = set(levels), set(QUANTILES)
    bits = []
    missing = [q for q in QUANTILES if q not in have]
    if missing:
        shown = ", ".join(str(q) for q in missing[:6])
        bits.append(f"{len(missing)} missing ({shown}"
                    + (", ..." if len(missing) > 6 else "") + ")")
    extra = sorted(x for x in have if x not in want)
    if extra:
        bits.append("not hub levels: "
                    + ", ".join(str(x) for x in extra[:6]))
    if len(levels) != len(have):
        bits.append("levels repeated")
    return "; ".join(bits) or "levels out of order"


def validate(df: pd.DataFrame, key_col: str = "location") -> list:
    """Gate before anything leaves the machine. Returns list of defects.

    Enforces all 23 levels per (location, horizon) (hub tasks.json requires
    them; rows_from_quantiles emits only what it is given), monotone,
    non-negative, and not zero-width (such cells once carried 49% of WIS).
    Horizons are optional in the hub schema, so a missing one is fine.
    `key_col` names the unit column: 'location' for the hub, or a custom
    dataset's own ('target_group' for a grouped-CSV export).
    """
    file_level, by_unit = validate_split(df, key_col)
    return file_level + [m for ms in by_unit.values() for m in ms]


def validate_split(df: pd.DataFrame, key_col: str = "location") -> tuple:
    """validate's defects split by where they sit: (file-level defects,
    {unit: [defects confined to that unit's rows]}), both in validate's
    order and words."""
    if df.empty:
        return ["submission is empty"], {}
    q = df[df.output_type == "quantile"].copy()
    if q.empty:
        return ["submission carries no quantile rows"], {}
    try:
        # numeric levels: a string column would sort lexicographically
        q["_level"] = [round(float(x), 4) for x in q.output_type_id]
    except (TypeError, ValueError):
        return ["quantile rows carry a non-numeric output_type_id"], {}
    by_unit: dict = {}
    for (loc, h), g in q.groupby([key_col, "horizon"]):
        problems = by_unit.setdefault(loc, [])
        g = g.sort_values("_level")
        levels = list(g["_level"])
        v = g.value.to_numpy()
        if levels != list(QUANTILES):
            problems.append(f"{loc} h={h}: incomplete quantile set, "
                            f"{len(levels)} of {len(QUANTILES)} levels "
                            f"({_level_report(levels)})")
        if (np.diff(v) < 0).any():
            problems.append(f"{loc} h={h}: quantiles not monotone")
        if (v < 0).any():
            problems.append(f"{loc} h={h}: negative quantile value")
        if v[0] == v[-1] and v[0] > 0:
            problems.append(f"{loc} h={h}: degenerate (zero-width) distribution")
    return [], {k: v for k, v in by_unit.items() if v}


def _reason(problems: list, strip: str = "") -> str:
    """One location's defects as a short reason for the run record."""
    out = []
    for m in problems[:3]:
        m = str(m)
        if strip and m.startswith(strip + " "):
            m = m[len(strip) + 1:]
        out.append(m)
    more = len(problems) - len(out)
    return "; ".join(out) + (f"; and {more} more" if more > 0 else "")


def write_submission(all_rows: Iterable[dict], model: str, asof: str,
                     out_dir: Path, suffix: str = "",
                     dropped: dict | None = None) -> Path:
    """One hub-format CSV per model (identity is the PATH, rule above).

    `model` is a MODEL_ABBR key (never a free-text name); `asof` is the
    as-of the rows were built from. A name/`reference_date` mismatch is
    fatal here, before the hub rejects it. `suffix` (knobs.MODIFIED_SUFFIX
    for a run with modified model settings) makes the directory and file
    a NON-hub name, so such a file can never pass for the registered
    model.

    Partial files: a defect confined to one location's rows (validate's
    per-location defects, or a hub check that fails on that location's
    rows alone) drops that location; the file is written with the rest
    and checked again. `dropped`, when given, receives location code ->
    reason for each one. A file-level defect (name, folder, columns,
    reference date, mixed dates, a non-Saturday date) or no valid location
    left still refuses the whole file. A file with no defect is written
    exactly as before."""
    df = pd.DataFrame(list(all_rows))
    file_level, by_loc = validate_split(df)
    if file_level or (by_loc and set(by_loc) >= set(df["location"])):
        problems = file_level + [m for ms in by_loc.values() for m in ms]
        raise ValueError("submission failed validation:\n  " +
                         "\n  ".join(problems[:10]))
    if "reference_date" not in df.columns:
        raise ValueError("submission rows carry no reference_date column; "
                         "the file name could not be checked against them")
    model_id = hub_model_id(model) + str(suffix or "")
    ref = str(hub_reference_date(asof).date())
    in_rows = sorted({str(v) for v in df["reference_date"]})
    if in_rows != [ref]:
        raise ValueError(
            "submission file name and reference_date column disagree: the "
            f"file would be named for {ref} (as-of {asof} + 7 days) while "
            f"the rows carry {', '.join(in_rows)}. Both must come from one "
            "as-of; build the rows and write the file with the same value.")
    gone: dict = {}
    if by_loc:
        gone.update({str(loc): _reason(ms, str(loc))
                     for loc, ms in by_loc.items()})
        df = df[~df["location"].isin(list(by_loc))]
    d = Path(out_dir) / model_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ref}-{model_id}.csv"
    # atomic: every CSV here is listed as submittable, so never a truncated one
    tmp = p.with_name(p.name + ".tmp")
    try:
        # LF on every platform (pandas defaults to os.linesep): the hub's
        # files are LF, and a Windows lab machine writes the same bytes
        df.to_csv(tmp, index=False, lineterminator="\n")
        bad_locs = _hub_gate(tmp, p.name, d.name, hub_named=not suffix)
        if bad_locs:
            # drop the locations the hub's checks fault on their own, then
            # write the rest and check the whole file again
            gone.update(bad_locs)
            df = df[~df["location"].astype(str).isin(list(bad_locs))]
            if df.empty:
                raise ValueError(
                    "submission failed the hub's checks "
                    "(app/core/hubcheck.py): no valid location left:\n  "
                    + "\n  ".join(f"{k}: {v}" for k, v in
                                   list(bad_locs.items())[:10]))
            df.to_csv(tmp, index=False, lineterminator="\n")
            _hub_gate(tmp, p.name, d.name, hub_named=not suffix,
                      split=False)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    if dropped is not None:
        dropped.update(gone)
    return p


#: hub checks whose failure is the whole file's (its name, its folder, its
#: columns, its reference date): never cured by dropping a location
FILE_CHECKS = ("file_name", "file_location", "colnames", "match_round_id")


def _hub_gate(tmp: Path, name: str, dir_name: str, hub_named: bool,
              split: bool = True) -> dict:
    """The written bytes, checked the way the hub checks them
    (app/core/hubcheck.py, rules from the vendored tasks.json). A
    file-level defect (FILE_CHECKS) is fatal before the file takes its
    name. An off-season reference date is not a defect (replays of summer
    weeks are records, not submissions); a <hub id>-modified file skips
    the name checks, since its name is deliberately not a hub name.

    Any other defect is traced to the locations whose rows fail on their
    own; with `split` those are returned as {location: reason} for the
    writer to drop. A defect no single location carries is fatal."""
    from app.core import hubcheck
    frame = hubcheck.read_text_frame(tmp)
    res = hubcheck.check_frame(frame, name if hub_named else None,
                               dir_name if hub_named else None)
    bad = hubcheck.failures(res)
    if not bad:
        return {}

    def _refuse(lines):
        raise ValueError("submission failed the hub's checks "
                         "(app/core/hubcheck.py):\n  "
                         + "\n  ".join(lines[:10]))
    if not split or any(res[c] for c in FILE_CHECKS) \
            or "location" not in frame.columns:
        _refuse(bad)
    per_loc: dict = {}
    pops = hubcheck._safe_populations()
    for loc, g in frame.groupby("location", sort=False):
        lb = hubcheck.failures(hubcheck.check_frame(
            g.reset_index(drop=True), None, None, populations=pops))
        if lb:
            per_loc[str(loc)] = _reason(lb)
    if not per_loc:
        _refuse(bad)            # no single location carries the defect
    if set(per_loc) >= set(frame["location"].astype(str)):
        _refuse(bad)            # zero valid locations
    return per_loc


def rows_from_quantiles(qs: dict, location_fips: str, asof: str,
                        horizons=HORIZONS) -> list:
    """FluSight rows from horizon -> {level: value} (quantile-native members).
    Same frozen join as quantile_rows, from the same hub_reference_date;
    horizon -1 is read from the ORIGIN key when `horizons` includes it.

    Emits only the levels given; `validate` refuses a partial set at the writer."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in horizons:
        q = qs.get(_key(h))
        if not q:
            continue
        target_end = ref + pd.Timedelta(weeks=h)
        levels = [l for l in QUANTILES if float(l) in q]
        values = _hub_values([q[float(l)] for l in levels])
        for level, v in zip(levels, values):
            rows.append({
                "reference_date": reference_date,
                "target": "wk inc flu hosp",
                "horizon": h,
                "target_end_date": str(target_end.date()),
                "location": location_fips,
                "output_type": "quantile",
                "output_type_id": level,
                "value": v,
            })
    return rows


def pmf_values(probs: dict, cats) -> list:
    """Probabilities for `cats`, in that order, as text to PMF_DECIMALS
    places, summing to exactly 1: each rounded to whole units of
    10**-PMF_DECIMALS, the remainder of the rounding (a unit or two) given
    to the most likely category. Refuses what is not a distribution."""
    p = np.array([float(probs.get(c, 0.0)) for c in cats])
    if (not np.isfinite(p).all() or (p < -1e-9).any()
            or abs(p.sum() - 1.0) > 1e-6):
        raise ValueError("rate-change probabilities are not a distribution: "
                         f"{dict(zip(cats, p.tolist()))}")
    unit = 10 ** PMF_DECIMALS
    n = np.rint(np.clip(p, 0.0, 1.0) * unit).astype(int)
    n[int(np.argmax(p))] += unit - int(n.sum())
    return [str(int(x) / unit) for x in n]


def rate_change_rows(probs_by_h: dict, location_fips: str, asof: str) -> list:
    """'wk flu hosp rate change' pmf rows for one location from hub horizon
    -> {category: probability} (app.core.categorical). Horizons outside
    RATE_CHANGE_HORIZONS and empty entries are skipped. The values are
    text ("0.1234"), so the file's whole-number admissions stay whole."""
    from app.core.categorical import CATS
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in RATE_CHANGE_HORIZONS:
        probs = probs_by_h.get(h) or probs_by_h.get(str(h))
        if not probs:
            continue
        target_end = ref + pd.Timedelta(weeks=h)
        for cat, v in zip(CATS, pmf_values(probs, CATS)):
            rows.append({
                "reference_date": reference_date,
                "target": RATE_CHANGE_TARGET,
                "horizon": h,
                "target_end_date": str(target_end.date()),
                "location": location_fips,
                "output_type": "pmf",
                "output_type_id": cat,
                "value": v,
            })
    return rows
