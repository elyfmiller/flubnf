"""In-Python mirror of the SIHRS model in `models/SIHRS.bngl`.

A 1-to-1 numerical re-implementation of the flagship SIHRS model, used the same
way `simulate.py` mirrors the legacy SIR: to predict `H_weekly(t)` from a
parameter set without shelling out to BioNetGen. Two jobs:

  1. compute the per-state `scaled` magnitude anchor analytically, so `mult`
     lands in the middle of its prior instead of pinning at the ceiling; and
  2. drive residual-based diagnostics and DE-bootstrap quantiles.

Compartments are FRACTIONS of the initial susceptible pool (S(0)=1, I(0)=I0),
time is in weeks, all rates are per week, seasonal period is 52 weeks:

    beta(t) = beta0 * exp( eps1*cos(2*pi*(t-phi1)/52)
                         + eps2*cos(4*pi*(t-phi2)/52) ),   beta0 = R0*gamma

    dS/dt = -beta(t)*S*I + omega*R
    dI/dt =  beta(t)*S*I - gamma*I
    dH/dt =  rho*gamma*I - gammaH*H
    dR/dt =  (1-rho)*gamma*I + gammaH*H - omega*R
    dHadm/dt = rho*gamma*I                    (cumulative admissions)

    H_weekly(t) = rho*gamma*I(t) * mult * scaled

Note `H_weekly` is the ADMISSION FLUX into H (`rho*gamma*I`), never the census
`H(t)` — matching the BNGL comment. `I0` is fixed in the model, not fitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.integrate import solve_ivp

# Free parameters of models/SIHRS.bngl (11), plus the fixed structural ones.
SIHRS_FREE = ("R0", "eps1", "phi1", "eps2", "phi2",
              "gamma", "rho", "gammaH", "omega", "mult", "r")
SIHRS_FIXED = ("scaled", "I0", "pi")

# Literature-ish nominal values; used only for the analytic anchor, never fitted.
NOMINAL: dict = {
    "impr": 1e-7,
    "R0": 1.3, "eps1": 0.35, "phi1": 4.0, "eps2": 0.0, "phi2": 0.0,
    "gamma": 2.33,      # 1/gamma ~ 3 days
    "rho": 0.02,        # IHR ~2%
    "gammaH": 1.17,     # ~6 day length of stay
    "omega": 0.019,     # ~1 year immunity
    "I0": 2.893509458464661732e-02,
}


@dataclass(frozen=True)
class SihrsResult:
    t: np.ndarray
    S: np.ndarray
    I: np.ndarray
    H: np.ndarray
    R: np.ndarray
    Hadm: np.ndarray
    H_weekly: np.ndarray   # rho*gamma*I*mult*scaled at integer weeks


def beta_of_t(t, *, R0: float, gamma: float, eps1: float, phi1: float,
              eps2: float = 0.0, phi2: float = 0.0) -> float:
    """The BNGL beta() function. exp() keeps beta > 0 by construction."""
    beta0 = R0 * gamma
    return beta0 * np.exp(eps1 * np.cos(2 * np.pi * (t - phi1) / 52.0)
                          + eps2 * np.cos(4 * np.pi * (t - phi2) / 52.0))


def simulate_sihrs(params: Mapping[str, float], n_weeks: int = 48) -> SihrsResult:
    """Integrate SIHRS on weeks 0..n_weeks and return the trajectory.

    `params` may use PyBNF `__FREE` suffixes; they are stripped. Missing values
    fall back to NOMINAL (so the anchor helper can run on a partial set).
    `mult` and `scaled` default to 1.0, which makes `H_weekly` the raw model
    admission-incidence fraction — the quantity the anchor needs.
    """
    p = {(k[:-6] if k.endswith("__FREE") else k): float(v)
         for k, v in params.items()}
    g = lambda k, d=None: float(p.get(k, NOMINAL.get(k, d)))

    R0, gamma, rho = g("R0"), g("gamma"), g("rho")
    gammaH, omega = g("gammaH"), g("omega")
    impr = float(p.get("impr", 0.0))   # external force of infection (S->I)
    eps1, phi1, eps2, phi2 = g("eps1"), g("phi1"), g("eps2", 0.0), g("phi2", 0.0)
    I0 = g("I0")
    mult = float(p.get("mult", 1.0))
    scaled = float(p.get("scaled", 1.0))

    # Population form (templates/SIHRS_pop.bngl): absolute people, frequency-
    # dependent infection beta*S*I/N, and NO magnitude anchor -- `mult` is a pure
    # ascertainment fraction. Selected by passing N. Substituting s=S/N, i=I/N
    # recovers the normalized dynamics identically, so R0/gamma/eps/phi priors
    # transfer unchanged (asserted in tests/test_sihrs_anchor.py).
    N = float(p.get("N", 1.0))
    if N != 1.0:
        s0 = float(p.get("s0", 1.0))
        i0 = float(p.get("i0", I0))
        y0 = [N * s0, N * i0, 0.0, N * max(0.0, 1.0 - s0 - i0), 0.0]
        # No `scaled` in the population form; keep it multiplicative-neutral.
        scaled = float(p.get("scaled", 1.0))
    else:
        y0 = [1.0, I0, 0.0, 0.0, 0.0]

    def rhs(t, y):
        S, I, H, R, _ = y
        b = beta_of_t(t, R0=R0, gamma=gamma, eps1=eps1, phi1=phi1,
                      eps2=eps2, phi2=phi2)
        infection = b * S * I / N          # N == 1.0 reduces to beta*S*I
        imported = impr * S                # external reseeding; keeps I off the floor
        to_H = rho * gamma * I
        to_R = (1.0 - rho) * gamma * I
        disch = gammaH * H
        wane = omega * R
        return [-infection - imported + wane,
                infection + imported - gamma * I,
                to_H - disch,
                to_R + disch - wane,
                to_H]

    t_eval = np.arange(0.0, n_weeks + 1.0, 1.0)
    sol = solve_ivp(rhs, (0.0, float(n_weeks)), y0,
                    t_eval=t_eval, method="LSODA", rtol=1e-8, atol=1e-10)
    S, I, H, R, Hadm = sol.y
    return SihrsResult(t=sol.t, S=S, I=I, H=H, R=R, Hadm=Hadm,
                       H_weekly=rho * gamma * I * mult * scaled)


def peak_admission_fraction(params: Mapping[str, float] | None = None,
                            n_weeks: int = 48) -> float:
    """max_t of the UNSCALED model admission incidence rho*gamma*I(t).

    This is the factor the magnitude anchor must absorb. It is tiny (order 1e-3),
    which is exactly why an anchor built only from the observed peak leaves
    `mult` needing to be O(100).
    """
    res = simulate_sihrs(dict(params or {}), n_weeks=n_weeks)
    return float(np.max(res.H_weekly))


def scaled_anchor(observed_peak: float,
                  params: Mapping[str, float] | None = None,
                  *, target_mult: float = 1.0, n_weeks: int = 48) -> float:
    """Per-state `scaled` that puts `mult` at `target_mult` for this peak.

    Solve  observed_peak = target_mult * scaled * max_t[rho*gamma*I(t)]  for
    `scaled`. Anchoring on the model's own peak admission fraction (rather than
    on the observed peak alone) is what keeps `mult` inside its prior: `mult`
    then only has to absorb reporting error, not the attack-rate scale.
    """
    f = peak_admission_fraction(params, n_weeks=n_weeks)
    if f <= 0:
        raise ValueError("model produced no admissions; cannot anchor")
    return float(observed_peak) / (float(target_mult) * f)
