"""The parsimonious template must drop exactly three parameters and nothing else.

Every removal is justified by a measurement (docs/MODEL-PROVENANCE.md section
3). These tests keep the change a PARAMETER-COUNT change, never a model change:
the dynamics, the observable and every retained parameter must be identical to
SIHRS_pop.bngl.

Rationale for existing at all: the measured defect is predictive SPREAD, not the
central estimate (swapping SIHRS's spread for a calibrated one gains 0.070
relWIS; swapping its median gains 0.003). Fewer fitted dimensions means less
posterior spread, so this is the one structural direction pointed at the real
problem.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.engines.pf import VARS_1S

TPL = Path(__file__).resolve().parent.parent / "flubnf" / "templates"
FULL = (TPL / "SIHRS_pop.bngl").read_text()
MIN = (TPL / "SIHRS_pop_min.bngl").read_text()
DROPPED = ("eps2", "phi2", "impr")


class TestParameterCount:
    def test_exactly_five_fitted_vars(self):
        assert set(re.findall(r"(\w+)__FREE", MIN)) == {
            "Reff", "eps1", "phi1", "mult", "r"}

    def test_priors_match_the_template(self):
        """The PF engine's prior block names exactly the template's params."""
        assert (set(re.findall(r"(\w+__FREE)", VARS_1S))
                == set(re.findall(r"(\w+__FREE)", MIN)))

    @pytest.mark.parametrize("name", DROPPED)
    def test_dropped_params_appear_nowhere_in_the_model_body(self, name):
        body = MIN.split("begin parameters", 1)[1]
        assert f"{name}__FREE" not in body
        # and not left dangling in a rule or function either
        assert not re.search(rf"\b{name}\b\s*$", body, re.M)


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
        """Code lines only. Comment wording is documentation, not dynamics:
        the two templates are annotated for different readers and `min` was
        trimmed in 2026-08 without touching a single model line."""
        def block(txt, name):
            body = txt.split(f"begin {name}", 1)[1].split(f"end {name}")[0]
            return [l.strip() for l in body.splitlines()
                    if l.strip() and not l.strip().startswith("#")]
        assert block(FULL, "molecule types") == block(MIN, "molecule types")
        assert block(FULL, "seed species") == block(MIN, "seed species")

    def test_fixed_constants_survive(self):
        for tok in ("{{POP}}", "{{S0FRAC}}", "{{I0FRAC}}", "{{GAMMA}}",
                    "{{RHO}}", "{{GAMMAH}}", "{{OMEGA}}"):
            assert tok in MIN


class TestImprIsKeptForMultiSeason:
    """impr exists to keep I off the numerical floor across MULTI-season runs,
    where dropping it once broke 100% of 230-week fits with CVODE stiffness.
    Its single-season inertness was checked on the in-Python mirror, now
    removed (git history; docs/MODEL-PROVENANCE.md section 3.3)."""

    def test_the_full_template_still_has_impr(self):
        """Multi-season work must not lose it."""
        assert "impr__FREE" in FULL
        assert "S() -> I()   impr" in FULL
