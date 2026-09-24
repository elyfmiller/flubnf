"""PRODUCTION: the Oracle step applied after the filter (retro.run_week,
server._run_all).

The Oracle step: the mechanistic member's stored samples, after collect()
and before the storage boundary.

WHERE IT RUNS. Once per week on the filter's collected samples, in the two
places that collect them (retro.run_week for a replay, server._run_all for
a console run), right after pf_engine.collect(). Never inside the engine:
the filter is fitted unchanged and the step reads its output
(pre-registration 10.3 (1)).

WHAT IT DOES. Builds the week's B2 donor bank (admissions half via
flubnf.oracle_bank from the week's own vintage; FluSurv-NET half via
flubnf.oracle_mix from the committed bank by digest, shrink fitted on the
vintage), applies flubnf.oracle.member_for_cell per jurisdiction, and
returns the member (stored under `pf`) plus the provenance written to
oracle.json (see the prov dict in apply_week for its fields).

HORIZONS. Canonical "0".."3" are the library's physical weeks 1..4 in
order, so the translation is the order of the four blocks, here and
nowhere else. Hub rows still go through submit.quantile_rows.

THE PLAIN FILTER. A spec with `oracle = "none"` skips the step: the
filter's own samples are stored under `pf`, the member's submission is
withheld, the run is a research run and oracle.json says not applied.

NO SILENT IDENTITY. An unreadable vintage, an unbuildable pool, a missing
or digest-failing FluSurv-NET bank, or an unfittable shrink RAISES: a week
shipped as Oracle SIHRS that was quietly the plain filter is the failure
this exists to prevent. The pool's identity rule (< 2 donor seasons) is
registered behaviour, applied and recorded (active = 0).
"""
from __future__ import annotations

import gzip
import json
import os
import time
from datetime import date
from pathlib import Path

import numpy as np

from app.core import horizons as hz
from app.core.data import vintage_path
from flubnf import oracle as OR
from flubnf import oracle_bank as OB
from flubnf import oracle_mix as MX
from flubnf.settings import LOCATIONS

#: the filter's own samples, before the step: kept by a console run
#: (FILTER_RECORD_NAME) and by `oracle backfill`, not by a replay (oracle.json's
#: quantiles.null has them). Never in the quantile sidecar, scored or shown.
FILTER_KEY = "pf_filter"

#: the spec.extra key; "none" asks for the plain filter (a research run)
OPTION_KEY = "oracle"

PROVENANCE_NAME = "oracle.json"
BANK_DIRNAME = "oracle_bank"
#: a console run keeps the filter's own samples here (a workroot stores no
#: week record); the stored convention, gzipped, like a week's samples
FILTER_RECORD_NAME = "pf_filter.json.gz"

MEMBER_NAME = "Oracle SIHRS"


def wanted(extra) -> bool:
    """Whether a spec asks for the step: everything but `oracle = "none"`."""
    extra = extra if isinstance(extra, dict) else {}
    return str(extra.get(OPTION_KEY) or "") != "none"


def name_to_fips(locations_csv=None) -> dict:
    """location_name -> two-character FIPS (or 'US'), the hub's map."""
    import csv
    out = {}
    with open(locations_csv or LOCATIONS, newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["location_name"]] = r["location"].zfill(2)
    return out


def weeks_dropped(cells_dir) -> dict:
    """location -> k trimmed weeks, from the cells.json prepare() wrote
    (the per-cell `weeks_dropped`, the same-day trim included; the max over
    a location's replicates); {} when the file is absent."""
    try:
        cells = json.loads((Path(cells_dir) / "cells.json").read_text())
    except Exception:
        return {}
    out: dict = {}
    for c in cells if isinstance(cells, list) else []:
        loc = c.get("location")
        if loc is None:
            continue
        k = int(c.get("weeks_dropped", 0) or 0)
        out[loc] = max(out.get(loc, 0), k)
    return out


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _q(v) -> list | None:
    v = np.asarray(v, float)
    return [float(z) for z in v] if np.isfinite(v).all() else None


def _by_horizon(q4x23) -> dict:
    """(4, 23) -> {"0".."3": [23]} keyed by the hub's horizon, the internal
    week beside each; None where a block has no finite sample."""
    return {h: {"internal_h": hi + 1, "unrounded": _q(q4x23[hi])}
            for hi, h in enumerate(hz.HORIZONS)}


def horizon_table(asof: str) -> dict:
    """The mapping every provenance file carries (A1 (4))."""
    from app.core.submit import hub_reference_date
    import pandas as pd
    ref = hub_reference_date(asof)
    return {"rule": ("the stored blocks '1'..'4' (the library's physical weeks 1..4) are "
                     "FluSight horizons 0..3; the origin block is FluSight horizon -1; "
                     "reference_date = as-of + 7 days (app.core.submit.hub_reference_date); "
                     "target_end_date = reference_date + 7 * horizon"),
            "reference_date": str(ref.date()),
            "table": [{"stored_block": "0", "canonical": hz.ORIGIN, "flusight_horizon": -1,
                       "target_end_date": asof}] +
                     [{"stored_block": str(hi + 1), "canonical": h, "flusight_horizon": hi,
                       "target_end_date": str((ref + pd.Timedelta(weeks=hi)).date())}
                      for hi, h in enumerate(hz.HORIZONS)]}


def apply_week(pf_samples: dict, asof: str, out_dir, *, extra=None,
               weeks_to_drop: int = 0, drop_same_day: bool = False,
               populations: dict | None = None, vintage=None,
               locations_csv=None, w: float = OR.W_PRODUCTION,
               seeds=OR.SEEDS, submitted_seed: int = OR.SUBMITTED_SEED,
               aux=None, shrink: float | None = None) -> tuple:
    """The member for one week. Returns (member, provenance).

    `pf_samples`: collect()'s canonical output, location -> {ORIGIN, "0".."3"}.
    `out_dir` receives oracle.json and oracle_bank/; its cells.json, when
    present, supplies k. `aux` ((bank, manifest)) and `shrink` override the
    committed bank and the fitted shrink (tests and research only).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    T = date.fromisoformat(asof)
    vf = Path(vintage) if vintage is not None else vintage_path(asof)
    pops = populations if populations is not None else OB.load_populations(locations_csv or LOCATIONS)
    n2f = name_to_fips(locations_csv)
    built = OB.build_pool(asof, vf, pops, out_dir / BANK_DIRNAME, built_utc=_utc())
    pool, man, vb = built["pool"], built["manifest"], built["vintage"]
    mix = MX.build_week(asof, vb.count_bank, aux=aux, shrink=shrink,
                        out_dir=out_dir / BANK_DIRNAME, built_utc=_utc())
    auxp = mix["pool"]
    adm_ok = pool["rule"] == 1 and pool["n"] > 0
    state = MX.mixture_state(adm_ok, mix["admissible"])
    w_aux = MX.resolve_w_aux(adm_ok, mix["admissible"])
    bank_label = MX.label(man["digest"], mix["bank_digest"])
    yT = vb.y_T()
    k_cells = weeks_dropped(out_dir)
    k_source = ("cells.json (weeks_dropped per cell, the same-day trim included)"
                if k_cells else
                f"the spec (weeks_to_drop = {int(weeks_to_drop or 0)}"
                + ("; drop_same_day is set and the per-location same-day trim is "
                   "not knowable here: read m_0 / y_T" if drop_same_day else "") + ")")

    member: dict = {}
    locs_prov: dict = {}
    q_null: dict = {}
    q_primary: dict = {s: {} for s in seeds}
    q_secondary: dict = {s: {} for s in seeds}
    q_adm: dict = {s: {} for s in seeds}
    mean_primary: dict = {}
    mean_secondary: dict = {}
    mean_adm: dict = {}
    n_active = n_elig = absten = guard = 0
    identity, not_eligible, outside = [], [], []
    for loc, blocks in pf_samples.items():
        fips = n2f.get(loc)
        entry = {"fips": fips}
        origin = blocks.get(hz.ORIGIN, [])
        y = yT.get(fips) if fips else None
        y = float(y) if (y is not None and np.isfinite(y)) else None
        k = k_cells.get(loc, int(weeks_to_drop or 0))
        if fips is None or not fips.isdigit():
            # US (or unknown): outside the registered member, samples untouched
            member[loc] = {h: list(v) for h, v in blocks.items()}
            entry.update({"eligible": None, "active": 0, "k": k, "state": "outside",
                          "reason": "outside the registered member (no integer FIPS key)",
                          "y_T": y})
            outside.append(loc)
            locs_prov[loc] = entry
            continue
        xh = [blocks.get(h, []) for h in hz.HORIZONS]      # physical 1..4, in order
        r = OR.member_for_cell(origin, xh, pool, T, fips, w=w, seeds=seeds,
                               submitted_seed=submitted_seed, aux_pool=auxp)
        r2 = OR.member_for_cell(origin, xh, pool, T, fips, w=OR.W_SECONDARY,
                                seeds=seeds, submitted_seed=submitted_seed, aux_pool=auxp)
        r0 = OR.member_for_cell(origin, xh, pool, T, fips, w=w, seeds=seeds,
                                submitted_seed=submitted_seed)
        member[loc] = {hz.ORIGIN: list(origin),
                       **{h: r.samples[hi].tolist() for hi, h in enumerate(hz.HORIZONS)}}
        m0 = float(r.m0) if np.isfinite(r.m0) else None
        entry.update({
            "eligible": bool(r.eligible), "active": int(r.active), "k": k,
            "state": (state if r.active else ("not eligible" if not r.eligible else "identity")),
            "w_aux": r.w_aux, "n_flusurv_drawn": int(r.n_aux_drawn),
            "m_0": m0, "y_T": y,
            "m0_over_yT": (m0 / y if (m0 is not None and y and y > 0) else None),
            "m0_equals_yT_1e-9_relative": (bool(abs(m0 - y) <= 1e-9 * max(1.0, abs(y)))
                                           if (m0 is not None and y is not None) else None),
            "m_h": [float(z) if np.isfinite(z) else None for z in r.m],
            "lam_T": (float(r.lam_T) if np.isfinite(r.lam_T) else None),
            "G_T": (float(r.G_T) if np.isfinite(r.G_T) else None),
            "n_samples": r.n_total, "n_finite": r.n_finite,
            "n0_samples": r.n0_total, "n0_finite": r.n0_finite,
            "abstentions": int(r.abstentions), "guard_hits": int(r.guard_hits)})
        if not r.eligible:
            entry["reason"] = "not eligible (m_0, m_1..m_4 or G_T not positive): the identity"
            not_eligible.append(loc)
        elif not r.active:
            entry["reason"] = ("neither half of the donor bank is admissible "
                               f"({pool['rule_text']}; FluSurv-NET {mix['rule']}): the identity")
            identity.append(loc)
        n_elig += int(r.eligible)
        n_active += int(r.active)
        absten += r.abstentions
        guard += r.guard_hits
        q_null[loc] = _by_horizon(r.q_null)
        for s in seeds:
            q_primary[s][loc] = _by_horizon(r.q_seed[s])
            q_secondary[s][loc] = _by_horizon(r2.q_seed[s])
            q_adm[s][loc] = _by_horizon(r0.q_seed[s])
        mean_primary[loc] = _by_horizon(r.q_mean())
        mean_secondary[loc] = _by_horizon(r2.q_mean())
        mean_adm[loc] = _by_horizon(r0.q_mean())
        locs_prov[loc] = entry

    prov = {
        "written_by": "app.core.oracle.apply_week", "utc": _utc(),
        "member": MEMBER_NAME, "applied": True, "reading": "F", "transform": "REPLACE",
        "prereg_sha256": OR.PREREG_SHA256,
        "b2_sha256": OR.B2_SHA256, "addendum_a2_sha256": OR.ADDENDUM_A2_SHA256,
        "asof": asof, "season_index": OR.season_index(T),
        "bank": {"label": bank_label, "stream": MX.STREAM,
                 "admissions": {"label": built["label"], "stream": man["stream"],
                                "digest": man["digest"],
                                "file": str(OB.pool_path(out_dir / BANK_DIRNAME, asof)),
                                "manifest": str(OB.manifest_path(out_dir / BANK_DIRNAME, asof)),
                                "pool_rule": man["pool_rule"], "pool_reason": man["pool_reason"],
                                "admissible": bool(adm_ok),
                                "n_paths": man["cells"], "n_by_season": man["n_by_season"],
                                "counts": man["counts"]},
                 "flusurv": {"label": mix["bank_label"], "stream": MX.AUX_STREAM,
                             "bank_digest": mix["bank_digest"], "pool_digest": mix["digest"],
                             "file": str(MX.pool_path(out_dir / BANK_DIRNAME, asof)),
                             "manifest": str(MX.manifest_path(out_dir / BANK_DIRNAME, asof)),
                             "pool_rule": mix["rule"], "admissible": bool(mix["admissible"]),
                             "n_paths": mix["n_paths"],
                             "n_by_season": {str(k): v for k, v in mix["counts"]["by_season"].items()},
                             "n_aggregate": mix["n_aggregate"], "n_ny_site": mix["n_ny_site"],
                             "counts": {**mix["counts"], "by_season": {
                                 str(k): v for k, v in mix["counts"]["by_season"].items()}},
                             "shrink": mix["shrink"],
                             "shrink_prior_seasons": mix["shrink_prior_seasons"]},
                 "mixture": {"identity_rule": MX.IDENTITY_RULE, "state": state,
                             "w_aux": w_aux, "w_aux_nominal": MX.W_AUX}},
        "vintage": {"file": str(vf), "sha256": man["source_sha256"],
                    "newest_row_date": vb.newest_row_date().isoformat()},
        "rule": man["rule"], "rule_flusurv": MX.rule_block(mix["bank_digest"]),
        "w": float(w), "w_secondary": float(OR.W_SECONDARY),
        "seeds": [int(s) for s in seeds], "submitted_seed": int(submitted_seed),
        "trimmed_weeks": {"source": k_source,
                          "k_by_location": {loc: e["k"] for loc, e in locs_prov.items()},
                          "locations_with_m0_not_equal_yT":
                              [loc for loc, e in locs_prov.items()
                               if e.get("m0_equals_yT_1e-9_relative") is False],
                          "locations_without_vintage_row":
                              [loc for loc, e in locs_prov.items() if e.get("y_T") is None]},
        "cells": {"locations": len(pf_samples), "eligible": n_elig, "active": n_active,
                  "identity_pool": identity, "not_eligible": not_eligible,
                  "outside_member": outside},
        "abstentions": int(absten), "guard_hits": int(guard),
        "locations": locs_prov,
        "quantiles": {"levels": OR.QL, "horizons": horizon_table(asof),
                      "rule": "numpy.quantile (linear) of the finite entries; None where none is finite",
                      "null": q_null,
                      "primary": {"w": float(w), "bank": MX.STREAM, "seed_mean": mean_primary,
                                  "per_seed": {str(s): q_primary[s] for s in seeds}},
                      "secondary": {"w": float(OR.W_SECONDARY), "bank": MX.STREAM,
                                    "seed_mean": mean_secondary,
                                    "per_seed": {str(s): q_secondary[s] for s in seeds},
                                    "note": ("the registered secondary weight on the shipped "
                                             "bank (LB25GH); logged, ships nothing")},
                      "admissions_only": {"w": float(w), "bank": OB.STREAM,
                                          "seed_mean": mean_adm,
                                          "per_seed": {str(s): q_adm[s] for s in seeds},
                                          "note": ("the frozen document's member on the "
                                                   "admissions half alone (LB), logged beside "
                                                   "the primary (addendum A2 (2)); ships nothing")}},
    }
    write_provenance(out_dir, prov)
    return member, prov


def write_provenance(out_dir, prov: dict) -> Path:
    """oracle.json beside the week, atomically."""
    fp = Path(out_dir) / PROVENANCE_NAME
    tmp = fp.with_name(fp.name + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(prov, fh)
    os.replace(tmp, fp)
    return fp


def write_not_applied(out_dir, asof: str, reason: str) -> Path:
    """The provenance of a week that ran the plain filter (the research
    configuration): the step was not applied, and the file says so."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    return write_provenance(out_dir, {
        "written_by": "app.core.oracle.write_not_applied", "utc": _utc(),
        "member": MEMBER_NAME, "applied": False, "asof": asof, "reason": reason,
        "prereg_sha256": OR.PREREG_SHA256,
        "b2_sha256": OR.B2_SHA256, "addendum_a2_sha256": OR.ADDENDUM_A2_SHA256,
        "stored_pf": "the filter's own samples (the plain filter, a research configuration)"})


def read_provenance(out_dir) -> dict | None:
    """oracle.json of a week, or None when absent or unreadable."""
    try:
        return json.loads((Path(out_dir) / PROVENANCE_NAME).read_text())
    except Exception:
        return None


def write_filter_record(workroot, asof: str, raw: dict) -> Path:
    """A console run's copy of the filter's own samples (stored convention,
    gzipped, under FILTER_KEY). Read by the 2026-27 shadow run, not the console."""
    fp = Path(workroot) / FILTER_RECORD_NAME
    tmp = fp.with_name(fp.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(hz.record_to_stored({"asof": asof, FILTER_KEY: raw}), fh)
    os.replace(tmp, fp)
    return fp
