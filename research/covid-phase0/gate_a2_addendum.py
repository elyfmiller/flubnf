"""Gate A round two addendum: the trajectory-file taxonomy, measured cleanly.

WHY THIS IS A SEPARATE FILE
---------------------------
gate_a2.py is the frozen pre-registration (hash 309ba9015b03519a, recorded in
its results); it is not edited after the run. This script reads the records it
wrote and corrects one factual matter discovered DURING the run, which also
retracts a round-one caveat.

THE DISCOVERY, WITH THE RECEIPTS
--------------------------------
PyBNF's AMCMC writes one noise trajectory per chain
(traj_noise_<obs>_chain_0..3.txt, algorithms.py write_out_trajactorys_noise)
AND, whenever num_parallel != 1, an aggregate combined_traj_noise_<obs>.txt
concatenating every chain (algorithms.py combine_chains_traj). In sorted glob
order "combined_..." precedes "traj_noise_...".

Consequence one, A ROUND-ONE RETRACTION: round one's gate_a.py took
sorted(glob("*traj_noise*"))[0], and its addendum (gate_a_report.py, "A SECOND
HARNESS DEFECT") declared that to be CHAIN 0 ONLY and the AMCMC width therefore
a lower bound that "cannot be repaired from the stored records". Both claims
are wrong: [0] was the COMBINED file, so the round-one AMCMC widths were
all-chain all along and the stored samples were all-chain samples. The
"lower bound" caveat is retracted; the round-one AMCMC width numbers stand as
measured, relabeled from "chain 0" to "all chains, aggregate anchor scale".

Consequence two, FOR THIS ROUND: gate_a2.py's samples_by_chain has FIVE
entries when the combine step ran: index "0" is the combined file, "1".."4"
are the real chains 0..3. Its pooled width therefore counts every draw exactly
twice (once in its chain file, once in the combined file), which is
WEIGHT-NEUTRAL for quantiles: the pooled raw widths are unbiased. Two derived
columns need relabeling and clean recomputation, done here:
  * "width_rel_chain0_raw" actually measured the combined file (all chains,
    matching the round-one metric), not chain 0;
  * "width_rel_rescaled" mixed aggregate-scaled and per-chain-scaled draws
    50/50. Both clean treatments are computed below: aggregate anchor scale
    (one scale from the combined origin median, the pf.collect convention) and
    per-chain anchor scale (each chain rescaled by its own origin median).

Run:  .venv/bin/python research/covid-phase0/gate_a2_addendum.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flubnf import covid_vintage as cv                 # noqa: E402
from flubnf.profiles import COVID                      # noqa: E402

OUT = Path(__file__).resolve().parent / "out" / "round2"
HORIZONS = (1, 2, 3, 4)


def split_files(rec: dict):
    """(combined_or_None, real_chain_dict). 5 files -> [0] is combined."""
    sbc = rec["samples_by_chain"]
    keys = sorted(sbc, key=int)
    if len(keys) >= 5:
        return sbc[keys[0]], {k: sbc[k] for k in keys[1:]}
    return None, dict(sbc)


def main() -> None:
    records = json.loads((OUT / "gate_a2_records.json").read_text())
    truth = cv.vintage_frame(cv.vintages()[-1])
    tmap = {(r.location_name, str(r.date)[:10]): float(r.value)
            for r in truth.itertuples()}
    rows = []
    for rec in records:
        if not rec.get("ok"):
            continue
        combined, chains = split_files(rec)
        anchor = rec["data_edge"]

        def arr(d, h):
            v = np.asarray(d[str(h)], float)
            return v[np.isfinite(v)]

        # anchor scales
        sc_chain = {}
        for k, d in chains.items():
            o = arr(d, 0)
            m0 = float(np.median(o)) if o.size else float("nan")
            sc_chain[k] = rec["last_observed"] / m0 if m0 > 0 else 1.0
        if combined is not None:
            o = arr(combined, 0)
            m0 = float(np.median(o)) if o.size else float("nan")
            sc_agg = rec["last_observed"] / m0 if m0 > 0 else 1.0
        else:
            pooled0 = np.concatenate([arr(d, 0) for d in chains.values()])
            m0 = float(np.median(pooled0)) if pooled0.size else float("nan")
            sc_agg = rec["last_observed"] / m0 if m0 > 0 else 1.0

        for h in HORIZONS:
            target = str((pd.Timestamp(anchor)
                          + pd.Timedelta(days=7 * h)).date())
            if COVID.excluded_for(anchor, target):
                continue
            actual = tmap.get((rec["state"], target))
            if actual is None or actual <= 0:
                continue
            raw = np.concatenate([arr(d, h) for d in chains.values()])
            agg = raw * sc_agg
            per = np.concatenate([arr(d, h) * sc_chain[k]
                                  for k, d in chains.items()])
            c0 = arr(chains[sorted(chains, key=int)[0]], h)

            def w(v):
                lo, hi = np.percentile(v, [2.5, 97.5])
                return float((hi - lo) / actual), bool(lo <= actual <= hi)
            w_raw, c_raw = w(raw)
            w_agg, c_agg2 = w(agg)
            w_per, c_per = w(per)
            w_c0, _ = w(c0)
            rows.append({
                "arm": rec["arm"], "state": rec["state"], "asof": rec["asof"],
                "horizon": h, "actual": actual,
                "scale_agg": round(sc_agg, 3),
                "scale_chain_max": round(max(sc_chain.values()), 3),
                "width_raw_allchain": w_raw, "cov_raw": c_raw,
                "width_agg_scale": w_agg, "cov_agg": c_agg2,
                "width_perchain_scale": w_per, "cov_perchain": c_per,
                "width_true_chain0_raw": w_c0})
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "addendum_amcmc_cells.csv", index=False)
    out = {}
    for arm in ("A1", "A2", "A3"):
        u = df[df["arm"] == arm]
        if not len(u):
            continue
        out[arm] = {
            "cells": int(len(u)),
            "width_raw_allchain_median": float(u["width_raw_allchain"].median()),
            "coverage_raw": float(u["cov_raw"].mean()),
            "width_agg_scale_median": float(u["width_agg_scale"].median()),
            "coverage_agg_scale": float(u["cov_agg"].mean()),
            "width_perchain_scale_median": float(
                u["width_perchain_scale"].median()),
            "coverage_perchain_scale": float(u["cov_perchain"].mean()),
            "width_true_chain0_raw_median": float(
                u["width_true_chain0_raw"].median()),
            "anchor_scale_agg_max": float(u["scale_agg"].max()),
            "anchor_scale_chain_max": float(u["scale_chain_max"].max()),
            "n_cells_agg_scale_gt3": int(
                (u.groupby(["state", "asof"])["scale_agg"].max() > 3).sum()),
        }
    out["notes"] = {
        "retraction": ("round one's AMCMC width was all-chain via the combined "
                       "file, not chain-0-only; the gate_a_report.py 'lower "
                       "bound' caveat is retracted"),
        "double_count": ("gate_a2.py pooled combined+chains, weight-neutral "
                         "for quantiles; clean decompositions above"),
    }
    (OUT / "gate_a2_addendum.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
