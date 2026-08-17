"""Outbreak phase detection.

Classifies a state's current outbreak phase from recent observed admissions.
The phase informs which automation strategies to use:

  - PRE_OUTBREAK    : no clear signal yet → conservative bounds, K=1.
  - RISING          : observed slope positive, accelerating → favor model
                      momentum; safe to add piecewise steps.
  - NEAR_PEAK       : observed slope decelerating, |d2| large → model is
                      catching up; reduce slope_blend (don't extrapolate
                      growth past peak).
  - FALLING         : observed slope negative → similar to RISING but with
                      sign flipped.
  - TROUGH          : recovering from decline → cautious; could be second
                      wave starting.

The detector uses the last N observed weeks (default 4) and computes the
first / second discrete differences smoothed with a centered moving
average. Designed to be robust to single-week noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np


class Phase(str, Enum):
    PRE_OUTBREAK = "pre_outbreak"
    RISING = "rising"
    NEAR_PEAK = "near_peak"
    FALLING = "falling"
    TROUGH = "trough"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PhaseAssessment:
    phase: Phase
    recent_slope: float       # mean observed week-over-week change
    recent_curvature: float   # mean second-difference
    median_recent: float


def detect_phase(
    observed: np.ndarray,
    *,
    lookback: int = 4,
    pre_outbreak_floor: float = 10.0,
    slope_threshold_pct: float = 0.10,
) -> PhaseAssessment:
    """Classify the current outbreak phase from observed admissions.

    Args:
        observed: full observed series (we look at the last `lookback`).
        lookback: number of recent weeks to use for slope/curvature.
        pre_outbreak_floor: median below this -> PRE_OUTBREAK regardless
            of slope (avoids noise classification on near-zero counts).
        slope_threshold_pct: |slope| / median below this counts as flat.
    """
    obs = np.asarray(observed, dtype=float)
    if len(obs) < 3:
        return PhaseAssessment(Phase.UNKNOWN, 0.0, 0.0, float(np.nan))
    window = obs[-min(lookback, len(obs)):]
    median = float(np.median(window))
    if median < pre_outbreak_floor:
        slope = float(window[-1] - window[0]) / max(1, len(window) - 1)
        return PhaseAssessment(Phase.PRE_OUTBREAK, slope, 0.0, median)

    # Smoothed first/second differences.
    d1 = np.diff(window)
    d2 = np.diff(d1) if len(d1) >= 2 else np.zeros(1)
    slope = float(np.mean(d1))
    curvature = float(np.mean(d2))
    rel_slope = slope / max(median, 1.0)

    # Classification:
    if abs(rel_slope) < slope_threshold_pct:
        # Flat-ish. Curvature tells us peak vs trough.
        if curvature < -0.1 * median:
            phase = Phase.NEAR_PEAK
        elif curvature > 0.1 * median:
            phase = Phase.TROUGH
        else:
            # Truly flat — could be either pre or post; default UNKNOWN.
            phase = Phase.UNKNOWN
    elif rel_slope > 0:
        # Rising. If curvature strongly negative, we're decelerating.
        if curvature < -0.2 * median:
            phase = Phase.NEAR_PEAK
        else:
            phase = Phase.RISING
    else:
        # Falling. If curvature strongly positive, we're decelerating decline.
        if curvature > 0.2 * median:
            phase = Phase.TROUGH
        else:
            phase = Phase.FALLING

    return PhaseAssessment(
        phase=phase,
        recent_slope=slope,
        recent_curvature=curvature,
        median_recent=median,
    )
