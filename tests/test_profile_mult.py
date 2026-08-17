"""Invariants of the mult-profiling shortcut.

Each test pins a property that, if broken, would silently bias every fit that
uses a fixed `mult` -- which is worse than sampling it, because there is no
posterior to reveal the problem.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from flubnf.profile_mult import (MULT_MAX, MULT_MIN, MultEstimate, estimate,
                                 fix_mult_in_model, optimal_mult)
from flubnf.sihrs_fit import FITTED_PRIORS, StateSetup, write_conf


@pytest.fixture
def setup():
    rng = np.random.default_rng(0)
    obs = np.concatenate([np.linspace(8, 90, 12), np.linspace(90, 25, 10)])
    obs = np.maximum(obs * rng.lognormal(0, 0.08, len(obs)), 1.0)
    return StateSetup(state="Testland", fips="01", population=5_000_000,
                      gamma=2.188, rho=0.02, rhomult=1e-3, gammaH=1.17,
                      omega=0.019, s0=0.85, i0=2e-4, attack_rate=0.18,
                      n_obs=len(obs), observed=obs)


class TestOptimalMult:
    def test_recovers_a_known_scale_exactly(self):
        """The whole premise: the optimum is attained, not searched for."""
        b = np.linspace(1.0, 50.0, 25)
        for true in (0.003, 0.05, 0.4, 0.9):
            assert optimal_mult(b, b * true) == pytest.approx(true, rel=1e-9)

    def test_is_the_geometric_mean_ratio(self):
        b = np.array([1.0, 2.0, 4.0, 8.0])
        o = np.array([2.0, 4.0, 4.0, 8.0])          # ratios 2,2,1,1
        assert optimal_mult(b, o) == pytest.approx(np.sqrt(2.0), rel=1e-9)

    def test_ignores_zero_and_negative_entries(self):
        b = np.array([1.0, 2.0, 0.0, 4.0, -1.0, 5.0])
        o = np.array([0.5, 1.0, 7.0, 2.0, 3.0, 2.5])
        assert optimal_mult(b, o) == pytest.approx(0.5, rel=1e-9)

    def test_too_few_usable_points_returns_none(self):
        assert optimal_mult(np.array([1.0, 0.0]), np.array([1.0, 0.0])) is None
        assert optimal_mult(np.array([]), np.array([])) is None

    def test_uses_only_the_observed_window(self):
        """`unscaled` runs past the data; the extra weeks must not enter."""
        b = np.concatenate([np.full(10, 2.0), np.full(5, 1e6)])
        o = np.full(10, 1.0)
        assert optimal_mult(b, o) == pytest.approx(0.5, rel=1e-9)


class TestEstimate:
    def test_returns_a_physical_value(self, setup):
        e = estimate(setup, maxiter=12, popsize=8)
        assert e.ok
        assert MULT_MIN <= e.mult <= MULT_MAX

    def test_clamped_flag_tracks_the_raw_value(self, setup):
        e = estimate(setup, maxiter=12, popsize=8)
        assert e.clamped == (e.raw > MULT_MAX)
        if e.clamped:
            assert e.mult == pytest.approx(MULT_MAX)

    def test_clamped_estimate_always_falls_back(self):
        """A clamp means rho is too small -- fixing at 1.0 would bake that in."""
        e = MultEstimate(mult=1.0, raw=1.8, clamped=True, fit_err=0.05, ok=True)
        assert e.needs_fallback()

    def test_poor_fit_falls_back(self):
        e = MultEstimate(mult=0.05, raw=0.05, clamped=False, fit_err=0.95, ok=True)
        assert e.needs_fallback()

    def test_failed_estimate_falls_back(self):
        assert MultEstimate(np.nan, np.nan, False, np.nan, ok=False).needs_fallback()

    def test_good_estimate_does_not_fall_back(self):
        e = MultEstimate(mult=0.05, raw=0.05, clamped=False, fit_err=0.15, ok=True)
        assert not e.needs_fallback()


class TestDropVarsIsTheOnlyDifference:
    """The profiled arm is compared against sweep cells that were fit with the
    stock conf. If ANY other setting differs, the measured effect is confounded.
    A hand-copied duplicate of write_conf silently drifted on `backup_every` and
    `max_iterations` when this was first written, which is why these exist.
    """

    def _confs(self, tmp_path, setup):
        kw = dict(model=tmp_path / "m.bngl", exp=tmp_path / "m.exp",
                  out_dir=tmp_path / "res", bng_command="/bin/true",
                  max_iterations=8000, burn_in=2000, adaptive=2000)
        a = write_conf(setup, conf_path=tmp_path / "a.conf", **kw).read_text()
        b = write_conf(setup, conf_path=tmp_path / "b.conf",
                       drop_vars=("mult__FREE",), **kw).read_text()
        return a.splitlines(), b.splitlines()

    def test_exactly_one_line_is_removed(self, tmp_path, setup):
        a, b = self._confs(tmp_path, setup)
        assert len(a) - len(b) == 1

    def test_the_removed_line_is_the_mult_prior(self, tmp_path, setup):
        a, b = self._confs(tmp_path, setup)
        gone = [ln for ln in a if ln not in b]
        assert len(gone) == 1 and "mult__FREE" in gone[0]

    def test_every_other_setting_is_untouched(self, tmp_path, setup):
        """Not just the sampler block -- burn_in, adaptive, backup_every,
        objfunc, population_size and the other seven priors must all survive."""
        a, b = self._confs(tmp_path, setup)
        assert [ln for ln in a if "mult__FREE" not in ln] == b

    def test_the_other_priors_all_remain(self, tmp_path, setup):
        _, b = self._confs(tmp_path, setup)
        for name in FITTED_PRIORS:
            if name != "mult__FREE":
                assert any(name in ln for ln in b), f"{name} vanished"

    def test_default_is_a_no_op(self, tmp_path, setup):
        """Omitting drop_vars must leave the production path bit-identical --
        the running sweep imports this same function."""
        kw = dict(model=tmp_path / "m.bngl", exp=tmp_path / "m.exp",
                  out_dir=tmp_path / "res", bng_command="/bin/true")
        a = write_conf(setup, conf_path=tmp_path / "a.conf", **kw).read_text()
        b = write_conf(setup, conf_path=tmp_path / "b.conf",
                       drop_vars=(), **kw).read_text()
        assert a == b and "mult__FREE" in a


class TestFixMultInModel:
    TEMPLATE = ("begin parameters\n"
                "Reff    Reff__FREE\n"
                "mult    mult__FREE     # ascertainment\n"
                "r       r__FREE\n"
                "end parameters\n"
                "H_weekly() = rho*mult*gamma*I\n")

    def test_replaces_only_the_declaration(self, tmp_path):
        p = tmp_path / "m.bngl"; p.write_text(self.TEMPLATE)
        fix_mult_in_model(p, 0.0731)
        t = p.read_text()
        assert re.search(r"^mult\s+0\.0731", t, re.M)
        assert "mult__FREE" not in t

    def test_leaves_the_observable_untouched(self, tmp_path):
        """The model PARAMETER is still `mult`; only the fitted var disappears."""
        p = tmp_path / "m.bngl"; p.write_text(self.TEMPLATE)
        fix_mult_in_model(p, 0.05)
        assert "H_weekly() = rho*mult*gamma*I" in p.read_text()

    def test_other_free_parameters_survive(self, tmp_path):
        p = tmp_path / "m.bngl"; p.write_text(self.TEMPLATE)
        fix_mult_in_model(p, 0.05)
        t = p.read_text()
        assert "Reff__FREE" in t and "r__FREE" in t

    def test_raises_if_the_line_is_missing(self, tmp_path):
        p = tmp_path / "m.bngl"; p.write_text("begin parameters\nReff Reff__FREE\n")
        with pytest.raises(ValueError):
            fix_mult_in_model(p, 0.05)

    def test_raises_rather_than_double_substituting(self, tmp_path):
        p = tmp_path / "m.bngl"
        p.write_text("mult    mult__FREE\nmult    mult__FREE\n")
        with pytest.raises(ValueError):
            fix_mult_in_model(p, 0.05)
