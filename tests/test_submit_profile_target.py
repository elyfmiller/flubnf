"""The submission writer needs one string from the profile and nothing else.

The reconnaissance found CovidHub and FluSight byte-identical on quantile
levels, horizons, cadence, columns, file naming and the reference-date
arithmetic. If that is right, routing the profile's `target_name` through the
existing writer produces a valid CovidHub file with no other change. This test
is that claim, made checkable.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from flubnf.config import FluBNFConfig
from flubnf.profiles import COVID, INFLUENZA
from flubnf.quantiles import FLUSIGHT_QUANTILES, QuantileForecast
from flubnf.submit import StateForecast, build_submission_dataframe


def _forecast(medians):
    q = np.zeros((len(FLUSIGHT_QUANTILES), len(medians)))
    for j, med in enumerate(medians):
        for i, lev in enumerate(FLUSIGHT_QUANTILES):
            q[i, j] = med + (lev - 0.5) * 100
    return QuantileForecast(horizons=(1, 2, 3, 4),
                            quantile_levels=tuple(FLUSIGHT_QUANTILES),
                            quantiles=q, point=np.array(medians))


def _df(profile):
    cfg = FluBNFConfig.load()
    sf = [StateForecast(state="Alabama", forecast=_forecast([100, 110, 120, 130]))]
    return build_submission_dataframe(sf, reference_date=date(2026, 1, 3),
                                      config=cfg, target_name=profile.target_name,
                                      include_us_aggregate=False)


class TestOneStringIsTheWholeChange:
    def test_covid_target_string_reaches_every_row(self):
        assert set(_df(COVID)["target"]) == {"wk inc covid hosp"}

    def test_influenza_is_unchanged(self):
        assert set(_df(INFLUENZA)["target"]) == {"wk inc flu hosp"}

    def test_everything_else_is_identical_between_the_two(self):
        a, b = _df(INFLUENZA), _df(COVID)
        assert list(a.columns) == list(b.columns)
        assert len(a) == len(b)
        other = [c for c in a.columns if c != "target"]
        assert a[other].reset_index(drop=True).equals(
            b[other].reset_index(drop=True))

    def test_the_hub_columns_and_quantile_count_are_the_shared_ones(self):
        d = _df(COVID)
        assert set(d.columns) == {"reference_date", "target", "horizon",
                                  "target_end_date", "location", "output_type",
                                  "output_type_id", "value"}
        assert set(d["horizon"]) == {0, 1, 2, 3}
        assert d["output_type_id"].nunique() == 23

    def test_target_end_date_arithmetic_is_the_shared_one(self):
        d = _df(COVID)
        for h, expected in ((0, "2026-01-03"), (1, "2026-01-10"),
                            (2, "2026-01-17"), (3, "2026-01-24")):
            assert set(d[d["horizon"] == h]["target_end_date"]) == {expected}

    def test_profile_target_strings_match_the_hub_task_definitions(self):
        """Read off hub-config/tasks.json during reconnaissance. A typo here is
        a rejected submission, and the hub gives no partial credit."""
        assert COVID.target_name == "wk inc covid hosp"
        assert INFLUENZA.target_name == "wk inc flu hosp"
