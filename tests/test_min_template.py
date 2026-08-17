"""The parsimonious template must drop exactly three parameters and nothing else.

Every removal is justified by a measurement (see the template header). What
these tests protect is that the change stays a PARAMETER-COUNT change and does
not silently become a model change -- the dynamics, the observable and every
retained parameter must be identical to SIHRS_pop.bngl.

Rationale for existing at all: the measured defect is predictive SPREAD, not the
central estimate (swapping SIHRS's spread for a calibrated one gains 0.070
relWIS; swapping its median gains 0.003). Fewer fitted dimensions means less
posterior spread, so this is the one structural direction pointed at the real
problem.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from flubnf.sihrs_fit import FITTED_PRIORS, MIN_PRIORS, StateSetup, write_conf

TPL = Path(__file__).resolve().parent.parent / "flubnf" / "templates"
FULL = (TPL / "SIHRS_pop.bngl").read_text()
MIN = (TPL / "SIHRS_pop_min.bngl").read_text()
DROPPED = ("eps2", "phi2", "impr")


@pytest.fixture
def setup():
    return StateSetup(state="T", fips="01", population=5_000_000, gamma=2.188,
                      rho=0.02, rhomult=1e-3, gammaH=1.17, omega=0.019, s0=0.85,
                      i0=2e-4, attack_rate=0.18, n_obs=5,
                      observed=np.array([1.0, 2, 3, 4, 5]))


class TestParameterCount:
    def test_exactly_five_fitted_vars(self):
        assert set(re.findall(r"(\w+)__FREE", MIN)) == {
            "Reff", "eps1", "phi1", "mult", "r"}

    def test_priors_match_the_template(self):
        assert set(MIN_PRIORS) == set(re.findall(r"(\w+__FREE)", MIN))

    @pytest.mark.parametrize("name", DROPPED)
    def test_dropped_params_appear_nowhere_in_the_model_body(self, name):
        body = MIN.split("begin parameters", 1)[1]
        assert f"{name}__FREE" not in body
        # and not left dangling in a rule or function either
        assert not re.search(rf"\b{name}\b\s*$", body, re.M)

    def test_retained_priors_are_byte_identical(self):
        for k in MIN_PRIORS:
            assert MIN_PRIORS[k] == FITTED_PRIORS[k], f"{k} prior drifted"


class TestModelUnchangedOtherwise:
    """A parameter-count change must not become a dynamics change."""

    def test_same_reaction_rules_minus_the_importation_rule(self):
        def rules(txt):
            b = txt.split("begin reaction rules", 1)[1].split("end reaction rules")[0]
            return [l.strip() for l in b.splitlines()
                    if l.strip() and not l.strip().startswith("#")]
        full, mini = rules(FULL), rules(MIN)
        assert "S() -> I()   impr" in full
        assert [r for r in full if "impr" not in r] == mini

    def test_observable_is_unchanged(self):
        line = "H_weekly() = rho*mult*gamma*I"
        assert line in FULL and line in MIN

    def test_seasonal_term_loses_only_the_semiannual_harmonic(self):
        assert "eps1*cos(2*pi*(t-phi1)/52)" in MIN
        assert "eps2*cos(4*pi*(t-phi2)/52)" not in MIN
        assert "beta0*exp(" in MIN

    def test_same_species_and_seed_values(self):
        def block(txt, name):
            return txt.split(f"begin {name}", 1)[1].split(f"end {name}")[0].strip()
        assert block(FULL, "molecule types") == block(MIN, "molecule types")
        assert block(FULL, "seed species") == block(MIN, "seed species")

    def test_fixed_constants_survive(self):
        for tok in ("{{POP}}", "{{S0FRAC}}", "{{I0FRAC}}", "{{GAMMA}}",
                    "{{RHO}}", "{{GAMMAH}}", "{{OMEGA}}"):
            assert tok in MIN


class TestConf:
    def test_conf_emits_five_vars(self, setup, tmp_path):
        txt = write_conf(setup, model=tmp_path / "m", exp=tmp_path / "e",
                         out_dir=tmp_path / "o", conf_path=tmp_path / "c.conf",
                         bng_command="x", priors=MIN_PRIORS).read_text()
        assert len(re.findall(r"^(?:log)?uniform_var = ", txt, re.M)) == 5
        for name in DROPPED:
            assert f"{name}__FREE" not in txt

    def test_full_conf_is_untouched(self, setup, tmp_path):
        """Omitting `priors` must still produce the 8-parameter config -- the
        multi-season path depends on `impr` and would fail without it."""
        txt = write_conf(setup, model=tmp_path / "m", exp=tmp_path / "e",
                         out_dir=tmp_path / "o", conf_path=tmp_path / "c.conf",
                         bng_command="x").read_text()
        assert len(re.findall(r"^(?:log)?uniform_var = ", txt, re.M)) == 8
        assert "impr__FREE" in txt


class TestImprIsSafeToDropForOneSeason:
    """impr exists to keep I off the numerical floor across MULTI-season runs,
    where dropping it once broke 100% of 230-week fits with CVODE stiffness.
    Over a single season it must be inert -- that is the whole justification."""

    def test_single_season_trajectory_is_unchanged_without_impr(self):
        from flubnf.simulate_sihrs import simulate_sihrs
        p = dict(N=5e6, s0=0.85, i0=2e-4, gamma=2.188, rho=0.02, gammaH=1.17,
                 omega=0.019, R0=1.10 / 0.85, eps1=0.05, phi1=22.0,
                 eps2=0.0, phi2=0.0, mult=0.05)
        a = np.asarray(simulate_sihrs(dict(p, impr=1e-7), n_weeks=48).H_weekly)
        b = np.asarray(simulate_sihrs(dict(p, impr=0.0), n_weeks=48).H_weekly)
        assert np.all(np.isfinite(a)) and np.all(np.isfinite(b))
        assert a.max() == pytest.approx(b.max(), rel=0.02)

    def test_the_full_template_still_has_impr(self):
        """Multi-season work must not lose it."""
        assert "impr__FREE" in FULL
        assert "S() -> I()   impr" in FULL
