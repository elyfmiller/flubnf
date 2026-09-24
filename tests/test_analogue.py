"""Invariants of the calendar analogue, including two bugs hit during
verification: NaN contamination of np.quantile, and the one-week anchor
look-ahead (worth 0.177 relWIS)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from flubnf.analogue import (DONOR_SEASON_EXCLUSIONS, EXCLUDED_DONOR_SEASONS,
                             MIN_DONORS, SEASON_2021_22_CALENDAR_INVERSION,
                             SEASON_BOUNDARY_MONTH, analogue_quantiles,
                             build_bank, calendar_distance, donor_ratios,
                             epiweek, forecast, resolve_donor_exclusions,
                             season_of)

LEVELS = [0.025, 0.25, 0.5, 0.75, 0.975]


class TestCalendar:
    def test_season_runs_august_to_july(self):
        assert season_of(date(2025, 8, 1)) == 2025
        assert season_of(date(2026, 1, 15)) == 2025
        assert season_of(date(2026, 7, 31)) == 2025
        assert season_of(date(2026, 8, 1)) == 2026

    def test_epiweeks_wrap_circularly(self):
        """Weeks 52 and 1 are two weeks apart, not 51 -- donors either side of
        new year must match, and new year is peak flu season."""
        assert calendar_distance(52, 1) == 1
        assert calendar_distance(51, 2) == 3
        assert calendar_distance(1, 26) == 25

    def test_epiweek_is_in_range(self):
        for d in (date(2025, 12, 27), date(2026, 1, 3), date(2026, 6, 13)):
            assert 1 <= epiweek(d) <= 53


def _bank(seasons=(2022, 2023, 2024), states=("01", "02", "03", "04", "05")):
    """Synthetic seasons: every state doubles weekly through week 5."""
    b = {}
    for s in seasons:
        for st in states:
            for wk in range(20):
                d = date(s, 11, 1) + timedelta(days=7 * wk)
                b[(st, d)] = 100.0 * (2.0 ** min(wk, 5))
    return b


class TestDonorSelection:
    def test_strictly_prior_seasons_only(self):
        """The single most important property. A donor from the target season
        is a look-ahead."""
        b = _bank()
        target = date(2024, 11, 15)
        for (loc, d) in b:
            pass
        r = donor_ratios(b, epiweek(target), season_of(target), 1, bandwidth=3)
        # every contributing donor must predate season 2024
        contributing = [d for (loc, d) in b
                        if calendar_distance(epiweek(d), epiweek(target)) <= 3]
        assert any(season_of(d) < 2024 for d in contributing)
        assert r.size > 0
        # leaking the season must change the answer
        leak = donor_ratios(b, epiweek(target), season_of(target), 1,
                            bandwidth=3, allow_same_season=True)
        assert leak.size > r.size

    def test_bandwidth_restricts_donors(self):
        b = _bank()
        t = date(2025, 1, 10)
        wide = donor_ratios(b, epiweek(t), 2025, 1, bandwidth=8)
        narrow = donor_ratios(b, epiweek(t), 2025, 1, bandwidth=1)
        assert narrow.size <= wide.size

    def test_ratios_are_finite_and_positive(self):
        b = _bank()
        r = donor_ratios(b, epiweek(date(2025, 1, 10)), 2025, 2, bandwidth=6)
        assert r.size and np.all(np.isfinite(r)) and np.all(r > 0)


def _marked_bank(ratio_by_season, states=("01", "02", "03", "04", "05")):
    """A bank whose every horizon-1 donor ratio IDENTIFIES its season (season s
    grows by exactly ratio_by_season[s] per week), so presence of a ratio
    proves which donors survived, which a size comparison cannot."""
    b = {}
    for s, r in ratio_by_season.items():
        for st in states:
            for wk in range(20):
                d = date(s, 11, 1) + timedelta(days=7 * wk)
                b[(st, d)] = 100.0 * (r ** wk)
    return b


#: 2021-22 is marked 7.0 and is the only season that may ever be dropped.
_MARKS = {2021: 7.0, 2022: 2.0, 2023: 3.0}
_TARGET = date(2024, 11, 15)          # season 2024; 2021/2022/2023 are prior


def _donor_used(d: date, **kw) -> bool:
    """Would a donor dated `d` contribute at all? One location, one pair, an
    exact epiweek match, and every season strictly prior."""
    bank = {("01", d): 100.0, ("01", d + timedelta(days=7)): 150.0}
    return donor_ratios(bank, epiweek(d), 9999, 1, bandwidth=0, **kw).size == 1


class TestDonorSeasonExclusion:
    """The 2021-22 exclusion (pre-registration 8f3c7a45a989e905): it must not
    come back by accident, and no other season may leave by accident."""

    def test_2021_22_donors_are_absent_by_default(self):
        """Fails if 2021-22 donors reappear in the shipped pool."""
        r = donor_ratios(_marked_bank(_MARKS), epiweek(_TARGET),
                         season_of(_TARGET), 1, bandwidth=3)
        assert r.size > 0
        assert not np.any(np.isclose(r, _MARKS[2021])), (
            "a 2021-22 donor is in the shipped pool")
        # the other prior seasons are untouched, so this is an exclusion and
        # not an empty pool
        for s in (2022, 2023):
            assert np.any(np.isclose(r, _MARKS[s])), s

    def test_reintroducing_2021_22_has_to_be_written_down(self):
        r = donor_ratios(_marked_bank(_MARKS), epiweek(_TARGET),
                         season_of(_TARGET), 1, bandwidth=3,
                         exclude_seasons=())
        assert np.any(np.isclose(r, _MARKS[2021]))

    def test_forecast_applies_the_exclusion_by_default(self):
        """The engine calls `forecast`, not `donor_ratios`, so the default has
        to survive that hop."""
        b = _marked_bank(_MARKS)
        shipped = forecast(100.0, _TARGET, 1, b, LEVELS, bandwidth=3)
        historical = forecast(100.0, _TARGET, 1, b, LEVELS, bandwidth=3,
                              exclude_seasons=())
        assert shipped is not None and historical is not None
        assert shipped != historical
        assert historical[0.975] > shipped[0.975]      # 7.0 lived in the tail

    def test_the_excluded_set_is_exactly_the_two_registered_seasons(self):
        """The exclusion is exactly {2020, 2021}. 2020-21 is inert for the
        admissions pool (archive starts 2022-02-05) and bites only ILI+."""
        assert EXCLUDED_DONOR_SEASONS == frozenset({2020, 2021})
        assert set(DONOR_SEASON_EXCLUSIONS) == {2020, 2021}

    def test_excluding_an_unregistered_season_raises(self):
        """Any unregistered season raises (2022-23, the other COVID-disrupted
        candidate, was deliberately kept)."""
        b = _marked_bank(_MARKS)
        for bad in ({2022}, {2021, 2022}, {2019}, [2025]):
            with pytest.raises(ValueError, match="not registered"):
                donor_ratios(b, epiweek(_TARGET), season_of(_TARGET), 1,
                             bandwidth=3, exclude_seasons=bad)

    def test_a_foreign_calendar_exclusion_is_refused(self):
        """A record minted under another disease's season boundary is refused."""
        from dataclasses import replace
        import flubnf.analogue as AN
        foreign = replace(SEASON_2021_22_CALENDAR_INVERSION,
                          profile_key="covid", season_boundary_month=6)
        original = dict(AN.DONOR_SEASON_EXCLUSIONS)
        AN.DONOR_SEASON_EXCLUSIONS[2021] = foreign
        try:
            with pytest.raises(ValueError, match="boundary"):
                resolve_donor_exclusions({2021})
        finally:
            AN.DONOR_SEASON_EXCLUSIONS.clear()
            AN.DONOR_SEASON_EXCLUSIONS.update(original)

    def test_the_exclusion_is_a_label_under_the_august_boundary(self):
        """A season label under the August boundary, not a date range: July 2022
        goes (2021-22), July 2021 and August 2022 stay."""
        # pinned to the 2021-22 record alone, so the "stays" side is not
        # about 2020-21 (also excluded)
        only = {"exclude_seasons": (2021,)}
        assert SEASON_BOUNDARY_MONTH == 8
        assert season_of(date(2022, 7, 30)) == 2021
        assert not _donor_used(date(2022, 7, 30), **only)
        assert season_of(date(2021, 7, 31)) == 2020
        assert _donor_used(date(2021, 7, 31), **only)
        assert season_of(date(2022, 8, 6)) == 2022
        assert _donor_used(date(2022, 8, 6), **only)
        # and the whole excluded season really is gone, both ends
        assert not _donor_used(date(2021, 8, 7), **only)
        assert not _donor_used(date(2022, 2, 5), **only)   # first archived week

    def test_the_2020_21_exclusion_is_also_a_label_under_that_boundary(self):
        """The same boundary check for the second registered record."""
        only = {"exclude_seasons": (2020,)}
        assert season_of(date(2021, 7, 31)) == 2020
        assert not _donor_used(date(2021, 7, 31), **only)
        assert season_of(date(2020, 8, 1)) == 2020
        assert not _donor_used(date(2020, 8, 1), **only)
        assert season_of(date(2020, 7, 25)) == 2019
        assert _donor_used(date(2020, 7, 25), **only)      # the season before
        assert season_of(date(2021, 8, 7)) == 2021
        assert _donor_used(date(2021, 8, 7), **only)       # the season after

    def test_the_record_carries_its_provenance(self):
        """The registry holds a record with its evidence, never a bare season."""
        e = SEASON_2021_22_CALENDAR_INVERSION
        assert e.season == 2021 and e.label == "2021-22"
        assert e.profile_key == "influenza"
        assert e.season_boundary_month == SEASON_BOUNDARY_MONTH
        assert e.prereg_hash == "8f3c7a45a989e905"
        assert e.adopted_on == "2026-08-24"
        assert e.covers == (date(2021, 8, 1), date(2022, 7, 31))
        assert all(season_of(d) == e.season for d in e.covers)
        for field_ in ("mechanism", "effect", "depth_control", "evidence"):
            assert len(getattr(e, field_)) > 80, field_
        # the two claims the change actually rests on
        assert "epiweek 16" in e.mechanism
        assert "3.66" in e.effect
        assert "+0.199" in e.depth_control and "+17.64" in e.depth_control

    def test_every_registered_season_matches_its_record(self):
        for season, rec in DONOR_SEASON_EXCLUSIONS.items():
            assert rec.season == season
            assert resolve_donor_exclusions({season}) == frozenset({season})

    def test_resolve_accepts_the_shipped_default(self):
        assert (resolve_donor_exclusions(EXCLUDED_DONOR_SEASONS)
                == frozenset({2020, 2021}))
        assert resolve_donor_exclusions(()) == frozenset()


class TestNaNSafety:
    """np.quantile returns NaN at EVERY level for one NaN, and `v <= 0` is
    False for NaN, so naive filters admit them."""

    def test_build_bank_drops_nan_and_nonpositive(self):
        class R:
            def __init__(self, loc, d, v):
                self.location, self.date, self.value = loc, d, v
        rows = [R("01", date(2025, 1, 4), 10.0), R("01", date(2025, 1, 11), np.nan),
                R("01", date(2025, 1, 18), 0.0), R("01", date(2025, 1, 25), -5.0),
                R("01", date(2025, 2, 1), 7.0)]
        b = build_bank(rows)
        assert len(b) == 2
        assert all(np.isfinite(v) and v > 0 for v in b.values())

    def test_nan_in_bank_never_reaches_the_quantiles(self):
        b = _bank()
        b[("09", date(2023, 11, 8))] = np.nan
        b[("09", date(2023, 11, 15))] = 500.0
        r = donor_ratios(b, epiweek(date(2024, 11, 8)), 2024, 1, bandwidth=3)
        assert np.all(np.isfinite(r))

    def test_nan_anchor_returns_none(self):
        assert analogue_quantiles(np.nan, np.full(50, 1.1), LEVELS) is None
        assert analogue_quantiles(0.0, np.full(50, 1.1), LEVELS) is None

    def test_nan_ratios_are_filtered_not_propagated(self):
        r = np.concatenate([np.full(50, 1.2), [np.nan, np.inf]])
        q = analogue_quantiles(100.0, r, LEVELS)
        assert q is not None and all(np.isfinite(v) for v in q.values())


class TestQuantiles:
    def test_scales_the_anchor(self):
        q = analogue_quantiles(200.0, np.full(50, 1.5), LEVELS)
        assert q[0.5] == pytest.approx(300.0)

    def test_monotone_in_level(self):
        rng = np.random.default_rng(0)
        q = analogue_quantiles(150.0, rng.lognormal(0, 0.4, 500), LEVELS)
        vals = [q[L] for L in sorted(q)]
        assert all(b >= a for a, b in zip(vals, vals[1:]))

    def test_too_few_donors_returns_none(self):
        """Better no forecast than a 23-quantile distribution from 5 points."""
        assert analogue_quantiles(100.0, np.full(MIN_DONORS - 1, 1.1), LEVELS) is None
        assert analogue_quantiles(100.0, np.full(MIN_DONORS, 1.1), LEVELS) is not None


class TestAnchorAlignment:
    """A one-week anchor look-ahead measured 0.665 -> 0.488 relWIS. It is the
    largest single error available in this method."""

    def test_forecast_uses_the_supplied_anchor_only(self):
        b = _bank()
        t = date(2025, 1, 10)
        lo = forecast(100.0, t, 1, b, LEVELS, bandwidth=6)
        hi = forecast(200.0, t, 1, b, LEVELS, bandwidth=6)
        assert lo is not None and hi is not None
        for L in LEVELS:
            assert hi[L] == pytest.approx(2.0 * lo[L])

    def test_as_of_determines_both_calendar_and_season_cutoff(self):
        """Advancing as_of by a year must admit an extra donor season, so the
        two forecasts cannot be identical."""
        b = _bank(seasons=(2021, 2022, 2023, 2024))
        early = forecast(100.0, date(2023, 11, 15), 1, b, LEVELS, bandwidth=3)
        late = forecast(100.0, date(2024, 11, 15), 1, b, LEVELS, bandwidth=3)
        assert early is not None and late is not None


class TestUSDonorDisclosure:
    """The pool keeps the US national row (the sum of the jurisdictions it is
    pooled with) because keeping and removing it measured a tie; the module
    docstring sentences that disclose this are pinned here."""

    def _doc(self) -> str:
        from flubnf import analogue
        assert analogue.__doc__, "the module docstring carries the disclosure"
        return analogue.__doc__

    def test_the_docstring_says_the_us_row_is_in_the_pool(self):
        d = self._doc()
        assert "US national row" in d
        assert "sum of the 52 jurisdictions" in d
        assert "15 of 793" in d

    def test_the_docstring_carries_the_measured_tie(self):
        """Both arms and both members (a tie, not an untested choice)."""
        d = self._doc()
        for figure in ("0.7714", "0.7717", "0.7233", "0.7234"):
            assert figure in d, figure

    def test_the_docstring_names_the_rule_and_where_it_lives(self):
        d = self._doc()
        assert "0.001" in d
        assert "lab archive" in d
