"""RESEARCH: forecasts on a user-supplied dataset (app/core/datasets.py).

One console run on a custom dataset: the Groundhog and, for counts with a
population, the plain SIHRS particle filter, both through the SAME engines
as the hub path (they read the dataset because the spec names it in
extra["dataset"]). What differs from app/ui/pipeline._run_all, and why:

  * no Oracle step: its donor bank is FluSight's admissions plus
    FluSurv-NET, keyed by FIPS; on other data it would be a silent identity
    (app/core/oracle.py). The member is the plain filter, labelled so.
  * no FluSurv-NET donors for the Groundhog unless the run opts in, and no
    flu donor-season exclusions (engines/analogue._source).
  * the output floor (a Poisson count rule) and integer rounding apply to
    counts only; a rate dataset keeps its decimals.
  * exports, never submissions: hubverse model-output CSVs keyed by the
    dataset's own unit column (location or target_group, holding the
    uploaded keys), under non-hub model names (EXPORT_IDS), in
    <workroot>/export/. Nothing is written under submission/.
  * scored against an in-house persistence baseline
    (flubnf.baseline_forecast), never FluSight-baseline, which has no cells
    for custom keys. The national group, when the dataset has one, is
    scored beside the pooled figure, never inside it.
  * hub-only steps are skipped: the US national aggregate, the weekly
    report (US map, categorical rate target) and the forecast archive.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.core import horizons as hz
from app.core import missing as MS
from app.core import submit as SB
from app.core.runs import GROUNDHOG_OWN_DATA
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL

#: member key -> exported model id (never a registered NAU_PyBNF identity)
EXPORT_IDS = {"analogue": "FluBNF-Groundhog", "pf": "FluBNF-SIHRS-PF"}
#: member key -> what pages call it on custom data ("Groundhog (own data)":
#: the export keeps FluBNF-Groundhog)
MEMBER_LABELS = {"analogue": GROUNDHOG_OWN_DATA,
                 "pf": "plain SIHRS particle filter"}
#: the baseline every custom relWIS is measured against, by name
BASELINE = "in-house persistence baseline"
BASELINE_NOTE = ("relWIS against the in-house persistence baseline "
                 "(flubnf.baseline_forecast), not FluSight-baseline; it is "
                 "not comparable with FluSight scores.")
EXPORT_DIR = "export"
#: quantile levels kept in results.json (the run page's fans)
FIVE = ("0.1", "0.25", "0.5", "0.75", "0.9")
#: stop between steps when this file appears in the workroot (the console's
#: Stop button touches it; the PF polls it too)
STOP = "STOP"


class Stopped(Exception):
    pass


def analogue_donors(extra) -> str:
    """Where a dataset run's Groundhog drew its donors: the dataset's own
    weeks, or those plus the FluSurv-NET bank when the run opted in."""
    extra = extra if isinstance(extra, dict) else {}
    if extra.get("aux_pools"):
        return ("calendar analogue with FluSurv-NET donors ("
                + str(extra.get("analogue_aux") or "auxiliary bank") + ")")
    return "calendar analogue on the dataset's own weeks"


def analogue_label(extra) -> str:
    """Which Groundhog a dataset run ran, named as the console names it on
    custom data: 'Groundhog (own data): <its donors>'."""
    return f"{GROUNDHOG_OWN_DATA}: {analogue_donors(extra)}"


def key_col(ds) -> str:
    """The export's unit column: target_group for a grouped CSV, else
    location."""
    return "target_group" if ds.meta.get("format") == "grouped" else "location"


def target_name(ds) -> str:
    return str(ds.meta.get("target") or "custom")


def source_keys(ds) -> dict:
    """group name -> the key the upload used for it."""
    return {g["name"]: g.get("source_key") or g["name"]
            for g in ds.meta["groups"]}


def observed(ds, as_of: str, names, drop_same_day: bool = False,
             tail: int = 15) -> dict:
    """{name: [[date, value], ...]}: the newest `tail` weeks each group had
    AT the as-of (the snapshot for versioned data, the final series cut at
    the as-of otherwise). The same-day row is dropped when the run drops it."""
    out = {}
    for n in names:
        s = ds.series(n, as_of)
        pairs = [[d, v] for d, v in zip(s["dates"], s["values"])
                 if not (drop_same_day and d == str(as_of))]
        out[n] = pairs[-tail:]
    return out


def quantiles_from_samples(samples: dict) -> dict:
    """{h: {level: value}} at the 23 levels from {h: samples}, forecast
    horizons only (the origin is never a forecast)."""
    out = {}
    for h in hz.HORIZONS:
        a = np.asarray(samples.get(h, []), float)
        a = a[np.isfinite(a)]
        if a.size:
            out[h] = {float(L): float(np.quantile(a, L)) for L in QL}
    return out


def five(qd: dict) -> dict:
    """{h: {"0.1".."0.9": value}}: the run page's fan levels."""
    return {h: {q: float(lv[float(q)]) for q in FIVE}
            for h, lv in qd.items() if all(float(q) in lv for q in FIVE)}


# ------------------------------------------------------------------ export

def export_rows(q_by_name: dict, ds, as_of: str, *, integer: bool) -> list:
    """Hubverse model-output rows keyed by the dataset's own unit column.
    reference_date is the as-of + 7 days (submit.hub_reference_date, the
    hub's frozen join); counts are whole numbers, rates keep 6 decimals."""
    ref = SB.hub_reference_date(as_of)
    col, tgt, keys = key_col(ds), target_name(ds), source_keys(ds)
    rows = []
    for name, qs in q_by_name.items():
        for h in hz.HORIZONS:
            q = qs.get(h)
            if not q:
                continue
            levels = [L for L in SB.QUANTILES if float(L) in q]
            raw = [q[float(L)] for L in levels]
            vals = (SB._hub_values(raw) if integer else
                    [round(float(x), 6) for x in
                     np.maximum.accumulate(np.asarray(raw, float))])
            for L, v in zip(levels, vals):
                rows.append({
                    "reference_date": str(ref.date()), "target": tgt,
                    "horizon": int(h),
                    "target_end_date": str((ref + pd.Timedelta(
                        weeks=int(h))).date()),
                    col: keys.get(name, name), "output_type": "quantile",
                    "output_type_id": L, "value": v})
    return rows


def export_id(model: str, modified: bool = False) -> str:
    from app.core import knobs as K
    return EXPORT_IDS[model] + (K.MODIFIED_SUFFIX if modified else "")


def write_export(rows: list, model_id: str, as_of: str, workroot: Path,
                 key: str) -> Path:
    """<workroot>/export/<model_id>/<reference_date>-<model_id>.csv, after
    submit.validate's structural checks (23 levels, monotone, non-negative,
    not zero-width). Atomic: a reader never sees half a file."""
    df = pd.DataFrame(rows)
    problems = SB.validate(df, key_col=key)
    if problems:
        raise ValueError("export failed validation:\n  "
                         + "\n  ".join(problems[:10]))
    ref = str(SB.hub_reference_date(as_of).date())
    d = Path(workroot) / EXPORT_DIR / model_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ref}-{model_id}.csv"
    tmp = p.with_name(p.name + ".tmp")
    try:
        df.to_csv(tmp, index=False)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return p


def export_files(workroot: Path) -> list:
    """The export CSVs under a workroot: [{model, name, path}]."""
    return [{"model": p.parent.name, "name": p.name, "path": str(p)}
            for p in sorted(Path(workroot).glob(f"{EXPORT_DIR}/*/*.csv"))]


# ----------------------------------------------------------------- scoring

def baseline_quantiles(ds, name: str, as_of: str, weeks_to_drop: int = 0):
    """The in-house persistence baseline (flubnf.baseline_forecast, the
    FluSight-baseline construction) for one group at one as-of, on the
    series the models saw: the snapshot (or final data cut at the as-of),
    less the dropped weeks, reaching each labelled horizon. None when fewer
    than two weeks are observed. It reads the series in date order and
    ignores gaps, as the library does."""
    from flubnf.baseline_forecast import persistence_quantile_forecast
    s = ds.series(name, as_of)
    vals = list(s["values"])
    k = int(weeks_to_drop or 0)
    if k:
        vals = vals[:-k] if len(vals) > k else []
    if len(vals) < 2:
        return None
    steps = [int(h) + 1 + k for h in hz.HORIZONS]      # physical weeks ahead
    fc = persistence_quantile_forecast(np.asarray(vals, float), steps)
    return {h: {float(L): float(fc.quantiles[i, j])
                for i, L in enumerate(fc.quantile_levels)}
            for j, h in enumerate(hz.HORIZONS)}


def score(q_by_name: dict, ds, as_of: str, *, weeks_to_drop: int = 0,
          truth: dict | None = None) -> pd.DataFrame:
    """One row per scored cell: location (group name), horizon, wis,
    base_wis, rel, national. The cell rule is scoring.py's (truth > 0,
    median > 0, a baseline cell) plus base_wis > 0: a flat series gives the
    persistence baseline a point mass that can score exactly zero."""
    from flubnf.wis import wis
    truth = ds.truth() if truth is None else truth
    nat = ds.national_group
    T = pd.Timestamp(as_of)
    rows = []
    for name, qs in q_by_name.items():
        base = None
        for h in hz.HORIZONS:
            q = qs.get(h)
            if not q:
                continue
            end = (T + timedelta(days=7 * (int(h) + 1))).date().isoformat()
            actual = truth.get((name, end))
            if actual is None or actual <= 0 or q.get(0.5, 0) <= 0:
                continue
            if base is None:
                base = baseline_quantiles(ds, name, as_of, weeks_to_drop) or {}
            bq = base.get(h)
            if not bq:
                continue
            try:
                w = float(wis(q, actual).wis)
                bw = float(wis(bq, actual).wis)
            except Exception:
                continue
            if not bw > 0:
                continue
            rows.append({"location": name, "horizon": int(h), "wis": w,
                         "base_wis": bw, "rel": w / bw,
                         "national": name == nat, "truth": actual})
    return pd.DataFrame(rows, columns=["location", "horizon", "wis",
                                       "base_wis", "rel", "national",
                                       "truth"])


def summarize(cells: pd.DataFrame) -> dict:
    """relWIS as a ratio of sums over the groups (the national group
    excluded), plus the national group's own figure beside it."""
    def block(c):
        if c.empty:
            return {"cells": 0, "relwis": None}
        return {"cells": int(len(c)),
                "relwis": round(float(c.wis.sum() / c.base_wis.sum()), 3)}
    if cells.empty:
        return {**block(cells), "national": None}
    nat = cells[cells.national.astype(bool)]
    return {**block(cells[~cells.national.astype(bool)]),
            "national": block(nat) if len(nat) else None}


# --------------------------------------------------------------------- run

def _check_stop(workroot: Path) -> None:
    if (Path(workroot) / STOP).exists():
        raise Stopped("stopped by user")


def run(spec, ds, workroot: Path, *, phase=lambda msg: None,
        pf_state: str = "absent") -> tuple:
    """Run one dataset forecast into `workroot`: (outcome, pf failures).

    Writes results.json (the console's stored shape plus the dataset's
    record) and the export CSVs. `pf_state` is pipeline._pf_engine_state():
    the filter runs only when it is 'ready' and the dataset is eligible."""
    from app.core import knobs as K
    from app.core.engines import analogue as an_engine
    from app.core.engines import pf as pf_engine
    from app.core.floor import floor_quantiles, floor_samples

    workroot = Path(workroot)
    extra = spec.extra or {}
    count = ds.kind == "count"
    modified = K.modified(spec)
    lam = K.value_of(extra, "output.floor_lam")
    fkw = {} if lam is None else {"lam": float(lam)}
    outcome = {"dataset": ds.name, "dataset_id": ds.id,
               "vintage_true": ds.vintage_true, "oracle": "none",
               "baseline": BASELINE}
    if modified:
        K.write_record(workroot / "knobs.json", spec)
        outcome["knobs"] = K.summary(K.record_of(spec))
    names = list(spec.locations)
    obs = observed(ds, spec.forecast_date, names,
                   drop_same_day=bool(getattr(spec, "drop_same_day", False)))
    fails: dict = {}
    pf_q: dict = {}
    # 1. the plain SIHRS filter: counts with a population, a ready engine
    if spec.engine in ("all", "pf"):
        if not ds.pf_eligible:
            outcome["pf_skipped"] = ("the dataset is not counts with a "
                                     "population (the filter needs both)")
        elif pf_state == "broken":
            msg = pf_engine.engine_missing_message()
            outcome["pf_engine_broken"] = msg
            raise RuntimeError(msg)
        elif pf_state != "ready":
            outcome["pf_skipped"] = "engine venv not installed (Tier A)"
        else:
            phase("materializing models (BNG network generation)")
            pf_engine.prepare(spec, workroot)
            phase(f"filtering {len(names)} group(s) × {spec.replicates} "
                  "replicate(s)")
            status = pf_engine.execute(workroot)
            fails = {k: v for k, v in status.items() if v != "ok"}
            outcome["pf_cells"] = len(status)
            outcome["pf_failures"] = fails
            # fit origins moved back by unreported newest weeks, or
            # abstentions (prepare's notes; absent when none moved)
            notes = pf_engine.read_anchor_notes(workroot)
            if notes:
                outcome["pf_anchor_notes"] = notes
            samples = pf_engine.collect(workroot)
            samples = {n: floor_samples(s, n, spec.forecast_date,
                                        recent=[v for _, v in obs.get(n, [])],
                                        **fkw) if count else s
                       for n, s in samples.items()}
            pf_q = {n: quantiles_from_samples(s) for n, s in samples.items()}
            pf_q = {n: q for n, q in pf_q.items() if q}
    _check_stop(workroot)
    # 2. the Groundhog (instant)
    an_q: dict = {}
    # the missing-data rules (app/core/missing.py): the flagged weeks are
    # recorded only when a rule is on, as the console's run records them
    rules = MS.rules_of(extra)
    gh_flags: list = []
    if spec.engine in ("all", "analogue"):
        phase("consulting the Groundhog")
        an_notes: dict = {}
        an_kw = {"notes": an_notes}
        if rules:
            an_kw["flags"] = gh_flags
        an_q = an_engine.run(spec, **an_kw)
        if an_notes:
            outcome["analogue_anchor_notes"] = an_notes
        if count:
            an_q = {n: floor_quantiles(q, **fkw) for n, q in an_q.items()}
    if rules:
        try:
            pf_cells = json.loads((workroot / "cells.json").read_text())
        except Exception:
            pf_cells = []
        outcome["data_flags"] = {"analogue": gh_flags,
                                 "pf": MS.cell_flags(pf_cells)}
    outcome["analogue_label"] = analogue_label(extra)
    members = {m: q for m, q in (("pf", pf_q), ("analogue", an_q))
               if spec.engine in ("all", m)}
    ran = {m for m in members
           if not (m == "pf" and ("pf_skipped" in outcome))}
    outcome["abstained"] = {m: sorted(set(names) - set(members[m]))
                            for m in ran if set(names) - set(members[m])}
    # 3. exports: non-hub names, the dataset's own unit column
    phase("writing the export files")
    exports, errors = {}, {}
    for m in sorted(ran):
        q = members[m]
        if not q:
            continue
        mid = export_id(m, modified)
        try:
            rows = export_rows(q, ds, spec.forecast_date, integer=count)
            exports[mid] = str(write_export(rows, mid, spec.forecast_date,
                                            workroot, key_col(ds)))
        except Exception as e:
            errors[mid] = str(e)[:400]
    outcome["exports"] = exports
    if errors:
        outcome["export_errors"] = errors
    # 4. scoring against the in-house persistence baseline, when the
    # dataset holds weeks after the as-of
    scores, frames = {}, []
    try:
        truth = ds.truth()
        for m in sorted(ran):
            c = score(members[m], ds, spec.forecast_date,
                      weeks_to_drop=int(spec.weeks_to_drop or 0),
                      truth=truth)
            if not c.empty:
                c["model"] = m
                frames.append(c)
                scores[m] = summarize(c)
        if frames:
            pd.concat(frames, ignore_index=True).to_json(
                workroot / "scores_custom.json")
    except Exception as e:
        outcome["score_error"] = str(e)[:200]
    if scores:
        outcome["custom_scores"] = scores
    # 5. results.json: the stored convention every run artefact uses
    body = {
        "spec": spec.to_json(), "forecast_date": spec.forecast_date,
        "research": True,
        "dataset": {**ds.ref(), "vintage_true": ds.vintage_true,
                    "kind": ds.kind, "national_group": ds.national_group,
                    "key_col": key_col(ds), "target": target_name(ds)},
        "oracle": "none", "baseline": BASELINE,
        **({"knobs": outcome["knobs"]} if "knobs" in outcome else {}),
        "observed": obs, "params": {},
        "scores": scores,
        "models": hz.models_to_stored({m: {n: five(q) for n, q in qd.items()}
                                       for m, qd in members.items()
                                       if m in ran}),
    }
    tmp = workroot / "results.json.tmp"
    tmp.write_text(json.dumps(body))
    os.replace(tmp, workroot / "results.json")
    outcome["archived"] = "skipped: custom dataset (research)"
    return outcome, fails
