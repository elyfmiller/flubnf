"""Parse PyBNF run outputs.

PyBNF (with `fit_type = de`) writes per-state into:

    <results_dir>/<State>/
        Results/
            sorted_params_final.txt    # final population, best-first
            sorted_params_0.txt        # intermediate snapshots
            <State>_gen<NN>ind<MM>.bngl
            <State>.conf
        Initialize/
            <State>_gen_net.bngl
            <State>_gen_net.net

For `fit_type = am` (AMCMC) there's an additional:

    Results/A_MCMC/Runs/traj_noise_<State>_fluH_chain_0.txt   # noise samples
    Results/A_MCMC/Runs/params_0.txt                          # chain params

This module is purely a *parser*: no decisions, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DEResults:
    """Final differential-evolution population for a single state."""

    state: str
    results_dir: Path
    population: pd.DataFrame   # columns: Simulation, Obj, <param>__FREE...
    param_names: tuple[str, ...]  # the FREE param column names

    @property
    def best_obj(self) -> float:
        return float(self.population["Obj"].iloc[0])

    @property
    def best_params(self) -> pd.Series:
        return self.population.iloc[0][list(self.param_names)]


def read_de_results(state_results_dir: Path, state: str) -> Optional[DEResults]:
    """Read `sorted_params_final.txt` for a DE run. Returns None if missing.

    The file is tab-separated with a header line starting with `#`. The first
    real column ('Simulation') is blank in the leading position.
    """
    p = state_results_dir / "Results" / "sorted_params_final.txt"
    if not p.exists():
        return None
    df = _read_pybnf_table(p)
    if df is None or df.empty:
        return None
    param_cols = tuple(c for c in df.columns if c.endswith("__FREE"))
    return DEResults(
        state=state,
        results_dir=state_results_dir,
        population=df,
        param_names=param_cols,
    )


def read_de_snapshots(state_results_dir: Path) -> list[pd.DataFrame]:
    """Read all `sorted_params_N.txt` snapshots (excluding backup), in order.
    Used for convergence diagnostics over generations."""
    base = state_results_dir / "Results"
    if not base.exists():
        return []
    snapshots: list[pd.DataFrame] = []
    files = sorted(
        base.glob("sorted_params_[0-9]*.txt"),
        key=lambda f: _snapshot_index(f.name),
    )
    for f in files:
        df = _read_pybnf_table(f)
        if df is not None:
            snapshots.append(df)
    return snapshots


def read_amcmc_chain(state_results_dir: Path, state: str) -> Optional[pd.DataFrame]:
    """Read the AMCMC chain output (`params_0.txt`).

    PyBNF writes the header tab-separated but data rows SPACE-separated, so
    we parse on `\\s+` rather than tab.
    """
    p = state_results_dir / "Results" / "A_MCMC" / "Runs" / "params_0.txt"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, sep=r"\s+", engine="python")
    except Exception:
        return None
    return df


def read_amcmc_traj(state_results_dir: Path, state: str) -> Optional[np.ndarray]:
    """Read the noise-augmented predictive trajectory used to build FluSight
    quantile forecasts. Shape: (n_samples, n_weeks)."""
    p = (state_results_dir / "Results" / "A_MCMC" / "Runs"
         / f"traj_noise_{state}_fluH_chain_0.txt")
    if not p.exists():
        return None
    return np.genfromtxt(p)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_pybnf_table(path: Path) -> Optional[pd.DataFrame]:
    """PyBNF tables are tab-separated with a `#\\tHeader1\\tHeader2...` line
    and rows that start with a leading tab (the implicit blank first col).
    """
    try:
        df = pd.read_csv(path, sep="\t", comment=None)
    except Exception:
        return None
    if df.empty:
        return None
    # The header begins with "#" — pandas reads it as column "#". Rename to
    # a sentinel and drop blank leading columns.
    df = df.rename(columns={"#": "_marker"})
    drop = [c for c in df.columns if c.startswith("Unnamed")]
    df = df.drop(columns=drop, errors="ignore")
    if "_marker" in df.columns:
        df = df.drop(columns="_marker")
    return df


def _snapshot_index(name: str) -> int:
    """Extract the integer N from `sorted_params_N.txt`. Used for sort key."""
    stem = name.removesuffix(".txt").rsplit("_", 1)[-1]
    try:
        return int(stem)
    except ValueError:
        return -1
