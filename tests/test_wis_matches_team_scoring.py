"""flubnf/wis.py must reproduce the scoring used for the team baseline.

Head-to-head numbers assume our WIS and the team's `wis` column use the SAME
formula (interval set, 1/(K+0.5), Bracher decomposition). Recomputing the
team's raw hub quantiles with our implementation against the pre-scored CSV
is exact (measured: max relative difference 0.0000% over 636 cells). Skips
when the hub clone or the scored CSV is absent.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flubnf.wis import wis

HUB = Path(os.environ.get("FLUSIGHT_HUB",
                          os.path.expanduser("~/Documents/GitHub/FluSight-forecast-hub")))
TEAM_DIR = HUB / "model-output" / "LosAlamos_NAU-CModel_Flu"
SCORED = (Path(__file__).resolve().parent.parent / "backtest_results"
          / "flusight_team_scored.csv")


def _pairs(limit_files: int = 3):
    """(our WIS, pre-scored WIS) for overlapping cells."""
    scored = pd.read_csv(SCORED, dtype={"location": str})
    scored["location"] = scored["location"].str.zfill(2)
    out = []
    for f in sorted(glob.glob(str(TEAM_DIR / "2026-01-*.csv")))[:limit_files]:
        sub = pd.read_csv(f, dtype={"location": str})
        sub["location"] = sub["location"].str.zfill(2)
        q = sub[sub.output_type == "quantile"].copy()
        if q.empty:
            continue
        q["output_type_id"] = pd.to_numeric(q.output_type_id, errors="coerce")
        ref = q.reference_date.iloc[0]
        for (loc, hz), g in q.groupby(["location", "horizon"]):
            row = scored[(scored.location == loc)
                         & (scored.reference_date == ref)
                         & (scored.horizon == hz)]
            if row.empty:
                continue
            qd = {float(r.output_type_id): float(r.value)
                  for r in g.itertuples() if np.isfinite(r.output_type_id)}
            if 0.5 not in qd:
                continue
            try:
                mine = wis(qd, float(row.iloc[0]["actual"])).wis
            except (KeyError, ValueError):
                continue
            out.append((mine, float(row.iloc[0]["wis"])))
    return out


@pytest.mark.skipif(not TEAM_DIR.is_dir() or not SCORED.is_file(),
                    reason="FluSight hub clone or scored baseline not present")
class TestWisMatchesTeamScoring:
    def test_enough_overlapping_cells_to_be_meaningful(self):
        assert len(_pairs()) >= 100

    def test_wis_is_numerically_identical(self):
        p = _pairs()
        mine = np.array([a for a, _ in p])
        theirs = np.array([b for _, b in p])
        rel = np.abs(mine - theirs) / np.maximum(theirs, 1e-9)
        assert rel.max() < 1e-4, (
            f"our WIS differs from the team's by up to {rel.max()*100:.4f}% -- "
            "the SIHRS-vs-team comparison would not be apples-to-apples")

    def test_not_trivially_passing_on_zeros(self):
        """Guard the guard: a set of all-zero scores would pass the check above."""
        theirs = np.array([b for _, b in _pairs()])
        assert np.median(theirs) > 0
        assert theirs.max() > 1.0
