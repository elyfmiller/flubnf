"""Build predictive trajectories from ANY PyBNF sampler's parameter samples.

WHY THIS EXISTS
---------------
`output_noise_trajectory` -- the thing this whole forecast pipeline consumes --
is implemented ONLY inside PyBNF's Adaptive_MCMC class (all references sit at
algorithms.py:2552-2868, and that class spans 2495-2990). So `dream`, `pt`,
`mh` and `sa` emit posterior PARAMETER samples but no predictive trajectories,
and are unusable by this project as shipped.

That matters because the sampler defect measured here is exactly what those
algorithms exist to fix: chains accept at a healthy 15.1% yet each explores 1.4%
of the phi1 range, with four chains sealed in four separate modes, plus four
documented degeneracies. Adaptive Metropolis proposes from ONE Gaussian fitted
to the local mode and structurally cannot cross a barrier or follow a ridge.

This module closes the gap: take the parameter draws, simulate each forward, and
apply the negative-binomial observation noise -- which is what Adaptive_MCMC
does internally.

THE TEMPERING TRAP
------------------
Parallel tempering writes ALL replicates to the same file. With
`beta = 1.0 0.5 0.25 0.125` the output holds run0..run3 at 400 draws each, and
ONLY run0 (beta = 1) samples the target distribution. Pooling them would
silently mix tempered chains into the posterior -- flatter, wider, and wrong.
`target_run` exists to prevent that and defaults to run0.

STATUS OF EACH ALGORITHM (measured 2026-08-11, Alabama 2026-01-24, 400 iters)
    am     works natively, emits trajectories
    pt     rc=0, 1600 draws across 4 replicates -- usable via this bridge
    dream  rc=1, samples.txt contains ONLY the header; produced no samples at
           all. Needs separate diagnosis before it can be evaluated.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .simulate_sihrs import simulate_sihrs
from .sihrs_fit import GAMMAH_PER_WEEK, OMEGA_PER_WEEK, RHO_IHR, StateSetup


def read_samples(path, target_run: Optional[str] = "run0",
                 burn_frac: float = 0.25) -> pd.DataFrame:
    """Posterior draws from a PyBNF sorted_params/samples file.

    `target_run` filters to the beta=1 replicate for parallel tempering; pass
    None for algorithms that write a single chain.
    """
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    df = pd.read_csv(p, sep="\t", comment=None)
    df.columns = [c.strip().lstrip("#").strip() for c in df.columns]
    label = next((c for c in df.columns if c.lower() in ("simulation", "name")), None)
    if label is None:
        return pd.DataFrame()
    df = df[df[label].astype(str).str.contains("iter", na=False)]
    if df.empty:
        return df
    df["_iter"] = df[label].astype(str).str.extract(r"iter(\d+)").astype(float)
    df["_run"] = df[label].astype(str).str.extract(r"(run\d+)")
    if target_run is not None and df["_run"].notna().any():
        df = df[df["_run"] == target_run]
    if df.empty:
        return df
    hi = df["_iter"].max()
    return df[df["_iter"] >= burn_frac * hi]


def predictive_from_samples(setup: StateSetup, samples: pd.DataFrame,
                            horizons=(0, 1, 2, 3, 4), max_draws: int = 400,
                            seed: int = 0) -> Optional[dict]:
    """Simulate each draw forward and add negative-binomial observation noise.

    Returns {str(h): [draws]} matching the shape Adaptive_MCMC writes, so the
    rest of the pipeline is unchanged.
    """
    if samples is None or samples.empty:
        return None
    cols = {c.replace("__FREE", ""): c for c in samples.columns}
    need = ("Reff", "eps1", "phi1", "eps2", "phi2", "mult", "r")
    if any(k not in cols for k in need):
        return None
    rng = np.random.default_rng(seed)
    idx = np.arange(len(samples))
    if len(idx) > max_draws:
        idx = rng.choice(idx, size=max_draws, replace=False)
    n = setup.n_obs
    out = {str(h): [] for h in horizons}
    for i in idx:
        row = samples.iloc[int(i)]
        try:
            p = dict(N=setup.population, s0=setup.s0, i0=setup.i0,
                     gamma=setup.gamma, rho=RHO_IHR, gammaH=GAMMAH_PER_WEEK,
                     omega=OMEGA_PER_WEEK,
                     R0=float(row[cols["Reff"]]) / setup.s0,
                     eps1=float(row[cols["eps1"]]), phi1=float(row[cols["phi1"]]),
                     eps2=float(row[cols["eps2"]]), phi2=float(row[cols["phi2"]]),
                     mult=float(row[cols["mult"]]),
                     impr=float(row[cols["impr"]]) if "impr" in cols else 1e-7)
            res = simulate_sihrs(p, n_weeks=n + max(horizons) + 2)
        except Exception:
            continue
        h_w = np.asarray(res.H_weekly, float)
        if not np.all(np.isfinite(h_w)):
            continue
        r_disp = float(row[cols["r"]])
        if not np.isfinite(r_disp) or r_disp <= 0:
            continue
        for h in horizons:
            j = n - 1 + h
            if j >= len(h_w):
                continue
            mu = max(float(h_w[j]), 1e-9)
            # NB parameterised by mean mu and dispersion r, matching
            # neg_bin_dynamic: p = r/(r+mu)
            out[str(h)].append(float(rng.negative_binomial(
                r_disp, r_disp / (r_disp + mu))))
    if not out.get("1"):
        return None
    return out
