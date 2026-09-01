"""Vincentization: quantile-average the members with EQUAL, unfitted weights.

The validated recipe (the lab archive NAU-Projects/NAU_Influenza_M_Model/FluBNF/docs/RESULTS.md (restated in docs/RELEASE-1.0.md)): average QUANTILES, not densities,
and do not fit the blend. Across the three sealed seasons, applying the
frozen fitted table scores 0.6958 pooled against the fixed 0.5's 0.6781, and
fitted weights anti-predicted the held-out season every time they were
tried. The unfitted 50/50 blend is what v1.0 ships and what every published
number in this repository was computed with.

So vincentize() DEFAULTS to equal weights. The LOSO-frozen table still
exists and can still be scored against, but only for a caller that asks for
it BY NAME (`weights=FROZEN`, or the table itself). It can never arrive by
omitting an argument: a fitted blend is a research path, and this project's
rule is that fitting never happens by default. Weights live in
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

#: The one value that requests the LOSO-fitted table. Spelled out at the call
#: site so `grep -rn '"frozen"'` finds every place fitted weights are used.
FROZEN = "frozen"


def frozen_weights() -> dict:
    """The 2026-08-17 freeze: per-horizon PF share rising 0.4->0.8 (analogue
    wins short-range, dynamics win long-range; LOSO 0.717), with 12 per-state
    overrides that each cleared a 2-of-3 held-out-season gain gate. A local
    state file overrides the shipped freeze; re-freezing is an explicit,
    dated act.

    NOT the shipped blend: this table is retained so the fitted alternative
    can be scored against, and it lost. Measured on the three-season seal,
    52 jurisdictions, 15460 cells: applying this table scores 0.6958 pooled
    against the unfitted 50/50's 0.6781 (before the 2021-22 donor exclusion
    the same comparison was 0.7107 against 0.7039). The fitted figure is the
    flattering one, since the table was fitted using the seasons it is
    scored on; the leave-one-season-out fit recorded at the freeze was
    0.717, measured on the pre-exclusion donor pool and not re-derivable,
    because no code for that fit survives. Fitted loses either way.
    vincentize() uses this table only when asked by name."""
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


def vincentize(members: dict, weights: dict | str | None = None,
               location_fips: str = "") -> dict:
    """members: {name: horizon->quantiles}. `weights` selects the blend:

    * None -- THE DEFAULT and the shipped forecast: equal weights over the
      members present at each horizon, no fitting anywhere. A member missing
      a horizon leaves the other at weight 1.
    * FROZEN ("frozen"), or a frozen-format dict carrying "global" /
      "per_state": the LOSO-fitted per-horizon and per-state PF share, for
      the {"pf", "analogue"} pair. Any other member set falls back to equal
      weights, because the frozen table knows nothing about it. Fitted
      weights must be named; omitting the argument never selects them.
    * {member_name: weight}: N-member quantile average, weights renormalized
      over the members present at each horizon.
    """
    if isinstance(weights, str):
        if weights != FROZEN:
            raise ValueError(
                f"unknown weights request {weights!r}: pass None for the "
                f"shipped equal-weight blend, ensemble.FROZEN for the "
                f"LOSO-fitted table, or a {{member: weight}} dict")
        weights = frozen_weights()
    frozen_table = weights is not None and (
        "global" in weights or "per_state" in weights)
    out = {}
    for h in ("1", "2", "3", "4"):
        have = {m: q[h] for m, q in members.items() if h in q}
        if not have:
            continue
        if frozen_table and set(have) == {"pf", "analogue"}:
            share = pf_share(weights, int(h) - 1, location_fips)  # keys 0..3
            levels = sorted(set(have["pf"]) & set(have["analogue"]))
            out[h] = {float(L): float(share * have["pf"][L]
                                      + (1 - share) * have["analogue"][L])
                      for L in levels}
            continue
        # Everything else is a weighted quantile average. `weights` None (the
        # default) and a frozen table that does not cover this member set both
        # land on equal weights rather than silently picking an arbitrary
        # member.
        named = (equal_weights(have) if weights is None or frozen_table
                 else {m: float(weights.get(m, 0.0)) for m in have})
        tot = sum(named.values())
        if tot <= 0:                           # nothing weighted -> uniform
            named, tot = equal_weights(have), 1.0
        # blend over the levels the members actually share: the live run
        # carries all 23 FluSight levels, a re-blend from stored results
        # carries the display set -- both must work (KeyError 0.01 otherwise)
        levels = sorted(set.intersection(*(set(q) for q in have.values())))
        out[h] = {float(L): float(sum(named[m] * have[m][L]
                                      for m in have) / tot)
                  for L in levels}
    return out
