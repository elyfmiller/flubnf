"""RESEARCH: estimate `mult` in closed form on the in-Python mirror and fix
it in the model, instead of sampling it (scripts/profiled_fit_run.py).

`mult` appears only in the observable (H_weekly = rho*mult*gamma*I), so
sampling it only adds a ridge (Hessian condition number 402k -> 37k when
profiled, at equal forecast error). This is the cheap approximation to true
profiling: mult* is computed once at the mirror's optimum (log-space squared
error, not PyBNF's NB likelihood), a good starting value rather than exact;
needs_fallback() says when to sample mult normally.

The clamp at 1 is a diagnostic: ascertainment cannot exceed 1, so a fired
clamp means the fixed rho (IHR 0.02) is too small for that state.
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
