"""Tests for the SIHRS mirror and the magnitude-anchor arithmetic.

The point of the anchor tests: the cold 2026-03-07 SIHRS run pinned `mult` at its
5.0 prior ceiling in 43/52 states and under-predicted admissions by ~30x. That was
read as "SIHRS needs more adaptive rounds". It is actually a closed-form scale
error in the anchor, and these tests pin the arithmetic so it cannot come back.

    H_weekly(t) = rho*gamma*I(t) * mult * scaled          (models/SIHRS.bngl)

With the shipped anchor `scaled = 5.5 * observed_peak`, matching an observed peak
P requires

    mult = P / (f * 5.5 * P) = 1 / (5.5 * f),     f = max_t[rho*gamma*I(t)]

which is INDEPENDENT OF P -- so every state needs the same out-of-range `mult`,
which is exactly why 43/52 pinned simultaneously rather than a few outliers.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf.simulate_sihrs import (NOMINAL, SIHRS_FREE, beta_of_t,
                                   peak_admission_fraction, scaled_anchor,
                                   simulate_sihrs)

SHIPPED_ANCHOR_FACTOR = 5.5    # priors/build_priors.py:46
MULT_PRIOR = (0.2, 5.0)        # priors/build_priors.py:42


class TestMirrorMatchesBnglStructure:
    def test_fractions_are_conserved(self):
        # S+I+H+R is closed; Hadm is a separate accumulator that counts I->H
        # events without consuming I.
        # NOTE the conserved total is 1 + I0, NOT 1: models/SIHRS.bngl seeds
        # `S() 1` and `I() I0` additively, so compartments are fractions of the
        # initial SUSCEPTIBLE pool and the initial infecteds sit on top of it.
        res = simulate_sihrs({})
        total = res.S + res.I + res.H + res.R
        assert np.allclose(total, 1.0 + NOMINAL["I0"], atol=1e-6)

    def test_waning_refills_susceptibles(self):
        # The second S in SIHRS: S must dip then recover.
        res = simulate_sihrs({})
        assert res.S.min() < 0.5
        assert res.S[-1] > res.S.min() + 0.05

    def test_no_waning_means_monotone_susceptibles(self):
        res = simulate_sihrs({"omega": 0.0})
        assert np.all(np.diff(res.S) <= 1e-9)

    def test_beta_is_positive_everywhere_by_construction(self):
        # exp() forcing cannot go non-positive, unlike an additive harmonic.
        ts = np.linspace(0, 52, 400)
        b = [beta_of_t(t, R0=1.3, gamma=2.33, eps1=0.9, phi1=4.0,
                       eps2=0.6, phi2=10.0) for t in ts]
        assert min(b) > 0.0

    def test_beta_is_seasonal_with_52_week_period(self):
        a = beta_of_t(10.0, R0=1.3, gamma=2.33, eps1=0.4, phi1=4.0)
        b = beta_of_t(62.0, R0=1.3, gamma=2.33, eps1=0.4, phi1=4.0)
        assert a == pytest.approx(b, rel=1e-9)

    def test_hweekly_is_admission_flux_not_census(self):
        # H_weekly must track the admission FLUX rho*gamma*I, never the census H.
        res = simulate_sihrs({})
        expected = NOMINAL["rho"] * NOMINAL["gamma"] * res.I
        assert np.allclose(res.H_weekly, expected, rtol=1e-9)
        # ...and it is not merely a rescaled census: no single constant maps H
        # onto H_weekly. (Their weekly-grid argmax CAN coincide, because
        # gammaH=1.17 is a sub-weekly discharge lag, so argmax is not the test.)
        live = res.H > 1e-12
        ratio = res.H_weekly[live] / res.H[live]
        assert ratio.std() > 1e-6 * max(abs(ratio.mean()), 1e-12)


class TestShippedAnchorCannotUnpinMult:
    """Falsification of `scaled = 5.5 * peak`."""

    def test_required_mult_is_independent_of_state_size(self):
        f = peak_admission_fraction()
        req = [P / (f * SHIPPED_ANCHOR_FACTOR * P) for P in (30, 501, 2151)]
        assert req[0] == pytest.approx(req[1]) == pytest.approx(req[2])

    def test_required_mult_is_far_above_the_prior_ceiling(self):
        f = peak_admission_fraction()
        required = 1.0 / (SHIPPED_ANCHOR_FACTOR * f)
        assert required > MULT_PRIOR[1], (
            f"required mult {required:.1f} should exceed the {MULT_PRIOR[1]} "
            "ceiling — this is the pinning mechanism"
        )
        # ~30x, which matches the documented "forecasts ~30x too low".
        assert 15.0 < required < 60.0

    def test_no_plausible_flu_ihr_rescues_the_shipped_anchor(self):
        # IHR (rho) for influenza is ~1-5%. Across that range and R0 1.2-2.0 the
        # shipped anchor always demands an out-of-prior mult.
        for rho in (0.01, 0.02, 0.05):
            for R0 in (1.2, 1.5, 2.0):
                f = peak_admission_fraction({"rho": rho, "R0": R0})
                required = 1.0 / (SHIPPED_ANCHOR_FACTOR * f)
                assert required > MULT_PRIOR[1], (
                    f"rho={rho} R0={R0}: required mult {required:.1f} "
                    "unexpectedly fits under the ceiling"
                )


class TestAnalyticAnchorUnpinsMult:
    def test_anchor_puts_mult_at_the_target(self):
        # Anchoring on the model's own peak admission fraction makes mult ~= 1.
        for P in (30.0, 501.0, 2151.0):
            s = scaled_anchor(P, target_mult=1.0)
            recovered = P / (s * peak_admission_fraction())
            assert recovered == pytest.approx(1.0, rel=1e-6)

    def test_resulting_mult_sits_inside_the_prior(self):
        s = scaled_anchor(501.0, target_mult=1.0)
        mult = 501.0 / (s * peak_admission_fraction())
        assert MULT_PRIOR[0] < mult < MULT_PRIOR[1]

    def test_anchor_scales_linearly_with_observed_peak(self):
        # Population/size enters analytically; no per-state hand tuning.
        assert (scaled_anchor(1000.0) / scaled_anchor(100.0)) == pytest.approx(10.0)

    def test_anchor_is_much_larger_than_the_shipped_one(self):
        P = 501.0
        assert scaled_anchor(P, target_mult=1.0) > 5.0 * SHIPPED_ANCHOR_FACTOR * P

    def test_zero_admission_model_is_rejected(self):
        with pytest.raises(ValueError):
            scaled_anchor(500.0, {"rho": 0.0})


def test_free_parameter_list_matches_the_bngl():
    # 11 __FREE params in models/SIHRS.bngl; I0 and scaled are fixed, not fitted.
    assert len(SIHRS_FREE) == 11
    assert "I0" not in SIHRS_FREE and "scaled" not in SIHRS_FREE


class TestPopulationParameterization:
    """templates/SIHRS_pop.bngl: absolute people, frequency-dependent infection,
    `mult` as a pure ascertainment fraction and NO magnitude anchor."""

    N_AL = 5_108_468

    def test_frequency_dependent_reduces_to_normalized_exactly(self):
        """The load-bearing claim: beta*S*I/N with S(0)=N*s0 reproduces the
        normalized model's per-capita dynamics, so R0/gamma/eps/phi priors
        transfer with no re-derivation."""
        frac = simulate_sihrs({})
        pop = simulate_sihrs({"N": self.N_AL, "s0": 1.0,
                              "i0": NOMINAL["I0"]})
        assert np.allclose(pop.S / self.N_AL, frac.S, rtol=1e-6)
        assert np.allclose(pop.I / self.N_AL, frac.I, rtol=1e-6)

    def test_population_is_conserved(self):
        res = simulate_sihrs({"N": self.N_AL, "s0": 0.5, "i0": 1e-4})
        total = res.S + res.I + res.H + res.R
        assert np.allclose(total, self.N_AL, rtol=1e-6)

    def test_pre_existing_immunity_is_representable(self):
        """s0 < 1 seeds immunes -- structurally impossible when S(0) == 1."""
        res = simulate_sihrs({"N": self.N_AL, "s0": 0.45, "i0": 1e-4})
        assert res.R[0] == pytest.approx(self.N_AL * (1 - 0.45 - 1e-4), rel=1e-9)
        # Less fuel => a smaller outbreak than a fully-susceptible population.
        full = simulate_sihrs({"N": self.N_AL, "s0": 1.0, "i0": 1e-4})
        assert res.I.max() < full.I.max()

    def test_mult_lands_inside_a_universal_prior(self):
        """Across the real 52-state population/peak range, the required
        ascertainment sits in one narrow dimensionless band -- the whole point."""
        f = peak_admission_fraction()
        # (population, observed season peak) for the extremes and the median-ish.
        cases = [(584_057, 58), (5_108_468, 501), (38_965_193, 2151),
                 (19_571_216, 3870), (30_503_301, 2831)]
        mults = [P / (f * N) for N, P in cases]
        assert all(0.002 < m < 0.10 for m in mults), mults
        assert max(mults) / min(mults) < 10.0        # one prior covers all

    def test_no_scaled_anchor_needed(self):
        # `mult` alone spans the observed magnitude; `scaled` stays neutral at 1.
        res = simulate_sihrs({"N": self.N_AL, "s0": 1.0, "i0": NOMINAL["I0"],
                              "mult": 0.01625})
        assert res.H_weekly.max() > 0
        # Peak lands near Alabama's real 501 without any anchor multiplier.
        assert 250 < res.H_weekly.max() < 1000

    def test_admissions_per_100k_is_a_usable_physical_check(self):
        """The check population buys you: the 52-state blowup cell was 77,231/wk
        in a 19.5M state = ~395 per 100k, vs a real peak of ~20."""
        N_NY = 19_571_216
        assert 3870 / N_NY * 1e5 < 50        # real NY peak: plausible
        assert 77_231 / N_NY * 1e5 > 300     # the blowup: absurd, and catchable
