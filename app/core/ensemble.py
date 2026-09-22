"""Member quantiles from sample arrays. The one formula every surface
uses to reduce a sample-shaped member (the PF's draws) to the 23-level
FluSight grid, so a served fan, a scored cell and a written submission
cannot disagree about what a member forecast.

The blend that used to live here, vincentize() at equal unfitted weights,
was retired on 2026-09-22 with the equal-weight ensemble it produced
(LosAlamos_NAU-CModel_Flu, submitted through version 3.0). The two models
now ship as standalone submissions and nothing in the product computes a
blend; its history is docs/RELEASE-1.0.md. The fitted-weight table that
the retired path could be asked for by name never shipped and has no
reader now.
"""
from __future__ import annotations

import numpy as np

from app.core import horizons as HZ
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL


def member_quantiles_from_samples(samples_by_h: dict) -> dict:
    """horizon -> {level: value} from raw sample arrays (the PF's shape).

    Canonical horizons only (app.core.horizons). The anchor week rides
    along in the samples under ORIGIN and is deliberately not summarised
    here: it is not a forecast, is never submitted, and is never scored."""
    out = {}
    for h in HZ.HORIZONS:
        s = np.asarray(samples_by_h.get(h, []), float)
        s = s[np.isfinite(s)]
        if s.size:
            out[h] = {float(L): float(np.quantile(s, L)) for L in QL}
    return out
