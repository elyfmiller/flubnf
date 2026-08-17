"""Per-state slope_blend auto-tuning via re-quantile sweep.

For each state we already have AMCMC posterior trajectories on disk (the
expensive part). Picking the right `slope_blend` does NOT require re-fitting:
we re-anchor + re-quantile the existing trajectory for a sweep of candidate
blends and score each against a held-out actual.

This makes slope_blend a "free" hyperparameter we can re-tune retroactively
each week using last week's now-observed actuals — a cheap closed-loop on
top of the expensive AMCMC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from .amcmc import anchor_trajectories
from .quantiles import FLUSIGHT_QUANTILES
from .wis import wis as wis_score


# Default candidate sweep. Includes the adaptive setting (-1) and a coarse
# grid from 0 (pure model) to 0.6 (mostly persistence). Above 0.6 the
# correction clamp at np.clip(0.1, 10) kicks in for most horizons.
DEFAULT_CANDIDATES: tuple[float, ...] = (
    0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, -1.0,
)


@dataclass(frozen=True)
class SweepRow:
    slope_blend: float       # candidate; -1 means "adaptive"
    mean_wis: float
    per_horizon_wis: tuple[float, ...]
    n_horizons: int


@dataclass
class SlopeTuneResult:
    state: str
    rows: list[SweepRow] = field(default_factory=list)

    @property
    def best(self) -> Optional[SweepRow]:
        valid = [r for r in self.rows if np.isfinite(r.mean_wis)]
        if not valid:
            return None
        return min(valid, key=lambda r: r.mean_wis)

    @property
    def baseline(self) -> Optional[SweepRow]:
        """The slope_blend=0 row, our pre-tuning default."""
        for r in self.rows:
            if r.slope_blend == 0.0:
                return r
        return None

    def improvement_vs_baseline(self) -> Optional[float]:
        """How much mean WIS the best candidate buys vs slope_blend=0.

        Positive = improvement (lower WIS); negative = regression.
        Returns None if either reference is missing/invalid.
        """
        best = self.best
        base = self.baseline
        if best is None or base is None:
            return None
        if not (np.isfinite(best.mean_wis) and np.isfinite(base.mean_wis)):
            return None
        return base.mean_wis - best.mean_wis


def sweep_slope_blend(
    traj: np.ndarray,
    observed: np.ndarray,
    actuals: Mapping[int, float],
    *,
    state: str = "",
    candidates: Sequence[float] = DEFAULT_CANDIDATES,
    anchor_lookback: int = 3,
    phase_aware: bool = True,
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
) -> SlopeTuneResult:
    """Sweep slope_blend candidates and score each by mean WIS.

    Args:
        traj:      AMCMC posterior trajectories, shape (n_samples, n_weeks).
                   Must cover at least n_observed + max(horizons) columns.
        observed:  in-sample observed series (used to anchor + measure recent
                   growth). Length defines `n_observed`.
        actuals:   {horizon (1-indexed): observed_value_at_h} — the held-out
                   "truth" we score each candidate against. Horizons not in
                   this dict are skipped from the WIS aggregate.
        state:     informational only — recorded on the result for logging.
        candidates: slope_blend values to try. -1 triggers the adaptive
                    heuristic in amcmc.anchor_trajectories.
        anchor_lookback: forwarded to anchor_trajectories.
        phase_aware: forwarded to anchor_trajectories.

    Returns SlopeTuneResult with one SweepRow per candidate.
    """
    n_observed = int(len(observed))
    horizons = sorted(int(h) for h in actuals.keys() if int(h) >= 1)
    if not horizons:
        return SlopeTuneResult(state=state, rows=[])

    max_h = max(horizons)
    if traj.shape[1] < n_observed + max_h:
        # Not enough trajectory columns to cover the requested horizons.
        return SlopeTuneResult(state=state, rows=[])

    # Keep only finite trajectory rows once.
    finite = ~np.any(~np.isfinite(traj), axis=1)
    traj = traj[finite]
    if traj.shape[0] == 0:
        return SlopeTuneResult(state=state, rows=[])

    q_levels = np.array(quantile_levels)
    rows: list[SweepRow] = []
    obs_arr = np.asarray(observed, dtype=float)

    for sb in candidates:
        try:
            anchored = anchor_trajectories(
                traj, obs_arr,
                mode="multiplicative",
                lookback=anchor_lookback,
                slope_blend=float(sb),
                phase_aware=phase_aware,
            )
        except Exception:
            rows.append(SweepRow(
                slope_blend=float(sb), mean_wis=float("nan"),
                per_horizon_wis=tuple([float("nan")] * len(horizons)),
                n_horizons=0,
            ))
            continue

        per_h: list[float] = []
        for h in horizons:
            col = anchored[:, n_observed + h - 1]
            if not np.any(np.isfinite(col)):
                per_h.append(float("nan"))
                continue
            qs = np.quantile(col[np.isfinite(col)], q_levels)
            qmap = {float(q): float(v) for q, v in zip(q_levels, qs)}
            try:
                w = wis_score(qmap, float(actuals[h])).wis
            except Exception:
                w = float("nan")
            per_h.append(float(w))

        finite_h = [v for v in per_h if np.isfinite(v)]
        mean = float(np.mean(finite_h)) if finite_h else float("nan")
        rows.append(SweepRow(
            slope_blend=float(sb),
            mean_wis=mean,
            per_horizon_wis=tuple(per_h),
            n_horizons=len(finite_h),
        ))
    return SlopeTuneResult(state=state, rows=rows)


def recommend_blend(
    result: SlopeTuneResult,
    *,
    min_improvement: float = 0.05,
    min_horizons: int = 2,
) -> Optional[float]:
    """Convert a sweep result into a tuning recommendation.

    We only recommend changing slope_blend away from the baseline when:
      - The best candidate is strictly better than baseline by at least
        `min_improvement` mean-WIS units (avoid noise-driven flapping).
      - The sweep scored at least `min_horizons` horizons (avoid acting
        on a single h=1 lucky pick).

    Returns the recommended slope_blend, or None if we should hold the
    current setting.
    """
    best = result.best
    base = result.baseline
    if best is None or base is None:
        return None
    if best.n_horizons < min_horizons:
        return None
    if not (np.isfinite(best.mean_wis) and np.isfinite(base.mean_wis)):
        return None
    if base.mean_wis - best.mean_wis < min_improvement:
        return None
    if best.slope_blend == base.slope_blend:
        return None
    return best.slope_blend
