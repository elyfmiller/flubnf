"""Tests for flubnf.exp_files.

Uses the legacy CSV checked into NAU_Influenza/cleaned_csvs/092425_Hdata.csv
as ground truth, and compares the output to the legacy
NAU_Influenza/current_job/exp_files/<State>_flu.exp files to make sure the
refactor is behavior-compatible.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flubnf import exp_files
from tests.conftest import LEGACY_NAU


LEGACY_EXP_DIR = (
    (LEGACY_NAU / "current_job" / "exp_files") if LEGACY_NAU else None
)


@pytest.fixture
def written_exp(legacy_cdc_csv, tmp_workspace, config):
    return exp_files.generate_exp_files(
        legacy_cdc_csv, tmp_workspace, config,
        states=["Alabama", "Arizona", "California"],
    )


class TestGenerateExpFiles:
    def test_writes_one_per_state(self, written_exp, tmp_workspace):
        names = sorted(r.state for r in written_exp)
        assert names == ["Alabama", "Arizona", "California"]
        for r in written_exp:
            assert r.path.exists()
            assert r.path.suffix == ".exp"

    def test_header_and_columns(self, written_exp):
        for r in written_exp:
            df = pd.read_csv(r.path, sep="\t")
            assert list(df.columns) == ["#time", "H_weekly"]
            # #time should be 0..N-1
            assert (df["#time"].values == range(len(df))).all()

    def test_matches_legacy_output_when_available(self, written_exp):
        """If a hand-generated legacy .exp exists, the new one should match
        column-wise on the overlap (length may differ if season window
        differs)."""
        if LEGACY_EXP_DIR is None:
            pytest.skip("legacy NAU_Influenza/ tree not present")
        for r in written_exp:
            legacy = LEGACY_EXP_DIR / f"{r.state}_flu.exp"
            if not legacy.exists():
                continue
            legacy_df = pd.read_csv(legacy, sep="\t")
            new_df = pd.read_csv(r.path, sep="\t")
            # Compare the overlap.
            n = min(len(legacy_df), len(new_df))
            assert n > 0, f"empty .exp for {r.state}"
            # Values should match within float tolerance.
            assert (
                legacy_df["H_weekly"].iloc[:n].to_numpy()
                == pytest.approx(new_df["H_weekly"].iloc[:n].to_numpy(), rel=0, abs=0)
            )
