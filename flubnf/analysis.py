"""Statistical decision rules for the FluBNF auto-pipeline.

Two questions get answered here, both via deterministic, auditable rules:

  1. **Bounds expansion** — do any uniform_var bounds need widening because the
     best fits are pushed up against the prior boundary?
  2. **Piecewise complexity** — does the beta(t) function need another step
     because recent observations are systematically over- or under-predicted
     by the current K-step fit?

Both functions take parsed data in / return recommendations out. They never
mutate files; the orchestrator in `auto.py` applies the recommendations.

Justification for hard-coded rules over AI inference:
  - Reproducibility: the same input must yield the same decision week-to-week
    for a manuscript.
  - Auditability: a reviewer can read these ~50 lines and replicate the rule.
  - Cheap: runs in milliseconds across all 52 jurisdictions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

from .conf_files import FreeParam


# ===========================================================================
# 1) Bounds expansion
# ===========================================================================
@dataclass(frozen=True)
class BoundsRecommendation:
    param: str                 # e.g. "b0__FREE"
    old_low: float
    old_high: float
    new_low: float
    new_high: float
    reason: str
    top_n_frac_at_low: float   # diagnostic: % of top-N within tol of low
    top_n_frac_at_high: float

    @property
    def changed(self) -> bool:
        return (self.new_low != self.old_low) or (self.new_high != self.old_high)


def recommend_bounds(
    population: pd.DataFrame,
    current_bounds: Sequence[FreeParam],
    *,
    top_n: int = 50,
    boundary_tol: float = 0.05,
    crowding_threshold: float = 0.30,
    expand_factor: float = 0.5,
    keep_positive: bool = True,
) -> list[BoundsRecommendation]:
    """Decide which uniform_var bounds need expansion.

    Algorithm (per parameter):
      1. Take the top `top_n` best fits (lowest Obj) from `population`.
      2. For each side (low / high), compute the fraction of those fits that
         sit within `boundary_tol * (high - low)` of that side.
      3. If that fraction exceeds `crowding_threshold`, expand that side by
         `expand_factor * (high - low)`.
      4. If `keep_positive`, never let the low bound go below 0.

    Args:
        population:           DE population table sorted ascending by Obj
                              (as returned by `results.read_de_results`).
        current_bounds:       Current uniform_var entries from the conf file.
        top_n:                Number of best individuals to inspect.
        boundary_tol:         Fraction of the range that counts as "at the
                              boundary".
        crowding_threshold:   If at least this fraction of the top-N is near
                              a boundary, recommend expansion.
        expand_factor:        How much to widen the bound, as a fraction of
                              the current range.
        keep_positive:        Clamp low bound at 0 (most epi params should
                              be non-negative).
    """
    if population.empty:
        return []
    top = population.head(top_n)
    recs: list[BoundsRecommendation] = []
    for fp in current_bounds:
        col = fp.name
        if col not in top.columns:
            continue
        values = pd.to_numeric(top[col], errors="coerce").dropna().to_numpy()
        if len(values) == 0:
            continue
        rng = fp.high - fp.low
        if rng <= 0:
            continue
        tol = boundary_tol * rng
        frac_low = float(np.mean(values <= fp.low + tol))
        frac_high = float(np.mean(values >= fp.high - tol))

        new_low, new_high = fp.low, fp.high
        reasons: list[str] = []
        if frac_low >= crowding_threshold:
            new_low = fp.low - expand_factor * rng
            if keep_positive:
                new_low = max(0.0, new_low)
            reasons.append(
                f"{frac_low:.0%} of top-{top_n} within {boundary_tol:.0%} of low bound"
            )
        if frac_high >= crowding_threshold:
            new_high = fp.high + expand_factor * rng
            reasons.append(
                f"{frac_high:.0%} of top-{top_n} within {boundary_tol:.0%} of high bound"
            )
        if not reasons:
            continue
        recs.append(BoundsRecommendation(
            param=col,
            old_low=fp.low, old_high=fp.high,
            new_low=new_low, new_high=new_high,
            reason="; ".join(reasons),
            top_n_frac_at_low=frac_low,
            top_n_frac_at_high=frac_high,
        ))
    return recs


# ===========================================================================
# 2) Piecewise complexity (residual-based + AICc model comparison)
# ===========================================================================
@dataclass(frozen=True)
class StepRecommendation:
    needs_new_step: bool
    n_current_steps: int
    recent_residuals: list[float]
    residual_run_length: int  # length of trailing same-sign run
    relative_error: float     # |residual| / observed, averaged over the run
    reason: str

    @property
    def n_proposed_steps(self) -> int:
        return self.n_current_steps + 1 if self.needs_new_step else self.n_current_steps


def recommend_piecewise_step(
    predicted: np.ndarray,
    observed: np.ndarray,
    n_current_steps: int,
    *,
    min_run_length: int = 3,
    min_relative_error: float = 0.20,
    max_steps: int = 8,
) -> StepRecommendation:
    """Decide whether the piecewise beta needs another segment.

    Rule (sign + magnitude):
      Look at the trailing residuals (predicted - observed). If the last
      `min_run_length` residuals all share the same sign AND their mean
      |residual|/observed exceeds `min_relative_error`, the model is
      systematically biased on the recent window. Add a step.

    This is intentionally conservative — we don't want to over-fit by
    adding a new step every week. The AICc comparison in
    `compare_models_aicc()` is the second gate before the decision is
    actually committed.
    """
    if len(predicted) != len(observed):
        raise ValueError(
            f"length mismatch: predicted={len(predicted)} observed={len(observed)}"
        )
    if len(observed) == 0 or n_current_steps >= max_steps:
        return StepRecommendation(
            needs_new_step=False, n_current_steps=n_current_steps,
            recent_residuals=[], residual_run_length=0,
            relative_error=0.0,
            reason="cap reached" if n_current_steps >= max_steps else "no data",
        )

    residuals = (np.asarray(predicted, dtype=float)
                 - np.asarray(observed, dtype=float))

    # Trailing same-sign run.
    sign = np.sign(residuals[-1]) if residuals[-1] != 0 else 0.0
    run = 0
    for r in residuals[::-1]:
        if (sign > 0 and r > 0) or (sign < 0 and r < 0):
            run += 1
        else:
            break

    recent = residuals[-min_run_length:]
    obs_recent = np.asarray(observed[-min_run_length:], dtype=float)
    safe = np.where(np.abs(obs_recent) < 1e-6, 1e-6, np.abs(obs_recent))
    rel_err = float(np.mean(np.abs(recent) / safe))

    needs = (run >= min_run_length) and (rel_err >= min_relative_error)
    reason = (
        f"trailing same-sign run length={run} (>= {min_run_length}), "
        f"mean rel. error={rel_err:.2f} (>= {min_relative_error})"
        if needs else
        f"run={run} (need {min_run_length}), rel.err={rel_err:.2f} "
        f"(need {min_relative_error})"
    )
    return StepRecommendation(
        needs_new_step=needs,
        n_current_steps=n_current_steps,
        recent_residuals=list(residuals[-min_run_length:].astype(float)),
        residual_run_length=run,
        relative_error=rel_err,
        reason=reason,
    )


# ===========================================================================
# 2b) Bidirectional K control — recommend removing redundant piecewise steps
# ===========================================================================
@dataclass(frozen=True)
class StepRemovalRecommendation:
    """When a piecewise segment's posterior is statistically indistinguishable
    from a neighbor, the model has more complexity than the data warrants."""
    needs_removal: bool
    step_to_remove: Optional[int]   # 1-based index (e.g. 2 means remove b1/t1)
    n_current_steps: int
    reason: str
    similarity_ratio: float        # |b_K_med - b_{K-1}_med| / b_{K-1}_med


def recommend_remove_step(
    population: "pd.DataFrame",
    *,
    min_relative_diff: float = 0.10,
    min_iqr_overlap: float = 0.50,
    n_top: int = 50,
) -> StepRemovalRecommendation:
    """Decide if a piecewise-beta step is redundant and should be removed.

    A step K is redundant when its `b_K` posterior is statistically very
    close to `b_{K-1}`'s — meaning the piecewise function effectively has
    the same beta value across two consecutive segments, so the K-th
    segment isn't capturing distinct dynamics.

    Rules:
      - |median(b_K) - median(b_{K-1})| / median(b_{K-1}) < min_relative_diff
        AND
      - IQR(b_K) ∩ IQR(b_{K-1}) / IQR_union > min_iqr_overlap

    If multiple steps look redundant, we recommend removing the LAST one
    (the most recent addition is the most likely to be unjustified).

    Args:
        population:        DE final population OR AMCMC chain post-burn,
                           sorted with best fits first.
        min_relative_diff: Threshold for "medians are too close".
        min_iqr_overlap:   Threshold for "IQRs substantially overlap".
        n_top:             Use only the top-N best fits for the comparison.
    """
    if population.empty:
        return StepRemovalRecommendation(
            needs_removal=False, step_to_remove=None, n_current_steps=0,
            reason="empty population", similarity_ratio=0.0,
        )
    sample = population.head(n_top)
    # Collect b_K columns in order.
    b_cols = sorted(
        [c for c in sample.columns
         if c.startswith("b") and c.endswith("__FREE")
         and c[1:].split("__")[0].isdigit()],
        key=lambda c: int(c[1:].split("__")[0]),
    )
    if len(b_cols) < 2:
        return StepRemovalRecommendation(
            needs_removal=False, step_to_remove=None,
            n_current_steps=len(b_cols),
            reason="fewer than 2 piecewise segments",
            similarity_ratio=0.0,
        )

    # Walk from last to second segment, flag the first redundant pair.
    redundant_idx: Optional[int] = None
    best_similarity = 0.0
    best_reason = ""
    for k in range(len(b_cols) - 1, 0, -1):
        prev = pd.to_numeric(sample[b_cols[k - 1]], errors="coerce").dropna().to_numpy()
        curr = pd.to_numeric(sample[b_cols[k]], errors="coerce").dropna().to_numpy()
        if len(prev) == 0 or len(curr) == 0:
            continue
        med_prev = float(np.median(prev))
        med_curr = float(np.median(curr))
        if med_prev == 0:
            continue
        rel_diff = abs(med_curr - med_prev) / abs(med_prev)
        # IQR overlap as Jaccard of [25%, 75%] intervals.
        p_lo, p_hi = np.percentile(prev, [25, 75])
        c_lo, c_hi = np.percentile(curr, [25, 75])
        overlap = max(0.0, min(p_hi, c_hi) - max(p_lo, c_lo))
        union = max(p_hi, c_hi) - min(p_lo, c_lo)
        iqr_overlap = overlap / union if union > 0 else 0.0
        if rel_diff < min_relative_diff and iqr_overlap > min_iqr_overlap:
            redundant_idx = k
            best_similarity = rel_diff
            best_reason = (
                f"b{k} median={med_curr:.3g} ≈ b{k-1} median={med_prev:.3g} "
                f"(rel_diff={rel_diff:.2%}); IQR overlap={iqr_overlap:.0%}"
            )
            break

    if redundant_idx is None:
        return StepRemovalRecommendation(
            needs_removal=False, step_to_remove=None,
            n_current_steps=len(b_cols),
            reason="all segments statistically distinguishable",
            similarity_ratio=0.0,
        )
    return StepRemovalRecommendation(
        needs_removal=True,
        step_to_remove=redundant_idx,
        n_current_steps=len(b_cols),
        reason=best_reason,
        similarity_ratio=best_similarity,
    )


@dataclass(frozen=True)
class ModelComparison:
    aicc_k: float
    aicc_kp1: float
    delta_aicc: float        # aicc_kp1 - aicc_k; negative favors the larger model
    favored: str             # "K", "K+1", or "tie"
    n_obs: int

    @property
    def improves(self) -> bool:
        return self.favored == "K+1"


def compare_models_aicc(
    residuals_k: np.ndarray,
    residuals_kp1: np.ndarray,
    n_params_k: int,
    n_params_kp1: int,
    *,
    delta_threshold: float = 2.0,
) -> ModelComparison:
    """Compare K-step vs (K+1)-step fits via AICc.

    Assumes Gaussian residuals (a fine approximation for AICc decisions, even
    when the actual fit objective is neg_bin) so:

        AIC = 2k + n * ln(RSS / n)
        AICc = AIC + 2k(k+1)/(n - k - 1)

    `delta_threshold` follows the common "delta > 2" rule of thumb for
    meaningful AIC improvement.
    """
    n = len(residuals_k)
    if n != len(residuals_kp1):
        raise ValueError("residual arrays must be the same length")
    if n <= max(n_params_k, n_params_kp1) + 1:
        # AICc is undefined; fall back to AIC.
        aic_k = _aic_gaussian(residuals_k, n_params_k)
        aic_kp1 = _aic_gaussian(residuals_kp1, n_params_kp1)
        delta = aic_kp1 - aic_k
        favored = "K+1" if delta < -delta_threshold else (
            "K" if delta > delta_threshold else "tie")
        return ModelComparison(aic_k, aic_kp1, delta, favored, n)
    aicc_k = _aicc_gaussian(residuals_k, n_params_k)
    aicc_kp1 = _aicc_gaussian(residuals_kp1, n_params_kp1)
    delta = aicc_kp1 - aicc_k
    if delta < -delta_threshold:
        favored = "K+1"
    elif delta > delta_threshold:
        favored = "K"
    else:
        favored = "tie"
    return ModelComparison(aicc_k, aicc_kp1, delta, favored, n)


def _aic_gaussian(residuals: np.ndarray, k: int) -> float:
    n = len(residuals)
    rss = float(np.sum(np.asarray(residuals) ** 2))
    if rss <= 0:
        rss = 1e-12
    return 2 * k + n * math.log(rss / n)


def _aicc_gaussian(residuals: np.ndarray, k: int) -> float:
    aic = _aic_gaussian(residuals, k)
    n = len(residuals)
    return aic + (2 * k * (k + 1)) / (n - k - 1)


# ===========================================================================
# 3) Per-state summary
# ===========================================================================
@dataclass
class StateAnalysis:
    state: str
    best_obj: Optional[float]
    n_population: int
    bounds_recs: list[BoundsRecommendation] = field(default_factory=list)
    step_rec: Optional[StepRecommendation] = None
    notes: list[str] = field(default_factory=list)

    @property
    def needs_intervention(self) -> bool:
        if any(r.changed for r in self.bounds_recs):
            return True
        if self.step_rec and self.step_rec.needs_new_step:
            return True
        return False
