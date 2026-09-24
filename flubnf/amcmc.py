"""LEGACY (AMCMC weekly loop): AMCMC posterior → FluSight quantile forecasts.

When PyBNF is run with `fit_type = am` and `output_noise_trajectory = H_weekly`,
it writes a noise-augmented predictive trajectory to

    <workspace>/results/<state>/Results/A_MCMC/Runs/
        traj_noise_<state>_H_weekly_chain_0.txt

shape (n_samples, n_weeks). Each row is one posterior draw with
negative-binomial observation noise applied at each time point. The last
`forecast_horizon` columns are the future-week predictions we forecast on.

Observation noise comes from PyBNF's own neg_bin_dynamic (no bootstrap).
`quantile_forecast_from_amcmc()` returns the same `QuantileForecast` shape
as flubnf.quantiles, so downstream code works unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from .quantiles import FLUSIGHT_QUANTILES, QuantileForecast

log = logging.getLogger(__name__)


def read_traj_noise(
    state_results: Path, state: str, observable: str = "H_weekly",
) -> Optional[np.ndarray]:
    """Read PyBNF's noise-augmented trajectory file(s) for all chains.

    PyBNF names the file `traj_noise_<suffix><observable>_chain_<idx>.txt`,
    one per chain when `population_size > 1`. We discover them all by
    globbing chain_0..chain_N and concatenate their samples to form a
    multi-chain ensemble.

    Returns shape (n_total_samples, n_weeks) or None if missing.
    """
    runs_dir = state_results / "Results" / "A_MCMC" / "Runs"
    if not runs_dir.exists():
        log.warning("AMCMC Runs dir missing: %s", runs_dir)
        return None
    # Find all chain_N files for the same observable prefix.
    chain_0_candidates = sorted(runs_dir.glob("traj_noise_*_chain_0.txt"))
    if not chain_0_candidates:
        log.warning("no traj_noise file in %s", runs_dir)
        return None
    # Use the chain_0 filename to derive the chain_N glob pattern.
    chain_0_name = chain_0_candidates[0].name
    prefix = chain_0_name.rsplit("_chain_0.txt", 1)[0]
    chain_files = sorted(runs_dir.glob(f"{prefix}_chain_*.txt"))
    arrays: list[np.ndarray] = []
    for p in chain_files:
        try:
            arr = np.genfromtxt(p)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            arrays.append(arr)
        except Exception as e:
            log.warning("could not parse %s: %s", p, e)
    if not arrays:
        return None
    if len(arrays) == 1:
        return arrays[0]
    # Align column counts (chains may differ slightly if PyBNF cuts off early).
    min_cols = min(a.shape[1] for a in arrays)
    return np.vstack([a[:, :min_cols] for a in arrays])


def anchor_trajectories(
    traj: np.ndarray,
    observed: np.ndarray,
    *,
    mode: str = "multiplicative",
    lookback: int = 3,
    clamp: tuple[float, float] = (0.25, 4.0),
    slope_blend: float = 0.0,
    phase_aware: bool = True,
) -> np.ndarray:
    """Shift / scale each posterior trajectory so it matches recently observed values.

    Conditioning on the last `lookback` observed weeks (robust to one noisy
    week) tightens the predictive where we have data, mostly helping h=0.

    Modes:
      - "multiplicative": scale each sample by geo-mean(obs / sample) over
        the lookback window. Best for outbreaks (exponential dynamics).
        `clamp` bounds the per-sample scale factor.
      - "additive": shift each sample by mean(obs - sample) over the window.
        Preserves absolute changes; clipped at 0 to avoid negative counts.
      - "none": pass-through.

    `slope_blend` ∈ [0, 1]: how much weight to give the recent observed
    growth-rate momentum, vs the model's intrinsic trajectory shape, in
    the forecast region (h ≥ 1). Computed as a geometric blend:

        anchored_h *= (obs_growth_rate ** h)^slope_blend / (model_growth_rate ** h)^slope_blend

    `slope_blend = 0` (default): pure anchored model dynamics.
    `slope_blend = 1`: pure persistence with recent growth.
    `slope_blend < 0`: auto-tune (see below).
    """
    if mode == "none" or len(observed) == 0:
        return traj
    last_idx = len(observed) - 1
    if last_idx >= traj.shape[1]:
        return traj
    k = max(1, min(lookback, len(observed)))
    obs_window = np.asarray(observed[-k:], dtype=float)
    sample_window = traj[:, last_idx - k + 1: last_idx + 1]
    if mode == "additive":
        # Mean (obs - sample) over the window per sample.
        shifts = np.mean(obs_window[None, :] - sample_window, axis=1)[:, None]
        return np.maximum(traj + shifts, 0.0)
    # Multiplicative: geometric mean of (obs / sample) per sample.
    safe_sample = np.where(sample_window < 0.5, 0.5, sample_window)
    safe_obs = np.where(obs_window < 0.5, 0.5, obs_window)
    ratios = safe_obs[None, :] / safe_sample            # (n_samples, k)
    # geo-mean: exp(mean(log(ratios))). Use log to keep numerically stable.
    log_ratios = np.log(np.clip(ratios, 1e-6, 1e6))
    factors = np.exp(np.mean(log_ratios, axis=1))
    factors = np.clip(factors, clamp[0], clamp[1])[:, None]
    anchored = np.maximum(traj * factors, 0.0)

    if k < 2:
        return anchored

    # Recent observed growth rate (per week, geo-mean over the window).
    obs_growth = float((safe_obs[-1] / safe_obs[0]) ** (1.0 / max(1, k - 1)))
    # Per-sample growth over the same in-sample window (used for correction).
    model_growth_per_sample = (sample_window[:, -1] / safe_sample[:, 0]) ** (1.0 / max(1, k - 1))
    model_growth_per_sample = np.clip(model_growth_per_sample, 1e-6, 1e6)

    # slope_blend < 0: auto-tune from |log(observed growth / model forward
    # growth)|: no blend inside a dead zone, then linear up to 0.6.
    if slope_blend < 0:
        n_total = traj.shape[1]
        # forward window: the k weeks after last_idx, else in-sample growth
        fwd_end = min(n_total - 1, last_idx + k - 1)
        if fwd_end > last_idx:
            fwd_window = anchored[:, last_idx: fwd_end + 1]
            safe_fwd = np.where(fwd_window < 0.5, 0.5, fwd_window)
            n_fwd = fwd_window.shape[1]
            model_fwd_growth_per_sample = (safe_fwd[:, -1] / safe_fwd[:, 0]) ** (
                1.0 / max(1, n_fwd - 1)
            )
            model_fwd_growth_median = float(np.median(model_fwd_growth_per_sample))
        else:
            # Trajectory doesn't extend forward; use in-sample as proxy.
            model_fwd_growth_median = float(np.median(model_growth_per_sample))
        log_disagreement = abs(np.log(obs_growth / max(model_fwd_growth_median, 1e-6)))
        # dead zone (~25% agreement): a small blend compounds over horizons
        DEAD_ZONE = 0.22
        if log_disagreement < DEAD_ZONE:
            slope_blend = 0.0
        else:
            # Map [0.22, 0.22+1.0] disagreement -> [0, 0.6] blend.
            slope_blend = float(min(0.6, 0.6 * (log_disagreement - DEAD_ZONE)))

    # No momentum blend at NEAR_PEAK/TROUGH: the curve is bending.
    if phase_aware and slope_blend > 0:
        try:
            from .phase import detect_phase, Phase
            pa = detect_phase(observed)
            if pa.phase in (Phase.NEAR_PEAK, Phase.TROUGH):
                slope_blend = 0.0
        except Exception:
            # If phase detection breaks, fall through with current blend.
            pass

    if slope_blend <= 0:
        return anchored

    # For h >= 1, multiply by (obs_growth / model_growth)^h * slope_blend.
    n_total = anchored.shape[1]
    horizons_idx = np.arange(n_total) - last_idx
    horizons_idx = np.maximum(horizons_idx, 0)
    correction = (obs_growth / model_growth_per_sample)[:, None]
    correction = np.power(correction, horizons_idx[None, :] * slope_blend)
    correction = np.clip(correction, 0.1, 10.0)
    return np.maximum(anchored * correction, 0.0)


def quantile_forecast_from_amcmc(
    traj: np.ndarray,
    n_observed: int,
    horizons: Sequence[int],
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
    *,
    anchor: bool = True,
    observed: np.ndarray | None = None,
    anchor_mode: str = "multiplicative",
    anchor_lookback: int = 3,
    anchor_slope_blend: float = 0.0,
    phase_aware: bool = True,
) -> QuantileForecast:
    """Build a QuantileForecast from an AMCMC noise trajectory.

    Args:
        traj:       shape (n_samples, n_total_weeks); n_total_weeks must be
                    at least n_observed + max(horizons).
        n_observed: number of weeks of historical data (defines where 'now' is).
        horizons:   forecast horizons in weeks (1-indexed).
        quantile_levels: the 23 FluSight quantile levels (default).
    """
    horizons = tuple(horizons)
    n_total = traj.shape[1]
    max_h = max(horizons)
    if n_total < n_observed + max_h:
        raise ValueError(
            f"traj has {n_total} weeks but needs at least "
            f"{n_observed + max_h} (n_observed={n_observed}, max_h={max_h})"
        )
    # Drop any non-finite samples (rare).
    finite = ~np.any(~np.isfinite(traj), axis=1)
    traj = traj[finite]
    if len(traj) == 0:
        raise ValueError("no finite trajectory samples")

    # Anchor on recent observations, if requested.
    if anchor and observed is not None and len(observed) > 0:
        traj = anchor_trajectories(
            traj, np.asarray(observed, dtype=float),
            mode=anchor_mode, lookback=anchor_lookback,
            slope_blend=anchor_slope_blend, phase_aware=phase_aware,
        )

    q_levels = np.array(quantile_levels)
    quants = np.empty((len(q_levels), len(horizons)), dtype=float)
    point = np.empty(len(horizons), dtype=float)
    for j, h in enumerate(horizons):
        # Column index for horizon h: predicted week = n_observed + h - 1.
        col = traj[:, n_observed + h - 1]
        quants[:, j] = np.quantile(col, q_levels)
        point[j] = float(np.median(col))
    return QuantileForecast(
        horizons=horizons,
        quantile_levels=tuple(quantile_levels),
        quantiles=quants,
        point=point,
    )
