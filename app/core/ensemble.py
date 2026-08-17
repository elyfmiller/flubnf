"""Vincentization: quantile-average the members with LOSO-frozen weights.

The validated recipe (docs/RESULTS.md): average QUANTILES, not densities;
weights chosen leave-one-season-out BEFORE the season and never retuned
in-season (rule: in-season weight search is leakage). Weights live in
app/state/ensemble_weights.json so re-freezing is an explicit, dated act.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from flubnf.quantiles import FLUSIGHT_QUANTILES as QL

WEIGHTS_FILE = Path(__file__).resolve().parents[1] / "state" / "ensemble_weights.json"
DEFAULT_WEIGHTS = {"pf": 0.6, "analogue": 0.4}   # 2025-26 LOSO grid pick; re-freeze pre-season


def frozen_weights() -> dict:
    if WEIGHTS_FILE.is_file():
        return json.loads(WEIGHTS_FILE.read_text())
    return dict(DEFAULT_WEIGHTS)


def member_quantiles_from_samples(samples_by_h: dict) -> dict:
    """horizon -> {level: value} from raw sample arrays (the PF's shape)."""
    out = {}
    for h in ("1", "2", "3", "4"):
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = {float(L): float(np.quantile(s, L)) for L in QL}
    return out


def vincentize(members: dict, weights: dict | None = None) -> dict:
    """members: name -> {horizon: {level: value}}. Returns the blended set.

    Members missing a horizon are excluded from that horizon with weights
    renormalized -- a member's gap must not drag the blend toward zero.
    """
    w = weights or frozen_weights()
    out = {}
    for h in ("1", "2", "3", "4"):
        have = {m: q[h] for m, q in members.items() if h in q and w.get(m, 0) > 0}
        if not have:
            continue
        tot = sum(w[m] for m in have)
        out[h] = {float(L): float(sum(w[m] * have[m][float(L)] for m in have) / tot)
                  for L in QL}
    return out
