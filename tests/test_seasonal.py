"""The Cartesian seasonal reparameterization must change coordinates ONLY.

If it changes the model, every comparison against the completed sweep becomes
meaningless -- and the whole point is that it is the SAME model in coordinates
an adaptive Metropolis sampler can actually traverse.
"""
from __future__ import annotations

import numpy as np
import pytest

from flubnf.seasonal import (ANNUAL_PERIOD, SEMIANNUAL_PERIOD, circular_rhat,
                             seasonal_term, summarize_phase, to_cartesian,
                             to_polar)
from flubnf.sihrs_fit import CART_PRIORS, FITTED_PRIORS


class TestIdentity:
    @pytest.mark.parametrize("eps,phi", [(0.35, 4.0), (0.8, 26.0), (0.05, 51.0),
                                         (1.0, 0.0), (0.5, 51.99)])
    def test_cartesian_reproduces_the_polar_harmonic_exactly(self, eps, phi):
        """The claim the entire change rests on."""
        t = np.arange(0, 60, 0.25)
        a, b = to_cartesian(eps, phi)
        polar = eps * np.cos(2 * np.pi * (t - phi) / ANNUAL_PERIOD)
        assert np.allclose(seasonal_term(t, a, b), polar, atol=1e-12)

    def test_identity_holds_across_random_parameters(self):
        rng = np.random.default_rng(0)
        t = np.arange(0, 104, 0.5)
        for _ in range(300):
            eps, phi = rng.uniform(0, 1.5), rng.uniform(0, 52)
            a, b = to_cartesian(eps, phi)
            polar = eps * np.cos(2 * np.pi * (t - phi) / ANNUAL_PERIOD)
            assert np.abs(seasonal_term(t, a, b) - polar).max() < 1e-11

    def test_semiannual_period_is_handled(self):
        t = np.arange(0, 60, 0.25)
        eps, phi = 0.3, 7.0
        a, b = to_cartesian(eps, phi, SEMIANNUAL_PERIOD)
        polar = eps * np.cos(2 * np.pi * (t - phi) / SEMIANNUAL_PERIOD)
        assert np.allclose(seasonal_term(t, a, b, SEMIANNUAL_PERIOD), polar, atol=1e-12)

    def test_round_trip(self):
        rng = np.random.default_rng(1)
        for _ in range(200):
            eps, phi = rng.uniform(1e-6, 1.5), rng.uniform(0, 52)
            e2, p2 = to_polar(*to_cartesian(eps, phi))
            assert e2 == pytest.approx(eps, rel=1e-9)
            assert p2 == pytest.approx(phi, abs=1e-7)

    def test_phase_wraps_into_range(self):
        for phi in (-3.0, 55.0, 104.0):
            _, p = to_polar(*to_cartesian(0.4, phi))
            assert 0.0 <= p < ANNUAL_PERIOD
            assert np.cos(2 * np.pi * p / 52) == pytest.approx(
                np.cos(2 * np.pi * phi / 52), abs=1e-9)


class TestOriginIsRegular:
    """The funnel: in polar coordinates eps->0 leaves phi undefined, and 46% of
    fits sit there. In Cartesian the origin is an ordinary interior point."""

    def test_zero_amplitude_is_representable_without_a_phase(self):
        t = np.arange(0, 52)
        assert np.allclose(seasonal_term(t, 0.0, 0.0), 0.0)

    def test_passing_through_the_origin_is_continuous(self):
        """A chain crossing the origin moves smoothly, which is the low-barrier
        path between phase modes that polar coordinates lack."""
        t = np.arange(0, 52)
        prev, path = None, np.linspace(-0.4, 0.4, 41)
        for a in path:
            cur = seasonal_term(t, a, 0.02)
            if prev is not None:
                assert np.abs(cur - prev).max() < 0.05
            prev = cur

    def test_phase_flips_but_the_harmonic_does_not_jump(self):
        """Crossing the origin flips the REPORTED phase by ~26 weeks; the
        underlying function is continuous. Summaries must convert per-draw."""
        _, p_before = to_polar(-0.001, 0.0)
        _, p_after = to_polar(+0.001, 0.0)
        assert abs(p_before - p_after) > 20
        t = np.arange(0, 52)
        assert np.abs(seasonal_term(t, -0.001, 0.0)
                      - seasonal_term(t, 0.001, 0.0)).max() < 0.01


class TestCircularSummaries:
    def test_linear_mean_of_wrapped_phases_is_wrong(self):
        """51 and 1 are two weeks apart, not 25 -- the reason summarize_phase
        exists at all."""
        phi = np.array([51.0, 51.5, 0.5, 1.0])
        assert phi.mean() == pytest.approx(26.0)
        s = summarize_phase(phi)
        assert s["mean"] > 51 or s["mean"] < 1

    def test_concentration_detects_an_undetermined_phase(self):
        rng = np.random.default_rng(2)
        tight = summarize_phase(rng.normal(20, 0.5, 2000) % 52)
        flat = summarize_phase(rng.uniform(0, 52, 2000))
        assert tight["R"] > 0.9
        assert flat["R"] < 0.1

    def test_circular_rhat_is_lower_than_linear_for_wrapped_chains(self):
        """Two chains at opposite ends of the wrap are nearly the same phase.
        Measured on a real fit: linear 127.2 vs circular 64.3."""
        rng = np.random.default_rng(3)
        chains = [rng.normal(51.5, 0.3, 500) % 52, rng.normal(0.5, 0.3, 500) % 52]
        lin_n = min(len(c) for c in chains)
        W = np.mean([c.var(ddof=1) for c in chains])
        B = lin_n * np.var([c.mean() for c in chains], ddof=1)
        linear = np.sqrt((((lin_n - 1) / lin_n) * W + B / lin_n) / W)
        assert circular_rhat(chains) < linear

    def test_circular_rhat_still_flags_genuine_disagreement(self):
        """It must not explain away real multimodality -- the raw chains sat at
        1.2 / 17.3 / 31.6 / 44.8 and circular R-hat was still 64."""
        rng = np.random.default_rng(4)
        chains = [rng.normal(m, 0.3, 500) % 52 for m in (1.2, 17.3, 31.6, 44.8)]
        assert circular_rhat(chains) > 5.0

    def test_too_few_chains_returns_nan(self):
        assert np.isnan(circular_rhat([np.linspace(0, 52, 500)]))


class TestPriorsMatchTheTemplate:
    def test_same_parameter_count(self):
        assert len(CART_PRIORS) == len(FITTED_PRIORS)

    def test_shared_parameters_are_untouched(self):
        for k in ("Reff__FREE", "mult__FREE", "impr__FREE", "r__FREE"):
            assert CART_PRIORS[k] == FITTED_PRIORS[k]

    def test_polar_parameters_are_gone(self):
        for k in ("eps1__FREE", "phi1__FREE", "eps2__FREE", "phi2__FREE"):
            assert k not in CART_PRIORS

    def test_boxes_are_signed_and_symmetric(self):
        """Signed is the point: an eps>=0 floor is a boundary the sampler
        piles against, and it is what makes the phase undefined."""
        for k in ("a1__FREE", "b1__FREE", "a2__FREE", "b2__FREE"):
            lo, hi = CART_PRIORS[k]
            assert lo < 0 < hi and lo == -hi

    def test_reachable_amplitude_covers_the_old_ceiling(self):
        a_hi = CART_PRIORS["a1__FREE"][1]
        b_hi = CART_PRIORS["b1__FREE"][1]
        assert np.hypot(a_hi, 0.0) >= FITTED_PRIORS["eps1__FREE"][1]
        assert np.hypot(a_hi, b_hi) <= np.sqrt(2) * FITTED_PRIORS["eps1__FREE"][1] + 1e-9

    def test_ab_are_not_log_scaled(self):
        """loguniform_var requires lo > 0; a/b are signed."""
        from flubnf.sihrs_fit import LOG_SCALE_VARS
        for k in ("a1__FREE", "b1__FREE", "a2__FREE", "b2__FREE"):
            assert k not in LOG_SCALE_VARS


class TestTemplateAndConf:
    def test_template_declares_exactly_the_fitted_vars(self):
        from pathlib import Path
        import re
        t = (Path(__file__).resolve().parent.parent
             / "flubnf" / "templates" / "SIHRS_pop_cart.bngl").read_text()
        declared = set(re.findall(r"(\w+__FREE)", t))
        assert declared == set(CART_PRIORS), (
            f"template/prior mismatch: {declared ^ set(CART_PRIORS)}")

    def test_template_has_no_polar_leftovers(self):
        from pathlib import Path
        t = (Path(__file__).resolve().parent.parent
             / "flubnf" / "templates" / "SIHRS_pop_cart.bngl").read_text()
        body = t.split("begin parameters", 1)[1]
        for bad in ("eps1__FREE", "phi1__FREE", "eps2__FREE", "phi2__FREE"):
            assert bad not in body

    def test_conf_emits_the_cartesian_priors(self, tmp_path):
        import numpy as np
        from flubnf.sihrs_fit import StateSetup, write_conf
        s = StateSetup(state="T", fips="01", population=5_000_000, gamma=2.188,
                       rho=0.02, rhomult=1e-3, gammaH=1.17, omega=0.019, s0=0.85,
                       i0=2e-4, attack_rate=0.18, n_obs=5,
                       observed=np.array([1.0, 2, 3, 4, 5]))
        txt = write_conf(s, model=tmp_path / "m", exp=tmp_path / "e",
                         out_dir=tmp_path / "o", conf_path=tmp_path / "c.conf",
                         bng_command="x", priors=CART_PRIORS).read_text()
        for k in CART_PRIORS:
            assert k in txt
        for k in ("eps1__FREE", "phi1__FREE"):
            assert k not in txt

    def test_default_conf_is_unchanged(self, tmp_path):
        """Omitting `priors` must still produce the polar config, or the
        running sweep/tau comparisons silently change."""
        import numpy as np
        from flubnf.sihrs_fit import StateSetup, write_conf
        s = StateSetup(state="T", fips="01", population=5_000_000, gamma=2.188,
                       rho=0.02, rhomult=1e-3, gammaH=1.17, omega=0.019, s0=0.85,
                       i0=2e-4, attack_rate=0.18, n_obs=5,
                       observed=np.array([1.0, 2, 3, 4, 5]))
        txt = write_conf(s, model=tmp_path / "m", exp=tmp_path / "e",
                         out_dir=tmp_path / "o", conf_path=tmp_path / "c.conf",
                         bng_command="x").read_text()
        assert "eps1__FREE" in txt and "phi1__FREE" in txt
        assert "a1__FREE" not in txt
