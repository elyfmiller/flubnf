"""`donor_paths`: complete growth trajectories from the shared donor rule.

The function exists for a consumer (the mechanistic model) that needs the
next several weeks of growth as one trajectory rather than one horizon's
marginal. It must select exactly the donors `donor_ratios` selects, and the
refactor that made the rule shared must leave `donor_ratios` byte for byte
where it was, because the shipped Groundhog path runs through it.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

import numpy as np
import pytest

from flubnf import bank as bankmod
from flubnf.analogue import (DEFAULT_BANDWIDTH, EXCLUDED_DONOR_SEASONS,
                             MIN_DONORS, calendar_distance, donor_paths,
                             donor_ratios, epiweek, season_of)


def _bank(seasons=(2022, 2023, 2024), states=("01", "02", "03", "04", "05"),
          weeks=20):
    """Synthetic seasons on Saturdays, gapless, whose weekly growth depends
    on the season, the state and the week, so no two donors share a ratio
    and membership can be tested by value (a checker found the earlier
    fixture repeated every season bit for bit)."""
    b = {}
    for j, s in enumerate(seasons):
        d0 = date(s, 11, 1)
        d0 += timedelta(days=(5 - d0.weekday()) % 7)      # first Saturday
        for i, st in enumerate(states):
            v = 100.0 + i
            for wk in range(weeks):
                b[(st, d0 + timedelta(days=7 * wk))] = v
                v *= 1.0 + 0.02 * (i + 1) + 0.01 * wk + 0.003 * (j + 1)
    return b


TARGET = date(2024, 12, 6)           # epiweek 49, season 2024
EW, SEASON = epiweek(TARGET), season_of(TARGET)


class TestShape:
    def test_one_row_per_donor_and_length_columns(self):
        b = _bank()
        p = donor_paths(b, EW, SEASON, length=6)
        assert p.ndim == 2 and p.shape[1] == 6
        # equal, not just <=, because the fixture is gapless
        assert p.shape[0] == len(donor_ratios(b, EW, SEASON, 6))

    def test_no_two_donors_share_a_ratio_in_the_fixture(self):
        """The by-value membership tests below depend on this."""
        r = donor_ratios(_bank(), EW, SEASON, 4)
        assert r.size > 1 and len(set(r.tolist())) == r.size

    def test_empty_result_keeps_the_column_count(self):
        p = donor_paths({}, EW, SEASON, length=4)
        assert p.shape == (0, 4)
        assert p[:, 3].size == 0            # indexable without a special case

    def test_length_below_one_raises(self):
        with pytest.raises(ValueError, match="length"):
            donor_paths(_bank(), EW, SEASON, length=0)

    def test_with_keys_aligns_rows_and_keys(self):
        b = _bank()
        p, keys = donor_paths(b, EW, SEASON, length=3, with_keys=True)
        assert len(keys) == p.shape[0]
        for row, (loc, d) in zip(p, keys):
            expect = [b[(loc, d + timedelta(days=7 * k))] / b[(loc, d)]
                      for k in (1, 2, 3)]
            assert np.allclose(row, expect)


class TestAgreementWithDonorRatios:
    def test_length_one_is_donor_ratios_at_horizon_one(self):
        b = _bank()
        p = donor_paths(b, EW, SEASON, length=1)
        r = donor_ratios(b, EW, SEASON, 1)
        assert np.array_equal(p[:, 0], r)     # same donors, same order

    def test_every_column_is_a_subset_of_the_matching_horizon(self):
        b = _bank(weeks=8)                    # short seasons: paths thin out
        for h in (1, 2, 3, 4):
            col = sorted(donor_paths(b, EW, SEASON, length=4)[:, h - 1])
            full = sorted(donor_ratios(b, EW, SEASON, h))
            assert len(col) <= len(full)
            # multiset inclusion
            j = 0
            for x in col:
                while j < len(full) and full[j] < x:
                    j += 1
                assert j < len(full) and full[j] == x
                j += 1

    def test_a_gap_inside_the_path_drops_the_donor_but_not_the_ratio(self):
        """donor_ratios at horizon 4 needs only the week-4 cell; a path of
        length 4 needs weeks 1 to 4. Knock out one donor's week-3 cell: the
        ratio pool keeps that donor, the path pool drops it."""
        b = _bank()
        (loc, d) = next(k for k in b if season_of(k[1]) < SEASON
                        and calendar_distance(epiweek(k[1]), EW) == 0)
        want4 = b[(loc, d + timedelta(days=28))] / b[(loc, d)]
        assert np.sum(donor_ratios(b, EW, SEASON, 4) == want4) == 1   # unique
        del b[(loc, d + timedelta(days=21))]
        assert np.sum(donor_ratios(b, EW, SEASON, 4) == want4) == 1   # kept
        _, k2 = donor_paths(b, EW, SEASON, length=2, with_keys=True)
        _, k4 = donor_paths(b, EW, SEASON, length=4, with_keys=True)
        assert (loc, d) in k2 and (loc, d) not in k4


class TestSharedSelectionRule:
    def test_strictly_prior_seasons_only(self):
        b = _bank(seasons=(2022, 2023, 2024))
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True)
        assert keys and all(season_of(d) < SEASON for _, d in keys)

    def test_allow_same_season_admits_the_target_season(self):
        b = _bank(seasons=(2022, 2023, 2024))
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True,
                              allow_same_season=True)
        assert any(season_of(d) == SEASON for _, d in keys)

    def test_bandwidth_is_inclusive(self):
        b = _bank()
        for bw in (0, 1, 2):
            _, keys = donor_paths(b, EW, SEASON, length=1, bandwidth=bw,
                                  with_keys=True)
            dist = {calendar_distance(epiweek(d), EW) for _, d in keys}
            assert max(dist) == bw

    def test_registered_exclusions_apply_and_unregistered_ones_raise(self):
        b = _bank(seasons=(2020, 2021, 2022, 2023))
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True)
        assert {season_of(d) for _, d in keys} == {2022, 2023}
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True,
                              exclude_seasons=())
        assert {season_of(d) for _, d in keys} == {2020, 2021, 2022, 2023}
        with pytest.raises(ValueError, match="not registered"):
            donor_paths(b, EW, SEASON, length=2, exclude_seasons=(2022,))

    def test_non_finite_or_non_positive_future_values_drop_the_donor(self):
        b = _bank()
        (loc, d) = next(k for k in b if season_of(k[1]) < SEASON
                        and calendar_distance(epiweek(k[1]), EW) == 0)
        b[(loc, d + timedelta(days=14))] = float("nan")
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True)
        assert (loc, d) not in keys
        b[(loc, d + timedelta(days=14))] = 0.0
        _, keys = donor_paths(b, EW, SEASON, length=2, with_keys=True)
        assert (loc, d) not in keys
        _, keys = donor_paths(b, EW, SEASON, length=1, with_keys=True)
        assert (loc, d) in keys               # week 1 is intact

    def test_no_donor_floor_is_applied(self):
        b = _bank(seasons=(2023,), states=("01",))
        p = donor_paths(b, EW, SEASON, length=2)
        assert 0 < p.shape[0] < MIN_DONORS


class TestWeek53Seam:
    def test_future_values_cross_the_seam_by_date_arithmetic(self):
        """MMWR 2014 has 53 weeks; 2015-01-03 is epiweek 53. A target at
        epiweek 1 with bandwidth 1 admits it (distance 0.5), and its path
        must be read from the Saturdays 7, 14, 21 days later, not from any
        week label."""
        seam = date(2015, 1, 3)
        assert epiweek(seam) == 53
        b = {}
        for i in range(-3, 6):
            b[("x", seam + timedelta(days=7 * i))] = 10.0 * (1.5 ** i)
        target = date(2016, 1, 9)             # epiweek 1 of 2016, season 2015
        assert epiweek(target) == 1
        p, keys = donor_paths(b, epiweek(target), season_of(target), length=3,
                              bandwidth=1, with_keys=True)
        assert ("x", seam) in keys
        row = p[keys.index(("x", seam))]
        assert np.allclose(row, [1.5, 1.5 ** 2, 1.5 ** 3])


# Reference values captured from `donor_ratios` on the committed banks
# BEFORE the selection rule was factored out (2026-09-22, main 623610b).
# The pin is on the array bytes, so order and every value are held. A
# rebuilt bank legitimately changes these; when the digest moves, re-capture
# the pin in the same commit as the new bank.
_BANK_DIGESTS = {"flusurv": "06eff6a7", "iliplus": "f6ee2840"}
_RATIO_PINS = {
    ("flusurv", 2, 4, "default"): (1235, "36742c70a3332980"),
    ("flusurv", 53, 1, "default"): (981, "c0664a3bba6c3ea6"),
    ("iliplus", 2, 4, "default"): (1687, "38f1baab7cde5859"),
    ("iliplus", 18, 6, "none"): (1143, "dd41c607252fb6ce"),
}
# Complete-path counts on the same banks (target season 2026, default
# exclusions, default bandwidth), the figures docs/DONOR-BANKS.md quotes.
_PATH_PINS = {
    ("flusurv", 2, 6): 1192,
    ("flusurv", 14, 6): 142,
    ("iliplus", 2, 6): 1658,
    ("iliplus", 14, 6): 1099,
}


def _committed(stream):
    try:
        b, man = bankmod.read(stream)
    except (FileNotFoundError, ValueError) as e:     # pragma: no cover
        pytest.skip(f"committed {stream} bank unavailable: {e}")
    if not man["digest"].startswith(_BANK_DIGESTS[stream]):
        pytest.skip(f"{stream} bank rebuilt ({man['digest'][:8]}); "
                    f"re-capture the pins in tests/test_donor_paths.py")
    return b


class TestCommittedBanks:
    @pytest.mark.parametrize("stream,ew,h,excl", sorted(_RATIO_PINS))
    def test_donor_ratios_is_byte_identical_to_before_the_refactor(
            self, stream, ew, h, excl):
        b = _committed(stream)
        kw = {} if excl == "default" else {"exclude_seasons": ()}
        a = donor_ratios(b, ew, 2026, h, **kw)
        n, sha = _RATIO_PINS[(stream, ew, h, excl)]
        assert a.size == n
        assert hashlib.sha256(a.tobytes()).hexdigest()[:16] == sha

    @pytest.mark.parametrize("stream,ew,length", sorted(_PATH_PINS))
    def test_complete_path_counts_match_the_handoff(self, stream, ew, length):
        b = _committed(stream)
        p = donor_paths(b, ew, 2026, length=length)
        assert p.shape == (_PATH_PINS[(stream, ew, length)], length)
        assert np.all(np.isfinite(p)) and np.all(p > 0)

    def test_each_column_is_inside_the_matching_ratio_pool(self):
        b = _committed("flusurv")
        p = donor_paths(b, 2, 2026, length=4)
        for h in (1, 2, 3, 4):
            r = donor_ratios(b, 2, 2026, h)
            assert p.shape[0] <= r.size
            assert set(np.round(p[:, h - 1], 12)) <= set(np.round(r, 12))
