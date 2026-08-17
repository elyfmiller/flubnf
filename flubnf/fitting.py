"""Minimal in-Python differential-evolution fitter for the SIR model.

This is a stand-in for PyBNF runs in contexts where we don't want to spawn
BioNetGen — namely the walk-forward backtest in `flubnf.backtest`. It uses
scipy's differential-evolution under the hood but captures the final
population and writes it to disk in PyBNF's exact `sorted_params_final.txt`
format so the same downstream parser / analyzer code works without
modification.

Objective: Gaussian negative log-likelihood on the H_weekly trajectory.
We don't use the negative-binomial PyBNF default because for this purpose
(decision-relevant point fits + bounds analysis) Gaussian is fine and far
simpler — and the analyzer's AICc code already assumes Gaussian residuals.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from scipy.optimize._differentialevolution import DifferentialEvolutionSolver

from .conf_files import FreeParam
from .simulate import predict_weekly

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FitResult:
    state: str
    param_names: tuple[str, ...]      # ordered, with __FREE suffix
    population: np.ndarray            # shape (popsize, n_params)
    objectives: np.ndarray            # shape (popsize,)
    best_idx: int

    @property
    def best_params(self) -> dict[str, float]:
        return dict(zip(self.param_names, self.population[self.best_idx]))

    @property
    def best_obj(self) -> float:
        return float(self.objectives[self.best_idx])


# ---------------------------------------------------------------------------
# Objective
# ---------------------------------------------------------------------------
def _objective_factory(
    observed: np.ndarray, param_names: Sequence[str],
    *, model_type: str = "sir_piecewise", fixed_params=None,
):
    """Build the Gaussian neg-log-likelihood objective.

    `model_type` / `fixed_params`: for `sirs_logistic`, route predictions
    through the SIRS mirror and merge the fixed structural params (sw, tc_k,
    N, omega) the DE vector does not carry. Without this a SIRS in-proc fit
    raises KeyError every call → a flat 1e12 objective (degenerate fit).
    """
    n_obs = len(observed)
    obs = np.asarray(observed, dtype=float)

    def objective(x: np.ndarray) -> float:
        params = dict(zip(param_names, x))
        if fixed_params:
            params = {**fixed_params, **params}
        try:
            pred = predict_weekly(params, n_obs, model_type=model_type)
        except Exception:
            return 1e12
        if not np.all(np.isfinite(pred)):
            return 1e12
        # Gaussian -log-likelihood ∝ sum((obs - pred)^2)
        return float(np.sum((obs - pred) ** 2))

    return objective


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def fit(
    state: str,
    observed: np.ndarray,
    bounds: Sequence[FreeParam],
    *,
    popsize: int = 15,
    max_iter: int = 200,
    seed: int = 0,
    tol: float = 1e-4,
    model_type: str = "sir_piecewise",
    fixed_params=None,
) -> FitResult:
    """Run DE on the SIR model. Returns the final population and best fit.

    `bounds` may include params unused by the SIR model (e.g. r__FREE, which
    PyBNF uses for the neg-bin AMCMC sampler). Those parameters are fit but
    do not affect the SIR objective; they'll wander within their bounds.

    `model_type` / `fixed_params`: route the in-proc objective through the
    SIRS mirror when fitting `sirs_logistic` (defaults keep piecewise SIR).
    """
    param_names = tuple(fp.name for fp in bounds)
    lo_hi = [(fp.low, fp.high) for fp in bounds]
    obj = _objective_factory(observed, param_names,
                             model_type=model_type, fixed_params=fixed_params)

    solver = DifferentialEvolutionSolver(
        obj, lo_hi,
        maxiter=max_iter, popsize=popsize, tol=tol, rng=seed,
        mutation=(0.5, 1.0), recombination=0.7,
        init="sobol", polish=False, updating="deferred",
    )
    result = solver.solve()
    population = solver.population.copy()
    # solver.population is in [0,1] scaled coords; convert to real bounds.
    scaled = np.array(lo_hi)
    real_pop = scaled[:, 0] + population * (scaled[:, 1] - scaled[:, 0])
    objectives = np.array([obj(row) for row in real_pop])
    best_idx = int(np.argmin(objectives))
    log.debug("fit(%s): best_obj=%.3f after %d iters",
              state, objectives[best_idx], result.nit)
    return FitResult(
        state=state,
        param_names=param_names,
        population=real_pop,
        objectives=objectives,
        best_idx=best_idx,
    )


# ---------------------------------------------------------------------------
# Write PyBNF-compatible output
# ---------------------------------------------------------------------------
def write_sorted_params(
    fit_result: FitResult, results_dir: Path,
) -> Path:
    """Write `sorted_params_final.txt` in PyBNF's exact format so the
    existing parser / analyzer can read it without modification."""
    out_dir = results_dir / "Results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "sorted_params_final.txt"

    # Sort by objective ascending (best first).
    order = np.argsort(fit_result.objectives)
    pop_sorted = fit_result.population[order]
    obj_sorted = fit_result.objectives[order]

    with open(out, "w") as f:
        header = "#\tSimulation\tObj\t" + "\t".join(fit_result.param_names) + "\n"
        f.write(header)
        for i, (params, obj) in enumerate(zip(pop_sorted, obj_sorted)):
            sim = f"gen{i:02d}ind{i:02d}"
            cells = [str(obj)] + [f"{x:.16g}" for x in params]
            f.write(f"\t{sim}\t" + "\t".join(cells) + "\n")
    return out
