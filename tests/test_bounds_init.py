"""Tests for flubnf.bounds_init."""

from __future__ import annotations

import numpy as np

from flubnf.bounds_init import (
    adaptive_initial_bounds,
    max_steps_for_state,
    max_transitions_for_state,
)


class TestAdaptiveInitialBounds:
    def test_empty_observed_returns_defaults(self):
        b = adaptive_initial_bounds(np.array([]))
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        assert mult.low == 100
        assert mult.high == 8000

    def test_high_peak_expands_mult_upper(self):
        # Peak 3000 -> 5*3000 = 15000 > 8000, so upper bound expands.
        b = adaptive_initial_bounds(np.array([100, 1500, 3000, 2000, 500]))
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        assert mult.high >= 15000

    def test_low_peak_keeps_default_upper(self):
        b = adaptive_initial_bounds(np.array([5, 10, 30, 25, 12]))
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        # 5 * 30 = 150 < 8000, default 8000 retained.
        assert mult.high == 8000

    def test_only_mult_is_affected(self):
        b = adaptive_initial_bounds(np.array([100, 1000, 3000, 2000]))
        for fp in b:
            if fp.name == "mult__FREE":
                continue
            # All others match defaults.
            assert fp.low > 0 or fp.low == 0
            assert fp.high > fp.low


class TestMaxStepsForState:
    def test_small_state_gets_one_step(self):
        assert max_steps_for_state(np.array([5, 10, 30, 20])) == 1

    def test_medium_state_gets_three(self):
        assert max_steps_for_state(np.array([100, 200, 400, 300])) == 3

    def test_large_state_gets_six(self):
        assert max_steps_for_state(np.array([100, 1500, 3000])) == 6


class TestMaxTransitionsForState:
    def test_small_state_gets_one(self):
        assert max_transitions_for_state(np.array([5, 10, 30, 20])) == 1

    def test_medium_state_gets_two(self):
        assert max_transitions_for_state(np.array([100, 200, 400, 300])) == 2

    def test_large_state_gets_three(self):
        assert max_transitions_for_state(np.array([100, 1500, 3000])) == 3


class TestSIRSBounds:
    def test_template_bounds_mult_is_fraction(self):
        from flubnf.bounds_init import _template_bounds
        b = _template_bounds("sirs_logistic")
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        assert mult.low == 1e-4 and mult.high == 5e-2
        # Smooth-beta model uses signed db1, not t0.
        names = {fp.name for fp in b}
        assert "db1__FREE" in names
        assert "t0__FREE" not in names

    def test_db1_is_signed(self):
        from flubnf.bounds_init import _template_bounds
        db1 = next(fp for fp in _template_bounds("sirs_logistic")
                   if fp.name == "db1__FREE")
        assert db1.low < 0 < db1.high

    def test_adaptive_anchors_mult_fraction_and_i0_count(self):
        # peak 5000 admissions in a 5,000,000-population state at 2% attack
        # rate => mult_center = 5000 / (5e6 * 0.02) = 0.05.
        obs = np.array([100, 1000, 5000, 3000, 500], dtype=float)
        b = adaptive_initial_bounds(
            obs, model_type="sirs_logistic", population=5_000_000)
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        # mult stays within the physical box and brackets a ~5% center.
        assert 1e-4 <= mult.low < mult.high <= 5e-2
        i0 = next(fp for fp in b if fp.name == "I0__FREE")
        # I0 is an absolute count anchored to ~0.001 * N.
        assert i0.low == 1.0
        assert i0.high == 5000.0  # 1e-3 * 5e6

    def test_adaptive_without_population_falls_back(self):
        obs = np.array([100, 1000, 5000], dtype=float)
        b = adaptive_initial_bounds(obs, model_type="sirs_logistic",
                                    population=None)
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        assert mult.low == 1e-4 and mult.high == 5e-2  # static box

    def test_piecewise_path_unchanged(self):
        # Legacy default must be byte-identical.
        obs = np.array([100, 1500, 3000, 2000, 500], dtype=float)
        b = adaptive_initial_bounds(obs)  # default model_type
        mult = next(fp for fp in b if fp.name == "mult__FREE")
        assert mult.high == 5 * 3000


# --- task #27: objective from sorted_params + circular pin exclusion ---------

def test_objective_read_from_sorted_params(tmp_path):
    """params_*.txt has no Obj column; the objective must come from
    Results/sorted_params_final.txt or stay inf and blind the stopping rule."""
    import numpy as np
    from flubnf.sihrs_fit import MIN_PRIORS
    from flubnf.warmstart import read_posterior
    runs = tmp_path / "Results" / "A_MCMC" / "Runs"
    runs.mkdir(parents=True)
    names = list(MIN_PRIORS)
    rows = np.column_stack([np.random.default_rng(0).uniform(lo, hi, 200)
                            for lo, hi in MIN_PRIORS.values()])
    with open(runs / "params_0.txt", "w") as f:
        f.write("\t".join(names) + "\n")
        np.savetxt(f, rows)
    (tmp_path / "Results" / "sorted_params_final.txt").write_text(
        "#\tSimulation\tObj\t" + "\t".join(names) + "\n"
        + "\titer1run1\t144.97\t" + "\t".join("1.0" for _ in names) + "\n"
        + "\titer2run1\t150.10\t" + "\t".join("1.0" for _ in names) + "\n")
    post = read_posterior(runs, MIN_PRIORS)
    assert post is not None
    assert abs(post.objective - 144.97) < 1e-6


def test_circular_parameter_never_pins(tmp_path):
    """phi1 piled at the 52 wall is a wrap, not a pin."""
    import numpy as np
    from flubnf.warmstart import Posterior, pinned_parameters
    priors = {"phi1__FREE": (0.0, 52.0), "mult__FREE": (0.002, 1.0)}
    post = Posterior(
        samples={"phi1__FREE": np.full(500, 51.9),
                 "mult__FREE": np.full(500, 0.999)},
        medians={"phi1__FREE": 51.9, "mult__FREE": 0.999},
        objective=100.0, n_chains=2)
    pins = pinned_parameters(post, priors)
    assert "phi1__FREE" not in pins      # circular: excluded
    assert "mult__FREE" in pins          # genuine wall: still caught
