"""Auto-pipeline orchestrator.

Threads together: parse previous results -> recommend changes -> (optionally)
apply them to .conf / .bngl files. This is the "step 3 + 4" of the user's
weekly workflow:

   (3) statistically analyze last week's run
   (4) apply bounds expansion / piecewise step changes for the new run

Recommendations are *not* applied unless `apply=True`. The CLI exposes a
dry-run by default and an `--apply` flag.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import analysis, bngl_files, conf_files, results, simulate
from .analysis import (BoundsRecommendation, StateAnalysis,
                       StepRecommendation, recommend_bounds,
                       recommend_piecewise_step)
from .config import FluBNFConfig
from .conf_files import FreeParam
from .constants import JURISDICTIONS
from .paths import WorkspacePaths

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Free-parameter discovery
# ---------------------------------------------------------------------------
def _count_beta_steps(uniform_vars: Iterable[FreeParam]) -> int:
    """Count how many b0, b1, ... parameters are in the current bounds."""
    bs = sorted(
        int(fp.short[1:]) for fp in uniform_vars
        if fp.short.startswith("b") and fp.short[1:].isdigit()
    )
    return len(bs)


# ---------------------------------------------------------------------------
# Per-state analysis
# ---------------------------------------------------------------------------
def analyze_state(
    state: str,
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    top_n: int = 50,
    boundary_tol: float = 0.05,
    crowding_threshold: float = 0.30,
    expand_factor: float = 0.5,
    min_run_length: int = 3,
    min_relative_error: float = 0.20,
) -> StateAnalysis:
    """Analyze one state's previous-run output, return recommendations.

    Pure read-only: never mutates files."""
    a = StateAnalysis(state=state, best_obj=None, n_population=0)
    state_results = paths.results_for(state)
    de = results.read_de_results(state_results, state)
    if de is None:
        a.notes.append("no DE results (sorted_params_final.txt missing)")
        return a

    a.best_obj = de.best_obj
    a.n_population = len(de.population)

    # --- Bounds expansion ---
    conf_path = paths.conf_file(state)
    if not conf_path.exists():
        a.notes.append(f"conf file missing at {conf_path}")
        return a
    current_bounds = conf_files.read_uniform_vars(conf_path)
    a.bounds_recs = recommend_bounds(
        de.population, current_bounds,
        top_n=top_n,
        boundary_tol=boundary_tol,
        crowding_threshold=crowding_threshold,
        expand_factor=expand_factor,
    )

    # --- Piecewise step recommendation ---
    exp_path = paths.exp_file(state)
    if not exp_path.exists():
        a.notes.append(f"exp file missing at {exp_path}")
        return a
    exp_df = pd.read_csv(exp_path, sep="\t")
    if exp_df.empty:
        a.notes.append("exp file empty (no observed data)")
        return a
    observed = exp_df["H_weekly"].to_numpy(dtype=float)
    try:
        predicted = simulate.predict_weekly(
            de.best_params.to_dict(), len(observed),
        )
    except Exception as e:
        a.notes.append(f"simulate failed: {e}")
        return a
    n_steps = _count_beta_steps(current_bounds)
    a.step_rec = recommend_piecewise_step(
        predicted=predicted, observed=observed,
        n_current_steps=n_steps,
        min_run_length=min_run_length,
        min_relative_error=min_relative_error,
    )
    return a


def analyze_all(
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    states: Iterable[str] = JURISDICTIONS,
    **kwargs,
) -> list[StateAnalysis]:
    return [analyze_state(s, paths, config, **kwargs) for s in states]


# ---------------------------------------------------------------------------
# Apply recommendations
# ---------------------------------------------------------------------------
@dataclass
class AppliedChange:
    state: str
    bounds_changed: list[str] = field(default_factory=list)  # FREE names updated
    bounds_added: list[str] = field(default_factory=list)    # new FREE names
    new_n_steps: int = 0    # the post-apply piecewise step count


def apply_recommendations(
    analyses: Iterable[StateAnalysis],
    paths: WorkspacePaths,
    config: FluBNFConfig,
    *,
    new_step_initial_b: tuple[float, float] = (0.05, 0.10),
    new_step_initial_t: tuple[float, float] = (1.0, 8.0),
) -> list[AppliedChange]:
    """Apply each analysis's recommendations to .conf and .bngl files.

    For bounds-only changes: edit `uniform_var` lines in the .conf.
    For a new piecewise step (K -> K+1): add b{K}/t{K} as uniform_vars,
    add them as BNGL params, rewrite the beta() function, and (optionally)
    bump the simulate t_end / n_steps in the .bngl actions block.
    """
    applied: list[AppliedChange] = []
    for a in analyses:
        change = AppliedChange(state=a.state)
        conf_path = paths.conf_file(a.state)
        bngl_path = paths.bngl_file(a.state)
        if not conf_path.exists() or not bngl_path.exists():
            continue

        # 1. Bounds expansion.
        new_bounds: dict[str, tuple[float, float]] = {}
        for r in a.bounds_recs:
            if not r.changed:
                continue
            new_bounds[r.param] = (r.new_low, r.new_high)
            change.bounds_changed.append(r.param)
        if new_bounds:
            conf_files.update_uniform_vars(conf_path, new_bounds)

        # 2. New piecewise step.
        if a.step_rec and a.step_rec.needs_new_step:
            current = conf_files.read_uniform_vars(conf_path)
            current_k = _count_beta_steps(current)
            new_k = current_k + 1
            new_b = f"b{new_k - 1}__FREE"   # zero-indexed: b{K} for K-th segment
            new_t = f"t{new_k - 1}__FREE"
            # Append new uniform_vars.
            conf_files.update_uniform_vars(conf_path, {
                new_b: new_step_initial_b,
                new_t: new_step_initial_t,
            })
            change.bounds_added.extend([new_b, new_t])
            # Add to BNGL params, rewrite beta().
            bngl_files.add_parameters(bngl_path, [new_b.split("__")[0],
                                                  new_t.split("__")[0]])
            beta_expr = bngl_files.build_piecewise_beta(new_k)
            bngl_files.set_beta_function(bngl_path, beta_expr)
            change.new_n_steps = new_k
        else:
            current = conf_files.read_uniform_vars(conf_path)
            change.new_n_steps = _count_beta_steps(current)

        applied.append(change)
    return applied


# ---------------------------------------------------------------------------
# Summary reporting
# ---------------------------------------------------------------------------
def analyses_to_dataframe(analyses: Iterable[StateAnalysis]) -> pd.DataFrame:
    rows = []
    for a in analyses:
        bounds_summary = "; ".join(
            f"{r.param}:{r.old_low:.3g}-{r.old_high:.3g}->{r.new_low:.3g}-{r.new_high:.3g}"
            for r in a.bounds_recs if r.changed
        )
        rows.append({
            "state": a.state,
            "best_obj": a.best_obj,
            "n_pop": a.n_population,
            "n_bounds_changes": sum(1 for r in a.bounds_recs if r.changed),
            "needs_new_step": (a.step_rec.needs_new_step
                               if a.step_rec else None),
            "step_reason": a.step_rec.reason if a.step_rec else None,
            "bounds_summary": bounds_summary,
            "notes": "; ".join(a.notes),
        })
    return pd.DataFrame(rows)
