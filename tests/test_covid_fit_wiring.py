"""The COVID fit wiring must be additive: influenza must come out unchanged.

Two things are checked. First, that routing influenza through the profile-aware
path reproduces the shipped path exactly -- same setup, same conf bytes. Second,
that the COVID path actually differs where it must and only there.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from flubnf import covid_fit, sihrs_fit
from flubnf.profiles import COVID, INFLUENZA


@pytest.fixture
def setup():
    return sihrs_fit.StateSetup(
        state="Alabama", fips="01", population=5_157_699, gamma=2.188,
        rho=0.02, rhomult=1e-3, gammaH=1.17, omega=0.019, s0=0.85, i0=1e-4,
        attack_rate=0.18, n_obs=20,
        observed=np.linspace(10.0, 200.0, 20), times=np.arange(20))


def _conf(profile, setup, tmp_path, **kw):
    p = covid_fit.write_profile_conf(
        profile, setup, model=tmp_path / "m.bngl", exp=tmp_path / "m.exp",
        out_dir=tmp_path / "res", conf_path=tmp_path / f"{profile.key}.conf",
        bng_command="/bin/true", **kw)
    return p.read_text()


class TestOmegaConversions:
    def test_round_trip(self):
        for m in (1.8, 3.0, 6.0, 9.0, 12.0, 18.0):
            assert covid_fit.omega_to_months(
                covid_fit.months_to_omega(m)) == pytest.approx(m)

    def test_the_flu_constant_is_about_a_year(self):
        assert covid_fit.omega_to_months(
            sihrs_fit.OMEGA_PER_WEEK) == pytest.approx(12.1, abs=0.2)


class TestConfWriting:
    def test_influenza_conf_is_byte_identical_to_the_shipped_writer(
            self, setup, tmp_path):
        a = _conf(INFLUENZA, setup, tmp_path)
        b = sihrs_fit.write_conf(
            setup, model=tmp_path / "m.bngl", exp=tmp_path / "m.exp",
            out_dir=tmp_path / "res", conf_path=tmp_path / "ref.conf",
            bng_command="/bin/true", priors=sihrs_fit.MIN_PRIORS).read_text()
        assert a == b.replace("ref.conf", "influenza.conf")

    def test_covid_conf_declares_six_fitted_vars(self, setup, tmp_path):
        t = _conf(COVID, setup, tmp_path)
        names = re.findall(r"^(?:log)?uniform_var = (\S+)", t, re.M)
        assert set(names) == {"Reff__FREE", "eps1__FREE", "phi1__FREE",
                              "omega__FREE", "mult__FREE", "r__FREE"}

    def test_omega_is_log_scaled(self, setup, tmp_path):
        """A strictly positive scale parameter spanning an order of magnitude.
        Proposing linearly there wastes the budget at the top of the box."""
        t = _conf(COVID, setup, tmp_path)
        assert re.search(r"^loguniform_var = omega__FREE ", t, re.M)
        assert not re.search(r"^uniform_var = omega__FREE ", t, re.M)

    def test_omega_bounds_are_the_profile_prior(self, setup, tmp_path):
        t = _conf(COVID, setup, tmp_path)
        m = re.search(r"^loguniform_var = omega__FREE (\S+) (\S+)", t, re.M)
        assert (float(m.group(1)), float(m.group(2))) == pytest.approx(
            COVID.fitted_priors["omega__FREE"])

    def test_influenza_conf_never_mentions_omega(self, setup, tmp_path):
        assert "omega" not in _conf(INFLUENZA, setup, tmp_path)

    def test_phi1_box_is_the_full_year_in_both(self, setup, tmp_path):
        for p in (INFLUENZA, COVID):
            t = _conf(p, setup, tmp_path)
            assert re.search(r"^uniform_var = phi1__FREE 0.0 52.0", t, re.M)

    def test_sampler_defaults_survive_the_profile_path(self, setup, tmp_path):
        t = _conf(COVID, setup, tmp_path)
        pop = int(re.search(r"^population_size = (\d+)", t, re.M).group(1))
        par = int(re.search(r"^parallel_count = (\d+)", t, re.M).group(1))
        assert pop >= 4 and par == pop


class TestMaterialization:
    def test_covid_template_materializes_with_no_omega_token(
            self, setup, tmp_path):
        out = covid_fit.materialize_for_profile(
            COVID, setup, tmp_path / "m.bngl", t_end=40)
        txt = out.read_text()
        assert "omega   omega__FREE" in txt
        assert "{{" not in txt
        assert "t_end=>40" in txt

    def test_influenza_template_still_needs_and_gets_its_omega(
            self, setup, tmp_path):
        out = covid_fit.materialize_for_profile(
            INFLUENZA, setup, tmp_path / "m.bngl")
        assert "{{" not in out.read_text()
        assert "omega   0.019" in out.read_text()

    @pytest.mark.parametrize("profile", [INFLUENZA, COVID])
    def test_profile_tokens_exactly_cover_its_template(self, profile):
        """The invariant that makes a profile/template mismatch impossible:
        the biology tokens a template asks for are exactly the ones the profile
        supplies. A profile that fixes omega against a template that frees it
        would supply a token nobody reads; a profile that frees omega against a
        template that fixes it would leave {{OMEGA}} unresolved."""
        want = set(re.findall(r"\{\{[A-Z0-9_]+\}\}", profile.template.read_text()))
        per_state = {"{{POP}}", "{{S0FRAC}}", "{{I0FRAC}}"}
        assert want - per_state == set(profile.fixed_tokens())

    def test_an_unresolved_token_still_fails_loudly(self, setup, tmp_path):
        bad = tmp_path / "bad.bngl"
        bad.write_text(COVID.template.read_text() + "\n# {{NOT_A_TOKEN}}\n")
        with pytest.raises(ValueError, match="unresolved tokens"):
            sihrs_fit.materialize_model(setup, bad, tmp_path / "x.bngl", "s")


class TestResolveForProfile:
    def test_influenza_resolution_is_the_shipped_one(self, tmp_path):
        from flubnf.settings import ARCHIVE, LOCATIONS
        vs = sorted(p.name.split("_")[-1].removesuffix(".csv")
                    for p in ARCHIVE.glob("target-hospital-admissions_*.csv"))
        if not vs or not LOCATIONS.is_file():
            pytest.skip("FluSight hub archive not available")
        asof = vs[-1]
        y = int(asof[:4]) if int(asof[5:7]) >= 8 else int(asof[:4]) - 1
        kw = dict(truth_csv=ARCHIVE / f"target-hospital-admissions_{asof}.csv",
                  locations_csv=LOCATIONS, season_start=f"{y}-08-01",
                  as_of=asof)
        a = covid_fit.resolve_for_profile(INFLUENZA, "Alabama", **kw)
        b = sihrs_fit.resolve_state("Alabama", **kw)
        assert a.gamma == pytest.approx(b.gamma)
        assert a.rho == b.rho and a.gammaH == b.gammaH and a.omega == b.omega
        assert a.rhomult == pytest.approx(b.rhomult)
        assert a.i0 == pytest.approx(b.i0)
        assert a.n_obs == b.n_obs

    def test_covid_resolution_swaps_gamma_and_recomputes_i0(self, tmp_path):
        from flubnf import covid_vintage as cv
        from flubnf.settings import LOCATIONS
        if not cv.TIMESERIES.is_file() or not LOCATIONS.is_file():
            pytest.skip("COVID archive or locations not available")
        p = cv.vintage_path("2026-03-18", cache_dir=tmp_path)
        s = covid_fit.resolve_covid_state(
            "Texas", truth_csv=p, locations_csv=LOCATIONS,
            season_start="2025-06-01", as_of="2026-03-18")
        assert s.gamma == pytest.approx(7.0 / 6.84)
        assert s.rho == COVID.fixed.rho
        # i0 must follow the SWAPPED gamma and rho, not the influenza ones
        expect = sihrs_fit.initial_infected_fraction(
            max(float(s.observed[0]), 1.0), s.population, s.rhomult, s.gamma)
        assert s.i0 == pytest.approx(expect)
