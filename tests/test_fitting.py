"""Tests for flubnf.fitting (in-Python DE fitter)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from flubnf.conf_files import FreeParam
from flubnf.fitting import fit, write_sorted_params
from flubnf.results import read_de_results
from flubnf.simulate import predict_weekly


class TestSIRSObjectiveG2:
    """G2 regression: a SIRS in-proc fit must route through the SIRS mirror.
    Without model_type/fixed_params the objective raised KeyError every call
    and returned a flat 1e12 (degenerate fit)."""

    def test_sirs_inproc_objective_is_not_degenerate(self):
        true = {"b0": 0.2, "db1": 0.8, "tc1": 8.0, "sw": 2.5, "gamma": 0.5,
                "mult": 0.01, "r": 20.0, "I0": 50.0, "N": 1_000_000.0, "omega": 0.0}
        obs = predict_weekly(true, n_weeks=22, model_type="sirs_logistic")
        fixed = {"tc1": 8.0, "sw": 2.5, "N": 1_000_000.0, "omega": 0.0}
        bounds = [
            FreeParam("b0__FREE", 0.05, 1.5),
            FreeParam("db1__FREE", -1.2, 1.2),
            FreeParam("gamma__FREE", 0.05, 0.9),
            FreeParam("mult__FREE", 1e-4, 5e-2),
            FreeParam("r__FREE", 1, 50),
            FreeParam("I0__FREE", 1.0, 1000.0),
        ]
        res = fit("SIRS", obs, bounds, popsize=12, max_iter=120, seed=0,
                  model_type="sirs_logistic", fixed_params=fixed)
        assert np.isfinite(res.best_obj)
        assert res.best_obj < 1e11           # not the degenerate flat objective
        assert float(np.std(res.objectives)) > 0.0  # the fit actually moved

    def test_sirs_default_model_type_would_be_degenerate(self):
        # Sanity: with the default piecewise objective, SIRS params (no t0)
        # give the degenerate 1e12 — proving model_type routing is the fix.
        true = {"b0": 0.2, "db1": 0.8, "tc1": 8.0, "sw": 2.5, "gamma": 0.5,
                "mult": 0.01, "r": 20.0, "I0": 50.0, "N": 1_000_000.0, "omega": 0.0}
        obs = predict_weekly(true, n_weeks=22, model_type="sirs_logistic")
        bounds = [FreeParam("b0__FREE", 0.05, 1.5),
                  FreeParam("db1__FREE", -1.2, 1.2),
                  FreeParam("gamma__FREE", 0.05, 0.9),
                  FreeParam("mult__FREE", 1e-4, 5e-2),
                  FreeParam("r__FREE", 1, 50),
                  FreeParam("I0__FREE", 1.0, 1000.0)]
        res = fit("SIRSbad", obs, bounds, popsize=8, max_iter=30, seed=0)
        assert res.best_obj >= 1e11          # degenerate, as expected


class TestFit:
    def test_recovers_known_params_on_synthetic_data(self):
        """If we generate data from known params and re-fit, the best fit
        should land near the truth."""
        true = {"I0": 0.005, "b0": 0.7, "gamma": 0.2, "mult": 2000.0, "t0": 2.0}
        obs = predict_weekly(true, n_weeks=20)
        # Add a touch of noise.
        rng = np.random.default_rng(7)
        obs = obs + rng.normal(0, 0.5, size=len(obs))
        bounds = [
            FreeParam("I0__FREE", 0.001, 0.02),
            FreeParam("b0__FREE", 0.1, 1.5),
            FreeParam("gamma__FREE", 0.05, 0.5),
            FreeParam("mult__FREE", 500, 5000),
            FreeParam("t0__FREE", 0, 10),
        ]
        result = fit("Synth", obs, bounds, popsize=10, max_iter=200, seed=0)
        bp = result.best_params
        # Loose recovery test — DE is stochastic and noise is non-negligible.
        assert abs(bp["b0__FREE"] - true["b0"]) < 0.2
        assert abs(bp["t0__FREE"] - true["t0"]) < 2.0

    def test_population_has_correct_shape(self):
        obs = np.linspace(5, 30, 12)
        bounds = [
            FreeParam("I0__FREE", 0.001, 0.01),
            FreeParam("b0__FREE", 0.1, 0.9),
            FreeParam("gamma__FREE", 0.05, 0.3),
            FreeParam("mult__FREE", 500, 3000),
            FreeParam("t0__FREE", 0, 5),
        ]
        result = fit("S", obs, bounds, popsize=10, max_iter=50, seed=1)
        assert result.population.shape[1] == len(bounds)
        assert result.population.shape[0] >= 10
        assert result.objectives.shape[0] == result.population.shape[0]


class TestWriteSortedParams:
    def test_round_trips_through_read_de_results(self, tmp_path):
        obs = np.linspace(5, 30, 12)
        bounds = [
            FreeParam("I0__FREE", 0.001, 0.01),
            FreeParam("b0__FREE", 0.1, 0.9),
            FreeParam("gamma__FREE", 0.05, 0.3),
            FreeParam("mult__FREE", 500, 3000),
            FreeParam("t0__FREE", 0, 5),
        ]
        result = fit("Roundtrip", obs, bounds, popsize=10, max_iter=30, seed=2)
        state_dir = tmp_path / "Roundtrip"
        out = write_sorted_params(result, state_dir)
        assert out.exists()
        # Now read it back via the production parser.
        de = read_de_results(state_dir, "Roundtrip")
        assert de is not None
        assert set(de.param_names) == {fp.name for fp in bounds}
        # Best obj from the file should match.
        assert abs(de.best_obj - result.best_obj) < 1e-6
        # And population should be sorted ascending by Obj.
        objs = de.population["Obj"].to_numpy()
        assert (objs[:-1] <= objs[1:]).all()
