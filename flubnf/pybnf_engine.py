"""Run real PyBNF as a fit engine, returning the same FitResult shape that
the in-Python DE in `fitting.fit()` produces.

This is what the backtest harness uses when `engine="pybnf"`. It's not the
same as `runs.run_one()` — that wrapper just launches PyBNF and exits. This
module also materializes the per-state conf/bngl/exp files with the current
bounds + piecewise structure + simulation window, then reads back the
PyBNF-written `sorted_params_final.txt` and packages it as a FitResult.

Compared to the in-Python DE (`fitting.fit`):
  - Uses BioNetGen + neg-binomial objective (the real PyBNF stack).
  - Slower per fit (~10-30s) but matches production behavior.
  - The DE settings come from the conf file; this module patches a few
    key fields (bounds, simulate window, max_iter, popsize) per call.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from . import bngl_files, conf_files
from .conf_files import FreeParam
from .config import FluBNFConfig
from .fitting import FitResult
from .paths import WorkspacePaths
from .results import read_amcmc_chain, read_de_results

log = logging.getLogger(__name__)


def _find_bng_path() -> Optional[Path]:
    """Locate BNG2.pl from the installed bionetgen package.

    We avoid `import bionetgen` because that package's top-level import
    depends on `pkg_resources.packaging`, which newer setuptools dropped.
    Instead, walk site-packages directly to find `bionetgen/bng-{mac,linux,win}/BNG2.pl`.
    """
    import sys
    import platform
    pick = {
        "Darwin": "bng-mac",
        "Linux": "bng-linux",
        "Windows": "bng-win",
    }.get(platform.system(), "bng-linux")
    for site in sys.path:
        candidate = Path(site) / "bionetgen" / pick / "BNG2.pl"
        if candidate.exists():
            return candidate
    return None


def _default_pybnf_binary() -> str:
    """Prefer the pybnf bundled in our venv over whatever's on PATH —
    multiple Python installs (anaconda etc.) often ship their own pybnf
    that doesn't match our installed bionetgen / numpy patches."""
    here = Path(__file__).resolve().parents[1]  # FluBNF/
    for venv_pybnf in (here / ".venv" / "bin" / "pybnf",
                       here / ".venv" / "Scripts" / "pybnf.exe"):
        if venv_pybnf.exists():
            return str(venv_pybnf)
    return "pybnf"


@dataclass(frozen=True)
class PyBNFOptions:
    """Per-call PyBNF settings; the conf file's other fields are kept.

    `method` selects the algorithm:
      - "de"  : differential evolution (point estimate + final population)
      - "am"  : adaptive Metropolis MCMC (Bayesian posterior + noise traj)

    AMCMC also uses `burn_in` / `adaptive` / `sample_every`.
    """
    method: str = "de"
    popsize: int = 12
    max_iter: int = 80
    # AMCMC-only settings; need max_iter > burn_in + adaptive + 2.
    burn_in: int = 150
    adaptive: int = 150
    sample_every: int = 1
    timeout_sec: float = 900.0
    pybnf_binary: str = ""

    def resolved_binary(self) -> str:
        return self.pybnf_binary or _default_pybnf_binary()


def fit_with_pybnf(
    state: str,
    observed: np.ndarray,
    bounds: Sequence[FreeParam],
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    n_steps: int = 1,
    options: Optional[PyBNFOptions] = None,
    forecast_horizon: int = 0,
) -> Optional[FitResult]:
    """Run real PyBNF on one state's observed data and return a FitResult.

    Materializes / rewrites the per-state .conf, .bngl, .exp under the
    workspace, launches `pybnf`, then reads `sorted_params_final.txt`.
    Returns None if the run fails (caller should fall back).
    """
    options = options or PyBNFOptions()
    paths.exp_dir.mkdir(parents=True, exist_ok=True)
    paths.conf_dir.mkdir(parents=True, exist_ok=True)
    paths.bngl_dir.mkdir(parents=True, exist_ok=True)

    n_obs = len(observed)

    # 1. Materialize conf + bngl. We force-regenerate the BNGL each call so
    # that stale b1/t1/... parameter declarations from a previous higher-K
    # run can't bleed into this fit (PyBNF would KeyError trying to look
    # them up in the uniform_var block).
    conf_path = conf_files.materialize_conf_from_template(state, paths, config)
    bngl_path = bngl_files.materialize_bngl_from_template(
        state, paths, config, force=True,
    )

    # 2. Add the time-varying-beta parameters + rewrite beta(), per model type.
    if config.model.model_type == "sirs_logistic":
        # `n_steps` is the transition count T (>=1). db1 ships in the template;
        # add db2..dbT. The centers tc_k, width sw, waning omega and population
        # N are FIXED in the template, so they cost no free parameters and need
        # no uniform_var. The bounds passed in must include db1..dbT.
        n_trans = max(1, int(n_steps))
        new_params = [f"db{k}" for k in range(2, n_trans + 1)]
        if new_params:
            bngl_files.add_parameters(bngl_path, new_params)
        bngl_files.set_beta_function(
            bngl_path, bngl_files.build_logistic_beta(n_trans))
    else:
        new_params = ([f"b{k}" for k in range(1, n_steps)]
                      + [f"t{k}" for k in range(1, n_steps)])
        if new_params:
            bngl_files.add_parameters(bngl_path, new_params)
        bngl_files.set_beta_function(
            bngl_path, bngl_files.build_piecewise_beta(n_steps))
    # AMCMC needs the simulation to run past the last observation so the
    # noise trajectory contains the forecast columns.
    sim_t_end = n_obs - 1 + max(0, forecast_horizon)
    bngl_files.set_simulation_window(
        bngl_path, t_start=0, t_end=sim_t_end, n_steps=sim_t_end,
    )

    # 3. Write the .exp file (overwrite each fit since week W changes).
    _write_exp(paths.exp_file(state), observed)

    # 4. Patch the conf: bounds + fit settings + bng path.
    bng_path = _find_bng_path()
    if bng_path is None:
        log.error("BNG2.pl not found in installed bionetgen package")
        return None
    conf_updates: dict = {
        "bng_command": str(bng_path),
        "fit_type": options.method,
        "population_size": options.popsize,
        "max_iterations": options.max_iter,
        "parallel_count": 2,
        "verbosity": 0,
    }
    if options.method == "am":
        # AMCMC-specific settings. PyBNF interprets `population_size` for
        # AMCMC as the number of parallel chains. popsize=1 on laptops;
        # popsize=4 on the Mac Studio gives multi-chain Gelman-Rubin
        # diagnostics. parallel_count == chain count so each chain runs
        # on its own subprocess thread.
        n_chains = max(1, int(options.popsize))
        conf_updates.update({
            "population_size": n_chains,
            "parallel_count": n_chains,
            "burn_in": options.burn_in,
            "adaptive": options.adaptive,
            "sample_every": options.sample_every,
            "output_noise_trajectory": "H_weekly",
            "continue_run": 0,
        })
    conf_files.update_keys(conf_path, conf_updates)
    # Replace (not just update) so stale b1/t1/... uniform_vars from a
    # higher-K previous run don't bleed into this fit.
    conf_files.replace_uniform_vars(conf_path, list(bounds))

    # 5. Clear stale results and run PyBNF.
    state_results = paths.results_for(state)
    if state_results.exists():
        shutil.rmtree(state_results, ignore_errors=True)
    state_results.mkdir(parents=True, exist_ok=True)
    log.debug("launching pybnf for %s (n_obs=%d, K=%d)", state, n_obs, n_steps)
    t0 = time.time()
    try:
        proc = subprocess.run(
            [options.resolved_binary(), "-c", str(conf_path), "-o", "-L", "warning"],
            capture_output=True, text=True,
            timeout=options.timeout_sec,
            cwd=paths.root,
        )
    except subprocess.TimeoutExpired:
        log.warning("pybnf timeout for %s after %.0fs", state, options.timeout_sec)
        return None
    if proc.returncode != 0:
        log.warning("pybnf failed for %s rc=%d:\n%s", state, proc.returncode, proc.stderr[-500:])
        return None
    elapsed = time.time() - t0

    # 6. Parse results into a FitResult shape.
    if options.method == "am":
        return _parse_amcmc_result(state, state_results, n_steps, elapsed)
    de = read_de_results(state_results, state)
    if de is None or de.population.empty:
        log.warning("pybnf produced no sorted_params_final for %s", state)
        return None
    log.info("pybnf(%s K=%d): best_obj=%.3f in %.1fs", state, n_steps, de.best_obj, elapsed)
    param_names = tuple(de.param_names)
    pop = de.population[list(param_names)].to_numpy(dtype=float)
    obj = de.population["Obj"].to_numpy(dtype=float)
    return FitResult(
        state=state,
        param_names=param_names,
        population=pop,
        objectives=obj,
        best_idx=int(np.argmin(obj)),
    )


def _parse_amcmc_result(
    state: str, state_results: Path, n_steps: int, elapsed: float,
) -> Optional[FitResult]:
    """Read AMCMC chain output and wrap it in a FitResult.

    PyBNF's AMCMC writes per-iteration parameter samples to
    `Results/A_MCMC/Runs/params_0.txt`. We treat the post-burn-in samples
    as a 'population' so the downstream analyzer code (bounds expansion,
    step recommendation) works without change. The noise trajectory at
    `Results/A_MCMC/Runs/traj_noise_<state>_H_weekly_chain_0.txt` is the
    thing quantile forecasts will read separately.
    """
    chain = read_amcmc_chain(state_results, state)
    if chain is None or chain.empty:
        log.warning("pybnf AMCMC produced no chain output for %s", state)
        return None
    param_cols = [c for c in chain.columns if c.endswith("__FREE")]
    if not param_cols:
        log.warning("AMCMC chain for %s has no FREE columns", state)
        return None
    pop = chain[param_cols].to_numpy(dtype=float)
    # PyBNF chain rows may have 'Obj' (neg log-likelihood). If not, set 0.
    obj = chain["Obj"].to_numpy(dtype=float) if "Obj" in chain.columns else np.zeros(len(pop))
    best_idx = int(np.argmin(obj)) if obj.std() > 0 else 0
    log.info("pybnf-am(%s K=%d): %d post-burn samples, best_obj=%.3f in %.1fs",
             state, n_steps, len(pop), obj[best_idx], elapsed)
    return FitResult(
        state=state,
        param_names=tuple(param_cols),
        population=pop,
        objectives=obj,
        best_idx=best_idx,
    )


def _write_exp(exp_path: Path, observed: np.ndarray) -> None:
    df = pd.DataFrame({
        "#time": np.arange(len(observed), dtype=int),
        "H_weekly": observed.astype(float),
    })
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(exp_path, sep="\t", index=False)
