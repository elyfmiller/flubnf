"""State-adaptive initial bounds for the SIR fit.

The legacy template `Alabama.conf` uses fixed bounds:

    uniform_var = I0__FREE  0.001 0.01
    uniform_var = b0__FREE  0.1   1.5
    uniform_var = gamma__FREE 0.01 0.5
    uniform_var = mult__FREE 100  8000
    uniform_var = r__FREE    1    30
    uniform_var = t0__FREE   0    12

The `mult` ceiling of 8000 silently breaks for high-volume jurisdictions
(California, Texas, Florida, New York) whose weekly admissions exceed it.
PyBNF's DE then sits at the ceiling, finds no good fit, and the backtest
records terrible WIS.

This module computes per-state initial bounds as a function of the observed
admissions to date. The rules are deterministic — same input, same bounds:

    mult.upper  = max(8000, 5 × peak_observed)
    mult.lower  = max(100,  0.01 × peak_observed)
    everything else: keep template defaults

The 5× / 0.01× factors give the DE meaningful headroom without being
absurdly wide. `r` (negbin dispersion) and the structural SIR params don't
scale with admissions volume — only `mult` does.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .conf_files import FreeParam

log = logging.getLogger(__name__)


def adaptive_initial_bounds(
    observed: np.ndarray,
    *,
    base: Optional[list[FreeParam]] = None,
    mult_upper_safety: float = 5.0,
    mult_lower_safety: float = 0.01,
    model_type: str = "sir_piecewise",
    population: Optional[float] = None,
    peak_attack_rate: float = 0.02,
) -> list[FreeParam]:
    """Build initial bounds that scale with observed admissions.

    Args:
        observed: Observed H_weekly for this state up to "now".
        base:     Override the default template bounds. If None, uses the
                  defaults for `model_type`.
        mult_upper_safety: factor over peak to set the mult upper bound
                  (sir_piecewise only).
        mult_lower_safety: factor under peak to set the mult lower bound
                  (sir_piecewise only).
        model_type: "sir_piecewise" (legacy mult-scales-with-peak) or
                  "sirs_logistic" (mult is an ascertainment fraction; I0 is an
                  absolute count anchored to `population`).
        population: absolute state population N (required to anchor the SIRS
                  mult fraction and the I0 count; ignored for sir_piecewise).
        peak_attack_rate: assumed fraction of the population infected at the
                  peak week, used to invert observed peak admissions into an
                  ascertainment×IHR `mult` center. ~2% is a defensible flu value.
    """
    base = base or _template_bounds(model_type)
    if observed is None or len(observed) == 0:
        return list(base)
    peak = float(np.nanmax(observed))
    if not np.isfinite(peak) or peak <= 0:
        return list(base)

    if model_type == "sirs_logistic":
        return _sirs_adaptive_bounds(base, peak, population, peak_attack_rate)

    out: list[FreeParam] = []
    for fp in base:
        if fp.name == "mult__FREE":
            new_upper = max(fp.high, mult_upper_safety * peak)
            new_lower = min(fp.low, max(1.0, mult_lower_safety * peak))
            if new_upper != fp.high or new_lower != fp.low:
                log.info(
                    "  bounds_init: mult %.0f-%.0f -> %.0f-%.0f (peak=%.0f)",
                    fp.low, fp.high, new_lower, new_upper, peak,
                )
            out.append(FreeParam(fp.name, new_lower, new_upper))
        else:
            out.append(fp)
    return out


def _sirs_adaptive_bounds(
    base: list[FreeParam], peak: float,
    population: Optional[float], peak_attack_rate: float,
) -> list[FreeParam]:
    """Anchor the SIRS `mult` (ascertainment×IHR fraction) and `I0` (absolute
    initial-infected count) to the observed peak + population.

    mult_center ~= peak / (N * peak_attack_rate); bounds 0.1x .. 10x, clamped
    to the physically-plausible [1e-4, 5e-2] box. I0 upper ~= 0.001 * N.
    """
    if population is None or population <= 0:
        return list(base)  # cannot anchor without N; leave static box

    mult_center = peak / (population * peak_attack_rate)
    mult_lower = max(1e-4, 0.1 * mult_center)
    mult_upper = min(5e-2, 10.0 * mult_center)
    if mult_lower >= mult_upper:  # degenerate (tiny/huge peak) -> fall back
        mult_lower, mult_upper = 1e-4, 5e-2
    i0_upper = max(10.0, 1e-3 * population)

    out: list[FreeParam] = []
    for fp in base:
        if fp.name == "mult__FREE":
            log.info("  bounds_init[SIRS]: mult fraction -> %.2e..%.2e "
                     "(peak=%.0f, N=%.0f)", mult_lower, mult_upper, peak, population)
            out.append(FreeParam(fp.name, mult_lower, mult_upper))
        elif fp.name == "I0__FREE":
            out.append(FreeParam(fp.name, 1.0, i0_upper))
        else:
            out.append(fp)
    return out


def _template_bounds(model_type: str = "sir_piecewise") -> list[FreeParam]:
    if model_type == "sirs_logistic":
        # Smooth-beta SIRS box. Centers/width/omega are FIXED (not here).
        # Each transition adds one signed amplitude db_k (appended elsewhere).
        return [
            FreeParam("b0__FREE", 0.05, 1.5),
            FreeParam("db1__FREE", -1.2, 1.2),
            FreeParam("gamma__FREE", 0.01, 0.5),
            FreeParam("mult__FREE", 1e-4, 5e-2),   # ascertainment x IHR fraction
            FreeParam("r__FREE", 1, 30),
            FreeParam("I0__FREE", 1.0, 1000.0),    # absolute count; anchored later
        ]
    return [
        FreeParam("I0__FREE", 0.001, 0.01),
        FreeParam("b0__FREE", 0.1, 1.5),
        FreeParam("gamma__FREE", 0.01, 0.5),
        FreeParam("mult__FREE", 100, 8000),
        FreeParam("r__FREE", 1, 30),
        FreeParam("t0__FREE", 0, 12),
    ]


def max_steps_for_state(observed: np.ndarray) -> int:
    """Heuristic: small-population states (peak < 50) get K_max=1; medium
    (peak < 500) get K_max=3; large (>500) get K_max=6.

    Reasoning: a multi-wave structure only resolves above the noise floor.
    Wyoming-class states have peaks ~30 admissions/wk where the SIR fit is
    already at the limit of what's identifiable; adding piecewise steps
    just overfits."""
    if observed is None or len(observed) == 0:
        return 5
    peak = float(np.nanmax(observed))
    if peak < 50:
        return 1
    if peak < 500:
        return 3
    return 6


def max_transitions_for_state(observed: np.ndarray) -> int:
    """SIRS smooth-beta analogue of `max_steps_for_state`: the maximum number
    of logistic transitions (each one free amplitude `db_k`) to allow.

    Small states (peak < 50) get 1 transition; medium (< 500) get 2; large
    get 3. This caps the free-parameter budget at 6/7/8 respectively — every
    tier inside the stable AMCMC band — and matches the count of FIXED
    transition centers declared in the SIRS template."""
    if observed is None or len(observed) == 0:
        return 2
    peak = float(np.nanmax(observed))
    if peak < 50:
        return 1
    if peak < 500:
        return 2
    return 3
