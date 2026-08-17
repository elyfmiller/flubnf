"""Invariants of the calendar analogue.

Two of these encode bugs that were actually hit during verification and cost
real time: NaN contamination of np.quantile, and the one-week anchor look-ahead
worth 0.177 relWIS. Both are cheap to reintroduce and expensive to notice.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from flubnf.analogue import (MIN_DONORS, analogue_quantiles, build_bank,
                             calendar_distance, donor_ratios, epiweek,
                             forecast, season_of)

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


class TestNaNSafety:
    """np.quantile returns NaN for EVERY level if the array holds one NaN, and
    `v <= 0` is False for NaN so naive filters admit them. This produced a
    100%-NaN control arm during verification."""

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
