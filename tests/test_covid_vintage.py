"""The COVID vintage adapter must offer the same contract vintage_path does.

Same shape, same loud failure, same missingness policy. If any of those drift,
a COVID retrospective silently stops being vintage-true, which is the one defect
that cannot be detected downstream.
"""
from __future__ import annotations

import pandas as pd
import pytest

from flubnf import covid_vintage as cv

pytestmark = pytest.mark.skipif(not cv.TIMESERIES.is_file(),
                                reason="CovidHub time-series.parquet not staged")


@pytest.fixture(scope="module")
def vs():
    return cv.vintages()


class TestArchiveShape:
    def test_the_archive_is_the_size_reconnaissance_measured(self, vs):
        assert len(vs) == 84
        assert vs[0] == "2024-11-20"
        assert vs[-1] == "2026-08-19"

    def test_vintages_are_sorted_and_unique(self, vs):
        assert vs == sorted(vs)
        assert len(set(vs)) == len(vs)

    def test_horizon_constant_matches_the_archive(self, vs):
        assert cv.VINTAGE_HORIZON == vs[0]


class TestFrameContract:
    def test_columns_match_the_flusight_archive_exactly(self, vs):
        df = cv.vintage_frame(vs[-1])
        assert list(df.columns) == ["date", "location", "location_name", "value"]

    def test_locations_are_zero_padded_fips_plus_us(self, vs):
        df = cv.vintage_frame(vs[-1])
        assert df["location"].nunique() == 53
        assert "US" in set(df["location"])
        assert all(len(l) == 2 for l in df["location"])

    def test_values_are_numeric_and_nan_rows_are_dropped(self, vs):
        df = cv.vintage_frame(vs[-1])
        assert pd.api.types.is_numeric_dtype(df["value"])
        assert df["value"].notna().all()

    def test_location_names_resolve(self, vs):
        df = cv.vintage_frame(vs[-1])
        names = set(df["location_name"])
        assert "California" in names and "Texas" in names

    def test_data_edge_is_the_saturday_before_the_as_of(self, vs):
        """What a Wednesday forecaster would have seen. If this slips by a week
        the whole retrospective gains a free look-ahead -- on the analogue arm a
        one-week look-ahead was worth 0.177 relWIS."""
        for a in (vs[0], vs[len(vs) // 2], vs[-1]):
            edge = pd.Timestamp(cv.data_edge(a))
            asof = pd.Timestamp(a)
            assert 0 < (asof - edge).days <= 7, (a, str(edge))
            assert edge.day_name() == "Saturday"

    def test_a_later_vintage_knows_at_least_as_much(self, vs):
        a, b = vs[-8], vs[-1]
        assert pd.Timestamp(cv.data_edge(a)) < pd.Timestamp(cv.data_edge(b))


class TestLoudFailure:
    def test_missing_vintage_names_nearby_alternatives(self, vs):
        with pytest.raises(FileNotFoundError) as e:
            cv.vintage_frame("2026-01-01")          # a Thursday, never archived
        msg = str(e.value)
        assert "2026-01-01" in msg and "Nearby" in msg
        assert "2025-12" in msg or "2026-01" in msg

    def test_pre_horizon_dates_refuse_rather_than_fall_back(self):
        """Falling back to settled truth here is the silent lie the whole
        vintage discipline exists to prevent."""
        with pytest.raises(ValueError) as e:
            cv.vintage_frame("2024-01-03")
        assert "vintage horizon" in str(e.value)

    def test_unknown_target_lists_what_is_available(self):
        with pytest.raises(KeyError) as e:
            cv.vintage_frame("2026-08-19", target="wk inc flu hosp")
        assert "wk inc covid hosp" in str(e.value)


class TestMaterializedCsv:
    def test_csv_round_trips_and_is_reused(self, vs, tmp_path):
        p = cv.vintage_path(vs[-1], cache_dir=tmp_path)
        assert p.name == f"target-hospital-admissions_{vs[-1]}.csv"
        mtime = p.stat().st_mtime_ns
        again = cv.vintage_path(vs[-1], cache_dir=tmp_path)
        assert again == p and again.stat().st_mtime_ns == mtime
        df = pd.read_csv(p, dtype={"location": str})
        assert list(df.columns) == ["date", "location", "location_name", "value"]
        assert len(df) == len(cv.vintage_frame(vs[-1]))

    def test_no_partial_file_is_left_behind(self, vs, tmp_path):
        cv.vintage_path(vs[-1], cache_dir=tmp_path)
        assert not list(tmp_path.glob("*.part"))

    def test_resolve_state_reads_it_unchanged(self, vs, tmp_path):
        """The whole point of the CSV shape: no consumer changes."""
        from flubnf.covid_fit import resolve_covid_state
        from flubnf.settings import LOCATIONS
        if not LOCATIONS.is_file():
            pytest.skip("locations.csv not available")
        p = cv.vintage_path("2026-03-18", cache_dir=tmp_path)
        s = resolve_covid_state("California", truth_csv=p,
                                locations_csv=LOCATIONS,
                                season_start="2025-06-01", as_of="2026-03-18")
        assert s.n_obs > 30
        assert s.population > 30_000_000
        assert (s.times[1:] - s.times[:-1]).min() >= 1


class TestDonorSilenceIsRecorded:
    def test_the_silent_block_brackets_the_2025_summer_peak(self):
        """Epiweek 36 is week ending 2025-09-06, the larger of that year's two
        national waves. If the recorded block ever stops covering it, the
        finding has gone stale and the constant is lying."""
        assert 36 in cv.ANALOGUE_SILENT_EPIWEEKS_2025_26
        assert len(cv.ANALOGUE_SILENT_EPIWEEKS_2025_26) == \
            cv.ANALOGUE_SILENT_WEEKS_2025_26

    def test_it_is_a_contiguous_block(self):
        w = list(cv.ANALOGUE_SILENT_EPIWEEKS_2025_26)
        assert w == list(range(w[0], w[-1] + 1))

    def test_it_is_a_minority_of_the_season(self):
        assert cv.ANALOGUE_SILENT_WEEKS_2025_26 < cv.ANALOGUE_ASOF_WEEKS_2025_26


class TestBankRows:
    def test_bank_rows_key_on_dates(self, vs):
        from flubnf.analogue import build_bank
        bank = build_bank(cv.build_bank_rows(vs[-1]))
        assert len(bank) > 3000
        (loc, d), v = next(iter(bank.items()))
        assert hasattr(d, "year") and v > 0
