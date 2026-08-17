"""Invariants of the automatic-parameterisation loop.

The rules here are the ones that cost real WIS when they were absent, so each
test names the measurement that motivates it.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf.autoparam import (CIRCULAR, FLOOR_AT_ZERO, PHYSICAL, Diagnosis,
                              RoundResult, choose, diagnose, is_pinned,
                              next_priors)
from flubnf.sihrs_fit import FITTED_PRIORS


class TestIsPinned:
    def test_mass_at_lower_bound(self):
        assert is_pinned(np.full(100, 0.0005), 0.0, 1.0)

    def test_mass_at_upper_bound(self):
        assert is_pinned(np.full(100, 0.9995), 0.0, 1.0)

    def test_interior_posterior_is_not_pinned(self):
        assert not is_pinned(np.random.default_rng(0).normal(0.5, 0.05, 500),
                             0.0, 1.0)

    def test_empty_and_degenerate_inputs(self):
        assert not is_pinned(np.array([]), 0.0, 1.0)
        assert not is_pinned(np.full(10, 0.5), 1.0, 1.0)   # zero-width prior


class TestDiagnoseClassifies:
    def test_circular_phases_are_ignored(self):
        """phi=0 and phi=52 are the same point; a boundary pin is a wrap."""
        d = diagnose(["phi1__FREE", "phi2__FREE"],
                     {"phi1__FREE": 0.1, "phi2__FREE": 25.9})
        assert d.circular == ("phi1__FREE", "phi2__FREE")
        assert not d.movable and not d.drop

    def test_amplitude_collapsed_to_zero_is_dropped_not_widened(self):
        """49% of pins are eps1/eps2 at 0 -- unwidenable, so remove them."""
        d = diagnose(["eps1__FREE"], {"eps1__FREE": 0.0})
        assert "eps1__FREE" in d.drop
        assert "eps1__FREE" not in d.movable

    def test_mult_at_physical_ceiling_is_blocked(self):
        """Ascertainment cannot exceed 1.0 -- that is a rho problem, not bounds."""
        lo, hi = FITTED_PRIORS["mult__FREE"]
        d = diagnose(["mult__FREE"], {"mult__FREE": hi})
        assert "mult__FREE" in d.blocked
        assert "mult__FREE" not in d.movable

    def test_parameter_pushing_outward_is_widened(self):
        lo, hi = FITTED_PRIORS["Reff__FREE"]
        d = diagnose(["Reff__FREE"], {"Reff__FREE": hi - 1e-6})
        assert "Reff__FREE" in d.movable
        nlo, nhi = d.movable["Reff__FREE"]
        assert nhi > hi and nlo < hi

    def test_widening_never_crosses_a_physical_limit(self):
        for p, (plo, phi) in PHYSICAL.items():
            lo, hi = FITTED_PRIORS[p]
            for med in (lo, hi):
                d = diagnose([p], {p: med})
                if p in d.movable:
                    nlo, nhi = d.movable[p]
                    assert nlo >= plo - 1e-12, f"{p} widened below physical floor"
                    assert nhi <= phi + 1e-12, f"{p} widened above physical ceiling"

    def test_unknown_or_missing_median_is_skipped(self):
        assert not diagnose(["nonsense__FREE"], {}).changed
        assert not diagnose(["Reff__FREE"], {}).changed
        assert not diagnose(["Reff__FREE"], {"Reff__FREE": np.nan}).changed


class TestNextPriors:
    def test_drops_are_removed_and_widening_applied(self):
        d = diagnose(["eps1__FREE", "Reff__FREE"],
                     {"eps1__FREE": 0.0,
                      "Reff__FREE": FITTED_PRIORS["Reff__FREE"][1]})
        nxt = next_priors(d)
        assert "eps1__FREE" not in nxt
        assert nxt["Reff__FREE"] != FITTED_PRIORS["Reff__FREE"]

    def test_untouched_parameters_are_preserved_exactly(self):
        d = diagnose(["Reff__FREE"], {"Reff__FREE": FITTED_PRIORS["Reff__FREE"][1]})
        nxt = next_priors(d)
        for k, v in FITTED_PRIORS.items():
            if k != "Reff__FREE":
                assert nxt[k] == v

    def test_no_diagnosis_is_a_no_op(self):
        assert next_priors(Diagnosis()) == dict(FITTED_PRIORS)


class TestChoose:
    """Measured: when pins did NOT clear, the refit was 20% WORSE on WIS.
    So 'always take the newer fit' is wrong and must be guarded."""

    def test_refit_that_clears_pins_is_kept(self):
        assert choose(RoundResult(100.0, 3), RoundResult(100.0, 1)) == "second"

    def test_refit_that_fits_materially_worse_is_rejected(self):
        assert choose(RoundResult(100.0, 3), RoundResult(130.0, 0)) == "first"

    def test_small_objective_regression_is_tolerated_if_pins_clear(self):
        assert choose(RoundResult(100.0, 3), RoundResult(101.0, 0)) == "second"

    def test_more_pins_after_refit_loses(self):
        assert choose(RoundResult(100.0, 1), RoundResult(100.0, 3)) == "first"

    def test_failed_round_never_wins(self):
        assert choose(RoundResult(100.0, 3), RoundResult(1.0, 0, ok=False)) == "first"
        assert choose(RoundResult(1.0, 0, ok=False), RoundResult(100.0, 3)) == "second"

    def test_tie_breaks_on_objective(self):
        assert choose(RoundResult(100.0, 2), RoundResult(90.0, 2)) == "second"
        assert choose(RoundResult(90.0, 2), RoundResult(100.0, 2)) == "first"

    def test_choice_uses_no_outcome_information(self):
        """RoundResult must not carry WIS or actuals -- selection would be circular."""
        fields = set(RoundResult.__dataclass_fields__)
        assert fields == {"objective", "n_pinned", "ok", "end_ratio"}, (
            "RoundResult gained a field; every field must be knowable BEFORE "
            "the observation arrives (no WIS, no actuals)")

    def test_origin_miss_is_symmetric_and_zero_at_one(self):
        assert RoundResult(1.0, 0, end_ratio=1.0).origin_miss == pytest.approx(0.0)
        over = RoundResult(1.0, 0, end_ratio=2.0).origin_miss
        under = RoundResult(1.0, 0, end_ratio=0.5).origin_miss
        assert over == pytest.approx(under)

    def test_origin_miss_handles_degenerate_end_ratio(self):
        assert RoundResult(1.0, 0, end_ratio=0.0).origin_miss == float("inf")
        assert RoundResult(1.0, 0).origin_miss == float("inf")

    def test_refit_landing_further_from_the_data_is_rejected(self):
        """Even if it clears pins -- the +20% regression case."""
        first = RoundResult(100.0, 3, end_ratio=1.00)
        second = RoundResult(100.0, 0, end_ratio=0.40)   # lands 60% low
        assert choose(first, second) == "first"

    def test_refit_landing_closer_wins_even_with_more_pins(self):
        first = RoundResult(100.0, 0, end_ratio=0.30)
        second = RoundResult(100.0, 2, end_ratio=0.98)
        assert choose(first, second) == "second"
