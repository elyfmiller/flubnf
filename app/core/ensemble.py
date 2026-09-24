"""PRODUCTION: reduces a sample-shaped member to its 23 quantiles; it blends
nothing (retro sidecar writer, playback, server).

Member quantiles from sample arrays: the one formula that reduces a
sample-shaped member (the PF's draws) to the 23-level FluSight grid, so a
served fan, a scored cell and a submission cannot disagree. (Historical name:
nothing here blends anything.)
"""
from __future__ import annotations

import numpy as np

from app.core import horizons as HZ
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL


def member_quantiles_from_samples(samples_by_h: dict) -> dict:
    """horizon -> {level: value} from raw sample arrays (the PF's shape).

    Canonical horizons only; the anchor under ORIGIN is not a forecast and
    is skipped."""
    out = {}
    for h in HZ.HORIZONS:
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = {float(L): float(np.quantile(s, L)) for L in QL}
    return out
