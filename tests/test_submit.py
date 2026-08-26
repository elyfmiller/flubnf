"""Tests for flubnf.submit (FluSight submission CSV builder)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from flubnf.config import FluBNFConfig
from flubnf.quantiles import FLUSIGHT_QUANTILES, QuantileForecast
from flubnf.submit import (BACKTEST_TO_FLUSIGHT_HORIZON,
                           StateForecast,
                           build_submission_dataframe)


def _make_qforecast(median_per_h: list[float]) -> QuantileForecast:
    """Synthesize a QuantileForecast with constant spread per horizon."""
    n_q = len(FLUSIGHT_QUANTILES)
    n_h = len(median_per_h)
    q_arr = np.zeros((n_q, n_h))
    for j, med in enumerate(median_per_h):
        for i, q in enumerate(FLUSIGHT_QUANTILES):
            # symmetric, ramp from -50..+50 around median.
            q_arr[i, j] = med + (q - 0.5) * 100
    return QuantileForecast(
        horizons=(1, 2, 3, 4),
        quantile_levels=tuple(FLUSIGHT_QUANTILES),
        quantiles=q_arr,
        point=np.array(median_per_h),
    )


class TestSubmissionDataframe:
    def test_basic_shape(self):
        cfg = FluBNFConfig.load()
        sf = [StateForecast(state="Alabama",
                            forecast=_make_qforecast([100, 110, 120, 130]))]
        df = build_submission_dataframe(
            sf, reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=False,
        )
        # 4 horizons × 23 quantiles = 92 rows.
        assert len(df) == 92
        assert set(df["horizon"]) == {0, 1, 2, 3}
        assert set(df["output_type"]) == {"quantile"}
        assert df["reference_date"].iloc[0] == "2026-01-03"

    def test_us_aggregate_sums_states(self):
        cfg = FluBNFConfig.load()
        # Two equal states -> US row is 2x.
        sf = [
            StateForecast(state="Alabama",
                          forecast=_make_qforecast([10, 10, 10, 10])),
            StateForecast(state="Arizona",
                          forecast=_make_qforecast([20, 20, 20, 20])),
        ]
        df = build_submission_dataframe(
            sf, reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=True,
        )
        us = df[df["location"] == "US"]
        assert not us.empty
        # For the median (q=0.5), US should be sum of state medians.
        us_med = us[us["output_type_id"] == 0.5]
        assert us_med["value"].iloc[0] == 30.0

    def test_negative_values_clipped(self):
        """Quantiles below 0 (numerical artifacts) must be clipped — FluSight
        rejects negative hospitalization predictions."""
        n_q = len(FLUSIGHT_QUANTILES)
        # All-negative quantiles.
        q_arr = -np.ones((n_q, 4)) * 5
        qf = QuantileForecast(
            horizons=(1, 2, 3, 4),
            quantile_levels=tuple(FLUSIGHT_QUANTILES),
            quantiles=q_arr,
            point=np.array([-5, -5, -5, -5]),
        )
        cfg = FluBNFConfig.load()
        df = build_submission_dataframe(
            [StateForecast(state="Alabama", forecast=qf)],
            reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=False,
        )
        assert (df["value"] >= 0).all()

    def test_horizon_mapping_matches_constant(self):
        """Backtest h=1 must land at FluSight h=0 (same calendar week)."""
        cfg = FluBNFConfig.load()
        sf = [StateForecast(state="Alabama",
                            forecast=_make_qforecast([7, 8, 9, 10]))]
        df = build_submission_dataframe(
            sf, reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=False,
        )
        h0 = df[df["horizon"] == 0]
        # Our backtest h=1 median was 7; FluSight h=0 should reflect that.
        h0_med = h0[h0["output_type_id"] == 0.5]
        assert h0_med["value"].iloc[0] == 7.0
        # target_end_date matches reference_date at h=0.
        assert h0["target_end_date"].iloc[0] == "2026-01-03"
        # h=1 -> +7 days.
        h1 = df[df["horizon"] == 1]
        assert h1["target_end_date"].iloc[0] == "2026-01-10"


class TestSubmissionIdentity:
    """The CLI weekly loop writes under THIS project's registered hub
    identity, and refuses to write a file that fails the hub's schema."""

    def test_default_name_is_the_registered_identity(self):
        """It used to default to "LosAlamos_NAU-CModel_Flu", which is not a
        placeholder but a different team, separately registered on the same
        hub. Every file the loop wrote was therefore named for somebody
        else's model. One definition now, shared with the console writer."""
        from app.core.submit import hub_model_id
        from flubnf.submit import DEFAULT_TEAM_MODEL
        assert DEFAULT_TEAM_MODEL == hub_model_id("pf") == "NAU_FluBNF-SIHRS"
        assert "LosAlamos" not in DEFAULT_TEAM_MODEL

    def test_file_is_named_for_the_registered_identity(self, tmp_path):
        from flubnf.submit import DEFAULT_TEAM_MODEL, write_submission
        cfg = FluBNFConfig.load()
        sf = [StateForecast(state="Alabama",
                            forecast=_make_qforecast([100, 110, 120, 130]))]
        df = build_submission_dataframe(
            sf, reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=False)
        out = write_submission(df, date(2026, 1, 3), tmp_path)
        assert out.name == f"2026-01-03-{DEFAULT_TEAM_MODEL}.csv"
        # flat in the workspace, where its five readers glob("*.csv")
        assert out.parent == tmp_path

    def test_a_file_that_fails_the_hub_schema_is_not_written(self, tmp_path):
        """strict defaults to True. This file is read back as truth by the
        calibration ingest and is named like a submission, so logging the
        errors and writing anyway is worse than failing loudly."""
        import pytest
        from flubnf.submit import write_submission
        cfg = FluBNFConfig.load()
        sf = [StateForecast(state="Alabama",
                            forecast=_make_qforecast([100, 110, 120, 130]))]
        df = build_submission_dataframe(
            sf, reference_date=date(2026, 1, 3), config=cfg,
            include_us_aggregate=False)
        partial = df[df["output_type_id"].isin([0.1, 0.5, 0.9])]
        with pytest.raises(ValueError, match="failed validation"):
            write_submission(partial, date(2026, 1, 3), tmp_path)
        assert not list(tmp_path.glob("*.csv"))
        # the escape hatch is still there, but has to be asked for
        p = write_submission(partial, date(2026, 1, 3), tmp_path, strict=False)
        assert p.is_file()
