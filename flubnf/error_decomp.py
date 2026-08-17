"""Per-state, per-horizon error decomposition.

WIS lumps three orthogonal failure modes into one scalar:
  * Sharpness — how wide our prediction intervals are. (Smaller is better
    only if we stay calibrated; over-narrow intervals get punished by
    over/underprediction.)
  * Calibration — whether the actual lands inside the PIs at the nominal
    rate. We track empirical coverage of the 50%, 80%, and 95% PIs.
  * Bias — signed median error (median - actual). Tells us whether we
    systematically over- or under-forecast.

This module reads a `merged` dataframe from `leaderboard.join_with_team`
(or a similarly shaped frame with `our_wis`, `our_median`, `actual`, and
the original submission CSVs) and returns a long-format DataFrame
suitable for per-state heatmaps in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .constants import load_locations
from .wis import FLUSIGHT_PI_QUANTILES, wis as wis_fn


# The 23 FluSight quantile levels paired into central PIs.
_PI_PAIRS: tuple[tuple[float, float, float], ...] = tuple(
    (1.0 - 2 * q, q, 1.0 - q) for q in FLUSIGHT_PI_QUANTILES
)
# e.g. (0.98, 0.01, 0.99), (0.95, 0.025, 0.975), ...
_KEY_COVERAGE_LEVELS: tuple[float, ...] = (0.50, 0.80, 0.95)


@dataclass(frozen=True)
class RowMetrics:
    """One (reference_date, location, horizon) row's decomposition."""
    sharpness: float       # mean interval width across all 11 central PIs
    overpred: float        # weighted overprediction penalty
    underpred: float       # weighted underprediction penalty
    bias: float            # signed (median - actual)
    abs_err: float         # |median - actual|
    coverage_50: float     # 1.0 if actual inside [q25, q75] else 0
    coverage_80: float     # 1.0 if actual inside [q10, q90]
    coverage_95: float     # 1.0 if actual inside [q025, q975]


def _decompose_single(quantiles: dict[float, float], actual: float) -> RowMetrics:
    """Compute the per-row decomposition from a quantile dict + actual."""
    median = float(quantiles.get(0.5, np.nan))
    bias = float(median - actual)
    abs_err = float(abs(median - actual))

    # Reuse wis() to get dispersion/over/under in one pass.
    res = wis_fn(quantiles, actual)
    sharpness = float(res.dispersion)
    over = float(res.overprediction)
    under = float(res.underprediction)

    # Empirical PI coverage at the key levels.
    def _covered(level: float) -> float:
        """1 if actual falls inside the central `level` PI."""
        q_lo = round((1.0 - level) / 2.0, 4)
        q_hi = round(1.0 - q_lo, 4)
        try:
            lo = quantiles[q_lo]; hi = quantiles[q_hi]
        except KeyError:
            # Tolerant fallback (float64 keys not equality-matching).
            lo = _nearest(quantiles, q_lo)
            hi = _nearest(quantiles, q_hi)
            if lo is None or hi is None:
                return float("nan")
        return 1.0 if (lo <= actual <= hi) else 0.0

    return RowMetrics(
        sharpness=sharpness, overpred=over, underpred=under,
        bias=bias, abs_err=abs_err,
        coverage_50=_covered(0.50),
        coverage_80=_covered(0.80),
        coverage_95=_covered(0.95),
    )


def _nearest(d: dict[float, float], q: float, tol: float = 1e-6
             ) -> Optional[float]:
    for k, v in d.items():
        if abs(float(k) - q) < tol:
            return float(v)
    return None


def decompose_submissions(
    submissions_dir: Path,
    observed_csv: Path,
    config,
) -> pd.DataFrame:
    """Walk our submissions, score each row, decompose, return long form.

    Schema: reference_date, location, state, horizon, actual, our_median,
            our_wis, sharpness, overpred, underpred, bias, abs_err,
            coverage_50, coverage_80, coverage_95.
    """
    from .backtest import _resolve_columns_quick
    locs = load_locations(config.locations_csv)
    fips_to_state = {info.fips: name for name, info in locs.items()}
    df_obs = pd.read_csv(observed_csv)
    geo_col, date_col, val_col = _resolve_columns_quick(df_obs, config)
    df_obs["_d"] = pd.to_datetime(df_obs[date_col]) - pd.Timedelta(days=1)
    df_obs = df_obs.sort_values([geo_col, "_d"])

    rows = []
    for sub_path in sorted(Path(submissions_dir).glob("*.csv")):
        try:
            sub = pd.read_csv(sub_path, dtype={"location": str})
        except Exception:
            continue
        if sub.empty:
            continue
        sub["location"] = sub["location"].astype(str).str.zfill(2).where(
            sub["location"] != "US", sub["location"])
        ref_date = str(sub["reference_date"].iloc[0])

        for (fips, h), group in sub[sub["output_type"] == "quantile"].groupby(
                ["location", "horizon"]):
            state = fips_to_state.get(fips)
            if state is None or state not in locs:
                continue
            abbrev = locs[state].abbreviation
            tgt = str(group["target_end_date"].iloc[0])
            obs_state = df_obs[df_obs[geo_col] == abbrev]
            obs_row = obs_state[obs_state["_d"].dt.date.astype(str) == tgt]
            if obs_row.empty:
                continue
            actual = float(obs_row[val_col].iloc[0])
            if not np.isfinite(actual):
                continue
            qd = dict(zip(group["output_type_id"].astype(float),
                          group["value"].astype(float)))
            try:
                metrics = _decompose_single(qd, actual)
                our_wis = wis_fn(qd, actual).wis
            except Exception:
                continue
            rows.append({
                "reference_date": ref_date,
                "location": fips,
                "state": state,
                "horizon": int(h),
                "actual": actual,
                "our_median": float(qd.get(0.5, np.nan)),
                "our_wis": float(our_wis),
                "sharpness": metrics.sharpness,
                "overpred": metrics.overpred,
                "underpred": metrics.underpred,
                "bias": metrics.bias,
                "abs_err": metrics.abs_err,
                "coverage_50": metrics.coverage_50,
                "coverage_80": metrics.coverage_80,
                "coverage_95": metrics.coverage_95,
            })
    return pd.DataFrame(rows)


def aggregate_by_state(decomp_df: pd.DataFrame,
                       *, horizons: Optional[Iterable[int]] = None
                       ) -> pd.DataFrame:
    """Aggregate per-row decomposition into per-state metrics.

    Returns columns:
      state, n_cells, mean_wis, mean_sharpness, mean_abs_err,
      mean_bias, signed_bias (= mean_bias), over_share,
      coverage_50, coverage_80, coverage_95,
      calibration_score (= 1 - |over_share - 0.5| * 2 — closer to 1 is
      more balanced over/under-prediction).
    """
    if decomp_df.empty:
        return pd.DataFrame()
    df = decomp_df
    if horizons is not None:
        df = df[df["horizon"].isin(list(horizons))]
        if df.empty:
            return pd.DataFrame()

    def _over_share(g: pd.DataFrame) -> float:
        tot = float(g["overpred"].sum() + g["underpred"].sum())
        if tot <= 0:
            return float("nan")
        return float(g["overpred"].sum() / tot)

    agg = df.groupby("state").agg(
        n_cells=("our_wis", "count"),
        mean_wis=("our_wis", "mean"),
        mean_sharpness=("sharpness", "mean"),
        mean_abs_err=("abs_err", "mean"),
        mean_bias=("bias", "mean"),
        coverage_50=("coverage_50", "mean"),
        coverage_80=("coverage_80", "mean"),
        coverage_95=("coverage_95", "mean"),
    ).reset_index()
    over_share = df.groupby("state").apply(_over_share)
    agg["over_share"] = agg["state"].map(over_share)
    # Calibration score: 1 when over/under split is 50/50, 0 when all one side.
    agg["calibration_score"] = 1.0 - (agg["over_share"].fillna(0.5) - 0.5).abs() * 2.0
    return agg.sort_values("mean_wis", ascending=False)


def aggregate_by_state_horizon(decomp_df: pd.DataFrame) -> pd.DataFrame:
    """Per-(state, horizon) decomposition for heatmaps."""
    if decomp_df.empty:
        return pd.DataFrame()
    return decomp_df.groupby(["state", "horizon"]).agg(
        n_cells=("our_wis", "count"),
        mean_wis=("our_wis", "mean"),
        mean_sharpness=("sharpness", "mean"),
        mean_bias=("bias", "mean"),
        mean_abs_err=("abs_err", "mean"),
        coverage_50=("coverage_50", "mean"),
        coverage_95=("coverage_95", "mean"),
    ).reset_index()
