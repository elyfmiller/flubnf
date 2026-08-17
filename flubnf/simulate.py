"""Tiny in-Python SIR simulator with piecewise-constant beta.

For the *analysis* layer we need to predict H_weekly(t) given best-fit
parameters so we can compute residuals against observed data — without
shelling out to BioNetGen, which adds latency and a dependency.

This is a 1-to-1 numerical re-implementation of the BNGL model in
`flubnf/templates/Alabama.bngl`:

    dS/dt = -beta(t) * S * I
    dI/dt =  beta(t) * S * I - gamma * I
    dR/dt =  gamma * I
    H_weekly(t) = I * S * mult * beta(t)

Initial conditions: S(0) = 1, I(0) = I0, R(0) = 0.

Piecewise beta: K constant segments with switch times t0, t0+t1, ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.integrate import solve_ivp


@dataclass(frozen=True)
class SimulationResult:
    t: np.ndarray
    S: np.ndarray
    I: np.ndarray
    R: np.ndarray
    H_weekly: np.ndarray  # I * S * mult * beta(t), sampled at integer weeks


def simulate(
    params: Mapping[str, float],
    n_steps: int,
    *,
    t_start: float = 0.0,
    model_type: str = "sir_piecewise",
) -> SimulationResult:
    """Run the in-Python model mirror from `t_start` to `t_start + n_steps`.

    `model_type`:
      - "sir_piecewise" (default): legacy fractional SIR with a
        piecewise-constant beta from `b0, t0, [b1, t1, ...]`. S0 = 1.
      - "sirs_logistic": smooth sum-of-logistics beta from
        `b0, db1, tc1, sw, [db2, tc2, ...]`. SIRS with waning rate `omega`
        (R->S) when present, and absolute-population scaling when `N` is
        present (S0 = N - I0, infection flux beta*S*I/N). Both `omega` and
        `N` are optional so this mirror can be exercised incrementally across
        the migration phases; absent => omega 0 / fractional (S0 = 1).

    `params` keys may use the PyBNF `__FREE` suffix; it is stripped.

    Returns the trajectory at integer time points
    `t = t_start, t_start+1, ..., t_start+n_steps`.
    """
    p = _strip_free(params)
    I0 = float(p["I0"])
    gamma = float(p["gamma"])
    mult = float(p["mult"])

    if model_type == "sirs_logistic":
        b0, dbs, centers, sw = _extract_logistic(p)
        beta = lambda t: _beta_logistic(t, b0, dbs, centers, sw)
        # Absolute population if N supplied, else fractional (S0 = 1).
        N = float(p.get("N", 1.0))
        omega = float(p.get("omega", 0.0))
    elif model_type == "sir_piecewise":
        bs, switch_times = _extract_piecewise(p)
        beta = lambda t: _beta_piecewise(t, bs, switch_times)
        N = 1.0
        omega = 0.0
    else:
        raise ValueError(f"unknown model_type {model_type!r}")

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        S, I, R = y
        b = beta(t)
        # Frequency-dependent mass action: flux = beta * S * I / N. With N = 1
        # (fractional) this reduces to the legacy beta * S * I exactly.
        infection = b * S * I / N
        waning = omega * R
        return np.array([
            -infection + waning,
            infection - gamma * I,
            gamma * I - waning,
        ])

    S0 = N - I0
    t_eval = np.arange(t_start, t_start + n_steps + 1, 1.0)
    sol = solve_ivp(
        rhs, (t_start, t_start + n_steps),
        y0=[S0, I0, 0.0],
        t_eval=t_eval, method="LSODA",
        rtol=1e-8, atol=1e-10,
    )
    S, I, R = sol.y
    beta_vals = np.array([beta(t) for t in sol.t])
    H = mult * beta_vals * S * I / N
    return SimulationResult(t=sol.t, S=S, I=I, R=R, H_weekly=H)


def predict_weekly(
    params: Mapping[str, float], n_weeks: int,
    *, model_type: str = "sir_piecewise",
) -> np.ndarray:
    """Convenience: just the H_weekly trajectory at integer weeks 0..n_weeks-1.

    Note: returns n_weeks values, *not* n_weeks+1 — aligns with how the
    legacy .exp files are indexed (`#time` 0..N-1).
    """
    res = simulate(params, n_weeks - 1, model_type=model_type)
    return res.H_weekly[:n_weeks]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_free(params: Mapping[str, float]) -> dict[str, float]:
    """Accept both `b0` and `b0__FREE` keys; return canonical short names."""
    return {(k.replace("__FREE", "") if k.endswith("__FREE") else k): v
            for k, v in params.items()}


def _extract_piecewise(p: dict[str, float]) -> tuple[list[float], list[float]]:
    """Find b0, b1, ... and t0, t1, ... return (bs, cumulative_switches).

    Switch times in the BNGL function are cumulative:
        b0 is in [t0,        t0+t1)
        b1 is in [t0+t1,     t0+t1+t2)
        ...
    """
    bs: list[float] = []
    ts: list[float] = []
    k = 0
    while f"b{k}" in p:
        bs.append(float(p[f"b{k}"]))
        if f"t{k}" not in p:
            raise KeyError(f"missing t{k} for b{k}")
        ts.append(float(p[f"t{k}"]))
        k += 1
    if not bs:
        raise ValueError("no b0 in params")
    # Cumulative switch times: t0, t0+t1, ... t0+t1+...+t_{K-1}
    switches = list(np.cumsum(ts))
    return bs, switches


def _beta_piecewise(t: float, bs: list[float], switches: list[float]) -> float:
    """Piecewise-constant beta. Returns 0 before t < switches[0]."""
    if t < switches[0]:
        return 0.0
    # bs has K entries; switches has K cumulative times.
    # bs[k] applies in [switches[k], switches[k+1]); bs[-1] applies for t>=switches[-1].
    for k in range(len(bs) - 1):
        if switches[k] <= t < switches[k + 1]:
            return bs[k]
    return bs[-1]


def _extract_logistic(
    p: dict[str, float],
) -> tuple[float, list[float], list[float], float]:
    """Find b0, sw, and db1.. / tc1.. ; return (b0, dbs, centers, sw).

    Mirrors `bngl_files.build_logistic_beta`:
        beta(t) = b0 + sum_k db_k / (1 + exp(-(t - tc_k)/sw))
    """
    b0 = float(p["b0"])
    sw = float(p["sw"])
    dbs: list[float] = []
    centers: list[float] = []
    k = 1
    while f"db{k}" in p:
        dbs.append(float(p[f"db{k}"]))
        if f"tc{k}" not in p:
            raise KeyError(f"missing tc{k} for db{k}")
        centers.append(float(p[f"tc{k}"]))
        k += 1
    if not dbs:
        raise ValueError("no db1 in params (need at least one transition)")
    return b0, dbs, centers, sw


def _beta_logistic(
    t: float, b0: float, dbs: list[float], centers: list[float], sw: float,
) -> float:
    """Smooth sum-of-logistics beta: b0 + sum_k db_k * sigmoid((t-tc_k)/sw)."""
    val = b0
    for db, tc in zip(dbs, centers):
        val += db / (1.0 + np.exp(-(t - tc) / sw))
    return float(val)
