"""Cartesian <-> polar conversion for the seasonal beta coefficients.

The model fits (a, b); humans and the literature speak in (amplitude, phase).
These are the same harmonic in different coordinates:

    eps*cos(2*pi*(t-phi)/P)  ==  a*cos(2*pi*t/P) + b*sin(2*pi*t/P)
        a = eps*cos(2*pi*phi/P),  b = eps*sin(2*pi*phi/P)

Exact, not an approximation. Fitting in (a, b) removes three defects of the
polar form that together make the posterior unsamplable -- see
templates/SIHRS_pop_cart.bngl for the measurements. Reporting stays in
(eps, phi), which is what these helpers are for.

CONVERT SAMPLES, NOT SUMMARIES. `to_polar(median(a), median(b))` is NOT
`median(eps)`: the map is nonlinear, and the phase is circular so its ordinary
mean is wrong near the wrap point. Convert every posterior draw first, then
summarise with `summarize_phase`, which uses the circular mean.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

ANNUAL_PERIOD = 52.0
SEMIANNUAL_PERIOD = 26.0


class Polar(NamedTuple):
    """Amplitude and phase, phase wrapped into [0, period)."""
    eps: np.ndarray | float
    phi: np.ndarray | float


def to_polar(a, b, period: float = ANNUAL_PERIOD) -> Polar:
    """(a, b) -> (amplitude, phase). Works elementwise on arrays."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    eps = np.hypot(a, b)
    phi = np.mod(np.arctan2(b, a) * period / (2.0 * np.pi), period)
    if eps.ndim == 0:
        return Polar(float(eps), float(phi))
    return Polar(eps, phi)


def to_cartesian(eps, phi, period: float = ANNUAL_PERIOD):
    """(amplitude, phase) -> (a, b). Inverse of `to_polar`."""
    eps = np.asarray(eps, dtype=float)
    phi = np.asarray(phi, dtype=float)
    ang = 2.0 * np.pi * phi / period
    a, b = eps * np.cos(ang), eps * np.sin(ang)
    if a.ndim == 0:
        return float(a), float(b)
    return a, b


def seasonal_term(t, a: float, b: float, period: float = ANNUAL_PERIOD):
    """The harmonic itself, for checking a fit against the model."""
    t = np.asarray(t, dtype=float)
    return a * np.cos(2 * np.pi * t / period) + b * np.sin(2 * np.pi * t / period)


def summarize_phase(phi, period: float = ANNUAL_PERIOD) -> dict:
    """Circular mean and concentration of a phase sample.

    The ORDINARY mean of phases straddling the wrap point is meaningless --
    phases of 51 and 1 average to 26, the opposite side of the year. This
    averages unit vectors instead. `R` in [0,1] is the resultant length: near
    1 the phase is well determined, near 0 it is uniform on the circle, which
    is exactly what happens when the amplitude collapses toward zero.
    """
    phi = np.asarray(phi, dtype=float)
    phi = phi[np.isfinite(phi)]
    if phi.size == 0:
        return {"mean": float("nan"), "R": float("nan"), "n": 0}
    ang = 2.0 * np.pi * phi / period
    C, S = np.cos(ang).mean(), np.sin(ang).mean()
    R = float(np.hypot(C, S))
    mean = float(np.mod(np.arctan2(S, C) * period / (2.0 * np.pi), period))
    return {"mean": mean, "R": R, "n": int(phi.size)}


def circular_rhat(chains, period: float = ANNUAL_PERIOD) -> float:
    """Gelman-Rubin for a circular parameter, via the resultant vector.

    Linear R-hat on a phase is inflated: chains at 1 and 51 are nearly the
    SAME phase but score as maximally disagreeing. Measured on a real fit,
    linear R-hat read 127.2 where the circular value was 64.3 -- so the linear
    form overstates by ~2x. Note the circular value was still catastrophic:
    use this to measure the disagreement honestly, not to explain it away.
    """
    cs = [np.asarray(c, dtype=float) for c in chains]
    cs = [c[np.isfinite(c)] for c in cs]
    cs = [c for c in cs if c.size > 20]
    if len(cs) < 2:
        return float("nan")
    n = min(c.size for c in cs)
    cs = [c[-n:] for c in cs]
    xs = [np.cos(2 * np.pi * c / period) for c in cs]
    ys = [np.sin(2 * np.pi * c / period) for c in cs]
    W = float(np.mean([x.var(ddof=1) + y.var(ddof=1) for x, y in zip(xs, ys)]))
    if W <= 0:
        return float("nan")
    B = n * float(np.var([x.mean() for x in xs], ddof=1)
                  + np.var([y.mean() for y in ys], ddof=1))
    return float(np.sqrt((((n - 1) / n) * W + B / n) / W))
