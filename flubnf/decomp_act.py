"""Act on error-decomposition signals from the calibration tracker.

`flubnf.error_decomp` *measures* per-state bias / sharpness / coverage on
historical submissions. `flubnf.calibration` *records* the same data in a
rolling per-(state, horizon) tracker. This module *acts* on those signals:

  * **Persistent positive bias** (median overpredicts for ≥`min_weeks`
    consecutive weeks) → recommend tightening the `mult__FREE` upper
    bound. The over-estimation is most often driven by an overly broad
    `mult` ceiling letting the fit chase a phantom peak.

  * **Persistent low 95% PI coverage** (cov_95 < `cov95_threshold` over
    the same window) → recommend widening the calibration rescale's
    `max_factor`, so the post-fit interval widening has more room to
    fight under-coverage.

Both functions are pure: they read the tracker and a session-config, and
return either a structured recommendation or `None`. The caller decides
whether to mutate `session.bounds` / `session.tuning`. `apply_to_session`
is a convenience that does the mutation for you.

These knobs were validated by the laptop-side tests in
`tests/test_decomp_act.py`; the actual *trigger thresholds* still want
Mac-Studio validation against a full season before being tightened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .calibration import CalibrationTracker
from .conf_files import FreeParam
from .session import StateSession


@dataclass(frozen=True)
class RecentSignals:
    """Decomposition signals computed from the most-recent tracker entries."""
    state: str
    horizon: int
    n_weeks: int
    bias_sequence: tuple[float, ...]     # (q50 - actual) per week
    cov95_sequence: tuple[bool, ...]     # 1 if actual in [q025, q975]
    median_sequence: tuple[float, ...]   # q50 per week
    mean_bias: float
    mean_cov95: float


def compute_recent_signals(
    tracker: CalibrationTracker,
    state: str,
    horizon: int = 1,
    *,
    lookback: int = 3,
) -> RecentSignals:
    """Extract bias + cov95 signals from the tracker's history.

    Defaults to horizon=1 (h=0 in FluSight numbering — the most-rewarded
    horizon). Empty history yields a benign `mean_cov95=1.0` so callers
    don't trigger on "no data."
    """
    recs = tracker.history.get((state, int(horizon)), [])
    recent = recs[-int(lookback):]
    biases = tuple(float(r.q50 - r.actual) for r in recent)
    cov95 = tuple(bool(r.q025 <= r.actual <= r.q975) for r in recent)
    medians = tuple(float(r.q50) for r in recent)
    return RecentSignals(
        state=state, horizon=int(horizon), n_weeks=len(recent),
        bias_sequence=biases, cov95_sequence=cov95,
        median_sequence=medians,
        mean_bias=float(np.mean(biases)) if biases else 0.0,
        mean_cov95=float(np.mean(cov95)) if cov95 else 1.0,
    )


@dataclass(frozen=True)
class MultTightenRec:
    """Recommendation to shrink the `mult__FREE` upper bound."""
    new_high_factor: float        # multiply current `high` by this
    reason: str


def recommend_mult_tighten(
    signals: RecentSignals,
    *,
    min_weeks: int = 3,
    factor: float = 0.85,
    min_relative_bias: float = 0.10,
) -> Optional[MultTightenRec]:
    """Tighten `mult__FREE` upper bound when bias is consistently positive
    and material.

    Triggers when:
      - `n_weeks >= min_weeks`, AND
      - every week in the window had `bias > 0` (median overpredicted), AND
      - the mean bias is at least `min_relative_bias` of the mean median
        (so we don't chase rounding-error positives on small counts).

    Returns the multiplicative factor (e.g. 0.85 → new_high = high * 0.85),
    capped at one tightening per call.
    """
    if signals.n_weeks < min_weeks:
        return None
    if not all(b > 0 for b in signals.bias_sequence):
        return None
    mean_med = float(np.mean(signals.median_sequence)) if signals.median_sequence else 0.0
    if mean_med <= 0:
        return None
    relative = signals.mean_bias / mean_med
    if relative < min_relative_bias:
        return None
    return MultTightenRec(
        new_high_factor=float(factor),
        reason=(f"positive bias in all {signals.n_weeks} recent weeks "
                f"(mean={signals.mean_bias:.1f}, rel={relative:.2f})"),
    )


@dataclass(frozen=True)
class CalibrationWidenRec:
    """Recommendation to raise the calibration rescale's `max_factor`."""
    new_max_factor: float
    reason: str


def recommend_calibration_widen(
    signals: RecentSignals,
    current_max_factor: float,
    *,
    min_weeks: int = 3,
    cov95_threshold: float = 0.7,
    increment: float = 0.25,
    cap: float = 2.5,
) -> Optional[CalibrationWidenRec]:
    """Raise the per-state calibration `max_factor` when 95% PI coverage
    has been chronically low.

    Triggers when `n_weeks >= min_weeks` AND `mean(cov_95) < cov95_threshold`.
    Returns the new max_factor (current + `increment`, capped at `cap`),
    or None if no widening is warranted.
    """
    if signals.n_weeks < min_weeks:
        return None
    if signals.mean_cov95 >= cov95_threshold:
        return None
    new = min(cap, current_max_factor + increment)
    if new <= current_max_factor + 1e-6:
        return None
    return CalibrationWidenRec(
        new_max_factor=float(new),
        reason=(f"cov_95={signals.mean_cov95:.2f} over {signals.n_weeks} "
                f"weeks (< {cov95_threshold})"),
    )


@dataclass(frozen=True)
class DecompActions:
    """What we actually changed on the session as a result of decomp signals."""
    state: str
    mult_tightened: Optional[float] = None        # the factor used
    calibration_max_factor: Optional[float] = None
    notes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return (self.mult_tightened is not None
                or self.calibration_max_factor is not None)


def apply_to_session(
    tracker: CalibrationTracker,
    session: StateSession,
    *,
    horizon: int = 1,
    lookback: int = 3,
    mult_factor: float = 0.85,
    cov95_threshold: float = 0.7,
    max_factor_increment: float = 0.25,
    max_factor_cap: float = 2.5,
    default_max_factor: float = 1.5,
) -> DecompActions:
    """Compute signals + apply both recommendations to `session` in place.

    Side effects on `session`:
      - `session.bounds`: the `mult__FREE` entry's `high` is multiplied
        by `mult_factor` when a positive-bias trigger fires.
      - `session.tuning["calibration_max_factor"]`: set to the new
        widened value when cov_95 is chronically low.

    Returns a `DecompActions` describing what was changed. `bool()` of the
    result is True iff anything was actually mutated.
    """
    sig = compute_recent_signals(tracker, session.state, horizon=horizon,
                                  lookback=lookback)
    notes: list[str] = []
    mult_factor_used: Optional[float] = None
    new_max_factor: Optional[float] = None

    mt = recommend_mult_tighten(sig, factor=mult_factor)
    if mt is not None:
        for i, fp in enumerate(session.bounds):
            if fp.name == "mult__FREE":
                new_high = max(fp.low * 1.05, fp.high * mt.new_high_factor)
                session.bounds[i] = FreeParam(fp.name, fp.low, float(new_high))
                mult_factor_used = mt.new_high_factor
                notes.append(f"mult upper: ×{mt.new_high_factor:.2f} ({mt.reason})")
                break

    current = float(session.tuning.get("calibration_max_factor",
                                        default_max_factor))
    cw = recommend_calibration_widen(
        sig, current_max_factor=current,
        cov95_threshold=cov95_threshold,
        increment=max_factor_increment, cap=max_factor_cap,
    )
    if cw is not None:
        session.tuning["calibration_max_factor"] = cw.new_max_factor
        new_max_factor = cw.new_max_factor
        notes.append(
            f"calibration max_factor: {current:.2f}→{cw.new_max_factor:.2f} "
            f"({cw.reason})"
        )

    return DecompActions(
        state=session.state,
        mult_tightened=mult_factor_used,
        calibration_max_factor=new_max_factor,
        notes=tuple(notes),
    )
