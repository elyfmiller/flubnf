"""Vincentization: quantile-average the members with LOSO-frozen weights.

The validated recipe (docs/RESULTS.md): average QUANTILES, not densities;
weights chosen leave-one-season-out BEFORE the season and never retuned
in-season (rule: in-season weight search is leakage). Weights live in
app/state/ensemble_weights.json so re-freezing is an explicit, dated act.

vincentize() also takes an explicit {member_name: weight} dict for N-member
blends (the optional three-member run with the two-strain candidate);
equal_weights() builds the uniform case.
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


def equal_weights(members: dict) -> dict:
    """Uniform weights over the given members: {name: 1/N}."""
    n = max(len(members), 1)
    return {name: 1.0 / n for name in members}


def vincentize(members: dict, weights: dict | None = None,
               location_fips: str = "") -> dict:
    """members: {name: horizon->quantiles}. Two blending modes:

    * weights None (or the frozen-format dict with "global"/"per_state"):
      the validated 2-member path -- {"pf", "analogue"} blend with the frozen
      per-horizon (and per-state, where earned) PF share. A member missing a
      horizon leaves the other at weight 1.
    * weights {member_name: weight}: N-member quantile average, weights
      renormalized over the members present at each horizon.
    """
    member_weighted = weights is not None and not (
        "global" in weights or "per_state" in weights)
    w = weights if member_weighted else (weights or frozen_weights())
    out = {}
    for h in ("1", "2", "3", "4"):
        have = {m: q[h] for m, q in members.items() if h in q}
        if not have:
            continue
        # blend over the levels the members actually share: the live run
        # carries all 23 FluSight levels, a re-blend from stored results
        # carries the display set -- both must work (KeyError 0.01 otherwise)
        if member_weighted:
            named = {m: float(w.get(m, 0.0)) for m in have}
            tot = sum(named.values())
            if tot <= 0:                       # nothing weighted -> uniform
                named, tot = equal_weights(have), 1.0
            levels = sorted(set.intersection(*(set(q) for q in have.values())))
            out[h] = {float(L): float(sum(named[m] * have[m][L]
                                          for m in have) / tot)
                      for L in levels}
        elif set(have) == {"pf", "analogue"}:
            share = pf_share(w, int(h) - 1, location_fips)   # freeze keys horizons 0..3
            levels = sorted(set(have["pf"]) & set(have["analogue"]))
            out[h] = {float(L): float(share * have["pf"][L]
                                      + (1 - share) * have["analogue"][L])
                      for L in levels}
        elif len(have) == 1:
            only = next(iter(have.values()))
            out[h] = {float(L): float(v) for L, v in only.items()}
        else:
            # frozen weights know nothing about this member set: average
            # equally rather than silently picking an arbitrary member
            levels = sorted(set.intersection(*(set(q) for q in have.values())))
            out[h] = {float(L): float(sum(q[L] for q in have.values())
                                      / len(have))
                      for L in levels}
    return out
