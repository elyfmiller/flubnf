"""RESEARCH (reference implementation, not the shipped engine): a sequential
particle filter for SIHRS. The shipped filter is fit_type = pf in the PyBNF
fork, driven by app/core/engines/pf.py; this module is used by
scripts/pf_run.py and tests to develop and benchmark the mechanism.

Last week's posterior is this week's prior, so old data decays through the
prior instead of weighing equally in a batch refit. Parameters drift too
(Liu-West jitter shrunk toward the ensemble mean): `jitter` sets how fast
the mechanism may change its mind; too much and it becomes a random walk.

Propagation is the SIHRS_pop_min.bngl ODE system (annual harmonic only, no
import term) with daily fixed-step RK4 vectorised across particles, pinned
against scipy solve_ivp at 2e-3 relative in tests/test_particle_filter.py.
Resampling is ESS-triggered; watch `ess` for particle depletion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

RHO, GAMMAH, OMEGA = 0.02, 1.17, 0.019
STEPS_PER_WEEK = 7


@dataclass
class Particles:
    """Parameter vectors and compartment states for the ensemble."""
    Reff: np.ndarray
    eps1: np.ndarray
    phi1: np.ndarray
    mult: np.ndarray
    r: np.ndarray
    S: np.ndarray
    I: np.ndarray
    H: np.ndarray
    R: np.ndarray
    w: np.ndarray          # normalised weights

    def n(self) -> int:
        return self.Reff.size


def _beta(t, Reff, eps1, phi1, s0):
    return (Reff * GAMMA_W / s0) * np.exp(eps1 * np.cos(2 * np.pi * (t - phi1) / 52))


GAMMA_W = 7.0 / 3.2  # must equal sihrs_priors.gamma_per_week()


def propagate(p: Particles, t0: float, weeks: float, N: float, s0: float,
              accumulate: bool = True):
    """Advance every particle `weeks` weeks with fixed-step RK4.

    Returns cumulative ascertained admissions over the interval when
    `accumulate`, which is the observable the likelihood uses.
    """
    dt = 1.0 / STEPS_PER_WEEK
    nsteps = int(round(weeks * STEPS_PER_WEEK))
    S, I, H, R = p.S.copy(), p.I.copy(), p.H.copy(), p.R.copy()
    adm = np.zeros_like(S)

    def deriv(t, S, I, H, R):
        b = _beta(t, p.Reff, p.eps1, p.phi1, s0)
        inf = b * S * I / N
        dS = -inf + OMEGA * R
        dI = inf - GAMMA_W * I
        dH = RHO * GAMMA_W * I - GAMMAH * H
        dR = (1 - RHO) * GAMMA_W * I + GAMMAH * H - OMEGA * R
        return dS, dI, dH, dR, RHO * GAMMA_W * I      # last = admission flux

    t = t0
    for _ in range(nsteps):
        k1 = deriv(t, S, I, H, R)
        k2 = deriv(t + dt / 2, S + dt / 2 * k1[0], I + dt / 2 * k1[1],
                   H + dt / 2 * k1[2], R + dt / 2 * k1[3])
        k3 = deriv(t + dt / 2, S + dt / 2 * k2[0], I + dt / 2 * k2[1],
                   H + dt / 2 * k2[2], R + dt / 2 * k2[3])
        k4 = deriv(t + dt, S + dt * k3[0], I + dt * k3[1],
                   H + dt * k3[2], R + dt * k3[3])
        S = np.maximum(S + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]), 0.0)
        I = np.maximum(I + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]), 0.0)
        H = np.maximum(H + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]), 0.0)
        R = np.maximum(R + dt / 6 * (k1[3] + 2 * k2[3] + 2 * k3[3] + k4[3]), 0.0)
        if accumulate:
            adm += dt / 6 * (k1[4] + 2 * k2[4] + 2 * k3[4] + k4[4])
        t += dt
    p.S, p.I, p.H, p.R = S, I, H, R
    return adm * p.mult      # ascertained


def _nb_logpmf(y, mu, r):
    from scipy.special import gammaln
    mu = np.maximum(mu, 1e-9)
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
            + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def ess(w) -> float:
    return float(1.0 / np.sum(w ** 2))


def resample(p: Particles, rng, return_idx: bool = False):
    """Systematic resampling -- lower variance than multinomial.

    `return_idx` hands back the ancestor indices. Anything holding per-particle
    history (see `anchor_factors`) MUST permute it by these, or row i of that
    history will describe a particle that no longer exists.
    """
    n = p.n()
    pos = (rng.random() + np.arange(n)) / n
    idx = np.searchsorted(np.cumsum(p.w), pos)
    idx = np.clip(idx, 0, n - 1)
    out = Particles(*[a[idx] for a in (p.Reff, p.eps1, p.phi1, p.mult, p.r,
                                       p.S, p.I, p.H, p.R)],
                    w=np.full(n, 1.0 / n))
    return (out, idx) if return_idx else out


def anchor_factors(mu_hist, obs_hist, clamp=(0.25, 4.0),
                   mode: str = "particle") -> np.ndarray:
    """Per-particle multiplicative anchor, matching amcmc.anchor_trajectories.

    Unanchored, the filter scored worse than baseline at h=0. mode
    "particle": factor_i = clipped geomean over the lookback of observed /
    particle i's mean, which shifts AND contracts the ensemble. mode
    "scalar": one factor for all (as anchor_analysis.transform), a pure
    shift; contraction can hurt an already overconfident filter.
    """
    mu = np.vstack(mu_hist)                      # (k, n_particles)
    obs = np.asarray(obs_hist, float)[:, None]   # (k, 1)
    safe_mu = np.where(mu < 0.5, 0.5, mu)
    safe_obs = np.where(obs < 0.5, 0.5, obs)
    if mode == "scalar":
        med = np.median(safe_mu, axis=1, keepdims=True)     # (k, 1)
        f = float(np.exp(np.mean(np.log(np.clip(safe_obs / med, 1e-6, 1e6)))))
        return np.full(mu.shape[1], float(np.clip(f, clamp[0], clamp[1])))
    log_r = np.log(np.clip(safe_obs / safe_mu, 1e-6, 1e6))
    return np.clip(np.exp(np.mean(log_r, axis=0)), clamp[0], clamp[1])


def jitter_params(p: Particles, rng, jitter: float, bounds: dict):
    """Liu-West shrinkage: move each particle toward the ensemble mean, then add
    matched noise. Preserves the mean and does NOT inflate variance, which naive
    additive jitter does."""
    a = np.sqrt(1.0 - jitter ** 2)
    for name in ("Reff", "eps1", "phi1", "mult", "r"):
        v = getattr(p, name)
        m = np.average(v, weights=p.w)
        sd = np.sqrt(max(np.average((v - m) ** 2, weights=p.w), 1e-12))
        v = a * v + (1 - a) * m + jitter * sd * rng.standard_normal(v.size)
        lo, hi = bounds[name]
        setattr(p, name, np.clip(v, lo, hi))


def update(p: Particles, y: float, t0: float, N: float, s0: float, rng,
           jitter: float, bounds: dict, ess_frac: float = 0.5) -> dict:
    """One weekly step: jitter -> propagate one week -> reweight on y -> resample.

    Returns `pit`, the probability-integral transform of `y` under the ONE-STEP
    predictive formed before `y` was seen. It is the honest online calibration
    signal -- see `AdaptiveJitter`.
    """
    jitter_params(p, rng, jitter, bounds)
    mu = propagate(p, t0, 1.0, N, s0)
    lw = np.log(np.maximum(p.w, 1e-300)) + _nb_logpmf(y, mu, p.r)
    lw -= lw.max()
    w = np.exp(lw)
    tot = w.sum()
    if not np.isfinite(tot) or tot <= 0:
        return {"ok": False, "ess": 0.0}

    # PIT under the weights carried IN (the updated ones would be circular)
    pit = _pit(y, mu, p.r, p.w, rng)

    p.w = w / tot
    e = ess(p.w)
    idx = None
    if e < ess_frac * p.n():
        newp, idx = resample(p, rng, return_idx=True)
        p.__dict__.update(newp.__dict__)
    return {"ok": True, "ess": e, "pit": pit, "mu": mu, "resample_idx": idx,
            "pred_mean": float(np.average(mu, weights=w / tot))}


def _pit(y, mu, r, w, rng, n_draw: int = 2000) -> float:
    """P(Y_pred <= y) under the mixture predictive, randomised for discreteness.

    P(Y<y) + U*P(Y=y): uniform for a perfect forecaster despite discreteness
    (the raw CDF is biased at low counts).
    """
    idx = rng.choice(w.size, size=min(n_draw, w.size * 4), p=w)
    m, rr = np.maximum(mu[idx], 1e-9), r[idx]
    draws = rng.negative_binomial(rr, rr / (rr + m))
    below = float(np.mean(draws < y))
    equal = float(np.mean(draws == y))
    return below + float(rng.random()) * equal


class AdaptiveJitter:
    """Choose `jitter` online from the filter's own calibration. No constant.

    The best fixed jitter moves from season to season, so it cannot be
    chosen in advance. Under a calibrated one-step predictive E|PIT - 1/2| =
    1/4: larger means too tight (raise jitter), smaller too wide. Only data
    in hand is used. Multiplicative update on log-jitter, clipped to [lo, hi],
    after `warmup` uninformative early PITs.
    """

    def __init__(self, init: float = 0.30, gain: float = 0.6,
                 lo: float = 0.05, hi: float = 0.90, warmup: int = 4,
                 halflife: float = 6.0):
        self.jitter = float(init)
        self.gain, self.lo, self.hi = gain, lo, hi
        self.warmup, self.halflife = warmup, halflife
        self._stat: Optional[float] = None
        self._n = 0
        self.history: list = []

    def observe(self, pit: float) -> float:
        """Feed one PIT, get the jitter to use on the NEXT step."""
        if pit is None or not np.isfinite(pit):
            return self.jitter
        self._n += 1
        d = abs(float(pit) - 0.5)
        a = 0.5 ** (1.0 / self.halflife)
        self._stat = d if self._stat is None else a * self._stat + (1 - a) * d
        if self._n > self.warmup:
            # >1 means under-dispersed (tails too thin) -> more jitter
            ratio = self._stat / 0.25
            self.jitter = float(np.clip(
                self.jitter * np.exp(self.gain * np.log(max(ratio, 1e-3))),
                self.lo, self.hi))
        self.history.append(self.jitter)
        return self.jitter


def forecast(p: Particles, t0: float, horizons, N: float, s0: float, rng,
             factors: Optional[np.ndarray] = None,
             drift: float = 0.0, bounds: Optional[dict] = None) -> dict:
    """Predictive draws at each horizon, with negative-binomial observation noise.

    Works on a COPY. `factors` (anchor_factors) scale the mean before
    observation noise, as in production. `drift` keeps jittering parameters
    over the horizon; without it the spread barely widens with h.
    """
    import copy
    q = copy.deepcopy(p)
    out, t = {}, t0
    for h in range(1, max(horizons) + 1):
        if drift and bounds:
            jitter_params(q, rng, drift, bounds)
        mu = propagate(q, t, 1.0, N, s0)
        if factors is not None:
            mu = mu * factors
        t += 1.0
        if h in horizons:
            draws = rng.negative_binomial(q.r, q.r / (q.r + np.maximum(mu, 1e-9)))
            # weight-aware: resample draws by particle weight
            idx = rng.choice(q.n(), size=q.n(), p=q.w)
            out[str(h)] = draws[idx].astype(float).tolist()
    return out
