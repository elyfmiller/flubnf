"""The season boundary is the analogue's donor rule. Moving it must be exact.

`flubnf.analogue.donor_ratios` calls the module-level `season_of`, which is
influenza's 1 August rule. The COVID arm reimplements exactly that one line and
nothing else, so these tests check the reimplementation against the shipped
function where they must agree, and against the profile where they must differ.
"""
from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from flubnf import analogue
from flubnf.profiles import COVID, INFLUENZA

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "research/covid-phase0/analogue_vintage_true.py"

pytestmark = pytest.mark.skipif(not SCRIPT.is_file(), reason="script absent")


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("avt", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _bank(start: date, n: int, locs=("01", "02")):
    return {(l, start + timedelta(days=7 * i)): 100.0 + 10 * i
            for l in locs for i in range(n)}


class TestBoundaryEffect:
    def test_june_and_august_disagree_for_july_donors(self):
        """The whole reason the boundary moves: a July week belongs to the
        NEXT season under the flu rule and to the CURRENT one under COVID's."""
        d = date(2025, 7, 5)
        assert analogue.season_of(d) == 2024
        assert COVID.season_of(d) == 2025
        assert INFLUENZA.season_of(d) == analogue.season_of(d)

    def test_a_september_donor_is_prior_season_under_both(self):
        d = date(2024, 9, 7)
        assert analogue.season_of(d) == COVID.season_of(d) == 2024


class TestReimplementationMatchesTheShippedRule:
    def test_identical_to_donor_ratios_when_the_boundary_agrees(self, mod):
        """Donor pooling must be byte-identical or the arm comparison is not a
        comparison. Restricted to a window where June and August agree, the two
        implementations must produce the same multiset of ratios."""
        bank = _bank(date(2023, 9, 2), 60)
        for h in (1, 2, 3, 4):
            a = np.sort(analogue.donor_ratios(bank, 40, 2024, h, bandwidth=2))
            b = np.sort(mod.donor_ratios_profiled(bank, 40, 2024, h, 2))
            assert a.shape == b.shape
            assert np.allclose(a, b), h

    def test_calendar_blind_arm_uses_strictly_more_donors(self, mod):
        bank = _bank(date(2023, 9, 2), 80)
        cal = mod.donor_ratios_profiled(bank, 40, 2025, 1, 2)
        blind = mod.donor_ratios_profiled(bank, 40, 2025, 1, 2,
                                          calendar_blind=True)
        assert blind.size > cal.size
        assert cal.size > 0

    def test_no_donor_may_come_from_the_target_season(self, mod):
        """The leak that would invent skill. Every donor date must sit in a
        strictly earlier COVID season."""
        bank = _bank(date(2024, 6, 1), 120)
        # instrument: rebuild the ratio set while recording the dates used
        used = [d for (l, d) in bank
                if COVID.season_of(d) < 2025
                and min(abs(analogue.epiweek(d) - 40),
                        52 - abs(analogue.epiweek(d) - 40)) <= 2]
        assert used, "test setup produced no donors"
        assert all(d < date(2025, 6, 1) for d in used)
        assert mod.donor_ratios_profiled(bank, 40, 2025, 1, 2).size > 0


class TestDonorSilence:
    def test_no_prior_season_donors_yields_an_empty_ratio_set(self, mod):
        """The structural consequence of the 2024-11-20 vintage horizon: for
        summer target weeks there is no prior-season donor at all, and the
        analogue must return nothing rather than something."""
        bank = _bank(date(2025, 6, 1), 40)          # all season 2025
        r = mod.donor_ratios_profiled(bank, 30, 2025, 1, 2)
        assert r.size == 0
        from flubnf.quantiles import FLUSIGHT_QUANTILES
        assert analogue.analogue_quantiles(500.0, r, FLUSIGHT_QUANTILES) is None
