"""The sampler defaults are a measured result, not a preference.

Guards the config that came out of the 2026-08-02 2x2. The old defaults
(population_size=1, all uniform_var) gave median ESS 9 of 11,250 samples and
split R-hat 1.192 -- chains that had not converged in any usable sense. The new
defaults give ~7x the ESS in less wall time. These tests exist so a future edit
cannot quietly revert them.
"""
from __future__ import annotations

import re

import numpy as np
import pytest

from flubnf.sihrs_fit import (FITTED_PRIORS, LOG_SCALE_VARS, StateSetup,
                              write_conf)


@pytest.fixture
def setup():
    return StateSetup(state="Alabama", fips="01", population=5_157_699,
                      gamma=2.188, rho=0.02, rhomult=1e-3, gammaH=1.17,
                      omega=0.019, s0=0.85, i0=1e-4, attack_rate=0.18,
                      n_obs=20, observed=np.linspace(10.0, 200.0, 20))


def conf(setup, tmp_path, **kw):
    p = write_conf(setup, model=tmp_path / "m.bngl", exp=tmp_path / "m.exp",
                   out_dir=tmp_path / "res", conf_path=tmp_path / "c.conf",
                   bng_command="/bin/true", **kw)
    return p.read_text()


class TestChainCount:
    def test_default_runs_multiple_chains(self, setup, tmp_path):
        """population_size IS the chain count (num_parallel = population_size).
        pop=1 makes multi-chain R-hat impossible to compute at all."""
        t = conf(setup, tmp_path)
        m = re.search(r"^population_size = (\d+)", t, re.M)
        assert m and int(m.group(1)) >= 4, "default must run >=4 chains"

    def test_chains_run_concurrently_by_default(self, setup, tmp_path):
        """parallel_count must track population_size, or 4 chains cost 4x wall
        time: measured 136 min serial vs 14 min concurrent."""
        t = conf(setup, tmp_path)
        pop = int(re.search(r"^population_size = (\d+)", t, re.M).group(1))
        par = int(re.search(r"^parallel_count = (\d+)", t, re.M).group(1))
        assert par == pop

    def test_parallel_count_can_still_be_pinned(self, setup, tmp_path):
        t = conf(setup, tmp_path, population_size=4, parallel_count=1)
        assert re.search(r"^parallel_count = 1$", t, re.M)


class TestLogScaling:
    def test_scale_parameters_are_log_sampled(self, setup, tmp_path):
        t = conf(setup, tmp_path)
        for v in LOG_SCALE_VARS:
            assert re.search(rf"^loguniform_var = {v} ", t, re.M), (
                f"{v} spans orders of magnitude and must be log-sampled")

    def test_amplitudes_are_not_log_sampled(self, setup, tmp_path):
        """eps1/eps2 have a lower bound of exactly 0 -- log is undefined."""
        t = conf(setup, tmp_path)
        for v in ("eps1__FREE", "eps2__FREE"):
            assert re.search(rf"^uniform_var = {v} ", t, re.M)

    def test_log_scaling_can_be_disabled(self, setup, tmp_path):
        t = conf(setup, tmp_path, log_scale=False)
        assert "loguniform_var" not in t
        assert re.search(r"^uniform_var = Reff__FREE ", t, re.M)

    def test_no_parameter_is_declared_twice(self, setup, tmp_path):
        t = conf(setup, tmp_path)
        names = re.findall(r"^(?:log)?uniform_var = (\S+) ", t, re.M)
        assert len(names) == len(set(names))

    def test_every_fitted_prior_is_declared_exactly_once(self, setup, tmp_path):
        t = conf(setup, tmp_path)
        names = set(re.findall(r"^(?:log)?uniform_var = (\S+) ", t, re.M))
        assert names == set(FITTED_PRIORS)

    def test_log_scaled_bounds_are_strictly_positive(self):
        """loguniform on a bound of 0 is undefined; catch it at the prior."""
        for v in LOG_SCALE_VARS:
            lo, _ = FITTED_PRIORS[v]
            assert lo > 0, f"{v} is log-sampled but its lower bound is {lo}"

    def test_bounds_are_unchanged_by_log_scaling(self, setup, tmp_path):
        """Log-scaling changes the PROPOSAL geometry, never the prior support."""
        t = conf(setup, tmp_path)
        for name, (lo, hi) in FITTED_PRIORS.items():
            m = re.search(rf"^(?:log)?uniform_var = {name} (\S+) (\S+)$", t, re.M)
            assert m and (float(m.group(1)), float(m.group(2))) == (lo, hi)


class TestUnchangedEssentials:
    def test_sbml_backend_is_never_set(self, setup, tmp_path):
        """`sbml_backend = bngsim` selects the SBML bridge, whose species-only
        output cannot see H_weekly (a function).

        Match the DIRECTIVE, not the substring: pytest derives tmp_path from the
        test name, so the conf's own file paths contain "sbml_backend".
        """
        t = conf(setup, tmp_path)
        assert not re.search(r"^\s*sbml_backend\s*=", t, re.M)

    def test_noise_trajectory_is_emitted(self, setup, tmp_path):
        assert "output_noise_trajectory = H_weekly" in conf(setup, tmp_path)

    def test_objective_requires_r_free(self, setup, tmp_path):
        """neg_bin_dynamic hard-requires a free parameter named exactly r__FREE
        (pybnf/config.py:695)."""
        t = conf(setup, tmp_path)
        assert "objfunc = neg_bin_dynamic" in t
        assert re.search(r"^(?:log)?uniform_var = r__FREE ", t, re.M)
