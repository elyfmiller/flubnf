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

#: Which stored quantile answers for each level in PI_LEVELS. The table is
#: the point: the declared interval and the measured interval come from the
#: same two numbers, so they cannot drift apart. They previously did — the
#: 80% row declared (0.10, 0.90) but was measured from q05/q95, the 90%
#: band, and filed under nominal 0.80. A perfectly calibrated forecaster
#: therefore measured ~0.90 against a 0.80 target and rescale_factor
#: narrowed its intervals by 20% for no reason. Adding a PI level now means
#: adding a row here, and a missing row is an immediate KeyError rather than
#: a silent substitution.
_Q_ATTR: dict[float, str] = {
    0.025: "q025", 0.05: "q05", 0.10: "q10", 0.25: "q25", 0.50: "q50",
    0.75: "q75", 0.90: "q90", 0.95: "q95", 0.975: "q975",
}


@dataclass
class CoverageRecord:
    """One forecast-vs-actual observation used to update calibration.

    q10 and q90 carry the 80% interval that PI_LEVELS declares. They trail
    the required fields with a NaN default so a calibration.json written
    before v1.0 still loads; a record without them is simply excluded from
    the 80% coverage estimate rather than measured against the wrong band.
    """
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
    q10: float = float("nan")
    q90: float = float("nan")


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
                q10=get_q(0.10), q25=get_q(0.25), q50=get_q(0.5),
                q75=get_q(0.75), q90=get_q(0.90), q95=get_q(0.95),
                q975=get_q(0.975),
                actual=float(actual),
            ))
            added += 1
        return added

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def empirical_coverage(self, state: str, horizon: int) -> dict[float, float]:
        """Return {nominal_coverage: empirical_coverage} per PI level.

        Each level is measured from the two quantiles PI_LEVELS declares for
        it, resolved through _Q_ATTR. Records missing a bound (a pre-v1.0
        tracker has no q10/q90) are dropped from that level only; a level
        with no usable record returns NaN, which rescale_factor reads as
        "no evidence" and answers with a factor of 1.0.
        """
        recs = self.history.get((state, horizon), [])
        if not recs:
            return {nom: float("nan") for _, _, nom in PI_LEVELS}
        actuals = np.array([r.actual for r in recs], dtype=float)
        out = {}
        for lo, hi, nominal in PI_LEVELS:
            lo_vals = np.array([getattr(r, _Q_ATTR[lo]) for r in recs],
                               dtype=float)
            hi_vals = np.array([getattr(r, _Q_ATTR[hi]) for r in recs],
                               dtype=float)
            usable = (np.isfinite(lo_vals) & np.isfinite(hi_vals)
                      & np.isfinite(actuals))
            if not usable.any():
                out[nominal] = float("nan")
                continue
            inside = ((actuals[usable] >= lo_vals[usable])
                      & (actuals[usable] <= hi_vals[usable]))
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

        Specifically targets the 80% PI, the q10..q90 band: if empirical
        coverage of that band is 60% (under-cover), we need wider intervals
        → factor > 1. If 95% (over-cover), factor < 1. A perfectly
        calibrated forecaster measures 0.80 and gets exactly 1.0.

        Returns 1.0 (no change) when not enough data, when the 80% band
        cannot be measured (no record carries q10/q90), or when coverage is
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
