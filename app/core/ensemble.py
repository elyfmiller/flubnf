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
SHIPPED_WEIGHTS = Path(__file__).resolve().parents[1] / "state_defaults_ensemble_weights.json"


def frozen_weights() -> dict:
    """The 2026-08-17 freeze: per-horizon PF share rising 0.4->0.8 (analogue
    wins short-range, dynamics win long-range; LOSO 0.717), with 12 per-state
    overrides that each cleared a 2-of-3 held-out-season gain gate. A local
    state file overrides the shipped freeze; re-freezing is an explicit,
    dated act."""
    f = WEIGHTS_FILE if WEIGHTS_FILE.is_file() else SHIPPED_WEIGHTS
    return json.loads(f.read_text())


def pf_share(weights: dict, horizon: int, location_fips: str = "") -> float:
    per = weights.get("per_state", {}).get(str(location_fips))
    table = per or weights.get("global", {})
    return float(table.get(str(horizon), 0.6))


def member_quantiles_from_samples(samples_by_h: dict) -> dict:
    """horizon -> {level: value} from raw sample arrays (the PF's shape)."""
    out = {}
    for h in ("1", "2", "3", "4"):
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = {float(L): float(np.quantile(s, L)) for L in QL}
    return out


def vincentize(members: dict, weights: dict | None = None,
               location_fips: str = "") -> dict:
    """members: {"pf": ..., "analogue": ...} of horizon->quantiles. Blends with
    the frozen per-horizon (and per-state, where earned) PF share. A member
    missing a horizon leaves the other at weight 1."""
    w = weights or frozen_weights()
    out = {}
    for h in ("1", "2", "3", "4"):
        share = pf_share(w, int(h) - 1, location_fips)   # freeze keys horizons 0..3
        have = {m: q[h] for m, q in members.items() if h in q}
        if not have:
            continue
        if set(have) == {"pf", "analogue"}:
            out[h] = {float(L): float(share * have["pf"][float(L)]
                                      + (1 - share) * have["analogue"][float(L)])
                      for L in QL}
        else:
            only = next(iter(have.values()))
            out[h] = {float(L): float(only[float(L)]) for L in QL}
    return out
