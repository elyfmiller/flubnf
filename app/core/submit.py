"""FluSight submission formatting + validation.

Hub facts (verified against model-metadata/README.md, 2026-08-17):
  * model identity lives in the PATH (model-output/<team>-<model>/), never in
    a CSV column -- one file per model_id per reference date;
  * a team may designate up to two models for the ensemble (more via email
    with out-of-sample evidence);
  * quantile targets: 'wk inc flu hosp' at 23 quantiles, horizons -1..3;
  * value precision: whole admissions (integers), matching every official
    FluSight-baseline / FluSight-ensemble 'wk inc flu hosp' value from
    2025 on (see _hub_values; measured in the hub clone 2026-08-21).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

QUANTILES = (0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45,
             0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.975, 0.99)

#: Hub identity, as registered in model-metadata/. ONE definition: the
#: directory name, the file name and the metadata file name are all built
#: from these, so a hub fork can take the tree verbatim.
#:
#: Held as a constant rather than read from the YAML at run time because
#: model-metadata/ is not packaged -- pyproject's
#: [tool.setuptools.packages.find] includes only `flubnf*` and `app*`, so an
#: installed copy carries no YAML to read and writing a submission must not
#: depend on a file the wheel does not ship. The drift guard is a test:
#: app/tests/test_submit_join.py parses both YAML files and asserts these
#: values verbatim, so changing one without the other fails the suite.
#: The team registered on the hub since 2023. Submitting under the
#: EXISTING registration (rather than a new NAU_FluBNF team) was the
#: PIs' decision, 2026-08-27: the slot, its history and its
#: contributors carry forward, and the revised metadata cards describe
#: what the models now are.
TEAM_ABBR = "LosAlamos_NAU"

#: internal model key -> hub model_abbr (model-metadata/<team>-<abbr>.yml).
#: The ensemble keeps the registered CModel_Flu identity, so its scoring
#: history stays attached to one model_id; the mechanistic member is a
#: second, undesignated model under the same team.
MODEL_ABBR = {"pf": "SIHRS", "ensemble": "CModel_Flu"}


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
    """THE FROZEN JOIN, in one place: hub reference_date = our as-of
    Saturday + 7 days.

    Every producer in this module calls this and nothing else -- the row
    builders for the `reference_date` column, `write_submission` for the
    file name -- so the name and the contents cannot be computed by two
    different rules. They once were: the rows were built from the as-of
    plus seven while the file was named for the bare as-of, and a real run
    on 2026-08-26 produced `2026-01-03-...csv` in which every row said
    2026-01-10. The hub's round-id check compares the file name against
    `reference_date` (hub-config/validations.yml, t0_colname), so that
    submission would have been rejected."""
    return pd.Timestamp(asof) + pd.Timedelta(days=7)


def _hub_values(vals) -> list:
    """Quantile values in the hub's precision: whole admissions.

    Measured against the official FluSight-baseline and FluSight-ensemble
    submissions in the hub clone (2026-08-21): every 'wk inc flu hosp'
    quantile value from 2025 on is an integer count (the long float tails
    in recent official files belong to the 'wk inc flu prop ed visits'
    proportion target; the officials' own 2023-24 era count files carried
    tails and were since cleaned up). Our ensemble path was emitting raw
    numpy quantiles with 17-digit tails; this rounds to the officials'
    precision.

    The guard: rounding is monotone, but the non-decreasing order of the
    quantile vector is a hub validation rule, so it is re-enforced after
    rounding rather than assumed (float ties and any future rounding
    change stay safe). Returns Python ints so the CSV writes '14', never
    '14.0'."""
    v = np.rint(np.asarray(vals, float))
    v = np.maximum.accumulate(v)
    return [int(x) for x in v]


def quantile_rows(samples: dict, location_fips: str, asof: str) -> list:
    """FluSight rows for one location from horizon->samples arrays.

    THE FROZEN JOIN (must match scripts/anchor_analysis.py, the formula the
    seal's scoring validated): hub reference_date = our as-of Saturday + 7
    days, and hub horizon 0..3 carries our samples "1".."4". Callers pass
    the AS-OF date (spec.forecast_date); the reference comes from
    hub_reference_date, the one place that formula lives. Passing the as-of
    straight through as the reference mislabeled every exported CSV by one
    week (caught 2026-08-21, before any real submission)."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        s = np.asarray(samples.get(str(h + 1), []), float)
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


def validate(df: pd.DataFrame) -> list:
    """Gate before anything leaves the machine. Returns list of defects.

    The degenerate-cell rule is measured, not theoretical: 0.23% of cells once
    carried 49% of total WIS (zero-width quantiles at wrong levels).

    The completeness rule is the structural half of a trap that was once
    closed only by deleting a caller. hub-config/tasks.json marks the
    quantile `output_type_id` as REQUIRED at all 23 levels, so a file
    carrying fewer is rejected on submission; `rows_from_quantiles` emits
    only the levels its input dict happens to hold, and a re-blend from
    stored results held five. Removing that caller fixed the day's
    behaviour and left nothing to stop the next one, so the requirement is
    enforced here, on the path every written file takes.

    Horizons are NOT required in the same way: the same tasks.json marks
    horizon as optional (-1..3), and `quantile_rows` legitimately drops a
    horizon with no finite samples. Only the level set within a horizon is
    a completeness rule.
    """
    problems = []
    if df.empty:
        return ["submission is empty"]
    q = df[df.output_type == "quantile"].copy()
    if q.empty:
        return ["submission carries no quantile rows"]
    try:
        # numeric levels, and the sort below rides them: a string
        # output_type_id column would otherwise order 0.1 after 0.05
        # lexicographically and make every check read the wrong vector
        q["_level"] = [round(float(x), 4) for x in q.output_type_id]
    except (TypeError, ValueError):
        return ["quantile rows carry a non-numeric output_type_id"]
    for (loc, h), g in q.groupby(["location", "horizon"]):
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
                     out_dir: Path) -> Path:
    """One hub-format CSV per model (identity is the PATH, rule above).

    `model` is an internal key from MODEL_ABBR, not a free-text label: the
    team and model abbreviations come from the registered metadata, so a
    call site cannot invent a name the hub has never seen. `asof` is the
    forecast as-of Saturday, the same value the row builders were given;
    the file is named for hub_reference_date(asof), so the name and the
    `reference_date` column are computed by one formula from one input.

    The divergence guard below is deliberately fatal. The hub compares the
    file name against the `reference_date` column (hub-config/
    validations.yml sets t0_colname: "reference_date"), so a mismatch is
    caught on submission; catching it here means it is caught first, on the
    machine that produced it, with the two dates named."""
    df = pd.DataFrame(list(all_rows))
    problems = validate(df)
    if problems:
        raise ValueError("submission failed validation:\n  " +
                         "\n  ".join(problems[:10]))
    if "reference_date" not in df.columns:
        raise ValueError("submission rows carry no reference_date column; "
                         "the file name could not be checked against them")
    model_id = hub_model_id(model)
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
    # Write beside, then replace (the scores.json rule the app's other
    # writers follow): every CSV in this tree is listed as submittable by
    # the output page, so a full disk mid-write must never leave a
    # truncated file under the hub-named path. The temp file is removed
    # on any failure; after a successful replace it no longer exists.
    tmp = p.with_name(p.name + ".tmp")
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return p


def rows_from_quantiles(qs: dict, location_fips: str, asof: str) -> list:
    """FluSight rows from horizon -> {level: value} (quantile-native members).
    Same frozen join as quantile_rows, from the same hub_reference_date.

    This builder emits the levels its input holds and no others: it cannot
    invent the ones a caller did not compute. Completeness is therefore
    checked once, at the writer, by `validate` -- a partial dict produces a
    partial row set here and a refusal there, never a file."""
    ref = hub_reference_date(asof)
    reference_date = str(ref.date())
    rows = []
    for h in (0, 1, 2, 3):
        q = qs.get(str(h + 1))
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
