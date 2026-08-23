"""A level shift must be found, attributed, and excluded -- in that order.

The scan alone cannot tell a fast epidemic from a changed instrument. The
attribution test can, because NHSN measures three pathogens on one form. These
tests pin both, and pin the recorded numbers against the live data so the
record cannot quietly go stale.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flubnf import covid_vintage as cv
from flubnf.profiles import COVID
from flubnf.reporting_breaks import (COVID_BREAKS, cross_pathogen_step,
                                     level_break_scan)


class TestScan:
    def test_a_clean_exponential_decline_produces_no_large_residual(self):
        """The point of the local-median subtraction: falling fast is not a
        break. A pure exponential must show a residual of zero everywhere."""
        v = 1000 * np.exp(-0.12 * np.arange(40))
        d = pd.date_range("2025-01-04", periods=40, freq="7D").astype(str)
        s = level_break_scan(d, v)
        assert max(abs(c.excess_log) for c in s) < 1e-9

    def test_an_injected_step_is_found_and_ranked_first(self):
        v = 1000 * np.exp(-0.12 * np.arange(40))
        v[20:] *= 0.6                       # a 40% level shift
        d = pd.date_range("2025-01-04", periods=40, freq="7D").astype(str)
        s = level_break_scan(d, v)
        assert s[0].week == str(d[20])[:10]
        assert s[0].excess_pct == pytest.approx(-0.40, abs=0.01)
        assert abs(s[1].excess_log) < 0.05 * abs(s[0].excess_log)

    def test_noise_alone_yields_no_seven_sigma_excursion(self):
        rng = np.random.default_rng(0)
        v = 1000 * np.exp(np.cumsum(rng.normal(0, 0.08, 90)))
        d = pd.date_range("2025-01-04", periods=90, freq="7D").astype(str)
        s = level_break_scan(d, v)
        assert abs(s[0].z) < 6.0

    def test_short_and_degenerate_series_return_empty(self):
        assert level_break_scan(["2025-01-04"], [1.0]) == []
        assert level_break_scan([], []) == []


class TestAttribution:
    @staticmethod
    def _frame(covid, flu, rsv, rep):
        return pd.DataFrame({"week": ["w0", "w1"], "c": covid, "f": flu,
                             "r": rsv, "rep": rep})

    def test_three_pathogens_stepping_together_is_the_instrument(self):
        out = cross_pathogen_step(
            self._frame([1000, 570], [2000, 1140], [1500, 870], [5000, 4950]),
            "w1", "w0", ["c", "f", "r"], reporting_col="rep")
        assert out["pathogens_agree"] and out["reporting_stable"]
        assert out["verdict"].startswith("INSTRUMENT")

    def test_one_pathogen_moving_alone_is_not_attributable(self):
        out = cross_pathogen_step(
            self._frame([1000, 570], [2000, 1950], [1500, 1480], [5000, 4950]),
            "w1", "w0", ["c", "f", "r"], reporting_col="rep")
        assert not out["pathogens_agree"]
        assert out["verdict"] == "NOT ATTRIBUTABLE from this test"

    def test_a_reporting_collapse_is_named_as_such_not_as_a_definition_change(self):
        """Different cause, different remedy: coverage can be corrected for,
        a case-definition change cannot."""
        out = cross_pathogen_step(
            self._frame([1000, 570], [2000, 1140], [1500, 870], [5000, 2900]),
            "w1", "w0", ["c", "f", "r"], reporting_col="rep")
        assert "COVERAGE" in out["verdict"]


class TestTheRecordedBreakMatchesLiveData:
    pytestmark = pytest.mark.skipif(not cv.TIMESERIES.is_file(),
                                    reason="CovidHub parquet not staged")

    def test_exactly_one_break_is_recorded(self):
        assert len(COVID_BREAKS) == 1
        b = COVID_BREAKS[0]
        assert b.last_clean_week == "2026-03-21"
        assert b.first_shifted_week == "2026-03-28"
        assert b.verdict.startswith("INSTRUMENT")

    def test_the_recorded_step_ratio_still_holds_in_the_parquet(self):
        if not cv.TIMESERIES.is_file():
            pytest.skip("CovidHub parquet not staged")
        df = cv.vintage_frame(cv.vintages()[-1])
        us = df[df["location"] == "US"].set_index("date")["value"]
        r = float(us["2026-03-28"] / us["2026-03-21"])
        assert r == pytest.approx(COVID_BREAKS[0].measured["covid_ratio"],
                                  rel=1e-6)

    def test_it_is_still_the_largest_excursion_in_the_record(self):
        if not cv.TIMESERIES.is_file():
            pytest.skip("CovidHub parquet not staged")
        df = cv.vintage_frame(cv.vintages()[-1])
        us = df[df["location"] == "US"].sort_values("date")
        s = level_break_scan(us["date"], us["value"])
        assert s[0].week == "2026-03-28"
        assert s[0].z < -7.0
        assert abs(s[0].excess_log) > 1.8 * abs(s[1].excess_log)

    def test_the_profile_and_the_record_agree(self):
        b, w = COVID_BREAKS[0], COVID.excluded_windows[0]
        assert (w.last_clean_week, w.first_shifted_week) == (
            b.last_clean_week, b.first_shifted_week)
