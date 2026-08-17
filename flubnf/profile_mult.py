"""Estimate `mult` analytically and fix it, instead of sampling it.

WHY
---
`mult` is an ascertainment fraction that appears ONLY in the observable
(`H_weekly = rho*mult*gamma*I`) and never in the dynamics. So for any trajectory
its optimum is available in closed form, and sampling it buys nothing except a
badly conditioned posterior:

    sampled (5 params)    Hessian condition number  402,219
    profiled (4 params)                              36,773   <- 10.9x better
    fit error   0.154 -> 0.158     forecast error 0.628 -> 0.644 (p=0.846)

Two of the four worst posterior ridges involve `mult` (Reff<->mult -0.668,
eps1<->mult -0.548), and the sampler cannot traverse them: measured multi-chain
R-hat 3.25 and ESS 44 with `mult` free.

THIS IS THE CHEAP APPROXIMATION TO PROFILING
--------------------------------------------
True profiling recomputes `mult*` inside the objective at every proposal, which
needs a PyBNF change. This module does it once, up front, on the in-Python
mirror -- a DE fit costing seconds rather than a second 14-minute AMCMC run --
then FIXES `mult` in the materialised model so PyBNF samples one fewer
dimension.

The approximation is that `mult*` is computed at the mirror's optimum rather
than at every point the chain visits. Because `mult` enters purely
multiplicatively, the optimum moves little as the other parameters vary, so this
recovers most of the geometric benefit. It is an approximation, not an identity
-- `needs_fallback()` exists to catch the cases where it is a bad one.

THE CLAMP IS A DIAGNOSTIC, NOT A DETAIL
---------------------------------------
`mult` is a FRACTION: ascertainment cannot exceed 1. Measured across 36 fits the
analytic optimum ranged 0.013 to 1.777, exceeding 1.0 in **8%** of cases. The
prior wall used to hide that; profiling exposes it. When the clamp fires it means
the model cannot generate as many admissions as are reported, i.e. the FIXED
`rho` (IHR = 0.02) is too small for that state -- a different repair, and worth
surfacing rather than silently clipping.

OBJECTIVE MISMATCH, STATED
--------------------------
The mirror optimises log-space squared error; PyBNF optimises a negative-binomial
likelihood. For a pure multiplicative scale the two optima are close but not
identical, so `mult*` is a good starting value rather than the exact NB optimum.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .simulate_sihrs import simulate_sihrs
from .sihrs_fit import GAMMAH_PER_WEEK, OMEGA_PER_WEEK, RHO_IHR, StateSetup

MULT_MIN, MULT_MAX = 1e-4, 1.0     # ascertainment is a fraction
DE_BOUNDS = [(0.6, 2.5), (0.0, 1.0), (0.0, 52.0), (0.0, 0.4), (0.0, 26.0), (0.2, 5.0)]


@dataclass(frozen=True)
class MultEstimate:
    """`mult*` plus everything needed to judge whether to trust it."""
    mult: float
    raw: float                 # before clamping
    clamped: bool              # True => rho is too small for this state
    fit_err: float             # median relative error at the mirror optimum
    ok: bool

    def needs_fallback(self, max_fit_err: float = 0.60) -> bool:
        """Fit `mult` normally instead of fixing it.

        Triggered when the mirror could not fit the state at all (so `mult*` is
        meaningless), or when the clamp fired (so the true optimum is outside
        the physical range and fixing at 1.0 would bake in a known-wrong value).
        """
        return (not self.ok) or self.clamped or not np.isfinite(self.fit_err) \
            or self.fit_err > max_fit_err


def optimal_mult(unscaled: np.ndarray, observed: np.ndarray) -> Optional[float]:
    """Closed-form multiplicative scale: the geometric mean ratio.

    Minimises sum (log(mult*B_t) - log(obs_t))^2 exactly, which is why sampling
    `mult` is wasted effort -- the optimum is attained, not searched for.
    """
    n = len(observed)
    b = np.asarray(unscaled, float)[:n]
    o = np.asarray(observed, float)
    m = (o > 0) & (b > 0) & np.isfinite(b) & np.isfinite(o)
    if m.sum() < 3:
        return None
    return float(np.exp(np.mean(np.log(o[m]) - np.log(b[m]))))


def _unscaled(x, s: StateSetup, n_weeks: int) -> Optional[np.ndarray]:
    """rho*gamma*I -- the observable with `mult` factored out."""
    Reff, eps1, phi1, eps2, phi2, i0f = x
    p = dict(N=s.population, s0=s.s0, i0=s.i0 * i0f, gamma=s.gamma, rho=RHO_IHR,
             gammaH=GAMMAH_PER_WEEK, omega=OMEGA_PER_WEEK, R0=Reff / s.s0,
             eps1=eps1, phi1=phi1, eps2=eps2, phi2=phi2, mult=1.0, impr=1e-7)
    try:
        r = simulate_sihrs(p, n_weeks=n_weeks)
    except Exception:
        return None
    h = r.H_weekly
    return h if np.all(np.isfinite(h)) and np.any(h > 0) else None


def estimate(setup: StateSetup, *, maxiter: int = 40, popsize: int = 14,
             seed: int = 0) -> MultEstimate:
    """Mirror DE fit with `mult` profiled out, returning the analytic optimum.

    Seconds, not minutes -- this is the whole point of doing round 1 on the
    mirror rather than as a second PyBNF run.
    """
    from scipy.optimize import differential_evolution
    obs = np.asarray(setup.observed, float)
    n = len(obs)

    def obj(x):
        b = _unscaled(x, setup, n + 4)
        if b is None:
            return 1e6
        m = optimal_mult(b, obs)
        if m is None:
            return 1e6
        h = b[:n] * m
        return float(np.mean((np.log(np.maximum(h, 1e-9))
                              - np.log(np.maximum(obs, 1e-9))) ** 2))

    try:
        r = differential_evolution(obj, DE_BOUNDS, seed=seed, maxiter=maxiter,
                                   popsize=popsize, tol=1e-8, polish=True)
    except Exception:
        return MultEstimate(np.nan, np.nan, False, np.nan, ok=False)
    b = _unscaled(r.x, setup, n + 4)
    if b is None:
        return MultEstimate(np.nan, np.nan, False, np.nan, ok=False)
    raw = optimal_mult(b, obs)
    if raw is None or not np.isfinite(raw):
        return MultEstimate(np.nan, np.nan, False, np.nan, ok=False)
    m = float(np.clip(raw, MULT_MIN, MULT_MAX))
    err = float(np.median(np.abs(b[:n] * m - obs) / np.maximum(obs, 1.0)))
    return MultEstimate(mult=m, raw=float(raw), clamped=bool(raw > MULT_MAX),
                        fit_err=err, ok=True)


def fix_mult_in_model(model_path, mult: float) -> None:
    """Replace `mult  mult__FREE` with a fixed value in a materialised model.

    The model PARAMETER name stays `mult`, so `H_weekly() = rho*mult*gamma*I`
    and every reaction rule are untouched -- only the fitted-variable
    declaration disappears.
    """
    import re
    from pathlib import Path
    p = Path(model_path)
    txt = p.read_text()
    new, k = re.subn(r"^(mult\s+)mult__FREE", rf"\g<1>{mult:.8g}", txt, flags=re.M)
    if k != 1:
        raise ValueError(f"expected exactly one 'mult mult__FREE' line, found {k}")
    p.write_text(new)
