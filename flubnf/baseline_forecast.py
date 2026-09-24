"""LEGACY (DE/AMCMC workspace loop; reached only from the legacy CLI commands).

Simple baseline forecasters as a WIS floor and signal-add sanity check.

Two reference models, neither using BNGL or PyBNF posteriors:

  * **Persistence** — symmetrised ADDITIVE random walk on week-over-week
    differences, as the official `FluSight-baseline` does.
  * **Rolling mean** — point at the mean of last N observed weeks; Gaussian
    spread from the same window, scaled by √h.

Uses: a diagnostic floor (model WIS > baseline WIS means something is
wrong), and a safety net: after sustained losses to the baseline,
`recommend_baseline_blend()` suggests a weight and
`blend_quantile_forecasts()` mixes. Outputs are `QuantileForecast` objects
shaped like `flubnf.quantiles.quantile_forecast`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .quantiles import FLUSIGHT_QUANTILES, QuantileForecast


def persistence_quantile_forecast(
    observed: np.ndarray,
    horizons: Sequence[int],
    *,
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
    lookback: int = 6,
    n_samples: int = 2000,
    seed: int = 0,
    epsilon: float = 0.5,
) -> QuantileForecast:
    """Symmetrised ADDITIVE random-walk persistence baseline.

    Matches the FluSight-baseline's construction: sample h week-over-week
    DIFFERENCES (not log-ratios), symmetrised (both +d and -d, so no drift),
    add them to the last observation, and truncate at zero. Not a log-ratio
    walk: that extrapolated growth exponentially (relWIS 2.555 vs 1.133 on
    2025-26), and this is the fallback for degenerate fits (backtest.py).

    `lookback` bounds the difference window; `epsilon` is kept only for API
    compatibility.
    """
    obs = np.asarray(observed, dtype=float)
    obs = obs[np.isfinite(obs)]
    if len(obs) < 2:
        raise ValueError("persistence baseline needs at least 2 observed values")

    last = float(obs[-1])
    win = obs[-(lookback + 1):] if len(obs) >= lookback + 1 else obs
    diffs = np.diff(win)
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        # Two-week edge case: a small symmetric step so quantiles do not
        # collapse to a point mass.
        diffs = np.array([-1.0, 0.0, 1.0])
    # Symmetrise: zero drift is the defining property of a naive reference.
    steps_pool = np.concatenate([diffs, -diffs])

    rng = np.random.default_rng(seed)
    q_levels = np.array(quantile_levels, dtype=float)
    quants = np.empty((len(q_levels), len(horizons)), dtype=float)
    point = np.empty(len(horizons), dtype=float)

    for j, h in enumerate(horizons):
        h = int(h)
        if h < 1:
            samples = np.full(n_samples, last, dtype=float)
        else:
            steps = rng.choice(steps_pool, size=(n_samples, h), replace=True)
            samples = np.clip(last + np.sum(steps, axis=1), 0.0, None)
        quants[:, j] = np.quantile(samples, q_levels)
        point[j] = float(np.quantile(samples, 0.5))

    return QuantileForecast(
        horizons=tuple(int(h) for h in horizons),
        quantile_levels=tuple(quantile_levels),
        quantiles=quants,
        point=point,
    )


def rolling_mean_quantile_forecast(
    observed: np.ndarray,
    horizons: Sequence[int],
    *,
    window: int = 4,
    quantile_levels: Sequence[float] = FLUSIGHT_QUANTILES,
    n_samples: int = 2000,
    seed: int = 0,
) -> QuantileForecast:
    """Rolling-mean baseline: point = mean(last `window` weeks).

    Spread is Gaussian with σ = sample std of the window, scaled by √h
    (matches a random-walk-around-trend assumption). Slightly biased toward
    the recent average — performs well in flat seasons, worse in sharp
    transitions.
    """
    obs = np.asarray(observed, dtype=float)
    obs = obs[np.isfinite(obs)]
    if len(obs) < 2:
        raise ValueError("rolling-mean baseline needs at least 2 observed values")

    win = obs[-window:] if len(obs) >= window else obs
    mean = float(np.mean(win))
    if len(win) > 1:
        std = float(np.std(win, ddof=1))
    else:
        std = max(0.1 * abs(mean), 1.0)
    # never let σ collapse to 0: a point mass tanks WIS on any movement
    std = max(std, 0.05 * max(mean, 1.0))

    rng = np.random.default_rng(seed)
    q_levels = np.array(quantile_levels, dtype=float)
    quants = np.empty((len(q_levels), len(horizons)), dtype=float)
    point = np.empty(len(horizons), dtype=float)

    for j, h in enumerate(horizons):
        h = int(h)
        scale = std * np.sqrt(max(h, 1))
        noise = rng.normal(0.0, scale, size=n_samples)
        samples = np.clip(mean + noise, 0.0, None)
        quants[:, j] = np.quantile(samples, q_levels)
        point[j] = float(np.quantile(samples, 0.5))

    return QuantileForecast(
        horizons=tuple(int(h) for h in horizons),
        quantile_levels=tuple(quantile_levels),
        quantiles=quants,
        point=point,
    )


def blend_quantile_forecasts(
    primary: QuantileForecast,
    secondary: QuantileForecast,
    *,
    weight: float,
) -> QuantileForecast:
    """Linear blend at each (quantile, horizon) cell.

    `weight` ∈ [0, 1] is the share of `secondary` in the output —
    weight=0 → primary unchanged; weight=1 → secondary only. Quantile
    levels and horizons must match.

    A convex blend of monotone arrays stays monotone.
    """
    if not (0.0 <= weight <= 1.0):
        raise ValueError(f"weight must be in [0, 1], got {weight}")
    if primary.horizons != secondary.horizons:
        raise ValueError(
            f"horizons mismatch: {primary.horizons} vs {secondary.horizons}"
        )
    if primary.quantile_levels != secondary.quantile_levels:
        raise ValueError("quantile_levels differ between primary and secondary")
    blended_q = (1.0 - weight) * primary.quantiles + weight * secondary.quantiles
    blended_p = (1.0 - weight) * primary.point + weight * secondary.point
    return QuantileForecast(
        horizons=primary.horizons,
        quantile_levels=primary.quantile_levels,
        quantiles=blended_q,
        point=blended_p,
    )


def recommend_baseline_blend(
    model_wis_history: Sequence[float],
    baseline_wis_history: Sequence[float],
    *,
    min_weeks: int = 3,
    ratio_threshold: float = 1.25,
    max_blend: float = 0.5,
) -> Optional[float]:
    """Suggest a blend weight when the model has been losing to baseline.

    Trigger: the model's WIS exceeds the baseline's WIS by at least
    `ratio_threshold`× in each of the last `min_weeks` weeks. When that
    holds, recommend a blend weight that scales with the mean excess —
    capped at `max_blend`.

    Returns None when the model is doing fine, when there's not enough
    history, or when any input is non-finite / non-positive.
    """
    m_seq = list(model_wis_history)
    b_seq = list(baseline_wis_history)
    if len(m_seq) < min_weeks or len(b_seq) < min_weeks:
        return None
    m = np.array(m_seq[-min_weeks:], dtype=float)
    b = np.array(b_seq[-min_weeks:], dtype=float)
    if not (np.all(np.isfinite(m)) and np.all(np.isfinite(b))):
        return None
    if np.any(b <= 0):
        return None
    ratios = m / b
    if not np.all(ratios >= ratio_threshold):
        return None
    excess = float(np.mean(ratios) - ratio_threshold)
    # Floor weight at 0.2 when triggered (otherwise a barely-triggered case
    # blends ~nothing); grow linearly with mean excess up to max_blend.
    weight = min(max_blend, 0.2 + 0.3 * excess)
    return float(weight)


# ---------------------------------------------------------------------------
# Scoring submissions against the baselines
# ---------------------------------------------------------------------------
def score_submissions_vs_baselines(
    submissions_dir: Path,
    target_csv: Path,
    locations: dict,
    *,
    rolling_window: int = 4,
    persistence_lookback: int = 6,
) -> pd.DataFrame:
    """Walk submissions, build matched baseline forecasts, score all three.

    For every (reference_date, state, horizon) cell where we have an
    actual on disk, compute:
      - our model's WIS (from the submission row),
      - persistence baseline WIS (using observed weeks BEFORE
        reference_date: only what was available at the as-of Saturday,
        reference_date - 7; the week ending reference_date is horizon 0,
        a target, never an observation),
      - rolling-mean baseline WIS (same observed cutoff).

    Returns a long-form DataFrame, one row per (state, horizon) aggregated
    across reference_dates; `model_wis > persistence_wis` flags a state
    whose model is worse than persistence.
    """
    from .wis import wis as wis_fn
    if not target_csv.exists():
        raise FileNotFoundError(f"target CSV not found: {target_csv}")
    tgt = pd.read_csv(target_csv, dtype={"location": str})
    tgt["date"] = pd.to_datetime(tgt["date"]).dt.date
    fips_to_state = {info.fips.zfill(2): name
                     for name, info in locations.items()}

    # Per-state cache of (sorted_dates, values) tuples — built lazily.
    per_state_obs: dict[str, tuple[list, list]] = {}

    def _obs_up_to(fips: str, ref_date_iso: str) -> np.ndarray:
        if fips not in per_state_obs:
            sub = tgt[tgt["location"].astype(str).str.zfill(2) == fips]
            sub = sub.sort_values("date")
            per_state_obs[fips] = (
                sub["date"].tolist(), sub["value"].astype(float).tolist()
            )
        dates, vals = per_state_obs[fips]
        from datetime import date as _date
        cutoff = _date.fromisoformat(ref_date_iso)
        # strictly before: the reference week is horizon 0's target
        out = [v for d, v in zip(dates, vals) if d < cutoff]
        return np.asarray(out, dtype=float)

    rows: list[dict] = []
    for sub_path in sorted(Path(submissions_dir).glob("*.csv")):
        try:
            sub = pd.read_csv(sub_path, dtype={"location": str})
        except Exception:
            continue
        if sub.empty:
            continue
        sub = sub[sub["output_type"] == "quantile"]
        ref_date = str(sub["reference_date"].iloc[0])

        for (fips_raw, h), group in sub.groupby(["location", "horizon"]):
            fips = str(fips_raw).zfill(2)
            state = fips_to_state.get(fips)
            if state is None:
                continue
            target_end = str(group["target_end_date"].iloc[0])
            tgt_rows = tgt[
                (tgt["location"].astype(str).str.zfill(2) == fips)
                & (tgt["date"].astype(str) == target_end)
            ]
            if tgt_rows.empty:
                continue
            actual = float(tgt_rows["value"].iloc[0])
            if not np.isfinite(actual):
                continue

            qd = dict(zip(group["output_type_id"].astype(float),
                          group["value"].astype(float)))
            try:
                model_w = wis_fn(qd, actual).wis
            except Exception:
                continue

            # Observed-up-to-cutoff for baselines.
            obs = _obs_up_to(fips, ref_date)
            if len(obs) < 2:
                continue
            horizons = [int(h) + 1]   # FluSight h0 → internal h1
            try:
                pers = persistence_quantile_forecast(
                    obs, horizons, lookback=persistence_lookback, seed=0,
                )
                roll = rolling_mean_quantile_forecast(
                    obs, horizons, window=rolling_window, seed=0,
                )
            except Exception:
                continue
            pers_qd = {float(q): float(v)
                       for q, v in zip(pers.quantile_levels,
                                        pers.quantiles[:, 0])}
            roll_qd = {float(q): float(v)
                       for q, v in zip(roll.quantile_levels,
                                        roll.quantiles[:, 0])}
            rows.append({
                "reference_date": ref_date,
                "state": state,
                "horizon": int(h),
                "actual": actual,
                "model_wis": float(model_w),
                "persistence_wis": float(wis_fn(pers_qd, actual).wis),
                "rolling_wis": float(wis_fn(roll_qd, actual).wis),
            })
    return pd.DataFrame(rows)


def aggregate_baseline_comparison(
    long_df: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate the long-form comparison into per-(state, horizon) means."""
    if long_df.empty:
        return pd.DataFrame()
    agg = long_df.groupby(["state", "horizon"]).agg(
        n_cells=("model_wis", "count"),
        model_wis=("model_wis", "mean"),
        persistence_wis=("persistence_wis", "mean"),
        rolling_wis=("rolling_wis", "mean"),
    ).reset_index()
    agg["model_vs_persistence"] = agg["persistence_wis"] - agg["model_wis"]
    agg["model_vs_rolling"] = agg["rolling_wis"] - agg["model_wis"]
    return agg.sort_values(["state", "horizon"])
