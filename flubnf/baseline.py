"""The validated FluSight-baseline construction.

Every relWIS in this repository is a ratio whose denominator comes from
here, so this is load-bearing code, not analysis. It scores the hub's OWN
archived `FluSight-baseline` submissions with this package's WIS, rather
than rebuilding the baseline from truth: a hand-rolled reconstruction
scored about 40 percent easier than the real thing and was retired the day
it was calibrated (2026-08-17).

The function lived in `scripts/anchor_analysis.py`, the analysis that
validated it, and `app.core.scoring` reached it by loading that 217-line
script from a path at every call. That worked only from a source clone: a
pip install packages `flubnf*` and `app*` and no `scripts/`, so scoring
raised FileNotFoundError on any installed copy. Library code now lives in
the library; the analysis script imports it back, so the validated formula
still has exactly one definition.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .wis import wis

#: the hub's target name for weekly influenza hospital admissions
TARGET = "wk inc flu hosp"


def baseline_cells(dates, locs_needed, truth, hub: Path | None = None
                   ) -> pd.DataFrame:
    """Per-cell WIS of the CDC FluSight-baseline, for the given forecast
    dates and locations.

    `hub` defaults to `flubnf.settings.HUB`, the clone the rest of the
    package reads. Callers with their own hub resolution pass it explicitly
    rather than relying on an environment variable read at import time.

    Returns rows of (variant, location, asof, horizon, wis). A forecast date
    whose baseline file is absent contributes no rows, which is how
    early-season weeks (fewer than five history points, so the hub publishes
    no baseline) end up with no scored cells.
    """
    if hub is None:
        from .settings import HUB as _HUB
        hub = _HUB
    hub = Path(hub)
    rows = []
    for asof in dates:
        ref = (pd.Timestamp(asof) + timedelta(days=7)).date().isoformat()
        fp = hub / "model-output" / "FluSight-baseline" / f"{ref}-FluSight-baseline.csv"
        if not fp.is_file():
            continue
        d = pd.read_csv(fp, dtype={"location": str})
        if "target" not in d.columns:
            continue
        d = d[(d.output_type == "quantile") & (d.target == TARGET)]
        d["location"] = d["location"].str.zfill(2)
        d["output_type_id"] = pd.to_numeric(d.output_type_id, errors="coerce")
        d["target_end_date"] = pd.to_datetime(d.target_end_date)
        for (loc, hz, ted), g in d.groupby(["location", "horizon", "target_end_date"]):
            if hz < 0 or loc not in locs_needed:
                continue
            a = truth.get((loc, ted))
            if a is None:
                continue
            q = {float(x.output_type_id): float(x.value) for x in g.itertuples()
                 if np.isfinite(x.output_type_id)}
            if 0.5 not in q:
                continue
            try:
                rows.append({"variant": "FluSight-baseline", "location": loc,
                             "asof": asof, "horizon": int(hz), "wis": wis(q, a).wis})
            except (KeyError, ValueError):
                pass
    return pd.DataFrame(rows)
