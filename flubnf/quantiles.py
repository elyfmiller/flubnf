"""Generate FluSight-style quantile forecasts from a DE fit.

Each FluSight submission supplies 23 quantiles at horizons 0..3 (or 1..4
depending on the season). The quantiles are computed from samples of the
predictive distribution.

Our predictive distribution is the marginal of the joint over:
  (parameter posterior approximation × negative-binomial observation noise)

The parameter posterior is approximated by the top-N members of the DE
final population (a cheap MAP-bootstrap proxy for a real Bayesian posterior).
On top of each member's deterministic trajectory we add negative-binomial
observation noise with the member's own `r` parameter, parameterized to
match PyBNF's `neg_bin_dynamic` objective:

    mean μ = H_weekly(t)
    p     = r / (r + μ)
    sample ~ NegBinomial(n=r, p=p)

This module produces both:
  - `sample_trajectories(...)` -> raw matrix of samples (n_samples × n_weeks)
  - `quantile_forecast(...)` -> per-horizon quantile dict matching FluSight

It does NOT depend on PyBNF — the FitResult is engine-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .fitting import FitResult
from .simulate import predict_weekly


# Standard 23 FluSight quantile levels.
FLUSIGHT_QUANTILES: tuple[float, ...] = (
    0.01, 0.025, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50,
    0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.975, 0.99,
)


def sample_trajectories(
    fit_result: FitResult,
    n_weeks: int,
    *,
    top_n: int = 80,
    samples_per_member: int = 50,
    seed: int = 0,
    model_type: str = "sir_piecewise",
    fixed_params: Optional[dict] = None,
) -> np.ndarray:
    """Generate Monte Carlo samples of the predictive H_weekly trajectory.

    Args:
        fit_result:           DE population + best fit.
        n_weeks:              How many weeks to predict (full trajectory length).
        top_n:                Use only the top-N members by Obj (sorted asc).
        samples_per_member:   Negative-binomial obs noise samples per member.
        seed:                 RNG seed.

    Returns:
        Array of shape (top_n * samples_per_member, n_weeks).
    """
    rng = np.random.default_rng(seed)

    order = np.argsort(fit_result.objectives)
    top_idx = order[: min(top_n, len(order))]
    param_names = list(fit_result.param_names)
    pop = fit_result.population[top_idx]

    r_col = _find_param_col(param_names, "r")

    n_members = len(top_idx)
    n_samples = n_members * samples_per_member
    out = np.empty((n_samples, n_weeks), dtype=float)

    for i, params_arr in enumerate(pop):
        params = dict(zip(param_names, params_arr))
        # SIRS: merge the FIXED structural params (sw, tc_k, N, omega) that the
        # fitted population does not carry, and route through the SIRS mirror.
        if fixed_params:
            params = {**fixed_params, **params}
        try:
            traj = predict_weekly(params, n_weeks, model_type=model_type)
        except Exception:
            out[i * samples_per_member:(i + 1) * samples_per_member] = np.nan
            continue
        r = float(params.get(r_col, 50.0)) if r_col else 50.0
        r = max(r, 0.5)  # numerical floor
        mu = np.maximum(traj, 1e-9)
        # negbin parameterization: n=r, p=r/(r+mu)
        p = r / (r + mu)
        # Draw samples_per_member samples per weekly mean, broadcasting.
        block = rng.negative_binomial(
            n=r, p=p[None, :], size=(samples_per_member, n_weeks),
        )
        out[i * samples_per_member:(i + 1) * samples_per_member] = block
    return out


@dataclass(frozen=True)
class QuantileForecast:
    """Per-horizon quantile arrays. `quantiles` has shape (n_quantiles, n_horizons)."""
    horizons: tuple[int, ...]
    quantile_levels: tuple[float, ...]
    quantiles: np.ndarray
    point: np.ndarray   # median forecast (one per horizon), for convenience

    def to_dict(self) -> dict:
        out: dict = {}
        for j, h in enumerate(self.horizons):
            out[h] = {
                float(q): float(self.quantiles[i, j])
                for i, q in enumerate(self.quantile_levels)
            }
        return out


def clip_forecast(qf: "QuantileForecast", cap: float) -> "QuantileForecast":
    """Clip every quantile + the point forecast to [0, cap].

    A forecast-sanity guard: an occasional numerically-unstable fit (stiff ODE
    integration or neg-bin noise blowup) can emit physically-impossible
    trajectories (e.g. 10^10 admissions in a 39M-person state). Left unchecked,
    one such week dominates WIS and — worse — could reach a real submission.
    `cap` should be a generous physical ceiling (e.g. 20x the largest observed
    week) so legitimate surges pass untouched while absurd values are tamed.

    DANGER — prefer `diagnose_forecast()` + a real fallback. Clipping a blown-up
    forecast pushes EVERY quantile onto the same ceiling, turning it into a
    zero-width point mass. WIS punishes that about as hard as the blowup it was
    meant to tame. Measured on the 2025-26 SIR backtest: 11 of 4784 cells
    saturated this way (New York 20x3870 = 77400, Louisiana 20x433 = 8660) and
    carried 49.4% of ALL WIS — mean 51,474 vs 133 for a normal cell. Guarding
    them moved relWIS 2.291 -> 1.166. See docs/RETROSPECTIVE_2026-07.md.
    """
    return QuantileForecast(
        horizons=qf.horizons,
        quantile_levels=qf.quantile_levels,
        quantiles=np.clip(qf.quantiles, 0.0, cap),
        point=np.clip(qf.point, 0.0, cap),
    )


@dataclass(frozen=True)
class ForecastDiagnosis:
    """Verdict on whether a forecast is fit to emit, and why not."""
    usable: bool
    reasons: tuple[str, ...]
    degenerate_horizons: tuple[int, ...]

    def __bool__(self) -> bool:      # `if diagnose_forecast(qf): ...`
        return self.usable


def diagnose_forecast(qf: "QuantileForecast", *, cap: Optional[float] = None,
                      last_observed: Optional[float] = None,
                      max_step: float = 20.0,
                      min_rel_width: float = 1e-9) -> ForecastDiagnosis:
    """Structural validity check on a quantile forecast, before it is emitted.

    These are failures no epidemiological argument can excuse — a distribution
    whose 2.5th and 97.5th percentiles coincide is not a forecast, whatever
    produced it. Checked per horizon:

      * ZERO WIDTH — q_hi == q_lo. The signature of `clip_forecast` saturating,
        and the single most expensive defect measured in this pipeline.
      * NON-MONOTONE quantiles — a sorting/indexing fault upstream.
      * NEGATIVE or non-finite values.
      * ABSURD LEVEL — median more than `max_step`x the last observation. This
        is the blowup that `clip_forecast` was built to catch; catching it HERE
        lets the caller substitute a real distribution instead of a point mass.

    Returns a verdict rather than mutating, so the caller decides the remedy
    (persistence fallback is the sane one — see
    `flubnf.baseline_forecast.persistence_quantile_forecast`).
    """
    reasons: list[str] = []
    degenerate: list[int] = []
    q = np.asarray(qf.quantiles, dtype=float)
    if q.size == 0:
        return ForecastDiagnosis(False, ("empty forecast",), ())
    if not np.all(np.isfinite(q)):
        reasons.append("non-finite quantiles")
    if np.any(q < 0):
        reasons.append("negative quantiles")
    for j, h in enumerate(qf.horizons):
        col = q[:, j]
        if not np.all(np.isfinite(col)):
            degenerate.append(h)
            continue
        span = float(col.max() - col.min())
        scale = max(abs(float(np.median(col))), 1.0)
        if span <= min_rel_width * scale:
            reasons.append(f"h={h}: zero-width predictive distribution "
                           f"(all quantiles == {col[0]:.6g})")
            degenerate.append(h)
        if np.any(np.diff(col) < -1e-9 * scale):
            reasons.append(f"h={h}: non-monotone quantiles")
            degenerate.append(h)
        if last_observed is not None and last_observed > 0:
            med = float(np.median(col))
            if med > max_step * last_observed:
                reasons.append(f"h={h}: median {med:.3g} exceeds {max_step:g}x "
                               f"last observed ({last_observed:.3g})")
                degenerate.append(h)
    if cap is not None and float(np.nanmax(q)) >= cap:
        reasons.append(f"forecast reaches the sanity cap ({cap:.3g}) — "
                       "clipping would flatten it to a point mass")
    return ForecastDiagnosis(not reasons, tuple(reasons),
                             tuple(sorted(set(degenerate))))


def quantile_forecast(
    fit_result: FitResult,
    n_observed: int,
    horizons: Sequence[int],
    *,
    top_n: int = 80,
    samples_per_member: int = 50,
    seed: int = 0,
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
    observed: Optional[np.ndarray] = None,
    anchor: bool = True,
    anchor_mode: str = "multiplicative",
    anchor_lookback: int = 3,
    anchor_slope_blend: float = 0.0,
    phase_aware: bool = True,
    model_type: str = "sir_piecewise",
    fixed_params: Optional[dict] = None,
) -> QuantileForecast:
    """Compute FluSight-style quantile forecasts at each horizon.

    Horizon h corresponds to the predicted observation at time index
    n_observed + h - 1 (1-indexed), matching `flubnf.backtest.forecast`.

    `anchor` + `observed`: when True, shift each sample trajectory so its
    value at the last observed week matches the actual observation. This
    is the same "posterior-predictive anchoring" used by the AMCMC path
    and dramatically improves h=0 calibration.

    `model_type` / `fixed_params`: for `sirs_logistic`, route the DE-bootstrap
    trajectories through the SIRS mirror and merge the fixed structural params
    (sw, tc_k, N, omega) that the fitted population does not carry. Defaults
    keep the legacy piecewise behavior.
    """
    max_h = max(horizons)
    total = n_observed + max_h
    traj = sample_trajectories(
        fit_result, total,
        top_n=top_n, samples_per_member=samples_per_member, seed=seed,
        model_type=model_type, fixed_params=fixed_params,
    )
    # Keep only finite rows.
    finite = ~np.any(~np.isfinite(traj), axis=1)
    traj = traj[finite]
    # Optional posterior-predictive anchoring.
    if anchor and observed is not None and len(observed) > 0:
        from .amcmc import anchor_trajectories
        traj = anchor_trajectories(
            traj, np.asarray(observed, dtype=float),
            mode=anchor_mode, lookback=anchor_lookback,
            slope_blend=anchor_slope_blend, phase_aware=phase_aware,
        )
    q_levels = np.array(quantile_levels)
    quants = np.empty((len(q_levels), len(horizons)), dtype=float)
    point = np.empty(len(horizons), dtype=float)
    for j, h in enumerate(horizons):
        t = n_observed + h - 1
        col = traj[:, t]
        quants[:, j] = np.quantile(col, q_levels)
        point[j] = float(np.median(col))
    return QuantileForecast(
        horizons=tuple(horizons),
        quantile_levels=tuple(quantile_levels),
        quantiles=quants,
        point=point,
    )


def _find_param_col(names: list[str], short: str) -> Optional[str]:
    """Find the column matching a short PyBNF name (e.g. 'r' -> 'r__FREE')."""
    for n in names:
        if n == short or n.replace("__FREE", "") == short:
            return n
    return None
