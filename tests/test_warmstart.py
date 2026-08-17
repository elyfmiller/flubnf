"""Warm-starting must be aligned, or it is worse than not warm-starting at all.

PyBNF assigns `starting_params` BY INDEX (algorithms.py:2175) and orders
parameters by the order their `*_var` lines appear in the conf. A misaligned
line hands Reff's chain mult's value, and the fit proceeds without complaint --
the same silent-failure shape as the spawn bug these tests were written after.

So the alignment is asserted from both ends: the emitted line must follow the
priors dict that writes the conf, and a posterior missing any of those names
must raise rather than emit a short line that PyBNF would happily misread.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from flubnf.warmstart import (Posterior, cold_start_needed, pinned_parameters,
                              read_posterior, starting_params)

PRIORS = {"Reff__FREE": (0.6, 2.5), "eps1__FREE": (0.0, 1.0),
          "phi1__FREE": (0.0, 52.0), "mult__FREE": (0.002, 1.0),
          "r__FREE": (0.1, 40.0)}


def make_post(**over):
    med = {"Reff__FREE": 1.2, "eps1__FREE": 0.2, "phi1__FREE": 22.0,
           "mult__FREE": 0.05, "r__FREE": 8.0}
    med.update(over)
    rng = np.random.default_rng(0)
    samp = {k: np.clip(v + rng.normal(0, abs(v) * 0.05 + 1e-3, 500),
                       *PRIORS[k]) for k, v in med.items()}
    return Posterior(medians=med, samples=samp, objective=123.4, n_chains=4)


def write_run(tmp_path, n_chains=4, rows=200, cols=None, jitter=0.0):
    d = tmp_path / "Runs"
    d.mkdir(parents=True, exist_ok=True)
    cols = cols or list(PRIORS)
    rng = np.random.default_rng(1)
    for c in range(n_chains):
        vals = {k: rng.normal(1.0 + jitter * c, 0.05, rows) for k in cols}
        hdr = " ".join(cols)
        lines = [hdr] + [" ".join(f"{vals[k][i]:.6f}" for k in cols)
                         for i in range(rows)]
        (d / f"params_{c}.txt").write_text("\n".join(lines) + "\n")
    return d


class TestAlignment:
    def test_values_follow_the_priors_dict_order(self):
        post = make_post()
        line = starting_params(post, PRIORS)
        vals = [float(x) for x in line.split("=", 1)[1].split()]
        assert vals == [post.medians[k] for k in PRIORS]

    def test_reordering_the_priors_reorders_the_line(self):
        """If it did not, the line could not be tracking conf order."""
        post = make_post()
        rev = dict(reversed(list(PRIORS.items())))
        a = [float(x) for x in starting_params(post, PRIORS).split("=", 1)[1].split()]
        b = [float(x) for x in starting_params(post, rev).split("=", 1)[1].split()]
        assert a == list(reversed(b))

    def test_missing_parameter_raises_rather_than_emitting_a_short_line(self):
        post = make_post()
        del post.medians["mult__FREE"]
        with pytest.raises(ValueError, match="misaligned|missing"):
            starting_params(post, PRIORS)

    def test_line_length_matches_the_number_of_var_lines(self):
        post = make_post()
        n = len(starting_params(post, PRIORS).split("=", 1)[1].split())
        assert n == len(PRIORS)

    def test_value_outside_a_narrowed_bound_is_clipped_into_it(self):
        """Bounds move between rounds; an out-of-range start would be rejected
        and silently replaced by a random one."""
        post = make_post(mult__FREE=0.9)
        narrowed = dict(PRIORS, mult__FREE=(0.002, 0.1))
        vals = [float(x) for x in
                starting_params(post, narrowed).split("=", 1)[1].split()]
        assert vals[list(narrowed).index("mult__FREE")] == pytest.approx(0.1)


class TestReadPosterior:
    def test_pools_all_chains(self, tmp_path):
        d = write_run(tmp_path, n_chains=4, rows=200)
        post = read_posterior(d, PRIORS)
        assert post is not None and post.n_chains == 4
        assert all(post.samples[k].size == 4 * 150 for k in PRIORS)   # 25% burn-in

    def test_returns_none_when_there_is_nothing_to_read(self, tmp_path):
        (tmp_path / "Runs").mkdir()
        assert read_posterior(tmp_path / "Runs", PRIORS) is None

    def test_returns_none_when_a_parameter_is_absent(self, tmp_path):
        """A model change mid-season must force a cold start, not a partial one."""
        d = write_run(tmp_path, cols=[k for k in PRIORS if k != "r__FREE"])
        assert read_posterior(d, PRIORS) is None

    def test_short_chains_are_ignored(self, tmp_path):
        d = write_run(tmp_path, rows=4)
        assert read_posterior(d, PRIORS) is None


class TestColdStart:
    def test_first_fit_is_cold(self):
        cold, why = cold_start_needed(None, PRIORS)
        assert cold and "no previous" in why

    def test_warm_when_a_usable_posterior_exists(self):
        cold, why = cold_start_needed(make_post(), PRIORS)
        assert not cold and why == "warm start"

    def test_model_change_forces_cold(self):
        post = make_post()
        extended = dict(PRIORS, impr__FREE=(1e-9, 3e-5))
        cold, why = cold_start_needed(post, extended)
        assert cold and "impr__FREE" in why

    def test_stale_posterior_forces_cold(self):
        cold, why = cold_start_needed(make_post(), PRIORS,
                                      max_gap_weeks=3, gap_weeks=7)
        assert cold and "stale" in why

    def test_a_recent_gap_stays_warm(self):
        cold, _ = cold_start_needed(make_post(), PRIORS,
                                    max_gap_weeks=3, gap_weeks=1)
        assert not cold

    def test_non_finite_objective_forces_cold(self):
        p = make_post()
        cold, why = cold_start_needed(
            Posterior(p.medians, p.samples, float("inf"), 4), PRIORS)
        assert cold and "finite" in why


class TestPinning:
    def test_a_parameter_at_its_wall_is_flagged(self):
        post = make_post()
        post.samples["mult__FREE"][:] = 0.002          # hard against the floor
        assert "mult__FREE" in pinned_parameters(post, PRIORS)

    def test_an_interior_parameter_is_not(self):
        assert "Reff__FREE" not in pinned_parameters(make_post(), PRIORS)
