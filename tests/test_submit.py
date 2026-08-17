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
