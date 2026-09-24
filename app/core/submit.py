"""PRODUCTION: hub submission CSVs and their validation
(app/ui/pipeline._run_all, oracle provenance).

FluSight submission formatting + validation.

Hub facts (model-metadata/README.md):
  * model identity lives in the PATH (model-output/<team>-<model>/), never in
    a CSV column: one file per model_id per reference date;
  * a team may designate up to two models for the ensemble;
  * quantile targets: 'wk inc flu hosp' at 23 quantiles; the hub takes
    horizons -1..3 and this app writes 0..3 (-1, the week already reported,
    is optional and never scored);
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


def quantile_rows(samples: dict, location_fips: str, asof: str) -> list:
    """FluSight rows for one location from horizon->samples arrays.

    Hub horizon 0..3 carries our canonical "0".."3" (the anchor under ORIGIN
    is never submitted). Callers pass the AS-OF date; the reference comes
    from hub_reference_date."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        s = np.asarray(samples.get(str(h), []), float)
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
    problems = []
    if df.empty:
        return ["submission is empty"]
    q = df[df.output_type == "quantile"].copy()
    if q.empty:
        return ["submission carries no quantile rows"]
    try:
        # numeric levels: a string column would sort lexicographically
        q["_level"] = [round(float(x), 4) for x in q.output_type_id]
    except (TypeError, ValueError):
        return ["quantile rows carry a non-numeric output_type_id"]
    for (loc, h), g in q.groupby([key_col, "horizon"]):
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
    return problems


def write_submission(all_rows: Iterable[dict], model: str, asof: str,
                     out_dir: Path, suffix: str = "") -> Path:
    """One hub-format CSV per model (identity is the PATH, rule above).

    `model` is a MODEL_ABBR key (never a free-text name); `asof` is the
    as-of the rows were built from. A name/`reference_date` mismatch is
    fatal here, before the hub rejects it. `suffix` (knobs.MODIFIED_SUFFIX
    for a run with modified model settings) makes the directory and file
    a NON-hub name, so such a file can never pass for the registered
    model."""
    df = pd.DataFrame(list(all_rows))
    problems = validate(df)
    if problems:
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
    d = Path(out_dir) / model_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ref}-{model_id}.csv"
    # atomic: every CSV here is listed as submittable, so never a truncated one
    tmp = p.with_name(p.name + ".tmp")
    try:
        df.to_csv(tmp, index=False)
        _hub_gate(tmp, p.name, d.name, hub_named=not suffix)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return p


def _hub_gate(tmp: Path, name: str, dir_name: str, hub_named: bool) -> None:
    """The written bytes, checked the way the hub checks them
    (app/core/hubcheck.py, rules from the vendored tasks.json). Any defect
    is fatal before the file takes its name. An off-season reference date
    is not a defect (replays of summer weeks are records, not
    submissions); a <hub id>-modified file skips the name checks, since
    its name is deliberately not a hub name."""
    from app.core import hubcheck
    res = hubcheck.check_frame(hubcheck.read_text_frame(tmp),
                               name if hub_named else None,
                               dir_name if hub_named else None)
    bad = hubcheck.failures(res)
    if bad:
        raise ValueError("submission failed the hub's checks "
                         "(app/core/hubcheck.py):\n  "
                         + "\n  ".join(bad[:10]))


def rows_from_quantiles(qs: dict, location_fips: str, asof: str) -> list:
    """FluSight rows from horizon -> {level: value} (quantile-native members).
    Same frozen join as quantile_rows, from the same hub_reference_date.

    Emits only the levels given; `validate` refuses a partial set at the writer."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        q = qs.get(str(h))
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
