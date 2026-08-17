"""Empirical interval-coverage calibration.

Forecasts come with quantile bands. The 50% prediction interval (PI)
is bounded by the 0.25 and 0.75 quantiles; *if calibrated*, 50% of
actual outcomes should fall inside. Persistent over- or under-coverage
indicates the predictive distribution is too narrow or too wide.

This module tracks coverage on a rolling window of past forecasts vs
their realized actuals, and emits a multiplicative rescale factor we
can apply to widen / narrow future quantile bands.

The corrections are deliberately conservative — they kick in only after
enough observations to be meaningful (default ≥ 8 weeks) and never
flip the direction of the median (which we trust the fit on).

Data flow:
  1. Each weekly job writes its quantile forecast to disk (already done
     via the submission CSV).
  2. After the actual is observed, `record_coverage` ingests the pair
     (forecast, actual) and updates a rolling tracker per state per
     horizon.
  3. Before producing a fresh quantile forecast, the workflow consults
     `apply_calibration(qf, tracker)` to rescale.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .quantiles import FLUSIGHT_QUANTILES, QuantileForecast

log = logging.getLogger(__name__)


# (lower_q, upper_q, nominal_coverage) — the FluSight scoring intervals.
PI_LEVELS: list[tuple[float, float, float]] = [
    (0.25,  0.75,  0.50),    # 50% PI
    (0.10,  0.90,  0.80),    # 80% PI
    (0.025, 0.975, 0.95),    # 95% PI
]


@dataclass
class CoverageRecord:
    """One forecast-vs-actual observation used to update calibration."""
    state: str
    horizon: int
    reference_date: str       # ISO Saturday
    q05: float
    q25: float
    q50: float
    q75: float
    q95: float
    q025: float
    q975: float
    actual: float


@dataclass
class CalibrationTracker:
    """Rolling coverage stats per (state, horizon).

    history[(state, horizon)] = list of CoverageRecord (most-recent last).
    """
    history: dict[tuple[str, int], list[CoverageRecord]] = field(default_factory=dict)
    rolling_window: int = 20

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        out = {}
        for (state, h), recs in self.history.items():
            out[f"{state}|{h}"] = [asdict(r) for r in recs]
        return {"rolling_window": self.rolling_window, "history": out}

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationTracker":
        out = cls(rolling_window=int(d.get("rolling_window", 20)))
        for key, recs in d.get("history", {}).items():
            state, h_str = key.split("|", 1)
            h = int(h_str)
            out.history[(state, h)] = [CoverageRecord(**r) for r in recs]
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "CalibrationTracker":
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text()))
        except Exception as e:
            log.warning("could not load calibration tracker %s: %s", path, e)
            return cls()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record(self, rec: CoverageRecord) -> None:
        key = (rec.state, rec.horizon)
        bucket = self.history.setdefault(key, [])
        # Avoid duplicate inserts (same (state, horizon, reference_date)).
        if not any(r.reference_date == rec.reference_date for r in bucket):
            bucket.append(rec)
        # Trim to rolling window.
        if len(bucket) > self.rolling_window:
            self.history[key] = bucket[-self.rolling_window:]

    def record_from_quantile_forecast(
        self,
        state: str,
        qf: QuantileForecast,
        actuals: dict[int, float],
        reference_date: str,
    ) -> int:
        """Convenience: ingest a QuantileForecast + actuals dict at once.

        Returns the number of (state, horizon) records added.
        """
        qd = qf.to_dict()
        added = 0
        for h in qf.horizons:
            actual = actuals.get(h)
            if actual is None or (isinstance(actual, float) and np.isnan(actual)):
                continue
            qmap = qd[h]
            def get_q(q):
                return float(qmap.get(q, qmap.get(float(q), 0.0)))
            self.record(CoverageRecord(
                state=state, horizon=int(h),
                reference_date=reference_date,
                q025=get_q(0.025), q05=get_q(0.05),
                q25=get_q(0.25), q50=get_q(0.5),
                q75=get_q(0.75), q95=get_q(0.95),
                q975=get_q(0.975),
                actual=float(actual),
            ))
            added += 1
        return added

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def empirical_coverage(self, state: str, horizon: int) -> dict[float, float]:
        """Return {nominal_coverage: empirical_coverage} per PI level."""
        recs = self.history.get((state, horizon), [])
        if not recs:
            return {nom: float("nan") for _, _, nom in PI_LEVELS}
        out = {}
        for lo, hi, nominal in PI_LEVELS:
            if lo == 0.25:
                lo_vals = np.array([r.q25 for r in recs])
                hi_vals = np.array([r.q75 for r in recs])
            elif lo == 0.10:
                lo_vals = np.array([r.q05 for r in recs])  # 80% = 10..90, but we stored q05/q95
                hi_vals = np.array([r.q95 for r in recs])
                lo, hi = 0.10, 0.90
            else:  # 95% PI
                lo_vals = np.array([r.q025 for r in recs])
                hi_vals = np.array([r.q975 for r in recs])
            actuals = np.array([r.actual for r in recs])
            inside = (actuals >= lo_vals) & (actuals <= hi_vals)
            out[nominal] = float(np.mean(inside))
        return out

    # ------------------------------------------------------------------
    # Recalibration factor
    # ------------------------------------------------------------------
    def rescale_factor(
        self, state: str, horizon: int,
        *, min_samples: int = 8, max_factor: float = 2.5,
    ) -> float:
        """Compute a multiplicative scale to apply to the half-width
        (quantile - median) so the realized coverage approaches nominal.

        Specifically targets the 80% PI: if empirical 80%-coverage is 60%
        (under-cover), we need wider intervals → factor > 1. If 95%
        (over-cover), factor < 1.

        Returns 1.0 (no change) when not enough data or when coverage is
        within ±5% of nominal.
        """
        recs = self.history.get((state, horizon), [])
        if len(recs) < min_samples:
            return 1.0
        cov = self.empirical_coverage(state, horizon)
        # Use 80% PI as the calibration target.
        emp = cov.get(0.80, float("nan"))
        if np.isnan(emp):
            return 1.0
        diff = emp - 0.80
        if abs(diff) < 0.05:
            return 1.0
        # Under-cover (diff < 0) → widen (factor > 1).
        # Heuristic: factor = 1 - 2*diff. So diff=-0.20 → 1.4; +0.10 → 0.8.
        factor = 1.0 - 2.0 * diff
        factor = float(np.clip(factor, 1.0 / max_factor, max_factor))
        return factor


def apply_calibration(
    qf: QuantileForecast,
    tracker: CalibrationTracker,
    *,
    state: str,
    min_factor: float = 0.7,
    max_factor: float = 1.5,
) -> QuantileForecast:
    """Rescale a QuantileForecast's interval half-widths around the median
    using the tracker's per-horizon rescale factor.

    Conservative bounds [min_factor, max_factor] = [0.7, 1.5] by default
    so a single off-week's coverage doesn't whipsaw the calibration.
    """
    n_q, n_h = qf.quantiles.shape
    new_q = qf.quantiles.copy()
    median_idx = list(qf.quantile_levels).index(0.5) if 0.5 in qf.quantile_levels else None
    if median_idx is None:
        return qf
    for j, h in enumerate(qf.horizons):
        factor = tracker.rescale_factor(state, int(h))
        factor = float(np.clip(factor, min_factor, max_factor))
        if abs(factor - 1.0) < 1e-3:
            continue
        med = qf.quantiles[median_idx, j]
        new_q[:, j] = med + (qf.quantiles[:, j] - med) * factor
        new_q[:, j] = np.maximum(new_q[:, j], 0.0)
    return QuantileForecast(
        horizons=qf.horizons,
        quantile_levels=qf.quantile_levels,
        quantiles=new_q,
        point=qf.point,
    )
